import os
import tempfile
import unittest

import main


class MatveyRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        main.MATVEY_DB_PATH = os.path.join(self.temp_dir.name, "matvey_test.sqlite3")
        main._DB_PATH_CHECKED = True
        main.init_property_database()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_generic_portal_homepage_is_removed(self):
        answer = "Found homes: https://www.bayut.com/ and https://www.propertyfinder.ae/en/search"
        cleaned = main.remove_generic_portal_urls(answer)
        self.assertNotIn("bayut.com", cleaned)
        self.assertNotIn("propertyfinder.ae", cleaned)
        self.assertIn("отдельные объявления", cleaned)

    def test_generic_portal_markdown_link_keeps_label_without_url(self):
        answer = "Portal: [Bayut](https://www.bayut.com/)"
        cleaned = main.remove_generic_portal_urls(answer)
        self.assertIn("Bayut", cleaned)
        self.assertNotIn("https://www.bayut.com/", cleaned)
        self.assertNotIn("Bayut]()", cleaned)

    def test_individual_listing_url_is_preserved(self):
        url = "https://www.bayut.com/property/details-1234567.html"
        self.assertIn(url, main.remove_generic_portal_urls("Listing: " + url))

    def test_non_portal_direct_listing_is_preserved(self):
        url = "https://example-estate.com/listing/123456"
        self.assertIn(url, main.remove_generic_portal_urls(url))

    def test_child_agent_profile_and_training_notes_are_saved(self):
        agent = main.register_child_agent(
            "Leasing Specialist | Dubai residential rentals | auto | "
            "Collect only missing requirements and never repeat questions."
        )
        saved = main.get_child_agent(agent["agent_key"])
        self.assertEqual(saved["specialization"], "Dubai residential rentals")
        self.assertEqual(saved["language_policy"], "auto")
        self.assertIn("never repeat questions", saved["system_notes"])
        self.assertEqual(saved["status"], "draft_token_required")

    def test_child_training_appends_without_erasing_previous_rules(self):
        agent = main.register_child_agent("Sales Agent | Dubai sales | auto")
        key = agent["agent_key"]
        self.assertTrue(main.update_child_agent_notes(key, "Never invent prices."))
        self.assertTrue(main.update_child_agent_notes(key, "Always include direct listing URLs."))
        saved = main.get_child_agent(key)
        self.assertIn("Never invent prices.", saved["system_notes"])
        self.assertIn("Always include direct listing URLs.", saved["system_notes"])

    def test_child_webhook_update_is_deduplicated_per_agent(self):
        self.assertTrue(main.claim_child_update("agent_a", 1001))
        self.assertFalse(main.claim_child_update("agent_a", 1001))
        self.assertTrue(main.claim_child_update("agent_b", 1001))

    def test_multilingual_voice_and_dialogue_rules_are_present(self):
        self.assertIn("УНИВЕРСАЛЬНЫЙ ЯЗЫКОВОЙ РЕЖИМ", main.SYSTEM_INSTRUCTIONS)
        self.assertIn("ЕСТЕСТВЕННЫЙ ЧЕЛОВЕЧЕСКИЙ ДИАЛОГ", main.SYSTEM_INSTRUCTIONS)
        self.assertIn("ПОИСК КОНКРЕТНЫХ ОБЪЯВЛЕНИЙ", main.SYSTEM_INSTRUCTIONS)


if __name__ == "__main__":
    unittest.main()
