# Copyright (C) 2026 Charlotte Townsley
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""
Configuration loading for Memento.

All configuration is read from environment variables.
The .env file is loaded automatically if present.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def get_config() -> dict:  # type: ignore[type-arg]
    """Return the full configuration dictionary from environment variables."""
    return {
        "database_url": os.getenv("DATABASE_URL", ""),
        "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY", ""),
        "transcript_dir": os.path.expanduser(
            os.getenv(
                "TRANSCRIPT_DIR", "~/.claude/projects/-Users-ct-Python/"
            )
        ),
        "embedding_model": os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2"),
        "claude_model": os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6"),
        "retrieval_limit": int(os.getenv("RETRIEVAL_LIMIT", "10")),
        "anonymizer_mapping": os.getenv(
            "ANONYMIZER_MAPPING", "anonymizer_mapping.json"
        ),
        "anonymizer_allowlist": os.getenv(
            "ANONYMIZER_ALLOWLIST", "anonymizer_allowlist.json"
        ),
    }


def validate_config(config: dict) -> list[str]:  # type: ignore[type-arg]
    """
    Check that required configuration values are present.
    Returns a list of warnings. An empty list means all checks passed.
    """
    warnings = []

    if not config["anthropic_api_key"]:
        warnings.append("ANTHROPIC_API_KEY is not set. Query pipeline will not work.")

    if not config["database_url"]:
        warnings.append("DATABASE_URL is not set. No database connection available.")
    elif "localhost/memento" in config["database_url"] and "@" not in config["database_url"]:
        warnings.append(
            "DATABASE_URL appears to use passwordless auth. "
            "Set a password in the connection string."
        )

    transcript_path = Path(config["transcript_dir"])
    if not transcript_path.exists():
        warnings.append(
            f"TRANSCRIPT_DIR does not exist: {config['transcript_dir']}"
        )

    return warnings
