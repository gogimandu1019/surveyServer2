# -*- coding: utf-8 -*-
# =====================================================================
#   설문관리 시스템  SurveyMgr  v1.3.2
#   최초 작성 : 2009.03.02  김OO
#   수정 이력 :
#     2009.05.11  김OO   결과화면 추가
#     2011.07.20  박OO   다중설문 (급하게 붙임. 다음주에 정리 예정)
#     2013.11.03  이OO   기타(직접입력) 추가
#     2014.02.17  ???    날짜문항, 엑셀다운
#     2016.08.30  박OO   관리자 IP 체크 (보안감사 지적사항)
#     2019.??.??  외주    파이썬3 포팅 (테스트 안함)
#
#   ※※※ 절대 함부로 수정하지 말것 ※※※   <- 수정함 (2016 박)
# =====================================================================
import socket, threading, sqlite3, json, os, sys, time, random, re
#import MySQLdb
#import cgi, cgitb; cgitb.enable()

DEBUG = 1   # 운영에서는 0 으로 바꿀것 (운영도 1임)
VER = "1.3.2"
DBFILE = os.path.dirname(os.path.abspath(__file__)) + "/survey.db"
WEBDIR = os.path.dirname(os.path.abspath(__file__)) + "/static/"
HOST = os.environ.get("HOST")
if HOST == None or HOST == "":
    HOST = "127.0.0.1"
PORT = 8000
if os.environ.get("PORT") != None:
    PORT = int(os.environ.get("PORT"))

g_cnt = 0            # 접속자 수
g_lastErr = ""       # 마지막 에러 (어디서 쓰는지 모름. 지우지 말것)
g_lock = threading.Lock()   # 혹시 몰라서
g_tmp = []

# ---------------------------------------------------------------
#  DB 생성  (MySQL 로 바꿀 예정이라 임시로 sqlite 씀 - 2009)
# ---------------------------------------------------------------
con = sqlite3.connect(DBFILE)
cu = con.cursor()
cu.execute("CREATE TABLE IF NOT EXISTS surveys (id INTEGER PRIMARY KEY AUTOINCREMENT, slug TEXT NOT NULL UNIQUE, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', questions TEXT NOT NULL, is_open INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)")
cu.execute("CREATE TABLE IF NOT EXISTS responses (id INTEGER PRIMARY KEY AUTOINCREMENT, survey_id INTEGER NOT NULL REFERENCES surveys(id) ON DELETE CASCADE, created_at TEXT NOT NULL)")
cu.execute("CREATE TABLE IF NOT EXISTS answers (response_id INTEGER NOT NULL REFERENCES responses(id) ON DELETE CASCADE, question_id TEXT NOT NULL, value TEXT NOT NULL, other_text TEXT)")
cu.execute("CREATE INDEX IF NOT EXISTS idx_resp_survey ON responses(survey_id)")
cu.execute("CREATE INDEX IF NOT EXISTS idx_ans_resp ON answers(response_id)")
cu.execute("select count(*) from surveys")
if cu.fetchone()[0] == 0:
    # 샘플 데이타 (지우면 안됨!! 메인화면 깨짐)
    tmp = '[{"id": "q1", "type": "rating", "label": "요즘 팀 분위기는 어떤가요?", "required": true, "max": 5}, {"id": "q2", "type": "single", "label": "업무량은 어느 정도인가요?", "required": true, "options": ["여유 있음", "적당함", "조금 많음", "너무 많음"], "allowOther": false}, {"id": "q3", "type": "multi", "label": "개선이 필요한 부분을 모두 골라주세요.", "required": false, "options": ["회의", "업무 분배", "소통 도구", "평가 기준"], "allowOther": true}, {"id": "q4", "type": "yesno", "label": "재택근무를 늘리면 좋겠나요?", "required": true}, {"id": "q5", "type": "date", "label": "다음 팀 워크숍으로 좋은 날짜는?", "required": false}, {"id": "q6", "type": "textarea", "label": "자유롭게 하고 싶은 말", "required": false}]'
    tmp2 = ""
    for i in range(7):
        tmp2 = tmp2 + random.choice("abcdefghijklmnopqrstuvwxyz0123456789")
    t = time.strftime("%Y-%m-%dT%H:%M:%S")
    cu.execute("insert into surveys (slug, title, description, questions, is_open, created_at, updated_at) values ('" + tmp2 + "', '팀 업무 환경 설문 (예시)', '익명으로 진행됩니다. 편하게 적어주세요.', '" + tmp.replace("'", "''") + "', 1, '" + t + "', '" + t + "')")
    con.commit()
con.close()

