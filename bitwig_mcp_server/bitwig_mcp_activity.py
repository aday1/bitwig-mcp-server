"""
Live activity log + optional localhost web dashboard for Bitwig MCP.

Env:
  BITWIG_MCP_DASHBOARD       1/true to start http://127.0.0.1:<port>/ (default off)
  BITWIG_MCP_DASHBOARD_PORT  port (default 3848)

HTTP:
  GET /                  Reference + live activity UI
  GET /api/events        JSON tail of MCP tool events
  GET /api/reference     JSON tool groups, flat tool list, sample prompts
"""

from __future__ import annotations

import html
import json
import os
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

_MAX_DEQUE = 400
_MAX_ARG_JSON = 1200
_MAX_RESULT_JSON = 2500

_lock = threading.Lock()
_events: deque[dict[str, Any]] = deque(maxlen=_MAX_DEQUE)
_log_file: Path | None = None
_server_started = False
_server_lock = threading.Lock()


def _dashboard_enabled() -> bool:
    v = os.getenv("BITWIG_MCP_DASHBOARD", "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _log_dir() -> Path:
    base = os.getenv("BITWIG_MCP_LOG_DIR")
    if base:
        return Path(base)
    if os.name == "nt":
        return Path(os.getenv("LOCALAPPDATA", "")) / "bitwig-mcp"
    return Path.home() / ".local" / "share" / "bitwig-mcp"


def _ensure_log_path() -> Path:
    global _log_file
    if _log_file is None:
        d = _log_dir()
        d.mkdir(parents=True, exist_ok=True)
        _log_file = d / "activity.jsonl"
    return _log_file


def _truncate(obj: Any, limit: int) -> str:
    try:
        s = json.dumps(obj, default=str)
    except TypeError:
        s = repr(obj)
    if len(s) > limit:
        return s[: limit - 3] + "..."
    return s


def _push(event: dict[str, Any]) -> None:
    event["t"] = datetime.now(timezone.utc).isoformat()
    with _lock:
        _events.append(event)
    if _dashboard_enabled():
        try:
            path = _ensure_log_path()
            line = json.dumps(event, default=str) + "\n"
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
        except OSError:
            pass


def log_tool_start(name: str, arguments: dict[str, Any]) -> str:
    rid = str(uuid.uuid4())[:8]
    _push(
        {
            "kind": "tool_start",
            "id": rid,
            "name": name,
            "args": _truncate(arguments, _MAX_ARG_JSON),
        }
    )
    return rid


def log_tool_end(
    rid: str,
    name: str,
    ok: bool,
    elapsed_s: float,
    result: Any = None,
    error: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        "kind": "tool_end",
        "id": rid,
        "name": name,
        "ok": ok,
        "ms": round(elapsed_s * 1000, 2),
    }
    if error:
        payload["error"] = error[:800]
    elif result is not None:
        payload["result"] = _truncate(result, _MAX_RESULT_JSON)
    _push(payload)


def get_events_tail(n: int = 200) -> list[dict[str, Any]]:
    with _lock:
        return list(_events)[-n:]


def _categorize_tool(name: str) -> str:
    if name.startswith(
        ("search_device", "recommend_devices", "get_device_", "build_browser")
    ):
        return "Browser and discovery"
    if name in ("bitwig_diagnose", "get_bitwig_mcp_install_guide"):
        return "Diagnostics"
    if name.startswith(("transport_", "set_tempo", "set_playhead", "start_arranger")):
        return "Transport"
    if name.startswith(
        (
            "add_",
            "select_track",
            "navigate_track",
            "toggle_track_bank",
            "set_track_",
            "duplicate_track",
            "remove_track",
            "set_layout",
        )
    ):
        return "Tracks and layout"
    if name.startswith(("toggle_mixer", "set_track_send", "set_project_remote")):
        return "Sends and project remotes"
    if name in (
        "open_track_device_browser",
        "assign_track_instrument",
        "apply_modulation_controls",
        "insert_poly_grid_on_track",
        "song_enhance_mix",
    ):
        return "High-level workflows"
    if name.startswith("send_midi") or name.startswith("set_vkb") or name == "play_midi_note_sequence":
        return "MIDI virtual keyboard"
    if name.startswith("launcher_") or name.startswith("clips_") or name.startswith("prepare_launcher"):
        return "Clip launcher"
    if name.startswith("clip_") or name.startswith("insert_seed") or name.startswith("toggle_arranger_clip"):
        return "Clips arranger"
    if name.startswith("toggle_") and (
        "overdub" in name or "automation" in name
    ):
        return "Overdub and automation arm"
    if name in (
        "set_automation_write_mode",
        "arranger_automation_sweep_session",
    ):
        return "Automation modes and sweeps"
    if name.startswith("scene_"):
        return "Scenes"
    if name.startswith("device_browser") or name.startswith("preset_browser"):
        return "Browser workflows"
    if name.startswith(("browse_", "commit_browser", "cancel_browser", "navigate_browser")):
        return "In-app browser navigation"
    if (
        name.startswith("set_device_")
        or name.startswith("navigate_device")
        or name.startswith("select_device")
        or name.startswith("scan_device")
        or name.startswith("warmup_device")
        or "last_touched_device" in name
        or name.startswith("enter_device")
        or name.startswith("exit_device")
        or name == "toggle_device_bypass"
        or name == "toggle_device_window"
        or name == "navigate_device"
        or name == "set_track_remote_parameter"
    ):
        return "Device parameters and chain"
    return "Other"


def _tool_groups_from_registry() -> dict[str, list[str]]:
    from bitwig_mcp_server.mcp.tools import get_bitwig_tools

    names = sorted(t.name for t in get_bitwig_tools())
    groups: dict[str, list[str]] = {}
    for n in names:
        cat = _categorize_tool(n)
        groups.setdefault(cat, []).append(n)
    return dict(sorted(groups.items(), key=lambda x: x[0].lower()))


SAMPLE_PROMPTS: list[tuple[str, str]] = [
    (
        "Install from zero",
        "Call get_bitwig_mcp_install_guide with topic full and paste the result into a note. "
        "Then walk the user through only the Bitwig OSC controller section for their OS.",
    ),
    (
        "Cursor MCP JSON for Bitwig",
        "Call get_bitwig_mcp_install_guide with topic cursor. Produce a ready-to-paste Cursor MCP "
        "server block using the user's actual path to bitwig-mcp-server and python or venv python.",
    ),
    (
        "OSC sanity check",
        "Call bitwig_diagnose and summarize send/receive ports and whether Bitwig is replying. "
        "If receive is dead, tell me exactly how to add the VAday/DrivenByMoss OSC controller in Bitwig.",
    ),
    (
        "EDM starter (four-on-the-floor)",
        "Using Bitwig MCP: set_tempo to 124, add_instrument_track and add_audio_track named Kick and Bass. "
        "select_track 1, open_track_device_browser after, then use device_browser_workflow or describe manual "
        "browser steps to load Drum Machine or a kick. prepare_launcher_clip_slot track 1 slot 1, "
        "launcher_clip_create with length_beats 4, transport_play true.",
    ),
    (
        "Breakcore energy",
        "set_tempo to 175. add_instrument_track for Amen-style chops. Use insert_poly_grid_on_track or "
        "assign_track_instrument for Sampler. Explain using launcher_clip_create with short loop lengths "
        "and clip_quantize_selected after recording.",
    ),
    (
        "Glitch and FX movement",
        "select_track 1, navigate_device next until a delay or distortion is selected (use scan_device_pages_and_params "
        "if needed). Enable arranger automation: toggle_arranger_automation_write, set_automation_write_mode latch. "
        "Use set_device_parameter with automation_touch true to sweep filter or wet/dry on params 1-8 while transport plays, "
        "or arranger_automation_sweep_session with device_params and start_playback true.",
    ),
    (
        "Read what the device sees",
        "Call scan_device_pages_and_params with max_bank_steps 4 and summarize parameter names on the first page "
        "that has real names.",
    ),
]


def reference_payload() -> dict[str, Any]:
    from bitwig_mcp_server.mcp.install_help import render_install_guide

    groups = _tool_groups_from_registry()
    flat: list[str] = []
    for _k, lst in sorted(groups.items(), key=lambda x: x[0].lower()):
        flat.extend(lst)
    return {
        "tool_count": len(flat),
        "tool_groups": groups,
        "tools_flat": sorted(set(flat)),
        "sample_prompts": [{"title": a, "prompt": b} for a, b in SAMPLE_PROMPTS],
        "install_guide_tool": "get_bitwig_mcp_install_guide",
        "install_topics": [
            "full",
            "cursor",
            "bitwig_osc",
            "index",
            "dashboard",
            "troubleshoot",
        ],
        "install_summary": render_install_guide("full")[:1200] + "\n\n[truncated; call get_bitwig_mcp_install_guide]",
        "osc_defaults": {
            "send_to_bitwig": "127.0.0.1:8000 (BITWIG_MCP_BITWIG_SEND_PORT)",
            "listen_from_bitwig": "127.0.0.1:9000 (BITWIG_MCP_BITWIG_RECEIVE_PORT)",
        },
        "fx_automation_note": (
            "Device parameter moves use OSC /device/param/N/value. For recorded automation, use automation_touch=true "
            "(sends .../touched) with arranger automation write armed and transport playing."
        ),
    }


def _render_tool_groups_html(groups: dict[str, list[str]]) -> str:
    blocks: list[str] = []
    for title in sorted(groups.keys(), key=str.lower):
        names = groups[title]
        lis = "".join(f"<li><code>{html.escape(n)}</code></li>" for n in names)
        blocks.append(
            f'<details class="ref-details"><summary>{html.escape(title)} '
            f'<span class="ct">({len(names)})</span></summary><ul class="tool-ul">{lis}</ul></details>'
        )
    return "\n".join(blocks)


def _render_prompts_html() -> str:
    parts: list[str] = []
    for i, (title, text) in enumerate(SAMPLE_PROMPTS):
        tid = f"p{i}"
        esc_t = html.escape(title)
        esc_p = html.escape(text)
        parts.append(
            f'<div class="prompt-card"><h4>{esc_t}</h4>'
            f'<pre class="prompt-pre" id="{tid}">{esc_p}</pre>'
            f'<button type="button" class="btn" data-copy="{tid}">Copy prompt</button></div>'
        )
    return "\n".join(parts)


def build_dashboard_html() -> str:
    groups = _tool_groups_from_registry()
    nt = sum(len(v) for v in groups.values())
    tools_html = _render_tool_groups_html(groups)
    prompts_html = _render_prompts_html()
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Bitwig MCP</title>
  <style>
    :root {{ --bg:#0f1419; --fg:#c8d0d8; --muted:#6b7a88; --acc:#22c55e; --ok:#5cb85c; --err:#d9534f; --card:#151b24; }}
    * {{ box-sizing: border-box; }}
    body {{ font-family: system-ui, Segoe UI, sans-serif; background: var(--bg); color: var(--fg); margin: 0; padding: 0; font-size: 14px; line-height: 1.45; }}
    code, pre {{ font-family: ui-monospace, Consolas, monospace; font-size: 12px; }}
    header {{ padding: 14px 18px; border-bottom: 1px solid #2a3440; background: #0a0e12; }}
    h1 {{ font-size: 1.15rem; font-weight: 600; margin: 0 0 4px 0; color: var(--acc); }}
    .tagline {{ color: var(--muted); font-size: 12px; max-width: 960px; }}
    nav {{ display: flex; gap: 8px; flex-wrap: wrap; padding: 10px 18px; background: #0d1118; border-bottom: 1px solid #2a3440; }}
    nav button {{ background: #1e2836; color: var(--fg); border: 1px solid #334155; padding: 6px 14px; border-radius: 6px; cursor: pointer; font-size: 13px; }}
    nav button.on {{ background: var(--acc); color: #0a0e12; border-color: var(--acc); font-weight: 600; }}
    section.panel {{ display: none; padding: 16px 18px 28px; max-width: 1100px; }}
    section.panel.on {{ display: block; }}
    h2 {{ font-size: 1rem; color: #e6edf3; margin: 18px 0 8px 0; }}
    h2:first-child {{ margin-top: 0; }}
    .callout {{ background: var(--card); border: 1px solid #2a3440; border-radius: 8px; padding: 12px 14px; margin: 10px 0; font-size: 13px; }}
    .callout strong {{ color: #86efac; }}
    ul.bullets {{ margin: 8px 0; padding-left: 1.2rem; color: #b8c4d0; }}
    .ref-details {{ margin: 6px 0; border: 1px solid #2a3440; border-radius: 6px; background: #0a0e12; }}
    .ref-details summary {{ cursor: pointer; padding: 8px 12px; font-weight: 600; color: #e6edf3; }}
    .ref-details summary:hover {{ background: #151b24; }}
    .ref-details .ct {{ color: var(--muted); font-weight: 400; }}
    ul.tool-ul {{ margin: 0; padding: 8px 12px 12px 28px; columns: 2; column-gap: 24px; }}
    @media (max-width: 720px) {{ ul.tool-ul {{ columns: 1; }} }}
    ul.tool-ul li {{ margin: 2px 0; }}
    .prompt-card {{ background: var(--card); border: 1px solid #2a3440; border-radius: 8px; padding: 12px 14px; margin: 12px 0; }}
    .prompt-card h4 {{ margin: 0 0 8px 0; font-size: 13px; color: var(--acc); }}
    .prompt-pre {{ white-space: pre-wrap; word-break: break-word; margin: 0 0 10px 0; color: #b8c4d0; max-height: 160px; overflow-y: auto; }}
    .btn {{ background: #16a34a; color: #fff; border: none; padding: 5px 12px; border-radius: 5px; cursor: pointer; font-size: 12px; }}
    .btn:hover {{ background: #15803d; }}
    #log {{ white-space: pre-wrap; word-break: break-word; line-height: 1.45; max-height: calc(100vh - 220px); overflow-y: auto; border: 1px solid #2a3440; border-radius: 6px; padding: 10px; background: #0a0e12; font-family: ui-monospace, Consolas, monospace; font-size: 12px; }}
    .row {{ margin-bottom: 6px; border-left: 3px solid #2a3440; padding-left: 8px; }}
    .row.tool_start {{ border-left-color: var(--acc); }}
    .row.tool_end {{ border-left-color: var(--muted); }}
    .row.tool_end.ok {{ border-left-color: var(--ok); }}
    .row.tool_end.fail {{ border-left-color: var(--err); }}
    .ts {{ color: var(--muted); }}
    .name {{ color: #e6edf3; font-weight: 600; }}
    .pill {{ display: inline-block; padding: 0 6px; border-radius: 4px; background: #1e2836; font-size: 11px; margin-right: 6px; }}
  </style>
</head>
<body>
  <header>
    <h1>Bitwig MCP dashboard</h1>
    <p class="tagline">Reference, OSC/automation notes, and copy-paste prompts. Live tab polls tool calls. JSON endpoints: <code>/api/reference</code>, <code>/api/events</code>. Enable with <code>BITWIG_MCP_DASHBOARD=1</code>.</p>
  </header>
  <nav>
    <button type="button" id="tab-ref" class="on">Reference</button>
    <button type="button" id="tab-log">Live activity</button>
  </nav>

  <section id="panel-ref" class="panel on">
    <div class="callout">
      <strong>Install.</strong> MCP tool <code>get_bitwig_mcp_install_guide</code> (topics: full, cursor, bitwig_osc, index, dashboard, troubleshoot) works without Bitwig running. After OSC works, call <code>bitwig_diagnose</code>.
    </div>
    <div class="callout">
      <strong>FX parameter movement.</strong> OSC addresses the <em>selected</em> device&rsquo;s parameter bank. Use <code>navigate_device</code>, <code>scan_device_pages_and_params</code>, or the Bitwig UI to select the right FX. For automation recording, arm write, use <code>set_automation_write_mode</code> (e.g. latch), play transport, and call <code>set_device_parameter</code> with <code>automation_touch: true</code> (default) so Bitwig receives <code>/device/param/N/touched</code> around value changes.
    </div>

    <h2>OSC ports (defaults)</h2>
    <ul class="bullets">
      <li>UDP to Bitwig: 127.0.0.1:8000 (<code>BITWIG_MCP_BITWIG_SEND_PORT</code>)</li>
      <li>UDP from Bitwig: 127.0.0.1:9000 (<code>BITWIG_MCP_BITWIG_RECEIVE_PORT</code>)</li>
      <li>Add the DrivenByMoss / VAday Open Sound Control controller in Bitwig; receive port must match MCP.</li>
    </ul>

    <h2>MCP tools ({nt})</h2>
    <p class="tagline" style="margin-bottom:10px">Grouped heuristically from the live tool registry.</p>
    {tools_html}

    <h2>Starter prompts</h2>
    <p class="tagline">Copy into Cursor with the Bitwig MCP enabled.</p>
    {prompts_html}
  </section>

  <section id="panel-log" class="panel">
    <p class="tagline" style="margin-bottom:10px">Polling <code>/api/events</code> every 400ms.</p>
    <div id="log"></div>
  </section>

  <script>
    const logEl = document.getElementById('log');
    let lastStamp = '';
    document.getElementById('tab-ref').onclick = function() {{
      document.getElementById('tab-ref').classList.add('on');
      document.getElementById('tab-log').classList.remove('on');
      document.getElementById('panel-ref').classList.add('on');
      document.getElementById('panel-log').classList.remove('on');
    }};
    document.getElementById('tab-log').onclick = function() {{
      document.getElementById('tab-log').classList.add('on');
      document.getElementById('tab-ref').classList.remove('on');
      document.getElementById('panel-log').classList.add('on');
      document.getElementById('panel-ref').classList.remove('on');
    }};
    document.querySelectorAll('[data-copy]').forEach(function(btn) {{
      btn.onclick = function() {{
        const id = btn.getAttribute('data-copy');
        const el = document.getElementById(id);
        if (el) navigator.clipboard.writeText(el.textContent || '');
      }};
    }});
    function esc(s) {{
      const d = document.createElement('div');
      d.textContent = s;
      return d.innerHTML;
    }}
    function render(ev) {{
      const k = ev.kind || '';
      let cls = 'row ' + k;
      if (k === 'tool_end') cls += ev.ok ? ' ok' : ' fail';
      let line = '<span class="ts">' + esc(ev.t || '') + '</span> ';
      line += '<span class="pill">' + esc(k) + '</span>';
      if (ev.name) line += '<span class="name">' + esc(ev.name) + '</span> ';
      if (ev.id) line += '<span class="pill">id:' + esc(ev.id) + '</span> ';
      if (ev.ms != null) line += '<span class="pill">' + esc(String(ev.ms)) + ' ms</span> ';
      if (ev.args) line += '\\n  args: ' + esc(typeof ev.args === 'string' ? ev.args : JSON.stringify(ev.args));
      if (ev.result) line += '\\n  out: ' + esc(typeof ev.result === 'string' ? ev.result : JSON.stringify(ev.result));
      if (ev.error) line += '\\n  <span style="color:#f88">' + esc(ev.error) + '</span>';
      return '<div class="' + cls + '">' + line + '</div>';
    }}
    async function poll() {{
      try {{
        const r = await fetch('/api/events');
        const data = await r.json();
        if (!data.events || !data.events.length) return;
        const tail = data.events.slice(-12);
        const stamp = data.events.length + '|' + tail.map(function(e) {{
          return (e.t||'') + '\\t' + (e.kind||'') + '\\t' + (e.id||'') + '\\t' + (e.name||'');
        }}).join('\\n');
        if (stamp === lastStamp) return;
        lastStamp = stamp;
        logEl.innerHTML = data.events.map(render).join('');
        logEl.scrollTop = logEl.scrollHeight;
      }} catch (e) {{}}
    }}
    setInterval(poll, 400);
    poll();
  </script>
</body>
</html>
"""


_INDEX_HTML: str | None = None


def _get_index_html() -> str:
    global _INDEX_HTML
    if _INDEX_HTML is None:
        _INDEX_HTML = build_dashboard_html()
    return _INDEX_HTML


class _DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        if self.path == "/" or self.path.startswith("/?"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(_get_index_html().encode("utf-8"))
        elif self.path.startswith("/api/events"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            body = json.dumps({"events": get_events_tail(300)}, default=str)
            self.wfile.write(body.encode("utf-8"))
        elif self.path.startswith("/api/reference"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(json.dumps(reference_payload(), indent=2).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()


def start_dashboard_background() -> None:
    global _server_started
    if not _dashboard_enabled():
        return
    with _server_lock:
        if _server_started:
            return
        base = int(os.getenv("BITWIG_MCP_DASHBOARD_PORT", "3848"))
        httpd: HTTPServer | None = None
        chosen = base
        for i in range(12):
            try:
                chosen = base + i
                httpd = HTTPServer(("127.0.0.1", chosen), _DashboardHandler)
                break
            except OSError:
                continue
        if httpd is None:
            return

        def run() -> None:
            httpd.serve_forever()

        t = threading.Thread(target=run, name="bitwig-mcp-dashboard", daemon=True)
        t.start()
        _server_started = True
        _push(
            {
                "kind": "meta",
                "message": f"dashboard http://127.0.0.1:{chosen}/",
            }
        )


def maybe_autostart_dashboard() -> None:
    try:
        start_dashboard_background()
    except Exception:
        pass
