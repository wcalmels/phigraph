import pytest

from phigraph.local import ToolRegistry


def test_tool_registry_requires_write_approval():
    registry = ToolRegistry()
    registry.register("read", "read", lambda value: value)
    registry.register("write", "write", lambda value: value, write_action=True)
    assert registry.call("read", {"value": 4}) == 4
    with pytest.raises(PermissionError):
        registry.call("write", {"value": 4})
    assert registry.call("write", {"value": 4}, approve_write=True) == 4
