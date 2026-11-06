"""AI 도우미 (OpenRouter). 가짜 OpenRouter 로 확인한다. 진짜 키·네트워크는 쓰지 않는다."""
import json
import os
import stat

from fake_openrouter import FakeOpenRouter
from server_fixture import ServerTestCase
from test_public_api import ALL_TYPES, GOOD

KEY = "sk-or-v1-test-abcd1234"
JSON_HEADERS = {"Content-Type": "application/json"}


class AiTestCase(ServerTestCase):
    @classmethod
    def setUpClass(cls):
        cls.fake = FakeOpenRouter()
        cls.server_env = {"OPENROUTER_BASE_URL": cls.fake.url}
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.fake.stop()

    def setUp(self):
        self.fake.requests.clear()
        self.fake.status = 200
        self.fake.reply = "답"

    def save(self, body, headers=None):
        h = dict(self.srv.ADMIN_HEADERS)
        h.update(headers or {})
        return self.srv.post_json("/api/adminAiSave", body, headers=h)[1]

    def fill(self, code, text, cookie=None):
        h = dict(JSON_HEADERS, **({"Cookie": cookie} if cookie else {}))
        return self.srv.post_json("/api/aiFill?code=" + code, {"text": text}, headers=h)[1]

    def ask(self, code, question, history=None):
        return self.srv.post_json("/api/aiAsk?code=" + code, {"question": question, "history": history or []},
                                  headers=JSON_HEADERS)[1]


class AiOffTest(AiTestCase):
    def test_disabled_without_key(self):
        _, code = self.srv.create_survey(ALL_TYPES)
        self.assertEqual(self.srv.get_json("/api/aiStatus")[1], {"result": "OK", "enabled": False})
        off = {"result": "FAIL", "msg": "AI 도우미가 꺼져 있습니다. 진행자에게 문의하세요."}
        self.assertEqual(self.fill(code, "좋아요"), off)
        self.assertEqual(self.ask(code, "요약해줘"), off)
        self.assertEqual(self.fake.requests, [])

    def test_settings_need_admin(self):
        for headers in [{"X-Requested-With": ""}, {"X-Forwarded-For": "1.2.3.4"}, {"Origin": "http://evil.example"}]:
            with self.subTest(headers=headers):
                self.assertEqual(self.save({"key": KEY}, headers)["result"], "FAIL")
        self.assertEqual(self.srv.get_json("/api/adminAi", host="example.com")[1]["result"], "FAIL")
        self.assertFalse(os.path.exists(os.path.join(self.srv.dir, "ai_settings.json")))

    def test_bad_key_or_model_rejected(self):
        self.assertEqual(self.save({"key": "sk or 공백"})["msg"], "API 키 모양이 올바르지 않습니다.")
        self.assertIn("모델 이름이 올바르지 않습니다", self.save({"key": KEY, "model": "a b"})["msg"])


