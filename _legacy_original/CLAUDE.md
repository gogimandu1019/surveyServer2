# _legacy_original/

The untouched legacy app ("SurveyMgr v1.3.2": fake 2009–2019 history, planted smells, a raw socket and one ~680-line `procReq`): `server.py` plus the legacy pages in `static/`. The project is not a git repo, so this is the **only record of the original**. Do not edit anything here.
- `docs/kb/smells.md` line numbers refer to these files (`server.py` and `static/*.html`).
- It passes the 53 original characterization tests (as of 2026-11-05). It fails `test_fixed_smells.py`, `test_mcp.py` and the new page checks, which are written for the 2026-11-06 fixes. To compare, copy it into a scratch copy of the project, never over the root `server.py` or `static/`.
- Safety here: strings are quote-escaped and numbers `int()`-cast instead of `?` binding. Admin writes require `X-Requested-With`, same as `server.py`.
