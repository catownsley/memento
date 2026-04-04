"""
Anonymization layer for Memento.

Strips identifying information from text before it is sent to the Claude API.
Replaces names, companies, usernames, URLs, and specific dates with placeholders.
The mapping is reversible so that responses can be de-anonymized.

Uses spaCy NER for automatic entity detection and a manual mapping file
for entities that NER models miss.
"""

import json
import re
from pathlib import Path

import spacy


_nlp = None


def get_nlp():  # type: ignore[no-untyped-def]
    """Load the spaCy model. Downloads en_core_web_sm on first use if needed."""
    global _nlp
    if _nlp is None:
        try:
            _nlp = spacy.load("en_core_web_sm")
        except OSError:
            from spacy.cli import download
            download("en_core_web_sm")
            _nlp = spacy.load("en_core_web_sm")
    return _nlp


def load_manual_mapping(mapping_path: str) -> dict[str, str]:
    """
    Load the manual anonymization mapping from a JSON file.

    The file should be a JSON object mapping real values to placeholders:
    {
        "Charlotte": "User",
        "Empower": "Company_A",
        "catownsley": "username_1"
    }
    """
    path = Path(mapping_path)
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)  # type: ignore[no-any-return]


def anonymize(
    text: str,
    manual_mapping: dict[str, str] | None = None,
    use_ner: bool = True,
) -> tuple[str, dict[str, str]]:
    """
    Remove identifying information from text.

    Applies manual mapping first (exact string replacements),
    then runs spaCy NER to catch PERSON, ORG, and GPE entities
    that the manual mapping missed.

    Returns:
        A tuple of (anonymized_text, full_mapping) where full_mapping
        includes both manual and auto-detected replacements.
    """
    full_mapping: dict[str, str] = {}
    result = text

    # Apply manual mapping first, longest keys first to avoid
    # partial matches (e.g., "charlottesweb-app" before "charlotte")
    if manual_mapping:
        sorted_entries = sorted(manual_mapping.items(), key=lambda x: len(x[0]), reverse=True)
        for real_value, placeholder in sorted_entries:
            if real_value in result:
                result = result.replace(real_value, placeholder)
                full_mapping[placeholder] = real_value

    # Apply NER for entities the manual mapping missed
    if use_ner:
        nlp = get_nlp()
        doc = nlp(result)

        # Track counters for generating placeholder names
        counters: dict[str, int] = {"PERSON": 0, "ORG": 0, "GPE": 0}
        prefixes = {"PERSON": "Person", "ORG": "Organization", "GPE": "Location"}

        for ent in doc.ents:
            if ent.label_ in counters and ent.text not in full_mapping.values():
                # Check if this entity was already replaced by manual mapping
                already_mapped = any(
                    ent.text == placeholder for placeholder in full_mapping
                )
                if not already_mapped:
                    counters[ent.label_] += 1
                    placeholder = f"{prefixes[ent.label_]}_{counters[ent.label_]}"
                    result = result.replace(ent.text, placeholder)
                    full_mapping[placeholder] = ent.text

    # Strip URLs
    url_count = 0
    urls_found = re.findall(r'https?://\S+', result)
    for url in urls_found:
        url_count += 1
        placeholder = f"[URL_{url_count}]"
        result = result.replace(url, placeholder)
        full_mapping[placeholder] = url

    # Strip email addresses
    email_count = 0
    emails_found = re.findall(r'\S+@\S+\.\S+', result)
    for email in emails_found:
        email_count += 1
        placeholder = f"[EMAIL_{email_count}]"
        result = result.replace(email, placeholder)
        full_mapping[placeholder] = email

    return result, full_mapping


def deanonymize(text: str, mapping: dict[str, str]) -> str:
    """
    Reverse the anonymization by swapping placeholders back to real values.

    The mapping should be the same dict returned by anonymize().
    Keys are placeholders, values are real strings.

    Replacements are applied longest placeholder first to avoid
    partial matches (e.g., "User" inside "/Users/user/").
    """
    result = text
    sorted_items = sorted(mapping.items(), key=lambda x: len(x[0]), reverse=True)
    for placeholder, real_value in sorted_items:
        result = result.replace(placeholder, real_value)
    return result
