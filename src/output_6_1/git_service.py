from collections.abc import Sequence
import subprocess


def run_git(arguments: Sequence[str]) -> str:
    """현재 작업 디렉터리에서 Git을 실행하고 표준 출력을 UTF-8로 반환합니다.

    subprocess의 바이트 출력을 직접 디코딩해 Windows 로캘에 따라 한글이나
    이모지가 달리 해석되는 일을 막습니다. Git 실패에서는 표준 오류를 먼저
    사용하고, 결과를 UTF-8로 읽지 못한 경우 빈 결과로 숨기지 않고 오류로 알립니다.
    """
    try:
        result = subprocess.run(
            ["git", *arguments],
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as error:
        # Git이 별도 오류 문구를 남기지 않은 경우 표준 출력을 진단 정보로 사용합니다.
        raw_detail = error.stderr or error.stdout
        detail = (
            raw_detail.decode("utf-8", errors="replace").strip()
            if isinstance(raw_detail, bytes)
            else str(error)
        )
        raise RuntimeError(f"Git 명령 실행에 실패했습니다: {detail}") from error
    except UnicodeError as error:
        raise RuntimeError("Git 결과를 UTF-8로 읽을 수 없습니다.") from error

    # 성공 출력도 로캘 대신 프로젝트가 기대하는 UTF-8로 명시해 해석합니다.
    try:
        return result.stdout.decode("utf-8")
    except UnicodeError as error:
        raise RuntimeError("Git 결과를 UTF-8로 읽을 수 없습니다.") from error


def git_status() -> str:
    """변경 파일 상태를 간단한 형식으로 반환합니다."""
    return run_git(["status", "--short"])


def git_diff() -> str:
    """스테이징하지 않은 추적 파일의 변경 내용을 반환합니다."""
    return run_git(["diff"])
