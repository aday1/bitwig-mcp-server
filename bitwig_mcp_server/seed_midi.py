"""Standard MIDI files for Bitwig launcher clips (OSC insertFile)."""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Final

_SEED_SUBDIR: Final[str] = "bitwig-mcp-server"

TPQ: Final[int] = 480
TICKS_PER_BAR: Final[int] = TPQ * 4
TICKS_2_BARS: Final[int] = TICKS_PER_BAR * 2
TICKS_8_BARS: Final[int] = TICKS_PER_BAR * 8


def euclidean_rhythm_indices(pulses: int, steps: int) -> list[int]:
    """Toussaint-style Euclidean hit positions in [0, steps), k pulses on n steps."""
    if pulses <= 0:
        return []
    if pulses >= steps:
        return list(range(steps))
    pauses = steps - pulses
    per_pulse = pauses // pulses
    remainder = pauses % pulses
    indices: list[int] = []
    tick = 0
    for i in range(pulses):
        indices.append(tick)
        spacing = per_pulse + (1 if i < remainder else 0)
        tick += 1 + spacing
    return indices


def _vlq(n: int) -> bytes:
    if n < 0:
        raise ValueError("vlq must be non-negative")
    buf = bytearray()
    buf.append(n & 0x7F)
    n >>= 7
    while n:
        buf.insert(0, (n & 0x7F) | 0x80)
        n >>= 7
    return bytes(buf)


def _mtrk(payload: bytes) -> bytes:
    return b"MTrk" + struct.pack(">I", len(payload)) + payload


def _mid_header_single_track() -> bytes:
    return b"MThd" + struct.pack(">I", 6) + struct.pack(">HHH", 0, 1, TPQ)


def _events_to_mtrk(events: list[tuple[int, bytes]]) -> bytes:
    events_sorted = sorted(events, key=lambda x: (x[0], x[1]))
    body = bytearray()
    prev = 0
    for tick, msg in events_sorted:
        body.extend(_vlq(tick - prev))
        body.extend(msg)
        prev = tick
    body.extend(_vlq(0))
    body.extend(bytes([0xFF, 0x2F, 0x00]))
    return bytes(body)


def _repeat_bars(ev: list[tuple[int, bytes]], num_bars: int) -> list[tuple[int, bytes]]:
    out: list[tuple[int, bytes]] = []
    for b in range(num_bars):
        o = b * TICKS_PER_BAR
        for t, m in ev:
            out.append((t + o, m))
    return out


def _tile_multibar(
    ev_block: list[tuple[int, bytes]], block_ticks: int, repeats: int
) -> list[tuple[int, bytes]]:
    out: list[tuple[int, bytes]] = []
    for r in range(repeats):
        o = r * block_ticks
        for t, m in ev_block:
            out.append((t + o, m))
    return out


def _ch1_on(nn: int, vel: int = 80) -> bytes:
    return bytes([0x90, nn & 0x7F, vel & 0x7F])


def _ch1_off(nn: int) -> bytes:
    return bytes([0x90, nn & 0x7F, 0x00])


def _ch10_on(nn: int, vel: int = 90) -> bytes:
    return bytes([0x99, nn & 0x7F, vel & 0x7F])


def _ch10_off(nn: int) -> bytes:
    return bytes([0x99, nn & 0x7F, 0x00])


def _cc(channel_0: int, controller: int, value: int) -> bytes:
    """Control change; channel_0 is 0..15 (ch1 = 0)."""
    return bytes([0xB0 | (channel_0 & 0x0F), controller & 0x7F, value & 0x7F])


def _modwheel_sweep_events(
    num_bars: int,
    channel_0: int,
    *,
    ticks_step: int = 120,
    low: int = 18,
    high: int = 108,
) -> list[tuple[int, bytes]]:
    """CC1 (mod wheel) triangle LFO so synths with MW-to-filter or PWM actually move."""
    ev: list[tuple[int, bytes]] = []
    total = num_bars * TICKS_PER_BAR
    period_steps = 28
    step = 0
    for tick in range(0, total, ticks_step):
        pos = step % period_steps
        half = period_steps // 2
        if pos < half:
            val = low + (high - low) * pos // max(half - 1, 1)
        else:
            q = pos - half
            val = high - (high - low) * q // max(half - 1, 1)
        ev.append((tick, _cc(channel_0, 1, val)))
        step += 1
    return ev


