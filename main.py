import repl
import argparse


def build_parser():
    parser = argparse.ArgumentParser(
        description="Git 변경사항으로 커밋 메시지와 PR 초안을 만듭니다."
    )
    subparsers = parser.add_subparsers(dest="command")

    for command in ("commit", "pr"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("--model", default=None)
        command_parser.add_argument("--temperature", type=float, default=0.2)
        command_parser.add_argument("--max-tokens", type=int, default=500)
        command_parser.add_argument("--safe-mode", action="store_true")

    return parser


def main():
    args = build_parser().parse_args()

    if args.command is None:
        if args.command is None:
            repl.run(
                model=None,
                temperature=0.2,
                max_tokens=500,
                safe_mode=False,
            )
    return

    assistant = repl.GitAssistant(
        model=args.model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        safe_mode=args.safe_mode,
    )
    assistant.onecmd(args.command)


if __name__ == "__main__":
    main()
