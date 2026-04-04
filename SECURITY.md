# Security

Memento processes private conversation transcripts. Every design decision prioritizes keeping that data on the local machine. This document describes every security control in the project.

## Privacy Architecture

All data processing and storage runs locally. The only external call is to the Claude API at query time, and all data passes through an anonymization layer before it leaves the machine.

| Component | Runs Where | Data Exposure |
|-----------|-----------|---------------|
| Transcript parsing | Local | None |
| Embedding generation | Local | None |
| Vector storage (pgvector) | Local | None |
| Anonymization | Local | None |
| Query to Claude API | External | Anonymized text only |

### What never leaves your machine

| Data | Storage |
|------|---------|
| Raw transcript files (.jsonl) | Local filesystem |
| Vector embeddings | PostgreSQL (local) |
| Anonymizer mapping file | Local filesystem (encrypted at rest) |
| Anonymizer allowlist | Local filesystem (encrypted at rest) |
| Audit log | Local filesystem |
| Database credentials | Local .env file |
| API keys | Local .env file |

### What goes to the Claude API

Retrieved conversation chunks, after passing through the anonymization layer. The anonymization layer strips all identifying information (names, companies, usernames, URLs, email addresses, file paths, dates) and replaces them with bracketed placeholders. The substance of the conversation is preserved because it is not identifying on its own.

Anthropic's API data policy: inputs are deleted after 7 days and are never used for model training.

## Anonymization

### Three layer approach

**Layer 1: Manual mapping.** A local JSON file maps real values to placeholders. Example: "Charlotte" becomes "[USER]", "Empower" becomes "[COMPANY_A]". Replacements are applied longest first to prevent substring collisions (e.g., "charlottesweb-app" is replaced before "charlotte").

**Layer 2: NER (Named Entity Recognition).** A transformers pipeline using dslim/bert-base-NER scans the original text (before manual replacements, to avoid false matches on placeholder text) and catches PER, ORG, and LOC entities that the manual mapping missed. Detected entities are replaced with sequential placeholders. Entities shorter than 2 characters are ignored. Entities that are substrings of allowlisted entries are also ignored (handles cases where the tokenizer splits a word, e.g., "GitH" from "GitHub").

**Layer 3: Pattern matching.** URLs and email addresses are detected with regex and replaced with numbered placeholders.

### Allowlist

A local JSON array of public entity names (GitHub, AWS, OWASP, PostgreSQL, etc.) that should pass through the anonymizer untouched. These names do not identify the user and removing them would degrade query quality.

### Round trip

The anonymization is reversible. After Claude responds, placeholders are swapped back to real values. The mapping for each query exists only in memory during that query.

## Approval Gate

The query pipeline requires explicit user approval before any data is sent to the Claude API. The full anonymized payload (context chunks and question) is displayed in the terminal. The user must type "yes" to proceed. If the user types anything else, the query is cancelled and nothing is sent.

This is the primary privacy control. No automated process can send data to the API without a human reviewing it first.

## Audit Log

Every query attempt is recorded in audit.log (a local JSONL file, gitignored). Each record contains:

| Field | Description |
|-------|-------------|
| timestamp | ISO 8601 UTC |
| action | QUERY_APPROVED or QUERY_DENIED |
| question_length | Character count of the question (not the question itself) |
| chunks_sent | Number of anonymized chunks sent to the API |

The audit log does not contain the question text or any chunk content. It records only metadata so you can verify what happened and when.

## Encryption at Rest

The anonymizer mapping and allowlist files can be encrypted using Fernet symmetric encryption with a key derived via PBKDF2.

| Parameter | Value |
|-----------|-------|
| Algorithm | Fernet (AES-128-CBC + HMAC-SHA256) |
| Key derivation | PBKDF2-HMAC-SHA256 |
| Iterations | 600,000 (NIST recommended minimum) |
| Salt | 16 bytes, randomly generated per file |

When encrypted, the plaintext mapping files are deleted from disk. The plaintext is only reconstructed in memory during query execution and is not written back to disk.

## Database Security

PostgreSQL is configured with scram-sha-256 authentication. The default Homebrew trust authentication (which allows passwordless connections) has been replaced. The database password is stored in the local .env file and in ~/.pgpass (permissions 600).

The database contains conversation chunks and their vector embeddings. It is accessible only from localhost.

