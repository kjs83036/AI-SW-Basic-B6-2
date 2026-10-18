import os
from unittest.mock import Mock

import pytest
import requests

from output_6_1 import ai_service


def pr_response(title: str = "PR 초안") -> str:
    """검증 가능한 PR 초안 예시를 반환합니다."""
    return (
        f"{title}\n\n"
        "## Why\n- 변경 배경\n\n"
        "## What\n- 핵심 변경 사항\n\n"
        "## How to Test\n- 자동 테스트를 실행합니다."
    )


@pytest.mark.parametrize(
    ("output_type", "length", "expected"),
    [
        ("commit", 50, True),
        ("commit", 51, True),
        ("commit", 71, True),
        ("commit", 72, True),
        ("commit", 73, False),
        ("pr", 79, True),
        ("pr", 80, True),
        ("pr", 81, False),
    ],
)
def test_title_length_boundaries(
    output_type: str, length: int, expected: bool
) -> None:
    """요구서의 권장 길이와 최대 제목 길이를 구분해 검증합니다."""
    response = "가" * length
    if output_type == "pr":
        response += pr_response()[len("PR 초안") :]

    if expected:
        assert ai_service.ai_validate(response, output_type)
    else:
        with pytest.raises(ValueError, match="자 이하"):
            ai_service.ai_validate(response, output_type)


def test_commit_title_only_is_valid() -> None:
    """커밋 제목만 있는 출력은 유효합니다."""
    assert ai_service.ai_validate("수정된 내용을 반영합니다", "commit")


@pytest.mark.parametrize("separator", ["- - -", "- ---", "- \t- \t-"])
def test_commit_rejects_thematic_break_as_body(separator: str) -> None:
    """커밋 본문에서도 내용 없는 구분선을 변경 요약으로 인정하지 않습니다."""
    with pytest.raises(ValueError, match="불릿으로만"):
        ai_service.ai_validate(f"커밋 제목\n\n{separator}", "commit")


def test_commit_body_requires_one_or_two_bullets() -> None:
    """커밋 본문이 있다면 한 개 또는 두 개의 내용 있는 불릿을 요구합니다."""
    assert ai_service.ai_validate("수정\n\n- 변경 사항", "commit")
    assert ai_service.ai_validate("수정\n\n- 변경 1\n- 변경 2", "commit")

    with pytest.raises(ValueError, match="1~2개의 불릿"):
        ai_service.ai_validate("수정\n\n- 1\n- 2\n- 3", "commit")

    with pytest.raises(ValueError, match="내용 있는 불릿"):
        ai_service.ai_validate("수정\n\n- \n- 실제 변경", "commit")


def test_pr_accepts_required_bilingual_headings() -> None:
    """영문 헤더와 요구서에 기재된 한글 병기 형식을 모두 허용합니다."""
    response = pr_response().replace(
        "## Why", "## Why(변경 배경)"
    ).replace("## What", "## What (핵심 변경 사항)").replace(
        "## How to Test", "## How to Test(테스트 방법)"
    )

    assert ai_service.ai_validate(response, "pr")


@pytest.mark.parametrize("separator", ["- - -", "- ---", "- \t- \t-"])
def test_pr_rejects_thematic_breaks_as_required_bullets(separator: str) -> None:
    """구분선은 필수 섹션의 불릿을 대신할 수 없습니다."""
    response = pr_response().replace("- 변경 배경", separator)
    with pytest.raises(ValueError, match="Why.*불릿"):
        ai_service.ai_validate(response, "pr")


@pytest.mark.parametrize("tag", ["span", "x-pr", 'span data-note="a>b"'])
def test_pr_rejects_sections_inside_general_html_blocks(tag: str) -> None:
    """일반 태그의 HTML 블록 내부 문자열도 실제 섹션으로 세지 않습니다."""
    response = (
        f"PR 초안\n\n<{tag}>\n"
        "## Why\n- 배경\n## What\n- 변경\n## How to Test\n- 미실행\n"
        f"</{tag.split()[0]}>"
    )
    with pytest.raises(ValueError, match="Why.*섹션"):
        ai_service.ai_validate(response, "pr")


def test_pr_accepts_real_sections_after_html_block_ends() -> None:
    """HTML 블록이 빈 줄에서 끝난 뒤의 실제 Markdown 섹션은 허용합니다."""
    response = pr_response().replace("\n\n## Why", "\n\n<span>설명</span>\n\n## Why")
    assert ai_service.ai_validate(response, "pr")


