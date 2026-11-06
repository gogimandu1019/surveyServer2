"""docs/kb/smells.md 의 문제 중 '일부러 남겨 둔' 동작을 고정한 테스트.

2026-11-06 에 고친 것들은 test_fixed_smells.py 로 옮겼다. 여기 남은 것은 고치지 않기로 한 것이다.
- HTTP 200 + FAIL: 화면과 맞춘 API 계약 (결정-기록.md)
- 쿠키로만 막는 중복 응답: 익명성과 맞바꾼 설계 (결정-기록.md)
바꾸기로 결정하면 이 테스트가 깨지는 게 정상이다. 그때 테스트를 새 동작에 맞게 고친다.
"""
from server_fixture import ServerTestCase
from test_public_api import ALL_TYPES, GOOD


class KnownQuirksTest(ServerTestCase):
    def test_errors_are_http_200(self):
        """smells: server.py 179 외 — 실패해도 200 + result FAIL."""
        status, _, res = self.srv.answer("nope", GOOD)
        self.assertEqual((status, res["result"]), (200, "FAIL"))

    def test_duplicate_guard_is_cookie_only(self):
        """smells: server.py 185–187, 214–216 — 쿠키만 안 보내면 몇 번이든 응답 가능 (익명성 때문에 유지)."""
        sid, code = self.srv.create_survey(ALL_TYPES)
        for _ in range(3):
            self.assertEqual(self.srv.answer(code, GOOD)[2], {"result": "OK"})
        self.assertEqual(self.srv.get_json("/api/getSurvey?code=" + code)[1]["data"]["cnt"], 3)

    def test_csv_skips_responses_with_no_answers(self):
        """답이 하나도 없는 응답은 CSV 에 줄이 없고, 번호도 건너뛴다."""
        sid, code = self.srv.create_survey([{"id": "t", "type": "text", "label": "a", "required": False}])
        self.srv.answer(code, {"t": "첫째"})
        self.srv.answer(code, {})
        self.srv.answer(code, {"t": "셋째"})
        self.assertEqual(self.srv.get_json("/api/getSurvey?code=" + code)[1]["data"]["cnt"], 3)
        _, _, body = self.srv.request("GET", "/api/excel?code=" + code)
        self.assertEqual(body.decode("utf-8"), '﻿"번호","a"\r\n1,"첫째"\r\n2,"셋째"\r\n')
