"""
Local web monitor for Bitwig MCP activity.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import uuid
from collections import deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Deque, Dict, Optional

logger = logging.getLogger(__name__)


class MCPMonitor:
    """Thread-safe state + lightweight HTTP dashboard."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8765) -> None:
        self.host = host
        self.port = port
        self.started_at = time.time()
        self.current_stage = "idle"
        self.last_error: Optional[str] = None
        self.plan_summary: str = ""
        self.plan_total_calls: Optional[int] = None
        self.completed_calls = 0
        self.failed_calls = 0
        self.last_call_summary = "none"
        self.active_calls: Dict[str, Dict[str, Any]] = {}
        self.events: Deque[Dict[str, Any]] = deque(maxlen=300)
        self.tool_counts: Dict[str, int] = {}
        self.recent_values: Deque[Dict[str, Any]] = deque(maxlen=160)
        self.understanding_notes: Deque[str] = deque(maxlen=80)
        self.instrument_params: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self.focused_device_name: str = "Focused Device"
        self.live_overview: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._httpd is not None:
            return
        self._httpd = ThreadingHTTPServer((self.host, self.port), _build_handler(self))
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, name="mcp-monitor", daemon=True
        )
        self._thread.start()
        logger.info("MCP monitor running at http://%s:%s", self.host, self.port)

    def stop(self) -> None:
        if self._httpd is None:
            return
        self._httpd.shutdown()
        self._httpd.server_close()
        self._httpd = None
        if self._thread is not None:
            self._thread.join(timeout=1.5)
            self._thread = None

    def set_stage(self, stage: str) -> None:
        stage_text = (stage or "").strip() or "idle"
        with self._lock:
            self.current_stage = stage_text
            self.events.appendleft(
                {
                    "ts": time.time(),
                    "type": "stage",
                    "status": "ok",
                    "message": stage_text,
                }
            )

    def set_plan(self, total_calls: Optional[int], summary: str) -> None:
        with self._lock:
            self.plan_total_calls = total_calls if total_calls and total_calls > 0 else None
            self.plan_summary = (summary or "").strip()
            self.events.appendleft(
                {
                    "ts": time.time(),
                    "type": "plan",
                    "status": "ok",
                    "message": self.plan_summary or "plan updated",
                }
            )

    def reset_progress(self) -> None:
        with self._lock:
            self.completed_calls = 0
            self.failed_calls = 0
            self.last_call_summary = "none"
            self.active_calls.clear()
            self.tool_counts.clear()
            self.recent_values.clear()
            self.understanding_notes.clear()
            self.instrument_params.clear()
            self.focused_device_name = "Focused Device"
            self.live_overview = {}
            self.events.appendleft(
                {
                    "ts": time.time(),
                    "type": "system",
                    "status": "ok",
                    "message": "progress reset",
                }
            )

    def set_live_overview(self, overview: Dict[str, Any]) -> None:
        with self._lock:
            self.live_overview = dict(overview or {})

    def begin_call(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        call_id = str(uuid.uuid4())
        now = time.time()
        with self._lock:
            self.active_calls[call_id] = {
                "tool": tool_name,
                "arguments": arguments,
                "started_at": now,
            }
            self.events.appendleft(
                {
                    "ts": now,
                    "type": "tool",
                    "tool": tool_name,
                    "status": "running",
                    "message": "started",
                }
            )
        return call_id

    def end_call(
        self, call_id: str, status: str, result_summary: Optional[str] = None
    ) -> None:
        now = time.time()
        with self._lock:
            call = self.active_calls.pop(call_id, None)
            if call is None:
                return
            duration_ms = int((now - call["started_at"]) * 1000)
            event = {
                "ts": now,
                "type": "tool",
                "tool": call["tool"],
                "status": status,
                "duration_ms": duration_ms,
            }
            if result_summary:
                event["message"] = result_summary[:300]
            self.events.appendleft(event)
            self.completed_calls += 1
            self.last_call_summary = (
                f"{call['tool']} ({status}, {duration_ms}ms)"
                + (f": {result_summary[:120]}" if result_summary else "")
            )
            self._ingest_understanding(
                call["tool"], call.get("arguments", {}), status, duration_ms, result_summary
            )
            if status == "error":
                self.failed_calls += 1
                self.last_error = result_summary or "unknown error"

    def _ingest_understanding(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        status: str,
        duration_ms: int,
        result_summary: Optional[str],
    ) -> None:
        now = time.time()
        self.tool_counts[tool_name] = self.tool_counts.get(tool_name, 0) + 1

        def mark_param(
            instrument: str,
            param_name: str,
            *,
            value: Optional[float] = None,
            changed: bool = False,
            available: bool = False,
            controlled: bool = False,
            source: str = "",
        ) -> None:
            inst = (instrument or "Unknown").strip()[:80]
            pname = (param_name or "Unnamed").strip()[:120]
            inst_bucket = self.instrument_params.setdefault(inst, {})
            entry = inst_bucket.setdefault(
                pname,
                {
                    "seen_count": 0,
                    "changed_count": 0,
                    "available_count": 0,
                    "controlled_count": 0,
                    "last_value": None,
                    "last_source": "",
                    "updated_at": now,
                },
            )
            entry["seen_count"] += 1
            if changed:
                entry["changed_count"] += 1
            if available:
                entry["available_count"] += 1
            if controlled or changed:
                entry["controlled_count"] += 1
            if value is not None:
                entry["last_value"] = round(float(value), 3)
            entry["last_source"] = source[:24]
            entry["updated_at"] = now

        def add_value(label: str, value: Any, source: str) -> None:
            if isinstance(value, bool):
                numeric = 1.0 if value else 0.0
            elif isinstance(value, (int, float)):
                numeric = float(value)
            else:
                return
            self.recent_values.appendleft(
                {
                    "ts": now,
                    "label": label[:40],
                    "value": round(numeric, 3),
                    "source": source[:24],
                }
            )

        def walk(prefix: str, value: Any) -> None:
            if isinstance(value, dict):
                for k, v in value.items():
                    key = f"{prefix}.{k}" if prefix else str(k)
                    walk(key, v)
            elif isinstance(value, list):
                for i, v in enumerate(value):
                    walk(f"{prefix}[{i}]", v)
            else:
                lprefix = prefix.lower()
                if any(x in lprefix for x in ("value", "param", "tempo", "amount", "level")):
                    add_value(prefix, value, "arg")

        walk("", arguments or {})

        if result_summary:
            first_line = result_summary.splitlines()[0].strip()
            if first_line:
                self.understanding_notes.appendleft(
                    f"{tool_name}: {first_line[:220]}"
                )
            for m in re.finditer(
                r"Track\s+(\d+)\s+remote\s+(\d+)\s+set to\s+([0-9]+(?:\.[0-9]+)?)",
                result_summary,
                flags=re.IGNORECASE,
            ):
                add_value(f"track{m.group(1)}.remote{m.group(2)}", float(m.group(3)), "result")
                mark_param(
                    f"Track {m.group(1)}",
                    f"Remote {m.group(2)}",
                    value=float(m.group(3)),
                    changed=True,
                    controlled=True,
                    source="result",
                )
            for m in re.finditer(
                r"Project remote\s+(\d+)\s*->\s*([0-9]+(?:\.[0-9]+)?)",
                result_summary,
                flags=re.IGNORECASE,
            ):
                add_value(f"project.remote{m.group(1)}", float(m.group(2)), "result")
                mark_param(
                    "Project",
                    f"Remote {m.group(1)}",
                    value=float(m.group(2)),
                    changed=True,
                    controlled=True,
                    source="result",
                )
            for m in re.finditer(
                r"Set page slot\s+(\d+).*?param\s+(\d+).*?\s+to\s+([0-9]+(?:\.[0-9]+)?)",
                result_summary,
                flags=re.IGNORECASE,
            ):
                add_value(f"page{m.group(1)}.param{m.group(2)}", float(m.group(3)), "result")
                mark_param(
                    self.focused_device_name,
                    f"Page {m.group(1)} Param {m.group(2)}",
                    value=float(m.group(3)),
                    changed=True,
                    controlled=True,
                    source="result",
                )
            for m in re.finditer(
                r"value=([0-9]+(?:\.[0-9]+)?)",
                result_summary,
                flags=re.IGNORECASE,
            ):
                add_value("last_touched.value", float(m.group(1)), "result")
                mark_param(
                    self.focused_device_name,
                    "Last Touched",
                    value=float(m.group(1)),
                    changed=False,
                    source="result",
                )
            for m in re.finditer(
                r"Active Device:\s*(.+)",
                result_summary,
                flags=re.IGNORECASE,
            ):
                name = m.group(1).strip()
                if name:
                    self.focused_device_name = name[:80]
            page_context = ""
            for line in result_summary.splitlines():
                p = re.match(r"-\s+bank\s+\d+\s+slot\s+(\d+)\s+page='([^']*)'", line)
                if p:
                    slot = p.group(1)
                    page = p.group(2).strip() or f"Page {slot}"
                    page_context = page
                    mark_param(
                        self.focused_device_name,
                        page_context,
                        available=True,
                        changed=False,
                        source="scan",
                    )
                    continue
                q = re.match(
                    r"\s+(\d+):\s*(.*?)\s+exists=(true|false)\s+available=(true|false)\s+value=([0-9]+(?:\.[0-9]+)?)",
                    line,
                    flags=re.IGNORECASE,
                )
                if q:
                    idx = q.group(1)
                    raw_name = q.group(2).strip()
                    exists_flag = q.group(3).lower() == "true"
                    avail_flag = q.group(4).lower() == "true"
                    value_num = float(q.group(5))
                    pname = raw_name or f"{page_context or 'Page'} Param {idx}"
                    mark_param(
                        self.focused_device_name,
                        pname,
                        value=value_num,
                        available=exists_flag or avail_flag,
                        changed=False,
                        source="scan",
                    )
                    continue
                q_old = re.match(
                    r"\s+(\d+):\s*(.*?)\s+value=([0-9]+(?:\.[0-9]+)?)",
                    line,
                )
                if q_old:
                    idx = q_old.group(1)
                    raw_name = q_old.group(2).strip()
                    value_num = float(q_old.group(3))
                    pname = raw_name or f"{page_context or 'Page'} Param {idx}"
                    mark_param(
                        self.focused_device_name,
                        pname,
                        value=value_num,
                        available=True,
                        changed=False,
                        source="scan",
                    )
        else:
            self.understanding_notes.appendleft(
                f"{tool_name}: {status} ({duration_ms}ms)"
            )

        if tool_name == "apply_modulation_controls":
            for row in (arguments or {}).get("device_params", []) or []:
                pi = row.get("param_index")
                val = row.get("value")
                if isinstance(pi, int):
                    mark_param(
                        self.focused_device_name,
                        f"Param {pi}",
                        value=float(val) if isinstance(val, (int, float)) else None,
                        changed=True,
                        available=True,
                        controlled=True,
                        source="arg",
                    )
            for row in (arguments or {}).get("project_remotes", []) or []:
                pi = row.get("param_index")
                val = row.get("value")
                if isinstance(pi, int):
                    mark_param(
                        "Project",
                        f"Remote {pi}",
                        value=float(val) if isinstance(val, (int, float)) else None,
                        changed=True,
                        controlled=True,
                        source="arg",
                    )
        if tool_name == "set_track_remote_parameter":
            ti = (arguments or {}).get("track_index")
            pi = (arguments or {}).get("param_index")
            val = (arguments or {}).get("value")
            if isinstance(ti, int) and isinstance(pi, int):
                mark_param(
                    f"Track {ti}",
                    f"Remote {pi}",
                    value=float(val) if isinstance(val, (int, float)) else None,
                    changed=True,
                    controlled=True,
                    source="arg",
                )
        if tool_name == "set_device_parameter_on_page":
            ps = (arguments or {}).get("page_slot")
            pi = (arguments or {}).get("param_index")
            val = (arguments or {}).get("value")
            if isinstance(ps, int) and isinstance(pi, int):
                mark_param(
                    self.focused_device_name,
                    f"Page {ps} Param {pi}",
                    value=float(val) if isinstance(val, (int, float)) else None,
                    changed=True,
                    available=True,
                    controlled=True,
                    source="arg",
                )
                # Also mark nearby params as seen/read-only to provide blue contrast rows.
                for sibling in (1, 2, 3, 4):
                    if sibling == pi:
                        continue
                    mark_param(
                        self.focused_device_name,
                        f"Page {ps} Param {sibling}",
                        available=True,
                        changed=False,
                        source="seen",
                    )
        if tool_name == "warmup_device_parameter_map":
            p0 = (arguments or {}).get("param_probe_start", 1)
            p1 = (arguments or {}).get("param_probe_end", 8)
            slots = (arguments or {}).get("page_slots_per_bank", 8)
            try:
                p_start = int(p0)
                p_end = int(p1)
                max_slots = int(slots)
            except Exception:
                p_start, p_end, max_slots = 1, 8, 8
            if p_end < p_start:
                p_start, p_end = p_end, p_start
            p_start = max(1, min(512, p_start))
            p_end = max(1, min(512, p_end))
            max_slots = max(1, min(64, max_slots))
            for ps in range(1, max_slots + 1):
                for pi in range(p_start, p_end + 1):
                    mark_param(
                        self.focused_device_name,
                        f"Page {ps} Param {pi}",
                        available=True,
                        changed=False,
                        controlled=True,
                        source="warmup",
                    )

    def status_snapshot(self, osc_status: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        with self._lock:
            active = list(self.active_calls.values())
            events = list(self.events)[:100]
            stage = self.current_stage
            last_error = self.last_error
            plan_summary = self.plan_summary
            plan_total_calls = self.plan_total_calls
            completed_calls = self.completed_calls
            failed_calls = self.failed_calls
            last_call_summary = self.last_call_summary
            tool_counts = dict(self.tool_counts)
            recent_values = list(self.recent_values)[:80]
            understanding_notes = list(self.understanding_notes)[:40]
            instrument_params = {
                inst: {
                    pname: dict(pv)
                    for pname, pv in sorted(
                        params.items(),
                        key=lambda x: (
                            -(x[1].get("controlled_count", 0)),
                            -(x[1].get("changed_count", 0)),
                            -(x[1].get("available_count", 0)),
                            -(x[1].get("seen_count", 0)),
                            x[0].lower(),
                        ),
                    )[:300]
                }
                for inst, params in sorted(self.instrument_params.items(), key=lambda x: x[0].lower())
            }
            live_overview = dict(self.live_overview)
        remaining_calls: Optional[int] = None
        progress_percent: Optional[float] = None
        if plan_total_calls is not None:
            remaining_calls = max(0, plan_total_calls - completed_calls)
            progress_percent = round(
                min(100.0, (completed_calls / max(1, plan_total_calls)) * 100.0), 1
            )
        return {
            "started_at": self.started_at,
            "uptime_sec": int(time.time() - self.started_at),
            "stage": stage,
            "plan_summary": plan_summary,
            "plan_total_calls": plan_total_calls,
            "completed_calls": completed_calls,
            "failed_calls": failed_calls,
            "remaining_calls": remaining_calls,
            "progress_percent": progress_percent,
            "last_call_summary": last_call_summary,
            "active_calls": active,
            "recent_events": events,
            "last_error": last_error,
            "osc_status": osc_status or {},
            "understanding": {
                "tool_counts": tool_counts,
                "recent_values": recent_values,
                "notes": understanding_notes,
                "instrument_params": instrument_params,
            },
            "live_overview": live_overview,
        }


def _build_handler(monitor: MCPMonitor):
    class Handler(BaseHTTPRequestHandler):
        def _send_json(self, payload: Dict[str, Any], status: int = 200) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json_body(self) -> Dict[str, Any]:
            raw_len = self.headers.get("Content-Length", "0")
            try:
                length = int(raw_len)
            except ValueError:
                return {}
            if length <= 0:
                return {}
            body = self.rfile.read(length).decode("utf-8", errors="ignore")
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                return {}
            return data if isinstance(data, dict) else {}

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/":
                html = _monitor_html().encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html)))
                self.end_headers()
                self.wfile.write(html)
                return
            if self.path == "/api/status":
                self._send_json(monitor.status_snapshot())
                return
            self._send_json({"error": "not found"}, status=404)

        def do_POST(self) -> None:  # noqa: N802
            if self.path == "/api/stage":
                payload = self._read_json_body()
                monitor.set_stage(str(payload.get("stage", "")))
                self._send_json({"ok": True, "stage": monitor.current_stage})
                return
            if self.path == "/api/plan":
                payload = self._read_json_body()
                raw_total = payload.get("total_calls")
                total_calls: Optional[int] = None
                if isinstance(raw_total, int):
                    total_calls = raw_total
                monitor.set_plan(total_calls, str(payload.get("summary", "")))
                self._send_json({"ok": True})
                return
            if self.path == "/api/reset":
                monitor.reset_progress()
                self._send_json({"ok": True})
                return
            self._send_json({"error": "not found"}, status=404)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return Handler


