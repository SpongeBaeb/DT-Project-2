"""설정 읽기와 경로. 모든 경로는 프로젝트 루트 기준."""
from __future__ import annotations

import importlib
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "default.yaml"


def load_yaml(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@lru_cache(maxsize=8)
def _load_config_cached(path: str) -> dict[str, Any]:
    return load_yaml(path)


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    return _load_config_cached(str(path or DEFAULT_CONFIG))


def path(rel: str | Path) -> Path:
    p = Path(rel)
    return p if p.is_absolute() else ROOT / p


def import_object(spec: str):
    """'패키지.모듈:이름' 문자열로 클래스·함수를 불러온다 (설정에서 부품을 바꿔 끼우는 용도)."""
    module, _, attr = spec.partition(":")
    if not attr:
        raise ValueError(f"'모듈:이름' 형식이어야 합니다: {spec}")
    return getattr(importlib.import_module(module), attr)
