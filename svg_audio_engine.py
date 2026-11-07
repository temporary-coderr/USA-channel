from __future__ import annotations

"""Original WISE-LAB audio: restrained SFX plus a continuous ambient music bed.

All sounds are synthesized locally; no external recordings or copyrighted tracks.
"""

from array import array
import math
import wave
from pathlib import Path

SAMPLE_RATE = 24000
SFX_DURATIONS = {
    "ui_click": 0.11,
    "soft_tick": 0.16,
    "soft_step": 0.22,
    "soft_impact": 0.42,
    "soft_whoosh": 0.48,
    "logo": 1.55,
}

SFX_FOR_ACTION = {
    "thinking": "soft_tick",
    "looking": "ui_click",
    "talking": "ui_click",
    "choosing": "ui_click",
    "walking": "soft_step",
    "turn_away": "soft_whoosh",
    "surprised": "soft_impact",
    "explaining": "soft_tick",
}


def build_sound_events(beats: list[dict], transition_seconds: float = 0.22) -> list[dict]:
    """Place deliberate effects at meaningful moments, not on every cut."""
    events = [{"time": 0.04, "kind": "logo", "gain": 0.78}]
    cursor = 0.0
    previous_subject = None
    for index, beat in enumerate(beats):
        subject = beat.get("subject")
        action = beat.get("action", "explaining")
        if index:
            cursor += transition_seconds
            # Avoid a repetitive whoosh on every cut. Mark every third cut and
            # genuine subject changes with a short, soft transition accent.
            if index % 3 == 0 or (subject and subject != previous_subject):
                events.append({"time": cursor, "kind": "soft_whoosh", "gain": 0.34})
        kind = SFX_FOR_ACTION.get(action, "soft_tick")
        meaningful_action = action in {"walking", "turn_away", "surprised", "choosing"}
        if meaningful_action or index % 3 == 0:
            gain = {
                "ui_click": 0.48,
                "soft_tick": 0.34,
                "soft_step": 0.58,
                "soft_whoosh": 0.38,
                "soft_impact": 0.62,
            }.get(kind, 0.34)
            events.append({
                "time": cursor + min(0.18, float(beat["duration_seconds"]) * 0.16),
                "kind": kind,
                "gain": gain,
            })
        previous_subject = subject
        cursor += float(beat["duration_seconds"])
    return events


def _sfx_sample(kind: str, t: float, duration: float, seed: int) -> float:
    p = max(0.0, min(1.0, t / max(duration, 1e-6)))
    if kind == "ui_click":
        return (math.sin(2 * math.pi * (1480 - 520 * p) * t)
                + 0.22 * math.sin(2 * math.pi * 2220 * t)) * math.exp(-13 * p)
    if kind == "soft_tick":
        return (math.sin(2 * math.pi * 880 * t)
                + 0.30 * math.sin(2 * math.pi * 1760 * t)) * math.exp(-8 * p)
    if kind == "soft_step":
        body = math.sin(2 * math.pi * (92 - 30 * p) * t) * math.exp(-5.5 * p)
        texture = math.sin(2 * math.pi * 540 * t) * math.exp(-17 * p) * 0.16
        return body + texture
    if kind == "soft_impact":
        body = math.sin(2 * math.pi * (82 - 36 * p) * t) * math.exp(-4.5 * p)
        upper = math.sin(2 * math.pi * 164 * t) * math.exp(-7 * p) * 0.22
        return body + upper
    if kind == "soft_whoosh":
        envelope = math.sin(math.pi * p) ** 1.35
        sweep = math.sin(2 * math.pi * (170 + 480 * p) * t)
        shimmer = math.sin(2 * math.pi * (420 + seed % 170) * t) * 0.10
        return (sweep + shimmer) * envelope
    if kind == "logo":
        # Three-note WISE-LAB sonic mark with a soft, clean release.
        envelope = min(1.0, t / 0.06) * max(0.0, 1.0 - p) ** 1.35
        notes = (
            math.sin(2 * math.pi * 392.00 * t)
            + 0.72 * math.sin(2 * math.pi * 523.25 * t)
            + 0.52 * math.sin(2 * math.pi * 659.25 * t)
        )
        pulse = 0.82 + 0.18 * math.sin(2 * math.pi * 2.0 * t)
        return notes * envelope * pulse * 0.48
    return 0.0


