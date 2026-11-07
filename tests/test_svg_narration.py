import unittest

from svg_narration import _ass_time, _caption_text


class SVGNarrationTests(unittest.TestCase):
    def test_ass_timestamp_format(self):
        self.assertEqual(_ass_time(65.27), "0:01:05.27")

    def test_caption_wraps_to_two_lines_and_preserves_highlight_tags(self):
        phrase = r"Look into your {\\c&H0054D4C8&}dog's{\\c&H00FFFFFF&} eyes and notice the bond"
        result = _caption_text(phrase, 24)
        self.assertIn(r"\\N", result)
        self.assertEqual(len(result.split(r"\\N")), 2)
        self.assertIn(r"{\\c&H0054D4C8&}", result)

    def test_caption_rejects_unreasonably_long_phrase(self):
        with self.assertRaises(RuntimeError):
            _caption_text("one two three four five six seven eight nine ten eleven twelve", 8)


if __name__ == "__main__":
    unittest.main()
