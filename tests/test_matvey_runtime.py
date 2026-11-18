import os
import inspect
import tempfile
import unittest

import main


class MatveyRuntimeTests(unittest.TestCase):
    def test_openai_is_disabled_by_default(self):
        # A configured secret alone must not activate paid API calls.
        self.assertFalse(main.MATVEY_OPENAI_ENABLED)
        self.assertEqual(main.OPENAI_API_KEY, "")
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


    def test_owner_motivation_is_detected_in_assistant_history(self):
        self.assertTrue(main.owner_motivation_was_sent([
            {"role": "assistant", "content": "Чем быстрее пришлёте фото, тем быстрее команда сможет представить объект заинтересованным клиентам."}
        ]))
        self.assertFalse(main.owner_motivation_was_sent([
            {"role": "user", "content": "Чем быстрее пришлёте фото."},
            {"role": "assistant", "content": "Спасибо, номер получил. Жду фотографии."}
        ]))

    def test_repeated_owner_motivation_is_suppressed_deterministically(self):
        repeated = (
            "Спасибо! У нас уже есть заявки от потенциальных арендаторов по вашему району. "
            "Пришлите фотографии как можно скорее. Чем быстрее мы получим материалы, "
            "тем быстрее представим объект заинтересованным клиентам."
        )
        suppressed = main.suppress_repeated_owner_motivation(repeated, True)
        self.assertEqual(
            suppressed,
            "Хорошо, понял. Буду ждать фотографии и дополнительные параметры, когда вам будет удобно."
        )
        self.assertEqual(main.suppress_repeated_owner_motivation(repeated, False), repeated)
        ordinary_answer = "Спасибо, номер получил. Завтра после 15:00 удобно."
        self.assertEqual(
            main.suppress_repeated_owner_motivation(ordinary_answer, True),
            ordinary_answer
        )

    def test_owner_motivation_flag_persists_on_property_card(self):
        now = "2026-11-18T08:40:00+00:00"
        with __import__("sqlite3").connect(main.MATVEY_DB_PATH) as conn:
            conn.execute(
                "INSERT INTO owner_properties (chat_id, created_at, updated_at) VALUES (?,?,?)",
                ("owner-persistent-motivation", now, now)
            )
        main.mark_owner_motivation_sent("owner-persistent-motivation")
        self.assertTrue(
            main.owner_motivation_was_sent([], "owner-persistent-motivation")
        )

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
        self.assertIn("photo_ack_sent_at", columns)

    def test_multiple_photo_messages_accumulate_and_acknowledge_only_once(self):
        import json
        import sqlite3
        now = "2026-11-18T10:00:00+00:00"
        with sqlite3.connect(main.MATVEY_DB_PATH) as conn:
            conn.execute(
                """INSERT INTO owner_properties (
                    chat_id, deal_type, property_category, community, price,
                    photo_file_ids, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?)""",
                ("photo-batch-owner", "rent", "apartment", "Dubai Marina",
                 "95000", "[]", now, now)
            )
            conn.commit()

        first_ack = main.store_owner_photos("photo-batch-owner", ["photo-1", "photo-2"])
        second_ack = main.store_owner_photos("photo-batch-owner", ["photo-3"])
        third_ack = main.store_owner_photos("photo-batch-owner", ["photo-4", "photo-5"])

        self.assertTrue(first_ack)
        self.assertFalse(second_ack)
        self.assertFalse(third_ack)
        with sqlite3.connect(main.MATVEY_DB_PATH) as conn:
            row = conn.execute(
                "SELECT photo_file_ids, photo_ack_sent_at FROM owner_properties "
                "WHERE chat_id='photo-batch-owner'"
            ).fetchone()
        self.assertEqual(json.loads(row[0]), ["photo-1", "photo-2", "photo-3", "photo-4", "photo-5"])
        self.assertTrue(row[1])

    def test_photo_updates_do_not_trigger_voice_replies(self):
        import inspect
        source = inspect.getsource(main.telegram)
        self.assertIn("if answer and not message.get(\"photo\"):", source)
        self.assertIn("if message.get(\"photo\"):\n                answer = None", source)

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



    def _insert_owner_listing_for_delivery_test(self, chat_id, deal_type):
        import sqlite3
        now = "2026-11-18T10:00:00+00:00"
        with sqlite3.connect(main.MATVEY_DB_PATH) as conn:
            conn.execute(
                """INSERT INTO owner_properties (
                    chat_id, deal_type, property_category, community, price, currency,
                    lease_term, payment_terms, deposit, contact_phone, photo_file_ids,
                    created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (chat_id, deal_type, "apartment", "Dubai Marina", "95000", "AED",
                 None, None, None, None, "[]", now, now)
            )
            conn.commit()

    def test_owner_rent_and_sale_leads_deliver_without_irrelevant_fields(self):
        original_api = main.TELEGRAM_API
        original_admins = main.ADMIN_TELEGRAM_IDS
        original_send = main.telegram_send
        sent = []
        try:
            main.TELEGRAM_API = "configured"
            main.ADMIN_TELEGRAM_IDS = {"101", "202"}
            main.telegram_send = lambda chat_id, text: sent.append((str(chat_id), text))
            self._insert_owner_listing_for_delivery_test("rent-owner", "rent")
            self._insert_owner_listing_for_delivery_test("sale-owner", "sale")
            main.process_owner_listing_actions("rent-owner")
            main.process_owner_listing_actions("sale-owner")
            self.assertEqual({item[0] for item in sent}, {"101", "202"})
            import sqlite3
            with sqlite3.connect(main.MATVEY_DB_PATH) as conn:
                rows = conn.execute(
                    "SELECT chat_id, lead_notification_status, lead_notified_at FROM owner_properties "
                    "WHERE chat_id IN ('rent-owner','sale-owner')"
                ).fetchall()
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(row[1] == "sent" and row[2] for row in rows))
        finally:
            main.TELEGRAM_API = original_api
            main.ADMIN_TELEGRAM_IDS = original_admins
            main.telegram_send = original_send

    def test_owner_lead_retry_sends_only_to_admins_not_yet_notified(self):
        original_api = main.TELEGRAM_API
        original_admins = main.ADMIN_TELEGRAM_IDS
        original_send = main.telegram_send
        sent = []
        fail_second = {"enabled": True}
        def fake_send(chat_id, text):
            sent.append(str(chat_id))
            if str(chat_id) == "202" and fail_second["enabled"]:
                raise RuntimeError("temporary Telegram failure")
        try:
            main.TELEGRAM_API = "configured"
            main.ADMIN_TELEGRAM_IDS = {"101", "202"}
            main.telegram_send = fake_send
            self._insert_owner_listing_for_delivery_test("retry-owner", "sale")
            main.process_owner_listing_actions("retry-owner")
            import sqlite3, json
            with sqlite3.connect(main.MATVEY_DB_PATH) as conn:
                row = conn.execute(
                    "SELECT lead_notification_status, lead_notified_admin_ids, lead_notified_at "
                    "FROM owner_properties WHERE chat_id='retry-owner'"
                ).fetchone()
            self.assertEqual(row[0], "pending")
            self.assertEqual(json.loads(row[1]), ["101"])
            self.assertIsNone(row[2])
            fail_second["enabled"] = False
            main.process_owner_listing_actions("retry-owner")
            with sqlite3.connect(main.MATVEY_DB_PATH) as conn:
                row = conn.execute(
                    "SELECT lead_notification_status, lead_notified_admin_ids, lead_notified_at "
                    "FROM owner_properties WHERE chat_id='retry-owner'"
                ).fetchone()
            self.assertEqual(row[0], "sent")
            self.assertEqual(json.loads(row[1]), ["101", "202"])
            self.assertIsNotNone(row[2])
            self.assertEqual(sent.count("101"), 1)
            self.assertEqual(sent.count("202"), 2)
        finally:
            main.TELEGRAM_API = original_api
            main.ADMIN_TELEGRAM_IDS = original_admins
            main.telegram_send = original_send

    def test_photo_notification_retries_after_lead_was_already_delivered(self):
        import sqlite3
        import json
        original_api = main.TELEGRAM_API
        original_admins = main.ADMIN_TELEGRAM_IDS
        original_send = main.telegram_send
        sent = []
        now = "2026-11-18T10:00:00+00:00"
        try:
            main.TELEGRAM_API = "configured"
            main.ADMIN_TELEGRAM_IDS = {"101", "202"}
            main.telegram_send = lambda chat_id, text: sent.append(str(chat_id))
            with sqlite3.connect(main.MATVEY_DB_PATH) as conn:
                conn.execute(
                    """INSERT INTO owner_properties (
                        chat_id, deal_type, property_category, community, price,
                        photo_file_ids, lead_notification_status, lead_notified_at,
                        lead_notified_admin_ids, photo_notified_admin_ids,
                        created_at, updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    ("photo-retry-owner", "rent", "apartment", "Dubai Marina",
                     "95000", '["telegram-photo-id"]', "sent", now,
                     '["101","202"]', '["101"]', now, now)
                )
                conn.commit()
            main.retry_pending_owner_photo_notifications()
            self.assertEqual(sent, ["202"])
            with sqlite3.connect(main.MATVEY_DB_PATH) as conn:
                row = conn.execute(
                    "SELECT photo_notified_admin_ids, photos_notification_sent_at "
                    "FROM owner_properties WHERE chat_id='photo-retry-owner'"
                ).fetchone()
            self.assertEqual(json.loads(row[0]), ["101", "202"])
            self.assertIsNotNone(row[1])
        finally:
            main.TELEGRAM_API = original_api
            main.ADMIN_TELEGRAM_IDS = original_admins
            main.telegram_send = original_send

    def test_stale_photo_followup_claim_is_recovered(self):
        original_api = main.TELEGRAM_API
        original_send = main.telegram_send
        sent = []
        try:
            main.TELEGRAM_API = "configured"
            main.telegram_send = lambda chat_id, text: sent.append((str(chat_id), text))
            import sqlite3
            with sqlite3.connect(main.MATVEY_DB_PATH) as conn:
                conn.execute(
                    """INSERT INTO owner_properties (
                        chat_id, photo_file_ids, photo_followup_1_due,
                        photo_followup_1_sent_at, photo_followup_1_claimed_at,
                        created_at, updated_at
                    ) VALUES (?,?,?,?,?,?,?)""",
                    ("photo-owner", "[]", "2000-01-01T00:00:00+00:00",
                     "sending", "2000-01-01T00:00:00+00:00",
                     "2000-01-01T00:00:00+00:00", "2000-01-01T00:00:00+00:00")
                )
                conn.commit()
            main.process_due_photo_followups()
            self.assertEqual(len(sent), 1)
            self.assertIn("Наш клиент просит фотографии", sent[0][1])
            with sqlite3.connect(main.MATVEY_DB_PATH) as conn:
                row = conn.execute(
                    "SELECT photo_followup_1_sent_at, photo_followup_1_claimed_at, "
                    "photo_followup_2_due FROM owner_properties WHERE chat_id='photo-owner'"
                ).fetchone()
            self.assertNotEqual(row[0], "sending")
            self.assertIsNone(row[1])
            self.assertIsNotNone(row[2])
        finally:
            main.TELEGRAM_API = original_api
            main.telegram_send = original_send


    def test_dubai_real_estate_expert_knowledge_is_injected(self):
        knowledge = main.DUBAI_REAL_ESTATE_EXPERT_INSTRUCTIONS
        for required in (
            "Form A", "Form B", "Form F", "Ejari", "Oqood", "Title Deed",
            "Dubai Land Department", "RERA", "Law No. 26 of 2007",
            "Law No. 33 of 2008", "Decree No. 43 of 2013",
            "gross yield", "net operating yield", "Mollak",
            "Rental Disputes Center", "коммерческая недвижимость", "escrow"
        ):
            with self.subTest(required=required):
                self.assertIn(required.lower(), knowledge.lower())

    def test_matvey_defaults_to_current_gpt_consultant_model(self):
        self.assertEqual(main.MATVEY_DEFAULT_MODEL, "gpt-6.2-astra")

    def test_expert_instructions_require_current_sources_and_no_fake_integrations(self):
        knowledge = main.DUBAI_REAL_ESTATE_EXPERT_INSTRUCTIONS.lower()
        self.assertIn("дату проверки", knowledge)
        self.assertIn("не заявляй, что у матвея есть api", knowledge)
        self.assertIn("не выдавай", knowledge)
        self.assertIn("официальн", knowledge)

    def test_form_a_b_f_definitions_are_not_confused(self):
        knowledge = main.DUBAI_REAL_ESTATE_EXPERT_INSTRUCTIONS.lower()
        self.assertIn("form a — брокерское соглашение собственника", knowledge)
        self.assertIn("form b — соглашение покупателя", knowledge)
        self.assertIn("form f — унифицированный договор купли-продажи", knowledge)


    def test_buyer_qualification_guidance_is_injected(self):
        guidance = main.BUYER_CLIENT_GUIDANCE.lower()
        for phrase in ("один следующий", "бюджет", "ипотека", "для инвестора", "не принимай цену примера",
                       "режим руководителя", "crm", "финансовые расчёты"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, guidance)

    def test_buyer_crm_card_and_admin_notification_path_exists(self):
        self.assertTrue(callable(main.save_buyer_lead_card))
        source = inspect.getsource(main.save_buyer_lead_card).lower()
        for phrase in ("history_json", "buyer_profile", "admin_notified_fingerprint",
                       "telegram_send", "consent_status", "budget_max_aed"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, source)

if __name__ == "__main__":
    unittest.main()
