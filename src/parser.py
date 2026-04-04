"""
Transcript parser for Claude Code conversation files.

Reads .jsonl files from the transcript directory,
extracts conversation turns, and splits them into chunks
suitable for embedding.
"""

import json
from pathlib import Path


def list_transcript_files(transcript_dir: str) -> list[Path]:
    """Return all .jsonl files in the transcript directory, sorted by modification time."""
    path = Path(transcript_dir)
    files = list(path.glob("*.jsonl"))
    files.sort(key=lambda f: f.stat().st_mtime)
    return files


def parse_transcript(file_path: Path) -> list[dict]:  # type: ignore[type-arg]
    """
    Parse a single .jsonl transcript file into a list of messages.

    Each line in the file is a JSON object. This function extracts
    the role (human/assistant) and content from each message.

    Returns a list of dicts with keys: role, content, timestamp (if available).
    """
    messages = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Claude Code transcripts wrap messages in a "message" field.
            # Only entries with type "user" or "assistant" contain conversation content.
            entry_type = entry.get("type", "")
            if entry_type not in ("user", "assistant"):
                continue

            message = entry.get("message", {})
            if not message:
                continue

            role = message.get("role", "")
            content = ""

            if isinstance(message.get("content"), str):
                content = message["content"]
            elif isinstance(message.get("content"), list):
                # Content can be a list of blocks (text, tool_use, thinking, etc.)
                text_parts = []
                for block in message["content"]:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif isinstance(block, str):
                        text_parts.append(block)
                content = "\n".join(text_parts)

            if role and content.strip():
                messages.append({
                    "role": role,
                    "content": content.strip(),
                    "timestamp": entry.get("timestamp", ""),
                })

    return messages


def chunk_messages(
    messages: list[dict],  # type: ignore[type-arg]
    conversation_id: str,
    max_chunk_size: int = 1000,
) -> list[dict]:  # type: ignore[type-arg]
    """
    Split a list of messages into chunks for embedding.

    Groups consecutive messages and splits them if they exceed max_chunk_size
    characters. Each chunk includes the conversation_id and a sequential index.

    Returns a list of dicts with keys: conversation_id, chunk_index, role, content, timestamp.
    """
    chunks = []
    chunk_index = 0

    for message in messages:
        content = message["content"]
        role = message["role"]
        timestamp = message.get("timestamp", "")

        # If the message fits in one chunk, add it directly
        if len(content) <= max_chunk_size:
            chunks.append({
                "conversation_id": conversation_id,
                "chunk_index": chunk_index,
                "role": role,
                "content": content,
                "timestamp": timestamp,
            })
            chunk_index += 1
        else:
            # Split long messages at sentence boundaries when possible
            sentences = content.replace(". ", ".\n").split("\n")
            current_chunk = ""

            for sentence in sentences:
                if len(current_chunk) + len(sentence) + 1 > max_chunk_size:
                    if current_chunk:
                        chunks.append({
                            "conversation_id": conversation_id,
                            "chunk_index": chunk_index,
                            "role": role,
                            "content": current_chunk.strip(),
                            "timestamp": timestamp,
                        })
                        chunk_index += 1
                    current_chunk = sentence
                else:
                    if current_chunk:
                        current_chunk += " " + sentence
                    else:
                        current_chunk = sentence

            if current_chunk.strip():
                chunks.append({
                    "conversation_id": conversation_id,
                    "chunk_index": chunk_index,
                    "role": role,
                    "content": current_chunk.strip(),
                    "timestamp": timestamp,
                })
                chunk_index += 1

    return chunks
