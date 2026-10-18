import os
from typing import Literal

import requests
from dotenv import load_dotenv

# 구현 예정: diff를 반영하고 제목·본문 작성 규칙을 안내하는 프롬프트를 작성합니다.
# 구현 예정: Why, What, How to Test 섹션과 각 섹션의 불릿 규칙을 포함합니다.

COMMIT_PROMPT = """다음 Git diff를 바탕으로 한국어 커밋 메시지를 작성하세요.

출력 형식:
커밋 제목 한 줄

- 핵심 변경 사항 1
- 핵심 변경 사항 2

규칙:
- 제목은 한 줄이며 최대 72자입니다. 가능하면 50자 이내로 작성하세요.
- 본문은 선택 사항입니다. 본문이 필요 없으면 제목만 출력하세요.
- 본문을 출력한다면 핵심 변경 사항을 1~2개의 "- " 불릿으로만 작성하세요.
- diff에 드러난 사실만 쓰고 변경 내용이나 테스트 결과를 지어내지 마세요.
- 출력 형식 예시의 안내 문구나 대괄호를 그대로 복사하지 마세요.
- 제목과 본문 외의 설명, 머리말, 코드 펜스는 출력하지 마세요.

변경 내용(diff):
"""

PR_PROMPT = """다음 Git diff를 바탕으로 한국어 Pull Request 제목과 본문 초안을 작성하세요.

출력 형식:
PR 제목 한 줄

## Why (변경 배경)
- 변경 이유

## What (핵심 변경 사항)
- 변경 내용

## How to Test (테스트 방법)
- 테스트 방법 또는 확인 상태

규칙:
- 제목은 한 줄이며 최대 80자입니다.
- 본문에는 Why, What, How to Test 세 섹션을 모두 포함하세요.
- 각 섹션에는 최소 한 개의 "- " 불릿을 작성하세요.
- 섹션 제목은 위의 영어 이름을 유지하고, 괄호 안에 한국어 설명을 덧붙일 수 있습니다.
- diff에서 확인할 수 없는 테스트를 이미 실행한 것처럼 쓰지 마세요. 실행 여부를 알 수 없으면 미실행이라고 쓰거나 확인할 테스트를 제안하세요.
- diff에 드러난 사실만 쓰고 내용을 지어내지 마세요.
- 제목과 본문 외의 설명, 머리말, 코드 펜스는 출력하지 마세요.

변경 내용(diff):
"""


def ai_commit(
    diff: str,
    model: str | None,
    temperature: float,
    max_tokens: int,
    safe_mode: bool = False,
) -> str | None:
    """Git diff로 커밋 메시지 초안을 생성하고 형식을 확인합니다."""
    if safe_mode:
        diff = limit_diff(diff)
    diff_after_prompt = ai_prompt(diff, "commit")
    return ai_generate_validated(
        diff_after_prompt, "commit", model, temperature, max_tokens
    )


def ai_pr(
    diff: str,
    model: str | None,
    temperature: float,
    max_tokens: int,
    safe_mode: bool = False,
) -> str | None:
    """Git diff로 PR 초안을 생성하고 형식을 확인합니다."""
    if safe_mode:
        diff = limit_diff(diff)
    diff_after_prompt = ai_prompt(diff, "pr")
    return ai_generate_validated(
        diff_after_prompt, "pr", model, temperature, max_tokens
    )


def ai_generate_validated(
    prompt: str,
    output_type: Literal["commit", "pr"],
    model: str | None,
    temperature: float,
    max_tokens: int,
) -> str:
    """생성 결과를 검증하고 형식 오류가 있으면 한 번 재생성합니다."""
    response = ai_call_api(prompt, model, temperature, max_tokens)

    try:
        return ai_validate(response, output_type)
    except ValueError as error:
        retry_prompt = (
            f"{prompt}\n\n"
            "앞선 출력이 형식 검증에서 실패했습니다.\n"
            f"실패 사유: {error}\n\n"
            f"앞선 출력:\n{response}\n\n"
            "실패 사유를 수정해 초안 전체를 다시 작성하세요. "
            "diff에 없는 사실은 추가하지 말고, 수정된 결과만 출력하세요."
        )

        retry_response = ai_call_api(
            retry_prompt,
            model,
            temperature,
            max_tokens,
        )
        return ai_validate(retry_response, output_type)


def ai_prompt(diff: str, output_type: Literal["commit", "pr"]) -> str:
    """출력 종류에 맞는 프롬프트를 선택합니다."""
    # 구현 예정: 선택한 프롬프트에 diff와 출력 형식 지침을 함께 구성합니다.
    if output_type == "pr":
        prompt = PR_PROMPT + diff

    if output_type == "commit":
        prompt = COMMIT_PROMPT + diff

    return prompt


