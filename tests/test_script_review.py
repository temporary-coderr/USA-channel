import tempfile
import unittest
from pathlib import Path

from script_review import review_script, write_review


class ScriptReviewTests(unittest.TestCase):
    def test_fallback_flags_research_claims_for_human_verification(self):
        report = review_script("In 2015, researchers found a change in oxytocin. This may matter.")
        self.assertTrue(report["claims_to_verify"])
        self.assertIn("check", report["claims_to_verify"][0])
        self.assertIn("does not guarantee rankings", report["seo_note"])

    def test_review_pack_does_not_modify_the_source_script(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "script.txt"
            source.write_text("A short psychology story. Here is what it means.", encoding="utf-8")
            before = source.read_text(encoding="utf-8")
            write_review(source, root / "review")
            self.assertEqual(source.read_text(encoding="utf-8"), before)
            self.assertTrue((root / "review" / "content_review.json").exists())
            self.assertTrue((root / "review" / "content_review.md").exists())


if __name__ == "__main__":
    unittest.main()
