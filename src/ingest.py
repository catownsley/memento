"""
Ingestion pipeline for Memento.

Orchestrates the full flow from transcript files to stored embeddings:
1. Find transcript files that have not been ingested yet
2. Parse each file into messages
3. Chunk the messages
4. Generate embeddings locally
5. Store chunks and embeddings in pgvector
"""

import psycopg2
from pgvector.psycopg2 import register_vector

from src.config import get_config, validate_config
from src.database import create_tables, get_connection
from src.embeddings import embed_batch
from src.parser import chunk_messages, list_transcript_files, parse_transcript


def get_ingested_files(database_url: str) -> set[str]:
    """Return the set of file paths that have already been ingested."""
    conn = get_connection(database_url)
    cur = conn.cursor()
    cur.execute("SELECT file_path FROM ingestion_log;")
    files = {row[0] for row in cur.fetchall()}
    cur.close()
    conn.close()
    return files


def ingest_file(
    file_path: str,
    database_url: str,
    embedding_model: str = "all-MiniLM-L6-v2",
    max_chunk_size: int = 1000,
) -> int:
    """
    Ingest a single transcript file.

    Parses the file, chunks the messages, generates embeddings,
    and stores everything in the database.

    Returns the number of chunks created.
    """
    from pathlib import Path

    path = Path(file_path)
    conversation_id = path.stem

    # Parse and chunk
    messages = parse_transcript(path)
    if not messages:
        return 0

    chunks = chunk_messages(messages, conversation_id, max_chunk_size=max_chunk_size)
    if not chunks:
        return 0

    # Generate embeddings for all chunks in one batch
    texts = [chunk["content"] for chunk in chunks]
    embeddings = embed_batch(texts, model_name=embedding_model)

    # Store in database
    conn = get_connection(database_url)
    cur = conn.cursor()

    for i, chunk in enumerate(chunks):
        cur.execute(
            """
            INSERT INTO chunks (conversation_id, chunk_index, role, content, timestamp, embedding)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (conversation_id, chunk_index) DO NOTHING;
            """,
            (
                chunk["conversation_id"],
                chunk["chunk_index"],
                chunk["role"],
                chunk["content"],
                chunk["timestamp"],
                embeddings[i].tolist(),
            ),
        )

    # Log the ingestion
    cur.execute(
        """
        INSERT INTO ingestion_log (file_path, file_size, chunks_created)
        VALUES (%s, %s, %s)
        ON CONFLICT (file_path) DO NOTHING;
        """,
        (str(file_path), path.stat().st_size, len(chunks)),
    )

    conn.commit()
    cur.close()
    conn.close()

    return len(chunks)


def ingest_all(
    database_url: str | None = None,
    transcript_dir: str | None = None,
    embedding_model: str | None = None,
) -> dict:  # type: ignore[type-arg]
    """
    Ingest all new transcript files that have not been processed yet.

    Uses configuration from environment if parameters are not provided.

    Returns a dict with keys: files_processed, total_chunks, skipped.
    """
    config = get_config()

    database_url = database_url or config["database_url"]
    transcript_dir = transcript_dir or config["transcript_dir"]
    embedding_model = embedding_model or config["embedding_model"]

    # Validate
    warnings = validate_config(config)
    for warning in warnings:
        print(f"WARNING: {warning}")

    # Create tables if they do not exist
    create_tables(database_url)

    # Find files to process
    all_files = list_transcript_files(transcript_dir)
    already_ingested = get_ingested_files(database_url)

    files_to_process = [
        f for f in all_files if str(f) not in already_ingested
    ]

    results = {
        "files_processed": 0,
        "total_chunks": 0,
        "skipped": len(all_files) - len(files_to_process),
    }

    for file_path in files_to_process:
        print(f"Ingesting: {file_path.name}")
        chunks_created = ingest_file(
            str(file_path), database_url, embedding_model=embedding_model
        )
        print(f"  Created {chunks_created} chunks")
        results["files_processed"] += 1
        results["total_chunks"] += chunks_created

    return results


if __name__ == "__main__":
    results = ingest_all()
    print(
        f"\nDone. Processed {results['files_processed']} files, "
        f"created {results['total_chunks']} chunks, "
        f"skipped {results['skipped']} already ingested."
    )