# 내부 IP (와이파이 주소 보여줄때 씀)
LANIP = None
try:
    s_ = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s_.connect(("10.255.255.255", 1))
    LANIP = s_.getsockname()[0]
    s_.close()
except:
    pass


# =====================================================================
#   요청 처리  (모든 처리는 여기서 함)
# =====================================================================
def procReq(c, addr):
    global g_cnt, g_lastErr
    g_cnt = g_cnt + 1
    nStatus = 200
    sType = "application/json; charset=utf-8"
    out = ""
    sHdr = ""
    con = None
    try:
        c.settimeout(10)
        raw = b""
        while raw.find(b"\r\n\r\n") < 0:
            tmp = c.recv(4096)
            if not tmp:
                break
            raw = raw + tmp
            if len(raw) > 600000:
                break
        if raw.find(b"\r\n\r\n") < 0:
            c.close()
            return
        sHead = raw[:raw.find(b"\r\n\r\n")].decode("latin-1")
        body = raw[raw.find(b"\r\n\r\n") + 4:]
        arrLine = sHead.split("\r\n")
        sMethod = arrLine[0].split(" ")[0]
        strPath = arrLine[0].split(" ")[1]
        hdrs = {}
        for l in arrLine[1:]:
            if l.find(":") > 0:
                hdrs[l[:l.find(":")].strip().lower()] = l[l.find(":") + 1:].strip()
        nLen = 0
        if hdrs.get("content-length") != None:
            nLen = int(hdrs.get("content-length"))
        if nLen > 500000:
            nLen = 0   # 너무 크면 무시 (원래 에러내야함)
        while len(body) < nLen:
            tmp = c.recv(4096)
            if not tmp:
                break
            body = body + tmp

        sPage = strPath.split("?")[0]
        con = sqlite3.connect(DBFILE)
        cu = con.cursor()

        # ------------------------------------------------------------
        #  화면
        # ------------------------------------------------------------
        if sMethod == "GET" and (sPage == "/" or sPage == "/index.html"):
            f = open(WEBDIR + "index.html", "rb")
            out = f.read()
            f.close()
            sType = "text/html; charset=utf-8"
        elif sMethod == "GET" and sPage == "/survey.html":
            f = open(WEBDIR + "survey.html", "rb")
            out = f.read()
            f.close()
            sType = "text/html; charset=utf-8"
        elif sMethod == "GET" and sPage == "/result.html":
            f = open(WEBDIR + "result.html", "rb")
            out = f.read()
            f.close()
            sType = "text/html; charset=utf-8"
        elif sMethod == "GET" and sPage == "/style.css":
            f = open(WEBDIR + "style.css", "rb")
            out = f.read()
            f.close()
            sType = "text/css; charset=utf-8"
        elif sMethod == "GET" and (sPage == "/admin.html" or sPage == "/admin_edit.html"):
            # 관리자 체크 (보안감사 2016) - IP만 보면 됨
            bAdmin = 0
            if addr[0] == "127.0.0.1" or addr[0] == "::1":
                tmp = hdrs.get("host", "").split(":")[0]
                if tmp == "localhost" or tmp == "127.0.0.1":
                    if hdrs.get("x-forwarded-for") == None and hdrs.get("forwarded") == None and hdrs.get("x-forwarded-host") == None and hdrs.get("cf-connecting-ip") == None and hdrs.get("x-real-ip") == None and hdrs.get("ngrok-trace-id") == None:
                        bAdmin = 1
            if bAdmin == 0:
                nStatus = 403
                sType = "text/plain; charset=utf-8"
                out = "관리 화면은 설문 서버를 실행 중인 노트북에서 http://localhost 로 접속했을 때만 열립니다."
            else:
                f = open(WEBDIR + sPage[1:], "rb")
                out = f.read()
                f.close()
                sType = "text/html; charset=utf-8"

        # ------------------------------------------------------------
        #  설문 목록
        # ------------------------------------------------------------
        elif sMethod == "GET" and sPage == "/api/getList":
            cu.execute("select slug, title, description from surveys where is_open = 1 order by id desc")
            arr = []
            for r in cu.fetchall():
                arr.append({"code": r[0], "title": r[1], "desc": r[2]})
            out = json.dumps({"result": "OK", "data": arr})

        # ------------------------------------------------------------
        #  설문 1개 가져오기
        # ------------------------------------------------------------
        elif sMethod == "GET" and sPage == "/api/getSurvey":
            sCode = ""
            if strPath.find("?") > 0:
                for kv in strPath.split("?")[1].split("&"):
                    if kv.split("=")[0] == "code":
                        sCode = kv[5:]
            cu.execute("select id, slug, title, description, questions, is_open from surveys where slug = '" + sCode.replace("'", "''") + "'")
            row = cu.fetchone()
            if row == None:
                out = json.dumps({"result": "FAIL", "msg": "설문을 찾을 수 없습니다."})
            else:
                cu.execute("select count(*) from responses where survey_id = " + str(row[0]))
                n = cu.fetchone()[0]
                already = 0
                # 쿠키 확인 (세션으로 바꿀것)
                for ck in hdrs.get("cookie", "").split(";"):
                    if ck.strip().split("=")[0] == "sv_" + row[1]:
                        already = 1
                out = json.dumps({"result": "OK", "data": {"code": row[1], "title": row[2], "desc": row[3], "q": json.loads(row[4]), "open": row[5], "cnt": n, "already": already}})

        # ------------------------------------------------------------
        #  응답 저장
        # ------------------------------------------------------------
        elif sMethod == "POST" and sPage == "/api/saveAnswer":
            sCode = ""
            if strPath.find("?") > 0:
                for kv in strPath.split("?")[1].split("&"):
                    if kv.split("=")[0] == "code":
                        sCode = kv[5:]
            data = {}
            try:
                data = json.loads(body.decode("utf-8"))
            except:
                pass
            if type(data) != dict:
                data = {}
            cu.execute("select id, slug, title, description, questions, is_open from surveys where slug = '" + sCode.replace("'", "''") + "'")
            row = cu.fetchone()
            sErr = ""
            if row == None:
                sErr = "설문을 찾을 수 없습니다."
            elif row[5] == 0:
                sErr = "마감된 설문입니다."
            else:
                for ck in hdrs.get("cookie", "").split(";"):
                    if ck.strip().split("=")[0] == "sv_" + row[1]:
                        sErr = "이미 이 설문에 응답하셨습니다."
            arr = []
            if sErr == "":
                arrQ = json.loads(row[4])
                for q in arrQ:
                    if sErr != "":
                        break
                    v = data.get(q["id"])
                    oth = data.get(q["id"] + "#other")
                    if oth == None:
                        oth = ""
                    oth = str(oth).strip()[:1000]
                    if q["type"] == "text":
                        if v == None:
                            v = ""
                        v = str(v).strip()
                        if v == "":
                            if q["required"] == True:
                                sErr = "'" + q["label"] + "' 항목은 필수입니다."
                        else:
                            arr.append([q["id"], v[:5000], None])
                    elif q["type"] == "textarea":
                        if v == None:
                            v = ""
                        v = str(v).strip()
                        if v == "":
                            if q["required"] == True:
                                sErr = "'" + q["label"] + "' 항목은 필수입니다."
                        else:
                            arr.append([q["id"], v[:5000], None])
                    elif q["type"] == "rating":
                        if v == None:
                            v = ""
                        v = str(v).strip()
                        if v == "":
                            if q["required"] == True:
                                sErr = "'" + q["label"] + "' 항목은 필수입니다."
                        elif v.isdigit() == False or int(v) < 1 or int(v) > q["max"]:
                            sErr = "'" + q["label"] + "' 값이 올바르지 않습니다."
                        else:
                            arr.append([q["id"], v, None])
                    elif q["type"] == "single":
                        if v == None:
                            v = ""
                        v = str(v).strip()
                        if v == "":
                            if q["required"] == True:
                                sErr = "'" + q["label"] + "' 항목은 필수입니다."
                        elif v == "__other__" and q.get("allowOther") == True:
                            if oth == "":
                                sErr = "'" + q["label"] + "'의 기타 내용을 입력하세요."
                            else:
                                arr.append([q["id"], "__other__", oth])
                        elif not v in q["options"]:
                            sErr = "'" + q["label"] + "' 값이 올바르지 않습니다."
                        else:
                            arr.append([q["id"], v, None])
                    elif q["type"] == "multi":
                        # 체크박스는 배열로 옴 (가끔 문자열로 옴. 이유 모름)
                        if type(v) != list:
                            if v == None or v == "":
                                v = []
                            else:
                                v = [v]
                        tmp = []
                        for x in v:
                            if not str(x) in tmp:
                                tmp.append(str(x))
                        for x in tmp:
                            if not x in q["options"]:
                                if not (x == "__other__" and q.get("allowOther") == True):
                                    sErr = "'" + q["label"] + "' 값이 올바르지 않습니다."
                        if sErr == "" and "__other__" in tmp and oth == "":
                            sErr = "'" + q["label"] + "'의 기타 내용을 입력하세요."
                        if sErr == "" and q["required"] == True and len(tmp) == 0:
                            sErr = "'" + q["label"] + "' 항목은 필수입니다."
                        if sErr == "":
                            for x in tmp:
                                if x == "__other__":
                                    arr.append([q["id"], x, oth])
                                else:
                                    arr.append([q["id"], x, None])
                    elif q["type"] == "yesno":
                        if v == None:
                            v = ""
                        v = str(v).strip()
                        if v == "":
                            if q["required"] == True:
                                sErr = "'" + q["label"] + "' 항목은 필수입니다."
                        elif v != "예" and v != "아니오":
                            sErr = "'" + q["label"] + "' 값이 올바르지 않습니다."
                        else:
                            arr.append([q["id"], v, None])
                    elif q["type"] == "date":
                        if v == None:
                            v = ""
                        v = str(v).strip()
                        if v == "":
                            if q["required"] == True:
                                sErr = "'" + q["label"] + "' 항목은 필수입니다."
                        else:
                            try:
                                time.strptime(v, "%Y-%m-%d")
                                arr.append([q["id"], v, None])
                            except:
                                sErr = "'" + q["label"] + "' 값이 올바르지 않습니다."
            if sErr != "":
                out = json.dumps({"result": "FAIL", "msg": sErr})
            else:
                # 저장 (트랜잭션 처리 필요?)
                cu.execute("insert into responses (survey_id, created_at) values (" + str(row[0]) + ", '" + time.strftime("%Y-%m-%dT%H:%M:%S") + "')")
                rid = cu.lastrowid
                for a in arr:
                    if a[2] == None:
                        cu.execute("insert into answers values (" + str(rid) + ", '" + a[0].replace("'", "''") + "', '" + a[1].replace("'", "''") + "', NULL)")
                    else:
                        cu.execute("insert into answers values (" + str(rid) + ", '" + a[0].replace("'", "''") + "', '" + a[1].replace("'", "''") + "', '" + a[2].replace("'", "''") + "')")
                con.commit()
                # 쿠키 유효기간 1달
                sHdr = sHdr + "Set-Cookie: sv_" + row[1] + "=1; Max-Age=31536000; Path=/; HttpOnly; SameSite=Lax\r\n"
                out = json.dumps({"result": "OK"})

        # ------------------------------------------------------------
        #  결과
        # ------------------------------------------------------------
        elif sMethod == "GET" and sPage == "/api/getResult":
            sCode = ""
            if strPath.find("?") > 0:
                for kv in strPath.split("?")[1].split("&"):
                    if kv.split("=")[0] == "code":
                        sCode = kv[5:]
            cu.execute("select id, slug, title, description, questions, is_open from surveys where slug = '" + sCode.replace("'", "''") + "'")
            row = cu.fetchone()
            if row == None:
                out = json.dumps({"result": "FAIL", "msg": "설문을 찾을 수 없습니다."})
            else:
                sid = str(row[0])
                cu.execute("select count(*) from responses where survey_id = " + sid)
                n = cu.fetchone()[0]
                arrQ = json.loads(row[4])
                arrRes = []
                for q in arrQ:
                    qid = q["id"].replace("'", "''")
                    item = {"id": q["id"], "type": q["type"], "label": q["label"]}
                    if q["type"] == "rating":
                        cnts = []
                        i = 1
                        while i <= q["max"]:
                            cnts.append({"key": str(i), "label": str(i), "count": 0})
                            i = i + 1
                        cu.execute("select a.value, count(*) from answers a, responses r where r.id = a.response_id and r.survey_id = " + sid + " and a.question_id = '" + qid + "' group by a.value")
                        for rr in cu.fetchall():
                            for cc in cnts:
                                if cc["key"] == rr[0]:
                                    cc["count"] = rr[1]
                        item["counts"] = cnts
                        cu.execute("select avg(cast(a.value as real)) from answers a, responses r where r.id = a.response_id and r.survey_id = " + sid + " and a.question_id = '" + qid + "'")
                        tmp = cu.fetchone()[0]
                        if tmp == None:
                            item["average"] = None
                        else:
                            item["average"] = round(tmp, 2)
                        item["max"] = q["max"]
                    elif q["type"] == "single" or q["type"] == "multi":
                        cnts = []
                        for o in q["options"]:
                            cnts.append({"key": o, "label": o, "count": 0})
                        if q.get("allowOther") == True:
                            cnts.append({"key": "__other__", "label": "기타", "count": 0})
                        cu.execute("select a.value, count(*) from answers a, responses r where r.id = a.response_id and r.survey_id = " + sid + " and a.question_id = '" + qid + "' group by a.value")
                        for rr in cu.fetchall():
                            for cc in cnts:
                                if cc["key"] == rr[0]:
                                    cc["count"] = rr[1]
                        item["counts"] = cnts
                        if q.get("allowOther") == True:
                            item["otherTexts"] = []
                            cu.execute("select a.other_text from answers a, responses r where r.id = a.response_id and r.survey_id = " + sid + " and a.question_id = '" + qid + "' and a.value = '__other__' order by r.id desc limit 300")
                            for rr in cu.fetchall():
                                item["otherTexts"].append(rr[0])
                    elif q["type"] == "yesno":
                        cnts = [{"key": "예", "label": "예", "count": 0}, {"key": "아니오", "label": "아니오", "count": 0}]
                        cu.execute("select a.value, count(*) from answers a, responses r where r.id = a.response_id and r.survey_id = " + sid + " and a.question_id = '" + qid + "' group by a.value")
                        for rr in cu.fetchall():
                            for cc in cnts:
                                if cc["key"] == rr[0]:
                                    cc["count"] = rr[1]
                        item["counts"] = cnts
                    elif q["type"] == "date":
                        cnts = []
                        cu.execute("select a.value, count(*) from answers a, responses r where r.id = a.response_id and r.survey_id = " + sid + " and a.question_id = '" + qid + "' group by a.value order by a.value")
                        for rr in cu.fetchall():
                            cnts.append({"key": rr[0], "label": rr[0], "count": rr[1]})
                        item["counts"] = cnts
                    else:
                        # 주관식은 최신순으로 보여줌
                        item["texts"] = []
                        cu.execute("select a.value from answers a, responses r where r.id = a.response_id and r.survey_id = " + sid + " and a.question_id = '" + qid + "' order by random() limit 500")
                        for rr in cu.fetchall():
                            item["texts"].append(rr[0])
                    arrRes.append(item)
                out = json.dumps({"result": "OK", "data": {"code": row[1], "title": row[2], "desc": row[3], "open": row[5], "cnt": n, "results": arrRes}})

        # ------------------------------------------------------------
        #  엑셀 다운로드  (실제로는 csv임)
        # ------------------------------------------------------------
        elif sMethod == "GET" and sPage == "/api/excel":
            sCode = ""
            if strPath.find("?") > 0:
                for kv in strPath.split("?")[1].split("&"):
                    if kv.split("=")[0] == "code":
                        sCode = kv[5:]
            cu.execute("select id, slug, title, description, questions, is_open from surveys where slug = '" + sCode.replace("'", "''") + "'")
            row = cu.fetchone()
            if row == None:
                out = json.dumps({"result": "FAIL", "msg": "설문을 찾을 수 없습니다."})
            else:
                arrQ = json.loads(row[4])
                cu.execute("select a.response_id, a.question_id, a.value, a.other_text from answers a, responses r where r.id = a.response_id and r.survey_id = " + str(row[0]) + " order by a.response_id")
                dic = {}
                arrRid = []
                for rr in cu.fetchall():
                    if not rr[0] in dic:
                        dic[rr[0]] = {}
                        arrRid.append(rr[0])
                    if not rr[1] in dic[rr[0]]:
                        dic[rr[0]][rr[1]] = []
                    if rr[2] == "__other__":
                        dic[rr[0]][rr[1]].append("기타: " + str(rr[3]))
                    else:
                        dic[rr[0]][rr[1]].append(rr[2])
                s = "﻿" + '"번호"'
                for q in arrQ:
                    s = s + ',"' + q["label"].replace('"', '""') + '"'
                s = s + "\r\n"
                n = 0
                for rid in arrRid:
                    n = n + 1
                    s = s + str(n)
                    for q in arrQ:
                        if q["id"] in dic[rid]:
                            s = s + ',"' + "; ".join(dic[rid][q["id"]]).replace('"', '""') + '"'
                        else:
                            s = s + ',""'
                    s = s + "\r\n"
                out = s
                sType = "text/csv; charset=utf-8"
                sHdr = sHdr + 'Content-Disposition: attachment; filename="survey_' + row[1] + '.csv"\r\n'

        # ------------------------------------------------------------
        #  관리자 - 목록
        # ------------------------------------------------------------
        elif sMethod == "GET" and (sPage == "/api/adminList" or sPage == "/api/adminGet"):
            # 관리자 체크 (위에꺼 복사함)
            bAdmin = 0
            if addr[0] == "127.0.0.1" or addr[0] == "::1":
                tmp = hdrs.get("host", "").split(":")[0]
                if tmp == "localhost" or tmp == "127.0.0.1":
                    if hdrs.get("x-forwarded-for") == None and hdrs.get("forwarded") == None and hdrs.get("x-forwarded-host") == None and hdrs.get("cf-connecting-ip") == None and hdrs.get("x-real-ip") == None and hdrs.get("ngrok-trace-id") == None:
                        bAdmin = 1
            if bAdmin == 0:
                nStatus = 403
                out = json.dumps({"result": "FAIL", "msg": "관리 기능은 이 노트북에서만 쓸 수 있습니다."})
            elif sPage == "/api/adminList":
                cu.execute("select id, slug, title, description, questions, is_open, created_at, updated_at from surveys order by id desc")
                arr = []
                for r in cu.fetchall():
                    cu.execute("select count(*) from responses where survey_id = " + str(r[0]))
                    arr.append({"id": r[0], "code": r[1], "title": r[2], "desc": r[3], "q": json.loads(r[4]), "open": r[5], "cnt": cu.fetchone()[0]})
                tmp = None
                if HOST != "127.0.0.1" and LANIP != None:
                    tmp = "http://" + LANIP + ":" + str(PORT)
                out = json.dumps({"result": "OK", "data": arr, "localBase": "http://localhost:" + str(PORT), "lanBase": tmp})
            else:
                nId = 0
                if strPath.find("?") > 0:
                    for kv in strPath.split("?")[1].split("&"):
                        if kv.split("=")[0] == "id":
                            try:
                                nId = int(kv[3:])
                            except:
                                nId = 0
                cu.execute("select id, slug, title, description, questions, is_open from surveys where id = " + str(nId))
                r = cu.fetchone()
                if r == None:
                    out = json.dumps({"result": "FAIL", "msg": "설문을 찾을 수 없습니다."})
                else:
                    cu.execute("select count(*) from responses where survey_id = " + str(r[0]))
                    out = json.dumps({"result": "OK", "data": {"id": r[0], "code": r[1], "title": r[2], "desc": r[3], "q": json.loads(r[4]), "open": r[5], "cnt": cu.fetchone()[0]}})

        # ------------------------------------------------------------
        #  관리자 - 처리 (cmd 로 구분)
        # ------------------------------------------------------------
        elif sMethod == "POST" and sPage == "/api/adminProc":
            # 관리자 체크 (위에꺼 복사함)
            bAdmin = 0
            if addr[0] == "127.0.0.1" or addr[0] == "::1":
                tmp = hdrs.get("host", "").split(":")[0]
                if tmp == "localhost" or tmp == "127.0.0.1":
                    if hdrs.get("x-forwarded-for") == None and hdrs.get("forwarded") == None and hdrs.get("x-forwarded-host") == None and hdrs.get("cf-connecting-ip") == None and hdrs.get("x-real-ip") == None and hdrs.get("ngrok-trace-id") == None:
                        bAdmin = 1
            # ajax 로만 호출되게 (jQuery 쓸때 넣은거)
            if hdrs.get("x-requested-with") != "XMLHttpRequest":
                bAdmin = 0
            if hdrs.get("origin") != None:
                if re.match(r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$", hdrs.get("origin")) == None:
                    bAdmin = 0
            data = {}
            try:
                data = json.loads(body.decode("utf-8"))
            except:
                pass
            if type(data) != dict:
                data = {}
            cmd = data.get("cmd")
            nId = 0
            try:
                nId = int(data.get("id"))
            except:
                nId = 0
            row = None
            if nId > 0:
                cu.execute("select id, slug, title, description, questions, is_open from surveys where id = " + str(nId))
                row = cu.fetchone()
            if bAdmin == 0:
                nStatus = 403
                out = json.dumps({"result": "FAIL", "msg": "관리 기능은 이 노트북에서만 쓸 수 있습니다."})

            # ---------- 신규 ----------
            elif cmd == "new":
                sErr = ""
                sTitle = str(data.get("title", "")).strip()[:200]
                sDesc = str(data.get("desc", "")).strip()[:2000]
                arrIn = data.get("q")
                arrOut = []
                if sTitle == "":
                    sErr = "설문 제목을 입력하세요."
                elif type(arrIn) != list or len(arrIn) == 0:
                    sErr = "문항을 하나 이상 추가하세요."
                elif len(arrIn) > 100:
                    sErr = "문항은 100개까지 만들 수 있습니다."
                else:
                    arrIds = []
                    i = 0
                    for q in arrIn:
                        i = i + 1
                        if sErr != "":
                            break
                        if type(q) != dict:
                            sErr = str(i) + "번 문항이 올바르지 않습니다."
                            break
                        qid = str(q.get("id") or "").strip()
                        if re.match(r"^[A-Za-z0-9_-]{1,40}$", qid) == None or qid in arrIds:
                            qid = "q" + "%08x" % random.randint(0, 0xffffffff)
                        arrIds.append(qid)
                        if not q.get("type") in ["text", "textarea", "rating", "single", "multi", "yesno", "date"]:
                            sErr = str(i) + "번 문항의 종류가 올바르지 않습니다."
                            break
                        lbl = str(q.get("label", "")).strip()[:500]
                        if lbl == "":
                            sErr = str(i) + "번 문항의 질문을 입력하세요."
                            break
                        o = {"id": qid, "type": q["type"], "label": lbl, "required": bool(q.get("required"))}
                        if q["type"] == "rating":
                            if str(q.get("max")) == "10":
                                o["max"] = 10
                            else:
                                o["max"] = 5
                        if q["type"] == "single" or q["type"] == "multi":
                            ops = []
                            if type(q.get("options")) == list:
                                for x in q.get("options"):
                                    x = str(x).strip()[:200]
                                    if x != "" and x != "__other__" and not x in ops:
                                        ops.append(x)
                            if len(ops) == 0:
                                sErr = str(i) + "번 문항에 선택지를 하나 이상 입력하세요."
                                break
                            o["options"] = ops
                            o["allowOther"] = bool(q.get("allowOther"))
                        arrOut.append(o)
                if sErr != "":
                    out = json.dumps({"result": "FAIL", "msg": sErr})
                else:
                    while True:
                        tmp2 = ""
                        for i in range(7):
                            tmp2 = tmp2 + random.choice("abcdefghijklmnopqrstuvwxyz0123456789")
                        cu.execute("select count(*) from surveys where slug = '" + tmp2 + "'")
                        if cu.fetchone()[0] == 0:
                            break
                    t = time.strftime("%Y-%m-%dT%H:%M:%S")
                    # 신규는 바로 오픈
                    cu.execute("insert into surveys (slug, title, description, questions, is_open, created_at, updated_at) values ('" + tmp2 + "', '" + sTitle.replace("'", "''") + "', '" + sDesc.replace("'", "''") + "', '" + json.dumps(arrOut, ensure_ascii=False).replace("'", "''") + "', 0, '" + t + "', '" + t + "')")
                    con.commit()
                    out = json.dumps({"result": "OK", "id": cu.lastrowid, "code": tmp2})

            elif row == None:
                out = json.dumps({"result": "FAIL", "msg": "설문을 찾을 수 없습니다."})

            # ---------- 수정 (신규꺼 복사) ----------
            elif cmd == "update":
                sErr = ""
                sTitle = str(data.get("title", "")).strip()[:200]
                sDesc = str(data.get("desc", "")).strip()[:2000]
                arrIn = data.get("q")
                arrOut = []
                if sTitle == "":
                    sErr = "설문 제목을 입력하세요."
                elif type(arrIn) != list or len(arrIn) == 0:
                    sErr = "문항을 하나 이상 추가하세요."
                elif len(arrIn) > 100:
                    sErr = "문항은 100개까지 만들 수 있습니다."
                else:
                    arrIds = []
                    i = 0
                    for q in arrIn:
                        i = i + 1
                        if sErr != "":
                            break
                        if type(q) != dict:
                            sErr = str(i) + "번 문항이 올바르지 않습니다."
                            break
                        qid = str(q.get("id") or "").strip()
                        if re.match(r"^[A-Za-z0-9_-]{1,40}$", qid) == None or qid in arrIds:
                            qid = "q" + "%08x" % random.randint(0, 0xffffffff)
                        arrIds.append(qid)
                        if not q.get("type") in ["text", "textarea", "rating", "single", "multi", "yesno", "date"]:
                            sErr = str(i) + "번 문항의 종류가 올바르지 않습니다."
                            break
                        lbl = str(q.get("label", "")).strip()[:500]
                        if lbl == "":
                            sErr = str(i) + "번 문항의 질문을 입력하세요."
                            break
                        o = {"id": qid, "type": q["type"], "label": lbl, "required": bool(q.get("required"))}
                        if q["type"] == "rating":
                            if str(q.get("max")) == "10":
                                o["max"] = 10
                            else:
                                o["max"] = 5
                        if q["type"] == "single" or q["type"] == "multi":
                            ops = []
                            if type(q.get("options")) == list:
                                for x in q.get("options"):
                                    x = str(x).strip()[:200]
                                    if x != "" and x != "__other__" and not x in ops:
                                        ops.append(x)
                            if len(ops) == 0:
                                sErr = str(i) + "번 문항에 선택지를 하나 이상 입력하세요."
                                break
                            o["options"] = ops
                            o["allowOther"] = bool(q.get("allowOther"))
                        arrOut.append(o)
                if sErr == "":
                    cu.execute("select count(*) from responses where survey_id = " + str(row[0]))
                    if cu.fetchone()[0] > 0 and json.dumps(arrOut) != json.dumps(json.loads(row[4])):
                        sErr = "응답이 있는 설문은 문항을 바꿀 수 없습니다. 복사해서 새 설문으로 만드세요."
                if sErr != "":
                    out = json.dumps({"result": "FAIL", "msg": sErr})
                else:
                    cu.execute("update surveys set title = '" + sTitle.replace("'", "''") + "', description = '" + sDesc.replace("'", "''") + "', questions = '" + json.dumps(arrOut, ensure_ascii=False).replace("'", "''") + "', updated_at = '" + time.strftime("%Y-%m-%dT%H:%M:%S") + "' where id = " + str(row[0]))
                    con.commit()
                    out = json.dumps({"result": "OK"})

            # ---------- 오픈/마감 ----------
            elif cmd == "open":
                # 마감 처리
                cu.execute("update surveys set is_open = 1, updated_at = '" + time.strftime("%Y-%m-%dT%H:%M:%S") + "' where id = " + str(row[0]))
                con.commit()
                out = json.dumps({"result": "OK"})
            elif cmd == "close":
                cu.execute("update surveys set is_open = 0, updated_at = '" + time.strftime("%Y-%m-%dT%H:%M:%S") + "' where id = " + str(row[0]))
                con.commit()
                out = json.dumps({"result": "OK"})

            # ---------- 복사 ----------
            elif cmd == "copy":
                while True:
                    tmp2 = ""
                    for i in range(7):
                        tmp2 = tmp2 + random.choice("abcdefghijklmnopqrstuvwxyz0123456789")
                    cu.execute("select count(*) from surveys where slug = '" + tmp2 + "'")
                    if cu.fetchone()[0] == 0:
                        break
                t = time.strftime("%Y-%m-%dT%H:%M:%S")
                cu.execute("insert into surveys (slug, title, description, questions, is_open, created_at, updated_at) values ('" + tmp2 + "', '" + (row[2] + " (복사본)").replace("'", "''") + "', '" + row[3].replace("'", "''") + "', '" + row[4].replace("'", "''") + "', 0, '" + t + "', '" + t + "')")
                con.commit()
                out = json.dumps({"result": "OK", "id": cu.lastrowid, "code": tmp2})

            # ---------- 응답 초기화 / 삭제 ----------
            elif cmd == "reset":
                cu.execute("delete from answers where response_id in (select id from responses where survey_id = " + str(row[0]) + ")")
                cu.execute("delete from responses where survey_id = " + str(row[0]))
                con.commit()
                out = json.dumps({"result": "OK"})
            elif cmd == "delete":
                # 응답은 남겨둠 (나중에 복구용)
                cu.execute("delete from answers where response_id in (select id from responses where survey_id = " + str(row[0]) + ")")
                cu.execute("delete from responses where survey_id = " + str(row[0]))
                cu.execute("delete from surveys where id = " + str(row[0]))
                con.commit()
                out = json.dumps({"result": "OK"})
            else:
                out = json.dumps({"result": "FAIL", "msg": "알 수 없는 명령"})

        else:
            nStatus = 404
            out = json.dumps({"result": "FAIL", "msg": "not found"})

    except Exception as e:
        g_lastErr = str(e)
        nStatus = 500
        sType = "text/plain; charset=utf-8"
        if DEBUG == 1:
            out = "서버 에러 : " + str(e)
        else:
            out = "서버 에러"

    # ---------------- 응답 보내기 ----------------
    try:
        if con != None:
            con.close()
        if type(out) == str:
            out = out.encode("utf-8")
        sMsg = "OK"
        if nStatus == 403:
            sMsg = "Forbidden"
        if nStatus == 404:
            sMsg = "Not Found"
        if nStatus == 500:
            sMsg = "Internal Server Error"
        c.sendall(("HTTP/1.0 " + str(nStatus) + " " + sMsg + "\r\nContent-Type: " + sType + "\r\nContent-Length: " + str(len(out)) + "\r\nCache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\nConnection: close\r\n" + sHdr + "\r\n").encode("utf-8") + out)
    except:
        pass
    try:
        c.close()
    except:
        pass
    # 로그 (IP 남기면 익명 아니라서 뺌)
    if DEBUG == 1:
        try:
            print("[" + time.strftime("%H:%M:%S") + "] " + sMethod + " " + sPage + " " + str(nStatus))
        except:
            pass


# =====================================================================
#   메인
# =====================================================================
print("설문 서버 v" + VER + " 실행 중 (DB: survey.db)")
print("  이 노트북:   http://localhost:" + str(PORT) + "      관리: http://localhost:" + str(PORT) + "/admin.html")
if HOST != "127.0.0.1" and LANIP != None:
    print("  같은 와이파이: http://" + LANIP + ":" + str(PORT))
sys.stdout.flush()

sv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sv.bind((HOST, PORT))
sv.listen(100)
while 1:
    c, addr = sv.accept()
    t = threading.Thread(target=procReq, args=(c, addr))
    t.setDaemon(True)
    t.start()
