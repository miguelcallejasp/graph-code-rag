"""Loads config.yaml and .env into a single Config object.

Keeping all knobs in one place is what makes the tool generic: retarget it at a
new set of repos by editing config.yaml, never the code.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

# Project root = the folder that contains config.yaml (one level up from here).
ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"


@dataclass
class Config:
    repos_root: str
    repos: list[dict]
    embed_model: str
    ollama_host: str
    answer_model: str
    llm_base_url: str
    db_dir: str
    collection: str
    chunk_lines: int
    chunk_lines_overlap: int
    max_chars: int
    text_chunk_size: int
    text_chunk_overlap: int
    embed_metadata_prefix: bool
    embed_summary: bool
    top_k: int
    log_dir: str
    price_input_per_mtok: float
    price_cached_input_per_mtok: float
    price_output_per_mtok: float
    llm_api_key: str | None = field(default=None, repr=False)

    @property
    def db_path(self) -> Path:
        """Absolute path to the vector-store folder."""
        p = Path(self.db_dir)
        return p if p.is_absolute() else (ROOT / p)

    @property
    def manifest_path(self) -> Path:
        return ROOT / ".codesplitter_manifest.json"

    @property
    def log_path(self) -> Path:
        p = Path(self.log_dir)
        return p if p.is_absolute() else (ROOT / p)

    def resolved_repos(self) -> list[dict]:
        """Return [{name, path}, ...].

        Explicit `repos` wins. Otherwise auto-discover: every immediate
        subdirectory of repos_root (excluding hidden/this project) is a repo.
        """
        if self.repos:
            return [{"name": r["name"], "path": str(Path(r["path"]).expanduser())}
                    for r in self.repos]

        root = Path(self.repos_root).expanduser()
        if not root.is_dir():
            raise FileNotFoundError(
                f"repos_root does not exist: {root}\n"
                "Edit config.yaml -> repos_root, or fill in the explicit `repos` list."
            )
        discovered = []
        for child in sorted(root.iterdir()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            if child.resolve() == ROOT:        # don't index this project itself
                continue
            discovered.append({"name": child.name, "path": str(child)})
        return discovered


def load_config(path: Path | str = CONFIG_PATH) -> Config:
    load_dotenv(ROOT / ".env")
    with open(path) as f:
        data = yaml.safe_load(f)
    return Config(
        repos_root=data["repos_root"],
        repos=data.get("repos") or [],
        embed_model=data["embed_model"],
        ollama_host=(data.get("ollama_host") or "").strip(),
        llm_base_url=data["llm_base_url"],
        answer_model=data["answer_model"],
        db_dir=data["db_dir"],
        collection=data["collection"],
        chunk_lines=data["chunk_lines"],
        chunk_lines_overlap=data["chunk_lines_overlap"],
        max_chars=data["max_chars"],
        text_chunk_size=data["text_chunk_size"],
        text_chunk_overlap=data["text_chunk_overlap"],
        embed_metadata_prefix=data.get("embed_metadata_prefix", True),
        embed_summary=data["embed_summary"],
        top_k=data["top_k"],
        log_dir=data.get("log_dir", "./logs"),
        price_input_per_mtok=float(data.get("price_input_per_mtok", 0.0)),
        price_cached_input_per_mtok=float(data.get("price_cached_input_per_mtok", 0.0)),
        price_output_per_mtok=float(data.get("price_output_per_mtok", 0.0)),
        llm_api_key=os.getenv("LLM_API_KEY") or os.getenv("MOONSHOT_API_KEY"),
    )
