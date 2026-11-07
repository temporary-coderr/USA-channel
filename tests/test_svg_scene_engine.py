import unittest
import xml.etree.ElementTree as ET

from svg_scene_engine import plan_scene, render_scene_svg


class SVGSceneEngineTests(unittest.TestCase):
    def test_script_selects_different_emotions_and_environments(self):
        sad = plan_scene("He felt sad and lonely in the rainy street.", 1)
        happy = plan_scene("She was happy while walking in the park.", 2)
        self.assertEqual(sad["emotion"], "sad")
        self.assertEqual(sad["environment"], "rainy_street")
        self.assertEqual(happy["emotion"], "happy")
        self.assertEqual(happy["environment"], "park")

    def test_dog_script_creates_dog_interaction_visual(self):
        brief = plan_scene("The dog waits beside its owner.", 4)
        svg = render_scene_svg("The dog waits beside its owner.", 4, 1280, 720, 0.5)
        self.assertEqual(brief["subject"], "dog")
        self.assertIn("<circle cx=\"78\"", svg)
        self.assertIn("park", brief["environment"])
        self.assertIn("scale(-1 1)", svg)

    def test_environment_background_contains_real_scene_layers(self):
        svg = render_scene_svg("A person relaxes in the park.", 8, 720, 1280)
        self.assertIn("linearGradient id=\"sceneSky\"", svg)
        self.assertIn("#70533E", svg)
        self.assertIn("#6F9479", svg)

    def test_dog_bond_scene_adds_a_visual_connection_cue(self):
        svg = render_scene_svg("The dog shares a loving gaze with its owner.", 9, 720, 1280)
        self.assertIn("#EF8175", svg)
        self.assertIn("scale(-1 1)", svg)

    def test_pose_and_expression_change_rendered_svg(self):
        sad = render_scene_svg("He feels sad and lonely.", 1, 1280, 720, 0.2)
        shocked = render_scene_svg("He is shocked by the unexpected sound.", 2, 1280, 720, 0.2)
        self.assertNotEqual(sad, shocked)
        self.assertIn("ellipse", shocked)

    def test_scenes_are_valid_svg_and_phase_animates_character(self):
        first = render_scene_svg("A person is walking through a doorway.", 3, 1280, 720, 0.0)
        moving = render_scene_svg("A person is walking through a doorway.", 3, 1280, 720, 0.8)
        ET.fromstring(first)
        self.assertNotEqual(first, moving)
        self.assertIn("translate(", moving)

    def test_composition_changes_between_beats(self):
        a = render_scene_svg("A person thinks about memory.", 1)
        b = render_scene_svg("A person thinks about memory.", 2)
        self.assertNotEqual(a, b)


if __name__ == "__main__":
    unittest.main()
