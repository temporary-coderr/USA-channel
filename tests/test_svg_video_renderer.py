import math
import tempfile
import unittest
import wave
from pathlib import Path

from svg_animation_engine import render_scene_svg
from svg_audio_engine import build_sound_events, write_audio_tracks


class SVGVideoRendererTests(unittest.TestCase):
    def test_camera_and_character_change_over_animation_phase(self):
        narration = "A person decides whether to answer a phone notification."
        first = render_scene_svg(narration, 3, 960, 540, phase=0.0)
        moving = render_scene_svg(narration, 3, 960, 540, phase=0.5)
        self.assertNotEqual(first, moving)
        self.assertIn("rotate(", moving)

    def test_sound_events_are_deliberate_not_a_whoosh_on_every_cut(self):
        beats = [
            {"duration_seconds": 2.0, "action": "thinking", "subject": "brain"},
            {"duration_seconds": 3.0, "action": "surprised", "subject": "heart"},
            {"duration_seconds": 2.0, "action": "explaining", "subject": "heart"},
            {"duration_seconds": 2.0, "action": "walking", "subject": "human"},
        ]
        events = build_sound_events(beats, transition_seconds=0.25)
        self.assertEqual(events[0]["kind"], "logo")
        self.assertTrue(any(e["kind"] == "soft_impact" for e in events))
        self.assertTrue(any(e["kind"] == "soft_step" for e in events))
        whooshes = [e for e in events if e["kind"] == "soft_whoosh"]
        self.assertLess(len(whooshes), len(beats))

    def test_audio_mix_has_continuous_music_and_valid_pcm(self):
        with tempfile.TemporaryDirectory() as temp:
            sfx_path = Path(temp) / "effects.wav"
            mix_path = Path(temp) / "mix.wav"
            report = write_audio_tracks(
                3.0,
                [{"time": 0.05, "kind": "logo", "gain": 0.78},
                 {"time": 1.2, "kind": "soft_impact", "gain": 0.62}],
                sfx_path,
                mix_path,
            )
            self.assertTrue(sfx_path.exists())
            self.assertTrue(mix_path.exists())
            self.assertEqual(report["music_bed"], "original_synthesized_ambient")
            with wave.open(str(mix_path), "rb") as wav:
                self.assertEqual(wav.getframerate(), 24000)
                self.assertEqual(wav.getnchannels(), 1)
                self.assertEqual(wav.getsampwidth(), 2)
                self.assertGreater(wav.getnframes(), 70000)
                samples = wav.readframes(wav.getnframes())
            values = [int.from_bytes(samples[i:i+2], "little", signed=True) for i in range(0, len(samples), 2)]
            # The ambient layer must remain audible between isolated effects.
            middle = values[24000:28800]
            rms = math.sqrt(sum(v*v for v in middle) / len(middle))
            self.assertGreater(rms, 100)


if __name__ == "__main__":
    unittest.main()