def _expression_swells_beat_events(num_bars: int, channel_0: int) -> list[tuple[int, bytes]]:
    """CC11 expression stepped each quarter for level breathing (chords/pads)."""
    ev: list[tuple[int, bytes]] = []
    for bar in range(num_bars):
        o = bar * TICKS_PER_BAR
        for i, val in enumerate((88, 102, 76, 118)):
            ev.append((o + i * 480, _cc(channel_0, 11, val & 0x7F)))
    return ev


def _kick_four_one_bar_events() -> list[tuple[int, bytes]]:
    ev: list[tuple[int, bytes]] = []
    pairs = [(0, 100), (480, 98), (960, 102), (1440, 100)]
    for t_on, vel in pairs:
        ev.append((t_on, _ch10_on(36, vel)))
        ev.append((t_on + 100, _ch10_off(36)))
    return ev


def build_kick_four_on_floor_mid() -> bytes:
    return _mid_header_single_track() + _mtrk(
        _events_to_mtrk(_kick_four_one_bar_events())
    )


def build_kick_four_on_floor_8bar_mid() -> bytes:
    ev = _repeat_bars(_kick_four_one_bar_events(), 8)
    o_last = 7 * TICKS_PER_BAR
    ev.append((o_last + 1760, _ch10_on(49, 85)))
    ev.append((o_last + 1880, _ch10_off(49)))
    return _mid_header_single_track() + _mtrk(_events_to_mtrk(ev))


def _hats_one_bar_events() -> list[tuple[int, bytes]]:
    ev: list[tuple[int, bytes]] = []
    for i in range(8):
        t_on = i * 240
        vel = 92 if (i % 2) == 1 else 68
        ev.append((t_on, _ch10_on(42, vel)))
        ev.append((t_on + 70, _ch10_off(42)))
    return ev


def build_hats_eighths_drive_mid() -> bytes:
    return _mid_header_single_track() + _mtrk(_events_to_mtrk(_hats_one_bar_events()))


def build_hats_eighths_drive_8bar_mid() -> bytes:
    ev = _repeat_bars(_hats_one_bar_events(), 8)
    for bar in (3, 7):
        o = bar * TICKS_PER_BAR
        ev.append((o + 1680, _ch10_on(46, 78)))
        ev.append((o + 1840, _ch10_off(46)))
    return _mid_header_single_track() + _mtrk(_events_to_mtrk(ev))


def _snare_backbeat_one_bar_events() -> list[tuple[int, bytes]]:
    return [
        (480, _ch10_on(38, 110)),
        (600, _ch10_off(38)),
        (1440, _ch10_on(38, 110)),
        (1560, _ch10_off(38)),
    ]


def build_snare_backbeat_44_mid() -> bytes:
    return _mid_header_single_track() + _mtrk(
        _events_to_mtrk(_snare_backbeat_one_bar_events())
    )


def build_snare_backbeat_44_8bar_mid() -> bytes:
    ev: list[tuple[int, bytes]] = []
    for bar in range(8):
        o = bar * TICKS_PER_BAR
        base = _snare_backbeat_one_bar_events()
        for t, m in base:
            ev.append((o + t, m))
        if bar % 2 == 1:
            ev.append((o + 240, _ch10_on(38, 52)))
            ev.append((o + 300, _ch10_off(38)))
            ev.append((o + 720, _ch10_on(38, 48)))
            ev.append((o + 780, _ch10_off(38)))
    return _mid_header_single_track() + _mtrk(_events_to_mtrk(ev))


