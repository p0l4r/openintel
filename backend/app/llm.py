"""One provider adapter for any OpenAI-compatible endpoint.

Ollama, vLLM, LM Studio, llama.cpp server (open source) and OpenAI/Anthropic-compatible
gateways (paid) all speak this protocol, so switching is just env vars.
"""
import json
import re

import httpx

from .config import settings


async def generate_json(system: str, user: str) -> dict:
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(
            f"{settings.llm_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            json={
                "model": settings.llm_model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise ValueError("Model did not return JSON")
        return json.loads(m.group(0))
