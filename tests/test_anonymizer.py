"""
Automated tests for the anonymizer module.

These tests verify that all known PII is stripped from text
before it could be sent to the Claude API. If any test fails,
it means identifying information would leak.
"""

import json
import re
from pathlib import Path

import pytest

from src.anonymizer import anonymize, deanonymize, load_allowlist, load_manual_mapping


MAPPING_PATH = "anonymizer_mapping.json"
ALLOWLIST_PATH = "anonymizer_allowlist.json"


@pytest.fixture
def mapping() -> dict[str, str]:
    """Load the manual mapping. Skip tests if file is not present."""
    path = Path(MAPPING_PATH)
    if not path.exists():
        pytest.skip("anonymizer_mapping.json not found (may be encrypted)")
    return load_manual_mapping(MAPPING_PATH)


@pytest.fixture
def allowlist() -> set[str]:
    """Load the allowlist. Return empty set if not present."""
    path = Path(ALLOWLIST_PATH)
    if not path.exists():
        return set()
    return load_allowlist(ALLOWLIST_PATH)


@pytest.fixture
def pii_values(mapping: dict[str, str]) -> list[str]:
    """Extract all real PII values from the mapping."""
    return list(mapping.keys())


class TestNoLeaks:
    """Verify that no PII survives anonymization."""

    def test_all_mapping_entries_replaced(
        self, mapping: dict[str, str], allowlist: set[str]
    ) -> None:
        """Every value in the mapping must be replaced when present in text."""
        for real_value, placeholder in mapping.items():
            text = f"This text contains {real_value} as a test."
            anonymized, _ = anonymize(text, manual_mapping=mapping, allowlist=allowlist)
            assert real_value not in anonymized, (
                f"PII leak: '{real_value}' survived anonymization. "
                f"Anonymized text: {anonymized}"
            )

    def test_combined_pii_paragraph(
        self, mapping: dict[str, str], allowlist: set[str]
    ) -> None:
        """A paragraph containing all PII values should have none after anonymization."""
        parts = [f"mention of {v}" for v in mapping.keys()]
        text = ". ".join(parts)
        anonymized, _ = anonymize(text, manual_mapping=mapping, allowlist=allowlist)

        for real_value in mapping.keys():
            assert real_value not in anonymized, (
                f"PII leak in combined text: '{real_value}' survived"
            )

    def test_urls_stripped(
        self, mapping: dict[str, str], allowlist: set[str]
    ) -> None:
        """URLs should be replaced with placeholders."""
        text = "Check out https://github.com/catownsley/memento for details."
        anonymized, _ = anonymize(text, manual_mapping=mapping, allowlist=allowlist)
        assert "https://" not in anonymized
        assert "github.com" not in anonymized

    def test_email_stripped(
        self, mapping: dict[str, str], allowlist: set[str]
    ) -> None:
        """Email addresses should be replaced with placeholders."""
        text = "Send mail to user@example.com for more info."
        anonymized, _ = anonymize(text, manual_mapping=mapping, allowlist=allowlist)
        assert "user@example.com" not in anonymized
        assert "[EMAIL_" in anonymized

    def test_file_paths_anonymized(
        self, mapping: dict[str, str], allowlist: set[str]
    ) -> None:
        """Local file paths containing the username should be anonymized."""
        text = "The file is at /Users/ct/Python/memento/src/config.py"
        anonymized, _ = anonymize(text, manual_mapping=mapping, allowlist=allowlist)
        assert "/Users/ct/" not in anonymized


class TestRoundTrip:
    """Verify that de-anonymization correctly restores original text."""

    def test_simple_round_trip(
        self, mapping: dict[str, str], allowlist: set[str]
    ) -> None:
        """Anonymize then de-anonymize should return the original text."""
        original = "Charlotte has an interview at Empower on Monday."
        anonymized, anon_mapping = anonymize(
            original, manual_mapping=mapping, allowlist=allowlist
        )
        restored = deanonymize(anonymized, anon_mapping)
        assert restored == original

    def test_complex_round_trip(
        self, mapping: dict[str, str], allowlist: set[str]
    ) -> None:
        """Round trip with multiple PII types."""
        original = (
            "Charlotte talked to Chris Thomas about her charlottesweb-app project. "
            "She has interviews at Empower and Upstart."
        )
        anonymized, anon_mapping = anonymize(
            original, manual_mapping=mapping, allowlist=allowlist
        )

        # Verify nothing leaked
        for name in ["Charlotte", "Chris Thomas", "charlottesweb-app", "Empower", "Upstart"]:
            assert name not in anonymized

        # Verify round trip
        restored = deanonymize(anonymized, anon_mapping)
        assert restored == original


class TestAllowlist:
    """Verify that allowlisted entities are preserved."""

    def test_allowlisted_orgs_preserved(
        self, mapping: dict[str, str], allowlist: set[str]
    ) -> None:
        """Public entity names on the allowlist should not be anonymized."""
        text = "She used GitHub and AWS at her previous job."
        anonymized, _ = anonymize(text, manual_mapping=mapping, allowlist=allowlist)
        assert "GitHub" in anonymized
        assert "AWS" in anonymized

    def test_allowlisted_tools_preserved(
        self, mapping: dict[str, str], allowlist: set[str]
    ) -> None:
        """Technology names on the allowlist should not be anonymized."""
        text = "The project uses PostgreSQL, Python, and FastAPI."
        anonymized, _ = anonymize(text, manual_mapping=mapping, allowlist=allowlist)
        assert "PostgreSQL" in anonymized
        assert "Python" in anonymized
        assert "FastAPI" in anonymized


class TestEdgeCases:
    """Test edge cases that could cause leaks."""

    def test_case_sensitivity(
        self, mapping: dict[str, str], allowlist: set[str]
    ) -> None:
        """Both 'Charlotte' and 'charlotte' should be anonymized."""
        text = "Charlotte said charlotte is her name."
        anonymized, _ = anonymize(text, manual_mapping=mapping, allowlist=allowlist)
        assert "Charlotte" not in anonymized
        assert "charlotte" not in anonymized

    def test_substring_safety(
        self, mapping: dict[str, str], allowlist: set[str]
    ) -> None:
        """Longer mappings should be replaced before shorter ones to avoid partial matches."""
        text = "The charlottesweb-app repo and charlottesweb project."
        anonymized, _ = anonymize(text, manual_mapping=mapping, allowlist=allowlist)
        assert "charlottesweb-app" not in anonymized
        assert "charlottesweb" not in anonymized

    def test_empty_text(
        self, mapping: dict[str, str], allowlist: set[str]
    ) -> None:
        """Empty text should not cause errors."""
        anonymized, anon_mapping = anonymize("", manual_mapping=mapping, allowlist=allowlist)
        assert anonymized == ""
        assert anon_mapping == {}

    def test_no_mapping_still_strips_urls_and_emails(self) -> None:
        """Even without a mapping, URLs and emails should be stripped."""
        text = "Visit https://secret.example.com or email me@secret.com"
        anonymized, _ = anonymize(text, manual_mapping=None, use_ner=False)
        assert "https://" not in anonymized
        assert "me@secret.com" not in anonymized
