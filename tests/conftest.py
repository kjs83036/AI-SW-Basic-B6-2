import os
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """기준 커밋이 있는 임시 Git 저장소를 준비합니다."""
    repository = tmp_path / "repository"
    repository.mkdir()

    def run_git(*arguments: str) -> None:
        """임시 저장소에서 Git 명령을 실행합니다."""
        subprocess.run(
            ["git", *arguments],
            cwd=repository,
            check=True,
            capture_output=True,
            encoding="utf-8",
        )

    run_git("init", "--quiet")
    run_git("config", "user.name", "Codex Test")
    run_git("config", "user.email", "codex-test@example.invalid")
    (repository / "app.py").write_text("value = 1\n", encoding="utf-8")
    run_git("add", "app.py")
    run_git("commit", "--quiet", "-m", "기준 상태")

    return repository


@pytest.fixture
def isolated_cli_environment() -> dict[str, str]:
    """CLI 테스트에서 개인 환경 변수와 실제 자격 증명을 격리합니다."""
    environment = os.environ.copy()
    environment.pop("API_KEY", None)
    environment.pop("PYTHONPATH", None)
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    source_path = str(Path(__file__).resolve().parents[1] / "src")
    environment["PYTHONPATH"] = source_path
    return environment
