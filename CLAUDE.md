# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A local-first code RAG tool ("CodeSplitter"). It indexes a set of code repos into a
Chroma vector store, then answers plain-English questions with citations. Despite the
repo name `graph-code-rag`, there is no graph yet — retrieval is pure vector similarity.
The package is `codesplitter/`; `cli.py` is the entry point.

## Commands

```bash
python cli.py status                 # show config, models, resolved repos, chunk count
python cli.py ingest                 # build/update the index (incremental via content hash)
python cli.py ingest --force         # rebuild from scratch (required after embed_model change)
python cli.py describe               # add per-repo LLM project summaries (spends API $)
python cli.py query "how does auth work?"
python cli.py query "..." --repo <name>   # limit retrieval to one repo

tail -f logs/ingest.log              # watch progress from another terminal (or describe/query.log)
```

There is no build step and **no test suite** — this is a small script-driven package.
Setup: `pip install -r requirements.txt`, plus an external Ollama server and a Kimi
(Moonshot) API key in `.env` (`LLM_API_KEY`).

## The three-stage pipeline (the key mental model)

Each stage is powered by a *different* engine — this separation is the core design:

1. **Split** (`chunker.py`) — tree-sitter via llama-index `CodeSplitter` cuts code into
   function/class-sized chunks; prose falls back to `SentenceSplitter`. **No model.**
2. **Embed** (`embedder.py`) — an **external Ollama server** turns chunks into vectors.
   Local (free). This is the *only* place that talks to the embedding model.
3. **Answer** (`llm.py`) — an **OpenAI-compatible LLM** (Kimi/Moonshot) reads retrieved
   chunks and writes the answer. This is the *only* place that costs money.

Data flow: `discovery.iter_files` → `chunker.chunks_for` → `embedder.embed` →
`store` (Chroma). Query: `query.answer` embeds the question, retrieves `top_k` chunks,
builds a context prompt, streams the LLM answer. The output is the `repo_index/` folder
(gitignored, rebuildable) — not a binary.

## Invariants that will silently break retrieval if violated

- **Same `embed_model` at ingest and query time.** Changing it without `ingest --force`
  makes retrieval noise (Chroma fixes vector dimensionality at collection creation;
  `reset_collection` in `store.py` exists precisely for this).
- **Never embed secrets.** `discovery.py` skips `SKIP_FILES` / `SKIP_SUFFIXES` (`.env`,
  keys, credentials). Add to those sets before indexing repos with other sensitive files —
  a vector store is a maximally searchable place to leak a credential.
- **Changing `embed_metadata_prefix` requires `ingest --force`.** File hashes are unchanged
  by a toggle, so a normal re-ingest skips everything and the change never takes effect.

## Config-driven design

Everything is retargeted via `config.yaml` + `.env` — **never edit code to point at new
repos or swap models.** `config.py` loads both into a single `Config` dataclass.
`resolved_repos()`: an explicit `repos:` list wins; otherwise every immediate subdirectory
of `repos_root` is auto-discovered as one repo. To use a different LLM provider, change
only `llm_base_url` + `answer_model` + the key in `.env` (any OpenAI-compatible endpoint).

## Notable implementation details

- **Incremental ingest** (`ingest.py`): each file's SHA-256 is stored in
  `.codesplitter_manifest.json`. Unchanged files are skipped, changed files re-embedded,
  deleted files purged. The manifest is flushed every 50 files so an interrupted run resumes.
- **Chroma IDs** are `"{repo}:{rel_path}:{chunk_index}"`; metadata carries `repo`/`file`/`kind`.
  `delete_file` clears a file's prior chunks before re-adding.
- **`describe.py`** builds an "orientation layer": it feeds the LLM key files + file tree,
  then **chunks the resulting summary by section** before embedding (one vector per section,
  `kind: "project"`) — a single vector for a long summary matches nothing sharply. The full
  doc is also written to `logs/description-<repo>.md` for humans.
- **`llm.py`**: `answer_model` (kimi-k2.6) is a *reasoning* model that spends tokens thinking
  before visible output, so `max_tokens` budgets are deliberately generous — too small starves
  the answer to empty with `finish_reason="length"`.
- **`usage.py`**: a process-wide `USAGE` singleton every LLM call folds token counts into,
  producing the running dollar estimate in logs (rates from `price_*_per_mtok` in config).
  Embeddings are local and not counted.
- **`embed_summary: true`** embeds an LLM-written summary of each chunk instead of raw code —
  better English→code matching but one LLM call per chunk at ingest time (costs money). Off
  by default; the raw code is always what's *stored*, regardless.
