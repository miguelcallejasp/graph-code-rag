"""LLM client for descriptions (ingest/describe) and answers (query).

Uses an OpenAI-COMPATIBLE endpoint, configured by `llm_base_url` + `answer_model`
in config.yaml and the LLM_API_KEY in .env. Currently pointed at Kimi (Moonshot),
but any OpenAI-compatible provider works by changing those three values.

Note: kimi-k2.6 is a REASONING model. It spends tokens "thinking" (returned in a
separate `reasoning_content` field) before emitting the visible answer, so
max_tokens budgets here are generous — too small and reasoning starves the
output, leaving content empty with finish_reason="length".
"""
from __future__ import annotations

from openai import OpenAI

from .config import Config
from .runlog import get_logger
from .usage import USAGE

_client: OpenAI | None = None


def client(cfg: Config) -> OpenAI:
    global _client
    if _client is None:
        if not cfg.llm_api_key:
            raise RuntimeError(
                "LLM_API_KEY is not set. Copy .env.example to .env and add your "
                "Kimi (Moonshot) API key."
            )
        _client = OpenAI(api_key=cfg.llm_api_key, base_url=cfg.llm_base_url)
    return _client


def _complete(messages: list[dict], cfg: Config, max_tokens: int) -> str:
    resp = client(cfg).chat.completions.create(
        model=cfg.answer_model,
        max_tokens=max_tokens,
        messages=messages,
    )
    USAGE.add(resp.usage)
    choice = resp.choices[0]
    content = choice.message.content or ""
    # A reasoning model can burn the whole token budget "thinking" and stop with
    # finish_reason="length" before emitting any visible content. Surface that
    # instead of silently returning an empty string.
    if not content.strip() and choice.finish_reason == "length":
        get_logger("llm", cfg).warning(
            "Model hit max_tokens (%d) with no visible output "
            "(finish_reason=length) \u2014 reasoning starved the answer. "
            "Increase max_tokens.", max_tokens,
        )
    return content


def summarize(code: str, cfg: Config) -> str:
    return _complete(
        [{"role": "user",
          "content": f"In 2-3 sentences, what does this code do?\n\n{code}"}],
        cfg, max_tokens=1024,
    )


def describe(prompt: str, cfg: Config, max_tokens: int = 2048) -> str:
    return _complete([{"role": "user", "content": prompt}], cfg, max_tokens)


def stream_answer(prompt: str, cfg: Config, max_tokens: int = 4096):
    """Yield answer text incrementally for printing.

    Requests usage in the final chunk so query spend is tracked too; falls back
    gracefully if the provider rejects stream_options.
    """
    kwargs = dict(
        model=cfg.answer_model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
        stream=True,
    )
    try:
        stream = client(cfg).chat.completions.create(
            **kwargs, stream_options={"include_usage": True})
    except Exception:
        stream = client(cfg).chat.completions.create(**kwargs)

    for chunk in stream:
        if getattr(chunk, "usage", None):
            USAGE.add(chunk.usage)
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta
