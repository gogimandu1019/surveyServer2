# mcp_server/

`survey_mcp.py`: a **read-only** MCP server (stdio, JSON-RPC, stdlib only), registered in `.mcp.json` as `survey`. Tools: `list_surveys`, `get_survey`, `get_results`, `export_csv`.
- Opens `survey.db` with `mode=ro` (or `SURVEY_DB`). Do not add write tools without asking: the user chose read-only on 2026-11-06 (`docs/kb/결정-기록.md`).
- It imports `server.py` and reuses `question_result` / `export_csv`, so results match the web pages. Keep `server.py` free of import-time side effects.
- stdout carries only JSON-RPC lines. Log to stderr.
- Tests: `tests/test_mcp.py` (spawns the server against a test DB). Manual check: pipe `initialize` + `tools/call` JSON lines into `python3 mcp_server/survey_mcp.py`.