@pytest.mark.parametrize(
    "invalid_response",
    [
        pr_response().replace("- 변경 배경", "- - -"),
        "PR 초안\n\n<span>\n## Why\n- 배경\n## What\n- 변경\n## How to Test\n- 미실행\n</span>",
    ],
)
def test_pr_regenerates_invalid_markdown_once(
    invalid_response: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """불릿·섹션이 없는 응답을 그대로 출력하지 않고 한 번 재생성합니다."""
    api_call = Mock(side_effect=[invalid_response, pr_response()])
    monkeypatch.setattr(ai_service, "ai_call_api", api_call)
    result = ai_service.ai_pr("+ 변경", None, 0.2, 500)
    assert result.endswith(pr_response().split("\n\n", 1)[1])
    assert api_call.call_count == 2


def test_pr_accepts_bullets_under_nested_headings() -> None:
    """필수 섹션 아래의 하위 제목과 불릿을 허용합니다."""
    response = pr_response().replace(
        "## Why\n- 변경 배경", "## Why\n### 배경 설명\n- 변경 배경"
    )

    assert ai_service.ai_validate(response, "pr")


@pytest.mark.parametrize("underline", ["---", "==="])
def test_pr_does_not_borrow_bullets_after_setext_section(underline: str) -> None:
    """다른 H1·H2 제목 뒤의 불릿은 비어 있는 필수 섹션에 귀속하지 않습니다."""
    response = pr_response().replace(
        "## Why\n- 변경 배경", f"## Why\n\nExtra\n{underline}\n- 무관한 불릿"
    )
    with pytest.raises(ValueError, match="Why.*불릿"):
        ai_service.ai_validate(response, "pr")


@pytest.mark.parametrize("heading", ["## Why ##", "Why\n---"])
def test_pr_accepts_equivalent_markdown_h2_forms(heading: str) -> None:
    """동일한 H2 구조인 닫는 해시와 밑줄 제목 표기도 허용합니다."""
    assert ai_service.ai_validate(pr_response().replace("## Why", heading), "pr")


@pytest.mark.parametrize("tag", ["pre", "div"])
def test_pr_does_not_count_html_block_content(
    tag: str,
) -> None:
    """HTML 블록 안의 제목과 불릿을 PR 구조로 인정하지 않습니다."""
    response = "\n".join(
        [
            "PR 초안",
            "",
            f"<{tag}>",
            *pr_response().splitlines()[2:],
            f"</{tag}>",
        ]
    )

    with pytest.raises(ValueError, match="Why.*섹션"):
        ai_service.ai_validate(response, "pr")


@pytest.mark.parametrize(
    "response",
    [
        pr_response().replace("## What", "## Other"),
        pr_response() + "\n## Why\n- 중복 섹션",
        pr_response().replace("- 변경 배경", "- "),
        "PR 초안\n\n<!--\n## Why\n- 변경 배경\n## What\n- 변경 내용\n## How to Test\n- 테스트 미실행\n-->",
        pr_response()
        .replace("- 변경 배경", "")
        .replace("## What", "## Extra\n- 무관한 불릿\n\n## What"),
    ],
)
def test_pr_rejects_invalid_sections_and_empty_bullets(response: str) -> None:
    """누락·중복·관련 없는 불릿·내용 없는 불릿을 거부합니다."""
    with pytest.raises(ValueError):
        ai_service.ai_validate(response, "pr")


def test_pr_does_not_count_sections_inside_fenced_code() -> None:
    """코드 펜스 안의 제목과 불릿은 PR 구조로 인정하지 않습니다."""
    response = (
        "PR 초안\n\n"
        "```markdown\n"
        "## Why\n- 예시 배경\n"
        "## What\n- 예시 변경\n"
        "## How to Test\n- 예시 테스트\n"
        "```"
    )

    with pytest.raises(ValueError, match="Why.*섹션"):
        ai_service.ai_validate(response, "pr")


def test_pr_does_not_count_indented_code_bullets() -> None:
    """들여쓰기 코드 안의 불릿은 섹션 내용을 충족하지 않습니다."""
    response = (
        "PR 초안\n\n"
        "## Why\n    - 코드 예시\n"
        "## What\n- 핵심 변경\n"
        "## How to Test\n- 테스트 방법"
    )

    with pytest.raises(ValueError, match="Why.*불릿"):
        ai_service.ai_validate(response, "pr")


def test_commit_rejects_indented_code_as_body_bullets() -> None:
    """들여쓰기 코드 줄을 커밋 본문의 불릿으로 인정하지 않습니다."""
    with pytest.raises(ValueError, match="불릿으로만"):
        ai_service.ai_validate("제목\n\n    - 코드 예시", "commit")


def test_valid_response_uses_one_api_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """유효한 생성 응답은 재요청하지 않습니다."""
    api_call = Mock(return_value="수정된 내용을 반영합니다")
    monkeypatch.setattr(ai_service, "ai_call_api", api_call)

    assert ai_service.ai_generate_validated(
        "diff", "commit", None, 0.2, 500
    ) == "-- Commit Message --\n수정된 내용을 반영합니다"
    assert api_call.call_count == 1


def test_invalid_response_retries_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """첫 응답이 형식에 맞지 않으면 한 번만 재요청합니다."""
    api_call = Mock(side_effect=["가" * 73, "수정된 내용을 반영합니다"])
    monkeypatch.setattr(ai_service, "ai_call_api", api_call)

    assert ai_service.ai_generate_validated(
        "diff", "commit", None, 0.2, 500
    ).startswith("-- Commit Message --")
    assert api_call.call_count == 2


@pytest.mark.parametrize("finish_reason", ["length", "max_tokens"])
def test_token_limited_response_retries_once(
    finish_reason: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """토큰 한도로 잘린 API 응답은 한 번 재요청하고 완성본을 검증합니다."""
    truncated_response = Mock()
    truncated_response.json.return_value = {
        "choices": [
            {
                "finish_reason": finish_reason,
                "message": {"content": "feat: 불완전한 커밋 제목"},
            }
        ]
    }
    valid_response = Mock()
    valid_response.json.return_value = {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"content": "완성된 커밋 제목"},
            }
        ]
    }
    post = Mock(side_effect=[truncated_response, valid_response])
    monkeypatch.setattr(ai_service, "load_dotenv", lambda: None)
    monkeypatch.setenv("API_KEY", "TEST_ONLY_KEY")
    monkeypatch.setattr(ai_service.requests, "post", post)

    result = ai_service.ai_commit("+ 변경 내용", None, 0.2, 500)

    assert "완성된 커밋 제목" in result
    assert post.call_count == 2
    retry_prompt = post.call_args_list[1].kwargs["json"]["messages"][0]["content"]
    assert "토큰 한도" in retry_prompt
    assert "불완전한 커밋 제목" not in retry_prompt


