"""데이터 파이프라인 (4-3절): ① 내려받기 → ② 열 맞추기 → ③ 제원 결합 → ④ 파생 → ⑤ 스냅샷.

결과: data/snapshots/ship_year.parquet (약속 SHIP_YEAR) + ship_year.manifest.json (영수증)
[담당: 차희성] 실제 MRV 는 download_mrv() 와 specs.fetch_one() 을 채우면 된다. 나머지 단계는 공통.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from contracts.tables import SHIP_YEAR
from pipeline import mrv_source, sample, specs
from shared.config import load_yaml, path
from shared.manifest import file_hash, frame_hash, write_manifest
from shared.preprocess import derive, ensure_schema_columns

log = logging.getLogger("pipeline")


@dataclass
class RawFile:
    path: Path
    year: int
    version: str
    sha: str


@dataclass
class Report:
    """단계마다 몇 행이 왜 빠졌는지 (영수증에 기록 → 발표 '데이터 품질' 근거)."""
    steps: list[dict[str, Any]] = field(default_factory=list)

    def add(self, step: str, rows: int, **detail: Any) -> None:
        self.steps.append({"step": step, "rows": rows, **detail})
        log.info("%-10s %7d행 %s", step, rows, detail or "")


# ① 내려받기 ─────────────────────────────────────────────────────────────
def download(cfg: dict) -> list[RawFile]:
    src = cfg["data"]["source"]
    raw_dir = path(cfg["data"]["raw_dir"]) / src
    if src == "sample":
        if not (raw_dir / "VERSION").exists():
            sample.generate(raw_dir, cfg["data"]["years"])
        version = (raw_dir / "VERSION").read_text(encoding="utf-8").strip()
        return [RawFile(p, int(p.stem.split("_")[1]), version, file_hash(p)) for p in sorted(raw_dir.glob("mrv_*.csv"))]
    if src == "mrv":
        return download_mrv(raw_dir, cfg["data"]["years"])
    raise ValueError(f"알 수 없는 data.source: {src}")


def download_mrv(raw_dir: Path, years: list[int]) -> list[RawFile]:
    """[차희성] THETIS-MRV 에서 연도별 최신 판을 확인·다운로드. 이미 같은 판이 있으면 건너뜀.

    지금은 raw_dir 에 사람이 넣어 둔 파일(mrv_{연도}_v{판}.xlsx)을 읽는다.
    """
    files = []
    for y in years:
        found = sorted(raw_dir.glob(f"mrv_{y}_v*.xlsx")) + sorted(raw_dir.glob(f"mrv_{y}_v*.csv"))
        if not found:
            raise FileNotFoundError(f"{raw_dir} 에 {y}년 파일(mrv_{y}_v<판>.xlsx)이 없습니다")
        p = found[-1]
        files.append(RawFile(p, y, p.stem.split("_v")[-1], file_hash(p)))
    return files


# ② 열 맞추기 ────────────────────────────────────────────────────────────
def harmonize(files: list[RawFile], colmap: dict, ship_types: list[str], report: Report) -> pd.DataFrame:
    frames = []
    for f in files:
        opts = {**colmap["read_options"]["default"], **colmap["read_options"].get(f.year, {})}
        if f.path.suffix == ".csv":
            raw = pd.read_csv(f.path, header=opts["header_row"])
        else:
            raw = pd.read_excel(f.path, sheet_name=opts["sheet"], header=opts["header_row"])
        rename = {}
        for std, aliases in colmap["columns"].items():
            hit = next((a for a in aliases if a in raw.columns), None)
            if hit:
                rename[hit] = std
        d = raw[list(rename)].rename(columns=rename)
        d["year"] = f.year if "year" not in d.columns else d["year"]
        d["source_version"] = f"{f.year}:{f.version}"
        frames.append(d)
        unused = [c for c in raw.columns if c not in rename]
        report.add(f"read {f.year}", len(d), mapped=len(rename), unmapped=len(unused))

    df = pd.concat(frames, ignore_index=True)
    df["ship_type"] = df["ship_type_raw"].map(colmap["ship_types"])
    unknown = df.loc[df["ship_type"].isna(), "ship_type_raw"].value_counts().to_dict()
    df = df[df["ship_type"].isin(ship_types)].drop(columns="ship_type_raw")
    report.add("harmonize", len(df), dropped_unknown_type=unknown)

    df["imo"] = pd.to_numeric(df["imo"], errors="coerce")
    df = df.dropna(subset=["imo"])
    df["imo"] = df["imo"].astype("int64")
    df["year"] = df["year"].astype("int64")
    before = len(df)
    df = df.drop_duplicates(["imo", "year"], keep="last")
    report.add("dedupe", len(df), duplicates=before - len(df))
    return df


# ③ 제원 결합 + 회사·옛 이름 ────────────────────────────────────────────
def enrich(df: pd.DataFrame, cfg: dict, report: Report) -> pd.DataFrame:
    src = cfg["data"]["source"]
    if src == "sample":
        spec = pd.read_csv(path(cfg["data"]["raw_dir"]) / src / "specs.csv")
    else:
        spec, failed = specs.fill_missing(sorted(df["imo"].unique()), path(cfg["data"]["cache_dir"]) / "specs.parquet")
        report.add("specs", len(spec), failed=len(failed))
    out = df.merge(spec[specs.SPEC_COLS], on="imo", how="left")
    matched = out["dwt"].notna().groupby(out["imo"]).first().mean()
    report.add("enrich", len(out), spec_match_ratio=round(float(matched), 4))
    return add_company_history(out)


def add_company_history(out: pd.DataFrame) -> pd.DataFrame:
    # 회사: 2024년 이후 값만 있음 → 같은 IMO 의 가장 최근 값을 과거 연도에 연결 ("최근 기준")
    latest_co = out.sort_values("year").dropna(subset=["company"]).groupby("imo")["company"].last()
    out["company"] = out["company"].fillna(out["imo"].map(latest_co))

    # 옛 이름: 그해보다 앞선 연도들의 다른 이름
    names = out.sort_values("year")[["imo", "year", "name"]]
    former = {}
    for imo, g in names.groupby("imo"):
        seen: list[str] = []
        for y, n in zip(g["year"], g["name"]):
            former[(imo, y)] = " | ".join(x for x in seen if x != n) or None
            if isinstance(n, str) and n not in seen:
                seen.append(n)
    out["former_names"] = [former.get((i, y)) for i, y in zip(out["imo"], out["year"])]
    return out


# ④ 파생 + 정리 ──────────────────────────────────────────────────────────
HARD_RULES = {
    "dwt_missing": lambda d: d["dwt"].isna(),
    "build_year_missing": lambda d: d["build_year"].isna(),
    "co2_nonpositive": lambda d: ~(d["co2_t"] > 0),
    "distance_unknown": lambda d: ~(d["co2_per_nm_kg"] > 0),
    "sea_hours_nonpositive": lambda d: ~(d["sea_hours"] > 0),
    "berth_gt_total": lambda d: d["berth_co2_t"] > d["co2_t"],
    "sea_co2_nonpositive": lambda d: ~(d["co2_t"] - d["berth_co2_t"].fillna(0) > 0),
}


def clean_and_derive(df: pd.DataFrame, report: Report) -> pd.DataFrame:
    """계산 자체가 불가능한 행만 버린다. 이상하지만 계산 가능한 행은 남기고 착시 신호로 표시한다."""
    d = df.copy()
    d["berth_co2_t"] = d["berth_co2_t"].fillna(0.0)
    drop = pd.Series(False, index=d.index)
    reasons = {}
    for name, rule in HARD_RULES.items():
        hit = rule(d) & ~drop
        reasons[name] = int(hit.sum())
        drop |= hit
    d = d[~drop]
    d["build_year"] = d["build_year"].astype("int64")
    for c in ("company", "name", "former_names", "ice_class"):
        d[c] = d[c].astype(object).where(d[c].notna(), None)
    d = derive(ensure_schema_columns(d))
    report.add("derive", len(d), dropped=reasons)
    return d


# ⑤ 스냅샷 ───────────────────────────────────────────────────────────────
def run(cfg: dict) -> Path:
    report = Report()
    colmap = load_yaml(cfg["data"]["column_map"])
    if cfg["data"]["source"] == "mrv_pipeline":
        # 팀 전처리 파이프라인(vendor/mrv_pipeline)이 이미 열 맞추기·제원·CII 까지 끝낸 결과를 쓴다
        files, df = mrv_source.load(cfg, colmap, report)
        df = add_company_history(df)
    else:
        files = download(cfg)
        df = harmonize(files, colmap, cfg["data"]["ship_types"], report)
        df = enrich(df, cfg, report)
    df = clean_and_derive(df, report)
    df = SHIP_YEAR.validate(df, extra="drop").sort_values(["imo", "year"]).reset_index(drop=True)

    out_dir = path(cfg["data"]["snapshot_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "ship_year.parquet"
    df.to_parquet(out, index=False)
    write_manifest(
        out_dir / "ship_year.manifest.json",
        table=SHIP_YEAR.name, table_version=SHIP_YEAR.version, data_hash=frame_hash(df),
        rows=len(df), ships=int(df["imo"].nunique()), years=sorted(df["year"].unique().tolist()),
        source=cfg["data"]["source"],
        raw_files=[{"file": f.path.name, "year": f.year, "version": f.version, "sha256_12": f.sha} for f in files],
        steps=report.steps,
    )
    report.add("snapshot", len(df), file=str(out))
    return out


def load_snapshot(cfg: dict) -> pd.DataFrame:
    p = path(cfg["data"]["snapshot_dir"]) / "ship_year.parquet"
    if not p.exists():
        raise FileNotFoundError(f"{p} 가 없습니다. 먼저 python tasks.py pipeline")
    df = pd.read_parquet(p)
    for c in ("company", "name", "former_names", "ice_class", "source_version", "ship_type", "eedi_kind", "cii_ship_type", "fuel_group"):
        if c in df.columns:
            df[c] = df[c].astype(object).where(df[c].notna(), None)
    df["eedi"] = df["eedi"].astype(float)
    return df
