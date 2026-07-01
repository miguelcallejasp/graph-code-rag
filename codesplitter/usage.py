"""Accumulates LLM token usage and turns it into a dollar estimate.

A single process-wide tracker is updated by every LLM call (see llm.py) so any
command can print running spend. Embeddings are local (Ollama) and free, so they
are not counted here.
"""
from __future__ import annotations

from dataclasses import dataclass

from .config import Config


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0

    def add(self, usage_obj) -> None:
        """Fold in an OpenAI-style usage object from one response."""
        if usage_obj is None:
            return
        self.calls += 1
        self.input_tokens += getattr(usage_obj, "prompt_tokens", 0) or 0
        self.output_tokens += getattr(usage_obj, "completion_tokens", 0) or 0
        details = getattr(usage_obj, "prompt_tokens_details", None)
        if details is not None:
            self.cached_input_tokens += getattr(details, "cached_tokens", 0) or 0

    def cost(self, cfg: Config) -> float:
        uncached = max(0, self.input_tokens - self.cached_input_tokens)
        return (uncached / 1e6 * cfg.price_input_per_mtok
                + self.cached_input_tokens / 1e6 * cfg.price_cached_input_per_mtok
                + self.output_tokens / 1e6 * cfg.price_output_per_mtok)

    def summary(self, cfg: Config) -> str:
        return (f"{self.calls} LLM calls | "
                f"in {self.input_tokens:,} ({self.cached_input_tokens:,} cached), "
                f"out {self.output_tokens:,} tokens | "
                f"est ${self.cost(cfg):.4f}")


# process-wide singleton
USAGE = Usage()
