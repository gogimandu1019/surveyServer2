"""응답자가 쓰는 API: 목록, 설문 조회, 응답 저장, 결과, CSV 다운로드. DB 스키마도 함께 확인한다."""
import json

from server_fixture import ServerTestCase

SAMPLE_TITLE = "팀 업무 환경 설문 (예시)"
SAMPLE_DESC = "익명으로 진행됩니다. 편하게 적어주세요."
SAMPLE_Q = [
    {"id": "q1", "type": "rating", "label": "요즘 팀 분위기는 어떤가요?", "required": True, "max": 5},
    {"id": "q2", "type": "single", "label": "업무량은 어느 정도인가요?", "required": True,
     "options": ["여유 있음", "적당함", "조금 많음", "너무 많음"], "allowOther": False},
    {"id": "q3", "type": "multi", "label": "개선이 필요한 부분을 모두 골라주세요.", "required": False,
     "options": ["회의", "업무 분배", "소통 도구", "평가 기준"], "allowOther": True},
    {"id": "q4", "type": "yesno", "label": "재택근무를 늘리면 좋겠나요?", "required": True},
    {"id": "q5", "type": "date", "label": "다음 팀 워크숍으로 좋은 날짜는?", "required": False},
    {"id": "q6", "type": "textarea", "label": "자유롭게 하고 싶은 말", "required": False},
]

# 모든 문항 타입이 한 번씩 들어간 설문 (서버가 정리한 뒤의 모양과 똑같이 적어 둠)
ALL_TYPES = [
    {"id": "t", "type": "text", "label": "단답", "required": False},
    {"id": "ta", "type": "textarea", "label": "장문", "required": False},
    {"id": "r", "type": "rating", "label": "점수", "required": True, "max": 5},
    {"id": "s", "type": "single", "label": "하나", "required": True, "options": ["A", "B"], "allowOther": True},
    {"id": "m", "type": "multi", "label": "여럿", "required": False, "options": ["X", "Y", "Z"], "allowOther": True},
    {"id": "yn", "type": "yesno", "label": "예아니오", "required": False},
    {"id": "d", "type": "date", "label": "날짜", "required": False},
]
GOOD = {"t": "홍길동", "ta": "좋아요", "r": "4", "s": "A", "m": ["X", "Z"], "yn": "예", "d": "2026-11-05"}

NOT_FOUND = {"result": "FAIL", "msg": "설문을 찾을 수 없습니다."}


