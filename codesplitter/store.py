"""Thin wrapper over the Chroma vector store (the repo_index/ folder)."""
from __future__ import annotations

import chromadb

from .config import Config


def get_collection(cfg: Config):
    client = chromadb.PersistentClient(path=str(cfg.db_path))
    # cosine distance is the right default for normalized text embeddings
    return client.get_or_create_collection(
        cfg.collection, metadata={"hnsw:space": "cosine"}
    )


def reset_collection(cfg: Config):
    """Drop and recreate the collection. Needed when the embedding model (and
    thus the vector dimensionality) changes — Chroma fixes dimensionality at
    creation, so old + new vectors can't coexist."""
    client = chromadb.PersistentClient(path=str(cfg.db_path))
    try:
        client.delete_collection(cfg.collection)
    except Exception:
        pass
    return client.get_or_create_collection(
        cfg.collection, metadata={"hnsw:space": "cosine"}
    )


def delete_repo(coll, repo: str) -> None:
    coll.delete(where={"repo": repo})


def delete_file(coll, repo: str, file: str) -> None:
    coll.delete(where={"$and": [{"repo": repo}, {"file": file}]})
