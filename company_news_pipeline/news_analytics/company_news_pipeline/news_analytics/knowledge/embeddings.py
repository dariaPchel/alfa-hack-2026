"""RouterAI embeddings with E5 prefixes, usage accounting and Wi-Fi egress."""

from __future__ import annotations

import math
import os
from typing import Sequence

import requests
from dotenv import load_dotenv

from ..budget import BudgetGate, EMBEDDING_MODEL_ALIAS
from ..db import Database
from ..wifi_egress import ensure_routerai_wifi_routes


load_dotenv()

ROUTERAI_EMBEDDINGS_URL = "https://routerai.ru/api/v1/embeddings"
EMBEDDING_DIMENSIONS = 1024
MAX_INPUTS_PER_REQUEST = 32
MAX_INPUT_CHARS = 1200
_PRICE_PER_MILLION_TOKENS_RUB = float(os.getenv("ROUTERAI_EMBEDDING_RUB_PER_1M_TOKENS", "1.10"))


def _prepare_session() -> requests.Session:
    api_key = os.getenv("ROUTERAI_API_KEY")
    if not api_key:
        raise RuntimeError("ROUTERAI_API_KEY is required for RouterAI embeddings")
    session = requests.Session()
    session.trust_env = False
    try:
        proxy_url = os.getenv("ROUTERAI_EGRESS_PROXY")
        if proxy_url:
            session.proxies.update({"https": proxy_url})
        elif os.name == "nt":
            ensure_routerai_wifi_routes("routerai.ru")
        else:
            raise RuntimeError("ROUTERAI_EGRESS_PROXY is required outside Windows for Wi-Fi-only RouterAI egress")
    except Exception:
        session.close()
        raise
    session.headers.update({
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    return session


def _embed(texts: Sequence[str], prefix: str) -> list[list[float]]:
    if not texts:
        return []
    session = _prepare_session()
    vectors: list[list[float]] = []
    budget = BudgetGate(Database())
    try:
        for start in range(0, len(texts), MAX_INPUTS_PER_REQUEST):
            batch = [f"{prefix}: {text[:MAX_INPUT_CHARS]}" for text in texts[start:start + MAX_INPUTS_PER_REQUEST]]
            estimated_tokens = max(1, sum(max(1, len(text) // 3) for text in batch))
            reservation = budget.reserve_call("Chroma embedding", EMBEDDING_MODEL_ALIAS, estimated_tokens)
            if not reservation.allowed or not reservation.request_id:
                raise RuntimeError(reservation.reason or "RouterAI embedding budget denied the request")
            try:
                response = session.post(
                    ROUTERAI_EMBEDDINGS_URL,
                    json={"model": EMBEDDING_MODEL_ALIAS, "input": batch, "encoding_format": "float"},
                    timeout=(10, 90),
                )
                response.raise_for_status()
                payload = response.json()
                items = payload.get("data")
                if not isinstance(items, list) or len(items) != len(batch):
                    raise RuntimeError("RouterAI returned an incomplete embeddings response")
                items = sorted(items, key=lambda item: int(item.get("index", 0)))
                batch_vectors = []
                for item in items:
                    vector = item.get("embedding")
                    if not isinstance(vector, list) or len(vector) != EMBEDDING_DIMENSIONS:
                        raise RuntimeError("RouterAI embedding dimension does not match the configured Chroma model")
                    numeric = [float(value) for value in vector]
                    norm = math.sqrt(sum(value * value for value in numeric))
                    if not math.isfinite(norm) or norm == 0:
                        raise RuntimeError("RouterAI returned an invalid zero or non-finite embedding")
                    batch_vectors.append([value / norm for value in numeric])
                usage = payload.get("usage") or {}
                actual_tokens = int(usage.get("prompt_tokens") or estimated_tokens)
                actual_cost = actual_tokens * _PRICE_PER_MILLION_TOKENS_RUB / 1_000_000
                budget.record_usage(reservation.request_id, actual_tokens=actual_tokens,
                                    actual_cost_rub=actual_cost)
                vectors.extend(batch_vectors)
            except Exception:
                budget.record_usage(reservation.request_id, failed=True)
                raise
    except requests.Timeout as exc:
        raise RuntimeError("RouterAI embedding request timed out") from exc
    except requests.RequestException as exc:
        raise RuntimeError("RouterAI embedding provider is unavailable") from exc
    finally:
        session.close()
    return vectors


def embed_passages(texts: Sequence[str]) -> list[list[float]]:
    """Embed stored chunks through RouterAI; source text leaves this host for inference."""
    return _embed(texts, "passage")


def embed_queries(texts: Sequence[str]) -> list[list[float]]:
    """Embed retrieval queries through the same model and vector space as indexed chunks."""
    return _embed(texts, "query")