def build_drums_all_in_one_gm_8bar_mid() -> bytes:
    """Single-track GM-style kit (ch10). Use Bitwig Drum Machine on this track."""
    ev: list[tuple[int, bytes]] = []
    for bar in range(8):
        o = bar * TICKS_PER_BAR
        for step, vel in [(0, 100), (480, 96), (960, 104), (1440, 98)]:
            ev.append((o + step, _ch10_on(36, vel)))
            ev.append((o + step + 95, _ch10_off(36)))
        for i in range(8):
            t = o + i * 240
            vel = 76 + (i % 2) * 18
            ev.append((t, _ch10_on(42, vel)))
            ev.append((t + 55, _ch10_off(42)))
        for beat in (1, 3):
            t = o + beat * 480
            ev.append((t, _ch10_on(38, 112)))
            ev.append((t + 110, _ch10_off(38)))
        if bar % 4 == 3:
            ev.append((o + 360, _ch10_on(37, 80)))
            ev.append((o + 420, _ch10_off(37)))
        if bar == 7:
            for i, nn in enumerate((41, 43, 45, 47)):
                t = o + 960 + i * 120
                ev.append((t, _ch10_on(nn, 100)))
                ev.append((t + 90, _ch10_off(nn)))
            ev.append((o + 1680, _ch10_on(49, 95)))
            ev.append((o + 1820, _ch10_off(49)))
    return _mid_header_single_track() + _mtrk(_events_to_mtrk(ev))


def build_bass_house_root_move_mid() -> bytes:
    ev = [
        (0, _ch1_on(0x30, 0x78)),
        (400, _ch1_off(0x30)),
        (480, _ch1_on(0x30, 0x78)),
        (880, _ch1_off(0x30)),
        (960, _ch1_on(0x37, 0x76)),
        (1360, _ch1_off(0x37)),
        (1440, _ch1_on(0x37, 0x76)),
        (1840, _ch1_off(0x37)),
    ]
    return _mid_header_single_track() + _mtrk(_events_to_mtrk(ev))


def build_bass_progression_8bar_mid() -> bytes:
    """Eight bars: roots walk Am F C G two bars each (ch1)."""
    roots = (57, 57, 53, 53, 60, 60, 55, 55)
    ev: list[tuple[int, bytes]] = []
    ev.extend(_modwheel_sweep_events(8, 0, ticks_step=160, low=12, high=92))
    for bar, root in enumerate(roots):
        o = bar * TICKS_PER_BAR
        for q in range(4):
            t0 = o + q * 480
            ev.append((t0, _ch1_on(root, 82)))
            ev.append((t0 + 400, _ch1_off(root)))
    return _mid_header_single_track() + _mtrk(_events_to_mtrk(ev))


def build_chords_min_stab_13_mid() -> bytes:
    ev: list[tuple[int, bytes]] = []

    def stab(t0: int) -> None:
        ev.append((t0, bytes([0x91, 0x3C, 0x64])))
        ev.append((t0, bytes([0x91, 0x3F, 0x64])))
        ev.append((t0, bytes([0x91, 0x43, 0x64])))
        t1 = t0 + 110
        ev.append((t1, bytes([0x91, 0x3C, 0x00])))
        ev.append((t1, bytes([0x91, 0x3F, 0x00])))
        ev.append((t1, bytes([0x91, 0x43, 0x00])))

    stab(0)
    stab(960)
    return _mid_header_single_track() + _mtrk(_events_to_mtrk(ev))


def build_chords_cycle_8bar_mid() -> bytes:
    """Am F C G: two bars each, stabs on 1 and 3 (ch2)."""
    voicings = [
        (57, 60, 64),
        (53, 57, 60),
        (60, 64, 67),
        (55, 59, 62),
    ]
    ev: list[tuple[int, bytes]] = []
    ev.extend(_modwheel_sweep_events(8, 1, ticks_step=90, low=22, high=98))
    ev.extend(_expression_swells_beat_events(8, 1))
    for bi, (a, b, c) in enumerate(voicings):
        for sub in range(2):
            bar = bi * 2 + sub
            o = bar * TICKS_PER_BAR
            for beat in (0, 960):
                t0 = o + beat
                ev.append((t0, bytes([0x91, a, 0x64])))
                ev.append((t0, bytes([0x91, b, 0x64])))
                ev.append((t0, bytes([0x91, c, 0x64])))
                t1o = t0 + 180
                ev.append((t1o, bytes([0x91, a, 0x00])))
                ev.append((t1o, bytes([0x91, b, 0x00])))
                ev.append((t1o, bytes([0x91, c, 0x00])))
    return _mid_header_single_track() + _mtrk(_events_to_mtrk(ev))


