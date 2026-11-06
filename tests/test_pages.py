"""화면 파일 서빙, 관리 화면 접근 제한, 공통 헤더, 404."""
import json
import os

from server_fixture import ROOT, ServerTestCase

PROXY_HEADERS = ["X-Forwarded-For", "Forwarded", "X-Forwarded-Host",
                 "Cf-Connecting-Ip", "X-Real-Ip", "Ngrok-Trace-Id"]
ADMIN_PAGE_403 = "관리 화면은 설문 서버를 실행 중인 노트북에서 http://localhost 로 접속했을 때만 열립니다."


def static_file(name):
    with open(os.path.join(ROOT, "static", name), "rb") as f:
        return f.read()


class PublicPagesTest(ServerTestCase):
    def test_only_listed_files_are_served(self):
        """static/ 안의 다른 파일(CLAUDE.md 등)은 내보내지 않는다."""
        for path in ["/CLAUDE.md", "/static/CLAUDE.md", "/static/common.js", "/../server.py"]:
            with self.subTest(path=path):
                self.assertEqual(self.srv.request("GET", path)[0], 404)

    def test_pages_do_not_use_eval_or_inline_handlers(self):
        """smells: static 공통 — eval() JSON 파싱, onclick="..." 문자열 로직."""
        import re
        for name in ["index.html", "survey.html", "result.html", "admin.html", "admin_edit.html", "common.js"]:
            with self.subTest(name=name):
                text = static_file(name).decode("utf-8")
                self.assertNotRegex(text, r"\beval\(")
                self.assertNotRegex(text, r"\son[a-z]+=[\"']")
                self.assertNotIn("XHTML", text)

    def test_pages_are_served_as_is(self):
        cases = [
            ("/", "index.html", "text/html; charset=utf-8"),
            ("/index.html", "index.html", "text/html; charset=utf-8"),
            ("/survey.html", "survey.html", "text/html; charset=utf-8"),
            ("/survey.html?code=abc", "survey.html", "text/html; charset=utf-8"),
            ("/result.html", "result.html", "text/html; charset=utf-8"),
            ("/style.css", "style.css", "text/css; charset=utf-8"),
            ("/common.js", "common.js", "text/javascript; charset=utf-8"),
        ]
        for path, name, ctype in cases:
            with self.subTest(path=path):
                status, h, body = self.srv.request("GET", path)
                self.assertEqual(status, 200)
                self.assertEqual(h["content-type"], ctype)
                self.assertEqual(body, static_file(name))

    def test_common_headers(self):
        for path in ["/", "/api/getList", "/no-such-page"]:
            with self.subTest(path=path):
                _, h, _ = self.srv.request("GET", path)
                self.assertEqual(h["cache-control"], "no-store")
                self.assertEqual(h["x-content-type-options"], "nosniff")

    def test_unknown_path_is_json_404(self):
        for method, path in [("GET", "/nope"), ("GET", "/api/nope"),
                             ("GET", "/api/saveAnswer"), ("POST", "/api/getList"),
                             ("POST", "/")]:
            with self.subTest(method=method, path=path):
                status, h, body = self.srv.request(method, path, body=b"" if method == "POST" else None)
                self.assertEqual(status, 404)
                self.assertTrue(h["content-type"].startswith("application/json"))
                self.assertEqual(json.loads(body), {"result": "FAIL", "msg": "not found"})


class AdminPagesTest(ServerTestCase):
    def test_admin_pages_open_from_localhost(self):
        for name in ["admin.html", "admin_edit.html"]:
            for host in ["localhost:%d" % self.srv.port, "127.0.0.1:%d" % self.srv.port, "localhost"]:
                with self.subTest(name=name, host=host):
                    status, h, body = self.srv.request("GET", "/" + name, host=host)
                    self.assertEqual(status, 200)
                    self.assertEqual(h["content-type"], "text/html; charset=utf-8")
                    self.assertEqual(body, static_file(name))

    def assert_page_blocked(self, path, **kw):
        status, h, body = self.srv.request("GET", path, **kw)
        self.assertEqual(status, 403)
        self.assertEqual(h["content-type"], "text/plain; charset=utf-8")
        self.assertEqual(body.decode("utf-8"), ADMIN_PAGE_403)

    def test_admin_pages_blocked_for_other_host_header(self):
        for host in ["example.com", "192.168.0.10:8000", ""]:
            with self.subTest(host=host):
                self.assert_page_blocked("/admin.html", host=host)

    def test_admin_pages_blocked_behind_proxy(self):
        for hdr in PROXY_HEADERS:
            with self.subTest(header=hdr):
                self.assert_page_blocked("/admin_edit.html", headers={hdr: "1.2.3.4"})
