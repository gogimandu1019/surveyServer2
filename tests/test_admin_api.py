"""관리자 API: 접근 제한, 목록/조회, 신규·수정 검증, 오픈/마감/복사/초기화/삭제."""
from server_fixture import ServerTestCase
from test_pages import PROXY_HEADERS
from test_public_api import ALL_TYPES, GOOD

FORBIDDEN = {"result": "FAIL", "msg": "관리 기능은 이 노트북에서만 쓸 수 있습니다."}
NOT_FOUND = {"result": "FAIL", "msg": "설문을 찾을 수 없습니다."}


class AdminAccessTest(ServerTestCase):
    def test_read_api_needs_localhost(self):
        for path in ["/api/adminList", "/api/adminGet?id=1"]:
            with self.subTest(path=path):
                self.assertEqual(self.srv.get_json(path)[1]["result"], "OK")
                status, res = self.srv.get_json(path, host="example.com")
                self.assertEqual((status, res), (403, FORBIDDEN))
                for hdr in PROXY_HEADERS:
                    status, res = self.srv.get_json(path, headers={hdr: "1.2.3.4"})
                    self.assertEqual((status, res), (403, FORBIDDEN), hdr)

    def test_write_api_needs_ajax_header_and_local_origin(self):
        body = {"cmd": "close", "id": 1}
        ok = self.srv.admin(body)
        self.assertEqual(ok, (200, {"result": "OK"}))
        cases = [
            {"X-Requested-With": "nope"},
            {"Origin": "http://evil.example"},
            {"Origin": "http://localhost.evil.example"},
            {"X-Forwarded-For": "1.2.3.4"},
        ]
        for h in cases:
            with self.subTest(headers=h):
                self.assertEqual(self.srv.admin(body, headers=h), (403, FORBIDDEN))
        # 헤더 없이
        status, res = self.srv.post_json("/api/adminProc", body)
        self.assertEqual((status, res), (403, FORBIDDEN))
        # 허용되는 Origin
        for origin in ["http://localhost:1234", "https://127.0.0.1", "http://localhost"]:
            with self.subTest(origin=origin):
                self.assertEqual(self.srv.admin(body, headers={"Origin": origin})[1], {"result": "OK"})
        # 다른 Host
        status, res = self.srv.post_json("/api/adminProc", body, host="example.com",
                                         headers=self.srv.ADMIN_HEADERS)
        self.assertEqual((status, res), (403, FORBIDDEN))

    def test_forbidden_request_changes_nothing(self):
        sid, _ = self.srv.create_survey(ALL_TYPES)
        self.srv.admin({"cmd": "delete", "id": sid}, headers={"X-Requested-With": ""})
        self.assertEqual(self.srv.db("SELECT count(*) FROM surveys WHERE id=?", (sid,))[0][0], 1)


class AdminReadTest(ServerTestCase):
    def test_list_and_get(self):
        sid, code = self.srv.create_survey(ALL_TYPES, title="목록", desc="d", open_=False)
        self.srv.admin({"cmd": "open", "id": sid})
        self.srv.answer(code, GOOD)
        self.srv.admin({"cmd": "close", "id": sid})

        status, res = self.srv.get_json("/api/adminList")
        self.assertEqual(status, 200)
        self.assertEqual(set(res), {"result", "data", "localBase", "lanBase"})
        self.assertEqual(res["localBase"], "http://localhost:%d" % self.srv.port)
        self.assertIsNone(res["lanBase"])           # HOST=127.0.0.1 로 띄웠으므로
        self.assertEqual(len(res["data"]), 2)       # 예시 설문 + 방금 만든 것 (최신순)
        self.assertEqual(res["data"][0], {"id": sid, "code": code, "title": "목록", "desc": "d",
                                          "q": ALL_TYPES, "open": 0, "cnt": 1})
        self.assertEqual(res["data"][1]["id"], 1)

        _, one = self.srv.get_json("/api/adminGet?id=%d" % sid)
        self.assertEqual(one, {"result": "OK", "data": res["data"][0]})

    def test_get_bad_id(self):
        for q in ["?id=999", "?id=abc", "", "?id="]:
            with self.subTest(q=q):
                self.assertEqual(self.srv.get_json("/api/adminGet" + q)[1], NOT_FOUND)


