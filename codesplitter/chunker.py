"""Turns a file into chunks.

Code files -> CodeSplitter (tree-sitter): each chunk is a whole function/class,
nothing cut mid-idea. Prose -> SentenceSplitter. If tree-sitter lacks a grammar
or the file won't parse, we fall back to the sentence splitter so ingest never
dies on one odd file.
"""
from __future__ import annotations

import pathlib

from llama_index.core import Document
from llama_index.core.node_parser import CodeSplitter, SentenceSplitter

from .config import Config
from .discovery import LANG_BY_EXT


def chunks_for(path: str, ext: str, kind: str, cfg: Config) -> list[str]:
    text = pathlib.Path(path).read_text(errors="ignore")
    if not text.strip():
        return []
    doc = Document(text=text)

    if kind == "code":
        try:
            splitter = CodeSplitter(
                language=LANG_BY_EXT[ext],
                chunk_lines=cfg.chunk_lines,
                chunk_lines_overlap=cfg.chunk_lines_overlap,
                max_chars=cfg.max_chars,
            )
            return [n.text for n in splitter.get_nodes_from_documents([doc])]
        except Exception:
            pass  # fall through to sentence splitting

    splitter = SentenceSplitter(
        chunk_size=cfg.text_chunk_size,
        chunk_overlap=cfg.text_chunk_overlap,
    )
    return [n.text for n in splitter.get_nodes_from_documents([doc])]
