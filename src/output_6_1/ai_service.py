from html import unescape
import os
import re
import sys
from typing import Literal

import truststore

truststore.inject_into_ssl()

import requests
from dotenv import load_dotenv
from markdown_it import MarkdownIt
from markdown_it.token import Token

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


class IncompleteResponseError(RuntimeError):
    """API가 토큰 한도에 도달해 생성을 끝낸 응답을 나타냅니다."""


def ai_commit(
    diff: str,
    model: str | None,
    temperature: float,
    max_tokens: int,
    safe_mode: bool = False,
) -> str:
    """Git diff로 커밋 메시지 초안을 생성하고 형식을 확인합니다."""
    diff = _prepare_diff(diff, safe_mode)
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
) -> str:
    """Git diff로 PR 초안을 생성하고 형식을 확인합니다."""
    diff = _prepare_diff(diff, safe_mode)
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
    call_count = 1
    try:
        response = ai_call_api(
            prompt, model, temperature, max_tokens, request_number=call_count
        )
    except IncompleteResponseError as error:
        response = None
        validation_error = error
    else:
        try:
            return ai_validate(response, output_type)
        except ValueError as error:
            validation_error = error

    retry_context = (
        f"앞선 출력:\n{response}\n\n" if response is not None else ""
    )
    retry_reason = (
        "API 응답이 토큰 한도에 도달해 일부만 생성되었습니다."
        if response is None
        else "앞선 출력의 형식 검증이 실패했습니다."
    )
    retry_prompt = (
        f"{prompt}\n\n"
        f"{retry_reason}\n"
        f"실패 사유: {validation_error}\n\n"
        f"{retry_context}"
        "실패 사유를 수정해 초안 전체를 다시 작성하세요. "
        "diff에 없는 사실은 추가하지 말고, 수정된 결과만 출력하세요."
    )

    call_count += 1
    try:
        retry_response = ai_call_api(
            retry_prompt,
            model,
            temperature,
            max_tokens,
            request_number=call_count,
        )
    except IncompleteResponseError:
        raise RuntimeError("AI API 재생성 응답도 토큰 한도에 도달했습니다.") from None
    return ai_validate(retry_response, output_type)


