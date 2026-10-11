"""영수증(manifest): 모든 산출물에 '어떤 데이터·코드·설정으로 만들었나'를 남긴다 (기획서 4-3, 7-5①)."""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any

import pandas as pd

from shared.config import ROOT

TRACKED_PACKAGES = ("numpy", "pandas", "scikit-learn", "lightgbm", "statsmodels", "pyarrow", "fastapi", "pydantic")


def file_hash(path: str | Path, n: int = 12) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:n]


def frame_hash(df: pd.DataFrame, n: int = 12) -> str:
    """표 내용 해시 (열 순서·행 순서 고정 후). 같은 내용이면 저장 형식과 관계없이 같은 값."""
    d = df.sort_index(axis=1)
    keys = [c for c in ("imo", "year") if c in d.columns]
    if keys:
        d = d.sort_values(keys, kind="mergesort")
    h = hashlib.sha256(pd.util.hash_pandas_object(d.reset_index(drop=True), index=False).values.tobytes())
    h.update(",".join(map(str, d.columns)).encode())
    return h.hexdigest()[:n]


def code_version() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=5)
        if out.returncode == 0:
            dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, timeout=5).stdout.strip()
            return out.stdout.strip() + ("-dirty" if dirty else "")
    except (OSError, subprocess.SubprocessError):
        pass
    return "no-git"


def environment() -> dict[str, str]:
    env = {"python": platform.python_version()}
    for p in TRACKED_PACKAGES:
        try:
            env[p] = metadata.version(p)
        except metadata.PackageNotFoundError:
            pass
    return env


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_manifest(path: str | Path, **fields: Any) -> dict[str, Any]:
    m = {"created_at": now_iso(), "code_version": code_version(), "environment": environment(), **fields}
    Path(path).write_text(json.dumps(m, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return m


def read_manifest(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