## Git Protection

### .gitignore

The following file patterns are excluded from version control:

| Pattern | Reason |
|---------|--------|
| anonymizer_mapping*.json | Contains real names mapped to placeholders |
| anonymizer_allowlist*.json | Indicates which entities are considered public |
| *.enc | Encrypted versions of the above |
| *.jsonl | Conversation transcript files |
| .env, .env.local, .env.*.local | Contains API keys and database passwords |
| audit.log | Contains query metadata |

### Pre-commit hook

A git pre-commit hook provides a second layer of protection beyond .gitignore. It runs automatically on every commit and:

1. Blocks any staged file matching the patterns above (with an explicit exception for .env.example)
2. Scans staged file contents for actual API key values (sk-ant- prefix)
3. Scans staged file contents for database passwords in connection strings

The hook has caught real issues during development, including a placeholder API key that matched the real key format and a documentation example containing a connection string.

## CI/CD Security Scanning

Three GitHub Actions workflows run on every pull request and nightly:

### CI (every PR)

Ruff linting and full pytest suite.

### Security Scan: Quick (every PR)

| Tool | Purpose |
|------|---------|
| CodeQL | Static analysis for Python security vulnerabilities |
| Bandit | Python SAST (Static Application Security Testing) |
| pip-audit | Dependency vulnerability scanning against OSV.dev |

### Security Scan: Deep (nightly at 04:17 UTC)

| Tool | Purpose |
|------|---------|
| CodeQL | Extended security-and-quality query suite |
| Bandit | Medium+ severity threshold, build fails on findings |
| pip-audit | Strict mode, build fails on any vulnerability |

SARIF results from CodeQL and Bandit are uploaded to the GitHub Security tab.

## Pre-commit Hooks

Configured via .pre-commit-config.yaml:

| Hook | Purpose |
|------|---------|
| detect-private-key | Prevents accidental commit of SSH/PGP keys |
| check-merge-conflict | Detects merge conflict markers |
| check-added-large-files | Prevents large binary commits |
| trailing-whitespace | Code formatting |
| end-of-file-fixer | File normalization |
| Black | Code formatter (88 char line length) |
| Ruff | Linter with auto-fix |
| Mypy | Type checker (strict mode) |

## Dependency Management

### Dependabot

Automated weekly updates for Python dependencies and GitHub Actions, with security labels and review assignment.

### Pinned versions

All dependencies in requirements.txt are pinned to exact versions. No wildcard or range specifiers.

## Memory Poisoning Defense

Transcript files are the input to the ingestion pipeline. If a transcript contained malicious content (injected instructions, leaked secrets, corrupted data), that content could end up in the vector database and influence future query results.

The sanitizer module (src/sanitizer.py) runs during ingestion and applies two checks to every chunk before it is stored:

### Chunk validation

| Check | Action |
|-------|--------|
| Empty or whitespace-only content | Chunk is skipped |
| Content exceeds 10,000 characters | Chunk is skipped |
| Content is mostly non-printable (below 80% printable characters) | Chunk is skipped |

### Secret redaction

The sanitizer scans for patterns that match real API keys and tokens. If found, the secret is replaced with `[REDACTED_SECRET]` before storage.

| Pattern | What It Catches |
|---------|----------------|
| sk-ant- followed by 20+ alphanumeric characters | Anthropic API keys |
| sk- followed by 20+ alphanumeric characters | OpenAI API keys |
| AKIA followed by 16 uppercase alphanumeric characters | AWS access keys |
| ghp_ followed by 30+ alphanumeric characters | GitHub personal access tokens |
| xox followed by b/p/s/a and alphanumeric characters | Slack tokens |

### Injection pattern detection

The sanitizer flags text that matches known prompt injection patterns. These are flagged with warnings in the ingestion log but not removed, because conversations may legitimately discuss prompt injection techniques. The patterns include:

| Pattern Category | Examples |
|-----------------|----------|
| Instruction override | "ignore all previous instructions", "disregard previous" |
| Role override | "you are now a", "system: you are" |
| Tag injection | &lt;system&gt;, &lt;instructions&gt;, [SYSTEM], [INST] |

Flagged chunks are stored but the warnings are printed during ingestion so the operator can review them.

## Prompt Injection Defense

Retrieved conversation chunks are inserted into the Claude API prompt as context. A chunk could contain text that resembles instructions to the model ("ignore previous instructions and..."). This is a form of indirect prompt injection.

