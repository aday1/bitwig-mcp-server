"""
Tests for the main application module.
"""

import inspect
from unittest.mock import patch

from bitwig_mcp_server.app import main


def _close_if_coroutine(obj: object) -> None:
    """Avoid RuntimeWarning when main() builds a coroutine then mocked asyncio.run aborts."""
    if inspect.iscoroutine(obj):
        obj.close()


def test_run_server_mock():
    """Test that asyncio.run is invoked from main() with run_server's coroutine."""

    def fake_asyncio_run(coro):
        _close_if_coroutine(coro)

    with patch(
        "bitwig_mcp_server.app.asyncio.run", side_effect=fake_asyncio_run
    ) as mock_asyncio_run:
        result = main()

        mock_asyncio_run.assert_called_once()
        assert result == 0


def test_main_keyboard_interrupt():
    """Test main() handling KeyboardInterrupt."""

    def interrupt_run(coro):
        _close_if_coroutine(coro)
        raise KeyboardInterrupt

    with patch("bitwig_mcp_server.app.asyncio.run", side_effect=interrupt_run):
        result = main()
        assert result == 0


def test_main_exception():
    """Test main() handling general exceptions."""

    def error_run(coro):
        _close_if_coroutine(coro)
        raise Exception("Test error")

    with patch("bitwig_mcp_server.app.asyncio.run", side_effect=error_run):
        result = main()
        assert result == 1
