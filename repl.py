import cmd
import git_service
import ai_service
import error_decorator


class GitAssistant(cmd.Cmd):
    prompt = "git-ai> "
    intro = "명령어: status, diff, commit, pr, quit"

    def __init__(self, model, temperature, max_tokens, safe_mode):
        super().__init__()
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.safe_mode = safe_mode

    @error_decorator.handle_error
    def do_status(self, arg):
        """현재 Git 변경 상태를 출력합니다."""
        print(git_service.git_status())

    @error_decorator.handle_error
    def do_diff(self, arg):
        """현재 변경 내용을 출력합니다."""
        print(git_service.git_diff())

    @error_decorator.handle_error
    def do_commit(self, arg):
        """변경 내용을 바탕으로 커밋 메시지 초안을 생성합니다."""
        diff = git_service.git_diff()
        if not diff:
            print("변경 사항이 없습니다.")
            return
        print(
            ai_service.ai_commit(
                diff,
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                safe_mode=self.safe_mode,
            )
        )

    @error_decorator.handle_error
    def do_pr(self, arg):
        """변경 내용을 바탕으로 PR 초안을 생성합니다."""
        diff = git_service.git_diff()
        if not diff:
            print("변경 사항이 없습니다.")
            return
        print(
            ai_service.ai_pr(
                diff,
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                safe_mode=self.safe_mode,
            )
        )

    def emptyline(self):
        """빈 줄을 입력하면 아무 작업도 하지 않습니다."""
        pass

    def do_quit(self, arg):
        """프로그램을 종료합니다."""
        return True

    def do_EOF(self, arg):
        """Ctrl-D 입력으로 프로그램을 종료합니다."""
        return self.do_quit(arg)


def run(model, temperature, max_tokens, safe_mode):
    GitAssistant(model, temperature, max_tokens, safe_mode).cmdloop()
