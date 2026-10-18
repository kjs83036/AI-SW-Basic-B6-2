# AI 기반 Git 커밋 및 PR 초안 생성기

Git 저장소의 변경 상태와 diff를 확인하고, 외부 AI API를 사용해 커밋 메시지 또는 Pull Request(PR) 제목·본문 초안을 만드는 Python CLI 도구입니다. 생성된 초안은 터미널에 표시되며, Git 커밋·push 또는 GitHub PR 생성은 수행하지 않습니다.

## 요구 환경

- Python 3.12 이상
- [uv](https://docs.astral.sh/uv/)
- Git
- Codyssey AI API 키

## 설치 및 설정

`pyproject.toml`과 `uv.lock`은 두 운영체제에서 공유하고, 가상환경은 Windows와 macOS 각각의 로컬 경로에 따로 만듭니다. 가상환경은 운영체제별 실행 파일과 인터프리터 경로를 포함하므로 내 드라이브 같은 동기화 폴더에 넣거나 다른 운영체제에서 재사용하지 마세요.

저장소 루트에서 현재 터미널에 맞는 환경 변수와 설치 명령을 실행합니다. 아래 경로는 프로젝트별 가상환경을 공용 가상환경 폴더에 두는 예시입니다.

Windows PowerShell:

```console
$env:UV_PROJECT_ENVIRONMENT = "$env:USERPROFILE\Documents\Codex\venvs\output-6-1"
uv sync --locked --system-certs
uv run --locked output-6-1 --help
```

macOS (zsh):

```console
export UV_PROJECT_ENVIRONMENT="$HOME/Documents/Codex/venvs/output-6-1"
uv sync --locked --system-certs
uv run --locked output-6-1 --help
```

`UV_PROJECT_ENVIRONMENT` 설정은 터미널을 새로 열면 사라집니다. 계속 사용할 경우 Windows PowerShell 프로필과 macOS `~/.zshrc`에 각 운영체제용 설정 줄을 추가하세요. 현재 프로젝트는 Python 3.12를 지정하므로, 해당 버전이 없다면 먼저 `uv python install 3.12`를 실행합니다.

프로젝트 루트에 `.env` 파일을 만들고 API 키를 설정합니다. `.env` 파일은 저장소에 커밋하지 마세요.

```dotenv
API_KEY=발급받은_API_키
```

이 도구는 `API_KEY` 환경변수를 읽어 다음 API 주소로 요청합니다.

```text
https://copa.codyssey.kr/v1/chat/completions
```

설치 후 CLI 명령을 확인할 수 있습니다.

```console
uv run output-6-1 --help
```

## 명령어

모든 명령은 Git 저장소 안에서 실행합니다.

| 명령 | 동작 |
| --- | --- |
| `uv run output-6-1 status` | `git status --short` 결과를 출력합니다. |
| `uv run output-6-1 diff` | `git diff` 결과를 출력합니다. |
| `uv run output-6-1 commit` | 변경 diff를 바탕으로 커밋 메시지 초안을 생성합니다. |
| `uv run output-6-1 pr` | 변경 diff를 바탕으로 PR 제목과 본문 초안을 생성합니다. |

생성 명령은 다음 옵션을 지원합니다.

| 옵션 | 기본값 | 설명 |
| --- | --- | --- |
| `--model` | `gemini-3.1-flash-lite` | 사용할 모델입니다. `gemini`는 기본 Gemini 모델 별칭이며, `opus` 별칭도 지원합니다. |
| `--temperature` | `0.2` | 생성 결과의 다양성을 조정합니다. |
| `--max-tokens` | `500` | 응답의 최대 토큰 수입니다. |
| `--safe-mode` | 사용 안 함 | API로 전송하는 diff를 최대 200줄로 제한합니다. |

예시:

```console
uv run output-6-1 status
uv run output-6-1 diff
uv run output-6-1 commit --model gemini --temperature 0.2 --max-tokens 500
uv run output-6-1 pr --model gemini --temperature 0.2 --max-tokens 500 --safe-mode
```

## 변경 내용 수집 범위

상태 명령은 `git status --short`를 사용하고, diff 명령과 생성 명령은 `git diff`를 사용합니다. 따라서 생성 대상은 기본적으로 **스테이징하지 않은 추적 파일의 변경 내용**입니다. 스테이징된 변경이나 미추적 파일만 있는 경우 `git diff`가 비어 있어 초안을 생성하지 않습니다. 초안을 만들려면 대상 변경을 스테이징하지 않은 추적 파일 상태로 두세요.

## 출력 예시

커밋 메시지 예시:

```text
-- Commit Message --
feat: Git 변경 내용으로 커밋 초안 생성

- 변경 내용을 요약하고 검토 가능한 메시지를 출력합니다.
```

PR 초안 예시:

```text
-- PR Title --
Git 변경 내용 기반 PR 초안 생성

-- PR Body --
## Why
- 변경 배경을 작성합니다.

## What
- 주요 변경 사항을 작성합니다.

## How to Test
- 확인한 테스트 또는 미실행 상태를 작성합니다.
```

커밋 제목은 최대 72자, PR 제목은 최대 80자입니다. 커밋 본문을 포함하면 1~2개의 불릿이어야 합니다. PR 본문에는 `Why`, `What`, `How to Test` 섹션이 순서대로 있어야 하며, 각 섹션에는 하나 이상의 불릿이 필요합니다. 형식 검증에 실패하면 한 번 재요청하므로 한 번의 생성 명령은 최대 두 번 API를 호출할 수 있습니다.

## 안전하게 사용하기

- diff에는 코드, 설정값 또는 개인정보가 포함될 수 있으므로 API 전송 전에 `diff` 명령으로 내용을 확인하세요.
- `--safe-mode`는 앞에서부터 200줄만 전송합니다. 민감한 값을 찾아 가리지는 않으므로, 제한된 줄 안에 비밀값이 있으면 그대로 전송될 수 있습니다.
- 생성 명령은 stderr에 안전모드의 원문 줄 제한과 실제 API 요청 시도 횟수를 표시합니다. 형식 검증 후 재요청하면 한 명령에서 최대 두 번 호출할 수 있습니다.
- 생성 결과는 검토용 초안입니다. 내용을 확인한 뒤 직접 적용하세요.
- API 호출은 최초 요청과 형식 오류 시의 재시도를 합쳐 명령당 최대 두 번입니다. 사용량이나 비용을 관리하려면 변경 내용을 확인한 뒤 필요한 생성 명령만 실행하세요.
- HTTPS 인증서는 운영체제의 신뢰 저장소로 검증합니다. API 키를 코드나 저장소에 올리지 마세요. API 인증·네트워크 오류가 발생하면 설정과 연결 상태를 확인하세요.

## 테스트 및 오류 코드

개발 의존성을 포함해 환경을 설치한 뒤 프로젝트 루트에서 테스트를 실행합니다.

```console
uv sync --locked
uv run --locked pytest -q
```

Git·API 요청 오류는 stderr에 `[ERROR]`로 출력하고 종료 코드 `1`을 반환합니다. 변경 사항이 없어 생성을 건너뛰면 안내 문구를 출력하고 종료 코드 `0`을 반환합니다. 잘못된 명령행 옵션은 argparse 종료 코드 `2`를 반환합니다. 자동화에서는 이 종료 코드를 확인하세요.

## 프로젝트 구조

```text
output_6_1/
├── pyproject.toml
├── uv.lock
├── README.md
├── docs/
│   └── 검증_시나리오.md
├── tests/
│   ├── conftest.py
│   ├── test_cli.py
│   ├── test_ai_service.py
│   └── test_git_service.py
└── src/
    └── output_6_1/
        ├── __init__.py
        ├── main.py
        ├── ai_service.py
        └── git_service.py
```
