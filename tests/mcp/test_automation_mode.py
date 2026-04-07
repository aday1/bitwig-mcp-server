import pytest

from bitwig_mcp_server.mcp.tools import _normalize_automation_write_mode


def test_normalize_aliases():
    assert _normalize_automation_write_mode("latch") == "LATCH"
    assert _normalize_automation_write_mode("LATCH_PREVIEW") == "LATCH_PREVIEW"
    assert _normalize_automation_write_mode("latch preview") == "LATCH_PREVIEW"
    assert _normalize_automation_write_mode("trim_read") == "TRIM_READ"


def test_normalize_invalid():
    with pytest.raises(ValueError):
        _normalize_automation_write_mode("not_a_mode")
