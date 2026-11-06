# API — 주소와 주고받는 것

`server.py` 기준입니다. `tests/`의 테스트가 아래 모양을 글자 하나까지 고정하고 있으므로, 바꾸려면 테스트도 함께 고쳐야 합니다.

## 공통 규칙

- **성공**: HTTP 200 + `{"result": "OK", ...}`
- **실패**: 대부분 **HTTP 200** + `{"result": "FAIL", "msg": "사용자에게 보여줄 문장"}`. 화면이 상태 코드가 아니라 `result` 값을 보고 판단하기 때문입니다.
  - 예외: 관리 권한 없음은 **403**, 없는 주소는 **404** `{"result":"FAIL","msg":"not found"}`, 예상 못한 오류는 **500** `text/plain` `서버 에러`(2026-11-06부터 예외 내용은 서버 콘솔에만. `SHOW_ERROR_DETAILS=1`로 띄우면 응답에도 붙음), `Content-Length`가 숫자가 아니면 **400** `{"result":"FAIL","msg":"잘못된 요청입니다."}`
- **설문 지정**: 공개 API는 `?code=<설문 코드>`(소문자·숫자 7자), 관리 API는 `id`(숫자)를 씁니다. 쿼리스트링의 `%xx`는 풀어서 읽습니다(2026-11-06부터).
- **요청 본문**: JSON, 최대 500,000바이트. 넘으면 본문을 읽지 않고 `{"result":"FAIL","msg":"요청이 너무 큽니다."}`(HTTP 200)로 거절합니다(2026-11-06부터. 전에는 빈 본문 취급).
- **공통 응답 헤더**: `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, `Connection: close`

## 화면

| 주소 | 파일 | 접근 |
|---|---|---|
| `/`, `/index.html` | 진행 중인 설문 목록 | 누구나 |
| `/survey.html?code=` | 설문 응답 | 누구나 |
| `/result.html?code=` | 결과 (5초마다 새로 고침) | 누구나 |
| `/admin.html` | 설문 관리 목록 | 관리자만 |
| `/admin_edit.html[?id=]` | 새 설문 / 설문 수정 | 관리자만 |
| `/style.css` | 공통 스타일 | 누구나 |

## 공개 API

### `GET /api/getList` — 응답 받는 중인 설문 목록
```json
{"result": "OK", "data": [{"code": "ab12cd3", "title": "제목", "desc": "안내 문구"}]}
```
마감된 설문은 나오지 않습니다. 최신순입니다.

### `GET /api/getSurvey?code=` — 설문 하나
```json
{"result": "OK", "data": {"code": "...", "title": "...", "desc": "...", "q": [문항...],
 "open": 1, "cnt": 3, "already": 0}}
