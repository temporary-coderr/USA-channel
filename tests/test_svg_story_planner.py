import os
import unittest
from unittest.mock import patch

from svg_story_planner import plan_story, _validate_scene


class StoryPlannerTests(unittest.TestCase):
    def test_missing_key_uses_safe_rule_fallback(self):
        beats = [{"narration": "A dog walks beside its owner."}]
        with patch.dict(os.environ, {"GROQ_API_KEY": ""}):
            scenes, report = plan_story(beats)
        self.assertEqual(report["provider"], "rules_fallback")
        self.assertEqual(scenes[0]["subject"], "dog")

    def test_ai_scene_values_are_validated_against_svg_capabilities(self):
        beat = {"narration": "She feels shocked when the phone rings."}
        raw = {
            "subject": "phone", "action": "shocked", "emotion": "shocked",
            "environment": "bedroom", "props": ["phone", "spaceship"],
            "character": "girl", "layout": "close_up",
        }
        scene = _validate_scene(raw, beat, 1)
        self.assertEqual(scene["subject"], "phone")
        self.assertEqual(scene["emotion"], "shocked")
        self.assertEqual(scene["props"], ["phone"])
        self.assertEqual(scene["layout"], "close_up")

    def test_groq_response_plans_each_beat(self):
        beats = [
            {"narration": "A dog waits for its owner."},
            {"narration": "The owner feels happy."},
        ]
        response = {
            "choices": [{
                "message": {
                    "content": (
                        '{"scenes":['
                        '{"beat_index":1,"subject":"dog","action":"sitting","emotion":"neutral","environment":"park","props":["dog"],"character":"boy","layout":"left_focus"},'
                        '{"beat_index":2,"subject":"human","action":"happy","emotion":"happy","environment":"park","props":[],"character":"girl","layout":"right_focus"}'
                        ']}'
                    )
                }
            }]
        }
        class FakeResponse:
            def raise_for_status(self):
                return None
            def json(self):
                return response

        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            with patch("svg_story_planner.requests.post", return_value=FakeResponse()) as post:
                scenes, report = plan_story(beats)
        self.assertEqual(report["provider"], "groq")
        self.assertEqual(report["planned_scene_count"], 2)
        self.assertEqual(scenes[0]["subject"], "dog")
        self.assertEqual(scenes[1]["emotion"], "happy")
        self.assertNotEqual(scenes[0]["layout"], scenes[1]["layout"])
        self.assertEqual(post.call_count, 1)


if __name__ == "__main__":
    unittest.main()
