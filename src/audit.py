"""
Audit logging for Memento.

Records every query attempt, whether it was approved or denied,
how many chunks were sent, and when. This is the forensic trail
for verifying that no unauthorized data left the machine.

The audit log file is gitignored and stays local.
"""

import json
from datetime import UTC, datetime
from pathlib import Path


def log_query(
    question: str,
    chunks_sent: int,
    approved: bool,
    log_path: str = "audit.log",
) -> None:
    """
    Append a query record to the audit log.

    Each record is a single JSON line with:
        timestamp: ISO 8601 UTC
        action: QUERY_APPROVED or QUERY_DENIED
        question_length: character count of the question (not the question itself)
        chunks_sent: number of anonymized chunks sent to the API
    """
    record = {
        "timestamp": datetime.now(UTC).isoformat(),
        "action": "QUERY_APPROVED" if approved else "QUERY_DENIED",
        "question_length": len(question),
        "chunks_sent": chunks_sent,
    }

    path = Path(log_path)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def read_audit_log(log_path: str = "audit.log") -> list[dict]:  # type: ignore[type-arg]
    """Read all records from the audit log."""
    path = Path(log_path)
    if not path.exists():
        return []

    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def print_audit_summary(log_path: str = "audit.log") -> None:
    """Print a summary of the audit log to stdout."""
    records = read_audit_log(log_path)
    if not records:
        print("No audit records found.")
        return

    approved = [r for r in records if r["action"] == "QUERY_APPROVED"]
    denied = [r for r in records if r["action"] == "QUERY_DENIED"]
    total_chunks = sum(r["chunks_sent"] for r in approved)

    print(f"Total queries: {len(records)}")
    print(f"Approved: {len(approved)}")
    print(f"Denied: {len(denied)}")
    print(f"Total chunks sent to API: {total_chunks}")
    if records:
        print(f"First query: {records[0]['timestamp']}")
        print(f"Last query: {records[-1]['timestamp']}")
