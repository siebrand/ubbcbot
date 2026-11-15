"""Tests for the public /privacy endpoint and the /privacy bot command."""

import os
from unittest.mock import Mock

from handlers.api import privacy as privacy_api
from handlers.customer.info_commands import InfoCommands


class TestPrivacyApi:
    def test_returns_rendered_html(self):
        resp = privacy_api.handler({}, None)
        assert resp["statusCode"] == 200
        assert resp["headers"]["Content-Type"] == "text/html; charset=utf-8"
        body = resp["body"]
        # Rendered HTML, not raw Markdown
        assert "<!DOCTYPE html>" in body
        assert "<h1>" in body and "<h2>" in body
        assert "<table>" in body and "<th>" in body
        assert "<strong>" in body
        # No leftover raw Markdown markers from the source document
        assert "| Gegeven |" not in body

    def test_includes_controller_identity(self):
        body = privacy_api.handler({}, None)["body"]
        assert "Kitano ICT" in body
        assert "30197597" in body  # KVK

    def test_deletion_matches_what_the_bot_does(self):
        # Line wrapping in the source must not matter, so compare on whitespace-normalised text
        body = " ".join(privacy_api.handler({}, None)["body"].split())
        # /delete_user wipes the customer record
        assert "klantrecord" in body
        assert "volledig gewist" in body
        # Deletion is postponed (not refused) while an order is open or a payment is due to us
        assert "een bestelling open" in body
        assert "nog een betaling aan ons doen" in body
        assert "We stellen de verwijdering dan uit" in body
        assert "binnen een maand" in body
        assert "tegoedsaldo" not in body

    def test_explains_how_to_exercise_the_right_to_be_forgotten(self):
        body = " ".join(privacy_api.handler({}, None)["body"].split())
        assert "neem contact op via het adres hierboven" in body
        assert "Je verzoek is kosteloos" in body
        assert "Telegram-gebruikersnaam te noemen" in body
        assert "We reageren binnen een maand" in body
        # Customers cannot run /delete_user themselves, so the statement must not point them to it
        assert "/delete_user" not in body

    def test_deletion_keeps_records_without_a_name(self):
        body = " ".join(privacy_api.handler({}, None)["body"].split())
        # Orders and payments are kept for the fiscal retention duty, without a name
        assert "tot 8 jaar" in body
        assert "fiscale" in body
        # The old claims no longer hold, so they must not come back
        assert "geanonimiseerde vorm" not in body
        assert "gewist of gepseudonimiseerd" not in body

    def test_describes_the_self_service_data_export(self):
        body = " ".join(privacy_api.handler({}, None)["body"].split())
        assert "/my_data" in body
        assert "zipbestand met JSON-bestanden" in body
        assert "één keer per 30 dagen" in body
        assert "na ongeveer een uur uit de chat verwijderd" in body
        # The timestamp used for the monthly limit is personal data too
        assert "Tijdstip van je laatste gegevensexport" in body

    def test_describes_exports_and_logs(self):
        body = " ".join(privacy_api.handler({}, None)["body"].split())
        assert "privéchat van de beheerder" in body
        assert "na een uur" in body
        assert "technische logbestanden" in body.lower()
        assert "7 dagen" in body

    def test_embeds_logo_as_data_uri(self):
        body = privacy_api.handler({}, None)["body"]
        # Logo is inlined as a base64 JPEG data URI in the top-right corner.
        assert '<img class="logo"' in body
        assert 'src="data:image/jpeg;base64,' in body
        assert 'alt="UBBC logo"' in body

    def test_safe_open_rejects_path_outside_asset_dir(self):
        import pytest

        # Defense in depth: reading outside the handler's own directory is refused.
        with pytest.raises(PermissionError):
            privacy_api._safe_open("/etc/passwd", "r")
        with pytest.raises(PermissionError):
            privacy_api._safe_open(privacy_api._STATEMENT_PATH + "/../../secrets.txt", "r")

    def test_safe_open_allows_asset_files(self):
        with privacy_api._safe_open(privacy_api._STATEMENT_PATH, "r") as f:
            assert f.read().lstrip().startswith("#")

    def test_render_handles_table(self):
        rendered = privacy_api._render("| A | B |\n|---|---|\n| 1 | 2 |")
        assert "<table>" in rendered
        assert "<th>A</th>" in rendered
        assert "<td>1</td>" in rendered

    def test_render_joins_wrapped_bullet(self):
        # A list item wrapped across an indented continuation line stays one <li>.
        rendered = privacy_api._render("- First part of the point\n  wrapped onto a second line.\n- Second item")
        assert "wrapped onto a second line." in rendered
        assert rendered.count("<li>") == 2
        # The continuation is not split off into its own paragraph.
        assert "<p>wrapped onto a second line.</p>" not in rendered


class TestEnsurePrivacyUrl:
    def test_derives_url_from_request(self, monkeypatch):
        import handlers.webhook as webhook

        monkeypatch.delenv("PRIVACY_URL", raising=False)
        event = {
            "headers": {"Host": "abc123.execute-api.eu-north-1.amazonaws.com"},
            "requestContext": {"stage": "test"},
        }
        webhook._ensure_privacy_url(event)
        assert os.environ["PRIVACY_URL"] == "https://abc123.execute-api.eu-north-1.amazonaws.com/test/privacy"

    def test_does_not_overwrite_existing(self, monkeypatch):
        import handlers.webhook as webhook

        monkeypatch.setenv("PRIVACY_URL", "https://preset/privacy")
        webhook._ensure_privacy_url({"headers": {"Host": "h"}, "requestContext": {"stage": "test"}})
        assert os.environ["PRIVACY_URL"] == "https://preset/privacy"

    def test_noop_when_fields_missing(self, monkeypatch):
        import handlers.webhook as webhook

        monkeypatch.delenv("PRIVACY_URL", raising=False)
        webhook._ensure_privacy_url({})
        assert "PRIVACY_URL" not in os.environ


class TestPrivacyCommand:
    def _handler(self):
        h = InfoCommands.__new__(InfoCommands)
        h.environment = "test"
        h._send_message = Mock(return_value={"success": True})
        h._t = lambda key, user_id=None, **p: f"{key}:{p.get('url', '')}"
        return h

    def test_privacy_command_sends_link(self, monkeypatch):
        monkeypatch.setenv("PRIVACY_URL", "https://example.com/test/privacy")
        h = self._handler()

        result = h.handle_privacy(123, 123, [])

        assert result == {"status": "success"}
        h._send_message.assert_called_once()
        sent_text = h._send_message.call_args[0][1]
        assert "https://example.com/test/privacy" in sent_text

    def test_privacy_command_without_url_configured(self, monkeypatch):
        monkeypatch.delenv("PRIVACY_URL", raising=False)
        h = self._handler()

        result = h.handle_privacy(123, 123, [])

        assert result == {"status": "success"}
        h._send_message.assert_called_once()
