"""LLM answers from the company knowledge base. Any OpenAI-compatible API (Groq, Gemini).

Providers are tried in order: if one fails or hits the free limit, the next one answers.
"""

import logging
import os
import re
from dataclasses import dataclass

import aiohttp

LEAD_TAG = "[LEAD]"

SYSTEM_PROMPT = """You are the customer support assistant of the company described below.
Rules:
- Answer ONLY with facts from the knowledge base. Never invent prices, services or dates.
- If the answer is not in the knowledge base, say you don't have this information
  and offer to leave a request so a manager can reply.
- Reply in the customer's language (Russian, Kazakh or English). Be short: 1-4 sentences.
- Plain text only, no markdown, no tables.
- If the customer wants to book, order, get a call back, or you could not answer,
  add {tag} at the very end of the reply.

Knowledge base:
{knowledge}"""


@dataclass
class Provider:
    name: str
    url: str
    key: str
    model: str


class AIError(Exception):
    pass


def providers_from_env() -> list[Provider]:
    result = []
    if key := os.getenv("GROQ_API_KEY"):
        url = "https://api.groq.com/openai/v1/chat/completions"
        result.append(Provider("groq", url, key, os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")))
        if fallback := os.getenv("GROQ_FALLBACK_MODEL", "openai/gpt-oss-120b"):
            result.append(Provider("groq-fallback", url, key, fallback))
    if key := os.getenv("GEMINI_API_KEY"):
        url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        result.append(Provider("gemini", url, key, os.getenv("GEMINI_MODEL", "gemini-2.5-flash")))
    return result


def build_messages(knowledge: str, history: list[dict], question: str) -> list[dict]:
    system = SYSTEM_PROMPT.format(tag=LEAD_TAG, knowledge=knowledge)
    return [{"role": "system", "content": system}, *history, {"role": "user", "content": question}]


def parse_reply(text: str) -> tuple[str, bool]:
    """Remove <think> blocks and the lead tag. Returns (clean text, wants_lead)."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    wants_lead = LEAD_TAG in text
    return text.replace(LEAD_TAG, "").strip(), wants_lead


async def ask(
    session: aiohttp.ClientSession, providers: list[Provider], messages: list[dict]
) -> str:
    for p in providers:
        body = {"model": p.model, "messages": messages, "max_tokens": 500, "temperature": 0.2}
        if "gpt-oss" in p.model:
            body["reasoning_effort"] = "low"
        try:
            async with session.post(
                p.url,
                json=body,
                headers={"Authorization": f"Bearer {p.key}"},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    raise AIError(f"HTTP {resp.status}: {(await resp.text())[:200]}")
                data = await resp.json()
                content = data["choices"][0]["message"]["content"]
                if content and content.strip():
                    return content
                raise AIError("empty answer")
        except Exception as e:
            logging.warning("provider %s (%s) failed: %s", p.name, p.model, e)
    raise AIError("all providers failed")