# 구현 예정: 커밋 제목은 최대 72자, PR 제목은 최대 80자로 확인합니다.
# 구현 예정: PR 본문에 세 필수 섹션과 섹션별 불릿이 있는지 확인합니다.
# 구현 예정: 규칙 위반 시 재생성 또는 후처리하는 방식을 선택합니다.
def ai_validate(
    response: str | None,
    output_type: Literal["commit", "pr"],
) -> str:
    """생성 결과의 제목과 본문이 요구 형식에 맞는지 확인합니다."""
    if not isinstance(response, str) or not response.strip():
        raise ValueError("AI 생성 결과가 비어 있습니다.")

    lines = response.strip().splitlines()
    title = lines[0].strip()

    if not title:
        raise ValueError("제목이 비어 있습니다.")

    if len(lines) > 1 and lines[1].strip():
        raise ValueError("제목과 본문 사이에 빈 줄이 필요합니다.")

    body = "\n".join(lines[2:]).strip() if len(lines) > 1 else ""
    title_limit = 72 if output_type == "commit" else 80

    if len(title) > title_limit:
        raise ValueError(f"제목은 {title_limit}자 이하여야 합니다.")

    if output_type == "commit":
        if body:
            body_lines = [line for line in body.splitlines() if line.strip()]
            if not 1 <= len(body_lines) <= 2:
                raise ValueError("커밋 본문은 1~2개의 불릿으로 작성해야 합니다.")
            if any(not line.lstrip().startswith("- ") for line in body_lines):
                raise ValueError("커밋 본문은 불릿으로만 작성해야 합니다.")

        result = f"-- Commit Message --\n{title}"
        if body:
            result += f"\n\n{body}"
        return result

    if output_type == "pr":
        if not body:
            raise ValueError("PR 본문이 비어 있습니다.")

        body_lines = body.splitlines()
        sections = ["## Why", "## What", "## How to Test"]
        positions = []

        for section in sections:
            matches = [
                index
                for index, line in enumerate(body_lines)
                if line.strip() == section or line.strip().startswith(section + " ")
            ]
            if len(matches) != 1:
                raise ValueError(
                    f"PR 본문에 '{section}' 섹션이 정확히 하나 있어야 합니다."
                )
            positions.append(matches[0])

        if positions != sorted(positions):
            raise ValueError("PR 섹션은 Why, What, How to Test 순서여야 합니다.")

        for index, position in enumerate(positions):
            end = (
                positions[index + 1] if index + 1 < len(positions) else len(body_lines)
            )
            section_lines = body_lines[position + 1 : end]
            if not any(line.lstrip().startswith("- ") for line in section_lines):
                raise ValueError(f"'{sections[index]}' 섹션에 불릿이 필요합니다.")

        return f"-- PR Title --\n{title}\n\n-- PR Body --\n{body}"

    raise ValueError("지원하지 않는 출력 종류입니다.")


def ai_call_api(
    diff_after_prompt: str,
    model: str | None,
    temperature: float,
    max_tokens: int,
) -> str | None:
    """환경변수의 키와 생성 설정을 사용해 AI API를 호출합니다."""
    # .env 파일에서 읽은 API 키를 요청 인증 정보로 사용합니다.
    # 구현 예정: API_KEY 누락을 호출 전에 확인하고 키 값은 오류 메시지에 노출하지 않습니다.
    # 구현 예정: HTTP 상태 코드와 네트워크·인증 오류를 확인해 원인을 안내합니다.
    # 구현 예정: 요청 시간 제한을 설정하고 응답에 예상한 생성 결과가 있는지 확인합니다.

    if not model or model == "gemini":
        model = "gemini-3.1-flash-lite"

    if model == "opus":
        model = "claude-opus-4-8"

    load_dotenv()
    api_key = os.getenv("API_KEY")

    if not api_key:

        raise ValueError("API_KEY is not set in the environment variables.")

    try:
        response = requests.post(
            "https://copa.codyssey.kr/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": diff_after_prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=10,  # 요청 시간 제한을 10초로 설정
        )
        response.raise_for_status()
    except requests.exceptions.HTTPError as error:
        status_code = error.response.status_code if error.response is not None else None

        if status_code in (401, 403):
            message = "API 인증 또는 접근 권한을 확인하세요."
        elif status_code == 429:
            message = "API 요청 한도를 초과했습니다."
        elif status_code is not None and status_code >= 500:
            message = "API 서버에서 오류가 발생했습니다."
        else:
            message = f"API 요청이 실패했습니다. 상태 코드: {status_code}"

        raise RuntimeError(message) from None

    except requests.exceptions.Timeout as error:
        raise RuntimeError("API 요청 시간이 초과되었습니다.") from error

    except requests.exceptions.ConnectionError as error:
        raise RuntimeError(
            "API 서버에 연결할 수 없습니다. 네트워크와 서버 주소를 확인하세요."
        ) from error

    except requests.RequestException as error:
        raise RuntimeError("API 요청 처리 중 오류가 발생했습니다.") from error

    return response.json()["choices"][0]["message"]["content"]


def limit_diff(diff: str) -> str:
    """안전모드에서 API에 전달할 diff의 크기를 제한합니다."""
    # 최대 200줄 제한
    lines = diff.splitlines()
    if len(lines) <= 200:
        return diff

    return "\n".join(lines[:200]) + "\n\n[Diff truncated: limited to 200 lines.]"
