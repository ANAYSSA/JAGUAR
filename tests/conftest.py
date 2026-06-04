import sys

if sys.platform == 'win32':
    # Workaround for Python 3.8+ asyncio ProactorEventLoop issue on Windows
    # https://github.com/python/asyncio/issues/509
    from asyncio.proactor_events import _ProactorBasePipeTransport  # type: ignore
    from functools import wraps

    def silence_event_loop_closed(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            try:
                return func(self, *args, **kwargs)
            except (RuntimeError, ValueError):
                pass
        return wrapper

    _ProactorBasePipeTransport.__del__ = silence_event_loop_closed(_ProactorBasePipeTransport.__del__)