def ai_prompt(diff: str, output_type: Literal["commit", "pr"]) -> str:
    """출력 종류에 맞는 프롬프트를 선택합니다."""
    if output_type == "pr":
        prompt = PR_PROMPT + diff

    if output_type == "commit":
        prompt = COMMIT_PROMPT + diff

    return prompt


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

    title_tokens = MarkdownIt("commonmark").parse(title)
    title_inline_tokens = [token for token in title_tokens if token.type == "inline"]
    if (
        len(title_inline_tokens) != 1
        or any(
            token.type not in {"paragraph_open", "inline", "paragraph_close"}
            for token in title_tokens
        )
        or any(child.type != "text" for child in title_inline_tokens[0].children or [])
        or not any(
            unescape(child.content).strip()
            for child in title_inline_tokens[0].children or []
        )
    ):
        raise ValueError("제목은 내용이 있는 서식 없는 한 줄이어야 합니다.")

    if len(lines) > 1 and lines[1].strip():
        raise ValueError("제목과 본문 사이에 빈 줄이 필요합니다.")

    body_lines = lines[2:]
    while body_lines and not body_lines[0].strip():
        body_lines.pop(0)
    while body_lines and not body_lines[-1].strip():
        body_lines.pop()
    body = "\n".join(body_lines)
    structural_lines, list_items_with_content = _markdown_structure(body.splitlines())
    title_limit = 72 if output_type == "commit" else 80

    if len(title) > title_limit:
        raise ValueError(f"제목은 {title_limit}자 이하여야 합니다.")

    if output_type == "commit":
        if body:
            body_lines = [line for line in body.splitlines() if line.strip()]
            if not 1 <= len(body_lines) <= 2:
                raise ValueError("커밋 본문은 1~2개의 불릿으로 작성해야 합니다.")
            if any(
                structural_lines[index] is None
                or index not in list_items_with_content
                or not line.startswith("- ")
                or not line[2:].strip()
                for index, line in enumerate(body.splitlines())
                if line.strip()
            ):
                raise ValueError("커밋 본문은 내용 있는 불릿으로만 작성해야 합니다.")

        result = f"-- Commit Message --\n{title}"
        if body:
            result += f"\n\n{body}"
        return result

    if output_type == "pr":
        if not body:
            raise ValueError("PR 본문이 비어 있습니다.")
        if "<!--" in body or "-->" in body:
            raise ValueError("PR 본문에 숨겨진 HTML 주석을 포함할 수 없습니다.")

        body_lines = body.splitlines()
        sections = ["## Why", "## What", "## How to Test"]
        positions = []

        for section in sections:
            section_pattern = re.compile(
                rf"{re.escape(section)}(?:\s*\([^()\r\n]+\))?"
            )
            matches = [
                index
                for index, line in enumerate(structural_lines)
                if line is not None and section_pattern.fullmatch(line.strip())
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
            following_headings = [
                line_number
                for line_number in range(position + 1, end)
                if structural_lines[line_number] is not None
                and (
                    heading := re.match(
                        r"^(#{1,6})(?:\s|$)", structural_lines[line_number]
                    )
                )
                and len(heading.group(1)) <= 2
            ]
            if following_headings:
                end = following_headings[0]
            section_lines = body_lines[position + 1 : end]
            bullets = [
                line
                for index, line in enumerate(section_lines, start=position + 1)
                if structural_lines[index] is not None
                if index in list_items_with_content
                if re.match(r"^\s*-\s+\S", line)
            ]
            if not bullets:
                raise ValueError(f"'{sections[index]}' 섹션에 불릿이 필요합니다.")

        return f"-- PR Title --\n{title}\n\n-- PR Body --\n{body}"

    raise ValueError("지원하지 않는 출력 종류입니다.")


def _markdown_structure(lines: list[str]) -> tuple[list[str | None], set[int]]:
    """실제 Markdown 제목과 내용이 있는 목록 항목의 줄 번호를 찾습니다."""
    structural_lines: list[str | None] = [None] * len(lines)
    list_items_with_content: set[int] = set()
    tokens = MarkdownIt("commonmark").parse("\n".join(lines))
    list_item_stack: list[int] = []
    for index, token in enumerate(tokens):
        is_heading = token.type == "heading_open" and token.level == 0
        if is_heading and token.map:
            line_number = token.map[0]
            structural_lines[line_number] = (
                f"{'#' * int(token.tag[1:])} {tokens[index + 1].content}"
            )
        elif token.type == "list_item_open" and token.map:
            line_number = token.map[0]
            list_item_stack.append(line_number)
            structural_lines[line_number] = lines[line_number]
        elif token.type == "inline" and _inline_token_has_content(token):
            list_items_with_content.update(list_item_stack)
        elif token.type == "list_item_close" and list_item_stack:
            list_item_stack.pop()
    return structural_lines, list_items_with_content


def _inline_token_has_content(token: Token) -> bool:
    """화면에 표시되는 텍스트나 대체 텍스트가 있는지 확인합니다."""
    return any(
        child.type in {"text", "code_inline", "image"}
        and unescape(child.content).strip()
        for child in token.children or []
    )


def ai_call_api(
    diff_after_prompt: str,
    model: str | None,
    temperature: float,
    max_tokens: int,
    request_number: int = 1,
) -> str:
    """환경변수의 키와 생성 설정을 사용해 AI API를 호출합니다."""
    # 환경변수에서 가져온 API 키를 요청 인증 정보로 사용합니다.

    if not model or model == "gemini":
        model = "gemini-3.1-flash-lite"

    if model == "opus":
        model = "claude-opus-4-8"

    load_dotenv()
    api_key = os.getenv("API_KEY")

    if not api_key:

        raise ValueError("API_KEY is not set in the environment variables.")

    try:
        print(f"[INFO] AI API 요청: {request_number}회", file=sys.stderr)
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

        if error.response is not None:
            try:
                payload = error.response.json()
            except ValueError:
                payload = None
            api_error = payload.get("error") if isinstance(payload, dict) else None
            detail = api_error.get("message") if isinstance(api_error, dict) else None
            if not isinstance(detail, str) and isinstance(payload, dict):
                detail = payload.get("message")
            if isinstance(detail, str) and detail.strip():
                detail = " ".join(detail.split())
                if api_key in detail:
                    detail = detail.replace(api_key, "[REDACTED]")
                detail = detail[:200]
                message += f" 원인: {detail}"

        raise RuntimeError(message) from None

    except requests.exceptions.Timeout as error:
        raise RuntimeError("API 요청 시간이 초과되었습니다.") from error

    except requests.exceptions.SSLError as error:
        raise RuntimeError(
            "API TLS 인증서 검증에 실패했습니다. 운영체제의 인증서 저장소를 확인하세요."
        ) from error

    except requests.exceptions.ConnectionError as error:
        raise RuntimeError(
            "API 서버에 연결할 수 없습니다. 네트워크와 서버 주소를 확인하세요."
        ) from error

    except requests.RequestException as error:
        raise RuntimeError("API 요청 처리 중 오류가 발생했습니다.") from error

    try:
        choice = response.json()["choices"][0]
        if isinstance(choice, dict) and choice.get("finish_reason") in (
            "length",
            "max_tokens",
        ):
            raise IncompleteResponseError(
                "AI API 응답이 토큰 한도에 도달해 일부만 생성되었습니다."
            )
        content = choice["message"]["content"]
    except IncompleteResponseError:
        raise
    except (IndexError, KeyError, TypeError, ValueError):
        raise RuntimeError("AI API 응답 형식이 올바르지 않습니다.") from None

    if not isinstance(content, str):
        raise RuntimeError("AI API 응답 형식이 올바르지 않습니다.")

    return content


def limit_diff(diff: str) -> str:
    """안전모드에서 API에 전달할 diff의 크기를 제한합니다."""
    # 200줄을 넘으면 앞부분만 남겨 전송량을 제한합니다.
    lines = diff.splitlines()
    if len(lines) <= 200:
        return diff

    return "\n".join(lines[:200]) + "\n\n[Diff truncated: limited to 200 lines.]"


def _prepare_diff(diff: str, safe_mode: bool) -> str:
    """안전모드 적용 여부를 알리고 API에 전달할 diff를 준비합니다."""
    if not safe_mode:
        return diff

    source_line_count = len(diff.splitlines())
    limited_diff = limit_diff(diff)
    print(
        f"[INFO] 안전모드: 원본 {source_line_count}줄, "
        f"전송하는 원문 최대 {min(source_line_count, 200)}줄",
        file=sys.stderr,
    )
    return limited_diff
