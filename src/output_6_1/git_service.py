from collections.abc import Sequence
import subprocess


def run_git(arguments: Sequence[str]) -> str:
    """현재 터미널 작업 위치에서 Git 명령을 실행합니다."""
    try:
        result = subprocess.run(
            ["git", *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or str(error)).strip()
        raise RuntimeError(f"Git 명령 실행에 실패했습니다: {detail}") from error
    except UnicodeError as error:
        raise RuntimeError("Git 결과를 UTF-8로 읽을 수 없습니다.") from error

    return result.stdout


def git_status() -> str:
    """변경 파일 상태를 간단한 형식으로 반환합니다."""
    return run_git(["status", "--short"])


def git_diff() -> str:
    """스테이징하지 않은 추적 파일의 변경 내용을 반환합니다."""
    return run_git(["diff"])
