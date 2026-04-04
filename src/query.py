"""
Query engine for Memento.

Handles the full query pipeline:
1. Embed the user's question locally
2. Search pgvector for similar chunks
3. Anonymize the retrieved chunks
4. Send to Claude API with the question
5. De-anonymize the response
"""

import anthropic
import numpy as np
import psycopg2
from pgvector.psycopg2 import register_vector

from src.anonymizer import anonymize, deanonymize, load_manual_mapping
from src.embeddings import embed_text


def search_similar_chunks(
    database_url: str,
    query_embedding: np.ndarray,
    limit: int = 10,
) -> list[dict]:  # type: ignore[type-arg]
    """
    Find the most similar chunks to the query embedding using cosine similarity.

    Returns a list of dicts with keys: id, role, content, timestamp, conversation_id, similarity.
    """
    conn = psycopg2.connect(database_url)
    register_vector(conn)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, role, content, timestamp, conversation_id,
               1 - (embedding <=> %s::vector) AS similarity
        FROM chunks
        ORDER BY embedding <=> %s::vector
        LIMIT %s;
        """,
        (query_embedding.tolist(), query_embedding.tolist(), limit),
    )

    results = []
    for row in cur.fetchall():
        results.append({
            "id": row[0],
            "role": row[1],
            "content": row[2],
            "timestamp": row[3],
            "conversation_id": row[4],
            "similarity": float(row[5]),
        })

    cur.close()
    conn.close()
    return results


def build_context(chunks: list[dict], mapping: dict[str, str]) -> tuple[str, dict[str, str]]:  # type: ignore[type-arg]
    """
    Build the context string from retrieved chunks, anonymizing each one.

    Returns the full anonymized context string and the combined mapping
    for de-anonymization.
    """
    context_parts = []
    full_mapping: dict[str, str] = {}

    for chunk in chunks:
        anonymized_content, chunk_mapping = anonymize(
            chunk["content"], manual_mapping=mapping
        )
        context_parts.append(
            f"[{chunk['role']}]: {anonymized_content}"
        )
        full_mapping.update(chunk_mapping)

    context = "\n\n".join(context_parts)
    return context, full_mapping


def query(
    question: str,
    database_url: str,
    anthropic_api_key: str,
    claude_model: str = "claude-sonnet-4-6",
    embedding_model: str = "all-MiniLM-L6-v2",
    retrieval_limit: int = 10,
    anonymizer_mapping_path: str = "anonymizer_mapping.json",
) -> dict:  # type: ignore[type-arg]
    """
    Run the full query pipeline.

    1. Embed the question locally
    2. Search for similar chunks in pgvector
    3. Anonymize the chunks
    4. Send to Claude API
    5. De-anonymize the response

    Returns a dict with keys: answer, chunks_used, anonymization_mapping.
    """
    # Step 1: Embed the question locally
    query_embedding = embed_text(question, model_name=embedding_model)

    # Step 2: Search for similar chunks
    chunks = search_similar_chunks(database_url, query_embedding, limit=retrieval_limit)

    if not chunks:
        return {
            "answer": "No relevant conversation history found.",
            "chunks_used": 0,
            "anonymization_mapping": {},
        }

    # Step 3: Anonymize
    manual_mapping = load_manual_mapping(anonymizer_mapping_path)
    context, anon_mapping = build_context(chunks, manual_mapping)

    # Step 4: Send to Claude API
    client = anthropic.Anthropic(api_key=anthropic_api_key)

    system_prompt = (
        "You are a memory retrieval assistant. "
        "You are given excerpts from past conversations and a question. "
        "Answer the question based on the conversation excerpts provided. "
        "If the excerpts do not contain enough information to answer, say so. "
        "Do not make up information that is not in the excerpts."
    )

    user_message = (
        f"Here are relevant excerpts from past conversations:\n\n"
        f"{context}\n\n"
        f"Question: {question}"
    )

    response = client.messages.create(
        model=claude_model,
        max_tokens=2048,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    raw_answer = response.content[0].text  # type: ignore[union-attr]

    # Step 5: De-anonymize the response
    answer = deanonymize(raw_answer, anon_mapping)

    return {
        "answer": answer,
        "chunks_used": len(chunks),
        "anonymization_mapping": anon_mapping,
    }
