import os
import re
import sys
from importlib import import_module
from typing import Any, Literal
from unicodedata import category

import truststore

truststore.inject_into_ssl()

import requests
from dotenv import load_dotenv

MarkdownIt = import_module("markdown_it").MarkdownIt

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
- 제목과 본문 외의 설명이나 머리말을 쓰거나 응답 전체를 코드 펜스로 감싸지 마세요. 테스트 불릿 안의 코드 블록은 허용합니다.

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
    """응답 형식을 검증하고 형식 오류가 있으면 한 번 재생성합니다.

    잘못된 형식과 토큰 한도에 걸린 응답만 재시도합니다. 네트워크·인증 등
    API 호출 자체의 실패는 별도 요청으로 반복하지 않고 호출자에게 전달합니다.
    토큰이 잘린 응답은 불완전한 내용을 재작성 참고문에 넣지 않습니다.
    """
    call_count = 1
    try:
        response = ai_call_api(
            prompt, model, temperature, max_tokens, request_number=call_count
        )
    except IncompleteResponseError as error:
        # 잘린 본문은 참고 가치가 없으므로 재시도 사유만 보존합니다.
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

    # 재시도는 루프 없이 한 번만 실행해 API 요청 횟수를 최대 두 번으로 제한합니다.
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
    """생성 결과의 제목과 본문이 커밋 또는 PR 형식에 맞는지 확인합니다.

    Markdown 파서가 인식한 제목·목록만 구조로 취급해 코드 블록 안의 문구가
    실제 섹션이나 불릿으로 오인되지 않게 합니다. 두 출력 형식의 제목 길이와
    본문 규칙을 각각 확인한 뒤 화면에 표시할 결과에 종류별 머리말을 붙입니다.
    """
    if not isinstance(response, str) or not response.strip():
        raise ValueError("AI 생성 결과가 비어 있습니다.")

    if any(
        category(character) == "Cc" and character not in "\n\r\t"
        for character in response
    ):
        raise ValueError("AI 생성 결과에 터미널 제어문자가 포함되어 있습니다.")

    lines = response.strip().splitlines()
    title = lines[0].strip()

    if not title:
        raise ValueError("제목이 비어 있습니다.")

    # Markdown 표기를 걷어낸 뒤에도 제목에 실제로 보이는 내용이 있는지 확인합니다.
    title_tokens = MarkdownIt("commonmark").parse(title)
    title_inline_tokens = [token for token in title_tokens if token.type == "inline"]
    if (
        len(title_inline_tokens) != 1
        or any(
            token.type not in {"paragraph_open", "inline", "paragraph_close"}
            for token in title_tokens
        )
        or not _inline_token_has_content(title_inline_tokens[0])
    ):
        raise ValueError("제목은 내용이 있는 한 줄이어야 합니다.")

    if len(lines) > 1 and lines[1].strip():
        raise ValueError("제목과 본문 사이에 빈 줄이 필요합니다.")

    # 제목 다음의 빈 줄은 형식으로 소비하고, 본문의 바깥쪽 공백 줄만 정리합니다.
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
        # 빈 본문은 허용하되, 본문이 있으면 실제 내용이 든 불릿만 받습니다.
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
        if _contains_html_comment(body):
            raise ValueError("PR 본문에 숨겨진 HTML 주석을 포함할 수 없습니다.")

        # 코드 펜스 밖에 있는 필수 제목만 찾고, 섹션마다 독립적으로 불릿을 확인합니다.
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
            # 임의의 상위 제목에서 섹션을 끊어 다음 섹션의 불릿을 빌리지 않게 합니다.
            following_headings = [
                line_number
                for line_number in range(position + 1, end)
                if (structural_line := structural_lines[line_number]) is not None
                and (
                    heading := re.match(
                        r"^(#{1,6})(?:\s|$)", structural_line
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
                if re.match(r"^\s*-(?:\s|$)", line)
            ]
            if not bullets:
                raise ValueError(f"'{sections[index]}' 섹션에 불릿이 필요합니다.")

        return f"-- PR Title --\n{title}\n\n-- PR Body --\n{body}"

    raise ValueError("지원하지 않는 출력 종류입니다.")


def _markdown_structure(lines: list[str]) -> tuple[list[str | None], set[int]]:
    """Markdown 토큰을 원문 줄에 대응시키고 내용 있는 목록을 찾습니다.

    줄별 구조 표시는 일반 문장이나 코드 블록의 문구를 제목·목록으로 오인하지
    않도록 파서가 인식한 토큰만 채웁니다. 중첩 목록 스택으로 내부의 실제 문구나
    코드가 어느 목록 항목에 속하는지도 함께 기록합니다.
    """
    structural_lines: list[str | None] = [None] * len(lines)
    list_items_with_content: set[int] = set()
    tokens = MarkdownIt("commonmark").parse("\n".join(lines))
    list_item_stack: list[int] = []
    for index, token in enumerate(tokens):
        is_heading = token.type == "heading_open" and token.level == 0
        if is_heading and token.map:
            # 파서의 제목 토큰을 검증기가 쓰는 일관된 Markdown 제목 형태로 바꿉니다.
            line_number = token.map[0]
            structural_lines[line_number] = (
                f"{'#' * int(token.tag[1:])} {tokens[index + 1].content}"
            )
        elif token.type == "list_item_open" and token.map:
            # 내부 목록도 유지할 수 있도록 열릴 때 쌓고 닫힐 때 하나씩 제거합니다.
            line_number = token.map[0]
            list_item_stack.append(line_number)
            structural_lines[line_number] = lines[line_number]
        elif token.type == "inline" and _inline_token_has_content(token):
            list_items_with_content.update(list_item_stack)
        elif token.type in {"fence", "code_block"} and _has_visible_content(token.content):
            list_items_with_content.update(list_item_stack)
        elif token.type == "list_item_close" and list_item_stack:
            list_item_stack.pop()
    return structural_lines, list_items_with_content


def _contains_html_comment(text: str) -> bool:
    """Markdown에서 HTML 주석으로 해석되는 토큰이 있는지 확인합니다."""
    tokens = MarkdownIt("commonmark", {"html": True}).parse(text)
    return any(
        token.type == "html_block" and "<!--" in token.content
        or token.type == "inline"
        and any(
            child.type == "html_inline" and "<!--" in child.content
            for child in token.children or []
        )
        for token in tokens
    )


def _inline_token_has_content(token: Any) -> bool:
    """인라인 토큰 트리에서 화면에 보일 문자나 이미지 대체 문구를 찾습니다.

    이미지 안의 텍스트는 대체 문구를 확인하도록 재귀적으로 살피고, 강조나
    링크 같은 장식 토큰 자체는 내용으로 세지 않습니다.
    """
    return any(
        _inline_token_has_content(child)
        if child.type == "image"
        else child.type in {"text", "text_special", "code_inline"}
        and _has_visible_content(child.content)
        for child in token.children or []
    )


def _has_visible_content(text: str) -> bool:
    """공백이나 유니코드 서식 문자만 있는 문자열을 내용으로 세지 않습니다.

    화면에서 독립된 글자로 읽히지 않는 제어·서식·결합 문자와 대표적인 빈
    유니코드 문자를 제외해, 눈에 보이지 않는 텍스트로 제목이나 불릿을 채우지
    못하게 합니다.
    """
    return any(
        not character.isspace()
        and category(character) not in {"Cc", "Cf", "Cs", "Mn", "Me"}
        and character not in "\u115f\u1160\u2800\u3164\uffa0"
        for character in text
    )


def ai_call_api(
    diff_after_prompt: str,
    model: str | None,
    temperature: float,
    max_tokens: int,
    request_number: int = 1,
) -> str:
    """모델 별칭과 옵션을 적용해 API를 호출하고 응답을 안전하게 해석합니다.

    Opus 모델에는 지원되지 않는 temperature를 보내지 않습니다. HTTP 상태,
    네트워크·TLS 오류와 응답 형식 오류를 사용자에게 구분해 안내하며, 서버가
    돌려준 상세 사유는 키를 가리고 제어 문자를 표시 가능한 형태로 정리합니다.
    """

    # 짧은 별칭만 정식 모델명으로 치환하고 다른 사용자 지정 모델은 보존합니다.
    if not model or model == "gemini":
        model = "gemini-3.1-flash-lite"

    if model == "opus":
        model = "claude-opus-4-8"

    load_dotenv()
    api_key = os.getenv("API_KEY")

    if not api_key:

        raise ValueError("API_KEY is not set in the environment variables.")

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": diff_after_prompt}],
        "max_tokens": max_tokens,
    }
    if not model.startswith("claude-opus-"):
        payload["temperature"] = temperature

    # 요청 단계의 원인을 구분해 인증 정보나 원시 응답을 오류 메시지에 노출하지 않습니다.
    try:
        print(f"[INFO] AI API 요청: {request_number}회", file=sys.stderr)
        response = requests.post(
            "https://copa.codyssey.kr/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=10,
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
                # 응답을 한 줄로 만들고 키를 가린 뒤 제어 문자를 이스케이프해 길이를 제한합니다.
                detail = " ".join(detail.split())
                if api_key in detail:
                    detail = detail.replace(api_key, "[REDACTED]")
                detail = "".join(
                    f"\\x{ord(character):02x}"
                    if category(character) == "Cc"
                    else character
                    for character in detail
                )
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

    # HTTP 요청이 성공해도 응답 JSON 구조와 생성 종료 사유를 별도로 검사합니다.
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
    """안전모드용으로 diff의 원문을 최대 200줄까지 남깁니다.

    이미 제한 안에 있으면 입력을 그대로 돌려주고, 초과한 경우에는 앞부분과
    잘렸음을 알리는 표식을 붙여 API가 일부 변경 내용만 받았음을 알립니다.
    """
    lines = diff.splitlines()
    if len(lines) <= 200:
        return diff

    return "\n".join(lines[:200]) + "\n\n[Diff truncated: limited to 200 lines.]"


def _prepare_diff(diff: str, safe_mode: bool) -> str:
    """안전모드에 맞춰 diff를 그대로 두거나 줄 수를 제한합니다.

    제한이 켜졌을 때만 원본 줄 수와 보낼 원문 줄 수를 stderr에 알려 사용자가
    전송 범위를 확인할 수 있게 합니다.
    """
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
