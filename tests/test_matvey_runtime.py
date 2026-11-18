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

    def test_child_agent_profiles_are_limited_to_fifty(self):
        for index in range(50):
            main.register_child_agent(f"Agent {index} | Specialist {index} | auto")
        with self.assertRaises(ValueError):
            main.register_child_agent("Agent 51 | Another specialty | auto")

    def test_child_webhook_update_is_deduplicated_per_agent(self):
        self.assertTrue(main.claim_child_update("agent_a", 1001))
        self.assertFalse(main.claim_child_update("agent_a", 1001))
        self.assertTrue(main.claim_child_update("agent_b", 1001))

    def test_group_monitoring_requires_explicit_allow_list(self):
        old = os.environ.get("TELEGRAM_MONITORED_CHAT_IDS")
        os.environ["TELEGRAM_MONITORED_CHAT_IDS"] = "-100123,-100456"
        try:
            self.assertEqual(main.monitored_group_ids(), {"-100123", "-100456"})
        finally:
            if old is None:
                os.environ.pop("TELEGRAM_MONITORED_CHAT_IDS", None)
            else:
                os.environ["TELEGRAM_MONITORED_CHAT_IDS"] = old

    def test_group_message_url_uses_public_username_or_private_group_id(self):
        public = main.build_group_message_url({"username": "dubai_chat"}, {"message_id": 88})
        private = main.build_group_message_url({"id": -10012345}, {"message_id": 89})
        self.assertEqual(public, "https://t.me/dubai_chat/88")
        self.assertEqual(private, "https://t.me/c/12345/89")

    def test_group_lead_table_exists(self):
        with __import__("sqlite3").connect(main.MATVEY_DB_PATH) as conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn("group_property_leads", tables)

    def test_owner_intake_asks_area_price_before_photos_and_contact(self):
        instructions = main.SYSTEM_INSTRUCTIONS
        priority = instructions.index("ПРИОРИТЕТНЫЙ СЦЕНАРИЙ ДЛЯ СОБСТВЕННИКА")
        section = instructions[priority:priority + 2600]
        area = section.index("Уточни район")
        price = section.index("После получения района спроси желаемую цену")
        photos = section.index("ТОЛЬКО ПОСЛЕ ТОГО")
        contact = section.index("номер телефона")
        self.assertLess(area, price)
        self.assertLess(price, photos)
        self.assertLess(photos, contact)
        self.assertIn("удобное время для связи", section)
        self.assertNotIn("Не проси фото и контакт раньше уточнения района и цены", section)
        self.assertNotIn("Не спрашивай цену раньше просьбы о фото и контакте", instructions)


    def test_owner_property_context_includes_known_facts_and_forbids_reasking(self):
        with __import__("sqlite3").connect(main.MATVEY_DB_PATH) as conn:
            conn.execute(
                """INSERT INTO owner_properties (
                    chat_id, deal_type, property_category, bedrooms, area, community,
                    price, currency, furnishing, availability, lease_term, payment_terms,
                    deposit, contact_time, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                ("owner-chat", "rent", "apartment", 1, "Dubai Marina", "Dubai Marina",
                 "95000", "AED", "fully furnished", "available now", "12 months",
                 "4 cheques", "5% deposit", "tomorrow after 15:00", "now", "now")
            )
            conn.commit()
        context = main.get_owner_property_context("owner-chat")
        self.assertIn("Dubai Marina", context)
        self.assertIn("95000", context)
        self.assertIn("fully furnished", context)
        self.assertIn("12 months", context)
        self.assertIn("4 cheques", context)
        self.assertIn("tomorrow after 15:00", context)
        self.assertIn("НЕ спрашивай их повторно", context)

    def test_owner_listing_schema_has_delivery_and_photo_followup_tracking(self):
        import sqlite3
        with sqlite3.connect(main.MATVEY_DB_PATH) as conn:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(owner_properties)")}
        self.assertIn("lead_notification_status", columns)
        self.assertIn("lead_notified_at", columns)
        self.assertIn("photo_followup_1_due", columns)
        self.assertIn("photo_followup_1_sent_at", columns)
        self.assertIn("photo_followup_2_due", columns)
        self.assertIn("photo_followup_2_sent_at", columns)
        self.assertIn("photos_notification_sent_at", columns)

    def test_owner_admin_summary_contains_listing_and_missing_photos_status(self):
        import sqlite3
        now = "2026-11-18T10:00:00+00:00"
        with sqlite3.connect(main.MATVEY_DB_PATH) as conn:
            conn.execute(
                """INSERT INTO owner_properties (
                    chat_id, deal_type, property_category, bedrooms, community,
                    price, currency, furnishing, lease_term, payment_terms, deposit,
                    contact_phone, whatsapp_allowed, call_allowed, contact_time,
                    photo_file_ids, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                ("lead-chat", "rent", "apartment", 1, "Dubai Marina", "95000", "AED",
                 "fully furnished", "12 months", "4 cheques", "5%", "+971501234567",
                 "yes", "yes", "tomorrow after 15:00", "[]", now, now)
            )
            conn.commit()
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM owner_properties WHERE chat_id='lead-chat'").fetchone()
        summary = main._owner_listing_admin_text(row)
        self.assertIn("Dubai Marina", summary)
        self.assertIn("95000 AED", summary)
        self.assertIn("4 cheques", summary)
        self.assertIn("Фотографии: ожидаются", summary)

    def test_multilingual_voice_and_dialogue_rules_are_present(self):
        self.assertIn("УНИВЕРСАЛЬНЫЙ ЯЗЫКОВОЙ РЕЖИМ", main.SYSTEM_INSTRUCTIONS)
        self.assertIn("ЕСТЕСТВЕННЫЙ ЧЕЛОВЕЧЕСКИЙ ДИАЛОГ", main.SYSTEM_INSTRUCTIONS)
        self.assertIn("ПОИСК КОНКРЕТНЫХ ОБЪЯВЛЕНИЙ", main.SYSTEM_INSTRUCTIONS)


if __name__ == "__main__":
    unittest.main()
