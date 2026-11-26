import importlib
import inspect
import re

from publishers.base import Adapter


def get_adapter(platform: str) -> Adapter:
    if not re.fullmatch(r"[a-z][a-z0-9_]*", platform):
        raise ValueError("平台标识格式无效。")
    try:
        module = importlib.import_module(f"publishers.{platform}.adapter")
    except ModuleNotFoundError as exc:
        if exc.name in {f"publishers.{platform}", f"publishers.{platform}.adapter"}:
            raise ValueError(f"平台适配器未实现：{platform}") from exc
        raise
    for candidate in vars(module).values():
        if (
            inspect.isclass(candidate)
            and candidate is not Adapter
            and issubclass(candidate, Adapter)
            and candidate.platform == platform
        ):
            return candidate()
    raise ValueError(f"平台适配器未实现：{platform}")