class AiOnTest(AiTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        h = dict(cls.srv.ADMIN_HEADERS)
        res = cls.srv.post_json("/api/adminAiSave", {"key": KEY, "model": "anthropic/claude-haiku-5.5"}, headers=h)[1]
        assert res["result"] == "OK", res
        cls.sid, cls.code = cls.srv.create_survey(ALL_TYPES, title="AI 설문")

    def test_key_is_saved_privately_and_never_returned(self):
        path = os.path.join(self.srv.dir, "ai_settings.json")
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        _, h, body = self.srv.request("GET", "/api/adminAi")
        res = json.loads(body)
        self.assertEqual((res["configured"], res["keyHint"], res["model"], res["source"]),
                         (True, "…1234", "anthropic/claude-haiku-5.5", "file"))
        self.assertNotIn(KEY.encode(), body)
        self.assertEqual(self.srv.get_json("/api/aiStatus")[1], {"result": "OK", "enabled": True})
        self.assertEqual(self.srv.request("GET", "/ai_settings.json")[0], 404)

    def test_saving_model_only_keeps_key(self):
        res = self.save({"key": "", "model": "anthropic/claude-haiku-5.5"})
        self.assertEqual((res["configured"], res["keyHint"]), (True, "…1234"))

    def test_fill_sends_questions_and_keeps_only_valid_answers(self):
        self.fake.reply = "```json\n" + json.dumps({"answers": {
            "t": "홍길동", "r": "9", "s": "__other__", "s#other": "C", "m": ["X", "없는것", "Z"],
            "yn": "몰라", "d": "2026-1-5", "zz": "없는 문항"}, "comment": "확인해 주세요"}, ensure_ascii=False) + "\n```"
        res = self.fill(self.code, "회의가 많아요")
        self.assertEqual(res["result"], "OK", res)
        self.assertEqual(res["answers"], {"t": "홍길동", "s": "__other__", "s#other": "C", "m": ["X", "Z"],
                                          "d": "2026-01-05"})
        self.assertEqual(res["filled"], ["t", "s", "m", "d"])
        self.assertEqual(res["comment"], "확인해 주세요")
        headers, body = self.fake.requests[-1]
        self.assertEqual(headers["authorization"], "Bearer " + KEY)
        self.assertEqual(body["model"], "anthropic/claude-haiku-5.5")
        self.assertIn("회의가 많아요", body["messages"][-1]["content"])
        self.assertIn('"id": "yn"', body["messages"][-1]["content"])
        self.assertEqual(self.srv.get_json("/api/getSurvey?code=" + self.code)[1]["data"]["cnt"], 0)   # 저장 안 함

    def test_fill_refuses_without_calling_ai(self):
        _, closed = self.srv.create_survey(ALL_TYPES, open_=False)
        self.assertEqual(self.fill(closed, "x")["msg"], "마감된 설문입니다.")
        self.assertEqual(self.fill(self.code, "x", cookie="sv_%s=1" % self.code)["msg"], "이미 이 설문에 응답하셨습니다.")
        self.assertEqual(self.fill(self.code, "   ")["msg"], "하고 싶은 말을 입력하세요.")
        self.assertEqual(self.fill(self.code, "가" * 2001)["msg"], "2000자까지 입력할 수 있습니다.")
        self.assertEqual(self.fill("zzzzzzz", "x")["msg"], "설문을 찾을 수 없습니다.")
        self.assertEqual(self.fake.requests, [])

    def test_fill_unreadable_reply(self):
        self.fake.reply = "잘 모르겠어요"
        self.assertEqual(self.fill(self.code, "x")["msg"], "AI 답을 이해하지 못했습니다. 조금 더 구체적으로 써 보세요.")

    def test_ask_sends_results_and_history(self):
        sid, code = self.srv.create_survey(ALL_TYPES, title="결과 질문")
        self.srv.answer(code, dict(GOOD, ta="회의 줄여 주세요"))
        self.fake.reply = "- 평균 4점입니다"
        history = [{"role": "user", "content": "q%d" % i} for i in range(10)] + [{"role": "system", "content": "x"}]
        res = self.ask(code, "요약해줘", history)
        self.assertEqual(res, {"result": "OK", "answer": "- 평균 4점입니다"})
        _, body = self.fake.requests[-1]
        messages = body["messages"]
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("회의 줄여 주세요", messages[0]["content"])   # 주관식 답 포함
        self.assertIn('"responses": 1', messages[0]["content"])
        self.assertEqual([m["content"] for m in messages[1:]], ["q4", "q5", "q6", "q7", "q8", "q9", "요약해줘"])

    def test_upstream_errors_become_messages(self):
        for status, msg in [(401, "AI API 키가 올바르지 않습니다. 관리 화면에서 키를 확인하세요."),
                            (402, "AI 크레딧이 부족합니다. OpenRouter 잔액을 확인하세요."),
                            (500, "AI 서비스 오류가 났습니다 (HTTP 500).")]:
            with self.subTest(status=status):
                self.fake.status = status
                _, h, body = self.srv.request("POST", "/api/aiAsk?code=" + self.code,
                                              body={"question": "?"}, headers=JSON_HEADERS)
                self.assertEqual(json.loads(body), {"result": "FAIL", "msg": msg})
                self.assertNotIn(KEY.encode(), body)

    def test_admin_connection_test(self):
        self.fake.reply = "연결됨"
        res = self.srv.post_json("/api/adminAiTest", {}, headers=self.srv.ADMIN_HEADERS)[1]
        self.assertEqual(res, {"result": "OK", "answer": "연결됨", "model": "anthropic/claude-haiku-5.5"})

    def test_z_clear_key_turns_off(self):   # 이름의 z: 이 클래스에서 마지막에 돈다
        res = self.save({"clearKey": True, "model": "anthropic/claude-haiku-5.5"})
        self.assertEqual((res["configured"], res["keyHint"]), (False, None))
        self.assertEqual(self.srv.get_json("/api/aiStatus")[1]["enabled"], False)


class AiRateLimitTest(AiTestCase):
    def test_calls_per_minute_are_limited(self):
        self.save({"key": KEY})
        _, code = self.srv.create_survey(ALL_TYPES)
        results = [self.ask(code, "?")["result"] for _ in range(31)]
        self.assertEqual(results[:30], ["OK"] * 30)
        self.assertEqual(self.ask(code, "?"), {"result": "FAIL", "msg": "AI 요청이 많습니다. 잠시 뒤에 다시 해 주세요."})
        self.assertEqual(len(self.fake.requests), 30)