def _write_mono_wav(path: Path, samples: array) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        block = 48000
        for start in range(0, len(samples), block):
            wav.writeframesraw(samples[start:start + block].tobytes())
        wav.writeframes(b"")


def _build_sfx(duration: float, events: list[dict]) -> array:
    count = max(1, int(math.ceil(duration * SAMPLE_RATE)))
    mixed = array("f", [0.0]) * count
    for event_index, event in enumerate(events):
        kind = event["kind"]
        start = max(0, int(float(event["time"]) * SAMPLE_RATE))
        length = int(SFX_DURATIONS.get(kind, 0.14) * SAMPLE_RATE)
        gain = float(event.get("gain", 0.35))
        end = min(count, start + length)
        for pos in range(start, end):
            t = (pos - start) / SAMPLE_RATE
            mixed[pos] += _sfx_sample(kind, t, length / SAMPLE_RATE, event_index * 97) * gain
    return mixed


def _build_music(duration: float, seed: int = 0) -> array:
    """Generate a calm, original ambient bed with slow chord movement."""
    count = max(1, int(math.ceil(duration * SAMPLE_RATE)))
    music = array("f", [0.0]) * count
    chords = (
        (110.00, 164.81, 220.00, 329.63),
        (87.31, 130.81, 174.61, 261.63),
        (98.00, 146.83, 196.00, 293.66),
        (73.42, 110.00, 146.83, 220.00),
    )
    # Rotate the progression and vary its pace from the script fingerprint,
    # so different videos do not all receive an identical music bed.
    rotation = seed % len(chords)
    chords = chords[rotation:] + chords[:rotation]
    chord_seconds = (7.5, 8.0, 8.5)[(seed >> 3) % 3]
    pulse_rate = (0.13, 0.16, 0.19)[(seed >> 5) % 3]
    fade_seconds = min(1.8, max(0.35, duration * 0.08))
    for pos in range(count):
        t = pos / SAMPLE_RATE
        chord_index = int(t // chord_seconds) % len(chords)
        local = t % chord_seconds
        chord = chords[chord_index]
        fade_in = min(1.0, t / fade_seconds)
        fade_out = min(1.0, max(0.0, (duration - t) / fade_seconds))
        edge = min(fade_in, fade_out)
        # Gentle slow pulse keeps the bed alive without competing with speech.
        pulse = 0.90 + 0.10 * math.sin(2 * math.pi * pulse_rate * t)
        pad = (
            0.40 * math.sin(2 * math.pi * chord[0] * t)
            + 0.25 * math.sin(2 * math.pi * chord[1] * t)
            + 0.19 * math.sin(2 * math.pi * chord[2] * t)
            + 0.10 * math.sin(2 * math.pi * chord[3] * t)
        )
        # A quiet, bell-like accent every four seconds; not a repetitive beat.
        note_phase = (t % 4.0)
        pluck_env = math.exp(-2.8 * note_phase)
        pluck = 0.10 * math.sin(2 * math.pi * (chord[3] * 2) * note_phase) * pluck_env
        music[pos] = (pad * pulse * 0.13 + pluck * 0.07) * edge
    return music


def write_audio_tracks(duration: float, events: list[dict],
                       sfx_path: Path, mix_path: Path, music_seed: int = 0) -> dict:
    """Write separate SFX and mastered SFX+music mix WAV files."""
    sfx = _build_sfx(duration, events)
    music = _build_music(duration, music_seed)
    mixed = array("f", [0.0]) * len(sfx)
    peak = 0.0
    for index in range(len(sfx)):
        # The music bed is deliberately restrained; effects remain in front.
        value = sfx[index] + music[index]
        peak = max(peak, abs(value))
        mixed[index] = value
    # Gentle global headroom protection; no hard clipping.
    if peak > 0.92:
        scale = 0.92 / peak
        for index in range(len(mixed)):
            mixed[index] *= scale
    sfx_pcm = array("h", (int(max(-1.0, min(1.0, value)) * 32767) for value in sfx))
    mix_pcm = array("h", (int(max(-1.0, min(1.0, value)) * 32767) for value in mixed))
    _write_mono_wav(sfx_path, sfx_pcm)
    _write_mono_wav(mix_path, mix_pcm)
    return {
        "sample_rate": SAMPLE_RATE,
        "event_count": len(events),
        "event_types": sorted({event["kind"] for event in events}),
        "music_bed": "original_synthesized_ambient",
        "music_seed": int(music_seed),
        "peak_linear": round(min(peak, 0.92), 4),
    }
