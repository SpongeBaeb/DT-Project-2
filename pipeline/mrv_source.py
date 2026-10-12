"""팀 MRV 전처리 파이프라인(vendor/mrv_pipeline)의 결과를 SHIP_YEAR 로 읽어 오는 어댑터 (data.source: mrv_pipeline).

팀 파이프라인은 규칙(1~11단계: 정제, 제원 통합, CII 등급, 연료 그룹)과 MRV 사이트 다운로드·제원 크롤링을 이미 갖고 있다.
규칙을 다시 쓰지 않고 그 결과 파일(`mrv_merged.parquet`)만 받아 이 프레임워크의 열 이름·약속으로 바꾼다.
→ 규칙이 바뀌어도 vendor/mrv_pipeline 폴더만 새 판으로 바꿔 끼우면 된다 (원본 코드는 고치지 않는다).

패키지 이름(`pipeline`, `tests`)이 이 프레임워크와 같아서 팀 파이프라인은 같은 프로세스에서 import 하지 않고
별도 프로세스(`python -m pipeline.run`, 작업 폴더 = vendor/mrv_pipeline)로 실행한다.

입력 파일 고르는 순서
  1. 환경변수 MRV_MERGED_PATH (이미 만들어 둔 mrv_merged.parquet/csv 를 그대로 쓸 때)
  2. config data.merged_path
  3. 둘 다 없으면 팀 파이프라인을 실행해 data.mrv_root/data/processed/mrv_merged.parquet 를 만든다
     (config data.team_pipeline: mode, fetch, crawl). fetch: true 이면 MRV 사이트에서 새 판을 내려받는다.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from shared.config import ROOT, path
from shared.manifest import file_hash

if TYPE_CHECKING:  # run.py 와 서로 import 하지 않도록 형식 검사 때만 읽는다
    from pipeline.run import RawFile, Report

log = logging.getLogger("pipeline")
VENDOR = ROOT / "vendor" / "mrv_pipeline"

# 팀 통합 파일 열 → SHIP_YEAR 열
RENAME = {
    "company_name": "company", "co2_berth_t": "berth_co2_t", "co2_between_eu_t": "co2_intra_eu_t", "co2_ets_t": "ets_co2_t",
    "time_at_sea_h": "sea_hours", "co2_per_nm": "co2_per_nm_kg", "built_year": "build_year", "gross_tonnage": "gt",
    "tech_eff_value": "eedi", "tech_eff_kind": "eedi_kind", "cii_hsc_proxy": "hsc_proxy",
}
KEEP = [
    "imo", "year", "name", "ship_type", "company", "ice_class", "fuel_t", "co2_t", "berth_co2_t", "co2_intra_eu_t", "ets_co2_t",
    "sea_hours", "co2_per_nm_kg", "distance_nm", "cargo_t", "dwt", "gt", "length_m", "build_year", "eedi", "eedi_kind",
    "cii_ship_type", "cii_capacity", "hsc_proxy", "fuel_group", "source_version",
    "mm_a", "mm_b", "mm_c", "co2_recovered", "co2_parts_bad", "cii_type_changed", "cii_ratio_2026basis", "cii_rating",
    "cii_rating_2026basis", "avg_load", "avg_load_basis", "avg_load_invalid",
]
BOOL_COLS = ["hsc_proxy", "mm_a", "mm_b", "mm_c", "co2_recovered", "co2_parts_bad", "cii_type_changed", "avg_load_invalid"]
REQUIRED = [
    "imo", "year", "ship_type", "co2_t", "co2_berth_t", "co2_per_nm", "time_at_sea_h", "dwt", "built_year", "mrv_file_version",
]


def run_team_pipeline(root: Path, *, mode: str = "version", fetch: bool = True, crawl: bool = False) -> Path:
    """팀 파이프라인을 실행하고 통합 파일 위치를 돌려준다. 종료 코드 2(사람 확인 필요)·1(오류)이면 예외."""
    cmd = [sys.executable, "-m", "pipeline.run", "--mode", mode, "--root", str(root)]
    if not fetch:
        cmd.append("--no-fetch")
    if crawl:
        cmd.append("--crawl")
    log.info("팀 MRV 파이프라인 실행: %s", " ".join(cmd[2:]))
    # CRAWLER_INPUT_TXT="" : 팀 파이프라인은 기본으로 작성자 PC 의 c:\DT Project\ 에도 '제원 없는 IMO 목록'을 덮어쓴다 → 프로젝트 밖은 건드리지 않게 끈다
    done = subprocess.run(cmd, cwd=VENDOR, env={**os.environ, "PYTHONIOENCODING": "utf-8", "CRAWLER_INPUT_TXT": ""})
    if done.returncode == 2:
        raise RuntimeError(f"팀 파이프라인이 사람 확인을 요청했습니다 → {root / 'reports' / 'pipeline' / 'latest_summary.md'} 를 읽고 조치하세요")
    if done.returncode != 0:
        raise RuntimeError(f"팀 파이프라인 오류 (종료 코드 {done.returncode})")
    return root / "data" / "processed" / "mrv_merged.parquet"


def locate_merged(cfg: dict) -> Path:
    d = cfg["data"]
    given = os.environ.get("MRV_MERGED_PATH") or d.get("merged_path")
    if given:
        p = path(given)
        if not p.exists():
            raise FileNotFoundError(f"통합 파일이 없습니다: {p}")
        return p
    t = d.get("team_pipeline", {})
    return run_team_pipeline(path(d.get("mrv_root", "data/mrv_pipeline")), mode=t.get("mode", "version"),
                             fetch=t.get("fetch", False), crawl=t.get("crawl", False))


def read_merged(p: Path) -> pd.DataFrame:
    return pd.read_parquet(p) if p.suffix == ".parquet" else pd.read_csv(p, encoding="utf-8-sig", low_memory=False)


def to_ship_year_input(df: pd.DataFrame, colmap: dict, ship_types: list[str], report: "Report", *, min_gt: float | None = None) -> pd.DataFrame:
    """팀 통합 파일 → SHIP_YEAR 의 원본·제원 열 (파생 열은 shared/preprocess.derive 가 만든다)."""
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise KeyError(f"팀 통합 파일에 필요한 열이 없습니다: {missing}")
    clash = [t for s_, t in RENAME.items() if t in df.columns and s_ in df.columns]     # 예: 팀 파일에 co2_ets_t 와 ets_co2_t(추정 포함)가 둘 다 있음 → 보고값(앞 것)만 쓴다
    d = df.drop(columns=clash).rename(columns=RENAME)  # 팀 파일의 ship_type 은 이미 정리된 영문 선종명 (ship_type_raw 는 원본 표기)
    d["imo"] = pd.to_numeric(d["imo"], errors="coerce")
    d = d.dropna(subset=["imo"])
    d["imo"] = d["imo"].astype("int64")
    d["year"] = d["year"].astype("int64")
    report.add("read merged", len(d), years=sorted(d["year"].unique().tolist()), ships=int(d["imo"].nunique()))

    std = d["ship_type"].map(colmap["ship_types"])
    unknown = d.loc[std.isna(), "ship_type"].value_counts().to_dict()
    d["ship_type"] = std
    d = d[d["ship_type"].isin(ship_types)]
    report.add("harmonize", len(d), dropped_unknown_type=unknown)

    if min_gt:
        before = len(d)
        d = d[d["gt"] >= min_gt]
        report.add("gt_filter", len(d), min_gt=min_gt, dropped=before - len(d))

    # 적재량은 톤 단위로 확인된 값만 (기준이 부피·인원 등이거나 유효하지 않으면 비움)
    if "avg_load" in d.columns:
        basis = d["avg_load_basis"] if "avg_load_basis" in d.columns else pd.Series(None, index=d.index, dtype=object)
        bad = d["avg_load_invalid"].fillna(False).astype(bool) if "avg_load_invalid" in d.columns else pd.Series(False, index=d.index)
        d["cargo_t"] = d["avg_load"].where(basis.eq("mass") & ~bad)
    for c in BOOL_COLS:                                # 빈칸은 False ("전년이 없어 선종 변경 여부를 모름" 등)
        d[c] = d[c].fillna(False).astype(str).isin(["True", "1", "1.0"]) if c in d.columns else False
    d["source_version"] = d["year"].astype(str) + ":" + d["mrv_file_version"].astype(str).str.lstrip("v")

    before = len(d)
    d = d.drop_duplicates(["imo", "year"], keep="last")
    report.add("dedupe", len(d), duplicates=before - len(d))
    for c in KEEP:
        if c not in d.columns:
            d[c] = np.nan
    return d[KEEP].reset_index(drop=True)


def load(cfg: dict, colmap: dict, report: "Report") -> tuple[list["RawFile"], pd.DataFrame]:
    from pipeline.run import RawFile  # 지연 import: run.py 가 이 모듈을 먼저 import 한다

    p = locate_merged(cfg)
    raw = read_merged(p)
    d = to_ship_year_input(raw, colmap, cfg["data"]["ship_types"], report, min_gt=cfg["data"].get("min_gross_tonnage"))
    sha = file_hash(p)
    ver = raw.assign(year=raw["year"].astype(int)).groupby("year")["mrv_file_version"].first().astype(str).str.lstrip("v")
    files = [RawFile(p, int(y), v, sha) for y, v in ver.items()]
    return files, d
