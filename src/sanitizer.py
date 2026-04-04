"""
Chunk sanitization for Memento.

Validates and sanitizes transcript chunks before they are stored in the
database. This defends against memory poisoning, where malicious or
corrupted content in transcript files could influence future query results.

Sanitization runs during ingestion, before embedding and storage.
"""

import re

# Patterns that look like prompt injection attempts.
# These could appear in transcripts if a conversation included
# discussion of prompt injection, so we flag rather than strip.
INJECTION_PATTERNS = [
    # Direct instruction override attempts
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"ignore\s+(all\s+)?above\s+instructions",
    r"disregard\s+(all\s+)?previous",
    r"forget\s+(all\s+)?previous",
    r"you\s+are\s+now\s+(a|an)\s+",
    r"new\s+instructions?\s*:",
    r"system\s*:\s*you\s+are",
    # Role override attempts
    r"<\s*system\s*>",
    r"<\s*/?\s*instructions?\s*>",
    r"\[SYSTEM\]",
    r"\[INST\]",
]

# Content that should never appear in stored chunks
BLOCKED_CONTENT = [
    # Actual API keys or secrets that may have leaked into transcripts
    r"sk-ant-[a-zA-Z0-9]{20,}",
    r"sk-[a-zA-Z0-9]{20,}",
    r"AKIA[A-Z0-9]{16}",  # AWS access key
    r"ghp_[a-zA-Z0-9]{30,}",  # GitHub personal access token
    r"xox[bpsa]-[a-zA-Z0-9-]+",  # Slack token
]


def sanitize_chunk(content: str) -> tuple[str, list[str]]:
    """
    Sanitize a chunk of text before storage.

    Returns a tuple of (sanitized_content, warnings).
    Warnings describe any modifications made.

    Blocked content (leaked secrets) is redacted.
    Injection patterns are flagged with warnings but preserved,
    because they may be legitimate conversation about prompt injection.
    """
    warnings: list[str] = []
    result = content

    # Redact any leaked secrets
    for pattern in BLOCKED_CONTENT:
        matches = re.findall(pattern, result)
        if matches:
            for match in matches:
                result = result.replace(match, "[REDACTED_SECRET]")
                warnings.append(
                    f"Redacted potential secret matching pattern: {pattern}"
                )

    # Flag injection patterns (warn but do not remove)
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, result, re.IGNORECASE):
            warnings.append(
                f"Chunk contains text matching injection pattern: {pattern}"
            )

    return result, warnings


def validate_chunk(content: str, max_length: int = 10000) -> tuple[bool, str]:
    """
    Validate that a chunk is suitable for storage.

    Returns (is_valid, reason). If is_valid is False, the chunk
    should be skipped during ingestion.
    """
    if not content or not content.strip():
        return False, "Empty content"

    if len(content) > max_length:
        return False, f"Content exceeds maximum length ({len(content)} > {max_length})"

    # Skip chunks that are mostly non-text (base64, binary data, etc.)
    printable_ratio = sum(1 for c in content if c.isprintable() or c.isspace()) / len(content)
    if printable_ratio < 0.8:
        return False, f"Content is mostly non-printable ({printable_ratio:.0%} printable)"

    return True, ""
