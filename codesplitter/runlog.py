"""Logging that writes to BOTH the console and a per-command file.

    logs/ingest.log     <- python cli.py ingest
    logs/describe.log   <- python cli.py describe
    logs/query.log      <- python cli.py query ...

Tail any of them from another terminal:  tail -f logs/ingest.log
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from .config import Config


def get_logger(name: str, cfg: Config) -> logging.Logger:
    cfg.log_path.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(f"codesplitter.{name}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if logger.handlers:           # already configured this process
        return logger

    fmt = logging.Formatter("%(asctime)s  %(message)s", datefmt="%H:%M:%S")

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)

    fileh = logging.FileHandler(cfg.log_path / f"{name}.log", encoding="utf-8")
    fileh.setFormatter(logging.Formatter(
        "%(asctime)s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    logger.addHandler(fileh)
    return logger


def fmt_duration(seconds: float) -> str:
    seconds = int(max(0, seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m{s:02d}s"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"


class Progress:
    """Tracks done/total and produces an ETA string from observed rate."""

    def __init__(self, total: int):
        self.total = total
        self.done = 0
        self.start = time.monotonic()

    def tick(self, n: int = 1) -> None:
        self.done += n

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.start

    @property
    def eta(self) -> float:
        if self.done == 0:
            return 0.0
        rate = self.elapsed / self.done           # seconds per item
        return rate * (self.total - self.done)

    def line(self, suffix: str = "") -> str:
        pct = (100 * self.done / self.total) if self.total else 100
        base = (f"[{self.done}/{self.total} {pct:4.1f}%] "
                f"elapsed {fmt_duration(self.elapsed)} "
                f"eta {fmt_duration(self.eta)}")
        return f"{base} | {suffix}" if suffix else base
