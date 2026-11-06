"""테스트용 서버 실행 도구.

server.py 와 static/ 을 임시 폴더에 복사해서 빈 DB 로 띄운다.
- 진짜 survey.db 는 건드리지 않는다.
- 서버 내부 구조와 상관없이 HTTP 로만 확인하므로, 리팩터링 후에도 그대로 쓸 수 있다.
  (진입점이 server.py 이고 화면 파일이 static/ 에 있다는 것만 전제로 한다.)
"""
import http.client
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Server:
    def __init__(self, env_extra=None):
        self.dir = tempfile.mkdtemp(prefix="survey-test-")
        shutil.copy(os.path.join(ROOT, "server.py"), self.dir)
        shutil.copytree(os.path.join(ROOT, "static"), os.path.join(self.dir, "static"))
        self.port = free_port()
        env = dict(os.environ, HOST="127.0.0.1", PORT=str(self.port), PYTHONDONTWRITEBYTECODE="1",
                   OPENROUTER_BASE_URL="http://127.0.0.1:9")   # 테스트가 진짜 OpenRouter 로 나가지 않게
        env.pop("OPENROUTER_API_KEY", None)                     # 사용자 환경의 진짜 키도 쓰지 않는다
        env.update(env_extra or {})
        self.proc = subprocess.Popen(
            [sys.executable, "server.py"], cwd=self.dir, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        deadline = time.time() + 10
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError("서버가 바로 종료됨:\n" + self.proc.stderr.read().decode())
            try:
                socket.create_connection(("127.0.0.1", self.port), timeout=0.2).close()
                return
            except OSError:
                time.sleep(0.05)
        self.stop()
        raise RuntimeError("서버가 10초 안에 뜨지 않음")

    def stop(self):
        self.proc.kill()
        self.proc.wait()
        self.proc.stderr.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    @property
    def db_path(self):
        return os.path.join(self.dir, "survey.db")

    def db(self, sql, args=()):
        con = sqlite3.connect(self.db_path)
        try:
            return con.execute(sql, args).fetchall()
        finally:
            con.close()

    # ---- HTTP ---------------------------------------------------------
    def request(self, method, path, body=None, headers=None, host=None):
        """(status, headers(dict, 소문자 키), body bytes) 를 돌려준다."""
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        try:
            conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
            conn.putheader("Host", host if host is not None else "localhost:%d" % self.port)
            if isinstance(body, (dict, list)):
                body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            elif isinstance(body, str):
                body = body.encode("utf-8")
            for k, v in (headers or {}).items():
                conn.putheader(k, v)
            if body is not None:
                conn.putheader("Content-Length", str(len(body)))
            conn.endheaders(body)
            r = conn.getresponse()
            return r.status, {k.lower(): v for k, v in r.getheaders()}, r.read()
        finally:
            conn.close()

    def get_json(self, path, **kw):
        status, _, body = self.request("GET", path, **kw)
        return status, json.loads(body.decode("utf-8"))

    def post_json(self, path, data, **kw):
        status, _, body = self.request("POST", path, body=data, **kw)
        return status, json.loads(body.decode("utf-8"))

    def raw(self, data):
        """소켓으로 날것의 요청을 보내고 응답 전체(bytes)를 받는다."""
        with socket.create_connection(("127.0.0.1", self.port), timeout=15) as s:
            s.sendall(data)
            chunks = []
            while True:
                c = s.recv(65536)
                if not c:
                    break
                chunks.append(c)
            return b"".join(chunks)

    # ---- 자주 쓰는 동작 -------------------------------------------------
    ADMIN_HEADERS = {"X-Requested-With": "XMLHttpRequest", "Content-Type": "application/json"}

    def admin(self, data, headers=None):
        h = dict(self.ADMIN_HEADERS)
        h.update(headers or {})
        return self.post_json("/api/adminProc", data, headers=h)

    def create_survey(self, questions, title="테스트 설문", desc="", open_=True):
        status, res = self.admin({"cmd": "new", "title": title, "desc": desc, "q": questions})
        assert res["result"] == "OK", res
        if open_:
            self.admin({"cmd": "open", "id": res["id"]})
        return res["id"], res["code"]

    def answer(self, code, data, cookie=None):
        headers = {"Content-Type": "application/json"}
        if cookie:
            headers["Cookie"] = cookie
        status, h, body = self.request("POST", "/api/saveAnswer?code=" + code, body=data, headers=headers)
        return status, h, json.loads(body.decode("utf-8"))


class ServerTestCase(unittest.TestCase):
    """클래스마다 새 서버(빈 DB)를 하나씩 띄운다."""

    server_env = None   # 서버에 더 넘길 환경 변수 (예: 가짜 OpenRouter 주소)

    @classmethod
    def setUpClass(cls):
        cls.srv = Server(cls.server_env)

    @classmethod
    def tearDownClass(cls):
        cls.srv.stop()
