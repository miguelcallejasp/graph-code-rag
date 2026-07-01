"""Embeds text via an Ollama server (local or remote).

This is the only place that talks to the embedding model. Batches requests so
ingest isn't one round-trip per chunk. The server is chosen by `ollama_host` in
config: blank = local default, or a URL like http://192.168.0.136:11434 to use
another machine on the network.
"""
from __future__ import annotations

import ollama


class OllamaUnavailable(RuntimeError):
    pass


_clients: dict[str, ollama.Client] = {}


def _normalize(host: str) -> str:
    """Default to localhost; ensure a scheme so the client accepts it."""
    host = (host or "").strip()
    if not host:
        return "http://localhost:11434"
    if not host.startswith(("http://", "https://")):
        host = "http://" + host
    return host


def client(host: str = "") -> ollama.Client:
    url = _normalize(host)
    if url not in _clients:
        _clients[url] = ollama.Client(host=url)
    return _clients[url]


def _check(model: str, host: str) -> None:
    url = _normalize(host)
    try:
        names = {m.get("model", "") for m in client(host).list().get("models", [])}
    except Exception as e:
        raise OllamaUnavailable(
            f"Could not reach Ollama at {url}. Is it running and reachable?\n"
            "  local:  brew install ollama && ollama serve\n"
            "  remote: check the host/port and that the server allows LAN "
            "connections (OLLAMA_HOST=0.0.0.0 on that machine)\n"
            f"(underlying error: {e})"
        ) from e
    # model names come back like "nomic-embed-text:latest"
    if not any(n == model or n.startswith(model + ":") for n in names):
        raise OllamaUnavailable(
            f"Embedding model '{model}' is not pulled on the server at {url}.\n"
            f"On that machine run:  ollama pull {model}"
        )


def embed(texts: list[str], model: str, host: str = "",
          batch_size: int = 64) -> list[list[float]]:
    """Return one vector per input text."""
    c = client(host)
    out: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        out.extend(c.embed(model=model, input=batch)["embeddings"])
    return out


def embed_one(text: str, model: str, host: str = "") -> list[float]:
    return client(host).embed(model=model, input=text)["embeddings"][0]


def ensure_ready(model: str, host: str = "") -> None:
    """Call once at the start of ingest/query for a friendly early error."""
    _check(model, host)
