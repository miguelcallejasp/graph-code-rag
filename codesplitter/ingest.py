"""Build (or incrementally update) the vector index.

Detail layer: every repo's code/text, chunked and embedded.
Incremental: each file's content is hashed into a manifest; unchanged files are
skipped on re-runs, changed files are re-embedded, deleted files are purged.
"""
from __future__ import annotations

import hashlib
import json
import os

from .config import Config, load_config
from .chunker import chunks_for
from .discovery import iter_files
from .embedder import embed, ensure_ready
from .llm import summarize
from .runlog import Progress, fmt_duration, get_logger
from .store import delete_file, get_collection, reset_collection
from .usage import USAGE


def _location_prefix(repo: str, rel: str) -> str:
    """A short location header prepended to each chunk before embedding.

    Surfaces the repo, top-level module, and file path so questions mentioning
    those names land near the right code. Not stored — only embedded.
    """
    parts = rel.replace("\\", "/").split("/")
    module = parts[0] if len(parts) > 1 else "(root)"
    return f"// repo: {repo} | module: {module} | file: {rel}\n"


def _hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def _load_manifest(cfg: Config) -> dict:
    if cfg.manifest_path.exists():
        return json.loads(cfg.manifest_path.read_text())
    return {}


def _save_manifest(cfg: Config, manifest: dict) -> None:
    cfg.manifest_path.write_text(json.dumps(manifest, indent=2))


def ingest(cfg: Config | None = None, *, force: bool = False) -> None:
    cfg = cfg or load_config()
    log = get_logger("ingest", cfg)
    ensure_ready(cfg.embed_model, cfg.ollama_host)

    # --force starts clean: fresh collection (handles embed-model/dim changes)
    # and an empty manifest so every file is re-embedded.
    coll = reset_collection(cfg) if force else get_collection(cfg)
    manifest = {} if force else _load_manifest(cfg)
    new_manifest: dict = {}
    repos = cfg.resolved_repos()
    if not repos:
        log.info("No repositories found. Check config.yaml.")
        return

    # Pre-scan so we know the total up front (enables % and ETA).
    log.info("Scanning %d repo(s) for files...", len(repos))
    files: list[tuple[str, str, str, str]] = []   # (repo, abs_path, ext, kind)
    for repo in repos:
        for path, ext, kind in iter_files(repo["path"]):
            files.append((repo["name"], path, ext, kind))
    roots = {r["name"]: r["path"] for r in repos}

    log.info("Found %d files. Embedding model '%s' on %s%s",
             len(files), cfg.embed_model,
             cfg.ollama_host or "localhost", " [SUMMARY MODE]" if cfg.embed_summary else "")
    log.info("Logging to %s", cfg.log_path / "ingest.log")

    prog = Progress(len(files))
    total_chunks = added = skipped = empty = 0

    for name, path, ext, kind in files:
        rel = os.path.relpath(path, roots[name])
        key = f"{name}:{rel}"
        digest = _hash(path)
        new_manifest[key] = digest
        prog.tick()

        if manifest.get(key) == digest:        # unchanged since last run
            skipped += 1
            if prog.done % 100 == 0:
                log.info(prog.line(f"...{skipped} unchanged so far"))
            continue

        delete_file(coll, name, rel)           # clear prior chunks, then re-add
        pieces = chunks_for(path, ext, kind, cfg)
        if not pieces:
            empty += 1
            continue

        bodies = [summarize(c, cfg) for c in pieces] if cfg.embed_summary else pieces
        if cfg.embed_metadata_prefix:
            header = _location_prefix(name, rel)
            to_embed = [header + b for b in bodies]
        else:
            to_embed = bodies
        vectors = embed(to_embed, cfg.embed_model, cfg.ollama_host)
        coll.add(
            ids=[f"{name}:{rel}:{i}" for i in range(len(pieces))],
            embeddings=vectors,
            documents=pieces,                  # always store the real code
            metadatas=[{"repo": name, "file": rel, "kind": kind} for _ in pieces],
        )
        total_chunks += len(pieces)
        added += 1

        suffix = f"{name}/{rel} ({len(pieces)} chunks)"
        if cfg.embed_summary:                  # only then are we spending money
            suffix += f" | {USAGE.summary(cfg)}"
        log.info(prog.line(suffix))

        # Flush periodically so an interrupted run resumes instead of restarting.
        if added % 50 == 0:
            _save_manifest(cfg, new_manifest)

    # purge files that disappeared from disk
    for stale_key in set(manifest) - set(new_manifest):
        repo_name, rel = stale_key.split(":", 1)
        delete_file(coll, repo_name, rel)

    _save_manifest(cfg, new_manifest)
    log.info("DONE in %s. %d files indexed, %d unchanged, %d empty, "
             "%d new chunks. Collection holds %d.",
             fmt_duration(prog.elapsed),
             added, skipped, empty, total_chunks, coll.count())
    if cfg.embed_summary:
        log.info("LLM spend: %s", USAGE.summary(cfg))


if __name__ == "__main__":
    ingest()
