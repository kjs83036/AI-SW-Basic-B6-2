"""Git·AI CLI를 실제 코드 경로로 실행하며 HTTP 요청을 관찰하는 수동 도구입니다."""

import argparse
import json
import os
from pathlib import Path
import runpy
import sys
from typing import cast
from urllib.parse import urlsplit

import requests


DUMMY_API_KEY = "manual-test-dummy-key"
API_HOST = "copa.codyssey.kr"
API_PATH = "/v1/chat/completions"


def valid_commit() -> str:
    """수동 확인에 쓸 정상 커밋 응답을 돌려줍니다."""
    return "feat: 검증용 변경을 반영\n\n- 수동 확인용 문구를 추가합니다."


def valid_pr() -> str:
    """수동 확인에 쓸 정상 PR 응답을 돌려줍니다."""
    return (
        "검증용 변경을 설명하는 PR\n\n"
        "## Why\n- 변경 내용을 검토하기 쉽게 정리합니다.\n\n"
        "## What\n- 수동 확인용 문구를 추가합니다.\n\n"
        "## How to Test\n- 출력 형식을 직접 확인합니다."
    )


def response_content(output_kind: str) -> str:
    """명령 종류에 맞는 정상 응답을 반환합니다."""
    return valid_pr() if output_kind == "pr" else valid_commit()


def fixture_sequence(case: str, output_kind: str) -> list[tuple[str, object]]:
    """선택한 수동 사례에 맞춰 순서가 정해진 응답을 만듭니다."""
    valid = response_content(output_kind)
    sequences: dict[str, list[tuple[str, object]]] = {
        "valid": [("json", (valid, "stop"))],
        "commit-title-50": [("json", ("가" * 50, "stop"))],
        "commit-title-51": [("json", ("가" * 51, "stop"))],
        "commit-title-72": [("json", ("가" * 72, "stop"))],
        "commit-title-73": [
            ("json", ("가" * 73, "stop")),
            ("json", (valid_commit(), "stop")),
        ],
        "commit-title-73-then-valid": [
            ("json", ("가" * 73, "stop")),
            ("json", (valid_commit(), "stop")),
        ],
        "commit-title-73-twice": [
            ("json", ("가" * 73, "stop")),
            ("json", ("가" * 73, "stop")),
        ],
        "commit-three-bullets": [
            ("json", ("제목\n\n- 첫째\n- 둘째\n- 셋째", "stop")),
            ("json", (valid_commit(), "stop")),
        ],
        "pr-title-80": [
            ("json", ("가" * 80 + "\n\n" + valid_pr().split("\n\n", 1)[1], "stop"))
        ],
        "pr-title-81": [
            ("json", ("가" * 81 + "\n\n" + valid_pr().split("\n\n", 1)[1], "stop")),
            ("json", (valid_pr(), "stop")),
        ],
        "pr-title-81-then-valid": [
            ("json", ("가" * 81 + "\n\n" + valid_pr().split("\n\n", 1)[1], "stop")),
            ("json", (valid_pr(), "stop")),
        ],
        "pr-missing-section": [
            ("json", ("검증용 PR\n\n## Why\n- 이유\n\n## What\n- 변경", "stop")),
            ("json", (valid_pr(), "stop")),
        ],
        "pr-empty-bullet": [
            (
                "json",
                (
                    "검증용 PR\n\n## Why\n- \n\n## What\n- 변경\n\n## How to Test\n- 확인",
                    "stop",
                ),
            ),
            ("json", (valid_pr(), "stop")),
        ],
        "pr-invalid-then-valid": [
            ("json", ("검증용 PR\n\n## Why\n- 이유\n\n## What\n- 변경", "stop")),
            ("json", (valid_pr(), "stop")),
        ],
        "invalid-twice": [("json", ("", "stop")), ("json", ("", "stop"))],
        "token-limit-then-valid": [
            ("json", (valid, "length")),
            ("json", (valid, "stop")),
        ],
        "token-limit-twice": [("json", (valid, "length")), ("json", (valid, "length"))],
        "http-401": [("http", 401)],
        "http-403": [("http", 403)],
        "http-429": [("http", 429)],
        "http-500": [("http", 500)],
        "http-control": [("http-control", None)],
        "connection-error": [("raise", requests.exceptions.ConnectionError)],
        "timeout": [("raise", requests.exceptions.Timeout)],
        "tls-error": [("raise", requests.exceptions.SSLError)],
        "invalid-json": [("invalid-json", None)],
        "missing-choices": [("json-body", {"message": "응답 구조 오류"})],
        "non-string-content": [
            (
                "json-body",
                {"choices": [{"message": {"content": None}, "finish_reason": "stop"}]},
            )
        ],
        "missing-key": [],
    }
    if case not in sequences:
        raise ValueError(f"알 수 없는 사례입니다: {case}")
    return sequences[case]


def make_response(url: str, kind: str, value: object) -> requests.Response:
    """requests가 사용하는 응답 객체로 모의 결과를 포장합니다."""
    response = requests.Response()
    response.url = url
    response.request = requests.Request("POST", url).prepare()
    response.headers["Content-Type"] = "application/json"

    if kind == "http":
        response.status_code = int(value)
        body = {"error": {"message": f"모의 오류: {DUMMY_API_KEY}"}}
    elif kind == "http-control":
        response.status_code = 400
        body = {"error": {"message": f"모의 오류: {DUMMY_API_KEY}\x1b\x00끝"}}
    elif kind == "invalid-json":
        response.status_code = 200
        response._content = b"{"  # 잘못된 JSON을 API 응답으로 재현합니다.
        return response
    elif kind == "json-body":
        response.status_code = 200
        body = value
    else:
        content, finish_reason = cast(tuple[object, object], value)
        response.status_code = 200
        body = {
            "choices": [
                {
                    "message": {"content": content},
                    "finish_reason": finish_reason,
                }
            ]
        }

    response._content = json.dumps(body, ensure_ascii=False).encode("utf-8")
    return response


