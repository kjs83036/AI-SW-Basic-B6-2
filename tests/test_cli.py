import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


CLI_BOOTSTRAP = """
import json
import os
import sys
from unittest.mock import Mock, patch

import output_6_1.ai_service as ai_service

patch.object(ai_service, "load_dotenv").start()
if "TEST_API_RESPONSES" in os.environ:
    responses = []
    for content in json.loads(os.environ["TEST_API_RESPONSES"]):
        response = Mock()
        response.json.return_value = {"choices": [{"message": {"content": content}}]}
        responses.append(response)
    patch.object(ai_service.requests, "post", side_effect=responses).start()
if "TEST_API_HTTP_ERROR" in os.environ:
    response = ai_service.requests.Response()
    response.status_code = 400
    response._content = os.environ["TEST_API_HTTP_ERROR"].encode("utf-8")
    patch.object(ai_service.requests, "post", side_effect=ai_service.requests.HTTPError(response=response)).start()
sys.argv = ["output-6-1", *sys.argv[1:]]

from output_6_1.main import main

main()
"""


def run_cli(
    repository: Path,
    environment: dict[str, str],
    *arguments: str,
) -> subprocess.CompletedProcess[str]:
    """테스트 저장소에서 CLI를 실행하고 터미널 결과를 반환합니다."""
    return subprocess.run(
        [sys.executable, "-B", "-c", CLI_BOOTSTRAP, *arguments],
        cwd=repository,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_clean_repository_exits_successfully(
    git_repo: Path, isolated_cli_environment: dict[str, str]
) -> None:
    """변경 사항이 없으면 안내를 출력하고 정상 종료합니다."""
    result = run_cli(git_repo, isolated_cli_environment, "commit")

    assert result.returncode == 0
    assert "변경 사항이 없습니다" in result.stdout
    assert result.stderr == ""


def test_non_git_directory_exits_with_error(
    tmp_path: Path, isolated_cli_environment: dict[str, str]
) -> None:
    """Git 저장소가 아니면 stderr와 비정상 종료 코드를 반환합니다."""
    result = run_cli(tmp_path, isolated_cli_environment, "status")

    assert result.returncode == 1
    assert "[ERROR]" in result.stderr
    assert "Git 명령 실행에 실패했습니다" in result.stderr
    assert result.stdout == ""


def test_cli_reports_cp949_diff_instead_of_clean_repository(
    git_repo: Path, isolated_cli_environment: dict[str, str]
) -> None:
    """CP949 diff 디코딩 실패는 정상 종료나 변경 없음으로 표시하지 않습니다."""
    target = git_repo / "app.py"
    target.write_bytes("기준 내용\n".encode("cp949"))
    subprocess.run(["git", "-C", str(git_repo), "add", "app.py"], check=True)
    subprocess.run(
        ["git", "-C", str(git_repo), "commit", "--quiet", "-m", "기준 상태"],
        check=True,
    )
    target.write_bytes("수정 내용\n".encode("cp949"))

    result = run_cli(git_repo, isolated_cli_environment, "commit")

    assert result.returncode == 1
    assert "[ERROR]" in result.stderr
    assert "UTF-8로 읽을 수 없습니다" in result.stderr
    assert "변경 사항이 없습니다" not in result.stdout


def test_diff_cli_prints_emoji_with_utf8_when_parent_uses_cp949(
    git_repo: Path, isolated_cli_environment: dict[str, str]
) -> None:
    """기본 파이프 인코딩이 CP949여도 diff의 이모지를 출력합니다."""
    (git_repo / "app.py").write_text('value = "😀"\n', encoding="utf-8")
    isolated_cli_environment["PYTHONUTF8"] = "0"
    isolated_cli_environment["PYTHONIOENCODING"] = "cp949"

    result = run_cli(git_repo, isolated_cli_environment, "diff")

    assert result.returncode == 0, result.stderr
    assert "😀" in result.stdout


def test_missing_api_key_exits_with_error(
    git_repo: Path, isolated_cli_environment: dict[str, str]
) -> None:
    """환경변수에 키가 없으면 외부 요청 없이 비정상 종료합니다."""
    (git_repo / "app.py").write_text("value = 2\n", encoding="utf-8")
    result = run_cli(git_repo, isolated_cli_environment, "commit")

    assert result.returncode == 1
    assert "[ERROR]" in result.stderr
    assert "API_KEY" in result.stderr


def test_commit_and_pr_print_mocked_drafts_without_git_changes(
    git_repo: Path, isolated_cli_environment: dict[str, str]
) -> None:
    """commit과 pr이 모의 응답을 출력해도 Git 상태를 변경하지 않습니다."""
    (git_repo / "app.py").write_text(
        'value = "한글 변경"\n', encoding="utf-8"
    )
    before_head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=git_repo, encoding="utf-8"
    )
    before_status = subprocess.check_output(
        ["git", "status", "--porcelain=v1"], cwd=git_repo, encoding="utf-8"
    )
    isolated_cli_environment["API_KEY"] = "TEST_ONLY_KEY"
    isolated_cli_environment["TEST_API_RESPONSES"] = json.dumps(
        ["한글 변경을 반영합니다"], ensure_ascii=False
    )

    commit_result = run_cli(git_repo, isolated_cli_environment, "commit")
    pr_content = (
        "PR 초안\n\n"
        "## Why\n- 변경 배경\n\n"
        "## What\n- 핵심 변경\n\n"
        "## How to Test\n- 테스트 미실행"
    )
    isolated_cli_environment["TEST_API_RESPONSES"] = json.dumps(
        [pr_content], ensure_ascii=False
    )
    pr_result = run_cli(git_repo, isolated_cli_environment, "pr")
    after_head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=git_repo, encoding="utf-8"
    )
    after_status = subprocess.check_output(
        ["git", "status", "--porcelain=v1"], cwd=git_repo, encoding="utf-8"
    )

    assert commit_result.returncode == 0, commit_result.stderr
    assert "한글 변경을 반영합니다" in commit_result.stdout
    assert "AI API 요청: 1회" in commit_result.stderr
    assert pr_result.returncode == 0, pr_result.stderr
    assert "## Why" in pr_result.stdout
    assert "## What" in pr_result.stdout
    assert "## How to Test" in pr_result.stdout
    assert "AI API 요청: 1회" in pr_result.stderr
    assert before_head == after_head
    assert before_status == after_status


