"""Ask a question: embed it, retrieve nearest chunks, let the LLM answer."""
from __future__ import annotations

from .config import Config, load_config
from .embedder import embed_one, ensure_ready
from .llm import stream_answer
from .runlog import get_logger
from .store import get_collection
from .usage import USAGE


def answer(question: str, cfg: Config | None = None, *, repo: str | None = None) -> None:
    cfg = cfg or load_config()
    ensure_ready(cfg.embed_model, cfg.ollama_host)
    coll = get_collection(cfg)
    if coll.count() == 0:
        print("Index is empty. Run `python cli.py ingest` first.")
        return

    qvec = embed_one(question, cfg.embed_model, cfg.ollama_host)
    where = {"repo": repo} if repo else None
    res = coll.query(query_embeddings=[qvec], n_results=cfg.top_k, where=where)

    docs = res["documents"][0]
    metas = res["metadatas"][0]
    if not docs:
        print("No matching context found.")
        return

    context = "\n\n".join(
        f"# {m['repo']}/{m.get('file', m.get('kind'))}\n{doc}"
        for doc, m in zip(docs, metas)
    )
    prompt = (
        "Answer using ONLY the context below. Cite the repo and file you rely "
        "on. If the answer isn't in the context, say so plainly.\n\n"
        f"CONTEXT:\n{context}\n\nQUESTION: {question}"
    )

    for piece in stream_answer(prompt, cfg):
        print(piece, end="", flush=True)
    print()

    log = get_logger("query", cfg)
    sources = ", ".join(f"{m['repo']}/{m.get('file', m.get('kind'))}" for m in metas)
    log.info("Q: %s", question)
    log.info("retrieved %d chunks: %s", len(docs), sources)
    log.info("spend: %s", USAGE.summary(cfg))


if __name__ == "__main__":
    import sys
    answer(" ".join(sys.argv[1:]) or "What do these repositories do?")
