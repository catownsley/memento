"""
Anonymization layer for Memento.

Strips identifying information from text before it is sent to the Claude API.
Replaces names, companies, usernames, URLs, and specific dates with placeholders.
The mapping is reversible so that responses can be de-anonymized.

Uses a transformers NER pipeline for automatic entity detection and a manual
mapping file for entities that NER models miss.
"""

import json
import re
from pathlib import Path

from transformers import pipeline

_ner_pipeline = None


def get_ner_pipeline():  # type: ignore[no-untyped-def]
    """
    Load and cache the NER pipeline.
    Uses dslim/bert-base-NER which is a small BERT model fine-tuned
    for named entity recognition. Downloads on first use.
    """
    global _ner_pipeline
    if _ner_pipeline is None:
        _ner_pipeline = pipeline(
            "ner",
            model="dslim/bert-base-NER",
            aggregation_strategy="simple",
        )
    return _ner_pipeline


# Map BERT NER labels to our placeholder categories
NER_LABEL_MAP = {
    "PER": "Person",
    "ORG": "Organization",
    "LOC": "Location",
}


def load_allowlist(allowlist_path: str) -> set[str]:
    """
    Load the NER allowlist from a JSON file.

    The file should be a JSON array of strings that the NER model should
    never anonymize, even if it detects them as named entities.
    These are public names that do not identify the user.
    """
    path = Path(allowlist_path)
    if not path.exists():
        return set()
    with open(path, encoding="utf-8") as f:
        return set(json.load(f))  # type: ignore[arg-type]


def load_manual_mapping(mapping_path: str) -> dict[str, str]:
    """
    Load the manual anonymization mapping from a JSON file.

    The file should be a JSON object mapping real values to placeholders:
    {
        "Charlotte": "[USER]",
        "Empower": "[COMPANY_A]",
        "catownsley": "[USERNAME_1]"
    }
    """
    path = Path(mapping_path)
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)  # type: ignore[no-any-return]


def _run_ner(text: str, allowlist: set[str] | None = None) -> list[dict]:  # type: ignore[type-arg]
    """
    Run NER on the original text and return detected entities
    that are not on the allowlist.

    Returns a list of dicts with keys: text, label, score.
    Deduplicated by entity text.
    """
    ner = get_ner_pipeline()
    entities = ner(text)
    safe_entities = allowlist or set()

    seen: set[str] = set()
    results = []

    for ent in entities:
        label = ent["entity_group"]
        entity_text = ent["word"].strip()

        if label not in NER_LABEL_MAP:
            continue
        if entity_text in safe_entities:
            continue
        # Also skip if the entity is a substring of an allowlisted entry
        # (BERT can split tokens, e.g., "GitH" from "GitHub")
        if any(entity_text in safe for safe in safe_entities):
            continue
        if entity_text in seen:
            continue
        if len(entity_text) < 2:
            continue

        seen.add(entity_text)
        results.append({
            "text": entity_text,
            "label": label,
            "score": ent["score"],
        })

    return results


def anonymize(
    text: str,
    manual_mapping: dict[str, str] | None = None,
    allowlist: set[str] | None = None,
    use_ner: bool = True,
) -> tuple[str, dict[str, str]]:
    """
    Remove identifying information from text.

    Runs NER on the original text first to detect entities,
    then applies manual mapping, then applies NER replacements
    for any entities that the manual mapping did not already cover.

    Returns:
        A tuple of (anonymized_text, full_mapping) where full_mapping
        includes both manual and auto-detected replacements.
    """
    full_mapping: dict[str, str] = {}
    result = text

    # Run NER on the original text before any replacements,
    # so the model sees clean text without placeholder brackets
    ner_entities = []
    if use_ner:
        ner_entities = _run_ner(text, allowlist=allowlist)

    # Apply manual mapping first, longest keys first to avoid
    # partial matches (e.g., "charlottesweb-app" before "charlotte")
    manual_covered: set[str] = set()
    if manual_mapping:
        sorted_entries = sorted(manual_mapping.items(), key=lambda x: len(x[0]), reverse=True)
        for real_value, placeholder in sorted_entries:
            if real_value in result:
                result = result.replace(real_value, placeholder)
                full_mapping[placeholder] = real_value
                manual_covered.add(real_value)

    # Now apply NER replacements for entities not already handled
    counters: dict[str, int] = {"PER": 0, "ORG": 0, "LOC": 0}
    for ent in ner_entities:
        entity_text = ent["text"]
        label = ent["label"]

        # Skip if manual mapping already replaced this entity
        if entity_text in manual_covered:
            continue
        # Skip if entity text is no longer in the result
        # (it may have been part of a longer manual mapping match)
        if entity_text not in result:
            continue

        counters[label] += 1
        prefix = NER_LABEL_MAP[label]
        placeholder = f"{prefix}_{counters[label]}"
        result = result.replace(entity_text, placeholder)
        full_mapping[placeholder] = entity_text

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