def test_cli_logs_both_api_attempts_after_format_retry(
    git_repo: Path, isolated_cli_environment: dict[str, str]
) -> None:
    """형식 오류로 재요청하면 첫 번째와 두 번째 호출을 표시합니다."""
    (git_repo / "app.py").write_text("value = 2\n", encoding="utf-8")
    isolated_cli_environment["API_KEY"] = "TEST_ONLY_KEY"
    isolated_cli_environment["TEST_API_RESPONSES"] = json.dumps(
        ["가" * 73, "수정된 내용을 반영합니다"], ensure_ascii=False
    )

    result = run_cli(git_repo, isolated_cli_environment, "commit")

    assert result.returncode == 0, result.stderr
    assert "AI API 요청: 1회" in result.stderr
    assert "AI API 요청: 2회" in result.stderr


@pytest.mark.parametrize("command", ["commit", "pr"])
@pytest.mark.parametrize("retry_succeeds", [True, False])
def test_cli_does_not_print_terminal_controls_from_api(
    git_repo: Path,
    isolated_cli_environment: dict[str, str],
    command: str,
    retry_succeeds: bool,
) -> None:
    """터미널 제어문자는 재생성 성공 여부와 관계없이 stdout과 stderr에 출력하지 않습니다."""
    (git_repo / "app.py").write_text("value = 2\n", encoding="utf-8")
    isolated_cli_environment["API_KEY"] = "TEST_ONLY_KEY"
    valid = (
        "PR 초안\n\n## Why\n- 배경\n\n## What\n- 변경\n\n## How to Test\n- 미실행"
        if command == "pr" else "변경 반영"
    )
    invalid = valid.replace(valid.splitlines()[0], "변경\x1b[2J 반영", 1)
    isolated_cli_environment["TEST_API_RESPONSES"] = json.dumps(
        [invalid, valid if retry_succeeds else invalid]
    )

    result = run_cli(git_repo, isolated_cli_environment, command)

    assert result.returncode == (0 if retry_succeeds else 1)
    assert "\x1b" not in result.stdout + result.stderr
    assert "AI API 요청: 2회" in result.stderr
    if not retry_succeeds:
        assert "터미널 제어문자" in result.stderr
        assert result.stdout == ""


