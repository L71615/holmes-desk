import unittest

from judgedee.identity import Account, Cluster
from judgedee.persona import build_persona
from judgedee.privacy import mask_domain, mask_email, mask_handle, mask_token, redact_persona


def sample_accounts() -> list[Account]:
    return [
        Account(
            username="L71615",
            site="GitHub",
            url="https://github.com/L71615",
            display_name="Alex",
            bio="mail me at alex.zhang@example.com, telegram @alexzhang, site https://alexzhang.dev",
            links=["https://alexzhang.dev"],
            ok=True,
        ),
        Account(
            username="L71615",
            site="Reddit",
            url="https://www.reddit.com/user/L71615",
            display_name="Alex",
            bio="a.z@example.org",
            links=[],
            ok=True,
        ),
    ]


class PrivacyTest(unittest.TestCase):
    def test_mask_email_keeps_first_chars_and_domain(self) -> None:
        self.assertEqual(mask_email("alex.zhang@example.com"), "al***@ex***.com")
        self.assertEqual(mask_email("a@b.cn"), "a***@b***.cn")

    def test_mask_email_keeps_public_providers(self) -> None:
        self.assertEqual(mask_email("alex.zhang@gmail.com"), "al***@gmail.com")

    def test_mask_handle_keeps_kind(self) -> None:
        self.assertEqual(mask_handle("Telegram: alexzhang"), "Telegram: al***")

    def test_mask_domain_keeps_tld(self) -> None:
        self.assertEqual(mask_domain("alexzhang.dev"), "al***.dev")

    def test_mask_token_short_values(self) -> None:
        self.assertEqual(mask_token("ab"), "a***")
        self.assertEqual(mask_token(""), "")

    def test_redact_persona_hides_contact_but_keeps_counts(self) -> None:
        accounts = sample_accounts()
        clusters = [Cluster(label="A", accounts=list(accounts), score=0.9, evidence=[])]
        persona = build_persona(accounts, clusters, [])
        redacted = redact_persona(persona)

        self.assertEqual(redacted["account_count"], persona["account_count"])
        self.assertEqual(redacted["cluster_count"], persona["cluster_count"])
        self.assertEqual(redacted["confidence"], persona["confidence"])
        self.assertTrue(redacted["redacted"])

        emails = dict(redacted["fields"]["emails"])
        self.assertTrue(emails)
        for value in emails:
            self.assertIn("***", value)
            self.assertNotIn("alex.zhang@", value)

        domains = dict(redacted["fields"]["domains"])
        for value in domains:
            self.assertNotIn("alexzhang", value)

        self.assertNotIn("example.com", redacted["summary"])
        self.assertIn("***", redacted["summary"])

    def test_redact_does_not_mutate_source(self) -> None:
        accounts = sample_accounts()
        clusters = [Cluster(label="A", accounts=list(accounts), score=0.9, evidence=[])]
        persona = build_persona(accounts, clusters, [])
        before = list(persona["fields"]["emails"])
        redact_persona(persona)
        self.assertEqual(persona["fields"]["emails"], before)
        self.assertNotIn("redacted", persona)


if __name__ == "__main__":
    unittest.main()
