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
        self.assertIn("linearGradient id=\"sky", svg)
        self.assertIn("#70533E", svg)
        self.assertIn("#6F9479", svg)

    def test_dog_bond_scene_adds_a_visual_connection_cue(self):
        svg = render_scene_svg("The dog shares a loving gaze with its owner.", 9, 720, 1280)
        self.assertIn("#EF8175", svg)
        self.assertIn("scale(-1 1)", svg)

    def test_seeded_backgrounds_have_multiple_distinct_compositions(self):
        park_a = render_scene_svg("A person relaxes in the park.", 1, 720, 1280)
        park_b = render_scene_svg("A person relaxes in the park.", 2, 720, 1280)
        self.assertNotEqual(park_a, park_b)
        bg_a = park_a.split("<g transform=", 1)[0]
        bg_b = park_b.split("<g transform=", 1)[0]
        self.assertNotEqual(bg_a, bg_b)

    def test_planner_recognizes_more_real_world_environments(self):
        self.assertEqual(plan_scene("A student studies in a classroom.", 1)["environment"], "classroom")
        self.assertEqual(plan_scene("They meet at a cafe for coffee.", 1)["environment"], "cafe")
        self.assertEqual(plan_scene("The commute through the city feels stressful.", 1)["environment"], "city")
        self.assertEqual(plan_scene("A family talks together at home.", 1)["environment"], "home")

    def test_mirror_and_eye_subjects_have_drawable_props(self):
        mirror = render_scene_svg("A person studies their reflection in a mirror.", 1)
        eye = render_scene_svg("The eye notices every movement.", 2)
        self.assertIn('rx="52"', mirror)
        self.assertIn("Q0 -90", eye)

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
