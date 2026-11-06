"""mcp_server/survey_mcp.py — 읽기 전용 MCP 서버. stdio 로 JSON-RPC 를 주고받아 확인한다."""
import json
import os
import subprocess
import sys

from server_fixture import ROOT, ServerTestCase
from test_public_api import ALL_TYPES, GOOD

MCP = os.path.join(ROOT, "mcp_server", "survey_mcp.py")


class McpTest(ServerTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sid, cls.code = cls.srv.create_survey(ALL_TYPES, title="MCP 확인")
        cls.srv.answer(cls.code, GOOD)
        cls.srv.answer(cls.code, dict(GOOD, r="2", t="=1+1"))

    def rpc(self, *messages, db=None):
        """메시지들을 한 번에 보내고, 받은 응답들을 돌려준다."""
        env = dict(os.environ, SURVEY_DB=db or self.srv.db_path, PYTHONDONTWRITEBYTECODE="1")
        lines = "".join(m if isinstance(m, str) else json.dumps(m) + "\n" for m in messages)
        out = subprocess.run([sys.executable, MCP], input=lines.encode(), env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, check=True)
        return [json.loads(x) for x in out.stdout.decode("utf-8").splitlines()]

    def call(self, name, **arguments):
        res = self.rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                        "params": {"name": name, "arguments": arguments}})[0]["result"]
        text = res["content"][0]["text"]
        return res["isError"], text

    def test_handshake_and_tool_list(self):
        init, tools = self.rpc(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        self.assertEqual(init["result"]["protocolVersion"], "2025-06-18")
        self.assertIn("tools", init["result"]["capabilities"])
        names = [t["name"] for t in tools["result"]["tools"]]
        self.assertEqual(names, ["list_surveys", "get_survey", "get_results", "export_csv"])
        self.assertTrue(all(t["annotations"]["readOnlyHint"] for t in tools["result"]["tools"]))

    def test_list_includes_closed_surveys(self):
        _, closed = self.srv.create_survey(ALL_TYPES, title="닫힌 설문", open_=False)
        err, text = self.call("list_surveys")
        self.assertFalse(err)
        rows = {r["code"]: r for r in json.loads(text)}
        self.assertEqual((rows[self.code]["open"], rows[self.code]["responses"]), (True, 2))
        self.assertEqual(rows[closed]["open"], False)

    def test_get_survey_and_results_match_http_api(self):
        err, text = self.call("get_survey", code=self.code)
        self.assertFalse(err)
        self.assertEqual(json.loads(text)["questions"], ALL_TYPES)
        err, text = self.call("get_results", code=self.code)
        mcp = {r["id"]: r for r in json.loads(text)["results"]}
        http = {r["id"]: r for r in self.srv.get_json("/api/getResult?code=" + self.code)[1]["data"]["results"]}
        for qid in ["r", "s", "m", "yn", "d"]:   # 주관식(t, ta)은 무작위 순서라 비교하지 않음
            self.assertEqual(mcp[qid], http[qid])
        self.assertEqual(sorted(mcp["t"]["texts"]), sorted(http["t"]["texts"]))

    def test_export_csv_matches_http_without_bom(self):
        err, text = self.call("export_csv", code=self.code)
        _, _, body = self.srv.request("GET", "/api/excel?code=" + self.code)
        self.assertEqual(text, body.decode("utf-8").lstrip("﻿"))
        self.assertIn("'=1+1", text)

    def test_unknown_code_is_tool_error(self):
        for args in [{"code": "zzzzzzz"}, {}]:
            with self.subTest(args=args):
                err, text = self.call("get_results", **args)
                self.assertTrue(err)

    def test_database_is_opened_read_only(self):
        before = os.path.getmtime(self.srv.db_path)
        for name in ["list_surveys", "get_survey", "get_results", "export_csv"]:
            self.call(name, code=self.code)
        self.assertEqual(os.path.getmtime(self.srv.db_path), before)

    def test_protocol_errors(self):
        replies = self.rpc("not json\n", {"jsonrpc": "2.0", "id": 5, "method": "resources/list"},
                           {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "drop_table"}})
        self.assertEqual([r["error"]["code"] for r in replies], [-32700, -32601, -32602])

    def test_missing_db(self):
        err, text = (lambda r: (r["isError"], r["content"][0]["text"]))(self.rpc(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "list_surveys"}},
            db=os.path.join(self.srv.dir, "nope.db"))[0]["result"])
        self.assertTrue(err)
        self.assertIn("DB 파일이 없습니다", text)
        self.assertFalse(os.path.exists(os.path.join(self.srv.dir, "nope.db")))