class SampleSurveyTest(ServerTestCase):
    """빈 DB 로 서버를 처음 띄웠을 때."""

    def test_sample_survey_is_seeded(self):
        status, res = self.srv.get_json("/api/getList")
        self.assertEqual(status, 200)
        self.assertEqual(res["result"], "OK")
        self.assertEqual(len(res["data"]), 1)
        item = res["data"][0]
        self.assertEqual(set(item), {"code", "title", "desc"})
        self.assertRegex(item["code"], r"^[a-z0-9]{7}$")
        self.assertEqual(item["title"], SAMPLE_TITLE)
        self.assertEqual(item["desc"], SAMPLE_DESC)

        status, res = self.srv.get_json("/api/getSurvey?code=" + item["code"])
        self.assertEqual(res, {"result": "OK", "data": {
            "code": item["code"], "title": SAMPLE_TITLE, "desc": SAMPLE_DESC,
            "q": SAMPLE_Q, "open": 1, "cnt": 0, "already": 0}})

    def test_schema(self):
        cols = {t: [r[1] for r in self.srv.db("PRAGMA table_info(%s)" % t)]
                for t in ("surveys", "responses", "answers")}
        self.assertEqual(cols, {
            "surveys": ["id", "slug", "title", "description", "questions", "is_open", "created_at", "updated_at"],
            "responses": ["id", "survey_id", "created_at"],
            "answers": ["response_id", "question_id", "value", "other_text"],
        })
        created, updated = self.srv.db("SELECT created_at, updated_at FROM surveys")[0]
        self.assertRegex(created, r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d$")
        self.assertEqual(created, updated)


class ListAndGetTest(ServerTestCase):
    def test_list_shows_only_open_surveys_newest_first(self):
        _, a = self.srv.create_survey(ALL_TYPES, title="A")
        _, b = self.srv.create_survey(ALL_TYPES, title="B", open_=False)
        _, c = self.srv.create_survey(ALL_TYPES, title="C", desc="설명")
        _, res = self.srv.get_json("/api/getList")
        codes = [x["code"] for x in res["data"]]
        self.assertEqual(codes[:2], [c, a])
        self.assertNotIn(b, codes)
        self.assertEqual(res["data"][0], {"code": c, "title": "C", "desc": "설명"})

    def test_get_unknown_or_missing_code(self):
        for path in ["/api/getSurvey?code=zzzzzzz", "/api/getSurvey", "/api/getSurvey?code=",
                     "/api/getSurvey?code=a'b"]:
            with self.subTest(path=path):
                status, res = self.srv.get_json(path)
                self.assertEqual(status, 200)
                self.assertEqual(res, NOT_FOUND)

    def test_get_closed_survey_still_returns_data(self):
        _, code = self.srv.create_survey(ALL_TYPES, open_=False)
        _, res = self.srv.get_json("/api/getSurvey?code=" + code)
        self.assertEqual(res["result"], "OK")
        self.assertEqual(res["data"]["open"], 0)
        self.assertEqual(res["data"]["q"], ALL_TYPES)

    def test_already_flag_follows_cookie(self):
        _, code = self.srv.create_survey(ALL_TYPES)
        for cookie, expected in [(None, 0), ("sv_%s=1" % code, 1), ("a=b; sv_%s=1; c=d" % code, 1),
                                 ("sv_other=1", 0)]:
            with self.subTest(cookie=cookie):
                h = {"Cookie": cookie} if cookie else None
                _, res = self.srv.get_json("/api/getSurvey?code=" + code, headers=h)
                self.assertEqual(res["data"]["already"], expected)


class SaveAnswerTest(ServerTestCase):
    def setUp(self):
        self.sid, self.code = self.srv.create_survey(ALL_TYPES)

    def answers_of_last_response(self):
        rid = self.srv.db("SELECT max(id) FROM responses WHERE survey_id=?", (self.sid,))[0][0]
        return self.srv.db("SELECT question_id, value, other_text FROM answers WHERE response_id=? ORDER BY rowid", (rid,))

    def test_success_sets_cookie_and_stores_rows(self):
        status, h, res = self.srv.answer(self.code, GOOD)
        self.assertEqual(status, 200)
        self.assertEqual(res, {"result": "OK"})
        self.assertEqual(h["set-cookie"], "sv_%s=1; Max-Age=31536000; Path=/; HttpOnly; SameSite=Lax" % self.code)
        self.assertEqual(self.answers_of_last_response(), [
            ("t", "홍길동", None), ("ta", "좋아요", None), ("r", "4", None), ("s", "A", None),
            ("m", "X", None), ("m", "Z", None), ("yn", "예", None), ("d", "2026-11-05", None)])
        _, got = self.srv.get_json("/api/getSurvey?code=" + self.code)
        self.assertEqual(got["data"]["cnt"], 1)

    def test_optional_blank_answers_are_not_stored(self):
        self.srv.answer(self.code, {"r": "1", "s": "B", "t": "   ", "m": [], "yn": "", "d": None})
        self.assertEqual(self.answers_of_last_response(), [("r", "1", None), ("s", "B", None)])

    def test_values_are_trimmed_and_cut(self):
        self.srv.answer(self.code, {"r": " 5 ", "s": " A ", "t": "  가" * 3000,
                                    "m": ["Z", "Z", "__other__"], "m#other": "  기" * 600})
        rows = self.answers_of_last_response()
        self.assertEqual(rows[0], ("t", ("  가" * 3000).strip()[:5000], None))
        self.assertEqual(rows[1], ("r", "5", None))
        self.assertEqual(rows[2], ("s", "A", None))
        self.assertEqual(rows[3], ("m", "Z", None))
        self.assertEqual(rows[4], ("m", "__other__", ("  기" * 600).strip()[:1000]))

    def test_other_option(self):
        self.srv.answer(self.code, {"r": "3", "s": "__other__", "s#other": "직접"})
        self.assertEqual(self.answers_of_last_response(), [("r", "3", None), ("s", "__other__", "직접")])

    def test_multi_accepts_single_string(self):
        self.srv.answer(self.code, {"r": "3", "s": "A", "m": "Y"})
        self.assertIn(("m", "Y", None), self.answers_of_last_response())

    def test_rating_and_date_edges_accepted(self):
        for extra in [{"r": "1"}, {"r": "5"}, {"r": 2}, {"d": "2024-02-29"}]:
            with self.subTest(extra=extra):
                data = dict(GOOD)
                data.update(extra)
                _, _, res = self.srv.answer(self.code, data)
                self.assertEqual(res, {"result": "OK"})

    def test_validation_messages(self):
        req = "'%s' 항목은 필수입니다."
        bad = "'%s' 값이 올바르지 않습니다."
        oth = "'%s'의 기타 내용을 입력하세요."
        cases = [
            ({}, req % "점수"),                                   # 첫 번째 필수 문항에서 멈춤
            ({"r": "4"}, req % "하나"),
            ({"r": "0", "s": "A"}, bad % "점수"),
            ({"r": "6", "s": "A"}, bad % "점수"),
            ({"r": "4.5", "s": "A"}, bad % "점수"),
            ({"r": "abc", "s": "A"}, bad % "점수"),
            ({"r": "4", "s": "C"}, bad % "하나"),
            ({"r": "4", "s": "__other__"}, oth % "하나"),
            ({"r": "4", "s": "__other__", "s#other": "   "}, oth % "하나"),
            ({"r": "4", "s": "A", "m": ["X", "W"]}, bad % "여럿"),
            ({"r": "4", "s": "A", "m": ["__other__"]}, oth % "여럿"),
            ({"r": "4", "s": "A", "yn": "네"}, bad % "예아니오"),
            ({"r": "4", "s": "A", "d": "2026-13-01"}, bad % "날짜"),
            ({"r": "4", "s": "A", "d": "2026/11/05"}, bad % "날짜"),
            ({"t": "x", "r": "9", "s": "C"}, bad % "점수"),           # 문항 순서대로 첫 에러만
        ]
        for data, msg in cases:
            with self.subTest(data=data):
                status, h, res = self.srv.answer(self.code, data)
                self.assertEqual(status, 200)
                self.assertEqual(res, {"result": "FAIL", "msg": msg})
                self.assertNotIn("set-cookie", h)
        self.assertEqual(self.srv.db("SELECT count(*) FROM responses WHERE survey_id=?", (self.sid,))[0][0], 0)

    def test_other_not_allowed_is_invalid(self):
        sid, code = self.srv.create_survey([
            {"id": "s", "type": "single", "label": "하나", "required": True, "options": ["A"], "allowOther": False},
            {"id": "m", "type": "multi", "label": "여럿", "required": False, "options": ["A"], "allowOther": False}])
        _, _, res = self.srv.answer(code, {"s": "__other__", "s#other": "x"})
        self.assertEqual(res["msg"], "'하나' 값이 올바르지 않습니다.")
        _, _, res = self.srv.answer(code, {"s": "A", "m": ["__other__"], "m#other": "x"})
        self.assertEqual(res["msg"], "'여럿' 값이 올바르지 않습니다.")

    def test_required_multi(self):
        sid, code = self.srv.create_survey([
            {"id": "m", "type": "multi", "label": "여럿", "required": True, "options": ["A"], "allowOther": False}])
        for v in [None, [], ""]:
            with self.subTest(v=v):
                _, _, res = self.srv.answer(code, {"m": v})
                self.assertEqual(res["msg"], "'여럿' 항목은 필수입니다.")

    def test_bad_body_is_treated_as_empty(self):
        for body in [b"not json", b"[1,2]", b""]:
            with self.subTest(body=body):
                _, _, raw = self.srv.request("POST", "/api/saveAnswer?code=" + self.code, body=body)
                self.assertEqual(json.loads(raw), {"result": "FAIL", "msg": "'점수' 항목은 필수입니다."})

    def test_refusals(self):
        _, _, res = self.srv.answer("zzzzzzz", GOOD)
        self.assertEqual(res, NOT_FOUND)
        _, closed = self.srv.create_survey(ALL_TYPES, open_=False)
        _, _, res = self.srv.answer(closed, GOOD)
        self.assertEqual(res, {"result": "FAIL", "msg": "마감된 설문입니다."})
        _, _, res = self.srv.answer(self.code, GOOD, cookie="sv_%s=1" % self.code)
        self.assertEqual(res, {"result": "FAIL", "msg": "이미 이 설문에 응답하셨습니다."})
        # 마감 검사가 쿠키 검사보다 먼저
        _, _, res = self.srv.answer(closed, GOOD, cookie="sv_%s=1" % closed)
        self.assertEqual(res["msg"], "마감된 설문입니다.")


class ResultAndCsvTest(ServerTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sid, cls.code = cls.srv.create_survey(ALL_TYPES, title='결과 "따옴표"', desc="설명")
        for data in [
            {"t": "하나", "ta": "줄1\n줄2", "r": "5", "s": "A", "m": ["X", "__other__"], "m#other": "기타1",
             "yn": "예", "d": "2026-11-05"},
            {"r": "3", "s": "__other__", "s#other": "직접", "m": ["X", "Y"], "yn": "아니오", "d": "2026-11-01"},
            {"t": 'a,"b"', "r": "4", "s": "A", "d": "2026-11-05"},
        ]:
            _, _, res = cls.srv.answer(cls.code, data)
            assert res["result"] == "OK", res

    def test_result_structure(self):
        status, res = self.srv.get_json("/api/getResult?code=" + self.code)
        self.assertEqual(status, 200)
        self.assertEqual(res["result"], "OK")
        data = res["data"]
        self.assertEqual({k: data[k] for k in ("code", "title", "desc", "open", "cnt")},
                         {"code": self.code, "title": '결과 "따옴표"', "desc": "설명", "open": 1, "cnt": 3})
        r = {x["id"]: x for x in data["results"]}
        self.assertEqual([x["id"] for x in data["results"]], [q["id"] for q in ALL_TYPES])

        def c(key, count, label=None):
            return {"key": key, "label": key if label is None else label, "count": count}

        self.assertEqual(r["r"], {"id": "r", "type": "rating", "label": "점수",
                                  "counts": [c("1", 0), c("2", 0), c("3", 1), c("4", 1), c("5", 1)],
                                  "average": 4.0, "max": 5})
        self.assertEqual(r["s"], {"id": "s", "type": "single", "label": "하나",
                                  "counts": [c("A", 2), c("B", 0), c("__other__", 1, "기타")],
                                  "otherTexts": ["직접"]})
        self.assertEqual(r["m"], {"id": "m", "type": "multi", "label": "여럿",
                                  "counts": [c("X", 2), c("Y", 1), c("Z", 0), c("__other__", 1, "기타")],
                                  "otherTexts": ["기타1"]})
        self.assertEqual(r["yn"], {"id": "yn", "type": "yesno", "label": "예아니오",
                                   "counts": [c("예", 1), c("아니오", 1)]})
        self.assertEqual(r["d"], {"id": "d", "type": "date", "label": "날짜",
                                  "counts": [c("2026-11-01", 1), c("2026-11-05", 2)]})
        self.assertEqual(set(r["t"]), {"id", "type", "label", "texts"})
        self.assertCountEqual(r["t"]["texts"], ["하나", 'a,"b"'])
        self.assertCountEqual(r["ta"]["texts"], ["줄1\n줄2"])

    def test_other_texts_newest_first(self):
        sid, code = self.srv.create_survey([
            {"id": "s", "type": "single", "label": "하나", "required": True, "options": ["A"], "allowOther": True}])
        for t in ["첫째", "둘째", "셋째"]:
            self.srv.answer(code, {"s": "__other__", "s#other": t})
        _, res = self.srv.get_json("/api/getResult?code=" + code)
        self.assertEqual(res["data"]["results"][0]["otherTexts"], ["셋째", "둘째", "첫째"])

    def test_empty_result(self):
        sid, code = self.srv.create_survey(ALL_TYPES, open_=False)
        _, res = self.srv.get_json("/api/getResult?code=" + code)
        r = {x["id"]: x for x in res["data"]["results"]}
        self.assertEqual(res["data"]["cnt"], 0)
        self.assertEqual(res["data"]["open"], 0)
        self.assertIsNone(r["r"]["average"])
        self.assertEqual(r["d"]["counts"], [])
        self.assertEqual(r["t"]["texts"], [])
        self.assertEqual(r["s"]["otherTexts"], [])

    def test_result_not_found(self):
        self.assertEqual(self.srv.get_json("/api/getResult?code=nope")[1], NOT_FOUND)

    def test_csv(self):
        status, h, body = self.srv.request("GET", "/api/excel?code=" + self.code)
        self.assertEqual(status, 200)
        self.assertEqual(h["content-type"], "text/csv; charset=utf-8")
        self.assertEqual(h["content-disposition"], 'attachment; filename="survey_%s.csv"' % self.code)
        expected = (
            "\ufeff" + '"번호","단답","장문","점수","하나","여럿","예아니오","날짜"\r\n'
            + '1,"하나","줄1\n줄2","5","A","X; 기타: 기타1","예","2026-11-05"\r\n'
            + '2,"","","3","기타: 직접","X; Y","아니오","2026-11-01"\r\n'
            + '3,"a,""b""","","4","A","","","2026-11-05"\r\n'
        )
        self.assertEqual(body.decode("utf-8"), expected)

    def test_csv_no_responses_and_not_found(self):
        sid, code = self.srv.create_survey([{"id": "t", "type": "text", "label": "a", "required": False}])
        _, _, body = self.srv.request("GET", "/api/excel?code=" + code)
        self.assertEqual(body.decode("utf-8"), '\ufeff"번호","a"\r\n')
        status, h, body = self.srv.request("GET", "/api/excel?code=nope")
        self.assertTrue(h["content-type"].startswith("application/json"))
        self.assertNotIn("content-disposition", h)