@pytest.mark.parametrize("command", ["commit", "pr"])
def test_cli_does_not_print_terminal_controls_from_http_errors(
    git_repo: Path, isolated_cli_environment: dict[str, str], command: str
) -> None:
    """HTTP 오류 원인도 제어문자와 API 키를 노출하지 않고 실패로 종료합니다."""
    (git_repo / "app.py").write_text("value = 2\n", encoding="utf-8")
    isolated_cli_environment["API_KEY"] = "TEST_ONLY_KEY"
    isolated_cli_environment["TEST_API_HTTP_ERROR"] = json.dumps(
        {"error": {"message": "Unsupported model \x1b[2J TEST_ONLY_KEY"}}
    )

    result = run_cli(git_repo, isolated_cli_environment, command)

    assert result.returncode == 1
    assert result.stdout == ""
    assert "Unsupported model" in result.stderr
    assert "TEST_ONLY_KEY" not in result.stderr
    assert "\x1b" not in result.stderr
    assert "AI API 요청: 2회" not in result.stderr


@pytest.mark.parametrize("command", ["commit", "pr"])
@pytest.mark.parametrize(
    ("option", "value", "message"),
    [
        ("--temperature", "nan", "유한한 실수"),
        ("--temperature", "inf", "유한한 실수"),
        ("--temperature", "-inf", "유한한 실수"),
        ("--temperature", "abc", "유한한 실수"),
        ("--max-tokens", "0", "양의 정수"),
        ("--max-tokens", "-1", "양의 정수"),
        ("--max-tokens", "1.5", "양의 정수"),
    ],
)
def test_invalid_generation_options_fail_before_request(
    git_repo: Path,
    isolated_cli_environment: dict[str, str],
    command: str,
    option: str,
    value: str,
    message: str,
) -> None:
    """잘못된 생성 옵션은 API 호출 전에 옵션 오류 코드 2로 거부합니다."""
    (git_repo / "app.py").write_text("value = 2\n", encoding="utf-8")
    result = run_cli(git_repo, isolated_cli_environment, command, f"{option}={value}")
    assert result.returncode == 2
    assert option in result.stderr
    assert message in result.stderr
    assert "AI API 요청:" not in result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize("command", ["commit", "pr"])
def test_generation_accepts_zero_temperature_and_one_token_setting(
    git_repo: Path,
    isolated_cli_environment: dict[str, str],
    command: str,
) -> None:
    """유효한 경계 설정은 모의 응답을 이용해 정상 생성할 수 있습니다."""
    (git_repo / "app.py").write_text("value = 2\n", encoding="utf-8")
    isolated_cli_environment["API_KEY"] = "TEST_ONLY_KEY"
    draft = (
        "PR 초안\n\n## Why\n- 배경\n\n## What\n- 변경\n\n## How to Test\n- 미실행"
        if command == "pr" else "변경 반영"
    )
    isolated_cli_environment["TEST_API_RESPONSES"] = json.dumps([draft])
    result = run_cli(
        git_repo, isolated_cli_environment, command,
        "--temperature=0", "--max-tokens=1",
    )
    assert result.returncode == 0, result.stderr
    assert "AI API 요청: 1회" in result.stderr