class AdminCreateUpdateTest(ServerTestCase):
    def survey(self, sid):
        return self.srv.get_json("/api/adminGet?id=%d" % sid)[1]["data"]

    def test_new_is_closed_and_normalized(self):
        status, res = self.srv.admin({"cmd": "new", "title": "  " + "제" * 250 + " ", "desc": " 설명 ", "q": [
            {"id": "ok_1", "type": "text", "label": "  질문  ", "required": 1, "extra": "x"},
            {"id": "bad id!", "type": "rating", "label": "점수", "max": 7},
            {"id": "ok_1", "type": "rating", "label": "십점", "max": "10"},
            {"type": "multi", "label": "선택", "options": [" A ", "A", "", "__other__", "B"], "allowOther": "yes"},
            {"id": "y", "type": "yesno", "label": "yn", "options": ["무시됨"]},
        ]})
        self.assertEqual(status, 200)
        self.assertEqual(set(res), {"result", "id", "code"})
        self.assertRegex(res["code"], r"^[a-z0-9]{7}$")
        s = self.survey(res["id"])
        self.assertEqual(s["open"], 0)
        self.assertEqual(s["title"], ("제" * 250)[:200])
        self.assertEqual(s["desc"], "설명")
        q = s["q"]
        self.assertEqual(q[0], {"id": "ok_1", "type": "text", "label": "질문", "required": True})
        self.assertRegex(q[1]["id"], r"^q[0-9a-f]{8}$")      # 잘못된 id 는 새로 만듦
        self.assertEqual({k: q[1][k] for k in ("type", "required", "max")}, {"type": "rating", "required": False, "max": 5})
        self.assertRegex(q[2]["id"], r"^q[0-9a-f]{8}$")      # 중복 id 도 새로 만듦
        self.assertEqual(q[2]["max"], 10)
        self.assertEqual(q[3]["options"], ["A", "B"])
        self.assertIs(q[3]["allowOther"], True)
        self.assertEqual(q[4], {"id": "y", "type": "yesno", "label": "yn", "required": False})

    def test_validation_messages_for_new_and_update(self):
        sid, _ = self.srv.create_survey(ALL_TYPES)
        one = [{"id": "a", "type": "text", "label": "a"}]
        cases = [
            ({"title": "  ", "q": one}, "설문 제목을 입력하세요."),
            ({"title": "t"}, "문항을 하나 이상 추가하세요."),
            ({"title": "t", "q": []}, "문항을 하나 이상 추가하세요."),
            ({"title": "t", "q": "x"}, "문항을 하나 이상 추가하세요."),
            ({"title": "t", "q": one * 101}, "문항은 100개까지 만들 수 있습니다."),
            ({"title": "t", "q": one + ["x"]}, "2번 문항이 올바르지 않습니다."),
            ({"title": "t", "q": [{"type": "slider", "label": "a"}]}, "1번 문항의 종류가 올바르지 않습니다."),
            ({"title": "t", "q": [{"type": "text", "label": "  "}]}, "1번 문항의 질문을 입력하세요."),
            ({"title": "t", "q": one + [{"type": "single", "label": "s", "options": ["", " "]}]},
             "2번 문항에 선택지를 하나 이상 입력하세요."),
            ({"title": "t", "q": [{"type": "multi", "label": "s", "options": "AB"}]},
             "1번 문항에 선택지를 하나 이상 입력하세요."),
        ]
        for data, msg in cases:
            for cmd in ("new", "update"):
                with self.subTest(cmd=cmd, msg=msg):
                    body = dict(data, cmd=cmd)
                    if cmd == "update":
                        body["id"] = sid
                    self.assertEqual(self.srv.admin(body), (200, {"result": "FAIL", "msg": msg}))
        self.assertEqual(self.survey(sid)["q"], ALL_TYPES)

    def test_update(self):
        sid, code = self.srv.create_survey(ALL_TYPES)
        before = self.srv.db("SELECT slug, created_at FROM surveys WHERE id=?", (sid,))
        new_q = ALL_TYPES[:2]
        self.assertEqual(self.srv.admin({"cmd": "update", "id": sid, "title": "새 제목", "desc": "새 설명", "q": new_q}),
                         (200, {"result": "OK"}))
        s = self.survey(sid)
        self.assertEqual((s["title"], s["desc"], s["q"], s["code"]), ("새 제목", "새 설명", new_q, code))
        self.assertEqual(self.srv.db("SELECT slug, created_at FROM surveys WHERE id=?", (sid,)), before)

    def test_update_with_responses_allows_only_title(self):
        sid, code = self.srv.create_survey(ALL_TYPES)
        self.srv.answer(code, GOOD)
        res = self.srv.admin({"cmd": "update", "id": sid, "title": "x", "desc": "", "q": ALL_TYPES[:1]})
        self.assertEqual(res, (200, {"result": "FAIL",
                                     "msg": "응답이 있는 설문은 문항을 바꿀 수 없습니다. 복사해서 새 설문으로 만드세요."}))
        res = self.srv.admin({"cmd": "update", "id": sid, "title": "제목만", "desc": "", "q": ALL_TYPES})
        self.assertEqual(res, (200, {"result": "OK"}))
        self.assertEqual(self.survey(sid)["title"], "제목만")

    def test_id_errors(self):
        self.assertEqual(self.srv.admin({"cmd": "open", "id": 999}), (200, NOT_FOUND))
        self.assertEqual(self.srv.admin({"cmd": "update", "id": "abc", "title": "t", "q": ALL_TYPES}), (200, NOT_FOUND))
        self.assertEqual(self.srv.admin({"cmd": "bogus", "id": 1}), (200, {"result": "FAIL", "msg": "알 수 없는 명령"}))