### Defenses

**Structural separation.** The system prompt, retrieved context, and user question are wrapped in distinct XML tags:

| Section | Tag |
|---------|-----|
| Retrieved conversation data | `<retrieved_conversation_data>` |
| User's question | `<question>` |

**System prompt hardening.** The system prompt explicitly instructs Claude to treat the retrieved conversation data as reference material and to not follow any instructions that appear inside it, even if they claim to override previous instructions or change the model's role.

**Approval gate.** The user sees the full anonymized payload (including retrieved chunks) before it is sent. If a chunk contains suspicious content, the user can reject the query.

These defenses follow the OWASP AI Agent Security Cheat Sheet recommendations for input validation and prompt injection defense. See: https://github.com/OWASP/CheatSheetSeries/blob/master/cheatsheets/AI_Agent_Security_Cheat_Sheet.md

## Automated Testing

Two test suites verify security controls:

### Anonymizer tests (tests/test_anonymizer.py, 13 tests)

| Test Category | What It Verifies |
|---------------|------------------|
| No Leaks | Every mapping entry is replaced, combined PII paragraph has zero leaks, URLs stripped, emails stripped, file paths anonymized |
| Round Trip | Anonymize then de-anonymize returns original text for both simple and complex inputs |
| Allowlist | Public org names and technology names are preserved |
| Edge Cases | Case sensitivity, substring ordering, empty text, URL/email stripping without a mapping |

### Sanitizer tests (tests/test_sanitizer.py, 14 tests)

| Test Category | What It Verifies |
|---------------|------------------|
| Secret Redaction | Anthropic, OpenAI, AWS, GitHub, and Slack tokens are redacted from chunks |
| Injection Detection | Instruction overrides, system tags, and role overrides are flagged |
| Injection Preservation | Flagged content is preserved (not deleted) since it may be legitimate discussion |
| Validation | Empty, oversized, and binary content is rejected |

If any test fails, it means either identifying information would survive anonymization, or malicious content would enter the database unsanitized.

## Threat Model

### What we defend against

| Threat | Control |
|--------|---------|
| PII sent to Claude API | Anonymization layer + approval gate |
| PII committed to GitHub | .gitignore + pre-commit hook + content scanning |
| Mapping file stolen from disk | Encryption at rest (Fernet/PBKDF2) |
| Unauthorized database access | scram-sha-256 password auth |
| Dependency vulnerabilities | pip-audit (PR + nightly), Dependabot |
| Code vulnerabilities | CodeQL, Bandit (PR + nightly) |
| Undetected data exfiltration | Audit log records every API call attempt |
| Accidental secret in code | Pre-commit hook scans file contents |
| Memory poisoning via transcript injection | Chunk sanitization during ingestion, secret redaction |
| Prompt injection via retrieved chunks | XML tag delimiters, system prompt hardening, approval gate |
| Leaked secrets in stored chunks | Regex pattern matching and redaction during ingestion |

### OWASP AI Agent Security coverage

This project's controls map to the following sections of the OWASP AI Agent Security Cheat Sheet:

| OWASP Section | Memento Control |
|--------------|-----------------|
| Tool Security and Least Privilege | Single external tool (Claude API), no shell access, no file write |
| Input Validation and Prompt Injection Defense | Chunk sanitization, XML delimiters, system prompt hardening |
| Memory and Context Security | Single user isolation, chunk validation, secret redaction, encryption at rest |
| Human-in-the-Loop Controls | Approval gate with full payload preview before any API call |
| Output Validation | De-anonymization only uses the query's own mapping |
| Monitoring and Observability | Audit log for all query attempts |
| Data Protection and Privacy | Anonymization, encryption at rest, database auth, gitignore + hooks |

Sections that do not apply: Multi-Agent Security (single agent), Cascading Failures (no agent chain), Denial of Wallet (manual approval prevents unbounded loops).

### What is out of scope

| Threat | Reason |
|--------|--------|
| Full disk encryption | Responsibility of the operating system, not this project |
| Network traffic interception | Claude API uses TLS. Local PostgreSQL does not leave localhost. |
| Physical access to the machine | Out of scope for application-level security |
| Compromise of the Claude API itself | Out of scope. Anthropic's infrastructure security is their responsibility. |
