import pytest

from publishers.base import Adapter
from publishers.registry import get_adapter


def test_adapter_registry_loads_csdn():
    adapter = get_adapter("csdn")
    assert isinstance(adapter, Adapter)
    assert adapter.platform == "csdn"
    assert adapter.display_name == "CSDN"


def test_adapter_registry_loads_zhihu():
    adapter = get_adapter("zhihu")
    assert isinstance(adapter, Adapter)
    assert adapter.platform == "zhihu"
    assert adapter.display_name == "知乎"


def test_adapter_registry_rejects_unknown_platform():
    with pytest.raises(ValueError):
        get_adapter("unknown")
