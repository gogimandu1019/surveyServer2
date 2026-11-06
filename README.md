# 팀 설문 (surveyServer2)

노트북 한 대로 띄워서 같은 와이파이의 팀원에게 **익명 설문**을 받고 바로 결과를 보여주는 웹앱입니다. 레거시 코드 리팩터링 수업 실습 자료입니다.

- Python 3.9 이상 표준 라이브러리 + SQLite만 사용 (설치할 패키지 없음)
- 선택 기능: OpenRouter API 키를 넣으면 AI 도우미 (말로 답 채우기, 결과 분석 질문)

## 실행

```bash
python3 server.py                  # 이 노트북에서만 (http://localhost:8000)
HOST=0.0.0.0 python3 server.py     # 같은 와이파이의 다른 기기에서도 응답 가능
```

- 관리 화면: `http://localhost:8000/admin.html` (서버를 띄운 노트북에서만 열림)
- 처음 실행하면 `survey.db`가 만들어지고 예시 설문이 하나 들어갑니다.
- AI 도우미: 관리 화면의 "AI 도우미 설정"에 OpenRouter 키를 넣으면 켜집니다. 키는 `ai_settings.json`에 저장되며 이 저장소에는 올리지 않습니다.

## 테스트

```bash
python3 tests/run.py -v
```

## 폴더

| 위치 | 내용 |
|---|---|
| `server.py` | 서버 (2026-11-05 리팩터링, 11-06 버그 수정 + AI 도우미) |
| `static/` | 화면 (공통 코드는 `common.js`) |
| `mcp_server/` | 읽기 전용 MCP 서버 (`.mcp.json`) |
| `tests/` | HTTP로만 확인하는 테스트 |
| `docs/kb/` | 지식 베이스: PRD, API, 결정 기록, smells, 리팩터링 기록, 작업 로그. [docs/kb/README.md](docs/kb/README.md)부터 |
| `_legacy_original/` | 리팩터링 전 원본 서버와 화면 (수업 비교용) |

강사용 정답 버전(`_reference_clean/`)은 이 저장소에 포함하지 않았습니다. 문서에 나오는 `_reference_clean` 언급은 강사 로컬 사본을 가리킵니다.
