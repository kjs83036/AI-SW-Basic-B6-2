import os
from typing import Literal

import requests
from dotenv import load_dotenv

# 구현 예정: diff를 반영하고 제목·본문 작성 규칙을 안내하는 프롬프트를 작성합니다.
COMMIT_PROMPT: str = ""
# 구현 예정: Why, What, How to Test 섹션과 각 섹션의 불릿 규칙을 포함합니다.
PR_PROMPT: str = ""


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
    response = ai_call_api(diff_after_prompt, model, temperature, max_tokens)
    return ai_validate(response, "commit")


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
    response = ai_call_api(diff_after_prompt, model, temperature, max_tokens)
    return ai_validate(response, "pr")


def ai_prompt(diff: str, output_type: Literal["commit", "pr"]) -> str:
    """출력 종류에 맞는 프롬프트를 선택합니다."""
    # 구현 예정: 선택한 프롬프트에 diff와 출력 형식 지침을 함께 구성합니다.
    if output_type == "pr":
        prompt = PR_PROMPT + diff

    if output_type == "commit":
        prompt = COMMIT_PROMPT + diff

    return prompt


def ai_validate(
    response: str | None,
    output_type: Literal["commit", "pr"],
) -> str | None:
    """생성 결과를 과제의 길이와 형식 기준에 맞게 확인합니다."""
    # 요구문서에 맞게
    # 구현 예정: 커밋 제목은 최대 72자, PR 제목은 최대 80자로 확인합니다.
    # 구현 예정: PR 본문에 세 필수 섹션과 섹션별 불릿이 있는지 확인합니다.
    # 구현 예정: 규칙 위반 시 재생성 또는 후처리하는 방식을 선택합니다.
    return


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
            timeout=10  # 요청 시간 제한을 10초로 설정
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
        raise RuntimeError("API 서버에 연결할 수 없습니다. 네트워크와 서버 주소를 확인하세요.") from error

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
