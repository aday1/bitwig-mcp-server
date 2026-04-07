"""
Static installation and setup text for Bitwig MCP (no OSC required).
"""

from __future__ import annotations


def render_install_guide(topic: str) -> str:
    t = (topic or "full").strip().lower().replace("-", "_")
    if t not in (
        "full",
        "cursor",
        "bitwig_osc",
        "index",
        "dashboard",
        "troubleshoot",
    ):
        t = "full"

    sections: dict[str, str] = {
        "cursor": _CURSOR,
        "bitwig_osc": _BITWIG_OSC,
        "index": _INDEX,
        "dashboard": _DASHBOARD,
        "troubleshoot": _TROUBLESHOOT,
    }

    if t == "full":
        return "\n\n".join(
            [
                _INTRO,
                _PYTHON,
                sections["cursor"],
                sections["bitwig_osc"],
                sections["index"],
                sections["dashboard"],
                sections["troubleshoot"],
            ]
        )
    return "\n\n".join([_INTRO, sections[t]])


_INTRO = """## Bitwig MCP Server -- install overview

1. Python 3.10+ on PATH.
2. Install this package (uv recommended): in the repo root run `uv sync` or `pip install -e .`.
3. Install DrivenByMoss (or a VAday-labeled OSC build) in Bitwig and add the Open Sound Control controller.
4. Match UDP ports: MCP sends TO Bitwig on the port Bitwig listens on (often 8000); Bitwig must SEND TO the port MCP listens on (often 9000). Override with BITWIG_MCP_BITWIG_SEND_PORT and BITWIG_MCP_BITWIG_RECEIVE_PORT if needed.
5. Register the server in Cursor (or Claude Desktop) MCP settings and start Bitwig before using tools that need OSC.
6. Call MCP tool `bitwig_diagnose` to confirm `/transport/tempo` and project name are non-null after refresh."""

_PYTHON = """## Python environment

From the `bitwig-mcp-server` directory:

  uv sync

or:

  pip install -e .

Run the server manually to verify:

  python -m bitwig_mcp_server

You should see logging and no immediate crash. Stdio mode is used when launched from Cursor."""

_CURSOR = """## Cursor MCP configuration

Add a server entry (adjust paths for your machine):

Windows example:

  "bitwig": {
    "command": "python",
    "args": ["-m", "bitwig_mcp_server"],
    "cwd": "C:\\\\Users\\\\YOU\\\\Documents\\\\Bitwig Studio\\\\Extensions\\\\bitwig-mcp-server",
    "env": {
      "BITWIG_MCP_DASHBOARD": "1"
    }
  }

Use the folder that contains `pyproject.toml`. If `python` is not on PATH, use the full path to `python.exe` from your venv.

Optional env vars:

- BITWIG_MCP_BITWIG_SEND_PORT -- UDP port Bitwig listens on (default 8000)
- BITWIG_MCP_BITWIG_RECEIVE_PORT -- port this process listens on for Bitwig (default 9000)
- BITWIG_MCP_BROWSER_INDEX_DIR -- override Chroma index directory
- BITWIG_MCP_DASHBOARD=1 -- localhost reference UI (default port 3848)
- BITWIG_MCP_DASHBOARD_PORT -- dashboard TCP port"""

_BITWIG_OSC = """## Bitwig Studio controller setup

1. Install the DrivenByMoss Bitwig extension (or your VAday OSC build) per mossgrabers.de instructions.
2. Restart Bitwig.
3. Settings > Controllers > Add > choose the Open Sound Control / OSC entry (menu title may show hardware model name).
4. Set Bitwig to receive OSC on the same port MCP sends to (default 8000).
5. Set Bitwig to send OSC to 127.0.0.1 on the same port MCP listens on (default 9000).
6. Enable the controller.

If `bitwig_diagnose` shows tempo/project as None, the send-from-Bitwig side is wrong or the firewall is blocking UDP."""

_INDEX = """## Semantic browser index (optional)

Tools like `search_device_browser` need a built index.

- Prefer MCP tool `build_browser_index` from Cursor (it stops OSC briefly, runs the indexer, restarts).
- CLI: `bitwig-browser-index` with the same env ports as MCP; only one process may bind the receive port.

Large libraries take time. Use `bitwig_diagnose` to see index path and device count."""

_DASHBOARD = """## Local reference dashboard

Set BITWIG_MCP_DASHBOARD=1 in the MCP server env. Open http://127.0.0.1:3848/ for tool groups, prompts, and JSON at /api/reference and /api/events."""

_TROUBLESHOOT = """## Troubleshooting

- No OSC data: fix controller ports, confirm Bitwig controller is enabled, run `bitwig_diagnose`.
- Index build fails: ensure Bitwig is sending to MCP receive port; try `build_browser_index` from MCP.
- Parameter moves do nothing: select the correct device in Bitwig; use `navigate_device` / UI; large plugins may need parameter pages (`scan_device_pages_and_params`).
- Automation not recording: arm write, set mode (e.g. latch), play transport; use `automation_touch: true` on `set_device_parameter`."""
