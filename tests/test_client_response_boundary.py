import unittest

import main


class ClientResponseBoundaryTests(unittest.TestCase):
    def test_russian_external_company_request_gets_directory_reply(self):
        self.assertEqual(
            main.enforce_client_response_boundary(
                "Подскажите контакты другой риелторской компании",
                "Обратитесь в Example Realty по email info@example.com",
            ),
            "Я такую информацию не предоставляю. Пожалуйста, воспользуйтесь справочником самостоятельно.",
        )

    def test_english_external_directory_request_gets_directory_reply(self):
        self.assertEqual(
            main.enforce_client_response_boundary(
                "Where can I find an agency contact?",
                "Try Example Realty.",
            ),
            "I don’t provide that information. Please consult a directory yourself.",
        )

    def test_all_urls_and_emails_are_removed(self):
        result = main.enforce_client_response_boundary(
            "I want to rent an apartment",
            "Please see https://example.com/listing and write to info@example.com.",
        )
        self.assertNotIn("https://", result)
        self.assertNotIn("example.com", result)
        self.assertNotIn("@", result)

    def test_uae_phone_numbers_are_removed(self):
        result = main.enforce_client_response_boundary(
            "I want to buy a villa",
            "Call our office at +971 50 123 4567.",
        )
        self.assertNotIn("+971", result)
        self.assertNotIn("123 4567", result)

    def test_portal_recommendation_is_rejected(self):
        result = main.enforce_client_response_boundary(
            "What areas do you cover?",
            "You can find listings on Property Finder.",
        )
        self.assertEqual(
            result,
            "Я такую информацию не предоставляю. Пожалуйста, воспользуйтесь справочником самостоятельно.",
        )

    def test_normal_intake_question_is_preserved(self):
        answer = "В каком районе вы рассматриваете квартиру?"
        self.assertEqual(
            main.enforce_client_response_boundary("Хочу снять квартиру", answer),
            answer,
        )


if __name__ == "__main__":
    unittest.main()
