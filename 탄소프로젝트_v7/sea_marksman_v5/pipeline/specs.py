"""선박 제원 수집 (VesselFinder 공개 페이지) — 빠진 배만, 캐시해서 재사용.

[담당: 차희성] fetch_one() 을 구현한다. 나머지(캐시·요청 간격·실패 목록)는 이미 되어 있다.
수집 전 이용 약관·robots.txt 를 확인하고, 허용되지 않으면 수집하지 않는다 (기획서 4-1).
"""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd

SPEC_COLS = ["imo", "dwt", "gt", "length_m", "build_year", "ice_class", "eedi"]


def fetch_one(imo: int) -> dict | None:
    """IMO 하나의 제원 dict(SPEC_COLS) 또는 못 찾으면 None. 네트워크 오류는 예외로 던진다."""
    raise NotImplementedError("제원 수집기는 아직 구현 전입니다 (pipeline/specs.py fetch_one)")


def load_cache(cache_file: Path) -> pd.DataFrame:
    if cache_file.exists():
        return pd.read_parquet(cache_file)
    return pd.DataFrame(columns=SPEC_COLS)


def fill_missing(imos: list[int], cache_file: Path, *, delay_s: float = 2.0, limit: int | None = None) -> tuple[pd.DataFrame, list[int]]:
    """캐시에 없는 IMO만 수집해 캐시에 더한다. (전체 제원 표, 실패한 IMO 목록) 을 돌려준다."""
    cache = load_cache(cache_file)
    todo = [i for i in imos if i not in set(cache["imo"])][:limit]
    got, failed = [], []
    for i in todo:
        try:
            rec = fetch_one(i)
        except NotImplementedError:
            failed.extend(todo)
            break
        except Exception:  # noqa: BLE001 — 한 척 실패로 전체를 멈추지 않는다
            rec = None
        (got.append(rec) if rec else failed.append(i))
        time.sleep(delay_s)
    if got:
        cache = pd.concat([cache, pd.DataFrame(got)[SPEC_COLS]], ignore_index=True)
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache.to_parquet(cache_file, index=False)
    return cache, failed