def test_token_limited_retry_stops_after_second_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """재요청도 토큰 한도에 도달하면 세 번째 호출 없이 원인을 반환합니다."""
    truncated_response = Mock()
    truncated_response.json.return_value = {
        "choices": [
            {
                "finish_reason": "length",
                "message": {"content": "불완전한 제목"},
            }
        ]
    }
    post = Mock(return_value=truncated_response)
    monkeypatch.setattr(ai_service, "load_dotenv", lambda: None)
    monkeypatch.setenv("API_KEY", "TEST_ONLY_KEY")
    monkeypatch.setattr(ai_service.requests, "post", post)

    with pytest.raises(RuntimeError, match="재생성 응답도 토큰 한도"):
        ai_service.ai_commit("+ 변경 내용", None, 0.2, 500)

    assert post.call_count == 2


def test_two_invalid_responses_stop_after_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """두 응답 모두 형식 오류면 세 번째 요청을 보내지 않습니다."""
    api_call = Mock(side_effect=["가" * 73, "나" * 73])
    monkeypatch.setattr(ai_service, "ai_call_api", api_call)

    with pytest.raises(ValueError, match="자 이하"):
        ai_service.ai_generate_validated("diff", "commit", None, 0.2, 500)
    assert api_call.call_count == 2


@pytest.mark.parametrize(
    ("line_count", "expected_diff_lines"),
    [(199, 199), (200, 200), (201, 200)],
)
def test_safe_mode_line_limit(line_count: int, expected_diff_lines: int) -> None:
    """안전모드가 diff의 원문을 최대 200줄까지만 보존합니다."""
    lines = [f"+line-{index}" for index in range(line_count)]
    safe_diff = ai_service.limit_diff("\n".join(lines))

    assert safe_diff.splitlines()[:expected_diff_lines] == lines[:expected_diff_lines]
    assert "+line-200" not in safe_diff
    assert ("Diff truncated" in safe_diff) is (line_count > 200)


