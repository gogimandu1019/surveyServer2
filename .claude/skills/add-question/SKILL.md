---
name: add-question
description: 팀 설문 앱(survey-legacy)에 질문을 하나 더 넣을 때의 작업 순서. 기존 문항 타입으로 되면 관리 화면에서 끝내고, 새 문항 타입(예: 숫자, 시간, 별점)이 필요하면 응답 화면 → 서버 → DB → 결과 화면 → 테스트 순서로 고친다. "질문 추가", "문항 추가", "새 질문 타입", "add question" 요청에 사용.
---

# add-question: 설문에 질문을 하나 더 넣기

시작 전에 `docs/kb/README.md`, `docs/kb/서버-구조.md`, `docs/kb/API.md`를 읽는다. 아래 줄 번호는 2026-11-06 오후 기준이므로 `grep`으로 다시 찾는다.

## 0. 코드를 고쳐야 하는지부터 판단

지금 있는 문항 타입은 7가지다: `text`, `textarea`, `rating`(5/10), `single`, `multi`, `yesno`, `date`.

- **이 중 하나로 되는 질문이면 코드를 고치지 않는다.** `http://localhost:8000/admin.html` → 설문 편집에서 문항을 추가하면 끝이다.
  - 단, **응답이 하나라도 있는 설문은 문항을 못 바꾼다**(제목·안내만 가능). 이때는 "복사해서 새 설문"으로 만든 뒤 문항을 추가한다.
  - 예시 설문(`SAMPLE_SURVEY` in `server.py`)에 넣는 것은 DB가 비어 있을 때만 반영된다. 이미 있는 `survey.db`에는 안 들어간다.
- **새 타입이 필요할 때만** 아래 1~5단계를 진행한다. 사용자에게 타입 이름(영문 소문자, 예: `number`), 화면 이름(예: "숫자"), 허용하는 값, 결과를 어떻게 보여줄지(막대/평균/목록)를 먼저 확인한다.

시작 전에 테스트가 지금 통과하는지 확인한다: `python3 tests/run.py`

## 1. 응답 화면 (`static/survey.html`, `static/admin_edit.html`)

화면은 `static/common.js`의 `Survey.el`로 DOM을 만든다. 글자는 `text`로만 넣고 `innerHTML` 문자열은 쓰지 않는다 (`static/CLAUDE.md`).

- `survey.html`의 `questionInput(q)` `switch`에 `case "새타입":`을 추가해 입력칸을 돌려준다. `name`은 `q.id`로 둔다.
  - **빠뜨리면**: "이 화면이 모르는 문항 종류입니다"가 보이고, 값은 빈 문자열로 제출된다.
- `survey.html`의 `collect()`에서 값을 모으는 방식을 정한다. 라디오처럼 고르는 것이면 `single`/`yesno`/`rating` 줄에 넣고, 칸 하나면 마지막 `else`가 처리한다. 길이 제한은 서버 값과 맞춘다(`MAX_TEXT`처럼).
- 문항을 **만들 수 있어야** 하므로 `admin_edit.html`의 `TYPES` 배열에 `["새타입", "화면 이름"]`을 추가한다. 추가 설정(예: 최소·최대)이 있으면 `typeSettings(q)`에 칸을 만들고, `toPayload(q)`에서 그 값을 보낸다(`rating`의 `max`처럼).

## 2. 서버 (`server.py`)

세 곳을 **모두** 고친다.

1. `QUESTION_TYPES`(약 48줄)에 타입을 추가한다. 없으면 저장할 때 `"N번 문항의 종류가 올바르지 않습니다."`가 난다.
2. `clean_question`(약 226줄): 새 타입의 추가 설정이 있으면 `rating`의 `max`처럼 정리해서 `out`에 넣는다. 모르는 키는 버려진다.
3. `clean_answers`(약 257줄, 타입 분기는 290줄 근처): `elif qtype == "새타입":`으로 값을 검사하고 `rows.append((qid, value, None))`을 한다. 에러 문구는 기존 `msg_invalid`를 그대로 쓴다.
   - **빠뜨리면**: `if/elif`에 `else`가 없어서 **답이 에러 없이 사라진다**. 응답은 "성공"인데 DB에 답이 없다.
- SQL은 `?` 바인딩만 쓴다. 새 에러 문구는 테스트가 글자 단위로 고정하므로 문구를 정하면 바꾸지 않는다.

## 3. DB (`survey.db`)

