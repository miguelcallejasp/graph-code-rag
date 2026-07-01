"""Orientation layer: LLM-written project descriptions embedded into the store.

A code chunk answers "what does this function do." A project description answers
"how is auth structured / how does a message flow / what are the modules" — the
map, not the territory.

Two things make this useful for *retrieval* (not just for humans):
  1. The LLM is given real context — key files (READMEs, build/module files) and
     a generous file tree — not just a truncated path list.
  2. The resulting document is CHUNKED by section before embedding. One long
     summary embedded as a single vector is a muddy average that matches nothing
     sharply; per-section vectors each match their own kind of question.
"""
from __future__ import annotations

import os
import pathlib

from llama_index.core import Document
from llama_index.core.node_parser import SentenceSplitter

from .config import Config, load_config
from .discovery import SKIP_DIRS
from .embedder import embed, ensure_ready
from .llm import describe as llm_describe
from .runlog import Progress, get_logger
from .store import get_collection
from .usage import USAGE

# Files that orient an LLM about a project, by basename (lowercased) or suffix.
ORIENTATION_NAMES = {
    "readme", "readme.md", "readme.txt", "settings.gradle", "build.gradle",
    "gradle.properties", "pom.xml", "package.json", "go.mod", "cargo.toml",
    "pyproject.toml", "requirements.txt", "dockerfile", "docker-compose.yml",
    "docker-compose.yaml", "makefile", "configuration.yml",
}
PER_KEY_FILE_CHARS = 4000      # truncate each key file
SUMMARY_CHUNK_CHARS = 1200     # size of each embedded section vector


def _tree(root: str, max_lines: int = 500, per_dir: int = 40) -> str:
    out: list[str] = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for f in sorted(files)[:per_dir]:
            out.append(os.path.relpath(os.path.join(dirpath, f), root))
            if len(out) >= max_lines:
                return "\n".join(out)
    return "\n".join(out)


def _modules(root: str) -> list[str]:
    """Immediate subdirectories — for a multi-module repo, the top-level units."""
    return sorted(
        d.name for d in pathlib.Path(root).iterdir()
        if d.is_dir() and d.name not in SKIP_DIRS and not d.name.startswith(".")
    )


def _key_files(root: str) -> str:
    """Concatenate orientation files (root + one level deep), each truncated."""
    blocks: list[str] = []
    rootp = pathlib.Path(root)
    for dirpath, dirs, files in os.walk(root):
        depth = len(pathlib.Path(dirpath).relative_to(rootp).parts)
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        if depth > 1:                      # root and one level down only
            dirs[:] = []
            continue
        for f in files:
            base = f.lower()
            if base in ORIENTATION_NAMES or base.startswith("readme"):
                full = os.path.join(dirpath, f)
                try:
                    text = pathlib.Path(full).read_text(errors="ignore")[:PER_KEY_FILE_CHARS]
                except OSError:
                    continue
                rel = os.path.relpath(full, root)
                blocks.append(f"=== {rel} ===\n{text}")
    return "\n\n".join(blocks)


def _context(root: str) -> str:
    return (
        f"## Top-level modules / directories\n{', '.join(_modules(root)) or '(none)'}\n\n"
        f"## Key files (contents, truncated)\n{_key_files(root) or '(none found)'}\n\n"
        f"## File tree (sampled)\n{_tree(root)}"
    )


PROMPT_TEMPLATE = """\
You are writing developer documentation for the repository "{name}" so that an
engineer who has never seen it can understand and navigate it, and so that a
search system can retrieve the right section for a given question.

Use ONLY the context provided below (key files, module list, file tree). Be
concrete and specific — name actual modules, files, classes, frameworks, and
config keys you can see. When something is uncertain, say so briefly rather than
inventing it. Do not pad.

Write GitHub-flavored Markdown with these sections, each under a `##` heading.
Keep each section self-contained (it may be retrieved on its own):

## Overview
What the project is and the problem it solves, in 2-4 sentences.

## Core functionality
The main capabilities/features, as a bulleted list. For each, one line on what
it does.

## Architecture & modules
The top-level modules/components and the responsibility of each. State how they
relate (who calls/depends on whom).

## Implementation details
Languages, frameworks, build system, key libraries, data stores, messaging, and
external services/integrations — whatever is evident from the context.

## Workflows & data flow
Trace 1-3 important end-to-end flows (e.g. how an inbound message/request is
received, processed, and emitted). Reference the modules/files involved.

## Conditions, configuration & constraints
Runtime conditions, important environment variables / config keys, deployment
assumptions, and notable limitations or preconditions.

## Architecture diagram
A Mermaid `flowchart` (```mermaid fenced```) showing the main components and the
direction of data/control flow.

=== CONTEXT FOR {name} ===
{context}
"""


def _chunk_summary(summary: str) -> list[str]:
    splitter = SentenceSplitter(chunk_size=SUMMARY_CHUNK_CHARS, chunk_overlap=120)
    return [n.text for n in splitter.get_nodes_from_documents([Document(text=summary)])]


def describe_repos(cfg: Config | None = None) -> None:
    cfg = cfg or load_config()
    log = get_logger("describe", cfg)
    ensure_ready(cfg.embed_model, cfg.ollama_host)
    coll = get_collection(cfg)
    repos = cfg.resolved_repos()

    log.info("Describing %d repo(s) with '%s'. Logging to %s",
             len(repos), cfg.answer_model, cfg.log_path / "describe.log")
    prog = Progress(len(repos))

    for repo in repos:
        name, root = repo["name"], repo["path"]
        prompt = PROMPT_TEMPLATE.format(name=name, context=_context(root))
        summary = llm_describe(prompt, cfg, max_tokens=6000)

        # Save the full doc as a single artifact for humans...
        out_dir = cfg.log_path
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"description-{name}.md").write_text(summary, encoding="utf-8")

        # ...and embed it as per-section vectors for retrieval.
        pieces = _chunk_summary(summary)
        vectors = embed(
            [f"Project overview of {name}:\n{p}" for p in pieces],  # light grounding
            cfg.embed_model, cfg.ollama_host,
        )
        coll.delete(where={"$and": [{"repo": name}, {"kind": "project"}]})
        coll.add(
            ids=[f"{name}:__project__:{i}" for i in range(len(pieces))],
            embeddings=vectors,
            documents=pieces,
            metadatas=[{"repo": name, "file": "(project description)",
                        "kind": "project"} for _ in pieces],
        )
        prog.tick()
        log.info(prog.line(
            f"described {name}: {len(pieces)} section chunks "
            f"(full doc -> {out_dir / f'description-{name}.md'}) | {USAGE.summary(cfg)}"))

    log.info("Orientation layer updated. Total LLM spend: %s", USAGE.summary(cfg))


if __name__ == "__main__":
    describe_repos()