def build_lead_eighths_hook_mid() -> bytes:
    notes = (0x48, 0x48, 0x4C, 0x4A, 0x48, 0x4D, 0x4C, 0x48)
    ev: list[tuple[int, bytes]] = []
    for i, nn in enumerate(notes):
        t_on = i * 240
        ev.append((t_on, bytes([0x92, nn, 0x6A])))
        ev.append((t_on + 130, bytes([0x92, nn, 0x00])))
    return _mid_header_single_track() + _mtrk(_events_to_mtrk(ev))


def build_lead_arc_8bar_mid() -> bytes:
    """Eight-bar contour on ch3 with phrase rests."""
    phrase = (
        72,
        74,
        76,
        74,
        72,
        69,
        72,
        74,
        76,
        79,
        77,
        76,
        74,
        72,
        71,
        72,
    )
    ev: list[tuple[int, bytes]] = []
    ev.extend(_modwheel_sweep_events(8, 2, ticks_step=80, low=30, high=115))
    for bar in range(8):
        o = bar * TICKS_PER_BAR
        base = bar % 2
        for i in range(8):
            nn = phrase[(bar * 2 + i + base) % len(phrase)]
            t_on = o + i * 240
            if i == 7 and bar % 3 == 2:
                continue
            ev.append((t_on, bytes([0x92, nn, 0x6C])))
            ev.append((t_on + 160, bytes([0x92, nn, 0x00])))
    return _mid_header_single_track() + _mtrk(_events_to_mtrk(ev))


def _euclid_kick_one_bar_events() -> list[tuple[int, bytes]]:
    ev: list[tuple[int, bytes]] = []
    step = TICKS_PER_BAR // 16
    for idx in euclidean_rhythm_indices(5, 16):
        t_on = idx * step
        ev.append((t_on, _ch10_on(36, 100)))
        ev.append((t_on + 70, _ch10_off(36)))
    return ev


def build_euclid_kick_5_16_mid() -> bytes:
    return _mid_header_single_track() + _mtrk(
        _events_to_mtrk(_euclid_kick_one_bar_events())
    )


def build_euclid_kick_5_16_8bar_mid() -> bytes:
    return _mid_header_single_track() + _mtrk(
        _events_to_mtrk(_repeat_bars(_euclid_kick_one_bar_events(), 8))
    )


def _euclid_hat_one_bar_events() -> list[tuple[int, bytes]]:
    ev: list[tuple[int, bytes]] = []
    step = TICKS_PER_BAR // 16
    for j, idx in enumerate(euclidean_rhythm_indices(7, 16)):
        t_on = idx * step
        vel = 88 if j % 2 == 0 else 66
        ev.append((t_on, _ch10_on(42, vel)))
        ev.append((t_on + 55, _ch10_off(42)))
    return ev


def build_euclid_hat_7_16_mid() -> bytes:
    return _mid_header_single_track() + _mtrk(
        _events_to_mtrk(_euclid_hat_one_bar_events())
    )


def build_euclid_hat_7_16_8bar_mid() -> bytes:
    return _mid_header_single_track() + _mtrk(
        _events_to_mtrk(_repeat_bars(_euclid_hat_one_bar_events(), 8))
    )


def build_euclid_snare_3_8_mid() -> bytes:
    ev: list[tuple[int, bytes]] = []
    step = TICKS_PER_BAR // 8
    for idx in euclidean_rhythm_indices(3, 8):
        t_on = idx * step
        ev.append((t_on, _ch10_on(38, 105)))
        ev.append((t_on + 90, _ch10_off(38)))
    return _mid_header_single_track() + _mtrk(_events_to_mtrk(ev))


def build_euclid_clap_5_12_mid() -> bytes:
    ev: list[tuple[int, bytes]] = []
    steps = 12
    step = TICKS_PER_BAR // steps
    for idx in euclidean_rhythm_indices(5, steps):
        t_on = idx * step
        ev.append((t_on, _ch10_on(39, 95)))
        ev.append((t_on + 65, _ch10_off(39)))
    return _mid_header_single_track() + _mtrk(_events_to_mtrk(ev))


