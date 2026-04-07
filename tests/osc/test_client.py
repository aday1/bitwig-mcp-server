"""Tests for the BitwigOSCClient class"""

import unittest
from unittest.mock import MagicMock, call

import pytest

from bitwig_mcp_server.osc.client import BitwigOSCClient
from bitwig_mcp_server.osc.exceptions import InvalidParameterError


class TestBitwigOSCClient(unittest.TestCase):
    """Test cases for BitwigOSCClient"""

    def setUp(self):
        """Set up test environment"""
        self.client = BitwigOSCClient()
        self.client.client = MagicMock()  # Mock the underlying UDP client

    def test_send(self):
        """Test sending OSC messages"""
        self.client.send("/test/address", 42)
        self.client.client.send_message.assert_called_once_with("/test/address", 42)
        self.assertEqual(self.client.addr_log, ["/test/address"])

    def test_transport_controls(self):
        """Test transport control methods"""
        # Test play with different states
        self.client.play(True)
        self.client.client.send_message.assert_called_with("/play", 1)

        self.client.play(False)
        self.client.client.send_message.assert_called_with("/play", 0)

    def test_device_controls(self):
        """Test device control methods"""
        # Test toggle device bypass
        self.client.toggle_device_bypass()
        self.client.client.send_message.assert_called_with("/device/bypass", None)

        # Test select device sibling
        self.client.select_device_sibling(3)
        self.client.client.send_message.assert_called_with(
            "/device/sibling/3/select", 1
        )

        # Test select device by index
        self.client.select_device_by_index(2)
        self.client.client.send_message.assert_called_with("/device/select/2", 1)

        # Test select invalid device index
        with pytest.raises(InvalidParameterError):
            self.client.select_device_by_index(0)  # Below range

        # Test select invalid sibling
        with pytest.raises(InvalidParameterError):
            self.client.select_device_sibling(0)  # Below range
        with pytest.raises(InvalidParameterError):
            self.client.select_device_sibling(9)  # Above range

        # Test navigate device next
        self.client.navigate_device("next")
        self.client.client.send_message.assert_called_with("/device/+", None)

        # Test navigate device previous
        self.client.navigate_device("previous")
        self.client.client.send_message.assert_called_with("/device/-", None)

        # Test invalid navigation direction
        with pytest.raises(InvalidParameterError):
            self.client.navigate_device("invalid")

        with pytest.raises(InvalidParameterError):
            self.client.set_automation_write_mode("")

        with pytest.raises(InvalidParameterError):
            self.client.send_midi_program_change(1, 200)

        # Test enter device layer
        self.client.enter_device_layer(2)
        self.client.client.send_message.assert_called_with(
            "/device/layer/2/enter", None
        )

        # Test exit device layer
        self.client.exit_device_layer()
        self.client.client.send_message.assert_called_with("/device/layer/parent", None)

        # Test toggle device window
        self.client.toggle_device_window()
        self.client.client.send_message.assert_called_with("/device/window", None)

        self.client.play()
        self.client.client.send_message.assert_called_with("/play", None)

        # Test stop
        self.client.stop()
        self.client.client.send_message.assert_called_with("/stop", 1)

        # Test playhead and arranger record
        self.client.set_playhead_beats(32.0)
        self.client.client.send_message.assert_called_with("/time", 32.0)
        self.client.start_arranger_record()
        self.client.client.send_message.assert_called_with("/record", None)

        self.client.toggle_write_arranger_automation()
        self.client.client.send_message.assert_called_with("/autowrite", None)
        self.client.toggle_write_launcher_automation()
        self.client.client.send_message.assert_called_with("/autowrite/launcher", None)
        self.client.set_automation_write_mode("LATCH")
        self.client.client.send_message.assert_called_with("/automationWriteMode", "LATCH")

        self.client.send_midi_program_change(1, 42)
        self.client.client.send_message.assert_called_with("/vkb_midi/1/program", 42)

        self.client.set_device_parameter_touched(3, True)
        self.client.client.send_message.assert_called_with("/device/param/3/touched", 1)
        self.client.set_device_parameter_touched(3, False)
        self.client.client.send_message.assert_called_with("/device/param/3/touched", 0)

        # Test tempo
        self.client.set_tempo(120.5)
        self.client.client.send_message.assert_called_with("/tempo/raw", 120.5)

        # Test tempo clamping
        self.client.set_tempo(1200)
        self.client.client.send_message.assert_called_with("/tempo/raw", 999)

    def test_osc_bank_rejects_track_beyond_page(self):
        """Bitwig uses bank-relative indices (default 8); 9 triggers Kotlin OOB in host."""
        with pytest.raises(InvalidParameterError, match="between 1 and 8"):
            self.client.select_track(9)
        with pytest.raises(InvalidParameterError, match="between 1 and 8"):
            self.client.launcher_clip_insert_file(9, 1, "C:/x.mid")

    def test_osc_bank_page_size_override(self):
        c = BitwigOSCClient(osc_bank_page_size=16)
        c.client = MagicMock()
        c.select_track(9)
        c.client.send_message.assert_called_with("/track/9/select", 1)

    def test_track_controls(self):
        """Test track control methods"""
        # Test volume
        self.client.set_track_volume(1, 64)
        self.client.client.send_message.assert_called_with("/track/1/volume", 64)

        # Test pan
        self.client.set_track_pan(2, 32)
        self.client.client.send_message.assert_called_with("/track/2/pan", 32)

        # Test mute
        self.client.set_track_mute(3, True)
        self.client.client.send_message.assert_called_with("/track/3/mute", 1)

        self.client.toggle_track_mute(4)
        self.client.client.send_message.assert_called_with("/track/4/mute", None)

    def test_track_session_and_layout_osc(self):
        """Add/select tracks, bank navigation, layout (session start)."""
        self.client.add_track_instrument()
        self.client.client.send_message.assert_called_with(
            "/track/add/instrument", None
        )
        self.client.add_track_audio()
        self.client.client.send_message.assert_called_with("/track/add/audio", None)
        self.client.add_track_effect()
        self.client.client.send_message.assert_called_with("/track/add/effect", None)

        self.client.select_track(2)
        self.client.client.send_message.assert_called_with("/track/2/select", 1)
        self.client.navigate_track_selection("next")
        self.client.client.send_message.assert_called_with("/track/+", None)
        self.client.navigate_track_selection("previous")
        self.client.client.send_message.assert_called_with("/track/-", None)

        self.client.navigate_track_bank("next", page=False)
        self.client.client.send_message.assert_called_with("/track/bank/+", None)
        self.client.navigate_track_bank("previous", page=True)
        self.client.client.send_message.assert_called_with("/track/bank/page/-", None)

        self.client.toggle_track_bank_mode()
        self.client.client.send_message.assert_called_with("/track/toggleBank", None)

        self.client.set_track_name(1, "Kick")
        self.client.client.send_message.assert_called_with("/track/1/name", "Kick")
        self.client.set_track_record_arm(1, True)
        self.client.client.send_message.assert_called_with("/track/1/recarm", 1)
        self.client.set_track_solo(2, True)
        self.client.client.send_message.assert_called_with("/track/2/solo", 1)

        self.client.duplicate_track(1)
        self.client.client.send_message.assert_called_with("/track/1/duplicate", None)
        self.client.remove_track(3)
        self.client.client.send_message.assert_called_with("/track/3/remove", None)

        self.client.set_layout("arrange")
        self.client.client.send_message.assert_called_with("/layout/arrange", None)

        with pytest.raises(InvalidParameterError):
            self.client.set_layout("invalid")

    def test_composition_and_launcher_osc(self):
        """Clip launcher, scenes, and virtual MIDI addresses"""
        self.client.send_midi_note(1, 60, 100)
        self.client.client.send_message.assert_called_with("/vkb_midi/1/note/60", 100)
        self.client.send_midi_note(2, 60, 0)
        self.client.client.send_message.assert_called_with("/vkb_midi/2/note/60", 0)
        self.client.send_midi_drum(10, 36, 110)
        self.client.client.send_message.assert_called_with("/vkb_midi/10/drum/36", 110)

        self.client.launcher_clip_select(2, 3)
        self.client.client.send_message.assert_called_with(
            "/track/2/clip/3/select", None
        )

        self.client.client.send_message.reset_mock()
        self.client.prepare_launcher_clip_slot(1, 2)
        self.client.client.send_message.assert_has_calls(
            [
                call("/refresh", 1),
                call("/track/1/select", 1),
                call("/track/1/clip/2/select", None),
            ]
        )
        self.client.client.send_message.reset_mock()
        self.client.toggle_arranger_clip_launcher_visible()
        self.client.client.send_message.assert_called_with(
            "/arranger/clipLauncherSectionVisibility", None
        )
        self.client.launcher_clip_create(1, 1, 16.0)
        self.client.client.send_message.assert_called_with(
            "/track/1/clip/1/create", 16.0
        )
        self.client.launcher_clip_launch(1, 2, True)
        self.client.client.send_message.assert_called_with(
            "/track/1/clip/2/launch", 1
        )
        self.client.launcher_clip_launch(1, 2, False)
        self.client.client.send_message.assert_called_with(
            "/track/1/clip/2/launch", 0
        )
        self.client.launcher_clip_record(2, 1)
        self.client.client.send_message.assert_called_with(
            "/track/2/clip/1/record", None
        )
        self.client.launcher_clip_remove(1, 4)
        self.client.client.send_message.assert_called_with(
            "/track/1/clip/4/remove", None
        )
        self.client.launcher_clip_duplicate(2, 2)
        self.client.client.send_message.assert_called_with(
            "/track/2/clip/2/duplicate", None
        )
        self.client.launcher_clip_insert_file(1, 1, r"C:\tmp\loop.wav")
        self.client.client.send_message.assert_called_with(
            "/track/1/clip/1/insertFile", r"C:\tmp\loop.wav"
        )
        self.client.launcher_track_stop(3)
        self.client.client.send_message.assert_called_with("/track/3/clip/stop", None)
        self.client.launcher_track_return_to_arrangement(2)
        self.client.client.send_message.assert_called_with(
            "/track/2/clip/returntoarrangement", None
        )
        self.client.clips_stop_all()
        self.client.client.send_message.assert_called_with("/clip/stopall", None)
        self.client.clip_create_at_cursor(8.0)
        self.client.client.send_message.assert_called_with("/clip/create", 8.0)
        self.client.clip_quantize_selected()
        self.client.client.send_message.assert_called_with("/clip/quantize", None)
        self.client.clip_set_name_selected("Kick 4x4")
        self.client.client.send_message.assert_called_with(
            "/clip/name", "Kick 4x4"
        )
        self.client.toggle_clip_launcher_overdub()
        self.client.client.send_message.assert_called_with("/overdub/launcher", None)
        self.client.toggle_arranger_overdub()
        self.client.client.send_message.assert_called_with("/overdub", None)
        self.client.scene_add()
        self.client.client.send_message.assert_called_with("/scene/add", None)
        self.client.scene_launch(2, True)
        self.client.client.send_message.assert_called_with("/scene/2/launch", 1)

        with pytest.raises(InvalidParameterError):
            self.client.send_midi_note(0, 60, 100)
        with pytest.raises(InvalidParameterError):
            self.client.launcher_clip_create(1, 1, 0)

    def test_browser_basic_controls(self):
        """Test basic browser control methods"""
        # Test browse for device
        self.client.browse_for_device("after")
        self.client.client.send_message.assert_called_with("/browser/device", None)

        self.client.browse_for_device("before")
        self.client.client.send_message.assert_called_with(
            "/browser/device/before", None
        )

        # Test invalid position
        with pytest.raises(InvalidParameterError):
            self.client.browse_for_device("invalid")

        # Test browse for preset
        self.client.browse_for_preset()
        self.client.client.send_message.assert_called_with("/browser/preset", None)

        # Test commit browser selection
        self.client.commit_browser_selection()
        self.client.client.send_message.assert_called_with("/browser/commit", None)

        # Test cancel browser
        self.client.cancel_browser()
        self.client.client.send_message.assert_called_with("/browser/cancel", None)

    def test_browser_navigation(self):
        """Test browser navigation methods"""
        # Test navigate browser tab
        self.client.navigate_browser_tab("+")
        self.client.client.send_message.assert_called_with("/browser/tab/+", None)

        self.client.navigate_browser_tab("-")
        self.client.client.send_message.assert_called_with("/browser/tab/-", None)

        # Test invalid direction
        with pytest.raises(InvalidParameterError):
            self.client.navigate_browser_tab("invalid")

        # Test navigate browser filter
        self.client.navigate_browser_filter(1, "+")
        self.client.client.send_message.assert_called_with("/browser/filter/1/+", None)

        self.client.navigate_browser_filter(2, "-")
        self.client.client.send_message.assert_called_with("/browser/filter/2/-", None)

        # Test invalid filter index
        with pytest.raises(InvalidParameterError):
            self.client.navigate_browser_filter(0, "+")  # Below range
        with pytest.raises(InvalidParameterError):
            self.client.navigate_browser_filter(7, "+")  # Above range

        # Test invalid direction
        with pytest.raises(InvalidParameterError):
            self.client.navigate_browser_filter(1, "invalid")

        # Test reset browser filter
        self.client.reset_browser_filter(1)
        self.client.client.send_message.assert_called_with(
            "/browser/filter/1/reset", None
        )

        # Test invalid filter index
        with pytest.raises(InvalidParameterError):
            self.client.reset_browser_filter(0)  # Below range
        with pytest.raises(InvalidParameterError):
            self.client.reset_browser_filter(7)  # Above range

        # Test navigate browser result
        self.client.navigate_browser_result("+")
        self.client.client.send_message.assert_called_with("/browser/result/+", None)

        self.client.navigate_browser_result("-")
        self.client.client.send_message.assert_called_with("/browser/result/-", None)

        # Test invalid direction
        with pytest.raises(InvalidParameterError):
            self.client.navigate_browser_result("invalid")

        # Test navigate browser result page
        self.client.navigate_browser_result_page("+")
        self.client.client.send_message.assert_called_with(
            "/browser/result/page/+", None
        )

        self.client.navigate_browser_result_page("-")
        self.client.client.send_message.assert_called_with(
            "/browser/result/page/-", None
        )

        # Test invalid direction
        with pytest.raises(InvalidParameterError):
            self.client.navigate_browser_result_page("invalid")

    def test_browser_convenience_methods(self):
        """Test browser convenience methods"""
        # Test insert device after selected
        self.client.insert_device_after_selected()
        self.client.client.send_message.assert_called_with("/browser/device", None)

        # Test insert device before selected
        self.client.insert_device_before_selected()
        self.client.client.send_message.assert_called_with(
            "/browser/device/before", None
        )

        # Test browse device presets
        self.client.browse_device_presets()
        self.client.client.send_message.assert_called_with("/browser/preset", None)

        # Test select next browser tab
        self.client.select_next_browser_tab()
        self.client.client.send_message.assert_called_with("/browser/tab/+", None)

        # Test select previous browser tab
        self.client.select_previous_browser_tab()
        self.client.client.send_message.assert_called_with("/browser/tab/-", None)

        # Test select next filter option
        self.client.select_next_filter_option(1)
        self.client.client.send_message.assert_called_with("/browser/filter/1/+", None)

        # Test select previous filter option
        self.client.select_previous_filter_option(2)
        self.client.client.send_message.assert_called_with("/browser/filter/2/-", None)

        # Test select next browser result
        self.client.select_next_browser_result()
        self.client.client.send_message.assert_called_with("/browser/result/+", None)

        # Test select previous browser result
        self.client.select_previous_browser_result()
        self.client.client.send_message.assert_called_with("/browser/result/-", None)

        # Test select next browser result page
        self.client.select_next_browser_result_page()
        self.client.client.send_message.assert_called_with(
            "/browser/result/page/+", None
        )

        # Test select previous browser result page
        self.client.select_previous_browser_result_page()
        self.client.client.send_message.assert_called_with(
            "/browser/result/page/-", None
        )

    def test_browser_workflow_methods(self):
        """Test browser workflow methods"""
        # Test browse and insert device
        self.client.browse_and_insert_device(
            num_tabs=2, num_filters=[(1, 3), (2, -1)], num_results=4
        )

        expected_calls = [
            call("/browser/device", None),  # Open browser
            call("/browser/tab/+", None),  # Tab navigation 1
            call("/browser/tab/+", None),  # Tab navigation 2
            call("/browser/filter/1/+", None),  # Filter 1, nav 1
            call("/browser/filter/1/+", None),  # Filter 1, nav 2
            call("/browser/filter/1/+", None),  # Filter 1, nav 3
            call("/browser/filter/2/-", None),  # Filter 2, nav 1
            call("/browser/result/+", None),  # Result nav 1
            call("/browser/result/+", None),  # Result nav 2
            call("/browser/result/+", None),  # Result nav 3
            call("/browser/result/+", None),  # Result nav 4
            call("/browser/commit", None),  # Commit selection
        ]

        # Check that the calls were made in the right order
        self.client.client.send_message.assert_has_calls(
            expected_calls, any_order=False
        )

        # Reset the mock
        self.client.client.send_message.reset_mock()

        # Test browse and load preset
        self.client.browse_and_load_preset(num_filters=[(1, 2)], num_results=3)

        expected_calls = [
            call("/browser/preset", None),  # Open preset browser
            call("/browser/filter/1/+", None),  # Filter 1, nav 1
            call("/browser/filter/1/+", None),  # Filter 1, nav 2
            call("/browser/result/+", None),  # Result nav 1
            call("/browser/result/+", None),  # Result nav 2
            call("/browser/result/+", None),  # Result nav 3
            call("/browser/commit", None),  # Commit selection
        ]

        # Check that the calls were made in the right order
        self.client.client.send_message.assert_has_calls(
            expected_calls, any_order=False
        )


if __name__ == "__main__":
    unittest.main()
