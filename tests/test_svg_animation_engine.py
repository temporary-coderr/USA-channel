import unittest
import xml.etree.ElementTree as ET

from svg_animation_engine import infer_subject, plan_visual_beats, render_scene_svg


class SVGEngineTests(unittest.TestCase):
    def test_script_words_are_preserved_in_order(self):
        script = "The spotlight effect changes what we notice. People often overestimate attention."
        beats = plan_visual_beats(script, target_wpm=140, target_seconds=3)
        self.assertEqual(" ".join(b["narration"] for b in beats).split(), script.split())
        self.assertGreaterEqual(len(beats), 2)

    def test_subject_selection_uses_script_context(self):
        self.assertEqual(infer_subject("A dog waits beside the front door."), "dog")
        self.assertEqual(infer_subject("Phone notifications interrupt attention."), "phone")
        self.assertEqual(infer_subject("Memory changes how we understand an experience."), "brain")

    def test_svg_is_valid_and_correctly_sized(self):
        svg = render_scene_svg("A dog waits for its owner.", 1, 1920, 1080)
        root = ET.fromstring(svg)
        self.assertEqual(root.attrib["width"], "1920")
        self.assertEqual(root.attrib["height"], "1080")
        self.assertIn("WISE LAB", svg)

    def test_new_beat_has_a_distinct_composition(self):
        first = render_scene_svg("A person thinks about a difficult decision.", 1)
        second = render_scene_svg("A person notices a phone notification.", 2)
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
