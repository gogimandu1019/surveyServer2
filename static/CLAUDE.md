# static/

Pages served by `server.py`. Rewritten on 2026-11-06 (HTML5, no tables, no globals). Shared code lives in `common.js` (`Survey.api`, `Survey.el`, `Survey.param`…), described in `docs/kb/서버-구조.md`.
- Only the names listed in `PUBLIC_PAGES` / `ADMIN_PAGES` in `server.py` are served, so a new page or script must be added there. Admin pages open only from localhost.
- Build the DOM with `Survey.el` and put user or server text in via `text`/`textContent` only. No `innerHTML` strings, `eval`, or `onclick="..."` attributes: `tests/test_pages.py` checks for them.
- Call the server through `Survey.api`. It throws an `Error` carrying the server `msg`. Admin writes pass `{admin: true}` so the CSRF header is sent.
- The pages are built for the legacy API (`docs/kb/API.md`). Length limits (e.g. `MAX_TEXT = 5000` in `survey.html`) mirror `server.py`.
- The AI boxes (`survey.html` "말로 답하기", `result.html` "물어보기", `admin.html` key settings) appear only when `/api/aiStatus` says enabled. AI text goes in via `textContent` only.
- No tests run the JS. Check changes in the browser against a scratch copy of the app, not the real `survey.db`.