def test_safe_mode_reports_truncation_and_excludes_later_lines(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """안전모드가 절단 상태를 알리고 201번째 원문 줄을 제외합니다."""
    generation = Mock(return_value="초안")
    monkeypatch.setattr(ai_service, "ai_generate_validated", generation)
    diff = "\n".join(f"+line-{index}" for index in range(201))

    ai_service.ai_commit(diff, None, 0.2, 500, safe_mode=True)

    prompt = generation.call_args.args[0]
    assert "+line-199" in prompt
    assert "+line-200" not in prompt
    assert "원본 201줄" in capsys.readouterr().err


def test_api_request_uses_selected_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """모델과 생성 파라미터를 HTTP 요청에 전달합니다."""
    response = Mock()
    response.json.return_value = {"choices": [{"message": {"content": "초안"}}]}
    post = Mock(return_value=response)
    monkeypatch.setattr(ai_service, "load_dotenv", lambda: None)
    monkeypatch.setenv("API_KEY", "TEST_ONLY_KEY")
    monkeypatch.setattr(ai_service.requests, "post", post)

    assert ai_service.ai_call_api("prompt", "chosen-model", 0.7, 321) == "초안"

    request = post.call_args.kwargs
    assert request["json"]["model"] == "chosen-model"
    assert request["json"]["temperature"] == 0.7
    assert request["json"]["max_tokens"] == 321
    assert request["timeout"] == 10


def test_missing_api_key_does_not_send_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """키가 없으면 요청 전에 원인을 알리는 오류가 발생합니다."""
    post = Mock()
    monkeypatch.setattr(ai_service, "load_dotenv", lambda: None)
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.setattr(ai_service.requests, "post", post)

    with pytest.raises(ValueError, match="API_KEY"):
        ai_service.ai_call_api("prompt", None, 0.2, 500)
    post.assert_not_called()


@pytest.mark.parametrize(
    ("status_code", "message"),
    [
        (400, "상태 코드: 400"),
        (401, "인증 또는 접근 권한"),
        (403, "인증 또는 접근 권한"),
        (429, "요청 한도"),
        (500, "서버에서 오류"),
    ],
)
def test_http_errors_are_explained(
    status_code: int, message: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """API HTTP 오류 상태에 맞는 안내 문구를 제공합니다."""
    response = requests.Response()
    response.status_code = status_code
    monkeypatch.setattr(ai_service, "load_dotenv", lambda: None)
    monkeypatch.setenv("API_KEY", "TEST_ONLY_KEY")
    monkeypatch.setattr(
        ai_service.requests,
        "post",
        Mock(side_effect=requests.HTTPError(response=response)),
    )

    with pytest.raises(RuntimeError, match=message):
        ai_service.ai_call_api("prompt", None, 0.2, 500)


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (requests.Timeout(), "시간이 초과"),
        (requests.exceptions.SSLError(), "TLS 인증서 검증"),
        (requests.ConnectionError(), "연결할 수 없습니다"),
    ],
)
def test_network_errors_are_explained(
    error: requests.RequestException,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """시간 초과와 연결 실패를 사용자용 오류로 변환합니다."""
    monkeypatch.setattr(ai_service, "load_dotenv", lambda: None)
    monkeypatch.setenv("API_KEY", "TEST_ONLY_KEY")
    monkeypatch.setattr(ai_service.requests, "post", Mock(side_effect=error))

    with pytest.raises(RuntimeError, match=message):
        ai_service.ai_call_api("prompt", None, 0.2, 500)


@pytest.mark.parametrize("payload", [{}, {"choices": []}, None])
def test_malformed_api_responses_have_clear_errors(
    payload: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """누락되거나 잘못된 API 응답을 읽기 쉬운 오류로 변환합니다."""
    response = Mock()
    response.json.return_value = payload
    monkeypatch.setattr(ai_service, "load_dotenv", lambda: None)
    monkeypatch.setenv("API_KEY", "TEST_ONLY_KEY")
    monkeypatch.setattr(ai_service.requests, "post", Mock(return_value=response))

    with pytest.raises(RuntimeError, match="AI API 응답 형식"):
        ai_service.ai_call_api("prompt", None, 0.2, 500)
