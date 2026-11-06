"""2026-11-06 에 고친 smells (docs/kb/smells.md). 예전에는 test_known_quirks.py 가 '버그 그대로' 고정하던 것들이다."""
import json

from server_fixture import ServerTestCase
from test_public_api import ALL_TYPES, GOOD


class FixedSmellsTest(ServerTestCase):
    def test_superscript_digit_rating_is_rejected(self):
        """smells: server.py 253 — 예전에는 500 + 예외 메시지 노출."""
        _, code = self.srv.create_survey(ALL_TYPES)
        for bad in ["²", "４", "٣"]:   # isdigit() 은 True 지만 ASCII 숫자가 아님
            with self.subTest(value=bad):
                status, _, res = self.srv.answer(code, dict(GOOD, r=bad))
                self.assertEqual((status, res), (200, {"result": "FAIL", "msg": "'점수' 값이 올바르지 않습니다."}))

    def test_bad_content_length_is_400(self):
        """smells: server.py 103 — 예전에는 500 + 예외 메시지 노출."""
        res = self.srv.raw(b"POST /api/getList HTTP/1.0\r\nHost: localhost\r\nContent-Length: abc\r\n\r\n")
        head, _, body = res.partition(b"\r\n\r\n")
        self.assertTrue(head.startswith(b"HTTP/1.0 400 "), head[:40])
        self.assertEqual(json.loads(body), {"result": "FAIL", "msg": "잘못된 요청입니다."})
        self.assertNotIn("서버 에러".encode("utf-8"), res)

    def test_unpadded_date_is_normalized(self):
        """smells: server.py 318 — 2026-1-5 와 2026-01-05 가 한 날짜로 집계된다."""
        sid, code = self.srv.create_survey(ALL_TYPES)
        self.srv.answer(code, dict(GOOD, d="2026-1-5"))
        self.srv.answer(code, dict(GOOD, d="2026-01-05"))
        _, res = self.srv.get_json("/api/getResult?code=" + code)
        d = [x for x in res["data"]["results"] if x["id"] == "d"][0]
        self.assertEqual([(c["key"], c["count"]) for c in d["counts"]], [("2026-01-05", 2)])

    def test_oversized_body_is_rejected(self):
        """smells: server.py 104–105 — 예전에는 빈 본문 취급이라 '필수입니다' 같은 엉뚱한 에러가 났다."""
        sid, code = self.srv.create_survey(ALL_TYPES)
        res = self.srv.raw(("POST /api/saveAnswer?code=%s HTTP/1.0\r\nHost: localhost\r\n"
                            "Content-Length: 500001\r\n\r\n" % code).encode())
        head, _, body = res.partition(b"\r\n\r\n")
        self.assertTrue(head.startswith(b"HTTP/1.0 200 "), head[:40])
        self.assertEqual(json.loads(body), {"result": "FAIL", "msg": "요청이 너무 큽니다."})
        self.assertEqual(self.srv.get_json("/api/getSurvey?code=" + code)[1]["data"]["cnt"], 0)

    def test_unknown_cmd_says_unknown(self):
        """smells: server.py 613 — 예전에는 '설문을 찾을 수 없습니다'."""
        sid, _ = self.srv.create_survey(ALL_TYPES)
        for body in [{"cmd": "bogus"}, {"cmd": "bogus", "id": sid}, {"id": sid}]:
            with self.subTest(body=body):
                self.assertEqual(self.srv.admin(body)[1], {"result": "FAIL", "msg": "알 수 없는 명령"})

    def test_csv_formula_is_neutralized(self):
        """smells: server.py 447–461 — CSV 인젝션. 수식으로 시작하는 값 앞에 ' 를 붙인다."""
        sid, code = self.srv.create_survey([{"id": "t", "type": "text", "label": "=라벨", "required": False}])
        for v in ["=1+1", "+1", "-1", "@SUM(A1)", "보통 글"]:
            self.srv.answer(code, {"t": v})
        _, _, body = self.srv.request("GET", "/api/excel?code=" + code)
        self.assertEqual(body.decode("utf-8"),
                         '﻿"번호","\'=라벨"\r\n1,"\'=1+1"\r\n2,"\'+1"\r\n3,"\'-1"\r\n4,"\'@SUM(A1)"\r\n5,"보통 글"\r\n')

    def test_query_param_is_url_decoded(self):
        """smells: server.py 171–175 — %xx 를 푼다."""
        sid, code = self.srv.create_survey(ALL_TYPES)
        encoded = "".join("%%%02x" % ord(ch) for ch in code)
        self.assertEqual(self.srv.get_json("/api/getSurvey?code=" + encoded)[1]["data"]["code"], code)
