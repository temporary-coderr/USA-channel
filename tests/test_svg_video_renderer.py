import tempfile
import unittest
import wave
from pathlib import Path

from svg_animation_engine import render_scene_svg
from svg_video_renderer import build_sound_events, write_sfx_track


class SVGVideoRendererTests(unittest.TestCase):
    def test_camera_and_character_change_over_animation_phase(self):
        narration = "A person decides whether to answer a phone notification."
        first = render_scene_svg(narration, 3, 960, 540, phase=0.0)
        moving = render_scene_svg(narration, 3, 960, 540, phase=0.5)
        self.assertNotEqual(first, moving)
        self.assertIn("rotate(", moving)

    def test_sound_events_follow_scene_timeline(self):
        beats = [
            {"duration_seconds": 2.0, "action": "thinking"},
            {"duration_seconds": 3.0, "action": "surprised"},
        ]
        events = build_sound_events(beats, transition_seconds=0.25)
        self.assertEqual(events[0]["kind"], "logo")
        self.assertTrue(any(e["kind"] == "soft_whoosh" and e["time"] == 2.25 for e in events))
        self.assertTrue(any(e["kind"] == "soft_impact" for e in events))

    def test_sfx_track_is_valid_pcm_wav(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "effects.wav"
            write_sfx_track(0.5, [{"time": 0.05, "kind": "ui_click", "gain": 0.2}], path)
            with wave.open(str(path), "rb") as wav:
                self.assertEqual(wav.getframerate(), 24000)
                self.assertEqual(wav.getnchannels(), 1)
                self.assertEqual(wav.getsampwidth(), 2)
                self.assertGreater(wav.getnframes(), 1000)


if __name__ == "__main__":
    unittest.main()