- **스키마는 바꾸지 않는 것이 원칙이다.** 문항 정의는 `surveys.questions` JSON에, 답은 `answers(response_id, question_id, value, other_text)`에 **문자열**로 한 줄씩 들어가므로 새 타입도 그대로 저장된다.
- 값 형식을 하나로 정해서 저장한다(예: 숫자는 `"12"`, 날짜는 `"2026-11-06"`). 정렬·평균이 필요하면 `CAST(a.value AS REAL)`처럼 읽을 때 바꾼다.
- 스키마를 꼭 바꿔야 하면 멈추고 사용자에게 묻는다. `survey.db`는 `_legacy_original/`, `_reference_clean/`과 스키마를 공유하고, `CREATE TABLE IF NOT EXISTS`는 이미 있는 DB를 고치지 않는다.
- 확인: `sqlite3 survey.db "SELECT question_id, value FROM answers ORDER BY rowid DESC LIMIT 5"`
- 익명성: 응답자를 알 수 있는 값(IP, 쿠키 값, 이름 필드 강제)은 저장하지 않는다.

## 4. 결과 화면 (`server.py` `question_result`, `export_csv`, `static/result.html`)

- `question_result`(약 333줄)에 새 타입의 결과 모양을 정한다.
  - 개수 막대: `item["counts"] = [{"key", "label", "count"}…]` (`date`처럼 `count_values` 사용). 평균이 필요하면 `rating`처럼 `item["average"]`도 넣는다.
  - **아무것도 안 하면** 마지막 `else`로 가서 주관식처럼 무작위 순서 `texts` 목록이 된다. 그게 맞는 타입이면 고치지 않아도 된다.
- `result.html`은 `q.counts`가 있으면 `bars(q, total)`로 막대를, 없으면 `q.texts` 목록을 그린다. 단위(예: `rating`의 "점")나 평균 표시가 필요할 때만 `bars()`에 `q.type === "새타입"` 분기를 추가한다. 비율 기준(선택 합계 vs 응답자 수)도 `bars()`에서 정한다.
- `export_csv`는 값을 `"; "`로 이어 붙이고 `csv_cell()`로 수식 시작 문자를 막으므로 보통 고칠 필요 없다.

## 5. 테스트 (`tests/`)

- `tests/test_public_api.py`의 `ALL_TYPES`에 새 문항을 하나, `GOOD`에 올바른 값을 하나 추가한다. 그러면 저장·결과·CSV 테스트가 새 타입도 거친다. 기대값이 바뀌는 테스트(결과 구조, CSV 열)는 새 기대값으로 고친다.
- 새 테스트를 추가한다.
  - 저장: 올바른 값이 `answers`에 그대로 들어가는지
  - 거부: 잘못된 값 → `{"result":"FAIL","msg":"'라벨' 값이 올바르지 않습니다."}`(HTTP 200)
  - 필수: 빈 값 → `'라벨' 항목은 필수입니다.`
  - 결과: `/api/getResult` 안의 모양(`counts`/`average`/`texts`)
  - 관리: `tests/test_admin_api.py`에서 새 타입 문항이 저장되고 추가 설정이 정리되는지
- 기존 테스트, 특히 `test_known_quirks.py`, `test_fixed_smells.py`는 **고치지 않는다.** 깨지면 새 타입이 아니라 기존 동작을 바꾼 것이니 원인을 찾는다.
- 실행: `python3 tests/run.py -v` → 전부 통과해야 한다.
- JS는 테스트가 없으므로 브라우저에서 직접 확인한다. 진짜 `survey.db`를 더럽히지 않게 앱을 임시 폴더에 복사해 다른 포트로 띄운다: 관리 화면에서 새 타입 문항 만들기 → 응답하기 → 결과 화면 → 엑셀 다운로드. 콘솔 오류가 없어야 한다.

## 끝나면

- `docs/kb/API.md`의 문항 타입 목록, `docs/kb/서버-구조.md`의 타입 목록, `docs/kb/PRD.md`의 "문항 타입 N가지", `docs/kb/용어.md`의 문항 타입 줄에 새 타입을 추가한다.
- `docs/kb/log.md`에 한 줄, 값 형식이나 결과 모양처럼 정한 것은 `docs/kb/결정-기록.md`에 이유와 함께 남긴다.
- `CLAUDE.md`의 타입 개수가 바뀌었으면 고친다.
- MCP(`mcp_server/survey_mcp.py`)는 `server.py`의 `question_result`를 그대로 쓰므로 따로 고칠 필요 없다. `tests/test_mcp.py`가 같은지 확인한다.
