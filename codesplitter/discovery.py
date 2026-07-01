"""Walks a repo and yields the files worth indexing.

Two jobs: skip noise (build dirs, vendored deps) and never embed secrets.
"""
from __future__ import annotations

import os
import pathlib

# ext -> tree-sitter language name understood by CodeSplitter
LANG_BY_EXT = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "tsx", ".go": "go", ".java": "java",
    ".rb": "ruby", ".rs": "rust", ".c": "c", ".h": "c", ".cpp": "cpp",
    ".cc": "cpp", ".cs": "c_sharp", ".php": "php", ".swift": "swift",
    ".kt": "kotlin", ".scala": "scala", ".sql": "sql", ".sh": "bash",
}

# Prose / config we index with a plain sentence splitter instead of an AST.
# Includes Java/Gradle build + config files (build.gradle, *.properties, XML
# configs like logback/spring). JSON is intentionally excluded — in this repo
# it's mostly test fixtures and data dumps that would bloat the index.
TEXT_EXT = {".md", ".mdx", ".txt", ".yaml", ".yml", ".toml", ".ini", ".cfg",
            ".gradle", ".properties", ".xml"}

# Directories never worth indexing.
SKIP_DIRS = {
    ".git", ".svn", ".hg", "node_modules", "dist", "build", "out",
    "__pycache__", ".venv", "venv", ".mypy_cache", ".pytest_cache",
    "target", "vendor", ".next", ".turbo", "coverage", ".idea", ".vscode",
}

# Files that must NEVER be embedded — a vector store is the most searchable
# place on earth to accidentally leak a credential.
SKIP_FILES = {".env", ".env.local", ".env.production", "secrets.yaml",
              "secrets.yml", "credentials.json", "id_rsa"}
SKIP_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".keystore"}

MAX_FILE_BYTES = 1_000_000   # skip giant generated/minified files


def iter_files(root: str):
    """Yield (abs_path, ext, kind) for each indexable file.

    kind is "code" or "text".
    """
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if name in SKIP_FILES:
                continue
            ext = pathlib.Path(name).suffix.lower()
            if ext in SKIP_SUFFIXES:
                continue
            full = os.path.join(dirpath, name)
            if ext in LANG_BY_EXT:
                kind = "code"
            elif ext in TEXT_EXT:
                kind = "text"
            else:
                continue
            try:
                if os.path.getsize(full) > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            yield full, ext, kind
