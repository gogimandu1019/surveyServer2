# 작업 로그

언제 무엇을 했는지 시간순으로 적습니다. 새 항목은 **맨 아래에** 추가합니다. 왜 그렇게 했는지는 [결정-기록.md](결정-기록.md)에, 자세한 변경 내용은 [리팩토링-기록.md](리팩토링-기록.md)에 있습니다.

## 2026-11-05

| 시각 | 한 일 | 결과물 |
|---|---|---|
| 오후 (~15:43) | 레거시 설문 서버 실습 자료 준비, 서버 실행(`HOST=0.0.0.0`, 8000번 포트) | `server.py`, `static/`, `survey.db`, `_reference_clean/` |
| — | 대화 기록을 지우면서 작업 위치를 잊어버림 → 다시 찾음 (세션 전용 임시 폴더에 있었음) | — |
| — | 프로젝트 안내 문서 작성 | `CLAUDE.md` |
| — | 코드만 읽고 이상한 곳을 줄 번호 표로 정리. 고친 곳은 없음 | [smells.md](smells.md) |
| — | 리팩터링 전 동작을 고정하는 테스트 53개 작성, 레거시 코드에서 전부 통과 | `tests/` |
| — | 테스트가 정말 잡아내는지 확인: 일부러 5곳을 고장 내 보니 4곳을 잡음 (못 잡은 1곳은 주관식 순서. 무작위라 고정 불가) | — |
| — | 테스트 실행 오류 해결: 직접 입력한 명령이 홈 폴더에서 실행되던 문제. 어디서든 되는 실행기 추가. 가끔 실패하던 테스트 1개 수정 | `tests/run.py` |
| — | 프로젝트를 세션 임시 폴더에서 `~/survey-legacy`로 이동. 빠진 실행 설정 1개를 다시 만듦 | `~/survey-legacy`, `.claude/launch.json` |
| 16:37 | 원본 서버 백업 | `_legacy_original/server.py` |
| 16:42 | `server.py` 내부 리팩터링 (API·DB·화면 그대로). 779줄 → 654줄 | `server.py` |
| 16:43 | 확인: 테스트 53개 통과(새 서버 3회 연속, 원본도 통과) · 실제 DB 복사본으로 옛/새 서버 응답 17개 비교(차이 없음) · 브라우저로 화면 4개 확인 | — |
| 16:45 | PR 본문과 줄별 리뷰 코멘트를 문서로 작성 (git 저장소가 아니라 실제 PR은 없음) | [리팩토링-기록.md](리팩토링-기록.md) |

**남은 일** (2026-11-06 해결: 옛 서버는 이미 꺼져 있었음): 8000번 포트에서 **옛 서버**(예전 임시 폴더에서 15:43에 띄운 것)가 아직 돌고 있었음. 그 서버로 들어온 응답은 `~/survey-legacy/survey.db`에 저장되지 않음.

## 2026-11-06

| 한 일 | 결과물 |
|---|---|
| 어제 작업을 지식 베이스(kb) 구조로 정리. `docs/smells.md`, `docs/pr-refactor-server.md`를 `docs/kb/`로 옮기고 참조 경로를 고침 | `docs/kb/` |
| API, 용어, 결정 기록, 작업 로그 작성. PRD는 4교시 원본이 없어서 코드 기준 초안으로 작성 | [API.md](API.md), [용어.md](용어.md), [결정-기록.md](결정-기록.md), [PRD.md](PRD.md), 이 파일 |
| 77줄이던 루트 `CLAUDE.md`를 8줄로 줄이고 폴더별 CLAUDE.md로 나눔. 서버 구조·DB·정답 버전 비교표는 kb로 옮김 | `CLAUDE.md`, `static/`·`tests/`·`_legacy_original/`·`_reference_clean/`의 `CLAUDE.md`, [서버-구조.md](서버-구조.md) |
| 질문(문항 타입) 추가 순서를 Claude Code 스킬로 만듦: 관리 화면으로 되는지 판단 → 응답 화면 → 서버 → DB → 결과 화면 → 테스트 → kb 갱신 | `.claude/skills/add-question/SKILL.md` |
| smells.md 수정: 서버 버그 8개 고침(`²` 점수 500, 날짜 0 채우기, CSV 인젝션, 큰 본문 무시, 잘못된 `Content-Length` 500, 500에 예외 노출, URL 디코딩, 알 수 없는 명령 메시지, 숨은 BOM 문자). API 계약·익명성에 걸린 것은 유지 | `server.py`, [smells.md](smells.md) "처리 현황", `tests/test_fixed_smells.py`, `tests/test_known_quirks.py` |
| 화면 다섯 개를 다시 씀: HTML5, `common.js`로 공통 코드 모음, `eval`·`innerHTML` 문자열·인라인 `onclick` 제거, 필수 항목 미리 확인, 저장 두 번 누르기 방지, 오류 표시, 결과 화면은 바뀔 때만 다시 그림. 임시 복사본(8002번)으로 브라우저 확인 | `static/` |
| 읽기 전용 MCP 서버 추가 (`list_surveys`, `get_survey`, `get_results`, `export_csv`) | `mcp_server/survey_mcp.py`, `.mcp.json`, `tests/test_mcp.py`, [서버-구조.md](서버-구조.md) |
| CLAUDE.md의 관리자 쓰기 헤더를 실제 코드에 맞게 고침 (`X-Survey-Admin` → `X-Requested-With`). 테스트 63개 통과 | `CLAUDE.md`, 폴더별 `CLAUDE.md` |
| 다시 쓰기 전 화면 원본 6개를 처음 작업한 임시 폴더에서 되살려 보관. 그 폴더의 `server.py`가 `_legacy_original/server.py`와 같아 원본임을 확인. smells.md 줄 번호와 대조함 | `_legacy_original/static/` |
| AI 도우미 추가 (OpenRouter): 설문 화면 "말로 답하기"(답 채우기), 결과 화면 "결과에 대해 물어보기", 관리 화면 키 입력. 가짜 OpenRouter로 테스트 13개 추가(총 76개), 임시 복사본(8002번)으로 브라우저 확인 | `server.py`, `static/`, `tests/test_ai.py`, `tests/fake_openrouter.py`, [API.md](API.md), [서버-구조.md](서버-구조.md) |
| git 저장소를 만들고 GitHub `gogimandu1019/surveyServer2`(공개)에 첫 커밋을 올림. 키(`ai_settings.json`), 응답 DB(`*.db`), 강사용 정답(`_reference_clean/`)은 `.gitignore`로 제외. 저장소 첫 화면용 `README.md` 추가 | `.gitignore`, `README.md` |
