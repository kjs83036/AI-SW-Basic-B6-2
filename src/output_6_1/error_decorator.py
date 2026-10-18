from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


def handle_error(func: Callable[P, R]) -> Callable[P, R | None]:
    """
    함수 실행 중 발생하는 예외를 가로채어 에러 메시지를 출력하고,
    CLI 명령 실행이 중단되지 않도록 None을 반환하는 오류 처리 데코레이터입니다.
    """
    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R | None:
        """예외를 표시하고 데코레이션된 함수의 인자와 반환값을 보존합니다."""
        try:
            return func(*args, **kwargs)
        except Exception as e:
            error_type = type(e).__name__
            print(f"[ERROR] {error_type}: {e}")
            return None

    return wrapper