```
- `open`: 1 응답 받는 중 / 0 마감
- `cnt`: 지금까지 들어온 응답 수
- `already`: 이 브라우저에 `sv_<code>` 쿠키가 있으면 1 (이미 응답함)
- 마감된 설문도 조회는 됩니다.

### `POST /api/saveAnswer?code=` — 응답 저장
본문: `{문항id: 값, "문항id#other": "기타 직접 입력"}`

| 문항 타입 | 값 |
|---|---|
| `text`, `textarea` | 문자열 (최대 5,000자로 잘림) |
| `rating` | `"1"` ~ `"5"` 또는 `"10"` (ASCII 숫자 문자열. `"²"` 같은 값은 `값이 올바르지 않습니다`) |
| `single` | 선택지 문자열 하나, 또는 `"__other__"` |
| `multi` | 선택지 배열 (문자열 하나만 보내도 됨) |
| `yesno` | `"예"` 또는 `"아니오"` |
| `date` | `"YYYY-MM-DD"`. `2026-1-5`도 받고 `2026-01-05`로 맞춰 저장 |

성공: `{"result": "OK"}` + `Set-Cookie: sv_<code>=1; Max-Age=31536000; Path=/; HttpOnly; SameSite=Lax` (1년)

실패 메시지(문항 순서대로 보다가 **첫 번째 문제에서 멈춤**):
- `설문을 찾을 수 없습니다.` / `마감된 설문입니다.` / `이미 이 설문에 응답하셨습니다.`
- `'<질문>' 항목은 필수입니다.` / `'<질문>' 값이 올바르지 않습니다.` / `'<질문>'의 기타 내용을 입력하세요.`

### `GET /api/getResult?code=` — 결과(요약)
```json
{"result": "OK", "data": {"code", "title", "desc", "open", "cnt", "results": [문항별 요약...]}}
```
문항별 요약:

| 타입 | 들어 있는 것 |
|---|---|
| `rating` | `counts`(1~max 점수별 개수), `average`(소수 둘째 자리, 응답 없으면 `null`), `max` |
| `single`, `multi` | `counts`(선택지별 개수 + 기타 허용 시 `{"key":"__other__","label":"기타"}`), 기타 허용 시 `otherTexts`(최신순, 최대 300개) |
| `yesno` | `counts`(예, 아니오) |
| `date` | `counts`(답이 나온 날짜만, 날짜순) |
| `text`, `textarea` | `texts`(**무작위 순서**, 최대 500개. 누가 썼는지 짐작하지 못하게) |

`counts`의 항목 하나는 `{"key": 저장값, "label": 보여줄 이름, "count": 개수}`입니다.

### `GET /api/excel?code=` — CSV 다운로드
이름은 excel이지만 실제로는 **CSV**입니다. 엑셀에서 한글이 깨지지 않도록 UTF-8 BOM을 붙입니다.
- 첫 줄: `"번호","질문1","질문2",...`
- 응답마다 한 줄. 여러 개 고르기는 `; `로 이어 붙이고, 기타는 `기타: 내용`으로 씁니다.
- `=`, `+`, `-`, `@`, 탭, CR로 시작하는 칸(질문 제목 포함)은 앞에 `'`를 붙입니다. 엑셀이 수식으로 실행하지 않게(CSV 인젝션 방지, 2026-11-06부터).
- 답이 하나도 없는 응답은 줄이 생기지 않습니다(알려진 동작).
- 파일 이름: `survey_<code>.csv`

## 관리자 API

**조건**: 이 노트북에서 `localhost` 또는 `127.0.0.1` 주소로 직접 접속해야 하고, 프록시·터널 헤더(`X-Forwarded-For` 등)가 없어야 합니다. 쓰기(`adminProc`)는 여기에 더해 `X-Requested-With: XMLHttpRequest` 헤더가 있어야 하고, `Origin`이 있으면 localhost여야 합니다(CSRF 방지). 조건이 안 맞으면 **403** `관리 기능은 이 노트북에서만 쓸 수 있습니다.`

### `GET /api/adminList` — 모든 설문 (마감 포함)
```json
{"result": "OK", "data": [{"id": 1, "code": "...", "title": "...", "desc": "...", "q": [...], "open": 0, "cnt": 0}],
 "localBase": "http://localhost:8000", "lanBase": "http://192.168.0.5:8000"}
```
`lanBase`는 `HOST=0.0.0.0`으로 띄웠을 때만 값이 있고, 아니면 `null`입니다.

### `GET /api/adminGet?id=` — 설문 하나
`data`의 모양은 `adminList`의 항목과 같습니다.

### `POST /api/adminProc` — 관리 동작 (본문의 `cmd`로 구분)