def parse_args() -> argparse.Namespace:
    """관찰기 옵션과 실제 CLI로 넘길 인자를 나눠 읽습니다."""
    parser = argparse.ArgumentParser(
        description="실제 CLI 코드 경로에서 API 요청 JSON을 확인합니다."
    )
    parser.add_argument("--mode", choices=("inspect", "fixture"), required=True)
    parser.add_argument("--case", help="fixture 모드에서 사용할 응답 사례")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--git-dir", type=Path, default=Path.cwd())
    parser.add_argument("app_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.app_args and args.app_args[0] == "--":
        args.app_args = args.app_args[1:]
    if not args.app_args:
        parser.error("-- 뒤에 실행할 status, diff, commit 또는 pr 명령이 필요합니다.")
    if args.mode == "fixture" and not args.case:
        parser.error("fixture 모드에는 --case가 필요합니다.")
    return args


def run() -> int:
    """네트워크를 차단한 상태에서 제품 CLI의 명령을 실행합니다."""
    args = parse_args()
    original_dir = Path.cwd()
    project_dir = (original_dir / args.project).resolve()
    git_dir = (original_dir / args.git_dir).resolve()
    source_dir = project_dir / "src"
    entrypoint = source_dir / "output_6_1" / "main.py"
    if not entrypoint.is_file():
        print("[관찰기] 프로젝트 경로에서 src/output_6_1/main.py를 찾지 못했습니다.", file=sys.stderr)
        return 2
    if not git_dir.is_dir():
        print("[관찰기] 지정한 Git 작업 디렉터리가 없습니다.", file=sys.stderr)
        return 2

    app_args = list(args.app_args)
    command = next((value for value in app_args if value in {"commit", "pr"}), "")
    if args.mode == "fixture":
        try:
            responses = fixture_sequence(args.case, command)
        except ValueError as error:
            print(f"[관찰기] {error}", file=sys.stderr)
            return 2
    else:
        responses = [("json", (response_content(command), "stop"))]

    call_count = 0

    def observed_post(url: str, **kwargs: object) -> requests.Response:
        """요청을 출력하고 로컬 모의 응답만 반환합니다."""
        nonlocal call_count
        parsed_url = urlsplit(url)
        if (
            parsed_url.scheme != "https"
            or parsed_url.hostname != API_HOST
            or parsed_url.path != API_PATH
        ):
            raise RuntimeError("[관찰기] 허용하지 않은 HTTP 목적지 요청을 차단했습니다.")

        call_count += 1
        payload = kwargs.get("json")
        if not isinstance(payload, dict):
            raise RuntimeError("[관찰기] 요청 JSON이 없습니다.")
        print(f"[관찰기] API 요청 {call_count}: HTTPS {API_HOST}{API_PATH}")
        print("[관찰기] Authorization 헤더를 제외한 요청 JSON:")
        print(json.dumps(payload, ensure_ascii=False, indent=2))

        index = call_count - 1
        if index >= len(responses):
            raise RuntimeError("[관찰기] 미리 정한 응답보다 API 요청이 더 많습니다.")
        kind, value = responses[index]
        if kind == "raise":
            error_type = cast(type[Exception], value)
            raise error_type("수동 확인용 모의 연결 오류")
        return make_response(url, kind, value)

    old_post = requests.post
    old_argv = sys.argv
    old_path = list(sys.path)
    old_api_key = os.environ.get("API_KEY")
    old_dotenv_flag = os.environ.get("PYTHON_DOTENV_DISABLED")
    sys.path.insert(0, str(source_dir))
    sys.argv = [str(entrypoint), *app_args]
    requests.post = observed_post

    if args.mode == "fixture" and args.case == "missing-key":
        os.environ.pop("API_KEY", None)
        os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    else:
        os.environ["API_KEY"] = DUMMY_API_KEY

    try:
        os.chdir(git_dir)
        try:
            runpy.run_module("output_6_1.main", run_name="__main__", alter_sys=True)
            exit_code = 0
        except SystemExit as error:
            exit_code = error.code if isinstance(error.code, int) else (0 if error.code is None else 1)
        print(f"[관찰기] 가로챈 API 요청 수: {call_count}")
        if call_count < len(responses):
            print(f"[관찰기] 사용하지 않은 모의 응답 수: {len(responses) - call_count}")
        return exit_code
    finally:
        os.chdir(original_dir)
        requests.post = old_post
        sys.argv = old_argv
        sys.path[:] = old_path
        if old_api_key is None:
            os.environ.pop("API_KEY", None)
        else:
            os.environ["API_KEY"] = old_api_key
        if old_dotenv_flag is None:
            os.environ.pop("PYTHON_DOTENV_DISABLED", None)
        else:
            os.environ["PYTHON_DOTENV_DISABLED"] = old_dotenv_flag


if __name__ == "__main__":
    raise SystemExit(run())
