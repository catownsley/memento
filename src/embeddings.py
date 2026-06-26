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
Local embedding generation using sentence-transformers.

All embedding computation runs on the local machine.
No data is sent to any external service.
"""

import numpy as np
from sentence_transformers import SentenceTransformer

_model_cache: dict[str, SentenceTransformer] = {}


def get_model(model_name: str = "all-MiniLM-L6-v2") -> SentenceTransformer:
    """
    Load and cache the embedding model.
    The model is downloaded on first use and cached locally.
    """
    if model_name not in _model_cache:
        _model_cache[model_name] = SentenceTransformer(model_name)
    return _model_cache[model_name]


def embed_text(text: str, model_name: str = "all-MiniLM-L6-v2") -> np.ndarray:
    """Generate an embedding vector for a single text string."""
    model = get_model(model_name)
    embedding = model.encode(text, convert_to_numpy=True)
    return embedding  # type: ignore[return-value]


def embed_batch(
    texts: list[str], model_name: str = "all-MiniLM-L6-v2"
) -> np.ndarray:
    """
    Generate embedding vectors for a list of text strings.
    More efficient than calling embed_text in a loop.
    """
    model = get_model(model_name)
    embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=True)
    return embeddings  # type: ignore[return-value]