def _fugue_violin_events_2bar() -> list[tuple[int, bytes]]:
    ev: list[tuple[int, bytes]] = []
    pairs = [
        (0, 74, 200),
        (240, 69, 200),
        (480, 74, 220),
        (720, 72, 200),
        (960, 71, 200),
        (1200, 69, 200),
        (1440, 67, 200),
        (1680, 66, 220),
        (1920, 67, 200),
        (2160, 69, 200),
        (2400, 70, 220),
        (2640, 69, 200),
        (2880, 67, 200),
        (3120, 65, 200),
        (3360, 64, 200),
        (3600, 62, 240),
    ]
    for t_on, nn, gate in pairs:
        ev.append((t_on, _ch1_on(nn, 88)))
        ev.append((t_on + gate, _ch1_off(nn)))
    return ev


def build_fugue_violin_subject_2bar_mid() -> bytes:
    return _mid_header_single_track() + _mtrk(
        _events_to_mtrk(_fugue_violin_events_2bar())
    )


def build_fugue_violin_subject_8bar_mid() -> bytes:
    ev = _tile_multibar(_fugue_violin_events_2bar(), TICKS_2_BARS, 4)
    return _mid_header_single_track() + _mtrk(_events_to_mtrk(ev))


def _fugue_piano_events_2bar() -> list[tuple[int, bytes]]:
    ev: list[tuple[int, bytes]] = []
    seq = [
        (0, 57, 180),
        (240, 64, 180),
        (480, 69, 200),
        (720, 67, 160),
        (960, 65, 160),
        (1200, 64, 160),
        (1440, 62, 160),
        (1680, 60, 200),
        (1920, 60, 180),
        (2160, 62, 160),
        (2400, 64, 160),
        (2640, 65, 160),
        (2880, 64, 160),
        (3120, 62, 160),
        (3360, 61, 200),
        (3600, 62, 220),
    ]
    for t_on, nn, gate in seq:
        ev.append((t_on, _ch1_on(nn, 76)))
        ev.append((t_on + gate, _ch1_off(nn)))
    return ev


def build_fugue_piano_answer_2bar_mid() -> bytes:
    return _mid_header_single_track() + _mtrk(
        _events_to_mtrk(_fugue_piano_events_2bar())
    )


def build_fugue_piano_answer_8bar_mid() -> bytes:
    ev = _tile_multibar(_fugue_piano_events_2bar(), TICKS_2_BARS, 4)
    return _mid_header_single_track() + _mtrk(_events_to_mtrk(ev))


def _fugue_organ_events_2bar() -> list[tuple[int, bytes]]:
    ev: list[tuple[int, bytes]] = []

    def chord(t0: int, notes: tuple[int, ...], duration: int) -> None:
        for nn in notes:
            ev.append((t0, _ch1_on(nn, 70)))
        t1 = t0 + duration
        for nn in notes:
            ev.append((t1, _ch1_off(nn)))

    chord(0, (50, 53, 57), 1880)
    chord(1920, (45, 48, 52), 1880)
    return ev


def build_fugue_organ_pedal_2bar_mid() -> bytes:
    return _mid_header_single_track() + _mtrk(_events_to_mtrk(_fugue_organ_events_2bar()))


def build_fugue_organ_pedal_8bar_mid() -> bytes:
    ev = _tile_multibar(_fugue_organ_events_2bar(), TICKS_2_BARS, 4)
    ev.extend(_modwheel_sweep_events(8, 0, ticks_step=200, low=22, high=104))
    return _mid_header_single_track() + _mtrk(_events_to_mtrk(ev))


def _counterpoint_alto_one_bar_events() -> list[tuple[int, bytes]]:
    ev: list[tuple[int, bytes]] = []
    notes = [
        (0, 65, 200),
        (240, 69, 200),
        (480, 67, 200),
        (720, 65, 200),
        (960, 64, 200),
        (1200, 62, 200),
        (1440, 61, 200),
        (1680, 62, 220),
    ]
    for t_on, nn, gate in notes:
        ev.append((t_on, _ch1_on(nn, 78)))
        ev.append((t_on + gate, _ch1_off(nn)))
    return ev


def build_counterpoint_alto_1bar_mid() -> bytes:
    return _mid_header_single_track() + _mtrk(
        _events_to_mtrk(_counterpoint_alto_one_bar_events())
    )


