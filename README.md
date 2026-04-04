# Memento

A local RAG (Retrieval Augmented Generation) pipeline that provides persistent memory across Claude Code sessions by indexing conversation transcripts.

Named after the 2000 film where the protagonist tattoos critical information on himself because he cannot form new memories. This project serves the same purpose: encoding conversation history into a searchable format so that future sessions can retrieve full context, not just summaries.

## What It Does

Claude Code saves conversation transcripts as `.jsonl` files on your local machine. Memento parses those transcripts, generates vector embeddings, and stores them in PostgreSQL with the pgvector extension. When you ask a question, Memento finds the most relevant conversation fragments and provides them as context.

## Architecture

All data processing and storage happens locally. The only external call is to the Claude API at query time, and all data sent to the API passes through an anonymization layer first.

### Data Ingestion (fully local)

1. Transcript files (`.jsonl`) are read and split into chunks
2. Each chunk is embedded using sentence-transformers, which runs locally
3. Chunks and their embeddings are stored in PostgreSQL with pgvector

### Query Pipeline

1. Your question is embedded locally using sentence-transformers
2. pgvector performs a similarity search to find relevant chunks
3. Retrieved chunks pass through the anonymization layer, which strips identifying information (names, companies, usernames, URLs, specific dates)
4. The anonymized chunks and your question are sent to the Claude API
5. The response is de-anonymized (placeholders swapped back to real values) before being shown to you

### Privacy Boundary

Everything above the anonymization layer stays on your machine. The anonymization layer strips identifiers but preserves the substance of the conversation. The Claude API receives text with no way to connect it to a specific person.

Anthropic's API policy: data is deleted after 7 days and is never used for model training.

## Stack

| Component | Technology | Runs Where |
|-----------|-----------|------------|
| Transcript parsing | Python | Local |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2) | Local |
| Vector storage | PostgreSQL 17 + pgvector 0.8.2 | Local |
| Anonymization | spaCy NER + manual mapping | Local |
| Query LLM | Claude API (anthropic SDK) | API call, anonymized data only |

## Requirements

| Dependency | Version |
|-----------|---------|
| Python | 3.14+ |
| PostgreSQL | 17+ |
| pgvector | 0.8.2+ |

## Project Structure

```
memento/
    .github/              GitHub Actions, templates, Dependabot
    src/
        config.py         Configuration and environment loading
        database.py       PostgreSQL and pgvector setup
        parser.py         Transcript file parser and chunking
        embeddings.py     Local embedding generation
        anonymizer.py     PII stripping before API calls
        query.py          Similarity search and Claude API integration
        ingest.py         Ingestion pipeline orchestration
    tests/                Test suite
```

## Setup

### PostgreSQL

Install PostgreSQL and pgvector:

```
brew install postgresql@17
brew install pgvector
brew services start postgresql@17
```

Enable the pgvector extension:

```
psql postgres -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### Python Environment

```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Configuration

Copy the example environment file and fill in your values:

```
cp .env.example .env
```

The only external API key required is for the Claude API (`ANTHROPIC_API_KEY`).

## Security

This project uses the same security tooling and CI/CD pipeline patterns established in [charlottesweb-app](https://github.com/catownsley/charlottesweb-app). See [SECURITY.md](SECURITY.md) for details.