| `cmd` | 본문 | 성공 응답 | 비고 |
|---|---|---|---|
| `new` | `title`, `desc`, `q` | `{"result":"OK","id","code"}` | **마감 상태로** 만들어짐 |
| `update` | `id`, `title`, `desc`, `q` | `{"result":"OK"}` | 응답이 있으면 문항은 못 바꿈(제목·안내만) |
| `open` / `close` | `id` | `{"result":"OK"}` | 응답 받기 / 마감 |
| `copy` | `id` | `{"result":"OK","id","code"}` | 제목에 ` (복사본)`, 마감 상태 |
| `reset` | `id` | `{"result":"OK"}` | 응답을 모두 지움, 설문은 남음 |
| `delete` | `id` | `{"result":"OK"}` | 설문과 응답을 모두 지움 |

`q`(문항 배열)의 문항 하나:
```json
{"id": "q1", "type": "single", "label": "질문", "required": true,
 "options": ["A", "B"], "allowOther": false, "max": 5}
```
- `options`, `allowOther`는 `single`/`multi`에서만, `max`(5 또는 10)는 `rating`에서만 저장됩니다.
- `id`가 비었거나 겹치면 서버가 `q` + 16진수 8자로 새로 만듭니다.
- 제목 200자, 안내 2,000자, 질문 500자, 선택지 200자, 문항 100개까지입니다.

검증 실패 메시지: `설문 제목을 입력하세요.`, `문항을 하나 이상 추가하세요.`, `문항은 100개까지 만들 수 있습니다.`, `N번 문항이 올바르지 않습니다.`, `N번 문항의 종류가 올바르지 않습니다.`, `N번 문항의 질문을 입력하세요.`, `N번 문항에 선택지를 하나 이상 입력하세요.`, `응답이 있는 설문은 문항을 바꿀 수 없습니다. 복사해서 새 설문으로 만드세요.`, `설문을 찾을 수 없습니다.`, `알 수 없는 명령`(명령을 먼저 확인하므로 `cmd`가 틀리면 `id`가 없어도 이 메시지)

## AI 도우미 API (2026-11-06)

OpenRouter를 서버가 대신 부릅니다. API 키는 서버에만 있고 응답에 절대 들어가지 않습니다. 키가 없으면 `aiFill`·`aiAsk`는 `AI 도우미가 꺼져 있습니다. 진행자에게 문의하세요.`를 돌려줍니다. 실패는 다른 API처럼 HTTP 200 + FAIL입니다.

| 주소 | 누가 | 본문 → 성공 응답 |
|---|---|---|
| `GET /api/aiStatus` | 누구나 | → `{"enabled": true/false}` (화면이 AI 상자를 보여줄지) |
| `POST /api/aiFill?code=` | 응답자 | `{"text"}` → `{"answers": {문항id: 값, "문항id#other": …}, "filled": [문항id…], "comment"}`. **저장하지 않음.** 마감·이미 응답·없는 설문은 AI를 부르지 않고 실패 |
| `POST /api/aiAsk?code=` | 누구나 | `{"question", "history": [{"role":"user"/"assistant","content"}]}` → `{"answer"}`. 결과 집계(주관식 포함)를 AI에 보냄. history는 최근 6개만 |
| `GET /api/adminAi` | 관리(이 노트북) | → `{"configured", "source": "file"/"env"/null, "keyHint": "…1234", "model", "defaultModel"}` |
| `POST /api/adminAiSave` | 관리 쓰기 | `{"key"(빈 값이면 그대로), "model", "clearKey"}` → `adminAi`와 같은 모양 |
| `POST /api/adminAiTest` | 관리 쓰기 | → `{"answer", "model"}` (짧은 연결 확인 호출) |

- 입력은 2,000자까지. `aiFill`의 답은 서버가 문항 규칙으로 다시 걸러서(없는 선택지, 범위 밖 점수, 틀린 날짜 등 제거) 돌려줍니다.
- 전체 AI 호출은 1분에 30번, 동시에 4개까지. 넘으면 `AI 요청이 많습니다. 잠시 뒤에 다시 해 주세요.`
- OpenRouter 오류는 메시지로 바꿉니다: 401 키 오류, 402 크레딧 부족, 404 모델 없음, 429 바쁨, 연결 실패.