def build_counterpoint_alto_8bar_mid() -> bytes:
    return _mid_header_single_track() + _mtrk(
        _events_to_mtrk(_repeat_bars(_counterpoint_alto_one_bar_events(), 8))
    )


def build_counterpoint_tenor_1bar_mid() -> bytes:
    ev: list[tuple[int, bytes]] = []
    notes = [
        (0, 50, 220),
        (240, 53, 220),
        (480, 57, 220),
        (720, 53, 220),
        (960, 50, 220),
        (1200, 52, 220),
        (1440, 49, 220),
        (1680, 50, 240),
    ]
    for t_on, nn, gate in notes:
        ev.append((t_on, _ch1_on(nn, 74)))
        ev.append((t_on + gate, _ch1_off(nn)))
    return _mid_header_single_track() + _mtrk(_events_to_mtrk(ev))


def build_counterpoint_tenor_8bar_mid() -> bytes:
    ev: list[tuple[int, bytes]] = []
    seq = [50, 52, 53, 55, 57, 55, 53, 52]
    for bar in range(8):
        o = bar * TICKS_PER_BAR
        root = seq[bar % len(seq)]
        for i in range(8):
            nn = root + (0, 4, 7, 4)[i % 4]
            t_on = o + i * 240
            ev.append((t_on, _ch1_on(nn, 72)))
            ev.append((t_on + 200, _ch1_off(nn)))
    return _mid_header_single_track() + _mtrk(_events_to_mtrk(ev))


def build_piano_alberti_dm_1bar_mid() -> bytes:
    ev: list[tuple[int, bytes]] = []
    pat = [62, 65, 69, 65]
    for i in range(8):
        nn = pat[i % 4]
        t_on = i * 240
        ev.append((t_on, _ch1_on(nn, 72)))
        ev.append((t_on + 180, _ch1_off(nn)))
    return _mid_header_single_track() + _mtrk(_events_to_mtrk(ev))


def build_piano_alberti_dm_8bar_mid() -> bytes:
    ev: list[tuple[int, bytes]] = []
    pats = (
        [62, 65, 69, 65],
        [60, 64, 67, 64],
        [57, 60, 64, 60],
        [55, 59, 62, 59],
    )
    ev.extend(_modwheel_sweep_events(8, 0, ticks_step=100, low=14, high=72))
    ev.extend(_expression_swells_beat_events(8, 0))
    for bar in range(8):
        o = bar * TICKS_PER_BAR
        pat = pats[bar % len(pats)]
        for i in range(8):
            nn = pat[i % 4]
            t_on = o + i * 240
            ev.append((t_on, _ch1_on(nn, 70 + bar % 4)))
            ev.append((t_on + 170, _ch1_off(nn)))
    return _mid_header_single_track() + _mtrk(_events_to_mtrk(ev))


def build_organ_plenum_dm_1bar_mid() -> bytes:
    ev: list[tuple[int, bytes]] = []
    ev.append((0, _ch1_on(50, 68)))
    ev.append((0, _ch1_on(53, 68)))
    ev.append((0, _ch1_on(57, 68)))
    ev.append((0, _ch1_on(62, 62)))
    t_rel = 1680
    for nn in (50, 53, 57, 62):
        ev.append((t_rel, _ch1_off(nn)))
    ev.append((1800, _ch1_on(45, 80)))
    ev.append((1800, _ch1_on(52, 76)))
    ev.append((1800, _ch1_on(57, 76)))
    ev.append((1880, _ch1_off(45)))
    ev.append((1880, _ch1_off(52)))
    ev.append((1880, _ch1_off(57)))
    return _mid_header_single_track() + _mtrk(_events_to_mtrk(ev))


def build_organ_plenum_dm_8bar_mid() -> bytes:
    progressions = [
        (50, 53, 57, 62),
        (48, 52, 55, 60),
        (45, 48, 52, 57),
        (43, 47, 50, 55),
    ]
    ev: list[tuple[int, bytes]] = []
    ev.extend(_modwheel_sweep_events(8, 0, ticks_step=240, low=20, high=100))
    ev.extend(_expression_swells_beat_events(8, 0))
    for bar in range(8):
        o = bar * TICKS_PER_BAR
        a, b, c, d = progressions[bar % len(progressions)]
        ev.append((o, _ch1_on(a, 66)))
        ev.append((o, _ch1_on(b, 66)))
        ev.append((o, _ch1_on(c, 64)))
        ev.append((o, _ch1_on(d, 58)))
        t1 = o + 1760
        for nn in (a, b, c, d):
            ev.append((t1, _ch1_off(nn)))
    return _mid_header_single_track() + _mtrk(_events_to_mtrk(ev))


