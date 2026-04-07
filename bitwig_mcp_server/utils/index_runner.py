"""
Synchronous entry points for browser indexing (e.g. MCP tool from a worker thread).
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from typing import Optional, Tuple

from bitwig_mcp_server.paths import browser_index_persistent_dir
from bitwig_mcp_server.utils.browser_indexer import build_index

logger = logging.getLogger(__name__)


def _clear_chroma(persistent_dir: str) -> None:
    chroma_dir = os.path.join(persistent_dir, "chroma")
    if os.path.isdir(chroma_dir):
        shutil.rmtree(chroma_dir)
        logger.info("Cleared existing Chroma data at %s", chroma_dir)


def run_browser_index_build_sync(
    persistent_dir: Optional[str] = None,
    clear: bool = False,
) -> Tuple[bool, str]:
    """Run a full browser index build (blocks). Intended after MCP releases UDP receive port.

    Returns:
        (success, human-readable message)
    """
    actual_dir = persistent_dir or browser_index_persistent_dir()
    os.makedirs(actual_dir, exist_ok=True)

    if clear:
        logger.warning("Clearing index (--clear) at %s", actual_dir)
        _clear_chroma(actual_dir)

    try:
        indexer = asyncio.run(build_index(persistent_dir=actual_dir, existing_controller=None))
    except Exception as e:
        logger.exception("Browser index build crashed: %s", e)
        log_hint = os.path.join(actual_dir, "indexer.log")
        return False, f"Build crashed: {e!s}. See log: {log_hint}"

    if indexer is None:
        log_hint = os.path.join(actual_dir, "indexer.log")
        return (
            False,
            "Build failed (no indexer returned). Bitwig must be open with OSC sending to "
            f"the configured receive port. See {log_hint}",
        )

    n = indexer.get_device_count()
    return True, f"Indexed {n} browser items into {actual_dir}"
