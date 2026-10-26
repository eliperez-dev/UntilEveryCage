import unittest

from pipeline.geocoding.german_streets import street_matches


class GermanStreetMatchTests(unittest.TestCase):
    def test_terminal_suffix_spellings_and_compound_spacing(self):
        for source, road in (
            ("Lindenstr. 12", "Lindenstraße"),
            ("Lindenstr 12", "Lindenstraße"),
            ("Lindenstraße 12", "Linden Strasse"),
            ("12 Lindenstrasse", "Linden Straße"),
            ("Linden Straße 12", "Lindenstr."),
        ):
            with self.subTest(source=source, road=road):
                self.assertTrue(street_matches(source, road, "12"))

    def test_house_number_and_suffix_are_exact(self):
        for source, number in (("Lindenstr. 12", "13"), ("Lindenstr. 12a", "12"),
                               ("Lindenstr. 12/1", "12-1"), ("Lindenstr. 12-1", "12/1")):
            with self.subTest(source=source, number=number):
                self.assertFalse(street_matches(source, "Lindenstraße", number))
        self.assertTrue(street_matches("Lindenstr. 12/1", "Lindenstraße", "12/1"))

    def test_different_stems_and_umlaut_distinctions_do_not_match(self):
        self.assertFalse(street_matches("Mühlenstraße 12", "Muhlenstraße", "12"))
        self.assertFalse(street_matches("Mühlenstraße 12", "Mühlenstrassex", "12"))
        self.assertFalse(street_matches("Mühlenstraße 12", "Mühlenweg", "12"))

    def test_umlaut_and_digraph_spellings_match_but_plain_vowels_do_not(self):
        for source, road in (("Mühlenstraße 12", "Muehlenstrasse"),
                             ("Kölnstraße 12", "Koelnstraße"),
                             ("Bärstraße 12", "Baerstr")):
            with self.subTest(source=source, road=road):
                self.assertTrue(street_matches(source, road, "12"))
        self.assertFalse(street_matches("Mühlenstraße 12", "Muhlenstrasse", "12"))
        self.assertFalse(street_matches("Kölnstraße 12", "Kolnstraße", "12"))

    def test_house_first_last_and_ambiguous_or_malformed_inputs(self):
        self.assertTrue(street_matches("12a Bahnhofstr.", "Bahnhofstraße", "12a"))
        self.assertFalse(street_matches("12 Bahnhofstr. 13", "Bahnhofstraße", "12"))
        for source, road, number in (("", "Roadstraße", "1"), (None, "Roadstraße", "1"),
                                     ("Roadstraße", "Roadstraße", "1"),
                                     ("Roadstraße 1 extra", "Roadstraße", "1"),
                                     ("Roadstraße 1", "", "1")):
            with self.subTest(source=source):
                self.assertFalse(street_matches(source, road, number))


if __name__ == "__main__":
    unittest.main()
