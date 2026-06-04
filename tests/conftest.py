import sys

if sys.platform == 'win32':
    # Workaround for Python 3.8+ asyncio ProactorEventLoop issue on Windows
    # https://github.com/python/asyncio/issues/509
    from asyncio.proactor_events import _ProactorBasePipeTransport
    from collections.abc import Callable
    from functools import wraps
    from typing import Any

    def silence_event_loop_closed(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            try:
                return func(self, *args, **kwargs)
            except (RuntimeError, ValueError):
                pass
        return wrapper

    _ProactorBasePipeTransport.__del__ = silence_event_loop_closed(_ProactorBasePipeTransport.__del__)  # type: ignore[method-assign]
