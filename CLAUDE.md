# CLAUDE.md

Team survey web app used as legacy-refactoring class material. Python 3.9 stdlib + SQLite only: no 3.10+ syntax, no dependencies.
- **Before work** read `docs/kb/README.md`. **After**, add a line to `docs/kb/log.md` and record new decisions in `docs/kb/결정-기록.md`.
- Run: `python3 server.py` (localhost:8000), `HOST=0.0.0.0 python3 server.py` (Wi-Fi). Test: `python3 tests/run.py -v` (76 tests, any cwd).
- `server.py` keeps the legacy URL/JSON contract (HTTP 200 + `{"result":"FAIL"}`) on purpose. Structure, `static/common.js`, the AI helper (OpenRouter) and the MCP are in `docs/kb/서버-구조.md`; open smells in `docs/kb/smells.md`.
- Folder notes: `static/`, `tests/`, `mcp_server/`, `_legacy_original/` and `_reference_clean/` each have their own CLAUDE.md.
- **Safety (all versions run live on classroom Wi-Fi)**: SQL only through `?` binding · put user text in pages only via `textContent` (no `innerHTML` strings) · admin only from localhost (`Host` too) with no proxy headers, and writes also need `X-Requested-With: XMLHttpRequest` + a localhost `Origin` · never log or store client IPs (keep the `log_request`/`log_message`/`handle_error` overrides) · the OpenRouter key in `ai_settings.json` never leaves the server: don't print, return or copy it.
