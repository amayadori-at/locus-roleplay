from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


class EmbeddingError(Exception):
    """Raised when embedding configuration is missing or API call fails."""


class EmbeddingConfig:
    """Read embedding settings from environment variables.

    Required env vars:
      LOCUS_EMBEDDING_MODEL       - embedding model ID; if empty, embedding is disabled
      LOCUS_EMBEDDING_ENDPOINT_ENV - name of env var holding the base URL (default: LLM_BASE_URL)
      LOCUS_EMBEDDING_API_KEY_ENV  - name of env var holding the API key  (default: LLM_API_KEY)

    API key is never read directly from LOCUS_EMBEDDING_API_KEY_ENV itself; the value of that var
    is treated as the name of another env var, following the same indirection used by model profiles.
    This keeps secrets out of the embedding config and out of the frontend.
    """

    def __init__(self) -> None:
        self.model: str = os.environ.get("LOCUS_EMBEDDING_MODEL", "").strip()
        endpoint_env: str = os.environ.get("LOCUS_EMBEDDING_ENDPOINT_ENV", "LLM_BASE_URL").strip()
        api_key_env: str = os.environ.get("LOCUS_EMBEDDING_API_KEY_ENV", "LLM_API_KEY").strip()
        self.base_url: str = os.environ.get(endpoint_env, "").rstrip("/")
        self.api_key: str = os.environ.get(api_key_env, "")

    @property
    def enabled(self) -> bool:
        return bool(self.model and self.base_url)

    def as_safe_dict(self) -> dict[str, Any]:
        """Return config metadata suitable for logging/API responses (no secrets)."""
        return {
            "enabled": self.enabled,
            "model": self.model or None,
        }

    def __repr__(self) -> str:
        return f"EmbeddingConfig(model={self.model!r}, enabled={self.enabled})"


def get_embedding_config() -> EmbeddingConfig:
    return EmbeddingConfig()


_BATCH_SIZE = 96


def embed_texts(texts: list[str], config: EmbeddingConfig | None = None) -> list[list[float]]:
    """Return one embedding vector per text using the configured OpenAI-compatible API.

    Sends texts in batches of up to _BATCH_SIZE to stay within provider limits.
    Raises EmbeddingError if embedding is not configured or the API call fails.
    """
    if config is None:
        config = get_embedding_config()
    if not config.enabled:
        raise EmbeddingError("Embedding is not configured (LOCUS_EMBEDDING_MODEL or endpoint missing)")
    if not texts:
        return []

    results: list[list[float]] = []
    for batch_start in range(0, len(texts), _BATCH_SIZE):
        batch = texts[batch_start : batch_start + _BATCH_SIZE]
        results.extend(_embed_batch(batch, config))
    return results


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors. Returns 0.0 on zero or mismatched vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _embed_batch(texts: list[str], config: EmbeddingConfig) -> list[list[float]]:
    url = f"{config.base_url}/embeddings"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"

    payload = json.dumps({"model": config.model, "input": texts}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data: Any = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:400]
        raise EmbeddingError(f"Embedding API HTTP {exc.code}: {body}") from exc
    except OSError as exc:
        raise EmbeddingError(f"Embedding API request failed: {exc}") from exc

    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        raise EmbeddingError("Unexpected embedding API response: missing 'data' list")

    items: list[Any] = data["data"]
    if len(items) != len(texts):
        raise EmbeddingError(
            f"Embedding API returned {len(items)} vectors for {len(texts)} inputs"
        )

    embeddings: list[list[float]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict) or not isinstance(item.get("embedding"), list):
            raise EmbeddingError(f"Malformed embedding item at index {index}")
        embeddings.append([float(v) for v in item["embedding"]])
    return embeddings