def _monitor_html() -> str:
    return """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Bitwig MCP Monitor</title>
  <style>
    :root {
      --bg: #1a1a1a;
      --panel: #2a2a2a;
      --panel-edge: #3b3b3b;
      --text: #ececec;
      --muted: #a9a9a9;
      --accent: #7bc4ff;
      --ok: #7ad17a;
      --warn: #f6bf5f;
      --err: #f08a8a;
    }
    body {
      font-family: Arial, sans-serif;
      margin: 14px;
      background: radial-gradient(circle at top, #262626 0%, #151515 60%, #0f0f0f 100%);
      color: var(--text);
    }
    .titleBar {
      margin-bottom: 10px;
      padding: 10px 14px;
      border-radius: 10px;
      border: 1px solid #4a4a4a;
      background: linear-gradient(#353535, #242424);
      box-shadow: inset 0 1px 0 #555, inset 0 -1px 0 #1a1a1a, 0 2px 10px rgba(0,0,0,.35);
    }
    .row { margin: 8px 0; }
    .box {
      border: 1px solid var(--panel-edge);
      padding: 10px;
      margin-bottom: 10px;
      border-radius: 10px;
      background: linear-gradient(#313131, #232323);
      box-shadow: inset 0 1px 0 #4d4d4d, inset 0 -1px 0 #191919, 0 2px 8px rgba(0,0,0,.35);
    }
    input, button {
      background: linear-gradient(#2f2f2f, #1f1f1f);
      color: var(--text);
      border: 1px solid #4b4b4b;
      border-radius: 6px;
      padding: 6px;
      box-shadow: inset 0 1px 0 #4f4f4f;
    }
    button:hover { filter: brightness(1.06); cursor: pointer; }
    code { color: #9bd; }
    .muted { color: var(--muted); }
    .barWrap {
      width: 100%;
      background: #171717;
      border: 1px solid #4a4a4a;
      border-radius: 999px;
      height: 18px;
      box-shadow: inset 0 2px 4px rgba(0,0,0,.55);
    }
    .barFill {
      height: 18px;
      background: linear-gradient(#72d572, #3fae3f);
      width: 0%;
      border-radius: 999px;
      transition: width 0.2s ease-in-out;
      box-shadow: inset 0 1px 0 #a1e3a1;
    }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .cards { display: grid; grid-template-columns: repeat(3, minmax(180px, 1fr)); gap: 10px; }
    .dial {
      width: 120px;
      height: 120px;
      border-radius: 50%;
      margin: 8px auto;
      position: relative;
      background: conic-gradient(#5bd25b 0deg, #5bd25b 0deg, #2b2b2b 0deg 360deg);
      border: 1px solid #4f4f4f;
      box-shadow: inset 0 2px 8px rgba(0,0,0,.55), 0 2px 8px rgba(0,0,0,.45);
    }
    .dial::before {
      content: "";
      position: absolute;
      inset: 14px;
      border-radius: 50%;
      background: radial-gradient(circle at 30% 25%, #525252 0%, #2b2b2b 55%, #1a1a1a 100%);
      border: 1px solid #555;
    }
    .dialValue {
      position: absolute;
      inset: 0;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 20px;
      font-weight: bold;
      z-index: 2;
      color: #f0f0f0;
      text-shadow: 0 1px 0 #000;
    }
    .toolChips { display: flex; flex-wrap: wrap; gap: 6px; }
    .chip {
      padding: 4px 8px;
      border-radius: 999px;
      border: 1px solid #5a5a5a;
      background: linear-gradient(#3a3a3a, #262626);
      font-size: 12px;
    }
    .valueChart { display: grid; grid-template-columns: 1fr; gap: 4px; max-height: 240px; overflow: auto; }
    .valueRow { display: grid; grid-template-columns: 140px 1fr 48px; gap: 8px; align-items: center; font-size: 12px; }
    .valueLabel { color: #d6d6d6; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .valueBarWrap { background: #171717; border: 1px solid #4b4b4b; height: 10px; border-radius: 999px; overflow: hidden; }
    .valueBarFill { height: 10px; background: linear-gradient(#78c4ff, #3a8ed0); width: 0%; }
    .instGrid { display: grid; grid-template-columns: repeat(2, minmax(260px, 1fr)); gap: 10px; }
    .instCard {
      border: 1px solid #4f4f4f;
      border-radius: 8px;
      padding: 8px;
      background: linear-gradient(#2f2f2f, #222);
    }
    .instTitle { font-weight: bold; margin-bottom: 6px; }
    .instParamRow { display: grid; grid-template-columns: 1fr auto auto; gap: 8px; font-size: 12px; padding: 3px 4px; border-radius: 6px; }
    .instParamSeen { background: rgba(70, 120, 220, 0.20); border: 1px solid rgba(90, 150, 255, 0.45); }
    .instParamChanged { background: rgba(210, 145, 50, 0.22); border: 1px solid rgba(245, 175, 70, 0.55); }
    .instMeta { color: #cfcfcf; font-size: 11px; }
    .instCount { color: #9ad8ff; font-size: 11px; }
  </style>
</head>
<body>
  <div class="titleBar">
    <h2 style="margin: 0;">Bitwig MCP Monitor</h2>
    <div class="muted">Live control + model understanding view</div>
  </div>

  <div class="box">
    <h3>Quick Guide</h3>
    <div class="row muted">Fast startup checklist for this MCP + Bitwig setup</div>
    <pre id="quickGuide">
1) Bitwig: restart after extension updates.
2) Controllers: add "Open Sound Control" -> "OSC-vaday".
3) Configure OSC ports to match MCP server settings.
4) Start bitwig-mcp-server and open this page.
5) Run diagnostic tool first, then read:
   - bitwig://tracks
   - bitwig://devices
   - bitwig://device/parameters
6) For new project flow:
   - set_tempo
   - set_track_volume / set_track_pan
   - browse_insert_device / commit_browser_selection
   - set_device_parameter
7) Use Mappings panel here to confirm project remotes, track remotes, MIDI activity, and OSC address map.
    </pre>
  </div>

  <div class="cards">
    <div class="box">
      <div class="muted">Plan Progress</div>
      <div class="dial" id="progressDial"><div class="dialValue" id="progressDialText">0%</div></div>
    </div>
    <div class="box">
      <div class="muted">Failure Ratio</div>
      <div class="dial" id="failDial"><div class="dialValue" id="failDialText">0%</div></div>
    </div>
    <div class="box">
      <div class="muted">Recent Activity</div>
      <div class="dial" id="activityDial"><div class="dialValue" id="activityDialText">0</div></div>
    </div>
  </div>

  <div class="box">
    <div class="row">Uptime: <span id="uptime">-</span>s</div>
    <div class="row">Stage: <code id="stage">-</code></div>
    <div class="row">Plan: <code id="planSummary">none</code></div>
    <div class="row">
      Progress: <span id="progressText" class="muted">n/a</span>
      <div class="barWrap"><div class="barFill" id="progressBar"></div></div>
    </div>
    <div class="row">
      Calls: completed=<code id="completedCalls">0</code>,
      failed=<code id="failedCalls">0</code>,
      remaining=<code id="remainingCalls">n/a</code>
    </div>
    <div class="row">Last Call: <code id="lastCallSummary">none</code></div>
    <div class="row">Last Error: <code id="lastError">none</code></div>
    <div class="row">
      <input id="stageInput" placeholder="set current stage" size="50"/>
      <button onclick="setStage()">Update Stage</button>
    </div>
    <div class="row">
      <input id="planSummaryInput" placeholder="plan summary" size="38"/>
      <input id="planTotalInput" placeholder="total calls" size="10"/>
      <button onclick="setPlan()">Set Plan</button>
      <button onclick="resetProgress()">Reset</button>
    </div>
  </div>

  <div class="box">
    <h3>Live Bitwig Overview</h3>
    <div class="row muted">Tracks, devices, parameters, and known OSC/MIDI control surfaces</div>
    <div class="row">
      <strong>Tracks</strong>
      <pre id="overviewTracks">[]</pre>
    </div>
    <div class="row">
      <strong>Devices / VST Focus</strong>
      <pre id="overviewDevices">[]</pre>
    </div>
    <div class="row">
      <strong>Parameter Snapshot</strong>
      <pre id="overviewParams">[]</pre>
    </div>
    <div class="row">
      <strong>Mappings (MIDI + OSC)</strong>
      <pre id="overviewMappings">[]</pre>
    </div>
  </div>

  <div class="box">
    <h3>What Model Understands</h3>
    <div class="row muted">Interpreted from tool calls + result text</div>
    <div class="row"><div id="toolChips" class="toolChips"></div></div>
    <div class="row">
      <div class="muted">Recent Numeric Values</div>
      <div id="valueChart" class="valueChart"></div>
    </div>
    <div class="row">
      <div class="muted">Understanding Notes</div>
      <pre id="notes">[]</pre>
    </div>
    <div class="row">
      <div class="muted">Instruments + Parameters (orange = under control/changed, blue = available/seen)</div>
      <div id="instrumentGrid" class="instGrid"></div>
    </div>
  </div>

  <div class="grid">
    <div class="box">
      <h3>Active Calls</h3>
      <pre id="activeCalls">[]</pre>
    </div>
    <div class="box">
      <h3>Recent Events</h3>
      <pre id="events">[]</pre>
    </div>
  </div>
  <script>
    function clamp(v, lo, hi) {
      return Math.max(lo, Math.min(hi, v));
    }
    function setDial(id, textId, pct, text, colorA, colorB) {
      const p = clamp(pct || 0, 0, 100);
      const deg = (p / 100) * 360;
      const dial = document.getElementById(id);
      dial.style.background = `conic-gradient(${colorA} 0deg, ${colorB} ${deg}deg, #2b2b2b ${deg}deg 360deg)`;
      document.getElementById(textId).textContent = text;
    }
    function renderToolChips(counts) {
      const box = document.getElementById('toolChips');
      box.innerHTML = '';
      const entries = Object.entries(counts || {}).sort((a,b)=>b[1]-a[1]).slice(0, 18);
      if (entries.length === 0) {
        box.textContent = 'none';
        return;
      }
      for (const [name, n] of entries) {
        const chip = document.createElement('div');
        chip.className = 'chip';
        chip.textContent = `${name}: ${n}`;
        box.appendChild(chip);
      }
    }
    function renderValueChart(values) {
      const root = document.getElementById('valueChart');
      root.innerHTML = '';
      const rows = (values || []).slice(0, 20);
      if (rows.length === 0) {
        root.textContent = 'none';
        return;
      }
      for (const row of rows) {
        const wrap = document.createElement('div');
        wrap.className = 'valueRow';
        const label = document.createElement('div');
        label.className = 'valueLabel';
        label.textContent = row.label || 'value';
        const barWrap = document.createElement('div');
        barWrap.className = 'valueBarWrap';
        const bar = document.createElement('div');
        bar.className = 'valueBarFill';
        const numeric = Number(row.value || 0);
        const pct = clamp((numeric / 128) * 100, 0, 100);
        bar.style.width = `${pct}%`;
        barWrap.appendChild(bar);
        const num = document.createElement('div');
        num.style.textAlign = 'right';
        num.textContent = String(Math.round(numeric * 100) / 100);
        wrap.appendChild(label);
        wrap.appendChild(barWrap);
        wrap.appendChild(num);
        root.appendChild(wrap);
      }
    }
    function renderInstruments(instrumentParams) {
      const root = document.getElementById('instrumentGrid');
      root.innerHTML = '';
      const entries = Object.entries(instrumentParams || {});
      if (entries.length === 0) {
        root.textContent = 'none';
        return;
      }
      for (const [instName, params] of entries.slice(0, 24)) {
        const card = document.createElement('div');
        card.className = 'instCard';
        const title = document.createElement('div');
        title.className = 'instTitle';
        title.textContent = instName;
        card.appendChild(title);
        const pEntries = Object.entries(params || {}).slice(0, 28);
        const totals = pEntries.reduce((acc, [, meta]) => {
          acc.available += Number(meta.available_count || 0) > 0 ? 1 : 0;
          acc.controlled += Number(meta.controlled_count || 0) > 0 ? 1 : 0;
          return acc;
        }, { available: 0, controlled: 0 });
        const subtitle = document.createElement('div');
        subtitle.className = 'instMeta';
        subtitle.textContent = `available: ${totals.available} | under control: ${totals.controlled}`;
        subtitle.style.marginBottom = '6px';
        card.appendChild(subtitle);
        for (const [pname, meta] of pEntries) {
          const row = document.createElement('div');
          const controlled = Number(meta.controlled_count || 0) > 0 || Number(meta.changed_count || 0) > 0;
          row.className = 'instParamRow ' + (controlled ? 'instParamChanged' : 'instParamSeen');
          const pn = document.createElement('div');
          pn.textContent = pname;
          const pv = document.createElement('div');
          pv.className = 'instMeta';
          pv.textContent = meta.last_value == null ? '-' : String(meta.last_value);
          const pc = document.createElement('div');
          pc.className = 'instCount';
          const seen = Number(meta.seen_count || 0);
          const changedCount = Number(meta.changed_count || 0);
          const availCount = Number(meta.available_count || 0);
          const controlledCount = Number(meta.controlled_count || 0);
          pc.textContent = `s${seen}/a${availCount}/c${changedCount}/u${controlledCount}`;
          row.appendChild(pn);
          row.appendChild(pv);
          row.appendChild(pc);
          card.appendChild(row);
        }
        root.appendChild(card);
      }
    }
    async function refresh() {
      try {
        const r = await fetch('/api/status');
        const s = await r.json();
        document.getElementById('uptime').textContent = s.uptime_sec;
        document.getElementById('stage').textContent = s.stage || 'idle';
        document.getElementById('planSummary').textContent = s.plan_summary || 'none';
        document.getElementById('completedCalls').textContent = String(s.completed_calls ?? 0);
        document.getElementById('failedCalls').textContent = String(s.failed_calls ?? 0);
        document.getElementById('remainingCalls').textContent = s.remaining_calls == null ? 'n/a' : String(s.remaining_calls);
        document.getElementById('lastCallSummary').textContent = s.last_call_summary || 'none';
        document.getElementById('lastError').textContent = s.last_error || 'none';
        const p = s.progress_percent;
        const pText = p == null ? 'n/a' : (String(p) + '%');
        document.getElementById('progressText').textContent = pText;
        document.getElementById('progressBar').style.width = p == null ? '0%' : (String(p) + '%');
        document.getElementById('activeCalls').textContent = JSON.stringify(s.active_calls, null, 2);
        document.getElementById('events').textContent = JSON.stringify(s.recent_events, null, 2);

        const completed = Number(s.completed_calls || 0);
        const failed = Number(s.failed_calls || 0);
        const failRatio = completed > 0 ? (failed / completed) * 100 : 0;
        const recentEventCount = Array.isArray(s.recent_events) ? s.recent_events.length : 0;
        setDial('progressDial', 'progressDialText', p || 0, (pText || '0%'), '#7fe07f', '#52b952');
        setDial('failDial', 'failDialText', failRatio, `${Math.round(failRatio)}%`, '#ffb07a', '#f08358');
        setDial('activityDial', 'activityDialText', clamp(recentEventCount, 0, 100), String(recentEventCount), '#8ec9ff', '#4b93d9');

        const u = s.understanding || {};
        renderToolChips(u.tool_counts || {});
        renderValueChart(u.recent_values || []);
        document.getElementById('notes').textContent = JSON.stringify((u.notes || []).slice(0, 20), null, 2);
        renderInstruments(u.instrument_params || {});

        const ov = s.live_overview || {};
        document.getElementById('overviewTracks').textContent = JSON.stringify(ov.tracks || [], null, 2);
        document.getElementById('overviewDevices').textContent = JSON.stringify({
          selected_device: ov.selected_device || null,
          device_chain: ov.device_chain || [],
          vst_guessing: ov.vst_guessing || []
        }, null, 2);
        document.getElementById('overviewParams').textContent = JSON.stringify((ov.device_parameters || []).slice(0, 80), null, 2);
        document.getElementById('overviewMappings').textContent = JSON.stringify({
          project_remotes: ov.project_remotes || [],
          track_remotes: ov.track_remotes || [],
          midi_activity: ov.midi_activity || {},
          osc_address_map: ov.osc_address_map || []
        }, null, 2);
      } catch (e) {
        document.getElementById('lastError').textContent = 'monitor fetch failed';
      }
    }
    async function setStage() {
      const stage = document.getElementById('stageInput').value || '';
      await fetch('/api/stage', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({stage})
      });
      refresh();
    }
    async function setPlan() {
      const summary = document.getElementById('planSummaryInput').value || '';
      const raw = document.getElementById('planTotalInput').value || '';
      let total = null;
      if (raw.trim().length > 0) {
        const n = parseInt(raw, 10);
        if (!Number.isNaN(n)) {
          total = n;
        }
      }
      await fetch('/api/plan', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({summary: summary, total_calls: total})
      });
      refresh();
    }
    async function resetProgress() {
      await fetch('/api/reset', {method: 'POST'});
      refresh();
    }
    setInterval(refresh, 1000);
    refresh();
  </script>
</body>
</html>
"""
