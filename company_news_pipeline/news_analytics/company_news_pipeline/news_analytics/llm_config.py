"""Single-provider RouterAI configuration with Wi-Fi route enforcement."""

from __future__ import annotations

import os

from dotenv import load_dotenv

from .budget import MODEL_ALIAS
from .wifi_egress import ensure_routerai_wifi_routes


BASE_URL = "https://routerai.ru/api/v1"
load_dotenv()


def build_autogen_llm_config() -> dict:
    api_key = os.getenv("ROUTERAI_API_KEY")
    if not api_key:
        raise RuntimeError("ROUTERAI_API_KEY is required for analysis")
    proxy_url = os.getenv("ROUTERAI_EGRESS_PROXY")
    model_config = {
            "api_type": "openai",
            "model": MODEL_ALIAS,
            "api_key": api_key,
            "base_url": BASE_URL,
            "temperature": 0.2,
            "max_tokens": 4096,
            "timeout": 45,
        }
    if proxy_url:
        try:
            import httpx
            model_config["http_client"] = httpx.Client(proxy=proxy_url, timeout=45, trust_env=False)
        except Exception as exc:
            raise RuntimeError("Could not configure the required RouterAI Wi-Fi proxy") from exc
    else:
        ensure_routerai_wifi_routes("routerai.ru")
    return {
        "config_list": [model_config],
        "cache": None,
    }
