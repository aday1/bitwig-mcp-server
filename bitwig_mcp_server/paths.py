"""
Canonical filesystem paths for bitwig-mcp-server.

Keep index location in one place so CLI indexer and MCP tools agree.
"""

from __future__ import annotations

import os
from pathlib import Path


def browser_index_persistent_dir() -> str:
    """Directory for Chroma browser device index (same default as indexer CLI).

    Override with env BITWIG_MCP_BROWSER_INDEX_DIR (absolute or ~ path).
    """
    override = os.environ.get("BITWIG_MCP_BROWSER_INDEX_DIR", "").strip()
    if override:
        return str(Path(override).expanduser().resolve())
    package_root = Path(__file__).resolve().parent.parent
    return str((package_root / "data" / "browser_index").resolve())
