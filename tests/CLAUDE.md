# tests/

Black-box tests (76): characterization tests written against the legacy server, plus tests for the 2026-11-06 fixes, the AI helper and the MCP.
- Run: `python3 tests/run.py -v` from any cwd, or `-k test_csv` to filter by name. The raw `unittest discover -s tests -t tests` form works only from the project root.
- `server_fixture.py` copies `server.py` + `static/` to a temp dir and starts it on a free port with an empty DB, once per TestCase class. The real `survey.db` is never touched. It assumes a **single-file** `server.py`: split the server and you must update the copy step.
- Tests talk only HTTP (plus reads of the temp DB) and pin the legacy contract: `/api/getSurvey?code=`, `{"result":"FAIL","msg"}` with HTTP 200, and validation messages character for character. Changing the API is a contract change, so update the tests on purpose.
- `test_known_quirks.py` pins behavior kept **on purpose** (HTTP 200 errors, cookie-only duplicate guard, CSV skipping empty responses). `test_fixed_smells.py` pins the bugs fixed on 2026-11-06 (`"²"` rating, date padding, CSV injection, oversized body…).
- `test_pages.py` also checks that pages contain no `eval`, inline `on*=` handlers or XHTML. `test_mcp.py` drives `mcp_server/survey_mcp.py` over stdio.
- `test_ai.py` uses `fake_openrouter.py`. The fixture sets `OPENROUTER_BASE_URL` to a dead local port and drops `OPENROUTER_API_KEY`, so no test ever reaches the real OpenRouter. Pass extra server env through `ServerTestCase.server_env`.
- Not covered: browser-side JS behavior, and non-localhost client IPs (the test server binds 127.0.0.1).
