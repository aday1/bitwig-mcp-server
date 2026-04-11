"""
Bitwig MCP Tools

This module provides MCP tools for controlling Bitwig Studio.
"""

import asyncio
import logging
import os
import re
from typing import Any, Dict, List, Optional

from mcp.types import TextContent, Tool

from bitwig_mcp_server.osc.controller import BitwigOSCController
from bitwig_mcp_server.paths import browser_index_persistent_dir

# Set up logging
logger = logging.getLogger(__name__)


def get_bitwig_tools() -> List[Tool]:
    """Get all available Bitwig tools

    Returns:
        List of Tool objects
    """
    return [
        # Browser content discovery tools
        Tool(
            name="search_device_browser",
            description="Search for devices in the Bitwig browser using semantic search",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (e.g., 'delay with filtering')",
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Number of results to return",
                        "default": 5,
                    },
                    "category": {
                        "type": "string",
                        "description": "Filter by device category",
                    },
                    "type": {
                        "type": "string",
                        "description": "Filter by device type",
                    },
                    "creator": {
                        "type": "string",
                        "description": "Filter by device creator",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="recommend_devices",
            description="Recommend devices based on a natural language description of the desired sound or effect",
            inputSchema={
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Description of the desired sound or effect (e.g., 'make the bass sound fatter and warmer')",
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Number of results to return",
                        "default": 5,
                    },
                    "category": {
                        "type": "string",
                        "description": "Filter by device category",
                    },
                },
                "required": ["description"],
            },
        ),
        Tool(
            name="get_device_categories",
            description="Get a list of all device categories",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="get_device_info",
            description="Get detailed information about a specific device",
            inputSchema={
                "type": "object",
                "properties": {
                    "device_name": {
                        "type": "string",
                        "description": "Name of the device to get information about",
                    },
                },
                "required": ["device_name"],
            },
        ),
        Tool(
            name="bitwig_diagnose",
            description=(
                "Report Bitwig OSC connection health, configured ports, browser index path, "
                "and how many devices are indexed. Use when indexing or semantic search fails."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="get_bitwig_mcp_install_guide",
            description=(
                "Return Markdown install steps for Bitwig MCP: Python, Cursor MCP JSON, DrivenByMoss/OSC ports, "
                "browser index, dashboard env vars, troubleshooting. Does not require Bitwig to be running. "
                "Use topic=full or cursor, bitwig_osc, index, dashboard, troubleshoot."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": (
                            "full (default), cursor, bitwig_osc, index, dashboard, troubleshoot"
                        ),
                        "default": "full",
                    },
                },
            },
        ),
        Tool(
            name="build_browser_index",
            description=(
                "Build the semantic browser device index (instruments, FX, etc.). "
                "Temporarily stops the MCP OSC listener so the indexer can bind the receive port; "
                "then restarts OSC. Bitwig must be open with OSC sending to BITWIG_MCP_BITWIG_RECEIVE_PORT. "
                "Takes several minutes on large libraries. Optional clear:true wipes the old Chroma DB first."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "persistent_dir": {
                        "type": "string",
                        "description": "Override index directory (default: package data/browser_index or BITWIG_MCP_BROWSER_INDEX_DIR)",
                    },
                    "clear": {
                        "type": "boolean",
                        "description": "If true, delete existing Chroma data before indexing",
                        "default": False,
                    },
                },
            },
        ),
        Tool(
            name="transport_play",
            description="Toggle play/pause state of Bitwig",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="transport_stop",
            description="Stop transport playback (does not toggle)",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="set_tempo",
            description="Set the tempo of the Bitwig project",
            inputSchema={
                "type": "object",
                "properties": {
                    "bpm": {
                        "type": "number",
                        "description": "Tempo in beats per minute (0-666)",
                    }
                },
                "required": ["bpm"],
            },
        ),
        Tool(
            name="set_playhead_beats",
            description=(
                "Move the playhead on the arranger timeline (position in beats, not bars). "
                "Pair with start_arranger_record and armed tracks to record timeline clips."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "beats": {
                        "type": "number",
                        "description": "Playback position in beats from project start",
                    }
                },
                "required": ["beats"],
            },
        ),
        Tool(
            name="start_arranger_record",
            description=(
                "Start arranger recording: creates clips on the timeline for armed tracks. "
                "OSC cannot place empty clips at arbitrary bar positions; use this or click "
                "the timeline first and use clip_create_at_cursor."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="set_track_volume",
            description="Set the volume of a track",
            inputSchema={
                "type": "object",
                "properties": {
                    "track_index": {
                        "type": "integer",
                        "description": "Track index (1-based)",
                    },
                    "volume": {
                        "type": "number",
                        "description": "Volume value (0-128, where 64 is 0dB)",
                    },
                },
                "required": ["track_index", "volume"],
            },
        ),
        Tool(
            name="set_track_pan",
            description="Set the pan of a track",
            inputSchema={
                "type": "object",
                "properties": {
                    "track_index": {
                        "type": "integer",
                        "description": "Track index (1-based)",
                    },
                    "pan": {
                        "type": "number",
                        "description": "Pan value (0-128, where 64 is center)",
                    },
                },
                "required": ["track_index", "pan"],
            },
        ),
        Tool(
            name="toggle_track_mute",
            description="Toggle mute state of a track",
            inputSchema={
                "type": "object",
                "properties": {
                    "track_index": {
                        "type": "integer",
                        "description": "Track index (1-based)",
                    }
                },
                "required": ["track_index"],
            },
        ),
        Tool(
            name="add_instrument_track",
            description=(
                "Add a new empty instrument track. Select it in Bitwig, then use browse_insert_device / "
                "device_browser_workflow to load Polysynth, Drum Machine, etc."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="add_audio_track",
            description="Add a new empty audio track",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="add_effect_track",
            description="Add a new effect return / bus-style track (depends on Bitwig project)",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="select_track",
            description=(
                "Select a track by index in the current OSC track bank (1-based). New tracks usually "
                "appear in the bank; use navigate_track_bank if the track is off-screen."
            ),
            inputSchema={
                "type": "object",
                "properties": {"track_index": {"type": "integer"}},
                "required": ["track_index"],
            },
        ),
        Tool(
            name="navigate_track_selection",
            description="Select next or previous track within the current bank",
            inputSchema={
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["next", "previous"],
                    }
                },
                "required": ["direction"],
            },
        ),
        Tool(
            name="navigate_track_bank",
            description=(
                "Scroll which tracks are mapped to OSC indices 1..N. Use page=true to jump by 8 "
                "(default bank page size)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["next", "previous"],
                    },
                    "page": {
                        "type": "boolean",
                        "description": "If true, scroll a full page of tracks",
                        "default": False,
                    },
                },
                "required": ["direction"],
            },
        ),
        Tool(
            name="toggle_track_bank_mode",
            description="Toggle OSC between main (audio/instrument) track bank and effect-track bank",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="set_track_name",
            description="Rename a track in the current OSC bank (1-based index)",
            inputSchema={
                "type": "object",
                "properties": {
                    "track_index": {"type": "integer"},
                    "name": {"type": "string"},
                },
                "required": ["track_index", "name"],
            },
        ),
        Tool(
            name="set_track_record_arm",
            description="Arm or disarm a track for recording (MIDI/audio into clips)",
            inputSchema={
                "type": "object",
                "properties": {
                    "track_index": {"type": "integer"},
                    "armed": {"type": "boolean"},
                },
                "required": ["track_index", "armed"],
            },
        ),
        Tool(
            name="set_track_solo",
            description="Set track solo on or off",
            inputSchema={
                "type": "object",
                "properties": {
                    "track_index": {"type": "integer"},
                    "solo": {"type": "boolean"},
                },
                "required": ["track_index", "solo"],
            },
        ),
        Tool(
            name="duplicate_track",
            description="Duplicate the track at the given bank index (destructive: creates tracks)",
            inputSchema={
                "type": "object",
                "properties": {"track_index": {"type": "integer"}},
                "required": ["track_index"],
            },
        ),
        Tool(
            name="remove_track",
            description="Delete the track at the given bank index (destructive)",
            inputSchema={
                "type": "object",
                "properties": {"track_index": {"type": "integer"}},
                "required": ["track_index"],
            },
        ),
        Tool(
            name="set_layout",
            description="Switch Bitwig layout: arrange (timeline), mix (mixer), or edit",
            inputSchema={
                "type": "object",
                "properties": {
                    "layout": {
                        "type": "string",
                        "enum": ["arrange", "mix", "edit"],
                    }
                },
                "required": ["layout"],
            },
        ),
        Tool(
            name="toggle_mixer_sends_section",
            description=(
                "Toggle Mixer layout sends column visibility (run twice if unsure). "
                "Use after set_layout mix when automating sends."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="set_track_send",
            description=(
                "Enable a track send and set its level (OSC /track/n/send/m). "
                "Requires a return/bus on that send slot in Bitwig; load Reverb/Delay on the return."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "track_index": {"type": "integer"},
                    "send_index": {
                        "type": "integer",
                        "description": "Send slot 1-8 (OSC bank)",
                        "default": 1,
                    },
                    "volume": {
                        "type": "number",
                        "description": "0-128 typical; 0 dry, ~40 light wet",
                        "default": 40,
                    },
                    "enable": {
                        "type": "boolean",
                        "description": "If true, activate send then set volume",
                        "default": True,
                    },
                },
                "required": ["track_index"],
            },
        ),
        Tool(
            name="set_project_remote_control",
            description=(
                "Set Bitwig project remote control slot 1-8 (OSC /project/param/n/value). "
                "Map sources in Bitwig to these first; then values move macros/rack controls."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "param_index": {
                        "type": "integer",
                        "description": "1-8",
                    },
                    "value": {
                        "type": "number",
                        "description": "0-128 (Moss OSC resolution)",
                    },
                },
                "required": ["param_index", "value"],
            },
        ),
        Tool(
            name="open_track_device_browser",
            description=(
                "Select a track (OSC bank index) and open the device insert browser. "
                "Then search Drum Machine, Organ, Polymer, Sampler, etc. and commit. "
                "Use for fixing drums: one Drum Machine on a track with drums_all_in_one_gm_8bar."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "track_index": {"type": "integer"},
                    "position": {
                        "type": "string",
                        "enum": ["after", "before"],
                        "default": "after",
                    },
                },
                "required": ["track_index"],
            },
        ),
        Tool(
            name="assign_track_instrument",
            description=(
                "Deterministically assign an instrument to a track without semantic index. "
                "Opens browser, applies filters, finds best result name match, commits, and reports active device."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "track_index": {"type": "integer"},
                    "instrument_name": {"type": "string"},
                    "position": {
                        "type": "string",
                        "enum": ["after", "before"],
                        "default": "after",
                    },
                    "category_filter": {
                        "type": "string",
                        "default": "Instrument",
                        "description": "Filter 3 target, e.g. Instrument",
                    },
                    "creator_filter": {
                        "type": "string",
                        "description": "Filter 5 target, e.g. Bitwig",
                    },
                    "location_filter": {
                        "type": "string",
                        "description": "Filter 1 target, e.g. Bitwig Studio",
                    },
                    "max_result_pages": {
                        "type": "integer",
                        "default": 8,
                        "description": "How many browser result pages to scan",
                    },
                },
                "required": ["track_index", "instrument_name"],
            },
        ),
        Tool(
            name="apply_modulation_controls",
            description=(
                "Apply immediate parameter values and optional sweeps for the currently selected "
                "device and project remotes. Targets use OSC device param indices (often 1-8 on the "
                "active remote page). By default sends /device/param/N/touched around device moves "
                "so Bitwig Latch/Touch automation write can record them (not only raw value). "
                "Enable arranger automation write and playback. Use automation_touch=false to "
                "disable. OSC cannot create automation lanes; use Write mode or draw lanes in UI "
                "if Touch still ignores OSC."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "automation_touch": {
                        "type": "boolean",
                        "default": True,
                        "description": "If true, wrap device param changes with OSC .../touched for automation recording",
                    },
                    "device_params": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "param_index": {"type": "integer"},
                                "value": {"type": "number"},
                            },
                            "required": ["param_index", "value"],
                        },
                    },
                    "project_remotes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "param_index": {"type": "integer"},
                                "value": {"type": "number"},
                            },
                            "required": ["param_index", "value"],
                        },
                    },
                    "sweeps": {
                        "type": "array",
                        "description": "Linear sweeps over time for device or remote targets",
                        "items": {
                            "type": "object",
                            "properties": {
                                "target": {
                                    "type": "string",
                                    "enum": ["device", "remote"],
                                },
                                "param_index": {"type": "integer"},
                                "start_value": {"type": "number"},
                                "end_value": {"type": "number"},
                                "steps": {"type": "integer", "default": 12},
                                "step_delay_ms": {"type": "integer", "default": 40},
                            },
                            "required": [
                                "target",
                                "param_index",
                                "start_value",
                                "end_value",
                            ],
                        },
                    },
                },
            },
        ),
        Tool(
            name="insert_poly_grid_on_track",
            description=(
                "Insert Poly Grid on a track using deterministic browser matching. "
                "Optionally load a preset by name match right after insertion."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "track_index": {"type": "integer"},
                    "position": {
                        "type": "string",
                        "enum": ["after", "before"],
                        "default": "after",
                    },
                    "preset_name": {
                        "type": "string",
                        "description": "Optional preset name fragment to load after Poly Grid insert",
                    },
                    "max_result_pages": {"type": "integer", "default": 8},
                },
                "required": ["track_index"],
            },
        ),
        Tool(
            name="song_enhance_mix",
            description=(
                "Mixer pass: layout Mix, toggle sends strip, enable send 1 on a track range with wet level, "
                "add empty effect return tracks (load Reverb/Delay on them in Bitwig). "
                "Optionally nudge project remote slots 1-4 to mid values if mapped."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "first_track_index": {"type": "integer", "default": 1},
                    "last_track_index": {"type": "integer", "default": 8},
                    "send_index": {"type": "integer", "default": 1},
                    "send_level": {"type": "number", "default": 38},
                    "effect_returns_to_add": {"type": "integer", "default": 2},
                    "nudge_project_remotes": {
                        "type": "boolean",
                        "default": False,
                        "description": "If true, set remotes 1-4 to staggered values (map remotes in Bitwig first)",
                    },
                },
            },
        ),
        Tool(
            name="set_track_mute_state",
            description="Set track mute on or off (for drops/breakdowns without toggling)",
            inputSchema={
                "type": "object",
                "properties": {
                    "track_index": {
                        "type": "integer",
                        "description": "Track index (1-based, OSC bank)",
                    },
                    "muted": {
                        "type": "boolean",
                        "description": "True to mute, False to unmute",
                    },
                },
                "required": ["track_index", "muted"],
            },
        ),
        Tool(
            name="send_midi_note",
            description=(
                "Inject one MIDI note via Bitwig OSC virtual keyboard (configure MIDI port in "
                "OSC extension). Use velocity 0 for note-off. Useful while clip launcher overdub is on."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "channel": {
                        "type": "integer",
                        "description": "MIDI channel 1-16",
                    },
                    "note": {
                        "type": "integer",
                        "description": "MIDI note number 0-127",
                    },
                    "velocity": {
                        "type": "integer",
                        "description": "Velocity 0-127 (0 = note off)",
                    },
                },
                "required": ["channel", "note", "velocity"],
            },
        ),
        Tool(
            name="send_midi_drum",
            description="Send a drum note via /vkb_midi/.../drum (channel 1-16, note 0-127)",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel": {"type": "integer"},
                    "note": {"type": "integer"},
                    "velocity": {"type": "integer"},
                },
                "required": ["channel", "note", "velocity"],
            },
        ),
        Tool(
            name="send_midi_cc",
            description="Send MIDI CC to the virtual MIDI bridge (/vkb_midi/{ch}/cc/{cc})",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel": {"type": "integer"},
                    "cc": {"type": "integer"},
                    "value": {"type": "integer"},
                },
                "required": ["channel", "cc", "value"],
            },
        ),
        Tool(
            name="send_midi_program_change",
            description=(
                "Send MIDI Program Change (0-127) into Bitwig's virtual MIDI input. "
                "Select the drum track first; match MIDI channel to the track/device chain. "
                "Requires a DrivenByMoss build that handles /vkb_midi/{ch}/program. "
                "For drawn timeline automation, prefer automating Bitwig's 'MIDI Program Change' "
                "device or a Reaktor parameter if the host exposes one."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "channel": {"type": "integer", "description": "1-16"},
                    "program": {
                        "type": "integer",
                        "description": "Program number 0-127",
                    },
                },
                "required": ["channel", "program"],
            },
        ),
        Tool(
            name="send_midi_aftertouch_poly",
            description="Send poly aftertouch for a note",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel": {"type": "integer"},
                    "note": {"type": "integer"},
                    "pressure": {"type": "integer"},
                },
                "required": ["channel", "note", "pressure"],
            },
        ),
        Tool(
            name="send_midi_aftertouch_channel",
            description="Send channel aftertouch",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel": {"type": "integer"},
                    "pressure": {"type": "integer"},
                },
                "required": ["channel", "pressure"],
            },
        ),
        Tool(
            name="send_midi_pitchbend",
            description="Send pitch bend (0..127, center 64)",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel": {"type": "integer"},
                    "value": {"type": "integer"},
                },
                "required": ["channel", "value"],
            },
        ),
        Tool(
            name="set_vkb_fixed_velocity",
            description="Set fixed MIDI velocity (0 disables, 1..127 sets fixed value)",
            inputSchema={
                "type": "object",
                "properties": {"value": {"type": "integer"}},
                "required": ["value"],
            },
        ),
        Tool(
            name="set_vkb_note_repeat",
            description="Enable/disable note repeat and optionally set period/length",
            inputSchema={
                "type": "object",
                "properties": {
                    "active": {"type": "boolean"},
                    "period": {"type": "string"},
                    "length": {"type": "string"},
                },
                "required": ["active"],
            },
        ),
        Tool(
            name="play_midi_note_sequence",
            description=(
                "Play a timed sequence of MIDI notes: waits delay_ms before each step, then sends "
                "the note. Max 400 steps, max 120s total delay. Use for step-recording style patterns."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "notes": {
                        "type": "array",
                        "description": "Each item: delay_ms (optional, default 0), channel, note, velocity",
                        "items": {
                            "type": "object",
                            "properties": {
                                "delay_ms": {"type": "number"},
                                "channel": {"type": "integer"},
                                "note": {"type": "integer"},
                                "velocity": {"type": "integer"},
                            },
                            "required": ["channel", "note", "velocity"],
                        },
                    }
                },
                "required": ["notes"],
            },
        ),
        Tool(
            name="launcher_clip_select",
            description=(
                "Select a clip LAUNCHER slot (scene grid under the track in Arrange view), NOT a "
                "timeline clip. Indices are OSC bank 1-based. For horizontal timeline clips use "
                "set_playhead_beats + start_arranger_record or click the timeline and clip_create_at_cursor."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "track_index": {"type": "integer"},
                    "slot_index": {"type": "integer"},
                },
                "required": ["track_index", "slot_index"],
            },
        ),
        Tool(
            name="launcher_clip_create",
            description=(
                "Create a new clip in the LAUNCHER grid (session slots), not on the arranger "
                "timeline. Per OSC spec this starts recording/overdub; length_beats is clip length "
                "in quarter notes."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "track_index": {"type": "integer"},
                    "slot_index": {"type": "integer"},
                    "length_beats": {
                        "type": "number",
                        "description": "Clip length in quarter notes (e.g. 16 for four 4/4 bars)",
                    },
                },
                "required": ["track_index", "slot_index", "length_beats"],
            },
        ),
        Tool(
            name="launcher_clip_launch",
            description="Launch or release a launcher clip (launch true = press, false = release)",
            inputSchema={
                "type": "object",
                "properties": {
                    "track_index": {"type": "integer"},
                    "slot_index": {"type": "integer"},
                    "launch": {"type": "boolean"},
                },
                "required": ["track_index", "slot_index", "launch"],
            },
        ),
        Tool(
            name="launcher_clip_record",
            description="Arm/start recording into the specified launcher slot",
            inputSchema={
                "type": "object",
                "properties": {
                    "track_index": {"type": "integer"},
                    "slot_index": {"type": "integer"},
                },
                "required": ["track_index", "slot_index"],
            },
        ),
        Tool(
            name="launcher_clip_remove",
            description="Delete the clip in a launcher slot",
            inputSchema={
                "type": "object",
                "properties": {
                    "track_index": {"type": "integer"},
                    "slot_index": {"type": "integer"},
                },
                "required": ["track_index", "slot_index"],
            },
        ),
        Tool(
            name="launcher_clip_duplicate",
            description="Duplicate the clip in a launcher slot",
            inputSchema={
                "type": "object",
                "properties": {
                    "track_index": {"type": "integer"},
                    "slot_index": {"type": "integer"},
                },
                "required": ["track_index", "slot_index"],
            },
        ),
        Tool(
            name="launcher_clip_insert_file",
            description="Load an audio or MIDI file from disk into a launcher slot (absolute path)",
            inputSchema={
                "type": "object",
                "properties": {
                    "track_index": {"type": "integer"},
                    "slot_index": {"type": "integer"},
                    "filepath": {"type": "string"},
                },
                "required": ["track_index", "slot_index", "filepath"],
            },
        ),
        Tool(
            name="launcher_track_stop",
            description="Stop the playing launcher clip on a track",
            inputSchema={
                "type": "object",
                "properties": {"track_index": {"type": "integer"}},
                "required": ["track_index"],
            },
        ),
        Tool(
            name="launcher_track_return_to_arrangement",
            description="Return track playback from launcher to arrangement",
            inputSchema={
                "type": "object",
                "properties": {"track_index": {"type": "integer"}},
                "required": ["track_index"],
            },
        ),
        Tool(
            name="clips_stop_all",
            description="Stop all playing launcher clips",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="prepare_launcher_clip_slot",
            description=(
                "Before creating or loading a launcher clip: refresh OSC state, select the track, "
                "then select the slot. Call this (or insert_seed_midi_clip which includes it) if "
                "clips were not appearing."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "track_index": {"type": "integer"},
                    "slot_index": {"type": "integer"},
                },
                "required": ["track_index", "slot_index"],
            },
        ),
        Tool(
            name="toggle_arranger_clip_launcher_visible",
            description=(
                "Toggle visibility of the clip launcher strip in Arrange view. If you only see the "
                "timeline and no scene slots under tracks, run this once or twice until slots show."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="insert_seed_midi_clip",
            description=(
                "Load built-in MIDI via insertFile. Use bars=8 for 8-bar (8x) clips. "
                "drums_all_in_one_gm_8bar = full kit on one track (ch10); put Drum Machine on that track. "
                "Many patterns auto-map to _8bar companions when bars=8 (e.g. kick_four_on_floor -> "
                "kick_four_on_floor_8bar). See seed_midi.SEED_PATTERN_NAMES. "
                "IMPORTANT: track_index and slot_index refer to the current OSC track/clip BANK "
                "(the visible page in DrivenByMoss), not absolute project track order. Use "
                "navigate_track_bank previous with page=true several times, or scroll_bank_pages_previous, "
                "so indices 1..8 line up with the tracks you see. "
                "After loading, use open_track_device_browser + commit to insert Organ, Polymer, Drum Machine, Sampler."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "track_index": {"type": "integer"},
                    "slot_index": {"type": "integer"},
                    "pattern": {
                        "type": "string",
                        "description": "Pattern name; use drums_all_in_one_gm_8bar for single-track drums.",
                        "default": "kick_four_on_floor",
                    },
                    "bars": {
                        "type": "integer",
                        "description": "1 or 8; 8 selects long / companion pattern",
                        "default": 1,
                    },
                    "scroll_bank_pages_previous": {
                        "type": "integer",
                        "description": (
                            "Before insert: call navigate_track_bank(previous, page=true) this many times "
                            "to move the OSC bank toward the start of the project (best-effort)."
                        ),
                        "default": 0,
                    },
                    "post_prepare_delay_sec": {
                        "type": "number",
                        "description": "Seconds to wait after selecting the slot before insertFile (Bitwig UI sync).",
                        "default": 0.28,
                    },
                },
                "required": ["track_index", "slot_index"],
            },
        ),
        Tool(
            name="clip_create_at_cursor",
            description=(
                "Create a clip where Bitwig's cursor clip is (click a timeline or launcher slot "
                "first in Bitwig). Same as OSC /clip/create; length_beats in quarter notes. "
                "This is how you target the arranger timeline without OSC xy coordinates."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "length_beats": {"type": "number"},
                },
                "required": ["length_beats"],
            },
        ),
        Tool(
            name="clip_quantize_selected",
            description="Quantize the clip under the Bitwig cursor clip",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="clip_set_name_selected",
            description="Rename the clip under the Bitwig cursor clip",
            inputSchema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        ),
        Tool(
            name="toggle_clip_launcher_overdub",
            description="Toggle clip launcher overdub (for recording MIDI into playing clips)",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="toggle_arranger_overdub",
            description="Toggle arranger overdub",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="toggle_arranger_automation_write",
            description=(
                "Toggle arranger automation write (Bitwig transport). Same as clicking the "
                "automation arm button for the timeline. If unsure of current state, check Bitwig; "
                "this is a toggle, not an absolute on/off."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="toggle_launcher_automation_write",
            description="Toggle clip-launcher automation write",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="set_automation_write_mode",
            description=(
                "Set automation write mode via OSC /automationWriteMode (latch, touch, write, read, "
                "trim_read, latch_preview). Requires DrivenByMoss-style Bitwig OSC."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "description": "e.g. latch, touch, write, read, trim_read, latch_preview",
                    },
                },
                "required": ["mode"],
            },
        ),
        Tool(
            name="arranger_automation_sweep_session",
            description=(
                "Optional playback + automation mode, then same sweeps as apply_modulation_controls "
                "on the selected device. Select drum track and Reaktor (or target device) first. "
                "Device sweeps use automation_touch=true by default for Bitwig recording. "
                "Enable arranger automation write in Bitwig when needed, or pass "
                "toggle_arranger_autowrite_first=true to flip the toggle once before sweeps "
                "(dangerous if already armed). For recorded automation, transport should be "
                "playing (start_playback=true) and automation write on."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "automation_touch": {
                        "type": "boolean",
                        "default": True,
                        "description": "Passed through to apply_modulation_controls device handling",
                    },
                    "automation_write_mode": {
                        "type": "string",
                        "description": "If set, sent before sweeps (e.g. latch)",
                    },
                    "toggle_arranger_autowrite_first": {
                        "type": "boolean",
                        "default": False,
                        "description": "If true, send one /autowrite toggle before sweeps",
                    },
                    "start_playback": {
                        "type": "boolean",
                        "default": False,
                        "description": "If true, send play on before sweeps",
                    },
                    "device_params": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "param_index": {"type": "integer"},
                                "value": {"type": "number"},
                            },
                            "required": ["param_index", "value"],
                        },
                    },
                    "project_remotes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "param_index": {"type": "integer"},
                                "value": {"type": "number"},
                            },
                            "required": ["param_index", "value"],
                        },
                    },
                    "sweeps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "target": {
                                    "type": "string",
                                    "enum": ["device", "remote"],
                                },
                                "param_index": {"type": "integer"},
                                "start_value": {"type": "number"},
                                "end_value": {"type": "number"},
                                "steps": {"type": "integer", "default": 12},
                                "step_delay_ms": {"type": "integer", "default": 40},
                            },
                            "required": [
                                "target",
                                "param_index",
                                "start_value",
                                "end_value",
                            ],
                        },
                    },
                },
            },
        ),
        Tool(
            name="scene_add",
            description="Add a new empty scene at end of scene list",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="scene_launch",
            description="Launch or release a scene by bank index (1-based)",
            inputSchema={
                "type": "object",
                "properties": {
                    "scene_index": {"type": "integer"},
                    "launch": {"type": "boolean"},
                },
                "required": ["scene_index", "launch"],
            },
        ),
        Tool(
            name="set_device_parameter",
            description=(
                "Set value of a device parameter on the currently selected device (OSC slot index). "
                "Use automation_touch=true (default) to send /device/param/N/touched so Latch/Touch "
                "automation write records moves. Optional refresh_first requests /refresh first so "
                "Bitwig's OSC cache matches the UI."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "param_index": {
                        "type": "integer",
                        "description": "Parameter index (1-based)",
                    },
                    "value": {
                        "type": "number",
                        "description": "Parameter value (0-128)",
                    },
                    "automation_touch": {
                        "type": "boolean",
                        "default": True,
                        "description": "Send touched true/false around the value write for automation recording",
                    },
                    "refresh_first": {
                        "type": "boolean",
                        "default": False,
                        "description": "Send /refresh and wait briefly before writing the parameter",
                    },
                },
                "required": ["param_index", "value"],
            },
        ),
        Tool(
            name="select_device_page_slot",
            description="Select device parameter page slot 1-8 in current page bank",
            inputSchema={
                "type": "object",
                "properties": {"page_slot": {"type": "integer"}},
                "required": ["page_slot"],
            },
        ),
        Tool(
            name="navigate_device_param_page",
            description="Navigate device parameter pages (next/previous)",
            inputSchema={
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["next", "previous"],
                    }
                },
                "required": ["direction"],
            },
        ),
        Tool(
            name="navigate_device_param_bank_page",
            description="Navigate banks of 8 device pages (next/previous)",
            inputSchema={
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["next", "previous"],
                    }
                },
                "required": ["direction"],
            },
        ),
        Tool(
            name="set_device_parameter_on_page",
            description=(
                "Select device page slot and set one parameter there. "
                "Useful for plugins with many pages. Does not create pages or assign targets; "
                "those are Bitwig UI actions."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "page_slot": {"type": "integer"},
                    "param_index": {"type": "integer"},
                    "value": {"type": "number"},
                    "automation_touch": {
                        "type": "boolean",
                        "default": True,
                        "description": "Send touched true/false around the value write for automation recording",
                    },
                },
                "required": ["page_slot", "param_index", "value"],
            },
        ),
        Tool(
            name="set_device_page_params",
            description=(
                "Optionally select a device parameter page, then set many /device/param slots "
                "(param_index 1..page size, value 0-128) in one call. Use after you built the "
                "page in Bitwig. OSC cannot create parameter pages or bind slots to plugin "
                "parameters; use scan_device_pages_and_params to discover names after mapping."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "page_slot": {
                        "type": "integer",
                        "description": "If set, select this page in the current bank (1-based)",
                    },
                    "automation_touch": {
                        "type": "boolean",
                        "default": True,
                        "description": "Wrap each set with /device/param/N/touched for automation write",
                    },
                    "params": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "param_index": {"type": "integer"},
                                "value": {"type": "number"},
                            },
                            "required": ["param_index", "value"],
                        },
                    },
                },
                "required": ["params"],
            },
        ),
        Tool(
            name="scan_device_pages_and_params",
            description=(
                "Deep scan of device parameter pages by walking bank pages and collecting "
                "page/param names, values, modulated values, and availability hints. "
                "Read-only for layout: cannot create pages or remap slot targets via OSC."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "max_bank_steps": {
                        "type": "integer",
                        "default": 8,
                        "description": "Maximum bank pages to scan",
                    },
                    "restore_initial_selection": {
                        "type": "boolean",
                        "default": True,
                    },
                    "max_params_per_page": {
                        "type": "integer",
                        "default": 64,
                        "description": "How many parameter slots to inspect per scanned page",
                    },
                    "include_unavailable": {
                        "type": "boolean",
                        "default": False,
                        "description": "Include unavailable placeholder slots in output",
                    },
                },
            },
        ),
        Tool(
            name="warmup_device_parameter_map",
            description=(
                "Force-warm device page/parameter access by cycling page slots and probing a "
                "parameter range with alternating values before scanning."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "track_index": {
                        "type": "integer",
                        "description": "Optional track to select before warmup",
                    },
                    "max_bank_steps": {
                        "type": "integer",
                        "default": 8,
                        "description": "How many page banks to walk",
                    },
                    "page_slots_per_bank": {
                        "type": "integer",
                        "default": 8,
                        "description": "How many slots to probe in each bank",
                    },
                    "param_probe_start": {
                        "type": "integer",
                        "default": 1,
                    },
                    "param_probe_end": {
                        "type": "integer",
                        "default": 8,
                    },
                    "low_value": {
                        "type": "number",
                        "default": 24,
                    },
                    "high_value": {
                        "type": "number",
                        "default": 104,
                    },
                    "settle_ms": {
                        "type": "integer",
                        "default": 35,
                        "description": "Delay between probe writes",
                    },
                    "restore_initial_selection": {
                        "type": "boolean",
                        "default": True,
                    },
                },
            },
        ),
        Tool(
            name="read_last_touched_device_parameter",
            description="Read details of the last hovered/clicked device parameter from Bitwig.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="set_last_touched_device_parameter",
            description=(
                "Set value (0..128) of the last hovered/clicked device parameter. "
                "Use automation_touch=true (default) for automation write modes that need touched state."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "value": {"type": "number"},
                    "automation_touch": {
                        "type": "boolean",
                        "default": True,
                        "description": "Send lastparam touched around the value write",
                    },
                },
                "required": ["value"],
            },
        ),
        Tool(
            name="reset_last_touched_device_parameter",
            description="Reset the last hovered/clicked device parameter to default.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="set_track_remote_parameter",
            description="Set selected track remote parameter (1..8) by track bank index",
            inputSchema={
                "type": "object",
                "properties": {
                    "track_index": {"type": "integer"},
                    "param_index": {"type": "integer"},
                    "value": {"type": "number"},
                },
                "required": ["track_index", "param_index", "value"],
            },
        ),
        Tool(
            name="toggle_device_bypass",
            description="Toggle bypass state of the currently selected device",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="select_device_sibling",
            description="Select a sibling device (in the same chain as current device)",
            inputSchema={
                "type": "object",
                "properties": {
                    "sibling_index": {
                        "type": "integer",
                        "description": "Index of the sibling device (1-8)",
                    },
                },
                "required": ["sibling_index"],
            },
        ),
        Tool(
            name="navigate_device",
            description="Navigate to next/previous device",
            inputSchema={
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["next", "previous"],
                        "description": "Navigation direction",
                    },
                },
                "required": ["direction"],
            },
        ),
        Tool(
            name="enter_device_layer",
            description="Enter a device layer/chain",
            inputSchema={
                "type": "object",
                "properties": {
                    "layer_index": {
                        "type": "integer",
                        "description": "Index of the layer to enter (1-8)",
                    },
                },
                "required": ["layer_index"],
            },
        ),
        Tool(
            name="exit_device_layer",
            description="Exit current device layer (go to parent)",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="toggle_device_window",
            description="Toggle device window visibility",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        # Browser tools
        Tool(
            name="browse_insert_device",
            description="Open browser to insert a device after the selected device",
            inputSchema={
                "type": "object",
                "properties": {
                    "position": {
                        "type": "string",
                        "enum": ["after", "before"],
                        "description": "Position to insert device (before or after selected device)",
                        "default": "after",
                    },
                },
            },
        ),
        Tool(
            name="browse_device_presets",
            description="Open browser to browse presets for the selected device",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="commit_browser_selection",
            description="Commit the current selection in the browser",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="cancel_browser",
            description="Cancel the current browser session",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="navigate_browser_tab",
            description="Navigate to next or previous browser tab",
            inputSchema={
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["next", "previous"],
                        "description": "Navigation direction",
                    },
                },
                "required": ["direction"],
            },
        ),
        Tool(
            name="navigate_browser_filter",
            description="Navigate through filter options in the browser",
            inputSchema={
                "type": "object",
                "properties": {
                    "filter_index": {
                        "type": "integer",
                        "description": "Index of the filter column (1-6)",
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["next", "previous"],
                        "description": "Navigation direction",
                    },
                },
                "required": ["filter_index", "direction"],
            },
        ),
        Tool(
            name="reset_browser_filter",
            description="Reset a browser filter column",
            inputSchema={
                "type": "object",
                "properties": {
                    "filter_index": {
                        "type": "integer",
                        "description": "Index of the filter column to reset (1-6)",
                    },
                },
                "required": ["filter_index"],
            },
        ),
        Tool(
            name="navigate_browser_result",
            description="Navigate through browser results",
            inputSchema={
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["next", "previous"],
                        "description": "Navigation direction",
                    },
                },
                "required": ["direction"],
            },
        ),
        Tool(
            name="device_browser_workflow",
            description="Complete workflow for browsing and inserting a device",
            inputSchema={
                "type": "object",
                "properties": {
                    "position": {
                        "type": "string",
                        "enum": ["after", "before"],
                        "description": "Position to insert device (before or after selected device)",
                        "default": "after",
                    },
                    "num_tab_navigations": {
                        "type": "integer",
                        "description": "Number of tab navigations (+ for next, - for previous)",
                        "default": 0,
                    },
                    "filter_navigations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "filter_index": {
                                    "type": "integer",
                                    "description": "Index of the filter column (1-6)",
                                },
                                "steps": {
                                    "type": "integer",
                                    "description": "Number of navigation steps (+ for next, - for previous)",
                                },
                            },
                            "required": ["filter_index", "steps"],
                        },
                        "description": "List of filter navigation operations",
                    },
                    "result_navigations": {
                        "type": "integer",
                        "description": "Number of result navigations (+ for next, - for previous)",
                        "default": 0,
                    },
                },
            },
        ),
        Tool(
            name="preset_browser_workflow",
            description="Complete workflow for browsing and loading a preset",
            inputSchema={
                "type": "object",
                "properties": {
                    "filter_navigations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "filter_index": {
                                    "type": "integer",
                                    "description": "Index of the filter column (1-6)",
                                },
                                "steps": {
                                    "type": "integer",
                                    "description": "Number of navigation steps (+ for next, - for previous)",
                                },
                            },
                            "required": ["filter_index", "steps"],
                        },
                        "description": "List of filter navigation operations",
                    },
                    "result_navigations": {
                        "type": "integer",
                        "description": "Number of result navigations (+ for next, - for previous)",
                        "default": 0,
                    },
                },
            },
        ),
    ]


