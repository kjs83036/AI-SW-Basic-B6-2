import argparse
import math
import sys
from argparse import ArgumentParser, Namespace

from . import ai_service, git_service


def show_status(_args: Namespace) -> None:
    """현재 Git 변경 상태를 출력합니다."""
    status = git_service.git_status()
    if status:
        print(status, end="")
    else:
        print("변경 사항이 없습니다.")


def show_diff(_args: Namespace) -> None:
    """스테이징하지 않은 추적 파일의 변경 내용을 출력합니다."""
    diff = git_service.git_diff()
    if diff:
        print(diff, end="")
    else:
        print("git diff에서 수집할 변경 내용이 없습니다.")


def generate_commit(args: Namespace) -> None:
    """Git 변경 내용으로 커밋 메시지 초안을 생성합니다."""
    status_result = git_service.git_status()
    if not status_result:
        print("변경 사항이 없습니다. 커밋 메시지를 생성할 수 없습니다.")
        return
    diff = git_service.git_diff()
    if not diff:
        print("git diff에서 수집할 변경 내용이 없습니다.")
        return

    result = ai_service.ai_commit(
        diff,
        model=args.model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        safe_mode=args.safe_mode,
    )
    print(result)


def generate_pr(args: Namespace) -> None:
    """Git 변경 내용으로 PR 초안을 생성합니다."""
    status_result = git_service.git_status()
    if not status_result:
        print("변경 사항이 없습니다. PR 초안을 생성할 수 없습니다.")
        return

    diff = git_service.git_diff()
    if not diff:
        print("git diff에서 수집할 변경 내용이 없습니다.")
        return

    result = ai_service.ai_pr(
        diff,
        model=args.model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        safe_mode=args.safe_mode,
    )
    print(result)


def finite_temperature(value: str) -> float:
    """JSON으로 전송할 수 있는 유한한 실수만 허용합니다."""
    try:
        temperature = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("유한한 실수를 입력하세요.") from None
    if not math.isfinite(temperature):
        raise argparse.ArgumentTypeError("유한한 실수를 입력하세요.")
    return temperature


def positive_token_count(value: str) -> int:
    """최대 생성 토큰 수는 양의 정수만 허용합니다."""
    try:
        token_count = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("양의 정수를 입력하세요.") from None
    if token_count <= 0:
        raise argparse.ArgumentTypeError("양의 정수를 입력하세요.")
    return token_count


def build_parser() -> ArgumentParser:
    """CLI 명령과 AI 생성 옵션을 정의한 파서를 구성합니다."""
    parser = argparse.ArgumentParser(
        description="Git 변경사항으로 커밋 메시지와 PR 초안을 만듭니다."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status", help="변경 파일 상태를 출력합니다.")
    status_parser.set_defaults(handler=show_status)

    diff_parser = subparsers.add_parser("diff", help="현재 변경 내용을 출력합니다.")
    diff_parser.set_defaults(handler=show_diff)

    commands = [
        ("commit", generate_commit, "커밋 메시지 초안을 생성합니다."),
        ("pr", generate_pr, "PR 초안을 생성합니다."),
    ]
    for command, handler, help_text in commands:
        command_parser = subparsers.add_parser(command, help=help_text)
        command_parser.add_argument("--model", default=None)
        command_parser.add_argument(
            "--temperature",
            type=finite_temperature,
            default=0.2,
            help="생성 다양성을 조정합니다. opus 또는 claude-opus-* 모델에는 전송하지 않습니다.",
        )
        command_parser.add_argument("--max-tokens", type=positive_token_count, default=500)
        command_parser.add_argument("--safe-mode", action="store_true")
        command_parser.set_defaults(handler=handler)

    return parser


def main() -> None:
    """명령행 인자를 해석하고 선택된 명령 처리 함수를 실행합니다."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    args = build_parser().parse_args()
    try:
        args.handler(args)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
