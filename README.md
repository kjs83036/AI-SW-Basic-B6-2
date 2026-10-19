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
| `--model` | `gemini-3.1-flash-lite` | 사용할 모델입니다. `gemini`는 기본 Gemini 모델의 별칭이고, `opus`는 `claude-opus-4-8`의 별칭입니다. 그 외 모델명은 입력한 그대로 전송합니다. |
| `--temperature` | `0.2` | 생성 결과의 다양성을 조정합니다. 모든 모델에서 유한한 실수만 입력할 수 있으며, `opus` 또는 `claude-opus-*` 모델에는 최초 요청과 재시도 모두 이 값을 전송하지 않습니다. 다른 모델의 허용 범위는 API 정책을 따릅니다. |
| `--max-tokens` | `500` | 응답의 최대 토큰 수입니다. 1 이상의 정수를 입력합니다. |
| `--safe-mode` | 사용 안 함 | API로 전송하는 diff를 최대 200줄로 제한합니다. |

예시:

```console
uv run output-6-1 status
uv run output-6-1 diff
uv run output-6-1 commit --model gemini --temperature 0.2 --max-tokens 500
uv run output-6-1 pr --model gemini --temperature 0.2 --max-tokens 500 --safe-mode
uv run output-6-1 commit --model opus --max-tokens 500
```

## 변경 내용 수집 범위

상태 명령은 `git status --short`를 사용하고, diff 명령과 생성 명령은 `git diff`를 사용합니다. 따라서 생성 대상은 기본적으로 **스테이징하지 않은 추적 파일의 변경 내용**입니다. 스테이징된 변경이나 미추적 파일만 있는 경우 `git diff`가 비어 있어 초안을 생성하지 않습니다. 초안을 만들려면 대상 변경을 스테이징하지 않은 추적 파일 상태로 두세요.

바이너리 파일은 Git이 `Binary files ... differ` 안내 줄만 diff에 넣으므로 파일 내용 없이 파일이 달라졌다는 정보만 AI에 전달됩니다. 제목 길이는 앞뒤 공백을 제거한 뒤 Python의 `len()`이 세는 문자 수로 계산합니다.

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

커밋 제목은 최대 72자, PR 제목은 최대 80자입니다. 커밋 본문을 포함하면 1~2개의 불릿이어야 합니다. PR 본문에는 `Why`, `What`, `How to Test` 섹션이 순서대로 있어야 하며, 각 섹션에는 하나 이상의 불릿이 필요합니다. 숨겨진 HTML 주석에 필수 섹션을 넣으면 검증에서 거부합니다. 형식 검증에 실패하거나 API가 토큰 한도 때문에 응답을 자르면 한 번 재요청하므로 한 번의 생성 명령은 최대 두 번 API를 호출할 수 있습니다.

제목은 표시 내용이 있는 한 줄을 일반 텍스트로 출력하며, `__init__.py` 같은 파일명과 인라인 기호를 그대로 유지합니다. 코드 펜스·블록 제목·구분선이나 표시 내용이 없는 빈 링크·공백 코드 구간은 제목으로 인정하지 않습니다. 본문은 실제 Markdown 구조로 확인하며, 코드·HTML 블록 안의 가짜 불릿·섹션은 인정하지 않습니다. PR의 실제 불릿 안에 있는 코드 블록은 내용이 있을 때 해당 불릿의 내용으로 인정합니다. 폭이 없는 문자·결합 문자·한글 채움 문자(U+115F, U+1160, U+3164, U+FFA0)·점자 빈 셀(U+2800)만 있는 제목·불릿은 재생성 대상으로 처리하고, 표시 내용과 함께 쓰인 문자는 원문을 보존합니다. 줄바꿈·탭을 제외한 터미널 제어문자가 AI 응답에 있으면 출력하지 않고 재생성합니다. `nan`·무한대 temperature와 0 이하 토큰 수 등 잘못된 옵션 값은 API를 호출하기 전에 옵션명과 오류 조건을 안내하고 종료 코드 `2`로 종료합니다.