def _clamp_osc_value(value: float) -> float:
    return max(0.0, min(128.0, float(value)))


_AUTOMATION_WRITE_MODE_ALIASES = {
    "trim_read": "TRIM_READ",
    "trim": "TRIM_READ",
    "read": "READ",
    "touch": "TOUCH",
    "latch": "LATCH",
    "latch_preview": "LATCH_PREVIEW",
    "latchpreview": "LATCH_PREVIEW",
    "preview": "LATCH_PREVIEW",
    "write": "WRITE",
}


def _normalize_automation_write_mode(mode: str) -> str:
    key = mode.strip().lower().replace(" ", "_").replace("/", "_")
    if key in _AUTOMATION_WRITE_MODE_ALIASES:
        return _AUTOMATION_WRITE_MODE_ALIASES[key]
    upper = mode.strip().upper().replace(" ", "_")
    if upper in (
        "TRIM_READ",
        "READ",
        "TOUCH",
        "LATCH",
        "LATCH_PREVIEW",
        "WRITE",
    ):
        return upper
    raise ValueError(
        f"Unknown automation write mode {mode!r}; use latch, touch, write, read, trim_read, "
        "latch_preview"
    )


_TOUCH_GAP_SEC = 0.012


async def _apply_modulation_payload(
    controller: BitwigOSCController, arguments: Dict[str, Any]
) -> tuple[int, int, int]:
    """Apply device_params, project_remotes, and sweeps (same semantics as apply_modulation_controls)."""
    device_params = arguments.get("device_params", []) or []
    project_remotes = arguments.get("project_remotes", []) or []
    sweeps = arguments.get("sweeps", []) or []
    automation_touch = bool(arguments.get("automation_touch", True))

    for entry in device_params:
        pi = int(entry.get("param_index"))
        val = _clamp_osc_value(float(entry.get("value")))
        if automation_touch:
            controller.client.set_device_parameter_touched(pi, True)
            await asyncio.sleep(_TOUCH_GAP_SEC)
        controller.client.set_device_parameter(pi, val)
        if automation_touch:
            await asyncio.sleep(_TOUCH_GAP_SEC)
            controller.client.set_device_parameter_touched(pi, False)

    for entry in project_remotes:
        pi = int(entry.get("param_index"))
        val = _clamp_osc_value(float(entry.get("value")))
        controller.client.set_project_remote_control_value(pi, val)

    for sweep in sweeps:
        target = str(sweep.get("target", "device"))
        pi = int(sweep.get("param_index"))
        v0 = _clamp_osc_value(float(sweep.get("start_value")))
        v1 = _clamp_osc_value(float(sweep.get("end_value")))
        steps = int(sweep.get("steps", 12))
        delay_ms = int(sweep.get("step_delay_ms", 40))
        steps = max(1, min(steps, 256))
        delay_ms = max(0, min(delay_ms, 5000))
        device_sweep = target != "remote" and automation_touch
        if device_sweep:
            controller.client.set_device_parameter_touched(pi, True)
            await asyncio.sleep(_TOUCH_GAP_SEC)
        try:
            for i in range(steps + 1):
                alpha = i / max(1, steps)
                val = _clamp_osc_value(v0 + (v1 - v0) * alpha)
                if target == "remote":
                    controller.client.set_project_remote_control_value(pi, val)
                else:
                    controller.client.set_device_parameter(pi, val)
                if i < steps and delay_ms > 0:
                    await asyncio.sleep(delay_ms / 1000.0)
        finally:
            if device_sweep:
                await asyncio.sleep(_TOUCH_GAP_SEC)
                controller.client.set_device_parameter_touched(pi, False)

    return len(device_params), len(project_remotes), len(sweeps)


