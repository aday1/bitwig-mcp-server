"""
Bitwig OSC Client

Handles communication with Bitwig Studio via OSC
"""

import logging
import socket
from typing import Any, Dict, List, Optional

from pythonosc import udp_client

from .exceptions import (
    ConnectionError,
    InvalidParameterError,
)

logger = logging.getLogger(__name__)

# Default OSC settings (matching patched DrivenByMoss defaults)
DEFAULT_BITWIG_IP = "127.0.0.1"
DEFAULT_SEND_PORT = 8000  # Port Bitwig listens on


class BitwigOSCClient:
    """Client for sending OSC messages to Bitwig Studio"""

    def __init__(
        self,
        ip: str = DEFAULT_BITWIG_IP,
        port: int = DEFAULT_SEND_PORT,
        *,
        osc_bank_page_size: int = 64,
    ):
        """Initialize the OSC client

        Args:
            ip: The IP address of the Bitwig instance
            port: The port Bitwig is listening on for OSC messages
            osc_bank_page_size: Bitwig OSC bank page size (default 64). Track and clip slot
                indices in OSC are relative to the visible bank; index must be in 1..this value.

        Raises:
            ConnectionError: If unable to create the UDP client
        """
        try:
            self.ip = ip
            self.port = port
            if not isinstance(osc_bank_page_size, int) or osc_bank_page_size < 1:
                raise InvalidParameterError(
                    "osc_bank_page_size", osc_bank_page_size, "must be a positive integer"
                )
            self.osc_bank_page_size = min(osc_bank_page_size, 512)
            self.client = udp_client.SimpleUDPClient(ip, port)
            self.addr_log: List[str] = []  # Log of sent addresses for verification
        except socket.error as e:
            raise ConnectionError(details=f"Failed to create UDP client: {e}")
        except Exception as e:
            raise ConnectionError(details=str(e))

    def send(self, address: str, value: Any) -> None:
        """Send an OSC message to Bitwig

        Args:
            address: The OSC address to send to
            value: The value to send

        Raises:
            ConnectionError: If unable to send the message
        """
        try:
            logger.debug(f"Sending: {address} = {value}")
            self.client.send_message(address, value)
            self.addr_log.append(address)
        except socket.error as e:
            raise ConnectionError(details=f"Failed to send message to {address}: {e}")
        except Exception as e:
            raise ConnectionError(details=f"Error sending message to {address}: {e}")

    def get_sent_addresses(self) -> List[str]:
        """Get list of addresses that were sent

        Returns:
            List of OSC addresses that have been sent
        """
        return self.addr_log

    def refresh(self) -> None:
        """Request a refresh of all values from Bitwig

        Raises:
            ConnectionError: If unable to send the refresh command
        """
        self.send("/refresh", 1)

    # Transport controls
    def play(self, state: Optional[bool] = None) -> None:
        """Control playback

        Args:
            state: True to play, False to stop, None to toggle

        Raises:
            ConnectionError: If unable to send the command
        """
        if state is None:
            self.send("/play", None)  # Toggle
        else:
            self.send("/play", 1 if state else 0)

    def stop(self) -> None:
        """Stop playback

        Raises:
            ConnectionError: If unable to send the command
        """
        self.send("/stop", 1)

    def set_playhead_beats(self, beats: float) -> None:
        """Move the transport play position (arranger timeline, in beats)."""
        if not isinstance(beats, (int, float)):
            raise InvalidParameterError("beats", beats, "must be a number")
        if beats < 0:
            raise InvalidParameterError("beats", beats, "must be non-negative")
        self.send("/time", float(beats))

    def start_arranger_record(self) -> None:
        """Start recording in the arranger (prints clips on the timeline when armed)."""
        self.send("/record", None)

    def set_tempo(self, bpm: float) -> None:
        """Set the tempo

        Args:
            bpm: Tempo in beats per minute (20-999)

        Raises:
            InvalidParameterError: If bpm is not a number
            ConnectionError: If unable to send the command
        """
        # Tempo range is effectively 20-999 in Bitwig
        if not isinstance(bpm, (int, float)):
            raise InvalidParameterError("bpm", bpm, "must be a number")

        # Give a wider range than Bitwig accepts to allow for clamping
        MAX_TEMPO = 999
        MIN_TEMPO = 20

        if bpm < MIN_TEMPO:
            logger.warning(f"Tempo {bpm} below minimum ({MIN_TEMPO}), clamping")
            bpm = MIN_TEMPO
        elif bpm > MAX_TEMPO:
            logger.warning(f"Tempo {bpm} above maximum ({MAX_TEMPO}), clamping")
            bpm = MAX_TEMPO

        self.send("/tempo/raw", bpm)

    # Track controls
    def set_track_volume(self, track_index: int, volume: float) -> None:
        """Set track volume

        Args:
            track_index: Track index (1-based)
            volume: Volume value (0-128, where 64 is 0dB)

        Raises:
            InvalidParameterError: If parameters are invalid
            ConnectionError: If unable to send the command
        """
        self._validate_track_bank_index(track_index)

        MAX_VALUE = 128
        MIN_VALUE = 0

        if not isinstance(volume, (int, float)):
            raise InvalidParameterError("volume", volume, "must be a number")

        if volume < MIN_VALUE:
            logger.warning(f"Volume {volume} below minimum ({MIN_VALUE}), clamping")
            volume = MIN_VALUE
        elif volume > MAX_VALUE:
            logger.warning(f"Volume {volume} above maximum ({MAX_VALUE}), clamping")
            volume = MAX_VALUE

        self.send(f"/track/{track_index}/volume", volume)

    def set_track_pan(self, track_index: int, pan: float) -> None:
        """Set track pan

        Args:
            track_index: Track index (1-based)
            pan: Pan value (0-128, where 64 is center)

        Raises:
            InvalidParameterError: If parameters are invalid
            ConnectionError: If unable to send the command
        """
        self._validate_track_bank_index(track_index)

        MAX_VALUE = 128
        MIN_VALUE = 0

        if not isinstance(pan, (int, float)):
            raise InvalidParameterError("pan", pan, "must be a number")

        if pan < MIN_VALUE:
            logger.warning(
                f"Pan {pan} below minimum ({MIN_VALUE}), clamping to left extreme"
            )
            pan = MIN_VALUE
        elif pan > MAX_VALUE:
            logger.warning(
                f"Pan {pan} above maximum ({MAX_VALUE}), clamping to right extreme"
            )
            pan = MAX_VALUE

        self.send(f"/track/{track_index}/pan", pan)

    def toggle_track_mute(self, track_index: int) -> None:
        """Toggle track mute state

        Args:
            track_index: Track index (1-based)

        Raises:
            InvalidParameterError: If track_index is invalid
            ConnectionError: If unable to send the command
        """
        self._validate_track_bank_index(track_index)

        self.send(f"/track/{track_index}/mute", None)

    def set_track_mute(self, track_index: int, mute: bool) -> None:
        """Set track mute state

        Args:
            track_index: Track index (1-based)
            mute: True to mute, False to unmute

        Raises:
            InvalidParameterError: If parameters are invalid
            ConnectionError: If unable to send the command
        """
        self._validate_track_bank_index(track_index)

        if not isinstance(mute, bool):
            raise InvalidParameterError("mute", mute, "must be a boolean")

        self.send(f"/track/{track_index}/mute", 1 if mute else 0)

    def _validate_track_bank_index(self, track_index: int) -> None:
        if not isinstance(track_index, int):
            raise InvalidParameterError(
                "track_index", track_index, "must be an integer"
            )
        mx = self.osc_bank_page_size
        if track_index < 1 or track_index > mx:
            raise InvalidParameterError(
                "track_index",
                track_index,
                f"must be between 1 and {mx} (OSC bank page; Bitwig errors with "
                f"'Index {mx} out of bounds for length {mx}' if you use {mx + 1}+). "
                "Call navigate_track_bank with page true to scroll the bank, or set "
                "BITWIG_MCP_OSC_BANK_PAGE_SIZE to match Bitwig's OSC bank size.",
            )

    def add_track_instrument(self) -> None:
        """Add a new instrument track (Bitwig Open Controller OSC)."""
        self.send("/track/add/instrument", None)

    def add_track_audio(self) -> None:
        """Add a new audio track."""
        self.send("/track/add/audio", None)

    def add_track_effect(self) -> None:
        """Add a new effect track."""
        self.send("/track/add/effect", None)

    def select_track(self, track_index: int) -> None:
        """Select a track in the current OSC track bank (1-based)."""
        self._validate_track_bank_index(track_index)
        self.send(f"/track/{track_index}/select", 1)

    def navigate_track_selection(self, direction: str) -> None:
        """Move selection to next/previous track in the bank."""
        if direction not in ["next", "previous"]:
            raise InvalidParameterError(
                "direction", direction, "must be 'next' or 'previous'"
            )
        sym = "+" if direction == "next" else "-"
        self.send(f"/track/{sym}", None)

    def navigate_track_bank(self, direction: str, *, page: bool = False) -> None:
        """Scroll the track bank by one track or by one page (osc_bank_page_size tracks)."""
        if direction not in ["next", "previous"]:
            raise InvalidParameterError(
                "direction", direction, "must be 'next' or 'previous'"
            )
        sym = "+" if direction == "next" else "-"
        if page:
            self.send(f"/track/bank/page/{sym}", None)
        else:
            self.send(f"/track/bank/{sym}", None)

    def toggle_track_bank_mode(self) -> None:
        """Toggle between audio/instrument bank and effect track bank."""
        self.send("/track/toggleBank", None)

    def set_track_name(self, track_index: int, name: str) -> None:
        self._validate_track_bank_index(track_index)
        if not isinstance(name, str):
            raise InvalidParameterError("name", name, "must be a string")
        self.send(f"/track/{track_index}/name", name)

    def set_track_record_arm(self, track_index: int, armed: bool) -> None:
        self._validate_track_bank_index(track_index)
        if not isinstance(armed, bool):
            raise InvalidParameterError("armed", armed, "must be a boolean")
        self.send(f"/track/{track_index}/recarm", 1 if armed else 0)

    def set_track_solo(self, track_index: int, solo: bool) -> None:
        self._validate_track_bank_index(track_index)
        if not isinstance(solo, bool):
            raise InvalidParameterError("solo", solo, "must be a boolean")
        self.send(f"/track/{track_index}/solo", 1 if solo else 0)

    def duplicate_track(self, track_index: int) -> None:
        self._validate_track_bank_index(track_index)
        self.send(f"/track/{track_index}/duplicate", None)

    def remove_track(self, track_index: int) -> None:
        self._validate_track_bank_index(track_index)
        self.send(f"/track/{track_index}/remove", None)

    def set_layout(self, layout: str) -> None:
        """Switch Bitwig layout: arrange, mix, or edit."""
        if layout not in ("arrange", "mix", "edit"):
            raise InvalidParameterError(
                "layout", layout, "must be 'arrange', 'mix', or 'edit'"
            )
        self.send(f"/layout/{layout}", None)

    # Device controls
    def set_device_parameter(self, param_index: int, value: float) -> None:
        """Set device parameter value

        Args:
            param_index: Parameter index (1-based)
            value: Parameter value (0-128)

        Raises:
            InvalidParameterError: If parameters are invalid
            ConnectionError: If unable to send the command
        """
        if not isinstance(param_index, int):
            raise InvalidParameterError(
                "param_index", param_index, "must be an integer"
            )

        if param_index < 1:
            raise InvalidParameterError(
                "param_index", param_index, "must be at least 1 (1-based indexing)"
            )

        mx = self.osc_bank_page_size
        if param_index > mx:
            raise InvalidParameterError(
                "param_index", param_index, f"must be at most {mx}"
            )

        MAX_VALUE = 128
        MIN_VALUE = 0

        if not isinstance(value, (int, float)):
            raise InvalidParameterError("value", value, "must be a number")

        if value < MIN_VALUE:
            logger.warning(
                f"Parameter value {value} below minimum ({MIN_VALUE}), clamping"
            )
            value = MIN_VALUE
        elif value > MAX_VALUE:
            logger.warning(
                f"Parameter value {value} above maximum ({MAX_VALUE}), clamping"
            )
            value = MAX_VALUE

        self.send(f"/device/param/{param_index}/value", value)

    def set_device_parameter_touched(self, param_index: int, touched: bool) -> None:
        """Tell Bitwig the device parameter is touched/released (needed for Latch/Touch automation write)."""
        if not isinstance(param_index, int):
            raise InvalidParameterError(
                "param_index", param_index, "must be an integer"
            )
        if param_index < 1:
            raise InvalidParameterError(
                "param_index", param_index, "must be at least 1 (1-based indexing)"
            )
        mx = self.osc_bank_page_size
        if param_index > mx:
            raise InvalidParameterError(
                "param_index", param_index, f"must be at most {mx}"
            )
        if not isinstance(touched, bool):
            raise InvalidParameterError("touched", touched, "must be a boolean")
        self.send(f"/device/param/{param_index}/touched", 1 if touched else 0)

    def toggle_device_bypass(self) -> None:
        """Toggle bypass state of the currently selected device

        Raises:
            ConnectionError: If unable to send the command
        """
        self.send("/device/bypass", None)

    def select_device_sibling(self, sibling_index: int) -> None:
        """Select a sibling device (in the same chain as current device)

        Args:
            sibling_index: Index of the sibling device (1-8)

        Raises:
            InvalidParameterError: If sibling_index is invalid
            ConnectionError: If unable to send the command
        """
        if not isinstance(sibling_index, int):
            raise InvalidParameterError(
                "sibling_index", sibling_index, "must be an integer"
            )

        if sibling_index < 1 or sibling_index > 8:
            raise InvalidParameterError(
                "sibling_index", sibling_index, "must be between 1 and 8"
            )

        self.send(f"/device/sibling/{sibling_index}/select", 1)

    def navigate_device(self, direction: str) -> None:
        """Navigate to next/previous device

        Args:
            direction: Navigation direction, either "next" or "previous"

        Raises:
            InvalidParameterError: If direction is invalid
            ConnectionError: If unable to send the command
        """
        if direction not in ["next", "previous"]:
            raise InvalidParameterError(
                "direction", direction, "must be either 'next' or 'previous'"
            )

        # Map to OSC command
        nav_symbol = "+" if direction == "next" else "-"
        self.send(f"/device/{nav_symbol}", None)

    def enter_device_layer(self, layer_index: int) -> None:
        """Enter a device layer/chain

        Args:
            layer_index: Index of the layer to enter (1-8)

        Raises:
            InvalidParameterError: If layer_index is invalid
            ConnectionError: If unable to send the command
        """
        if not isinstance(layer_index, int):
            raise InvalidParameterError(
                "layer_index", layer_index, "must be an integer"
            )

        if layer_index < 1 or layer_index > 8:
            raise InvalidParameterError(
                "layer_index", layer_index, "must be between 1 and 8"
            )

        self.send(f"/device/layer/{layer_index}/enter", None)

    def exit_device_layer(self) -> None:
        """Exit current device layer (go to parent)

        Raises:
            ConnectionError: If unable to send the command
        """
        self.send("/device/layer/parent", None)

    def toggle_device_window(self) -> None:
        """Toggle device window visibility

        Raises:
            ConnectionError: If unable to send the command
        """
        self.send("/device/window", None)

    def select_device_by_index(self, device_index: int) -> None:
        """Select a device by its index

        Args:
            device_index: Index of the device to select (1-based)

        Raises:
            InvalidParameterError: If device_index is invalid
            ConnectionError: If unable to send the command
        """
        if not isinstance(device_index, int):
            raise InvalidParameterError(
                "device_index", device_index, "must be an integer"
            )

        if device_index < 1:
            raise InvalidParameterError(
                "device_index", device_index, "must be at least 1 (1-based indexing)"
            )

        self.send(f"/device/select/{device_index}", 1)

    # Browser controls based on OSC documentation
    def browse_for_device(self, position: str = "after") -> None:
        """Activate browser to insert a device

        Args:
            position: Where to insert the device ("after" or "before" the selected device)

        Raises:
            InvalidParameterError: If position is invalid
            ConnectionError: If unable to send the command
        """
        if position not in ["after", "before"]:
            raise InvalidParameterError(
                "position", position, "must be either 'after' or 'before'"
            )

        if position == "after":
            self.send("/browser/device", None)
        else:
            self.send("/browser/device/before", None)

    def browse_for_preset(self) -> None:
        """Activate browser to browse for presets of currently selected device

        Raises:
            ConnectionError: If unable to send the command
        """
        self.send("/browser/preset", None)

    def commit_browser_selection(self) -> None:
        """Commit the current selection in the browser

        Raises:
            ConnectionError: If unable to send the command
        """
        self.send("/browser/commit", None)

    def cancel_browser(self) -> None:
        """Cancel the current browser session

        Raises:
            ConnectionError: If unable to send the command
        """
        self.send("/browser/cancel", None)

    def navigate_browser_tab(self, direction: str) -> None:
        """Navigate between browser tabs

        Args:
            direction: Direction to navigate ("+", "-")

        Raises:
            InvalidParameterError: If direction is invalid
            ConnectionError: If unable to send the command
        """
        if direction not in ["+", "-"]:
            raise InvalidParameterError(
                "direction", direction, "must be either '+' or '-'"
            )

        self.send(f"/browser/tab/{direction}", None)

    def navigate_browser_filter(self, filter_index: int, direction: str) -> None:
        """Navigate through filter options

        Args:
            filter_index: Index of the filter column (1-6)
            direction: Direction to navigate ("+", "-")

        Raises:
            InvalidParameterError: If parameters are invalid
            ConnectionError: If unable to send the command
        """
        if not isinstance(filter_index, int) or filter_index < 1 or filter_index > 6:
            raise InvalidParameterError(
                "filter_index", filter_index, "must be between 1 and 6"
            )

        if direction not in ["+", "-"]:
            raise InvalidParameterError(
                "direction", direction, "must be either '+' or '-'"
            )

        self.send(f"/browser/filter/{filter_index}/{direction}", None)

    def reset_browser_filter(self, filter_index: int) -> None:
        """Reset a browser filter

        Args:
            filter_index: Index of the filter column to reset (1-6)

        Raises:
            InvalidParameterError: If filter_index is invalid
            ConnectionError: If unable to send the command
        """
        if not isinstance(filter_index, int) or filter_index < 1 or filter_index > 6:
            raise InvalidParameterError(
                "filter_index", filter_index, "must be between 1 and 6"
            )

        self.send(f"/browser/filter/{filter_index}/reset", None)

    def navigate_browser_result(self, direction: str) -> None:
        """Navigate through browser results

        Args:
            direction: Direction to navigate ("+", "-")

        Raises:
            InvalidParameterError: If direction is invalid
            ConnectionError: If unable to send the command
        """
        if direction not in ["+", "-"]:
            raise InvalidParameterError(
                "direction", direction, "must be either '+' or '-'"
            )

        self.send(f"/browser/result/{direction}", None)

    def navigate_browser_result_page(self, direction: str) -> None:
        """Navigate through browser result pages (each page contains up to 16 results)

        Args:
            direction: Direction to navigate ("+", "-")

        Raises:
            InvalidParameterError: If direction is invalid
            ConnectionError: If unable to send the command
        """
        if direction not in ["+", "-"]:
            raise InvalidParameterError(
                "direction", direction, "must be either '+' or '-'"
            )

        # Page navigation addresses based on DrivenByMoss implementation
        self.send(f"/browser/result/page/{direction}", None)

    # Higher-level convenience methods for common tasks
    def insert_device_after_selected(self) -> None:
        """Open browser to insert a device after the currently selected one

        Raises:
            ConnectionError: If unable to send the command
        """
        self.browse_for_device("after")

    def insert_device_before_selected(self) -> None:
        """Open browser to insert a device before the currently selected one

        Raises:
            ConnectionError: If unable to send the command
        """
        self.browse_for_device("before")

    def browse_device_presets(self) -> None:
        """Open browser to browse presets for the currently selected device

        Raises:
            ConnectionError: If unable to send the command
        """
        self.browse_for_preset()

    def select_next_browser_tab(self) -> None:
        """Select the next browser tab

        Raises:
            ConnectionError: If unable to send the command
        """
        self.navigate_browser_tab("+")

    def select_previous_browser_tab(self) -> None:
        """Select the previous browser tab

        Raises:
            ConnectionError: If unable to send the command
        """
        self.navigate_browser_tab("-")

    def select_next_filter_option(self, filter_index: int) -> None:
        """Select the next option in a filter column

        Args:
            filter_index: Index of the filter column (1-6)

        Raises:
            InvalidParameterError: If filter_index is invalid
            ConnectionError: If unable to send the command
        """
        self.navigate_browser_filter(filter_index, "+")

    def select_previous_filter_option(self, filter_index: int) -> None:
        """Select the previous option in a filter column

        Args:
            filter_index: Index of the filter column (1-6)

        Raises:
            InvalidParameterError: If filter_index is invalid
            ConnectionError: If unable to send the command
        """
        self.navigate_browser_filter(filter_index, "-")

    def select_next_browser_result(self) -> None:
        """Select the next result in the browser

        Raises:
            ConnectionError: If unable to send the command
        """
        self.navigate_browser_result("+")

    def select_previous_browser_result(self) -> None:
        """Select the previous result in the browser

        Raises:
            ConnectionError: If unable to send the command
        """
        self.navigate_browser_result("-")

    def select_next_browser_result_page(self) -> None:
        """Navigate to the next page of browser results (up to 16 results per page)

        Raises:
            ConnectionError: If unable to send the command
        """
        self.navigate_browser_result_page("+")

    def select_previous_browser_result_page(self) -> None:
        """Navigate to the previous page of browser results (up to 16 results per page)

        Raises:
            ConnectionError: If unable to send the command
        """
        self.navigate_browser_result_page("-")

    # Workflow helper methods
    def browse_and_insert_device(
        self, num_tabs: int = 0, num_filters: List[int] = None, num_results: int = 0
    ) -> None:
        """Browse and insert a device using navigation commands

        Args:
            num_tabs: Number of tab navigations (positive = forward, negative = backward)
            num_filters: List of filter navigations by column index (e.g., [(1, 2), (4, -1)])
                        Format: List of tuples (filter_index, num_navigations)
            num_results: Number of result navigations (positive = forward, negative = backward)

        Raises:
            ConnectionError: If unable to send commands
        """
        # Open device browser
        self.browse_for_device("after")

        # Navigate to desired tab
        for _ in range(abs(num_tabs)):
            direction = "+" if num_tabs >= 0 else "-"
            self.navigate_browser_tab(direction)

        # Apply filter selections
        if num_filters:
            for filter_index, num_navigations in num_filters:
                for _ in range(abs(num_navigations)):
                    direction = "+" if num_navigations >= 0 else "-"
                    self.navigate_browser_filter(filter_index, direction)

        # Navigate to desired result
        for _ in range(abs(num_results)):
            direction = "+" if num_results >= 0 else "-"
            self.navigate_browser_result(direction)

        # Commit selection
        self.commit_browser_selection()

    def browse_and_load_preset(
        self, num_filters: List[int] = None, num_results: int = 0
    ) -> None:
        """Browse and load a preset using navigation commands

        Args:
            num_filters: List of filter navigations by column index (e.g., [(1, 2), (4, -1)])
                        Format: List of tuples (filter_index, num_navigations)
            num_results: Number of result navigations (positive = forward, negative = backward)

        Raises:
            ConnectionError: If unable to send commands
        """
        # Open preset browser
        self.browse_for_preset()

        # Apply filter selections
        if num_filters:
            for filter_index, num_navigations in num_filters:
                for _ in range(abs(num_navigations)):
                    direction = "+" if num_navigations >= 0 else "-"
                    self.navigate_browser_filter(filter_index, direction)

        # Navigate to desired result
        for _ in range(abs(num_results)):
            direction = "+" if num_results >= 0 else "-"
            self.navigate_browser_result(direction)

        # Commit selection
        self.commit_browser_selection()

    def _validate_send_index(self, send_index: int) -> None:
        if not isinstance(send_index, int) or send_index < 1 or send_index > 8:
            raise InvalidParameterError(
                "send_index", send_index, "must be between 1 and 8 (OSC)"
            )

    def _validate_project_param_index(self, index: int) -> None:
        if not isinstance(index, int) or index < 1 or index > 8:
            raise InvalidParameterError(
                "project_param_index", index, "must be between 1 and 8 (OSC)"
            )

    def toggle_mixer_sends_section(self) -> None:
        """Toggle visibility of sends column in Mixer layout (OSC)."""
        self.send("/mixer/sendsSectionVisibility", None)

    def enable_track_send(self, track_index: int, send_index: int) -> None:
        """Enable a track send (OSC: activated with value 1)."""
        self._validate_track_bank_index(track_index)
        self._validate_send_index(send_index)
        self.send(f"/track/{track_index}/send/{send_index}/activated", 1)

    def set_track_send_volume(self, track_index: int, send_index: int, value: float) -> None:
        """Set track send level (0-MAX_VALUE, typically 0-128 in Moss OSC)."""
        self._validate_track_bank_index(track_index)
        self._validate_send_index(send_index)
        self.send(f"/track/{track_index}/send/{send_index}/volume", float(value))

    def set_project_remote_control_value(self, param_index: int, value: float) -> None:
        """Set one of the 8 Bitwig project remote controls (mixer macro-style)."""
        self._validate_project_param_index(param_index)
        self.send(f"/project/param/{param_index}/value", float(value))

    def open_track_device_browser(self, track_index: int, position: str = "after") -> None:
        """Select track and open device browser to insert before/after selected device."""
        self.refresh()
        self.select_track(track_index)
        self.browse_for_device(position)

    # --- Clip launcher, scenes, MIDI (DrivenByMoss / Bitwig Open Controller OSC) ---
    # Track/slot indices address the OSC bank page (default 8; increase in Bitwig OSC prefs).

    def _validate_osc_bank_index(self, value: int, name: str) -> None:
        if not isinstance(value, int):
            raise InvalidParameterError(name, value, "must be an integer")
        mx = self.osc_bank_page_size
        if value < 1 or value > mx:
            raise InvalidParameterError(
                name,
                value,
                f"must be between 1 and {mx} (OSC bank page). "
                "Use navigate_track_bank to show other project tracks, or increase "
                "BITWIG_MCP_OSC_BANK_PAGE_SIZE if Bitwig's OSC bank size is larger.",
            )

    def send_midi_note(self, channel: int, note: int, velocity: int) -> None:
        """Inject a MIDI note via virtual keyboard (velocity 0 = note off)."""
        if not isinstance(channel, int) or channel < 1 or channel > 16:
            raise InvalidParameterError(
                "channel", channel, "must be between 1 and 16"
            )
        if not isinstance(note, int) or note < 0 or note > 127:
            raise InvalidParameterError("note", note, "must be between 0 and 127")
        if not isinstance(velocity, int) or velocity < 0 or velocity > 127:
            raise InvalidParameterError(
                "velocity", velocity, "must be between 0 and 127"
            )
        self.send(f"/vkb_midi/{channel}/note/{note}", velocity)

    def send_midi_drum(self, channel: int, note: int, velocity: int) -> None:
        """Send a drum note on the virtual MIDI keyboard."""
        if not isinstance(channel, int) or channel < 1 or channel > 16:
            raise InvalidParameterError(
                "channel", channel, "must be between 1 and 16"
            )
        if not isinstance(note, int) or note < 0 or note > 127:
            raise InvalidParameterError("note", note, "must be between 0 and 127")
        if not isinstance(velocity, int) or velocity < 0 or velocity > 127:
            raise InvalidParameterError(
                "velocity", velocity, "must be between 0 and 127"
            )
        self.send(f"/vkb_midi/{channel}/drum/{note}", velocity)

    def send_midi_cc(self, channel: int, cc: int, value: int) -> None:
        """Send a MIDI CC message through the virtual keyboard bridge."""
        if not isinstance(channel, int) or channel < 1 or channel > 16:
            raise InvalidParameterError(
                "channel", channel, "must be between 1 and 16"
            )
        if not isinstance(cc, int) or cc < 0 or cc > 127:
            raise InvalidParameterError("cc", cc, "must be between 0 and 127")
        if not isinstance(value, int) or value < 0 or value > 127:
            raise InvalidParameterError("value", value, "must be between 0 and 127")
        self.send(f"/vkb_midi/{channel}/cc/{cc}", value)

    def send_midi_program_change(self, channel: int, program: int) -> None:
        """Send MIDI Program Change 0-127 via /vkb_midi/{ch}/program (DrivenByMoss fork with program case)."""
        if not isinstance(channel, int) or channel < 1 or channel > 16:
            raise InvalidParameterError(
                "channel", channel, "must be between 1 and 16"
            )
        if not isinstance(program, int) or program < 0 or program > 127:
            raise InvalidParameterError(
                "program", program, "must be between 0 and 127"
            )
        self.send(f"/vkb_midi/{channel}/program", program)

    def send_midi_aftertouch_poly(self, channel: int, note: int, pressure: int) -> None:
        """Send poly aftertouch for one note."""
        if not isinstance(channel, int) or channel < 1 or channel > 16:
            raise InvalidParameterError(
                "channel", channel, "must be between 1 and 16"
            )
        if not isinstance(note, int) or note < 0 or note > 127:
            raise InvalidParameterError("note", note, "must be between 0 and 127")
        if not isinstance(pressure, int) or pressure < 0 or pressure > 127:
            raise InvalidParameterError(
                "pressure", pressure, "must be between 0 and 127"
            )
        self.send(f"/vkb_midi/{channel}/aftertouch/{note}", pressure)

    def send_midi_aftertouch_channel(self, channel: int, pressure: int) -> None:
        """Send channel aftertouch."""
        if not isinstance(channel, int) or channel < 1 or channel > 16:
            raise InvalidParameterError(
                "channel", channel, "must be between 1 and 16"
            )
        if not isinstance(pressure, int) or pressure < 0 or pressure > 127:
            raise InvalidParameterError(
                "pressure", pressure, "must be between 0 and 127"
            )
        self.send(f"/vkb_midi/{channel}/aftertouch", pressure)

    def send_midi_pitchbend(self, channel: int, value: int) -> None:
        """Send pitch bend value (0..127, center=64)."""
        if not isinstance(channel, int) or channel < 1 or channel > 16:
            raise InvalidParameterError(
                "channel", channel, "must be between 1 and 16"
            )
        if not isinstance(value, int) or value < 0 or value > 127:
            raise InvalidParameterError("value", value, "must be between 0 and 127")
        self.send(f"/vkb_midi/{channel}/pitchbend", value)

    def set_vkb_fixed_velocity(self, value: int) -> None:
        """Set fixed velocity (0 disables, 1..127 enables)."""
        if not isinstance(value, int) or value < 0 or value > 127:
            raise InvalidParameterError("value", value, "must be between 0 and 127")
        self.send("/vkb_midi/velocity", value)

    def set_vkb_note_repeat_active(self, active: bool) -> None:
        """Enable or disable note repeat."""
        if not isinstance(active, bool):
            raise InvalidParameterError("active", active, "must be a boolean")
        self.send("/vkb_midi/noterepeat/isActive", 1 if active else 0)

    def set_vkb_note_repeat_timing(self, period: str, length: str) -> None:
        """Set note repeat period and length values."""
        allowed = {"1/4", "1/4t", "1/8", "1/8t", "1/16", "1/16t", "1/32", "1/32t"}
        if period not in allowed:
            raise InvalidParameterError("period", period, f"must be one of {sorted(allowed)}")
        if length not in allowed:
            raise InvalidParameterError("length", length, f"must be one of {sorted(allowed)}")
        self.send("/vkb_midi/noterepeat/period", period)
        self.send("/vkb_midi/noterepeat/length", length)

    def navigate_device_param_page(self, direction: str) -> None:
        """Select next/previous device parameter page."""
        if direction not in ["next", "previous"]:
            raise InvalidParameterError(
                "direction", direction, "must be either 'next' or 'previous'"
            )
        sym = "+" if direction == "next" else "-"
        self.send(f"/device/param/{sym}", None)

    def navigate_device_param_bank_page(self, direction: str) -> None:
        """Select next/previous bank of 8 device pages."""
        if direction not in ["next", "previous"]:
            raise InvalidParameterError(
                "direction", direction, "must be either 'next' or 'previous'"
            )
        sym = "+" if direction == "next" else "-"
        self.send(f"/device/param/bank/page/{sym}", None)

    def select_device_page_slot(self, page_slot: int) -> None:
        """Select one of the currently visible device pages."""
        mx = self.osc_bank_page_size
        if not isinstance(page_slot, int) or page_slot < 1 or page_slot > mx:
            raise InvalidParameterError(
                "page_slot", page_slot, f"must be between 1 and {mx}"
            )
        self.send("/device/page/selected", page_slot)

    def set_track_remote_parameter(
        self, track_index: int, param_index: int, value: float
    ) -> None:
        """Set one of the selected track remote parameters (1..8)."""
        self._validate_track_bank_index(track_index)
        if not isinstance(param_index, int) or param_index < 1 or param_index > 8:
            raise InvalidParameterError("param_index", param_index, "must be between 1 and 8")
        if not isinstance(value, (int, float)) or value < 0 or value > 128:
            raise InvalidParameterError("value", value, "must be between 0 and 128")
        self.select_track(track_index)
        self.send(f"/track/param/{param_index}/value", float(value))

    def navigate_track_param_page(self, direction: str) -> None:
        """Select next/previous track parameter page."""
        if direction not in ["next", "previous"]:
            raise InvalidParameterError(
                "direction", direction, "must be either 'next' or 'previous'"
            )
        sym = "+" if direction == "next" else "-"
        self.send(f"/track/param/{sym}", None)

    def navigate_track_param_bank_page(self, direction: str) -> None:
        """Select next/previous bank of 8 track parameter pages."""
        if direction not in ["next", "previous"]:
            raise InvalidParameterError(
                "direction", direction, "must be either 'next' or 'previous'"
            )
        sym = "+" if direction == "next" else "-"
        self.send(f"/track/param/bank/page/{sym}", None)

    def select_track_page_slot(self, page_slot: int) -> None:
        """Select one of the currently visible 8 track pages."""
        if not isinstance(page_slot, int) or page_slot < 1 or page_slot > 8:
            raise InvalidParameterError("page_slot", page_slot, "must be between 1 and 8")
        self.send("/track/page/selected", page_slot)

    def set_last_touched_device_parameter(self, value: float) -> None:
        """Set value of last hovered/clicked parameter."""
        if not isinstance(value, (int, float)) or value < 0 or value > 128:
            raise InvalidParameterError("value", value, "must be between 0 and 128")
        self.send("/device/lastparam/value", float(value))

    def reset_last_touched_device_parameter(self) -> None:
        """Reset last hovered/clicked parameter to default."""
        self.send("/device/lastparam/reset", None)

    def set_last_touched_device_parameter_touched(self, touched: bool) -> None:
        """Set touched state for the last hovered/clicked parameter."""
        if not isinstance(touched, bool):
            raise InvalidParameterError("touched", touched, "must be a boolean")
        self.send("/device/lastparam/touched", 1 if touched else 0)

    def launcher_clip_select(self, track_index: int, slot_index: int) -> None:
        self._validate_osc_bank_index(track_index, "track_index")
        self._validate_osc_bank_index(slot_index, "slot_index")
        self.send(f"/track/{track_index}/clip/{slot_index}/select", None)

    def prepare_launcher_clip_slot(self, track_index: int, slot_index: int) -> None:
        """Sync Bitwig focus: refresh, select track, then select launcher slot (needed for reliable clips)."""
        self.refresh()
        self.select_track(track_index)
        self.launcher_clip_select(track_index, slot_index)

    def toggle_arranger_clip_launcher_visible(self) -> None:
        """Toggle clip launcher strip visibility in Arrange layout (run twice if it was hidden)."""
        self.send("/arranger/clipLauncherSectionVisibility", None)

    def launcher_clip_create(
        self, track_index: int, slot_index: int, length_beats: float
    ) -> None:
        """Create a new clip, enable overdub, and start (length in quarter notes)."""
        self._validate_osc_bank_index(track_index, "track_index")
        self._validate_osc_bank_index(slot_index, "slot_index")
        if not isinstance(length_beats, (int, float)) or length_beats <= 0:
            raise InvalidParameterError(
                "length_beats", length_beats, "must be a positive number"
            )
        self.send(f"/track/{track_index}/clip/{slot_index}/create", float(length_beats))

    def launcher_clip_launch(
        self, track_index: int, slot_index: int, launch: bool
    ) -> None:
        self._validate_osc_bank_index(track_index, "track_index")
        self._validate_osc_bank_index(slot_index, "slot_index")
        if not isinstance(launch, bool):
            raise InvalidParameterError("launch", launch, "must be a boolean")
        self.send(
            f"/track/{track_index}/clip/{slot_index}/launch", 1 if launch else 0
        )

    def launcher_clip_record(self, track_index: int, slot_index: int) -> None:
        self._validate_osc_bank_index(track_index, "track_index")
        self._validate_osc_bank_index(slot_index, "slot_index")
        self.send(f"/track/{track_index}/clip/{slot_index}/record", None)

    def launcher_clip_remove(self, track_index: int, slot_index: int) -> None:
        self._validate_osc_bank_index(track_index, "track_index")
        self._validate_osc_bank_index(slot_index, "slot_index")
        self.send(f"/track/{track_index}/clip/{slot_index}/remove", None)

    def launcher_clip_duplicate(self, track_index: int, slot_index: int) -> None:
        self._validate_osc_bank_index(track_index, "track_index")
        self._validate_osc_bank_index(slot_index, "slot_index")
        self.send(f"/track/{track_index}/clip/{slot_index}/duplicate", None)

    def launcher_clip_insert_file(
        self, track_index: int, slot_index: int, filepath: str
    ) -> None:
        self._validate_osc_bank_index(track_index, "track_index")
        self._validate_osc_bank_index(slot_index, "slot_index")
        if not isinstance(filepath, str) or not filepath.strip():
            raise InvalidParameterError("filepath", filepath, "must be a non-empty string")
        self.send(f"/track/{track_index}/clip/{slot_index}/insertFile", filepath)

    def launcher_track_stop(self, track_index: int) -> None:
        self._validate_osc_bank_index(track_index, "track_index")
        self.send(f"/track/{track_index}/clip/stop", None)

    def launcher_track_return_to_arrangement(self, track_index: int) -> None:
        self._validate_osc_bank_index(track_index, "track_index")
        self.send(f"/track/{track_index}/clip/returntoarrangement", None)

    def clips_stop_all(self) -> None:
        self.send("/clip/stopall", None)

    def clip_create_at_cursor(self, length_beats: float) -> None:
        if not isinstance(length_beats, (int, float)) or length_beats <= 0:
            raise InvalidParameterError(
                "length_beats", length_beats, "must be a positive number"
            )
        self.send("/clip/create", float(length_beats))

    def clip_quantize_selected(self) -> None:
        self.send("/clip/quantize", None)

    def clip_set_name_selected(self, name: str) -> None:
        if not isinstance(name, str):
            raise InvalidParameterError("name", name, "must be a string")
        self.send("/clip/name", name)

    def toggle_clip_launcher_overdub(self) -> None:
        self.send("/overdub/launcher", None)

    def toggle_arranger_overdub(self) -> None:
        self.send("/overdub", None)

    def toggle_write_arranger_automation(self) -> None:
        """Toggle arranger automation write (same as Bitwig transport autowrite button)."""
        self.send("/autowrite", None)

    def toggle_write_launcher_automation(self) -> None:
        """Toggle clip-launcher automation write."""
        self.send("/autowrite/launcher", None)

    def set_automation_write_mode(self, mode: str) -> None:
        """Set automation write mode (DrivenByMoss OSC /automationWriteMode).

        Bitwig expects enum names like LATCH, TOUCH, WRITE, READ, TRIM_READ, LATCH_PREVIEW.
        """
        if not isinstance(mode, str) or not mode.strip():
            raise InvalidParameterError("mode", mode, "must be a non-empty string")
        self.send("/automationWriteMode", mode.strip())

    def scene_add(self) -> None:
        self.send("/scene/add", None)

    def scene_launch(self, scene_index: int, launch: bool) -> None:
        self._validate_osc_bank_index(scene_index, "scene_index")
        if not isinstance(launch, bool):
            raise InvalidParameterError("launch", launch, "must be a boolean")
        self.send(f"/scene/{scene_index}/launch", 1 if launch else 0)

    def get_status(self) -> Dict[str, Any]:
        """Get client status information

        Returns:
            Dict with status information
        """
        return {
            "ip": self.ip,
            "port": self.port,
            "messages_sent": len(self.addr_log),
            "last_addresses": self.addr_log[-5:] if self.addr_log else [],
        }
