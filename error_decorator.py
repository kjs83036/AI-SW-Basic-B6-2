from functools import wraps

def handle_error(func):
    """
    함수 실행 중 발생하는 예외를 가로채어 에러 메시지를 출력하고,
    REPL 환경이 중단되지 않도록 None을 반환하는 오류 처리 데코레이터입니다.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            error_type = type(e).__name__
            print(f"[ERROR] {error_type}: {e}")
            return None
    return wrapper