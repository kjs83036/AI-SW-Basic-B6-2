import subprocess
from pathlib import Path

import pytest

from output_6_1 import git_service


def test_git_diff_preserves_korean_and_emoji(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """UTF-8 인코딩으로 한국어와 이모지가 포함된 diff를 수집합니다."""
    monkeypatch.chdir(git_repo)
    (git_repo / "app.py").write_text(
        'value = "안녕하세요😀"\n', encoding="utf-8"
    )

    diff = git_service.git_diff()
    status = git_service.git_status()

    assert '"안녕하세요😀"' in diff
    assert "app.py" in status


def test_git_command_failure_includes_git_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Git 저장소가 아닌 위치에서 실행하면 원인과 함께 실패합니다."""
    monkeypatch.chdir(tmp_path)
    with pytest.raises(RuntimeError, match="Git 명령 실행에 실패했습니다"):
        git_service.run_git(["status", "--short"])


def test_invalid_git_output_encoding_has_actionable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """UTF-8이 아닌 Git 결과를 빈 변경 내용으로 처리하지 않습니다."""

    def run_git_with_invalid_output(*args: object, **kwargs: object) -> None:
        raise UnicodeDecodeError("utf-8", b"\x80", 0, 1, "잘못된 바이트")

    monkeypatch.setattr(git_service.subprocess, "run", run_git_with_invalid_output)

    with pytest.raises(RuntimeError, match="Git 결과를 UTF-8로 읽을 수 없습니다"):
        git_service.run_git(["diff"])


def test_git_diff_reports_cp949_content_encoding_error(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CP949 변경 내용은 빈 diff가 아니라 명확한 인코딩 오류를 반환합니다."""
    target = git_repo / "app.py"
    target.write_bytes("기준 내용\n".encode("cp949"))
    subprocess.run(["git", "-C", str(git_repo), "add", "app.py"], check=True)
    subprocess.run(
        ["git", "-C", str(git_repo), "commit", "--quiet", "-m", "기준 상태"],
        check=True,
    )
    target.write_bytes("수정 내용\n".encode("cp949"))
    monkeypatch.chdir(git_repo)

    with pytest.raises(RuntimeError, match="UTF-8로 읽을 수 없습니다"):
        git_service.git_diff()


def test_git_output_is_explicitly_decoded_as_utf8(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Git subprocess에 UTF-8 출력 인코딩을 전달합니다."""
    received: dict[str, object] = {}

    def run_git(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        received.update(kwargs)
        return subprocess.CompletedProcess(args[0], 0, "한글".encode("utf-8"), b"")

    monkeypatch.setattr(git_service.subprocess, "run", run_git)

    assert git_service.run_git(["status"]) == "한글"
    assert "text" not in received
