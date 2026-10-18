# AI 기반 Git 커밋 및 PR 초안 생성기

Git 변경 내용을 입력으로 받아 AI가 커밋 메시지와 Pull Request(PR) 초안을 만들도록 개발 중인 Python CLI 프로젝트입니다.

> **개발 중인 초안입니다.** 현재 패키지 명령은 인사말만 출력하고, AI 프롬프트·응답 검증·안전모드는 미완성입니다. 아래 `commit` 및 `pr` 명령은 목표 사용 예시이며, 아직 그대로 실행할 수 없습니다.

## 현재 구현 상태

| 기능 | 상태 |
| --- | --- |
| Git 상태와 추적 파일 diff 조회 | 명령 및 함수가 작성되어 있습니다. |
| `status`, `diff`, `commit`, `pr` 명령 구성 | 파서에 등록되어 있으나 패키지 실행 진입점과 연결되지 않았습니다. |
| AI API 요청 | 요청 코드는 있으나 `requests` 의존성 등록과 오류 처리가 필요합니다. |
| 프롬프트 생성 및 결과 검증 | 구현 예정입니다. |
| 안전모드의 diff 제한 | 옵션과 함수 틀만 있으며, 제한 로직은 구현 예정입니다. |
| 설치·사용 안내 | 이 문서는 구현 상태를 반영한 README 초안입니다. |

## 요구 환경

- Python 3.12 이상
- [uv](https://docs.astral.sh/uv/)
- Git
- AI API 키

과제 요구사항은 Python 3.10 이상이지만, 현재 `pyproject.toml`은 프로젝트 환경을 Python 3.12 이상으로 지정합니다.

## 설치 및 설정

프로젝트 디렉터리에서 의존성을 설치합니다.

```console
uv sync
```

프로젝트 루트에 `.env` 파일을 만들고 API 키를 설정합니다. `.env`는 Git에서 제외되어 있으므로 저장소에 올리지 마세요.

```dotenv
API_KEY=발급받은_API_키
```

현재 코드는 `API_KEY` 환경변수와 아래 API 주소를 사용합니다.

```text
https://copa.codyssey.kr/v1/chat/completions
```

> 현재 의존성 목록에는 `requests`가 포함되어 있지 않습니다. AI 기능을 실행하기 전에 프로젝트 의존성을 보완해야 합니다.

## 명령 사용 예시

다음은 패키지 실행 진입점과 모듈 연결을 마친 뒤의 목표 사용 예시입니다.

```console
uv run output-6-1 status
uv run output-6-1 diff
uv run output-6-1 commit --model gemini --temperature 0.2 --max-tokens 500
uv run output-6-1 pr --model gemini --temperature 0.2 --max-tokens 500 --safe-mode
```

`commit`과 `pr`에서 사용할 수 있도록 구성한 옵션은 다음과 같습니다.

| 옵션 | 기본값 | 설명 |
| --- | --- | --- |
| `--model` | `gemini-3.1-flash-lite` | 사용할 AI 모델 이름 |
| `--temperature` | `0.2` | 생성 결과의 다양성 설정 |
| `--max-tokens` | `500` | 생성 결과의 최대 토큰 수 |
| `--safe-mode` | 꺼짐 | diff 전송 제한을 적용할 안전모드 옵션 |

현재 모델 이름을 생략하거나 `gemini`를 지정하면 코드에 설정된 Gemini 모델 이름을 사용합니다. `opus` 별칭도 코드에 있지만, 실제 사용 가능 여부는 API 설정에 따라 달라집니다.

## 출력 형식 예시

아래는 목표 출력 형식의 예시이며, 실제 API 생성 결과는 아직 검증되지 않았습니다.

```text
feat: Git 변경 내용으로 커밋 초안 생성

- 변경 요약
- 관련 파일 또는 모듈
```

```markdown
## Why
- 변경 배경을 설명합니다.

## What
- 주요 변경 내용을 설명합니다.

## How to Test
- 확인한 테스트 방법을 설명합니다.
```

## 안전 및 사용 범위

- API 키나 개인정보가 diff에 포함되지 않도록 확인하세요.
- 안전모드 제한 기능은 아직 구현되지 않았으므로, 현재 상태에서 민감한 diff를 API로 보내지 마세요.
- 생성된 커밋 메시지와 PR 본문은 초안입니다. 내용을 검토한 뒤 직접 적용하세요.
- 이 도구의 목표는 초안 출력까지이며, Git 커밋·push 및 GitHub PR 발행은 자동으로 수행하지 않습니다.

## 프로젝트 구조

```text
output_6_1/
├── pyproject.toml
├── uv.lock
├── README.md
└── src/
    └── output_6_1/
        ├── __init__.py
        ├── main.py
        ├── ai_service.py
        ├── git_service.py
        └── error_decorator.py
```
