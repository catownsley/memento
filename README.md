# Memento

A local RAG (Retrieval Augmented Generation) pipeline that provides persistent memory across Claude Code sessions by indexing conversation transcripts.

Named after the 2000 film where the protagonist tattoos critical information on himself because he cannot form new memories. This project serves the same purpose: encoding conversation history into a searchable format so that future sessions can retrieve full context, not just summaries.

## What It Does

Claude Code saves conversation transcripts as `.jsonl` files on your local machine. Memento parses those transcripts, generates vector embeddings, and stores them in PostgreSQL with the pgvector extension. When you ask a question, Memento finds the most relevant conversation fragments and provides them as context to a Claude API call.

The key constraint: private data stays private. Conversation content never leaves your machine in identifiable form. See the Security section below and [SECURITY.md](SECURITY.md) for the full breakdown.

## Architecture

```
Transcript Files (.jsonl)
        |
        v
   Transcript Parser -----> Chunks
        |
        v
   sentence-transformers -----> Vector embeddings (local, no API call)
        |
        v
   PostgreSQL + pgvector -----> Stores chunks + embeddings locally
```

At query time:

```
Your Question
        |
        v
   sentence-transformers -----> Embeds your question (local)
        |
        v
   pgvector similarity search -----> Finds relevant chunks (local)
        |
        v
   Anonymization layer -----> Strips names, companies, usernames, URLs, paths
        |
        v
   Approval gate -----> You see the full payload and type 'yes' to send
        |
        v
   Claude API -----> Receives anonymized text, returns answer
        |
        v
   De-anonymize -----> Placeholders swapped back to real values
        |
        v
   Audit log -----> Records that a query was sent (no content logged)
```

## Security

This project handles private conversation data. Security is not an afterthought.

### Data stays local

| Data | Where It Lives | Leaves Your Machine? |
|------|---------------|---------------------|
| Transcript files | Local filesystem | No |
| Vector embeddings | PostgreSQL (local) | No |
| Anonymizer mapping | Local filesystem, encrypted at rest | No |
| Database | PostgreSQL (localhost only) | No |
| Audit log | Local filesystem | No |
| Anonymized query chunks | Sent to Claude API | Yes, stripped of all identifiers |

### Anonymization: three layers

1. **Manual mapping:** A local JSON file maps real names, companies, usernames, URLs, and file paths to bracketed placeholders. Longest replacements applied first to prevent substring collisions.

2. **NER (Named Entity Recognition):** spaCy scans text after manual replacements and catches any PERSON, ORG, or location entities the manual list missed.

3. **Pattern matching:** URLs and email addresses are detected with regex and replaced.

An allowlist of public entity names (GitHub, AWS, OWASP, etc.) prevents over-anonymization of non-identifying terms.

### Approval gate

Nothing is sent to the Claude API without your explicit approval. The full anonymized payload is displayed in the terminal. You review it and type "yes" to proceed. Anything else cancels the query.

### Encryption at rest

The anonymizer mapping and allowlist can be encrypted on disk using Fernet symmetric encryption with PBKDF2 key derivation (600,000 iterations, SHA256). Plaintext exists only in memory during query execution.

### Database authentication

PostgreSQL requires scram-sha-256 password authentication. The default trust (passwordless) authentication has been replaced.

### Git protection

Two layers prevent accidental commits of sensitive files:

1. `.gitignore` excludes mapping files, transcripts, `.env`, encrypted files, and audit logs
2. A pre-commit hook blocks those same patterns and scans file contents for actual API keys and database passwords

### Automated testing

13 tests verify that every known PII value is stripped, URLs and emails are caught, allowlisted entities are preserved, and round-trip de-anonymization works. If a test fails, identifying information would leak.

### CI/CD security scanning

| Tool | Runs When | Purpose |
|------|----------|---------|
| CodeQL | Every PR + nightly | Static analysis for security vulnerabilities |
| Bandit | Every PR + nightly | Python SAST |
| pip-audit | Every PR + nightly | Dependency vulnerability scanning |
| Ruff | Every PR | Linting |
| Mypy | Pre-commit | Type checking (strict mode) |

### Audit trail

Every query attempt (approved or denied) is logged with a timestamp and chunk count. No question text or content is recorded. The log is local and gitignored.

For full details, see [SECURITY.md](SECURITY.md).

## Stack

| Component | Technology | Runs Where |
|-----------|-----------|------------|
| Transcript parsing | Python | Local |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2) | Local |
| Vector storage | PostgreSQL 17 + pgvector 0.8.2 | Local |
| Anonymization | spaCy NER + manual mapping + regex | Local |
| Encryption | Fernet + PBKDF2 (cryptography library) | Local |
| Query LLM | Claude API (anthropic SDK) | API call, anonymized data only |
| Audit | Local JSONL log | Local |

## Requirements

| Dependency | Version |
|-----------|---------|
| Python | 3.14+ |
| PostgreSQL | 17+ |
| pgvector | 0.8.2+ |

## Project Structure

```
memento/
    .github/
        workflows/        CI, security scan, nightly deep scan
        ISSUE_TEMPLATE/   Bug, feature, ticket templates
        dependabot.yml    Weekly dependency updates
        pull_request_template.md
    src/
        config.py         Configuration and environment loading
        database.py       PostgreSQL and pgvector setup
        parser.py         Transcript file parser and chunking
        embeddings.py     Local embedding generation
        anonymizer.py     PII stripping before API calls
        encryption.py     File encryption at rest
        audit.py          Query audit logging
        query.py          Similarity search, approval gate, Claude API
        ingest.py         Ingestion pipeline orchestration
    tests/
        test_anonymizer.py  PII leak detection test suite
```

## Setup

### PostgreSQL

Install PostgreSQL and pgvector:

```
brew install postgresql@17
brew install pgvector
brew services start postgresql@17
```

Create the database and enable pgvector:

```
psql postgres -c "CREATE DATABASE memento;"
psql memento -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

Set a password (replace the placeholder with a real password):

```
psql postgres -c "ALTER USER your_user WITH PASSWORD 'your_password';"
```

Update pg_hba.conf to require scram-sha-256 authentication and restart PostgreSQL.

### Python Environment

```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

### Configuration

Copy the example environment file and fill in your values:

```
cp .env.example .env
```

Required values:

| Variable | Description |
|----------|-------------|
| ANTHROPIC_API_KEY | Your Claude API key |
| DATABASE_URL | PostgreSQL connection string with password |

### Anonymizer Setup

Create `anonymizer_mapping.json` with your PII mappings:

```json
{
    "Your Name": "[USER]",
    "Company Name": "[COMPANY_A]"
}
```

Create `anonymizer_allowlist.json` with public names to preserve:

```json
["GitHub", "AWS", "Python"]
```

Both files are gitignored and should be encrypted at rest for additional protection.

### Ingest Transcripts

```
python -m src.ingest
```

### Run Tests

```
pytest tests/ -v
```