class AdminActionsTest(ServerTestCase):
    def test_open_close(self):
        sid, code = self.srv.create_survey(ALL_TYPES, open_=False)
        self.assertEqual(self.srv.admin({"cmd": "open", "id": sid}), (200, {"result": "OK"}))
        self.assertEqual(self.srv.get_json("/api/getSurvey?code=" + code)[1]["data"]["open"], 1)
        self.assertEqual(self.srv.admin({"cmd": "close", "id": str(sid)}), (200, {"result": "OK"}))
        self.assertEqual(self.srv.get_json("/api/getSurvey?code=" + code)[1]["data"]["open"], 0)

    def test_copy(self):
        sid, code = self.srv.create_survey(ALL_TYPES, title="원본", desc="설명")
        self.srv.answer(code, GOOD)
        status, res = self.srv.admin({"cmd": "copy", "id": sid})
        self.assertEqual(set(res), {"result", "id", "code"})
        self.assertNotEqual(res["code"], code)
        _, got = self.srv.get_json("/api/adminGet?id=%d" % res["id"])
        self.assertEqual(got["data"], {"id": res["id"], "code": res["code"], "title": "원본 (복사본)",
                                       "desc": "설명", "q": ALL_TYPES, "open": 0, "cnt": 0})

    def test_reset(self):
        sid, code = self.srv.create_survey(ALL_TYPES)
        self.srv.answer(code, GOOD)
        self.srv.answer(code, GOOD)
        self.assertEqual(self.srv.admin({"cmd": "reset", "id": sid}), (200, {"result": "OK"}))
        self.assertEqual(self.srv.get_json("/api/getSurvey?code=" + code)[1]["data"]["cnt"], 0)
        self.assertEqual(self.srv.db("SELECT count(*) FROM responses WHERE survey_id=?", (sid,))[0][0], 0)
        self.assertEqual(self.srv.db("SELECT count(*) FROM answers WHERE response_id NOT IN (SELECT id FROM responses)")[0][0], 0)
        self.assertEqual(self.srv.db("SELECT count(*) FROM surveys WHERE id=?", (sid,))[0][0], 1)

    def test_delete_removes_survey_and_its_responses_only(self):
        keep_id, keep_code = self.srv.create_survey(ALL_TYPES)
        sid, code = self.srv.create_survey(ALL_TYPES)
        self.srv.answer(keep_code, GOOD)
        self.srv.answer(code, GOOD)
        self.assertEqual(self.srv.admin({"cmd": "delete", "id": sid}), (200, {"result": "OK"}))
        self.assertEqual(self.srv.get_json("/api/getSurvey?code=" + code)[1], NOT_FOUND)
        self.assertEqual(self.srv.db("SELECT count(*) FROM responses WHERE survey_id=?", (sid,))[0][0], 0)
        self.assertEqual(self.srv.db("SELECT count(*) FROM responses WHERE survey_id=?", (keep_id,))[0][0], 1)
        self.assertEqual(self.srv.db("SELECT count(*) FROM answers WHERE response_id NOT IN (SELECT id FROM responses)")[0][0], 0)
        self.assertEqual(self.srv.admin({"cmd": "delete", "id": sid}), (200, NOT_FOUND))