## 생성 파라미터와 응답 처리 근거

`temperature`는 다음 토큰을 선택할 때 출력의 다양성을 조절합니다. 값을 높이면 표현이 다양해지는 경향이 있고, 낮추면 상대적으로 일관된 표현을 얻는 데 도움이 됩니다. 효과는 모델과 입력에 따라 다르며, 같은 diff와 옵션으로 실행해도 결과 문장이 완전히 같다고 보장되지는 않습니다. 이 도구는 생성 seed를 고정하지 않으므로, 비교할 때 diff·모델·temperature·max_tokens와 실행 시점을 함께 기록합니다.

`max_tokens`는 모델이 반환할 수 있는 응답 토큰의 상한입니다. 입력 diff의 줄 수나 제목의 글자 수를 제한하는 옵션이 아닙니다. 상한에 도달해 API가 응답을 끝내면 불완전한 초안으로 처리하고 한 번 다시 요청합니다.

출력 규칙을 어긴 응답에는 원래 diff와 실패 이유를 프롬프트에 포함해 한 번 재생성을 요청합니다. 제목을 기계적으로 자르거나 빠진 PR 섹션을 자동으로 만들어 붙이면 문장의 뜻이 바뀌거나 실제 변경·테스트에 없던 내용이 추가될 수 있어 선택하지 않았습니다. 재생성은 의미와 근거를 모델이 다시 맞추도록 하지만 요청 비용과 대기 시간이 늘고, 두 번째 응답도 실패할 수 있습니다. 이를 제한하기 위해 한 명령에서 최대 두 번만 요청하고, 재생성 결과도 규칙을 통과하지 못하면 초안을 성공처럼 출력하지 않습니다. 네트워크·인증 오류는 형식 오류와 다르므로 재생성하지 않습니다.

## 수동 확인

요구사항별 명령과 판정 기준은 [수동 확인 시나리오](docs/수동_확인_시나리오.md), 결과 기록 양식은 [수동 확인 결과 기록 양식](docs/manual_check/결과기록_양식.md)을 참고하세요. 관찰 도구는 합성된 테스트용 응답만 사용하며 실제 API 연동 확인을 대체하지 않습니다.

## 안전하게 사용하기

- diff에는 코드, 설정값 또는 개인정보가 포함될 수 있으므로 API 전송 전에 `diff` 명령으로 내용을 확인하세요.
- `--safe-mode`는 앞에서부터 200줄만 전송합니다. 민감한 값을 찾아 가리지는 않으므로, 제한된 줄 안에 비밀값이 있으면 그대로 전송될 수 있습니다.
- 생성 명령은 stderr에 안전모드의 원문 줄 제한과 실제 API 요청 시도 횟수를 표시합니다. 형식 검증 후 재요청하면 한 명령에서 최대 두 번 호출할 수 있습니다.
- 생성 결과는 검토용 초안입니다. 내용을 확인한 뒤 직접 적용하세요.
- API 호출은 최초 요청과 형식 오류 시의 재시도를 합쳐 명령당 최대 두 번입니다. 사용량이나 비용을 관리하려면 변경 내용을 확인한 뒤 필요한 생성 명령만 실행하세요.
- HTTPS 인증서는 운영체제의 신뢰 저장소로 검증합니다. API 키를 코드나 저장소에 올리지 마세요. API 오류는 HTTP 상태에 따른 안내와 서버가 제공한 원인을 표시하며, 응답 메시지에서 API 키와 일치하는 문자열은 가립니다. 오류 원인의 터미널 제어문자는 실행되지 않는 문자 표기로 표시합니다. API 인증·네트워크 오류가 발생하면 설정과 연결 상태를 확인하세요.

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
│   ├── 수동_확인_시나리오.md
│   ├── manual_check/
│   │   ├── 결과기록_양식.md
│   │   └── observe_cli.py
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