def _violin_ornament_one_bar_events() -> list[tuple[int, bytes]]:
    ev: list[tuple[int, bytes]] = []
    base = 74
    for i in range(16):
        t_on = i * 120
        nn = base if (i % 2) == 0 else base - 1
        ev.append((t_on, _ch1_on(nn, 70 + (i % 3) * 4)))
        ev.append((t_on + 90, _ch1_off(nn)))
    return ev


def build_violin_ornament_turn_1bar_mid() -> bytes:
    return _mid_header_single_track() + _mtrk(
        _events_to_mtrk(_violin_ornament_one_bar_events())
    )


def build_violin_ornament_turn_8bar_mid() -> bytes:
    ev = _repeat_bars(_violin_ornament_one_bar_events(), 8)
    ev.extend(_modwheel_sweep_events(8, 0, ticks_step=120, low=18, high=95))
    return _mid_header_single_track() + _mtrk(_events_to_mtrk(ev))


def build_pad_evolution_8bar_mid() -> bytes:
    """Slow ch1 held chords, 2 bars each."""
    stacks = [
        (57, 60, 64),
        (55, 59, 62),
        (53, 57, 60),
        (50, 53, 57),
    ]
    ev: list[tuple[int, bytes]] = []
    ev.extend(_modwheel_sweep_events(8, 0, ticks_step=360, low=8, high=58))
    ev.extend(_expression_swells_beat_events(8, 0))
    for bi, (a, b, c) in enumerate(stacks):
        for sub in range(2):
            bar = bi * 2 + sub
            o = bar * TICKS_PER_BAR
            ev.append((o, _ch1_on(a, 55)))
            ev.append((o, _ch1_on(b, 55)))
            ev.append((o, _ch1_on(c, 55)))
            t1 = o + 1880
            ev.append((t1, _ch1_off(a)))
            ev.append((t1, _ch1_off(b)))
            ev.append((t1, _ch1_off(c)))
    return _mid_header_single_track() + _mtrk(_events_to_mtrk(ev))


_BUILDERS: dict[str, bytes] = {
    "kick_four_on_floor": build_kick_four_on_floor_mid(),
    "kick_four_on_floor_8bar": build_kick_four_on_floor_8bar_mid(),
    "hats_eighths_drive": build_hats_eighths_drive_mid(),
    "hats_eighths_drive_8bar": build_hats_eighths_drive_8bar_mid(),
    "snare_backbeat_44": build_snare_backbeat_44_mid(),
    "snare_backbeat_44_8bar": build_snare_backbeat_44_8bar_mid(),
    "drums_all_in_one_gm_8bar": build_drums_all_in_one_gm_8bar_mid(),
    "bass_house_root_move": build_bass_house_root_move_mid(),
    "bass_progression_8bar": build_bass_progression_8bar_mid(),
    "chords_min_stab_13": build_chords_min_stab_13_mid(),
    "chords_cycle_8bar": build_chords_cycle_8bar_mid(),
    "lead_eighths_hook": build_lead_eighths_hook_mid(),
    "lead_arc_8bar": build_lead_arc_8bar_mid(),
    "euclid_kick_5_16": build_euclid_kick_5_16_mid(),
    "euclid_kick_5_16_8bar": build_euclid_kick_5_16_8bar_mid(),
    "euclid_hat_7_16": build_euclid_hat_7_16_mid(),
    "euclid_hat_7_16_8bar": build_euclid_hat_7_16_8bar_mid(),
    "euclid_snare_3_8": build_euclid_snare_3_8_mid(),
    "euclid_clap_5_12": build_euclid_clap_5_12_mid(),
    "fugue_violin_subject_2bar": build_fugue_violin_subject_2bar_mid(),
    "fugue_violin_subject_8bar": build_fugue_violin_subject_8bar_mid(),
    "fugue_piano_answer_2bar": build_fugue_piano_answer_2bar_mid(),
    "fugue_piano_answer_8bar": build_fugue_piano_answer_8bar_mid(),
    "fugue_organ_pedal_2bar": build_fugue_organ_pedal_2bar_mid(),
    "fugue_organ_pedal_8bar": build_fugue_organ_pedal_8bar_mid(),
    "counterpoint_alto_1bar": build_counterpoint_alto_1bar_mid(),
    "counterpoint_alto_8bar": build_counterpoint_alto_8bar_mid(),
    "counterpoint_tenor_1bar": build_counterpoint_tenor_1bar_mid(),
    "counterpoint_tenor_8bar": build_counterpoint_tenor_8bar_mid(),
    "piano_alberti_dm_1bar": build_piano_alberti_dm_1bar_mid(),
    "piano_alberti_dm_8bar": build_piano_alberti_dm_8bar_mid(),
    "organ_plenum_dm_1bar": build_organ_plenum_dm_1bar_mid(),
    "organ_plenum_dm_8bar": build_organ_plenum_dm_8bar_mid(),
    "violin_ornament_turn_1bar": build_violin_ornament_turn_1bar_mid(),
    "violin_ornament_turn_8bar": build_violin_ornament_turn_8bar_mid(),
    "pad_evolution_8bar": build_pad_evolution_8bar_mid(),
}

