#!/usr/bin/env python3
"""CodeSplitter command line.

    python cli.py ingest            build / update the index
    python cli.py ingest --force    rebuild everything from scratch
    python cli.py describe          add LLM project summaries (needs API key)
    python cli.py query "..."       ask a question
    python cli.py query "..." --repo track-and-trace   limit to one repo
    python cli.py status            show what's configured and indexed
"""
from __future__ import annotations

import argparse

from codesplitter.config import load_config


def cmd_ingest(args):
    from codesplitter.ingest import ingest
    ingest(force=args.force)


def cmd_describe(args):
    from codesplitter.describe import describe_repos
    describe_repos()


def cmd_query(args):
    from codesplitter.query import answer
    answer(" ".join(args.question), repo=args.repo)


def cmd_status(args):
    cfg = load_config()
    print(f"embed model : {cfg.embed_model}")
    print(f"ollama host : {cfg.ollama_host or 'http://localhost:11434 (local default)'}")
    print(f"answer model: {cfg.answer_model}  (via {cfg.llm_base_url})")
    print(f"index dir   : {cfg.db_path}")
    print(f"API key set : {bool(cfg.llm_api_key)}")
    try:
        repos = cfg.resolved_repos()
        print(f"repos ({len(repos)}):")
        for r in repos:
            print(f"  - {r['name']}  ({r['path']})")
    except FileNotFoundError as e:
        print(e)
    try:
        from codesplitter.store import get_collection
        print(f"chunks indexed: {get_collection(cfg).count()}")
    except Exception as e:
        print(f"chunks indexed: (store not built yet — {e})")


def main():
    p = argparse.ArgumentParser(prog="codesplitter")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("ingest", help="build/update the index")
    pi.add_argument("--force", action="store_true", help="rebuild from scratch")
    pi.set_defaults(func=cmd_ingest)

    pd = sub.add_parser("describe", help="add LLM project summaries")
    pd.set_defaults(func=cmd_describe)

    pq = sub.add_parser("query", help="ask a question")
    pq.add_argument("question", nargs="+")
    pq.add_argument("--repo", default=None, help="limit to one repo by name")
    pq.set_defaults(func=cmd_query)

    ps = sub.add_parser("status", help="show config + index state")
    ps.set_defaults(func=cmd_status)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
