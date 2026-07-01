# CodeSplitter

A local-first knowledge base over your code repositories. Point it at a folder
of repos and ask questions in plain English — *"how does auth flow through the
gateway?"*, *"where do we touch the Mongo connection string?"* — and get answers
that cite the repo and file they came from.

## What this actually is (no magic)

"CodeSplitter" is **not a model**. The pipeline has three stages, each powered by
a different thing:

| Stage | What it does | Powered by |
|---|---|---|
| **1. Split** | Cut each file into function-sized chunks | `CodeSplitter` — a pure-Python library (tree-sitter). No model. |
| **2. Embed** | Turn each chunk into a vector (list of numbers) | A small model **run by Ollama** (local or on your network) |
| **3. Answer** | Read the retrieved chunks and write the answer | An **OpenAI-compatible LLM** — currently **Kimi (Moonshot)** |

So you install **three things**: access to an Ollama server (a small app), this
Python project, and a Kimi API key.

**The output is not a binary.** It's a folder — `repo_index/` — that holds the
vectors + the original code + metadata. You build it once, then query it many
times. A query prints a text answer to your terminal; it doesn't write a file.

```
your repos ──build──▶ repo_index/ folder ──ask──▶ text answers
```

## One-time setup

```bash
# 1. Ollama — the local embedding engine
brew install ollama
ollama serve &                 # leave running (or use the menu-bar app)
ollama pull nomic-embed-text   # the embedding model, ~300MB

# 2. Python dependencies
cd CodeSplitter
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. Kimi (Moonshot) API key (only the answer LLM needs one; Ollama is keyless)
cp .env.example .env           # then edit .env and paste your LLM_API_KEY
```

## Point it at your repos

Edit `config.yaml`:

```yaml
repos_root: "/Users/you/Documents/Engineering/Seagull"
```

By default every immediate subfolder of `repos_root` is treated as one repo. To
pick specific ones or rename them, fill in the explicit `repos:` list instead
(see the comments in `config.yaml`). This is the only file you edit to retarget
the tool at a different set of repositories.

Check what it sees before building:

```bash
python cli.py status
```

## Use it

```bash
python cli.py ingest                  # build the index (slow first run, incremental after)
python cli.py describe                # optional: add LLM project summaries (uses Kimi API)
python cli.py query "how does auth work?"
python cli.py query "where is the db connection configured?" --repo track-and-trace
```

Re-running `ingest` only re-embeds files that changed (tracked by content hash
in `.codesplitter_manifest.json`), so keep it cheap to run often — wire it to a
git hook later if you like. Use `--force` to rebuild from scratch.

## Logs, progress & cost

Every command writes to both the console and a file under `logs/`, so you can
watch progress from another terminal:

```bash
tail -f logs/ingest.log      # or describe.log / query.log
```

Each `ingest` line shows position, percent, elapsed, and **ETA**:

```
[123/975 12.6%] elapsed 1m00s eta 6m55s | riot-core-bridges/src/Foo.java (4 chunks)
```

**Cost.** Embeddings run on your Ollama server and are **free** — a normal
`ingest` (with `embed_summary: false`) spends $0. Money is only spent on LLM
calls: `describe`, every `query`, and `ingest` *if* `embed_summary: true`. Those
commands log a running token + dollar estimate:

```
2 LLM calls | in 12,400 (8,000 cached), out 3,100 tokens | est $0.0166
```

The dollar figure uses the `price_*_per_mtok` values in `config.yaml`
(kimi-k2.6 rates by default) — adjust them if your plan differs. It's an
estimate for visibility, not your actual invoice.

## Key rules

- **Same embedding model at ingest and query time.** Changing `embed_model`
  means you must `ingest --force`, or retrieval silently turns to noise.
- **Never embed secrets.** `.env`, key files, and credential files are skipped
  in `discovery.py`. Add to `SKIP_FILES` / `SKIP_SUFFIXES` if your repos have
  other sensitive files.

## Project layout

```
config.yaml              all settings — edit this to retarget
cli.py                   entry point (ingest / describe / query / status)
codesplitter/
  config.py              loads config.yaml + .env, discovers repos
  discovery.py           which files to index; what to skip
  chunker.py             CodeSplitter (AST) + prose fallback
  embedder.py            Ollama embedding calls
  store.py               Chroma vector store wrapper
  llm.py                 OpenAI-compatible LLM client (Kimi: summaries + answers)
  usage.py               token + dollar-cost tracking
  runlog.py              file/console logging, progress + ETA
  ingest.py              build/update the index (incremental)
  describe.py            orientation layer (project summaries)
  query.py               retrieve + answer
repo_index/              the built index (gitignored, rebuildable)
logs/                    per-command logs (gitignored): ingest/describe/query
```

## Where this can grow (later)

The shape stays the same as you harden it:

- **Per-folder / per-function summaries** for finer orientation (more API cost).
- **Hybrid search** (vector + BM25 keyword) so exact identifiers never get lost.
- **Reranking** top-20 → top-8 with a cross-encoder for sharper context.
- **Scale the store** past ~100k chunks: move to pgvector or Qdrant.
- **A code graph** (imports/calls) once repos clearly reference each other.

You picked a setup that grows up rather than one you throw away.