SEED_PATTERN_NAMES: Final[tuple[str, ...]] = tuple(sorted(_BUILDERS.keys()))

_BAR_VARIANTS: dict[str, str] = {
    "kick_four_on_floor": "kick_four_on_floor_8bar",
    "hats_eighths_drive": "hats_eighths_drive_8bar",
    "snare_backbeat_44": "snare_backbeat_44_8bar",
    "bass_house_root_move": "bass_progression_8bar",
    "chords_min_stab_13": "chords_cycle_8bar",
    "lead_eighths_hook": "lead_arc_8bar",
    "euclid_kick_5_16": "euclid_kick_5_16_8bar",
    "euclid_hat_7_16": "euclid_hat_7_16_8bar",
    "fugue_violin_subject_2bar": "fugue_violin_subject_8bar",
    "fugue_piano_answer_2bar": "fugue_piano_answer_8bar",
    "fugue_organ_pedal_2bar": "fugue_organ_pedal_8bar",
    "counterpoint_alto_1bar": "counterpoint_alto_8bar",
    "counterpoint_tenor_1bar": "counterpoint_tenor_8bar",
    "piano_alberti_dm_1bar": "piano_alberti_dm_8bar",
    "organ_plenum_dm_1bar": "organ_plenum_dm_8bar",
    "violin_ornament_turn_1bar": "violin_ornament_turn_8bar",
}


def resolve_seed_pattern(pattern: str, bars: int) -> str:
    if bars not in (1, 8):
        raise ValueError("bars must be 1 or 8")
    if bars == 1:
        return pattern
    if pattern.endswith("_8bar") or pattern == "drums_all_in_one_gm_8bar":
        return pattern
    if pattern in _BAR_VARIANTS:
        return _BAR_VARIANTS[pattern]
    if f"{pattern}_8bar" in _BUILDERS:
        return f"{pattern}_8bar"
    raise ValueError(
        f"No 8-bar mapping for {pattern!r}; try drums_all_in_one_gm_8bar, "
        f"pad_evolution_8bar, or a pattern with an _8bar variant"
    )


def seed_midi_cache_dir() -> Path:
    base = Path.home() / ".cache" / _SEED_SUBDIR
    base.mkdir(parents=True, exist_ok=True)
    return base


def write_seed_midi_file(pattern: str, *, bars: int = 1) -> Path:
    """Write seed MIDI; bars=8 selects longer companion pattern when available."""
    name = resolve_seed_pattern(pattern, bars)
    if name not in _BUILDERS:
        allowed = ", ".join(SEED_PATTERN_NAMES)
        raise ValueError(f"Unknown seed pattern: {name!r} (try one of: {allowed})")
    path = seed_midi_cache_dir() / f"seed_{name}.mid"
    path.write_bytes(_BUILDERS[name])
    return path.resolve()
