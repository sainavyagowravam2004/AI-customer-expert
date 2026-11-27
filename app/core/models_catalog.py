import math
import httpx
from app.core.config import settings

MODELS_14 = [
    {"id": "claude-opus-5-5", "name": "Claude Opus 5.5", "provider": "claude", "in_per_m": 4.00, "out_per_m": 20.00, "job": "Improve skills, write lessons, default judge"},
    {"id": "claude-sonnet-5-5", "name": "Claude Sonnet 5.5", "provider": "claude", "in_per_m": 2.00, "out_per_m": 10.00, "job": "Main writer: support & consultant replies"},
    {"id": "claude-haiku-5-5", "name": "Claude Haiku 5.5", "provider": "claude", "in_per_m": 0.10, "out_per_m": 0.50, "job": "Tag job, find facts, short replies (<=100k tokens)"},
    {"id": "gemini-3.8-flash", "name": "Gemini 3.8 Flash", "provider": "gemini", "in_per_m": 0.75, "out_per_m": 3.75, "job": "Writer, read screenshots"},
    {"id": "gemini-3-flash", "name": "Gemini 3 Flash", "provider": "gemini", "in_per_m": 0.50, "out_per_m": 3.00, "job": "Cheaper writer, read screenshots"},
    {"id": "gemini-2.5-flash-lite", "name": "Gemini 2.5 Flash-Lite", "provider": "gemini", "in_per_m": 0.10, "out_per_m": 0.40, "job": "Tag job, find facts"},
    {"id": "nvidia/nemotron-3-ultra-550b-a55b:free", "name": "Nemotron 3 Ultra 550B", "provider": "openrouter", "in_per_m": 0.0, "out_per_m": 0.0, "job": "Zero-cost writer & second-opinion judge"},
    {"id": "nvidia/nemotron-3.5-super-vl:free", "name": "Nemotron 3.5 Super VL", "provider": "openrouter", "in_per_m": 0.0, "out_per_m": 0.0, "job": "Zero-cost screenshot reader"},
    {"id": "nvidia/nemotron-3.5-lightning:free", "name": "Nemotron 3.5 Lightning", "provider": "openrouter", "in_per_m": 0.0, "out_per_m": 0.0, "job": "Zero-cost job tagger"},
    {"id": "google/gemma-4-31b-it:free", "name": "Gemma 4 31B", "provider": "openrouter", "in_per_m": 0.0, "out_per_m": 0.0, "job": "Zero-cost writer"},
    {"id": "qwen/qwen3.8-max-0902", "name": "Qwen 3.8 Max", "provider": "openrouter", "in_per_m": 2.00, "out_per_m": 6.00, "job": "Support & consultant writing"},
    {"id": "qwen/qwen3.7-flash", "provider": "openrouter", "in_per_m": 0.03, "out_per_m": 0.13, "job": "Low-cost job tagger (<=32k tokens)"},
    {"id": "gemma4:e4b", "name": "gemma4:e4b (Local)", "provider": "ollama", "in_per_m": 0.0, "out_per_m": 0.0, "job": "Offline replies, screenshots, private data"},
    {"id": "qwen3.5:4b", "name": "qwen3.5:4b (Local)", "provider": "ollama", "in_per_m": 0.0, "out_per_m": 0.0, "job": "Offline job tagging & fact finding"},
]

MODEL_MAP = {m["id"]: m for m in MODELS_14}

def estimate_tokens(text_val: str) -> int:
    return max(1, math.ceil(len(text_val) / 4))

def compute_cost_usd(model_id: str, tokens_in: int, tokens_out: int) -> float:
    m = MODEL_MAP.get(model_id, {"in_per_m": 0.0, "out_per_m": 0.0})
    in_rate = 0.50 if (model_id == "claude-haiku-5-5" and tokens_in > 100_000) else m["in_per_m"]
    return round((tokens_in * in_rate + tokens_out * m["out_per_m"]) / 1_000_000, 6)

async def call_model_router(
    model_id: str,
    system_prompt: str,
    user_prompt: str,
    api_keys: dict[str, str] | None = None,
    local_only: bool = False,
) -> tuple[str, str, int, int, float]:
    api_keys = api_keys or {}
    tokens_in = estimate_tokens(system_prompt + user_prompt)
    selected = model_id

    if local_only and selected not in ("gemma4:e4b", "qwen3.5:4b"):
        selected = "gemma4:e4b" if tokens_in > 400 else "qwen3.5:4b"
    if selected == "claude-haiku-5-5" and tokens_in > 100_000:
        selected = "claude-sonnet-5-5"

    info = MODEL_MAP.get(selected, MODEL_MAP["qwen3.5:4b"])
    provider = info["provider"]
    reply = ""

    if provider == "claude" and api_keys.get("claude"):
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                r = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": api_keys["claude"], "anthropic-version": "2023-06-01", "content-type": "application/json"},
                    json={"model": selected, "max_tokens": 800, "system": system_prompt, "messages": [{"role": "user", "content": user_prompt}]},
                )
                if r.status_code == 200:
                    reply = r.json()["content"][0]["text"]
        except Exception:
            pass
    elif provider == "openrouter" and api_keys.get("openrouter"):
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                r = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_keys['openrouter']}", "content-type": "application/json"},
                    json={"model": selected, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]},
                )
                if r.status_code == 200:
                    reply = r.json()["choices"][0]["message"]["content"]
        except Exception:
            pass
    elif provider == "gemini" and api_keys.get("gemini"):
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                r = await client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{selected}:generateContent?key={api_keys['gemini']}",
                    json={"contents": [{"parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]}]},
                )
                if r.status_code == 200:
                    reply = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception:
            pass

    if not reply:
        ollama_model = selected if provider == "ollama" else "qwen3.5:4b"
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                r = await client.post(
                    f"{settings.ollama_base_url.rstrip('/')}/api/chat",
                    json={"model": ollama_model, "stream": False, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]},
                )
                if r.status_code == 200:
                    reply = r.json().get("message", {}).get("content", "")
                elif ollama_model != "gemma4:e4b":
                    r2 = await client.post(
                        f"{settings.ollama_base_url.rstrip('/')}/api/chat",
                        json={"model": "gemma4:e4b", "stream": False, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]},
                    )
                    if r2.status_code == 200:
                        reply = r2.json().get("message", {}).get("content", "")
                        selected = "gemma4:e4b"
        except Exception as exc:
            reply = f"[Offline/Fallback] Based on company knowledge: {user_prompt[:240]} ({exc})"

    tokens_out = estimate_tokens(reply)
    cost = compute_cost_usd(selected, tokens_in, tokens_out)
    return reply, selected, tokens_in, tokens_out, cost