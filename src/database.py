"""
Database setup and connection management for Memento.

Uses PostgreSQL with the pgvector extension for vector similarity search.
"""

import psycopg2
from pgvector.psycopg2 import register_vector


EMBEDDING_DIMENSIONS = 384  # all-MiniLM-L6-v2 output size


def get_connection(database_url: str):  # type: ignore[no-untyped-def]
    """Create a new database connection and register the vector type."""
    conn = psycopg2.connect(database_url)
    register_vector(conn)
    return conn


def create_tables(database_url: str) -> None:
    """
    Create the database tables if they do not exist.

    Tables:
        transcripts: stores parsed conversation chunks with their embeddings
        anonymizer_entities: stores the mapping of real values to placeholders
    """
    conn = get_connection(database_url)
    cur = conn.cursor()

    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS chunks (
            id SERIAL PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp TEXT,
            embedding vector({EMBEDDING_DIMENSIONS}),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(conversation_id, chunk_index)
        );
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_chunks_embedding
        ON chunks USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100);
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS anonymizer_entities (
            id SERIAL PRIMARY KEY,
            entity_type TEXT NOT NULL,
            real_value TEXT NOT NULL,
            placeholder TEXT NOT NULL,
            UNIQUE(real_value)
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ingestion_log (
            id SERIAL PRIMARY KEY,
            file_path TEXT NOT NULL UNIQUE,
            file_size BIGINT NOT NULL,
            chunks_created INTEGER NOT NULL,
            ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    conn.commit()
    cur.close()
    conn.close()