async def _browser_refresh(controller: BitwigOSCController, delay_sec: float = 0.12) -> None:
    controller.client.refresh()
    await asyncio.sleep(delay_sec)


def _browser_filter_items(
    controller: BitwigOSCController, filter_index: int, max_items: int = 64
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for i in range(1, max_items + 1):
        exists = controller.server.get_message(
            f"/browser/filter/{filter_index}/item/{i}/exists"
        )
        if not exists:
            continue
        out.append(
            {
                "index": i,
                "name": str(
                    controller.server.get_message(
                        f"/browser/filter/{filter_index}/item/{i}/name"
                    )
                    or ""
                ),
                "selected": bool(
                    controller.server.get_message(
                        f"/browser/filter/{filter_index}/item/{i}/isSelected"
                    )
                ),
            }
        )
    return out


async def _set_filter_item_by_name(
    controller: BitwigOSCController, filter_index: int, target_name: str
) -> bool:
    if not target_name:
        return False
    target_norm = target_name.strip().lower()
    for _ in range(40):
        await _browser_refresh(controller)
        items = _browser_filter_items(controller, filter_index)
        if not items:
            return False
        selected_idx = next((x["index"] for x in items if x["selected"]), 1)
        match = next(
            (
                x
                for x in items
                if x["name"].strip().lower() == target_norm
                or target_norm in x["name"].strip().lower()
            ),
            None,
        )
        if match is None:
            return False
        if match["index"] == selected_idx:
            return True
        direction = "+" if match["index"] > selected_idx else "-"
        controller.client.navigate_browser_filter(filter_index, direction)
    return False


def _browser_results(
    controller: BitwigOSCController, max_results: int = 16
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for i in range(1, max_results + 1):
        exists = controller.server.get_message(f"/browser/result/{i}/exists")
        if not exists:
            continue
        out.append(
            {
                "index": i,
                "name": str(controller.server.get_message(f"/browser/result/{i}/name") or ""),
                "selected": bool(
                    controller.server.get_message(f"/browser/result/{i}/isSelected")
                ),
            }
        )
    return out


def _score_result_name(name: str, query: str) -> int:
    n = name.lower().strip()
    q = query.lower().strip()
    if n == q:
        return 0
    if n.startswith(q):
        return 1
    if q in n:
        return 2
    tokens = [t for t in re.split(r"[^a-z0-9]+", q) if t]
    if tokens and all(t in n for t in tokens):
        return 3
    return 99


async def _seek_and_select_browser_result(
    controller: BitwigOSCController, query: str, max_pages: int
) -> Optional[Dict[str, Any]]:
    for _ in range(10):
        controller.client.navigate_browser_result_page("-")
        await _browser_refresh(controller, 0.05)

    best: Optional[Dict[str, Any]] = None
    best_page = 0
    for page in range(max_pages):
        await _browser_refresh(controller)
        results = _browser_results(controller)
        if not results:
            break
        ranked = []
        for row in results:
            score = _score_result_name(row["name"], query)
            if score < 99:
                ranked.append((score, row))
        if ranked:
            ranked.sort(key=lambda x: x[0])
            best = ranked[0][1]
            best_page = page
            break
        controller.client.navigate_browser_result_page("+")
        await _browser_refresh(controller, 0.08)

    if best is None:
        return None

    selected_idx = 1
    for row in _browser_results(controller):
        if row["selected"]:
            selected_idx = int(row["index"])
            break
    target_idx = int(best["index"])
    if target_idx != selected_idx:
        direction = "+" if target_idx > selected_idx else "-"
        for _ in range(abs(target_idx - selected_idx)):
            controller.client.navigate_browser_result(direction)
            await _browser_refresh(controller, 0.04)

    return {"page": best_page, "index": target_idx, "name": best["name"]}


async def _refresh_state(controller: BitwigOSCController, delay_sec: float = 0.1) -> None:
    controller.client.refresh()
    await asyncio.sleep(delay_sec)


def _device_page_slots(controller: BitwigOSCController) -> List[Dict[str, Any]]:
    slots: List[Dict[str, Any]] = []
    max_slots = max(8, int(getattr(controller.client, "osc_bank_page_size", 64)))
    for i in range(1, max_slots + 1):
        exists = bool(controller.server.get_message(f"/device/page/{i}/exists"))
        if not exists:
            continue
        slots.append(
            {
                "slot": i,
                "name": str(controller.server.get_message(f"/device/page/{i}/name") or ""),
                "selected": bool(
                    controller.server.get_message(f"/device/page/{i}/selected")
                ),
            }
        )
    return slots


def _read_device_param_slots(
    controller: BitwigOSCController, max_params: int
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    max_params = max(1, min(int(max_params), 512))
    for i in range(1, max_params + 1):
        exists = bool(controller.server.get_message(f"/device/param/{i}/exists"))
        raw_name = controller.server.get_message(f"/device/param/{i}/name")
        raw_value = controller.server.get_message(f"/device/param/{i}/value")
        raw_value_str = controller.server.get_message(f"/device/param/{i}/valueStr")
        raw_mod = controller.server.get_message(f"/device/param/{i}/modulatedValue")
        name = str(raw_name or "").strip()
        value_str = str(raw_value_str or "").strip()
        available = bool(
            exists
            or name
            or raw_value is not None
            or value_str
            or raw_mod is not None
            or bool(controller.server.get_message(f"/device/param/{i}/available"))
        )
        out.append(
            {
                "index": i,
                "exists": exists,
                "available": available,
                "name": name or f"Param {i}",
                "value": raw_value,
                "value_str": value_str,
                "modulated_value": raw_mod,
            }
        )
    return out


def _read_device_params_with_mod(controller: BitwigOSCController) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    max_params = max(8, int(getattr(controller.client, "osc_bank_page_size", 64)))
    for row in _read_device_param_slots(controller, max_params):
        if row["exists"] or row["available"]:
            out.append(
                {
                    "index": row["index"],
                    "name": row["name"],
                    "value": row["value"],
                    "value_str": row["value_str"],
                    "modulated_value": row["modulated_value"],
                    "available": row["available"],
                    "exists": row["exists"],
                }
            )
    return out


async def execute_tool(
    controller: BitwigOSCController, name: str, arguments: Dict[str, Any]
) -> List[TextContent]:
    """Execute a Bitwig tool

    Args:
        controller: BitwigOSCController instance
        name: Tool name to execute
        arguments: Tool arguments

    Returns:
        List of TextContent with results

    Raises:
        ValueError: If tool name is unknown or arguments are invalid
    """
    try:
        if name == "transport_play":
            controller.client.play()
            return [TextContent(type="text", text="Transport play/pause toggled")]

        elif name == "transport_stop":
            controller.client.stop()
            return [TextContent(type="text", text="Transport stopped")]

        elif name == "set_playhead_beats":
            beats = arguments.get("beats")
            if beats is None:
                raise ValueError("Missing required argument: beats")
            controller.client.set_playhead_beats(float(beats))
            return [
                TextContent(type="text", text=f"Playhead set to {float(beats)} beats")
            ]

        elif name == "start_arranger_record":
            controller.client.start_arranger_record()
            return [TextContent(type="text", text="Arranger record started")]

        elif name == "set_tempo":
            bpm = arguments.get("bpm")
            if bpm is None:
                raise ValueError("Missing required argument: bpm")

            if not isinstance(bpm, (int, float)) or bpm < 0 or bpm > 666:
                raise ValueError("Invalid tempo value: must be between 0 and 666")

            controller.client.set_tempo(bpm)
            return [TextContent(type="text", text=f"Tempo set to {bpm} BPM")]

        elif name == "set_track_volume":
            track_index = arguments.get("track_index")
            volume = arguments.get("volume")

            if track_index is None or volume is None:
                raise ValueError("Missing required arguments: track_index, volume")

            if not isinstance(track_index, int) or track_index < 1:
                raise ValueError("Invalid track_index: must be a positive integer")

            if not isinstance(volume, (int, float)) or volume < 0 or volume > 128:
                raise ValueError("Invalid volume: must be between 0 and 128")

            controller.client.set_track_volume(track_index, volume)
            return [
                TextContent(
                    type="text", text=f"Track {track_index} volume set to {volume}"
                )
            ]

        elif name == "set_track_pan":
            track_index = arguments.get("track_index")
            pan = arguments.get("pan")

            if track_index is None or pan is None:
                raise ValueError("Missing required arguments: track_index, pan")

            if not isinstance(track_index, int) or track_index < 1:
                raise ValueError("Invalid track_index: must be a positive integer")

            if not isinstance(pan, (int, float)) or pan < 0 or pan > 128:
                raise ValueError("Invalid pan: must be between 0 and 128")

            controller.client.set_track_pan(track_index, pan)
            return [
                TextContent(type="text", text=f"Track {track_index} pan set to {pan}")
            ]

        elif name == "toggle_track_mute":
            track_index = arguments.get("track_index")

            if track_index is None:
                raise ValueError("Missing required argument: track_index")

            if not isinstance(track_index, int) or track_index < 1:
                raise ValueError("Invalid track_index: must be a positive integer")

            controller.client.toggle_track_mute(track_index)
            return [TextContent(type="text", text=f"Track {track_index} mute toggled")]

        elif name == "add_instrument_track":
            controller.client.add_track_instrument()
            return [TextContent(type="text", text="Added instrument track")]

        elif name == "add_audio_track":
            controller.client.add_track_audio()
            return [TextContent(type="text", text="Added audio track")]

        elif name == "add_effect_track":
            controller.client.add_track_effect()
            return [TextContent(type="text", text="Added effect track")]

        elif name == "select_track":
            t = arguments.get("track_index")
            if t is None:
                raise ValueError("Missing track_index")
            controller.client.select_track(int(t))
            return [TextContent(type="text", text=f"Selected track {t}")]

        elif name == "navigate_track_selection":
            direction = arguments.get("direction")
            if direction not in ("next", "previous"):
                raise ValueError("direction must be 'next' or 'previous'")
            controller.client.navigate_track_selection(direction)
            return [
                TextContent(
                    type="text", text=f"Track selection: {direction}"
                )
            ]

        elif name == "navigate_track_bank":
            direction = arguments.get("direction")
            if direction not in ("next", "previous"):
                raise ValueError("direction must be 'next' or 'previous'")
            page = bool(arguments.get("page", False))
            controller.client.navigate_track_bank(direction, page=page)
            mode = "page" if page else "step"
            return [
                TextContent(
                    type="text",
                    text=f"Track bank {mode}: {direction}",
                )
            ]

        elif name == "toggle_track_bank_mode":
            controller.client.toggle_track_bank_mode()
            return [TextContent(type="text", text="Toggled track bank mode")]

        elif name == "set_track_name":
            t, n = arguments.get("track_index"), arguments.get("name")
            if t is None or n is None:
                raise ValueError("Missing track_index or name")
            controller.client.set_track_name(int(t), str(n))
            return [TextContent(type="text", text=f"Track {t} renamed")]

        elif name == "set_track_record_arm":
            t, armed = arguments.get("track_index"), arguments.get("armed")
            if t is None or armed is None:
                raise ValueError("Missing track_index or armed")
            if not isinstance(armed, bool):
                raise ValueError("armed must be a boolean")
            controller.client.set_track_record_arm(int(t), armed)
            state = "armed" if armed else "disarmed"
            return [TextContent(type="text", text=f"Track {t} record {state}")]

        elif name == "set_track_solo":
            t, solo = arguments.get("track_index"), arguments.get("solo")
            if t is None or solo is None:
                raise ValueError("Missing track_index or solo")
            if not isinstance(solo, bool):
                raise ValueError("solo must be a boolean")
            controller.client.set_track_solo(int(t), solo)
            state = "soloed" if solo else "unsoloed"
            return [TextContent(type="text", text=f"Track {t} {state}")]

        elif name == "duplicate_track":
            t = arguments.get("track_index")
            if t is None:
                raise ValueError("Missing track_index")
            controller.client.duplicate_track(int(t))
            return [TextContent(type="text", text=f"Duplicated track {t}")]

        elif name == "remove_track":
            t = arguments.get("track_index")
            if t is None:
                raise ValueError("Missing track_index")
            controller.client.remove_track(int(t))
            return [TextContent(type="text", text=f"Removed track {t}")]

        elif name == "set_layout":
            layout = arguments.get("layout")
            if layout not in ("arrange", "mix", "edit"):
                raise ValueError("layout must be arrange, mix, or edit")
            controller.client.set_layout(str(layout))
            return [TextContent(type="text", text=f"Layout: {layout}")]

        elif name == "toggle_mixer_sends_section":
            controller.client.toggle_mixer_sends_section()
            return [
                TextContent(
                    type="text",
                    text="Toggled mixer sends section visibility",
                )
            ]

        elif name == "set_track_send":
            t = arguments.get("track_index")
            if t is None:
                raise ValueError("Missing track_index")
            sidx = int(arguments.get("send_index", 1))
            vol = float(arguments.get("volume", 40))
            if arguments.get("enable", True):
                controller.client.enable_track_send(int(t), sidx)
            controller.client.set_track_send_volume(int(t), sidx, vol)
            return [
                TextContent(
                    type="text",
                    text=f"Track {t} send {sidx} set to {vol}",
                )
            ]

        elif name == "set_project_remote_control":
            pi = arguments.get("param_index")
            val = arguments.get("value")
            if pi is None or val is None:
                raise ValueError("Missing param_index or value")
            controller.client.set_project_remote_control_value(int(pi), float(val))
            return [
                TextContent(
                    type="text",
                    text=f"Project remote {pi} -> {val}",
                )
            ]

        elif name == "open_track_device_browser":
            t = arguments.get("track_index")
            if t is None:
                raise ValueError("Missing track_index")
            pos = arguments.get("position", "after")
            if pos not in ("after", "before"):
                raise ValueError("position must be after or before")
            controller.client.open_track_device_browser(int(t), str(pos))
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Opened device browser on track {t} ({pos}). "
                        "In Bitwig: find Drum Machine / Organ / Polymer / Sampler, commit."
                    ),
                )
            ]

        elif name == "assign_track_instrument":
            t = arguments.get("track_index")
            instrument_name = arguments.get("instrument_name")
            if t is None or not instrument_name:
                raise ValueError("Missing track_index or instrument_name")
            pos = str(arguments.get("position", "after"))
            if pos not in ("after", "before"):
                raise ValueError("position must be after or before")
            category_filter = str(arguments.get("category_filter", "Instrument"))
            creator_filter = arguments.get("creator_filter")
            location_filter = arguments.get("location_filter")
            max_pages = int(arguments.get("max_result_pages", 8))
            max_pages = max(1, min(max_pages, 20))

            controller.client.open_track_device_browser(int(t), pos)
            await _browser_refresh(controller, 0.2)

            if location_filter:
                await _set_filter_item_by_name(controller, 1, str(location_filter))
            controller.client.reset_browser_filter(2)
            await _browser_refresh(controller, 0.08)
            if category_filter:
                await _set_filter_item_by_name(controller, 3, category_filter)
            if creator_filter:
                await _set_filter_item_by_name(controller, 5, str(creator_filter))

            match = await _seek_and_select_browser_result(
                controller, str(instrument_name), max_pages=max_pages
            )
            if match is None:
                await _browser_refresh(controller, 0.05)
                preview = _browser_results(controller)
                preview_names = ", ".join(x["name"] for x in preview[:8]) or "none"
                return [
                    TextContent(
                        type="text",
                        text=(
                            f"No browser result matched {instrument_name!r} on track {t}. "
                            f"Visible results: {preview_names}"
                        ),
                    )
                ]

            controller.client.commit_browser_selection()
            await _browser_refresh(controller, 0.15)
            device_name = controller.server.get_message("/device/name")
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Track {t}: matched result {match['name']!r} (page {match['page'] + 1}, "
                        f"slot {match['index']}) and committed. Active device: {device_name!r}"
                    ),
                )
            ]

        elif name == "apply_modulation_controls":
            dp, pr, sw = await _apply_modulation_payload(controller, arguments)
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Applied modulation controls: device_params={dp}, "
                        f"project_remotes={pr}, sweeps={sw}"
                    ),
                )
            ]

        elif name == "toggle_arranger_automation_write":
            controller.client.toggle_write_arranger_automation()
            return [
                TextContent(
                    type="text",
                    text="Toggled arranger automation write (/autowrite)",
                )
            ]

        elif name == "toggle_launcher_automation_write":
            controller.client.toggle_write_launcher_automation()
            return [
                TextContent(
                    type="text",
                    text="Toggled launcher automation write (/autowrite/launcher)",
                )
            ]

        elif name == "set_automation_write_mode":
            mode_arg = arguments.get("mode")
            if mode_arg is None:
                raise ValueError("Missing mode")
            osc_mode = _normalize_automation_write_mode(str(mode_arg))
            controller.client.set_automation_write_mode(osc_mode)
            return [
                TextContent(
                    type="text",
                    text=f"Automation write mode set to {osc_mode}",
                )
            ]

        elif name == "arranger_automation_sweep_session":
            mode_arg = arguments.get("automation_write_mode")
            if mode_arg:
                osc_mode = _normalize_automation_write_mode(str(mode_arg))
                controller.client.set_automation_write_mode(osc_mode)
            if bool(arguments.get("toggle_arranger_autowrite_first")):
                controller.client.toggle_write_arranger_automation()
            if bool(arguments.get("start_playback")):
                controller.client.play(True)
            dp, pr, sw = await _apply_modulation_payload(controller, arguments)
            parts = [
                f"device_params={dp}, project_remotes={pr}, sweeps={sw}",
            ]
            if mode_arg:
                parts.append(f"mode={_normalize_automation_write_mode(str(mode_arg))}")
            if bool(arguments.get("start_playback")):
                parts.append("play=true")
            if bool(arguments.get("toggle_arranger_autowrite_first")):
                parts.append("autowrite_toggled_once")
            return [
                TextContent(
                    type="text",
                    text="Arranger automation sweep session: " + "; ".join(parts),
                )
            ]

        elif name == "insert_poly_grid_on_track":
            t = arguments.get("track_index")
            if t is None:
                raise ValueError("Missing track_index")
            pos = str(arguments.get("position", "after"))
            if pos not in ("after", "before"):
                raise ValueError("position must be after or before")
            max_pages = int(arguments.get("max_result_pages", 8))
            max_pages = max(1, min(max_pages, 20))
            preset_name = arguments.get("preset_name")

            controller.client.open_track_device_browser(int(t), pos)
            await _browser_refresh(controller, 0.2)
            await _set_filter_item_by_name(controller, 3, "Instrument")
            await _set_filter_item_by_name(controller, 5, "Bitwig")

            poly_match = await _seek_and_select_browser_result(
                controller, "Poly Grid", max_pages=max_pages
            )
            if poly_match is None:
                return [
                    TextContent(
                        type="text",
                        text="Could not find Poly Grid in browser results",
                    )
                ]

            controller.client.commit_browser_selection()
            await _browser_refresh(controller, 0.2)
            active = controller.server.get_message("/device/name")

            preset_msg = "no preset requested"
            if preset_name:
                controller.client.browse_for_preset()
                await _browser_refresh(controller, 0.12)
                preset_match = await _seek_and_select_browser_result(
                    controller, str(preset_name), max_pages=max_pages
                )
                if preset_match is None:
                    preset_msg = f"preset {preset_name!r} not found"
                    controller.client.cancel_browser()
                else:
                    controller.client.commit_browser_selection()
                    preset_msg = f"preset committed: {preset_match['name']!r}"
                    await _browser_refresh(controller, 0.12)

            return [
                TextContent(
                    type="text",
                    text=(
                        f"Track {t}: inserted Poly Grid (matched {poly_match['name']!r}), "
                        f"active device now {active!r}; {preset_msg}"
                    ),
                )
            ]

        elif name == "song_enhance_mix":
            controller.client.refresh()
            controller.client.set_layout("mix")
            controller.client.toggle_mixer_sends_section()
            first = int(arguments.get("first_track_index", 1))
            last = int(arguments.get("last_track_index", 8))
            sidx = int(arguments.get("send_index", 1))
            level = float(arguments.get("send_level", 38))
            for t in range(first, last + 1):
                controller.client.enable_track_send(t, sidx)
                controller.client.set_track_send_volume(t, sidx, level)
            nfx = int(arguments.get("effect_returns_to_add", 2))
            for _ in range(max(0, nfx)):
                controller.client.add_track_effect()
            if arguments.get("nudge_project_remotes", False):
                for i, v in enumerate((42, 50, 58, 66), start=1):
                    controller.client.set_project_remote_control_value(i, float(v))
            msg = (
                f"Mix layout, sends toggled, tracks {first}-{last} send {sidx} ~{level}, "
                f"added {max(0, nfx)} effect return(s). Load Reverb/Delay on returns; map project remotes in Bitwig."
            )
            return [TextContent(type="text", text=msg)]

        elif name == "set_track_mute_state":
            track_index = arguments.get("track_index")
            muted = arguments.get("muted")
            if track_index is None or muted is None:
                raise ValueError("Missing required arguments: track_index, muted")
            if not isinstance(track_index, int) or track_index < 1:
                raise ValueError("Invalid track_index: must be a positive integer")
            if not isinstance(muted, bool):
                raise ValueError("Invalid muted: must be a boolean")
            controller.client.set_track_mute(track_index, muted)
            state = "muted" if muted else "unmuted"
            return [
                TextContent(
                    type="text", text=f"Track {track_index} {state}"
                )
            ]

        elif name == "send_midi_note":
            ch = arguments.get("channel")
            note = arguments.get("note")
            vel = arguments.get("velocity")
            if ch is None or note is None or vel is None:
                raise ValueError("Missing required arguments: channel, note, velocity")
            controller.client.send_midi_note(int(ch), int(note), int(vel))
            return [
                TextContent(
                    type="text",
                    text=f"MIDI ch{ch} note {note} velocity {vel}",
                )
            ]

        elif name == "send_midi_drum":
            ch = arguments.get("channel")
            note = arguments.get("note")
            vel = arguments.get("velocity")
            if ch is None or note is None or vel is None:
                raise ValueError("Missing required arguments: channel, note, velocity")
            controller.client.send_midi_drum(int(ch), int(note), int(vel))
            return [
                TextContent(
                    type="text",
                    text=f"Drum ch{ch} note {note} velocity {vel}",
                )
            ]

        elif name == "send_midi_cc":
            ch = arguments.get("channel")
            cc = arguments.get("cc")
            val = arguments.get("value")
            if ch is None or cc is None or val is None:
                raise ValueError("Missing required arguments: channel, cc, value")
            controller.client.send_midi_cc(int(ch), int(cc), int(val))
            return [
                TextContent(
                    type="text",
                    text=f"MIDI CC ch{ch} cc{cc} value {val}",
                )
            ]

        elif name == "send_midi_program_change":
            ch = arguments.get("channel")
            prog = arguments.get("program")
            if ch is None or prog is None:
                raise ValueError("Missing required arguments: channel, program")
            controller.client.send_midi_program_change(int(ch), int(prog))
            return [
                TextContent(
                    type="text",
                    text=f"MIDI Program Change ch{ch} program {prog}",
                )
            ]

        elif name == "send_midi_aftertouch_poly":
            ch = arguments.get("channel")
            note = arguments.get("note")
            pressure = arguments.get("pressure")
            if ch is None or note is None or pressure is None:
                raise ValueError("Missing required arguments: channel, note, pressure")
            controller.client.send_midi_aftertouch_poly(
                int(ch), int(note), int(pressure)
            )
            return [
                TextContent(
                    type="text",
                    text=f"Poly aftertouch ch{ch} note {note} pressure {pressure}",
                )
            ]

        elif name == "send_midi_aftertouch_channel":
            ch = arguments.get("channel")
            pressure = arguments.get("pressure")
            if ch is None or pressure is None:
                raise ValueError("Missing required arguments: channel, pressure")
            controller.client.send_midi_aftertouch_channel(int(ch), int(pressure))
            return [
                TextContent(
                    type="text",
                    text=f"Channel aftertouch ch{ch} pressure {pressure}",
                )
            ]

        elif name == "send_midi_pitchbend":
            ch = arguments.get("channel")
            val = arguments.get("value")
            if ch is None or val is None:
                raise ValueError("Missing required arguments: channel, value")
            controller.client.send_midi_pitchbend(int(ch), int(val))
            return [
                TextContent(
                    type="text",
                    text=f"Pitchbend ch{ch} value {val}",
                )
            ]

        elif name == "set_vkb_fixed_velocity":
            val = arguments.get("value")
            if val is None:
                raise ValueError("Missing required argument: value")
            controller.client.set_vkb_fixed_velocity(int(val))
            return [TextContent(type="text", text=f"Fixed velocity set to {val}")]

        elif name == "set_vkb_note_repeat":
            active = arguments.get("active")
            if active is None:
                raise ValueError("Missing required argument: active")
            if not isinstance(active, bool):
                raise ValueError("active must be a boolean")
            controller.client.set_vkb_note_repeat_active(bool(active))
            period = arguments.get("period")
            length = arguments.get("length")
            if period is not None and length is not None:
                controller.client.set_vkb_note_repeat_timing(str(period), str(length))
                return [
                    TextContent(
                        type="text",
                        text=f"Note repeat {'on' if active else 'off'} period={period} length={length}",
                    )
                ]
            return [
                TextContent(
                    type="text",
                    text=f"Note repeat {'on' if active else 'off'}",
                )
            ]

        elif name == "play_midi_note_sequence":
            notes = arguments.get("notes")
            if not isinstance(notes, list) or len(notes) == 0:
                raise ValueError("notes must be a non-empty array")
            if len(notes) > 400:
                raise ValueError("notes: maximum 400 steps")
            total_delay_ms = 0.0
            for step in notes:
                if not isinstance(step, dict):
                    raise ValueError("each note step must be an object")
                d = step.get("delay_ms", 0)
                if not isinstance(d, (int, float)) or d < 0:
                    raise ValueError("delay_ms must be a non-negative number")
                total_delay_ms += float(d)
            if total_delay_ms > 120_000:
                raise ValueError("sum of delay_ms must not exceed 120000 (120s)")
            for step in notes:
                delay_ms = step.get("delay_ms", 0)
                await asyncio.sleep(float(delay_ms) / 1000.0)
                ch = step.get("channel")
                note = step.get("note")
                vel = step.get("velocity")
                if ch is None or note is None or vel is None:
                    raise ValueError("each step requires channel, note, velocity")
                controller.client.send_midi_note(int(ch), int(note), int(vel))
            return [
                TextContent(
                    type="text",
                    text=f"Played MIDI sequence ({len(notes)} steps)",
                )
            ]

        elif name == "launcher_clip_select":
            t, s = arguments.get("track_index"), arguments.get("slot_index")
            if t is None or s is None:
                raise ValueError("Missing track_index or slot_index")
            controller.client.launcher_clip_select(int(t), int(s))
            return [
                TextContent(
                    type="text", text=f"Selected track {t} slot {s}"
                )
            ]

        elif name == "launcher_clip_create":
            t, s = arguments.get("track_index"), arguments.get("slot_index")
            lb = arguments.get("length_beats")
            if t is None or s is None or lb is None:
                raise ValueError("Missing track_index, slot_index, or length_beats")
            controller.client.launcher_clip_create(int(t), int(s), float(lb))
            return [
                TextContent(
                    type="text",
                    text=f"Created clip on track {t} slot {s} ({lb} beats)",
                )
            ]

        elif name == "launcher_clip_launch":
            t, s = arguments.get("track_index"), arguments.get("slot_index")
            launch = arguments.get("launch")
            if t is None or s is None or launch is None:
                raise ValueError("Missing track_index, slot_index, or launch")
            if not isinstance(launch, bool):
                raise ValueError("launch must be a boolean")
            controller.client.launcher_clip_launch(int(t), int(s), launch)
            return [
                TextContent(
                    type="text",
                    text=f"Clip launch track {t} slot {s}: {'on' if launch else 'off'}",
                )
            ]

        elif name == "launcher_clip_record":
            t, s = arguments.get("track_index"), arguments.get("slot_index")
            if t is None or s is None:
                raise ValueError("Missing track_index or slot_index")
            controller.client.launcher_clip_record(int(t), int(s))
            return [
                TextContent(type="text", text=f"Record armed track {t} slot {s}")
            ]

        elif name == "launcher_clip_remove":
            t, s = arguments.get("track_index"), arguments.get("slot_index")
            if t is None or s is None:
                raise ValueError("Missing track_index or slot_index")
            controller.client.launcher_clip_remove(int(t), int(s))
            return [
                TextContent(type="text", text=f"Removed clip track {t} slot {s}")
            ]

        elif name == "launcher_clip_duplicate":
            t, s = arguments.get("track_index"), arguments.get("slot_index")
            if t is None or s is None:
                raise ValueError("Missing track_index or slot_index")
            controller.client.launcher_clip_duplicate(int(t), int(s))
            return [
                TextContent(type="text", text=f"Duplicated clip track {t} slot {s}")
            ]

        elif name == "launcher_clip_insert_file":
            t, s = arguments.get("track_index"), arguments.get("slot_index")
            fp = arguments.get("filepath")
            if t is None or s is None or fp is None:
                raise ValueError("Missing track_index, slot_index, or filepath")
            controller.client.launcher_clip_insert_file(int(t), int(s), str(fp))
            return [
                TextContent(
                    type="text", text=f"Insert file into track {t} slot {s}"
                )
            ]

        elif name == "launcher_track_stop":
            t = arguments.get("track_index")
            if t is None:
                raise ValueError("Missing track_index")
            controller.client.launcher_track_stop(int(t))
            return [TextContent(type="text", text=f"Stopped launcher on track {t}")]

        elif name == "launcher_track_return_to_arrangement":
            t = arguments.get("track_index")
            if t is None:
                raise ValueError("Missing track_index")
            controller.client.launcher_track_return_to_arrangement(int(t))
            return [
                TextContent(
                    type="text", text=f"Track {t} return to arrangement"
                )
            ]

        elif name == "clips_stop_all":
            controller.client.clips_stop_all()
            return [TextContent(type="text", text="Stopped all launcher clips")]

        elif name == "prepare_launcher_clip_slot":
            t, s = arguments.get("track_index"), arguments.get("slot_index")
            if t is None or s is None:
                raise ValueError("Missing track_index or slot_index")
            controller.client.prepare_launcher_clip_slot(int(t), int(s))
            return [
                TextContent(
                    type="text",
                    text=f"Prepared launcher slot track {t} slot {s}",
                )
            ]

        elif name == "toggle_arranger_clip_launcher_visible":
            controller.client.toggle_arranger_clip_launcher_visible()
            return [
                TextContent(
                    type="text",
                    text="Toggled clip launcher visibility in Arrange",
                )
            ]

        elif name == "insert_seed_midi_clip":
            from bitwig_mcp_server.seed_midi import write_seed_midi_file

            t = arguments.get("track_index")
            s = arguments.get("slot_index")
            pattern = arguments.get("pattern", "kick_four_on_floor")
            bars = int(arguments.get("bars", 1))
            scroll_pp = int(arguments.get("scroll_bank_pages_previous", 0) or 0)
            delay_sec = float(arguments.get("post_prepare_delay_sec", 0.28) or 0.0)
            if t is None or s is None:
                raise ValueError("Missing track_index or slot_index")
            if bars not in (1, 8):
                raise ValueError("bars must be 1 or 8")
            scroll_pp = max(0, min(scroll_pp, 64))
            delay_sec = max(0.0, min(delay_sec, 3.0))
            for _ in range(scroll_pp):
                controller.client.navigate_track_bank("previous", page=True)
            path = write_seed_midi_file(str(pattern), bars=bars)
            fp = str(path.resolve())
            if os.name == "nt":
                fp = fp.replace("\\", "/")
            controller.client.prepare_launcher_clip_slot(int(t), int(s))
            if delay_sec > 0:
                await asyncio.sleep(delay_sec)
            controller.client.launcher_clip_insert_file(int(t), int(s), fp)
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Inserted seed {pattern!r} bars={bars} scroll_bank_pages_previous={scroll_pp} "
                        f"-> {path.name}"
                    ),
                )
            ]

        elif name == "clip_create_at_cursor":
            lb = arguments.get("length_beats")
            if lb is None:
                raise ValueError("Missing length_beats")
            controller.client.clip_create_at_cursor(float(lb))
            return [
                TextContent(
                    type="text", text=f"Clip create at cursor ({lb} beats)"
                )
            ]

        elif name == "clip_quantize_selected":
            controller.client.clip_quantize_selected()
            return [TextContent(type="text", text="Quantized cursor clip")]

        elif name == "clip_set_name_selected":
            clip_name = arguments.get("name")
            if clip_name is None:
                raise ValueError("Missing name")
            controller.client.clip_set_name_selected(str(clip_name))
            return [
                TextContent(type="text", text=f"Clip name set to {clip_name!r}")
            ]

        elif name == "toggle_clip_launcher_overdub":
            controller.client.toggle_clip_launcher_overdub()
            return [TextContent(type="text", text="Toggled clip launcher overdub")]

        elif name == "toggle_arranger_overdub":
            controller.client.toggle_arranger_overdub()
            return [TextContent(type="text", text="Toggled arranger overdub")]

        elif name == "scene_add":
            controller.client.scene_add()
            return [TextContent(type="text", text="Added scene")]

        elif name == "scene_launch":
            si, launch = arguments.get("scene_index"), arguments.get("launch")
            if si is None or launch is None:
                raise ValueError("Missing scene_index or launch")
            if not isinstance(launch, bool):
                raise ValueError("launch must be a boolean")
            controller.client.scene_launch(int(si), launch)
            return [
                TextContent(
                    type="text",
                    text=f"Scene {si} launch {'on' if launch else 'off'}",
                )
            ]

        elif name == "set_device_parameter":
            param_index = arguments.get("param_index")
            value = arguments.get("value")

            if param_index is None or value is None:
                raise ValueError("Missing required arguments: param_index, value")

            if not isinstance(param_index, int) or param_index < 1:
                raise ValueError("Invalid param_index: must be a positive integer")

            if not isinstance(value, (int, float)) or value < 0 or value > 128:
                raise ValueError("Invalid value: must be between 0 and 128")

            automation_touch = bool(arguments.get("automation_touch", True))
            refresh_first = bool(arguments.get("refresh_first", False))
            if refresh_first:
                controller.client.refresh()
                await _refresh_state(controller, 0.12)
            if automation_touch:
                controller.client.set_device_parameter_touched(int(param_index), True)
                await asyncio.sleep(_TOUCH_GAP_SEC)
            controller.client.set_device_parameter(int(param_index), float(value))
            if automation_touch:
                await asyncio.sleep(_TOUCH_GAP_SEC)
                controller.client.set_device_parameter_touched(int(param_index), False)
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Device parameter {param_index} set to {value} "
                        f"(automation_touch={automation_touch}, refresh_first={refresh_first})"
                    ),
                )
            ]

        elif name == "select_device_page_slot":
            page_slot = arguments.get("page_slot")
            if page_slot is None:
                raise ValueError("Missing required argument: page_slot")
            controller.client.select_device_page_slot(int(page_slot))
            await _refresh_state(controller, 0.12)
            page_name = controller.server.get_message("/device/page/selected/name")
            return [
                TextContent(
                    type="text",
                    text=f"Selected device page slot {page_slot}; page={page_name!r}",
                )
            ]

        elif name == "navigate_device_param_page":
            direction = arguments.get("direction")
            if direction not in ("next", "previous"):
                raise ValueError("direction must be 'next' or 'previous'")
            controller.client.navigate_device_param_page(str(direction))
            await _refresh_state(controller, 0.12)
            page_name = controller.server.get_message("/device/page/selected/name")
            return [
                TextContent(
                    type="text",
                    text=f"Navigated device page {direction}; page={page_name!r}",
                )
            ]

        elif name == "navigate_device_param_bank_page":
            direction = arguments.get("direction")
            if direction not in ("next", "previous"):
                raise ValueError("direction must be 'next' or 'previous'")
            controller.client.navigate_device_param_bank_page(str(direction))
            await _refresh_state(controller, 0.14)
            slots = _device_page_slots(controller)
            names = ", ".join(
                f"{s['slot']}:{s['name']}{'*' if s['selected'] else ''}" for s in slots
            )
            return [
                TextContent(
                    type="text",
                    text=f"Navigated device page bank {direction}; slots=[{names}]",
                )
            ]

        elif name == "set_device_parameter_on_page":
            page_slot = arguments.get("page_slot")
            param_index = arguments.get("param_index")
            value = arguments.get("value")
            if page_slot is None or param_index is None or value is None:
                raise ValueError("Missing required arguments: page_slot, param_index, value")
            automation_touch = bool(arguments.get("automation_touch", True))
            controller.client.select_device_page_slot(int(page_slot))
            await _refresh_state(controller, 0.08)
            pi = int(param_index)
            if automation_touch:
                controller.client.set_device_parameter_touched(pi, True)
                await asyncio.sleep(_TOUCH_GAP_SEC)
            controller.client.set_device_parameter(pi, float(value))
            if automation_touch:
                await asyncio.sleep(_TOUCH_GAP_SEC)
                controller.client.set_device_parameter_touched(pi, False)
            await _refresh_state(controller, 0.05)
            page_name = controller.server.get_message("/device/page/selected/name")
            param_name = controller.server.get_message(
                f"/device/param/{int(param_index)}/name"
            )
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Set page slot {page_slot} ({page_name!r}) param {param_index} "
                        f"({param_name!r}) to {value}"
                    ),
                )
            ]

        elif name == "set_device_page_params":
            params = arguments.get("params") or []
            if not isinstance(params, list) or not params:
                raise ValueError("params must be a non-empty array")
            page_slot = arguments.get("page_slot")
            automation_touch = bool(arguments.get("automation_touch", True))
            if page_slot is not None:
                controller.client.select_device_page_slot(int(page_slot))
                await _refresh_state(controller, 0.08)
            for entry in params:
                if not isinstance(entry, dict):
                    raise ValueError("each params entry must be an object")
                pi = entry.get("param_index")
                val = entry.get("value")
                if pi is None or val is None:
                    raise ValueError("each entry needs param_index and value")
                pi_i = int(pi)
                val_c = _clamp_osc_value(float(val))
                if automation_touch:
                    controller.client.set_device_parameter_touched(pi_i, True)
                    await asyncio.sleep(_TOUCH_GAP_SEC)
                controller.client.set_device_parameter(pi_i, val_c)
                if automation_touch:
                    await asyncio.sleep(_TOUCH_GAP_SEC)
                    controller.client.set_device_parameter_touched(pi_i, False)
            await _refresh_state(controller, 0.06)
            page_name = controller.server.get_message("/device/page/selected/name")
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Set {len(params)} device param(s); "
                        f"page={page_name!r} slot_hint={page_slot!r}"
                    ),
                )
            ]

        elif name == "scan_device_pages_and_params":
            max_bank_steps = int(arguments.get("max_bank_steps", 8))
            max_bank_steps = max(1, min(max_bank_steps, 64))
            restore = bool(arguments.get("restore_initial_selection", True))
            max_params_per_page = int(
                arguments.get(
                    "max_params_per_page",
                    max(8, int(getattr(controller.client, "osc_bank_page_size", 64))),
                )
            )
            max_params_per_page = max(8, min(max_params_per_page, 512))
            include_unavailable = bool(arguments.get("include_unavailable", False))

            await _refresh_state(controller, 0.14)
            initial_slots = _device_page_slots(controller)
            initial_slot = next((s["slot"] for s in initial_slots if s["selected"]), 1)
            initial_sig = tuple((s["slot"], s["name"]) for s in initial_slots)

            for _ in range(256):
                has_prev = bool(controller.server.get_message("/device/page/hasPrevious"))
                if not has_prev:
                    break
                controller.client.navigate_device_param_bank_page("previous")
                await _refresh_state(controller, 0.03)

            scanned: List[Dict[str, Any]] = []
            seen_signatures = set()

            for bank in range(max_bank_steps):
                await _refresh_state(controller, 0.1)
                slots = _device_page_slots(controller)
                sig = tuple((s["slot"], s["name"]) for s in slots)
                if not slots or sig in seen_signatures:
                    break
                seen_signatures.add(sig)

                for slot in slots:
                    controller.client.select_device_page_slot(int(slot["slot"]))
                    await _refresh_state(controller, 0.08)
                    params = _read_device_param_slots(controller, max_params_per_page)
                    if not include_unavailable:
                        params = [p for p in params if p["available"] or p["exists"]]
                    scanned.append(
                        {
                            "bank": bank + 1,
                            "slot": slot["slot"],
                            "page_name": slot["name"],
                            "params": params,
                        }
                    )

                has_next = bool(controller.server.get_message("/device/page/hasNext"))
                if not has_next:
                    break
                controller.client.navigate_device_param_bank_page("next")
                await _refresh_state(controller, 0.05)

            if restore and initial_sig:
                restored = False
                for _ in range(64):
                    await _refresh_state(controller, 0.04)
                    cur_slots = _device_page_slots(controller)
                    cur_sig = tuple((s["slot"], s["name"]) for s in cur_slots)
                    if cur_sig == initial_sig:
                        controller.client.select_device_page_slot(int(initial_slot))
                        restored = True
                        break
                    controller.client.navigate_device_param_bank_page("previous")
                if not restored:
                    controller.client.select_device_page_slot(int(initial_slot))

            lines = ["Device page scan:"]
            lines.append(f"Banks scanned: {len(set(x['bank'] for x in scanned))}")
            lines.append(f"Pages scanned: {len(scanned)}")
            for page in scanned:
                available_count = len(
                    [p for p in page["params"] if p.get("available") or p.get("exists")]
                )
                total_count = len(page["params"])
                lines.append(
                    f"- bank {page['bank']} slot {page['slot']} page={page['page_name']!r} "
                    + f"available={available_count}/{total_count}"
                )
                for param in page["params"]:
                    flags = (
                        f"exists={str(bool(param.get('exists'))).lower()} "
                        + f"available={str(bool(param.get('available'))).lower()}"
                    )
                    lines.append(
                        "  "
                        + f"{param['index']}: {param['name']} "
                        + f"{flags} "
                        + f"value={param['value']} mod={param['modulated_value']} "
                        + (f"str={param['value_str']}" if param["value_str"] else "")
                    )
            return [TextContent(type="text", text="\n".join(lines))]

        elif name == "warmup_device_parameter_map":
            track_index = arguments.get("track_index")
            if track_index is not None:
                controller.client.select_track(int(track_index))

            max_bank_steps = max(1, min(int(arguments.get("max_bank_steps", 8)), 64))
            max_slots = max(
                1,
                min(
                    int(
                        arguments.get(
                            "page_slots_per_bank",
                            min(8, int(getattr(controller.client, "osc_bank_page_size", 64))),
                        )
                    ),
                    int(getattr(controller.client, "osc_bank_page_size", 64)),
                ),
            )
            probe_start = max(1, min(int(arguments.get("param_probe_start", 1)), 512))
            probe_end = max(1, min(int(arguments.get("param_probe_end", 8)), 512))
            if probe_end < probe_start:
                probe_start, probe_end = probe_end, probe_start
            low_value = _clamp_osc_value(float(arguments.get("low_value", 24)))
            high_value = _clamp_osc_value(float(arguments.get("high_value", 104)))
            settle_ms = max(0, min(int(arguments.get("settle_ms", 35)), 1000))
            restore = bool(arguments.get("restore_initial_selection", True))

            await _refresh_state(controller, 0.14)
            initial_slots = _device_page_slots(controller)
            initial_slot = next((s["slot"] for s in initial_slots if s["selected"]), 1)
            initial_sig = tuple((s["slot"], s["name"]) for s in initial_slots)

            for _ in range(256):
                has_prev = bool(controller.server.get_message("/device/page/hasPrevious"))
                if not has_prev:
                    break
                controller.client.navigate_device_param_bank_page("previous")
                await _refresh_state(controller, 0.03)

            warmed_pages: List[Dict[str, Any]] = []
            write_count = 0
            seen_signatures = set()

            for bank in range(max_bank_steps):
                await _refresh_state(controller, 0.08)
                slots = _device_page_slots(controller)
                sig = tuple((s["slot"], s["name"]) for s in slots)
                if slots and sig in seen_signatures:
                    break
                if slots:
                    seen_signatures.add(sig)
                    slot_ids = [int(s["slot"]) for s in slots[:max_slots]]
                else:
                    slot_ids = list(range(1, max_slots + 1))

                for slot in slot_ids:
                    try:
                        controller.client.select_device_page_slot(int(slot))
                        await _refresh_state(controller, 0.03)
                    except Exception:
                        continue

                    for pi in range(probe_start, probe_end + 1):
                        value = low_value if ((bank + slot + pi) % 2 == 0) else high_value
                        try:
                            controller.client.set_device_parameter(int(pi), float(value))
                            write_count += 1
                            if settle_ms > 0:
                                await asyncio.sleep(settle_ms / 1000.0)
                        except Exception:
                            continue

                    await _refresh_state(controller, 0.03)
                    params = _read_device_param_slots(
                        controller, max(8, min(probe_end, 512))
                    )
                    available_count = len(
                        [p for p in params if p.get("available") or p.get("exists")]
                    )
                    page_name = str(
                        controller.server.get_message("/device/page/selected/name")
                        or f"Page {slot}"
                    )
                    warmed_pages.append(
                        {
                            "bank": bank + 1,
                            "slot": int(slot),
                            "page_name": page_name,
                            "available_count": available_count,
                        }
                    )

                has_next = bool(controller.server.get_message("/device/page/hasNext"))
                if not has_next:
                    break
                controller.client.navigate_device_param_bank_page("next")
                await _refresh_state(controller, 0.04)

            if restore and initial_sig:
                restored = False
                for _ in range(64):
                    await _refresh_state(controller, 0.03)
                    cur_slots = _device_page_slots(controller)
                    cur_sig = tuple((s["slot"], s["name"]) for s in cur_slots)
                    if cur_sig == initial_sig:
                        controller.client.select_device_page_slot(int(initial_slot))
                        restored = True
                        break
                    controller.client.navigate_device_param_bank_page("previous")
                if not restored:
                    controller.client.select_device_page_slot(int(initial_slot))

            lines = ["Warmup device parameter map:"]
            lines.append(f"Banks visited: {len(set(p['bank'] for p in warmed_pages))}")
            lines.append(f"Pages warmed: {len(warmed_pages)}")
            lines.append(f"Probe writes sent: {write_count}")
            lines.append(f"Probe param range: {probe_start}-{probe_end}")
            for page in warmed_pages[:160]:
                lines.append(
                    f"- bank {page['bank']} slot {page['slot']} page={page['page_name']!r} "
                    + f"available={page['available_count']}"
                )
            return [TextContent(type="text", text="\n".join(lines))]

        elif name == "read_last_touched_device_parameter":
            await _refresh_state(controller, 0.12)
            exists = bool(controller.server.get_message("/device/lastparam/exists"))
            if not exists:
                return [
                    TextContent(
                        type="text",
                        text=(
                            "No last-touched parameter available. Click or hover a plugin parameter in Bitwig first."
                        ),
                    )
                ]
            name_text = str(controller.server.get_message("/device/lastparam/name") or "")
            val = controller.server.get_message("/device/lastparam/value")
            val_str = str(controller.server.get_message("/device/lastparam/valueStr") or "")
            mod = controller.server.get_message("/device/lastparam/modulatedValue")
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Last touched parameter: {name_text!r}\n"
                        f"value={val} valueStr={val_str!r} modulatedValue={mod}"
                    ),
                )
            ]

        elif name == "set_last_touched_device_parameter":
            value = arguments.get("value")
            if value is None:
                raise ValueError("Missing required argument: value")
            automation_touch = bool(arguments.get("automation_touch", True))
            if automation_touch:
                controller.client.set_last_touched_device_parameter_touched(True)
                await asyncio.sleep(_TOUCH_GAP_SEC)
            controller.client.set_last_touched_device_parameter(float(value))
            if automation_touch:
                await asyncio.sleep(_TOUCH_GAP_SEC)
                controller.client.set_last_touched_device_parameter_touched(False)
            await _refresh_state(controller, 0.06)
            return [
                TextContent(
                    type="text",
                    text=f"Set last touched parameter to {value} (automation_touch={automation_touch})",
                )
            ]

        elif name == "reset_last_touched_device_parameter":
            controller.client.reset_last_touched_device_parameter()
            await _refresh_state(controller, 0.06)
            return [
                TextContent(
                    type="text",
                    text="Reset last touched parameter",
                )
            ]

        elif name == "set_track_remote_parameter":
            track_index = arguments.get("track_index")
            param_index = arguments.get("param_index")
            value = arguments.get("value")
            if track_index is None or param_index is None or value is None:
                raise ValueError(
                    "Missing required arguments: track_index, param_index, value"
                )
            controller.client.set_track_remote_parameter(
                int(track_index), int(param_index), float(value)
            )
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Track {track_index} remote {param_index} set to {value}"
                    ),
                )
            ]

        elif name == "toggle_device_bypass":
            controller.client.toggle_device_bypass()
            return [TextContent(type="text", text="Device bypass toggled")]

        elif name == "select_device_sibling":
            sibling_index = arguments.get("sibling_index")

            if sibling_index is None:
                raise ValueError("Missing required argument: sibling_index")

            if (
                not isinstance(sibling_index, int)
                or sibling_index < 1
                or sibling_index > 8
            ):
                raise ValueError("Invalid sibling_index: must be between 1 and 8")

            controller.client.select_device_sibling(sibling_index)
            return [
                TextContent(
                    type="text", text=f"Selected sibling device {sibling_index}"
                )
            ]

        elif name == "navigate_device":
            direction = arguments.get("direction")

            if direction is None:
                raise ValueError("Missing required argument: direction")

            if direction not in ["next", "previous"]:
                raise ValueError("Invalid direction: must be 'next' or 'previous'")

            controller.client.navigate_device(direction)
            return [TextContent(type="text", text=f"Navigated to {direction} device")]

        elif name == "enter_device_layer":
            layer_index = arguments.get("layer_index")

            if layer_index is None:
                raise ValueError("Missing required argument: layer_index")

            if not isinstance(layer_index, int) or layer_index < 1 or layer_index > 8:
                raise ValueError("Invalid layer_index: must be between 1 and 8")

            controller.client.enter_device_layer(layer_index)
            return [
                TextContent(type="text", text=f"Entered device layer {layer_index}")
            ]

        elif name == "exit_device_layer":
            controller.client.exit_device_layer()
            return [TextContent(type="text", text="Exited device layer")]

        elif name == "toggle_device_window":
            controller.client.toggle_device_window()
            return [TextContent(type="text", text="Device window toggled")]

        # Browser tools
        elif name == "browse_insert_device":
            position = arguments.get("position", "after")

            if position not in ["after", "before"]:
                raise ValueError("Invalid position: must be 'after' or 'before'")

            controller.client.browse_for_device(position)
            return [
                TextContent(
                    type="text",
                    text=f"Browser opened to insert device {position} selected device",
                )
            ]

        elif name == "browse_device_presets":
            controller.client.browse_for_preset()
            return [
                TextContent(type="text", text="Browser opened to browse device presets")
            ]

        elif name == "commit_browser_selection":
            controller.client.commit_browser_selection()
            return [TextContent(type="text", text="Browser selection committed")]

        elif name == "cancel_browser":
            controller.client.cancel_browser()
            return [TextContent(type="text", text="Browser session canceled")]

        elif name == "navigate_browser_tab":
            direction = arguments.get("direction")

            if direction is None:
                raise ValueError("Missing required argument: direction")

            # Convert direction to "+" or "-"
            if direction == "next":
                dir_symbol = "+"
            elif direction == "previous":
                dir_symbol = "-"
            else:
                raise ValueError("Invalid direction: must be 'next' or 'previous'")

            controller.client.navigate_browser_tab(dir_symbol)
            return [
                TextContent(type="text", text=f"Navigated to {direction} browser tab")
            ]

        elif name == "navigate_browser_filter":
            filter_index = arguments.get("filter_index")
            direction = arguments.get("direction")

            if filter_index is None or direction is None:
                raise ValueError("Missing required arguments: filter_index, direction")

            if (
                not isinstance(filter_index, int)
                or filter_index < 1
                or filter_index > 6
            ):
                raise ValueError("Invalid filter_index: must be between 1 and 6")

            # Convert direction to "+" or "-"
            if direction == "next":
                dir_symbol = "+"
            elif direction == "previous":
                dir_symbol = "-"
            else:
                raise ValueError("Invalid direction: must be 'next' or 'previous'")

            controller.client.navigate_browser_filter(filter_index, dir_symbol)
            return [
                TextContent(
                    type="text",
                    text=f"Navigated to {direction} option in filter {filter_index}",
                )
            ]

        elif name == "reset_browser_filter":
            filter_index = arguments.get("filter_index")

            if filter_index is None:
                raise ValueError("Missing required argument: filter_index")

            if (
                not isinstance(filter_index, int)
                or filter_index < 1
                or filter_index > 6
            ):
                raise ValueError("Invalid filter_index: must be between 1 and 6")

            controller.client.reset_browser_filter(filter_index)
            return [TextContent(type="text", text=f"Reset filter {filter_index}")]

        elif name == "navigate_browser_result":
            direction = arguments.get("direction")

            if direction is None:
                raise ValueError("Missing required argument: direction")

            # Convert direction to "+" or "-"
            if direction == "next":
                dir_symbol = "+"
            elif direction == "previous":
                dir_symbol = "-"
            else:
                raise ValueError("Invalid direction: must be 'next' or 'previous'")

            controller.client.navigate_browser_result(dir_symbol)
            return [
                TextContent(
                    type="text", text=f"Navigated to {direction} browser result"
                )
            ]

        elif name == "device_browser_workflow":
            position = arguments.get("position", "after")
            num_tab_navigations = arguments.get("num_tab_navigations", 0)
            filter_navigations = arguments.get("filter_navigations", [])
            result_navigations = arguments.get("result_navigations", 0)

            # Validate parameters
            if position not in ["after", "before"]:
                raise ValueError("Invalid position: must be 'after' or 'before'")

            if not isinstance(num_tab_navigations, int):
                raise ValueError("Invalid num_tab_navigations: must be an integer")

            if not isinstance(result_navigations, int):
                raise ValueError("Invalid result_navigations: must be an integer")

            # Convert filter_navigations to the format required by browse_and_insert_device
            filter_nav_list = []
            if filter_navigations:
                for filter_nav in filter_navigations:
                    filter_index = filter_nav.get("filter_index")
                    steps = filter_nav.get("steps")

                    if filter_index is None or steps is None:
                        raise ValueError(
                            "Filter navigation missing filter_index or steps"
                        )

                    if (
                        not isinstance(filter_index, int)
                        or filter_index < 1
                        or filter_index > 6
                    ):
                        raise ValueError(
                            f"Invalid filter_index: {filter_index} must be between 1 and 6"
                        )

                    if not isinstance(steps, int):
                        raise ValueError(f"Invalid steps: {steps} must be an integer")

                    filter_nav_list.append((filter_index, steps))

            # Execute the workflow
            # Open device browser
            controller.client.browse_for_device(position)

            # Navigate through tabs
            for _ in range(abs(num_tab_navigations)):
                direction = "+" if num_tab_navigations >= 0 else "-"
                controller.client.navigate_browser_tab(direction)

            # Apply filter selections
            if filter_nav_list:
                for filter_index, steps in filter_nav_list:
                    for _ in range(abs(steps)):
                        direction = "+" if steps >= 0 else "-"
                        controller.client.navigate_browser_filter(
                            filter_index, direction
                        )

            # Navigate through results
            for _ in range(abs(result_navigations)):
                direction = "+" if result_navigations >= 0 else "-"
                controller.client.navigate_browser_result(direction)

            # Commit selection
            controller.client.commit_browser_selection()

            return [
                TextContent(
                    type="text", text="Device browser workflow completed successfully"
                )
            ]

        elif name == "preset_browser_workflow":
            filter_navigations = arguments.get("filter_navigations", [])
            result_navigations = arguments.get("result_navigations", 0)

            # Validate parameters
            if not isinstance(result_navigations, int):
                raise ValueError("Invalid result_navigations: must be an integer")

            # Convert filter_navigations to the format required by browse_and_load_preset
            filter_nav_list = []
            if filter_navigations:
                for filter_nav in filter_navigations:
                    filter_index = filter_nav.get("filter_index")
                    steps = filter_nav.get("steps")

                    if filter_index is None or steps is None:
                        raise ValueError(
                            "Filter navigation missing filter_index or steps"
                        )

                    if (
                        not isinstance(filter_index, int)
                        or filter_index < 1
                        or filter_index > 6
                    ):
                        raise ValueError(
                            f"Invalid filter_index: {filter_index} must be between 1 and 6"
                        )

                    if not isinstance(steps, int):
                        raise ValueError(f"Invalid steps: {steps} must be an integer")

                    filter_nav_list.append((filter_index, steps))

            # Execute the workflow
            # Open preset browser
            controller.client.browse_for_preset()

            # Apply filter selections
            if filter_nav_list:
                for filter_index, steps in filter_nav_list:
                    for _ in range(abs(steps)):
                        direction = "+" if steps >= 0 else "-"
                        controller.client.navigate_browser_filter(
                            filter_index, direction
                        )

            # Navigate through results
            for _ in range(abs(result_navigations)):
                direction = "+" if result_navigations >= 0 else "-"
                controller.client.navigate_browser_result(direction)

            # Commit selection
            controller.client.commit_browser_selection()

            return [
                TextContent(
                    type="text", text="Preset browser workflow completed successfully"
                )
            ]

        elif name == "bitwig_diagnose":
            from bitwig_mcp_server.utils.browser_indexer import BitwigBrowserIndexer

            idx_dir = browser_index_persistent_dir()
            count = BitwigBrowserIndexer(persistent_dir=idx_dir).get_device_count()
            status = controller.get_status()
            controller.server.clear_messages()
            controller.client.refresh()
            await asyncio.sleep(0.25)
            controller.client.refresh()
            await asyncio.sleep(0.6)
            controller.refresh(timeout=2.0)
            tempo = controller.server.get_message("/transport/tempo")
            proj = controller.server.get_message("/application/projectName")
            browser_active = controller.server.get_message("/browser/isActive")
            lines = [
                "Bitwig MCP / indexer diagnose",
                f"Index directory: {idx_dir}",
                f"Indexed devices (Chroma count): {count}",
                f"OSC ready: {status.get('ready')} connected: {status.get('connected')}",
                f"OSC send to Bitwig: {status.get('ip')}:{status.get('send_port')}",
                f"OSC listen (from Bitwig): {status.get('ip')}:{status.get('receive_port')}",
                f"Sample /transport/tempo: {tempo!r}",
                f"Sample /application/projectName: {proj!r}",
                f"Sample /browser/isActive: {browser_active!r}",
                "",
                "Indexer CLI uses the same index dir and BITWIG_MCP_BITWIG_* ports as MCP (.env or environment).",
                "To index from Cursor without a port fight: call MCP tool build_browser_index (releases OSC, runs indexer, restarts).",
                "If tempo/project stay None: Bitwig is not sending OSC to this listener port; match Bitwig OSC remote/receive target to BITWIG_MCP_BITWIG_RECEIVE_PORT.",
                "",
                "Automation: MCP can send /autowrite, /autowrite/launcher, /automationWriteMode, and parameter sweeps; "
                "it cannot create or enumerate automation lanes (Bitwig UI / host API).",
                "",
                "Device remote pages: MCP can select pages and set /device/param/1..n values; "
                "it cannot create pages or assign which plugin parameter fills each slot (Bitwig UI).",
                "",
                "Automation recording: device moves default to wrapping /device/param/N/touched so "
                "Latch/Touch can see knob gestures; use Write mode if host still skips OSC.",
            ]
            return [TextContent(type="text", text="\n".join(lines))]

        # Device browser index tools
        elif name == "search_device_browser":
            query = arguments.get("query")
            if not query:
                raise ValueError("Missing required argument: query")

            num_results = arguments.get("num_results", 5)
            category = arguments.get("category")
            type_filter = arguments.get("type")
            creator = arguments.get("creator")

            from bitwig_mcp_server.utils.device_recommender import (
                BitwigDeviceRecommender,
            )

            index_dir = browser_index_persistent_dir()
            recommender = BitwigDeviceRecommender(persistent_dir=index_dir)

            # Build filter dictionary
            filter_options = {}
            if category:
                filter_options["category"] = category
            if type_filter:
                filter_options["type"] = type_filter
            if creator:
                filter_options["creator"] = creator

            # Use None if no filters
            if not filter_options:
                filter_options = None

            # Search for devices
            try:
                # Check if index exists
                if recommender.indexer.get_device_count() == 0:
                    return [
                        TextContent(
                            type="text",
                            text=(
                                "The device index has not been built yet. With Bitwig open and OSC configured, run: "
                                "bitwig-browser-index index\n"
                                f"Index directory: {index_dir}"
                            ),
                        )
                    ]

                results = recommender.indexer.search_devices(
                    query=query, n_results=num_results, filter_options=filter_options
                )

                # Format results
                response_lines = [f"Search results for: {query}"]
                response_lines.append("")

                for i, result in enumerate(results, 1):
                    response_lines.append(f"{i}. {result['name']}")
                    response_lines.append(f"   Category: {result['category']}")
                    response_lines.append(f"   Type: {result['type']}")
                    response_lines.append(f"   Creator: {result['creator']}")
                    if result.get("tags"):
                        response_lines.append(f"   Tags: {', '.join(result['tags'])}")
                    if result.get("description"):
                        # Truncate long descriptions
                        desc = result["description"]
                        if len(desc) > 200:
                            desc = desc[:200] + "..."
                        response_lines.append(f"   Description: {desc}")
                    response_lines.append("")

                return [TextContent(type="text", text="\n".join(response_lines))]

            except Exception as e:
                logger.exception(f"Error searching device browser: {e}")
                return [
                    TextContent(
                        type="text", text=f"Error searching device browser: {str(e)}"
                    )
                ]

        elif name == "recommend_devices":
            description = arguments.get("description")
            if not description:
                raise ValueError("Missing required argument: description")

            num_results = arguments.get("num_results", 5)
            category = arguments.get("category")

            from bitwig_mcp_server.utils.device_recommender import (
                BitwigDeviceRecommender,
            )

            index_dir = browser_index_persistent_dir()
            recommender = BitwigDeviceRecommender(persistent_dir=index_dir)

            try:
                # Check if index exists
                if recommender.indexer.get_device_count() == 0:
                    return [
                        TextContent(
                            type="text",
                            text=(
                                "The device index has not been built yet. Run: bitwig-browser-index index\n"
                                f"Index directory: {index_dir}"
                            ),
                        )
                    ]

                recommendations = recommender.recommend_devices(
                    task_description=description,
                    num_results=num_results,
                    filter_category=category,
                )

                # Format recommendations
                response_lines = [f"Recommended devices for: {description}"]
                response_lines.append("")

                for i, rec in enumerate(recommendations, 1):
                    response_lines.append(f"{i}. {rec['device']} ({rec['category']})")
                    response_lines.append(f"   Creator: {rec['creator']}")
                    response_lines.append(f"   Relevance: {rec['relevance_score']:.2f}")
                    response_lines.append(f"   Why: {rec['explanation']}")
                    if rec.get("description"):
                        # Truncate long descriptions
                        desc = rec["description"]
                        if len(desc) > 150:
                            desc = desc[:150] + "..."
                        response_lines.append(f"   Description: {desc}")
                    response_lines.append("")

                return [TextContent(type="text", text="\n".join(response_lines))]

            except Exception as e:
                logger.exception(f"Error recommending devices: {e}")
                return [
                    TextContent(
                        type="text", text=f"Error recommending devices: {str(e)}"
                    )
                ]

        elif name == "get_device_categories":
            from bitwig_mcp_server.utils.device_recommender import (
                BitwigDeviceRecommender,
            )

            index_dir = browser_index_persistent_dir()
            recommender = BitwigDeviceRecommender(persistent_dir=index_dir)

            try:
                # Check if index exists
                if recommender.indexer.get_device_count() == 0:
                    return [
                        TextContent(
                            type="text",
                            text=(
                                "The device index has not been built yet. Run: bitwig-browser-index index\n"
                                f"Index directory: {index_dir}"
                            ),
                        )
                    ]

                # Get stats including categories
                stats = recommender.indexer.get_collection_stats()

                # Format response
                response_lines = ["Available Device Categories:"]
                response_lines.append("")

                for category in stats.get("categories", []):
                    response_lines.append(f"- {category}")

                response_lines.append("")
                response_lines.append("Available Device Types:")
                response_lines.append("")

                for type_ in stats.get("types", []):
                    response_lines.append(f"- {type_}")

                response_lines.append("")
                response_lines.append("Available Creators:")
                response_lines.append("")

                for creator in stats.get("creators", []):
                    response_lines.append(f"- {creator}")

                return [TextContent(type="text", text="\n".join(response_lines))]

            except Exception as e:
                logger.exception(f"Error getting device categories: {e}")
                return [
                    TextContent(
                        type="text", text=f"Error getting device categories: {str(e)}"
                    )
                ]

        elif name == "get_device_info":
            device_name = arguments.get("device_name")
            if not device_name:
                raise ValueError("Missing required argument: device_name")

            from bitwig_mcp_server.utils.device_recommender import (
                BitwigDeviceRecommender,
            )

            index_dir = browser_index_persistent_dir()
            recommender = BitwigDeviceRecommender(persistent_dir=index_dir)

            try:
                # Check if index exists
                if recommender.indexer.get_device_count() == 0:
                    return [
                        TextContent(
                            type="text",
                            text=(
                                "The device index has not been built yet. Run: bitwig-browser-index index\n"
                                f"Index directory: {index_dir}"
                            ),
                        )
                    ]

                # Search for the exact device
                results = recommender.indexer.search_devices(
                    query=device_name, n_results=10
                )

                # Find an exact match if possible
                exact_match = None
                for result in results:
                    if result["name"].lower() == device_name.lower():
                        exact_match = result
                        break

                if not exact_match and results:
                    # Use the closest match
                    exact_match = results[0]

                if exact_match:
                    # Format the device information
                    response_lines = [f"Device Information: {exact_match['name']}"]
                    response_lines.append("")
                    response_lines.append(f"Category: {exact_match['category']}")
                    response_lines.append(f"Type: {exact_match['type']}")
                    response_lines.append(f"Creator: {exact_match['creator']}")

                    if exact_match.get("tags"):
                        response_lines.append(f"Tags: {', '.join(exact_match['tags'])}")

                    if exact_match.get("description"):
                        response_lines.append("")
                        response_lines.append("Description:")
                        response_lines.append(exact_match["description"])

                    return [TextContent(type="text", text="\n".join(response_lines))]
                else:
                    return [
                        TextContent(
                            type="text",
                            text=f"No device found with name '{device_name}'",
                        )
                    ]

            except Exception as e:
                logger.exception(f"Error getting device info: {e}")
                return [
                    TextContent(
                        type="text", text=f"Error getting device info: {str(e)}"
                    )
                ]

        else:
            raise ValueError(f"Unknown tool: {name}")

    except Exception as e:
        logger.exception(f"Error executing tool {name}: {e}")
        return [TextContent(type="text", text=f"Error: {str(e)}")]
