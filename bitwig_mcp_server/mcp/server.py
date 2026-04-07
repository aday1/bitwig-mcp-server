"""
Bitwig MCP Server

Implementation of the Model Context Protocol server for Bitwig Studio integration.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from mcp.server import Server as MCPServer
from mcp.server.stdio import stdio_server
from mcp.types import TextContent

from bitwig_mcp_server.osc.controller import BitwigOSCController
from bitwig_mcp_server.monitor import MCPMonitor
from bitwig_mcp_server.settings import Settings

# Set up logging
logger = logging.getLogger(__name__)


class BitwigMCPServer:
    """MCP server for Bitwig Studio integration"""

    def __init__(self, settings: Optional[Settings] = None):
        """Initialize the Bitwig MCP server

        Args:
            settings: Application settings (uses default Settings if not provided)
        """
        # Use provided settings or create default
        self.settings = settings or Settings()

        # Create the MCP server
        self.mcp_server = MCPServer(f"bitwig-mcp-server-{self.settings.app_name}")

        # Create the Bitwig OSC controller with settings
        self.controller = BitwigOSCController(
            self.settings.bitwig_host,
            self.settings.bitwig_send_port,
            self.settings.bitwig_receive_port,
            osc_bank_page_size=self.settings.osc_bank_page_size,
        )
        self.monitor = MCPMonitor(
            host=self.settings.monitor_host, port=self.settings.monitor_port
        )
        if self.settings.monitor_enabled:
            try:
                self.monitor.start()
                self.monitor.set_stage("server initialized")
            except Exception as e:
                logger.warning("Failed to start monitor UI: %s", e)

        # Set up handlers
        self._setup_handlers()

        # OSC starts lazily so MCP stdio can handshake before Bitwig responds
        self._osc_lock = asyncio.Lock()
        self._last_osc_ping: float = 0.0
        self._osc_health_interval_sec: float = 8.0

    def _setup_handlers(self) -> None:
        """Set up MCP server handlers"""
        self.mcp_server.list_tools()(self.list_tools)
        self.mcp_server.call_tool()(self.call_tool)
        self.mcp_server.list_resources()(self.list_resources)
        self.mcp_server.read_resource()(self.read_resource)

    async def start(self) -> None:
        """Start the OSC controller (blocking). Prefer ensure_osc_started for MCP stdio."""
        try:
            await self.ensure_osc_started()
            logger.info(f"Bitwig MCP Server started - hosting {self.settings.app_name}")
        except Exception as e:
            logger.exception(f"Failed to start Bitwig MCP Server: {e}")
            await self.stop()
            raise

    async def ensure_osc_started(self) -> None:
        """Bind OSC receive port, connect to Bitwig, and recover if the link went stale."""
        async with self._osc_lock:
            if self.controller.ready:
                now = time.time()
                if now - self._last_osc_ping < self._osc_health_interval_sec:
                    return
                ok = await asyncio.to_thread(self.controller.ping, 1.0)
                self._last_osc_ping = time.time()
                if ok:
                    return
                logger.warning("Bitwig OSC ping failed; reconnecting controller")
                await asyncio.to_thread(self._stop_osc_safe)
            await asyncio.to_thread(self._start_osc_blocking)
            self._last_osc_ping = time.time()

    def _stop_osc_safe(self) -> None:
        try:
            self.controller.stop()
        except Exception as e:
            logger.warning("Error stopping OSC controller during reconnect: %s", e)

    def _start_osc_blocking(self) -> None:
        self.controller.start()

    async def stop(self) -> None:
        """Stop the Bitwig MCP server"""
        try:
            if hasattr(self, "controller"):
                self.controller.stop()
            if hasattr(self, "monitor"):
                self.monitor.stop()
            logger.info("Bitwig MCP Server stopped")
        except Exception as e:
            logger.exception(f"Error while stopping Bitwig MCP Server: {e}")

    async def list_tools(self) -> List[Any]:
        """List available Bitwig tools"""
        from bitwig_mcp_server.mcp.tools import get_bitwig_tools

        return get_bitwig_tools()

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> List[TextContent]:
        """Call a Bitwig tool

        Args:
            name: Tool name to call
            arguments: Arguments for the tool

        Returns:
            Result from the tool execution

        Raises:
            ValueError: If tool name is unknown or arguments are invalid
        """
        from bitwig_mcp_server import bitwig_mcp_activity as _bw_activity

        call_id = self.monitor.begin_call(name, arguments)
        self.monitor.set_stage(f"running {name}")
        act_rid = _bw_activity.log_tool_start(name, arguments)
        t0 = time.time()
        try:
            if name == "get_bitwig_mcp_install_guide":
                from bitwig_mcp_server.mcp.install_help import render_install_guide

                topic = str(arguments.get("topic", "full") or "full")
                text = render_install_guide(topic)
                result = [TextContent(type="text", text=text)]
                self.monitor.end_call(call_id, "ok", _summarize_text_content(result))
                _bw_activity.log_tool_end(
                    act_rid, name, True, time.time() - t0, result=_summarize_text_content(result)
                )
                self.monitor.set_stage("idle")
                return result
            if name == "build_browser_index":
                result = await self._run_build_browser_index(arguments)
                self.monitor.set_live_overview(self._build_live_overview())
                self.monitor.end_call(call_id, "ok", _summarize_text_content(result))
                _bw_activity.log_tool_end(
                    act_rid, name, True, time.time() - t0, result=_summarize_text_content(result)
                )
                return result
            await self.ensure_osc_started()
            from bitwig_mcp_server.mcp.tools import execute_tool

            result = await execute_tool(self.controller, name, arguments)
            self.monitor.set_live_overview(self._build_live_overview())
            self.monitor.end_call(call_id, "ok", _summarize_text_content(result))
            self.monitor.set_stage("idle")
            _bw_activity.log_tool_end(
                act_rid, name, True, time.time() - t0, result=_summarize_text_content(result)
            )
            return result
        except Exception as e:
            logger.exception(f"Error calling tool {name}: {e}")
            self.monitor.set_live_overview(self._build_live_overview())
            self.monitor.end_call(call_id, "error", str(e))
            self.monitor.set_stage("error")
            _bw_activity.log_tool_end(
                act_rid, name, False, time.time() - t0, error=str(e)
            )
            return [TextContent(type="text", text=f"Error: {e!s}")]

    async def _run_build_browser_index(
        self, arguments: dict[str, Any]
    ) -> List[TextContent]:
        """Stop OSC (free receive port), run indexer, restart OSC."""
        from bitwig_mcp_server.utils.index_runner import run_browser_index_build_sync

        persistent_dir = arguments.get("persistent_dir")
        clear = bool(arguments.get("clear", False))

        async with self._osc_lock:
            await asyncio.to_thread(self._stop_osc_safe)
            ok = False
            msg = ""
            try:
                ok, msg = await asyncio.to_thread(
                    run_browser_index_build_sync, persistent_dir, clear
                )
            except Exception as e:
                logger.exception("build_browser_index failed: %s", e)
                msg = f"Build error: {e!s}"
                ok = False
            try:
                await asyncio.to_thread(self._start_osc_blocking)
            except Exception as e:
                logger.exception("OSC restart after index failed: %s", e)
                tail = f" Also failed to restart OSC: {e!s}"
                return [
                    TextContent(
                        type="text",
                        text=("Failed. " + msg + tail),
                    )
                ]
            self._last_osc_ping = time.time()
            self.monitor.set_stage("index build completed")

        prefix = "Success. " if ok else "Failed. "
        return [TextContent(type="text", text=prefix + msg)]

    async def list_resources(self) -> List[Any]:
        """List available Bitwig resources"""
        from bitwig_mcp_server.mcp.resources import get_bitwig_resources

        return get_bitwig_resources()

    async def read_resource(self, uri: str) -> str:
        """Read a Bitwig resource

        Args:
            uri: Resource URI to read

        Returns:
            Content of the resource

        Raises:
            ValueError: If resource URI is unknown
        """
        try:
            await self.ensure_osc_started()
            from bitwig_mcp_server.mcp.resources import read_resource

            text = await read_resource(self.controller, uri)
            self.monitor.set_live_overview(self._build_live_overview())
            return text
        except Exception as e:
            logger.exception(f"Error reading resource {uri}: {e}")
            raise ValueError(f"Failed to read resource {uri}: {e}")

    def _build_live_overview(self) -> Dict[str, Any]:
        """
        Build a monitor-friendly snapshot from current OSC cache.

        This is a best-effort introspection layer so the monitor can show:
        tracks, focused/chain devices (including likely VSTs), parameters,
        and known OSC/MIDI control mappings.
        """
        msgs = dict(getattr(self.controller.server, "received_messages", {}) or {})
        max_tracks = max(8, int(getattr(self.controller.client, "osc_bank_page_size", 64)))

        tracks: List[Dict[str, Any]] = []
        for i in range(1, max_tracks + 1):
            name = msgs.get(f"/track/{i}/name")
            if not name:
                continue
            tracks.append(
                {
                    "index": i,
                    "name": name,
                    "volume": msgs.get(f"/track/{i}/volume"),
                    "pan": msgs.get(f"/track/{i}/pan"),
                    "mute": bool(msgs.get(f"/track/{i}/mute"))
                    if f"/track/{i}/mute" in msgs
                    else None,
                    "solo": bool(msgs.get(f"/track/{i}/solo"))
                    if f"/track/{i}/solo" in msgs
                    else None,
                    "record_armed": bool(msgs.get(f"/track/{i}/recarm"))
                    if f"/track/{i}/recarm" in msgs
                    else None,
                }
            )

        selected_device = msgs.get("/device/name")
        chain_size = msgs.get("/device/chain/size")
        device_chain: List[Dict[str, Any]] = []
        if isinstance(chain_size, (int, float)):
            for i in range(1, int(chain_size) + 1):
                n = msgs.get(f"/device/chain/{i}/name")
                if n:
                    device_chain.append({"index": i, "name": n})

        params: List[Dict[str, Any]] = []
        missing = 0
        for i in range(1, 513):
            exists = msgs.get(f"/device/param/{i}/exists")
            if not exists:
                missing += 1
                if missing >= 32 and params:
                    break
                continue
            missing = 0
            pname = msgs.get(f"/device/param/{i}/name")
            pvalue = msgs.get(f"/device/param/{i}/value")
            pstr = msgs.get(f"/device/param/{i}/value/str")
            params.append(
                {
                    "index": i,
                    "name": pname,
                    "value": pvalue,
                    "display": pstr,
                }
            )

        project_remotes: List[Dict[str, Any]] = []
        for i in range(1, 9):
            v = msgs.get(f"/project/param/{i}/value")
            n = msgs.get(f"/project/param/{i}/name")
            if v is not None or n is not None:
                project_remotes.append({"index": i, "name": n, "value": v})

        track_remotes: List[Dict[str, Any]] = []
        for t in range(1, max_tracks + 1):
            if not msgs.get(f"/track/{t}/name"):
                continue
            for r in range(1, 9):
                rv = msgs.get(f"/track/{t}/remote/{r}/value")
                rn = msgs.get(f"/track/{t}/remote/{r}/name")
                if rv is not None or rn is not None:
                    track_remotes.append(
                        {"track_index": t, "remote_index": r, "name": rn, "value": rv}
                    )

        vst_guessing: List[str] = []
        for d in [selected_device] + [row["name"] for row in device_chain]:
            if not d:
                continue
            ds = str(d)
            dsl = ds.lower()
            if any(k in dsl for k in ("vst", "clap", "reaktor", "kontakt")):
                if ds not in vst_guessing:
                    vst_guessing.append(ds)

        tool_counts = (
            self.monitor.status_snapshot()
            .get("understanding", {})
            .get("tool_counts", {})
        )
        midi_activity = {
            k: int(v)
            for k, v in tool_counts.items()
            if str(k).startswith("send_midi_") or str(k) in ("play_midi_note_sequence",)
        }

        osc_address_map = [
            {
                "address": "/project/param/{1..8}/value",
                "semantic_name": "project_remote_control",
                "target_kind": "project_remote",
                "value_range": "0..128",
            },
            {
                "address": "/track/{track}/remote/{1..8}/value",
                "semantic_name": "track_remote_parameter",
                "target_kind": "track_remote",
                "value_range": "0..128",
            },
            {
                "address": "/device/param/{index}/value",
                "semantic_name": "selected_device_parameter",
                "target_kind": "device_param",
                "value_range": "0..128",
            },
            {
                "address": "/vkb_midi/{channel}/cc/{cc}",
                "semantic_name": "midi_cc_bridge",
                "target_kind": "midi_virtual_keyboard",
                "value_range": "0..127",
            },
        ]

        return {
            "tracks": tracks,
            "selected_device": selected_device,
            "device_chain": device_chain,
            "vst_guessing": vst_guessing,
            "device_parameters": params,
            "project_remotes": project_remotes,
            "track_remotes": track_remotes,
            "midi_activity": midi_activity,
            "osc_address_map": osc_address_map,
        }


def _summarize_text_content(contents: List[TextContent]) -> str:
    if not contents:
        return "ok"
    text = "; ".join(
        c.text for c in contents if isinstance(c, TextContent) and hasattr(c, "text")
    )
    return text[:300] if text else "ok"


async def run_server(settings: Optional[Settings] = None) -> None:
    """Run the Bitwig MCP server (MCP over stdio for Cursor / Claude Desktop)."""
    from bitwig_mcp_server.bitwig_mcp_activity import maybe_autostart_dashboard

    maybe_autostart_dashboard()
    server = BitwigMCPServer(settings)

    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.mcp_server.run(
                read_stream,
                write_stream,
                server.mcp_server.create_initialization_options(),
            )
    except asyncio.CancelledError:
        pass
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
    finally:
        await server.stop()
