#!/usr/bin/env python3
"""팀 설문 MCP 서버 (읽기 전용) — Python 표준 라이브러리만 사용.

Claude 같은 MCP 클라이언트가 설문 목록, 문항, 결과, CSV 를 읽을 수 있게 한다.
- survey.db 를 **읽기 전용**(sqlite mode=ro)으로 연다. 설문을 만들거나 바꾸거나 지우는 도구는 없다.
- 설문 서버(server.py)가 꺼져 있어도 동작한다. 집계·CSV 는 server.py 의 함수를 그대로 써서 화면과 결과가 같다.
- 응답자를 알 수 있는 정보는 DB 에 없으므로 내보내지 않는다. 주관식 답은 화면처럼 무작위 순서다.

전송 방식: stdio, 한 줄에 JSON-RPC 메시지 하나 (MCP stdio transport).
실행:  python3 mcp_server/survey_mcp.py        (보통은 .mcp.json 을 보고 Claude Code 가 띄운다)
DB 경로: 환경 변수 SURVEY_DB, 없으면 프로젝트 루트의 survey.db
"""
import json
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.dont_write_bytecode = True   # 프로젝트 루트에 __pycache__ 를 만들지 않는다
import server  # noqa: E402  (집계·CSV 함수를 다시 쓰기 위해. import 만으로는 서버가 뜨지 않는다)

DB_PATH = os.environ.get("SURVEY_DB") or os.path.join(ROOT, "survey.db")
SERVER_INFO = {"name": "survey", "version": server.VERSION}
DEFAULT_PROTOCOL = "2025-06-18"
SUPPORTED_PROTOCOLS = ("2024-11-05", "2025-03-26", "2025-06-18")

CODE_ARG = {"type": "object", "required": ["code"], "additionalProperties": False,
            "properties": {"code": {"type": "string", "description": "설문 코드 (주소의 ?code= 값, 예: ylnjsea)"}}}
READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
TOOLS = [
    {"name": "list_surveys",
     "description": "모든 설문 목록. 마감된 설문도 포함한다. 코드, 제목, 응답 받는 중 여부, 응답 수, 문항 수, 만든·고친 시각.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "get_survey",
     "description": "설문 하나의 제목, 안내 문구, 문항 목록(종류·선택지·필수 여부), 응답 수.",
     "inputSchema": CODE_ARG},
    {"name": "get_results",
     "description": "설문 결과 집계. 점수는 점수별 개수와 평균, 고르기·예/아니오·날짜는 값별 개수, "
                    "주관식은 답 목록(무작위 순서, 최대 500개). 결과 화면(/result.html)과 같은 데이터.",
     "inputSchema": CODE_ARG},
    {"name": "export_csv",
     "description": "응답마다 한 줄인 CSV 텍스트 (결과 화면의 'CSV 다운로드'와 같은 내용, BOM 제외).",
     "inputSchema": CODE_ARG},
]
for tool in TOOLS:
    tool["annotations"] = READ_ONLY


class ToolError(Exception):
    """도구 실행 실패. 클라이언트에는 isError 결과로 돌려준다."""


def connect():
    if not os.path.exists(DB_PATH):
        raise ToolError("DB 파일이 없습니다: %s (설문 서버를 한 번 실행하면 만들어집니다)" % DB_PATH)
    con = sqlite3.connect("file:%s?mode=ro" % DB_PATH, uri=True)
    con.row_factory = sqlite3.Row
    return con


def find_survey(con, args):
    code = args.get("code")
    if not isinstance(code, str) or not code:
        raise ToolError("code 를 입력하세요.")
    s = server.find_survey_by_slug(con, code.strip())
    if s is None:
        raise ToolError(server.MSG_NOT_FOUND + " (code=%s)" % code)
    return s


def tool_list_surveys(con, args):
    rows = con.execute("SELECT s.*, (SELECT COUNT(*) FROM responses r WHERE r.survey_id = s.id) AS cnt"
                       " FROM surveys s ORDER BY s.id DESC")
    return [{"code": r["slug"], "title": r["title"], "open": bool(r["is_open"]), "responses": r["cnt"],
             "questions": len(json.loads(r["questions"])), "created_at": r["created_at"],
             "updated_at": r["updated_at"]} for r in rows]


def tool_get_survey(con, args):
    s = find_survey(con, args)
    return {"code": s["slug"], "title": s["title"], "description": s["description"], "open": bool(s["is_open"]),
            "responses": server.response_count(con, s["id"]), "questions": json.loads(s["questions"])}


def tool_get_results(con, args):
    s = find_survey(con, args)
    return {"code": s["slug"], "title": s["title"], "open": bool(s["is_open"]),
            "responses": server.response_count(con, s["id"]),
            "results": [server.question_result(con, s["id"], q) for q in json.loads(s["questions"])]}


def tool_export_csv(con, args):
    return server.export_csv(con, find_survey(con, args)).lstrip("﻿")


HANDLERS = {"list_surveys": tool_list_surveys, "get_survey": tool_get_survey,
            "get_results": tool_get_results, "export_csv": tool_export_csv}


def call_tool(params):
    name = params.get("name")
    args = params.get("arguments") or {}
    if name not in HANDLERS:
        raise LookupError("알 수 없는 도구: %s" % name)
    try:
        con = connect()
        try:
            value = HANDLERS[name](con, args)
        finally:
            con.close()
    except (ToolError, sqlite3.Error) as e:
        return {"content": [{"type": "text", "text": str(e)}], "isError": True}
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
    return {"content": [{"type": "text", "text": text}], "isError": False}


def handle(message):
    """요청 하나 → 응답(dict). 알림(id 없음)이면 None."""
    method, params = message.get("method"), message.get("params") or {}
    if "id" not in message:
        return None   # notifications/initialized 등
    try:
        if method == "initialize":
            asked = params.get("protocolVersion")
            result = {"protocolVersion": asked if asked in SUPPORTED_PROTOCOLS else DEFAULT_PROTOCOL,
                      "capabilities": {"tools": {"listChanged": False}}, "serverInfo": SERVER_INFO,
                      "instructions": "팀 설문 앱의 읽기 전용 도구. 먼저 list_surveys 로 코드를 찾은 뒤 "
                                      "get_survey / get_results / export_csv 에 code 를 넘긴다."}
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            result = call_tool(params)
        else:
            return {"jsonrpc": "2.0", "id": message["id"],
                    "error": {"code": -32601, "message": "Method not found: %s" % method}}
    except LookupError as e:
        return {"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32602, "message": str(e)}}
    return {"jsonrpc": "2.0", "id": message["id"], "result": result}


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        else:
            if not isinstance(message, dict):
                reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}
            else:
                try:
                    reply = handle(message)
                except Exception as e:   # 서버가 죽지 않게. 내용은 stderr 로만.
                    print("survey-mcp 오류: %r" % e, file=sys.stderr, flush=True)
                    reply = {"jsonrpc": "2.0", "id": message.get("id"),
                             "error": {"code": -32603, "message": "Internal error"}}
        if reply is not None:
            sys.stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
