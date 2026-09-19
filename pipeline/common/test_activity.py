import unittest

from .activity import classify_activities


class ActivityClassificationTests(unittest.TestCase):
    def test_known_words_and_monthly_codes_are_stable(self):
        self.assertEqual(
            classify_activities(("Slaughterhouse", "Cutting plant", "Meat products", "Cold Store")),
            ("slaughter", "cutting", "processing", "logistics_and_storage"),
        )
        self.assertEqual(classify_activities(("CP", "SH", "CS")), ("cutting", "slaughter", "logistics_and_storage"))

    def test_unknown_activity_is_not_guessed(self):
        self.assertEqual(classify_activities(("rendering", "other")), ())


if __name__ == "__main__":
    unittest.main()
