"""Tests for seed MIDI generation."""

from pathlib import Path

import pytest

from bitwig_mcp_server.seed_midi import (
    SEED_PATTERN_NAMES,
    build_drums_all_in_one_gm_8bar_mid,
    build_kick_four_on_floor_8bar_mid,
    build_kick_four_on_floor_mid,
    euclidean_rhythm_indices,
    resolve_seed_pattern,
    write_seed_midi_file,
)


def test_build_kick_mid_header_and_track() -> None:
    data = build_kick_four_on_floor_mid()
    assert data[:4] == b"MThd"
    assert b"MTrk" in data
    assert len(data) > 40


def test_write_seed_midi_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "bitwig_mcp_server.seed_midi.seed_midi_cache_dir", lambda: tmp_path
    )
    p = write_seed_midi_file("kick_four_on_floor")
    assert p.exists()
    raw = p.read_bytes()
    assert raw.startswith(b"MThd")


def test_write_seed_unknown_pattern() -> None:
    with pytest.raises(ValueError, match="Unknown seed pattern"):
        write_seed_midi_file("not_a_pattern")


def test_write_all_seed_patterns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "bitwig_mcp_server.seed_midi.seed_midi_cache_dir", lambda: tmp_path
    )
    for name in SEED_PATTERN_NAMES:
        p = write_seed_midi_file(name)
        assert p.exists()
        assert p.read_bytes().startswith(b"MThd")


def test_euclidean_rhythm_indices_basic() -> None:
    assert euclidean_rhythm_indices(3, 8) == [0, 3, 6]
    assert euclidean_rhythm_indices(5, 16)[0] == 0
    assert len(euclidean_rhythm_indices(5, 16)) == 5


def test_resolve_seed_pattern_8bar() -> None:
    assert resolve_seed_pattern("kick_four_on_floor", 8) == "kick_four_on_floor_8bar"
    assert resolve_seed_pattern("kick_four_on_floor_8bar", 8) == "kick_four_on_floor_8bar"
    assert resolve_seed_pattern("kick_four_on_floor", 1) == "kick_four_on_floor"


def test_eight_bar_midi_longer() -> None:
    assert len(build_kick_four_on_floor_8bar_mid()) > len(build_kick_four_on_floor_mid())
    assert len(build_drums_all_in_one_gm_8bar_mid()) > 800


def test_write_seed_bars_8(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "bitwig_mcp_server.seed_midi.seed_midi_cache_dir", lambda: tmp_path
    )
    p = write_seed_midi_file("kick_four_on_floor", bars=8)
    assert "kick_four_on_floor_8bar" in p.name
    assert p.read_bytes().startswith(b"MThd")
