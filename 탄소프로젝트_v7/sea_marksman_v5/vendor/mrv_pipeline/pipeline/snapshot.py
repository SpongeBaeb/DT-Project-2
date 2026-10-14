"""최종 파일 스냅샷 — 내용이 바뀔 때만 날짜 + 내용 해시 이름으로 보관 (최근 SNAPSHOT_KEEP개).

data/processed/snapshots/
  ├─ mrv_merged_2026-10-06_3183d290.parquet   ← mrv_merged.parquet을 그대로 복사 (바이트까지 같음)
  └─ index.csv                                  ← 스냅샷 목록: 파일, 저장 시각, 해시, 행 수, 원본 버전, 리포트

- 해시는 mrv_reader.data_hash와 같은 방식이라, 노트북에서 load_merged()로 읽은 값과 파일 이름의 해시가 일치한다
- 쓰기 직후 parquet을 다시 읽어 해시를 계산 (노트북이 읽는 것과 똑같은 데이터 기준)
- 스냅샷은 되돌리기(--rollback)·직전 결과 백업 대상이 아니다 (한 번 만들면 바뀌지 않는 기록)
"""
from __future__ import annotations

import json
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from pipeline import config

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))     # mrv_reader.py (파이프라인 폴더 바로 아래)
import mrv_reader  # noqa: E402

log = logging.getLogger("pipeline.snapshot")
INDEX_COLS = ["file", "saved_at", "data_hash", "rows", "columns", "ships", "versions", "report"]


def _index_path(d: Path) -> Path:
    return d / "index.csv"


def load_index(d: Path) -> pd.DataFrame:
    p = _index_path(d)
    return pd.read_csv(p, dtype=str) if p.exists() else pd.DataFrame(columns=INDEX_COLS)


def save(parquet_path: Path, snap_dir: Path, report_name: str, now: datetime | None = None) -> str:
    """parquet_path(방금 쓴 mrv_merged.parquet)의 스냅샷을 남긴다. 반환: 리포트에 넣을 한 줄"""
    now = now or datetime.now()
    df = pd.read_parquet(parquet_path)
    h = mrv_reader.data_hash(df)
    snap_dir.mkdir(parents=True, exist_ok=True)
    same = sorted(snap_dir.glob(f"mrv_merged_*_{h[:8]}.parquet"))
    if same:
        return f"스냅샷: 내용이 같은 스냅샷이 이미 있어 새로 만들지 않음 ({same[-1].name})"

    name = f"mrv_merged_{now:%Y-%m-%d}_{h[:8]}.parquet"
    tmp = snap_dir / (name + ".tmp")
    shutil.copy2(parquet_path, tmp)
    tmp.replace(snap_dir / name)

    versions = (df.groupby("year")["mrv_file_version"].first() if "mrv_file_version" in df else pd.Series(dtype=str))
    idx = load_index(snap_dir)
    row = {"file": name, "saved_at": now.isoformat(timespec="seconds"), "data_hash": h, "rows": len(df),
           "columns": df.shape[1], "ships": int(df["imo"].nunique()),
           "versions": json.dumps({str(int(y)): str(v) for y, v in versions.items()}), "report": report_name}
    idx = pd.concat([idx, pd.DataFrame([row])], ignore_index=True)

    # 최근 SNAPSHOT_KEEP개만 보관
    files = sorted(snap_dir.glob("mrv_merged_*.parquet"), key=lambda p: p.stat().st_mtime)
    removed = []
    for p in files[:-config.SNAPSHOT_KEEP] if len(files) > config.SNAPSHOT_KEEP else []:
        p.unlink()
        removed.append(p.name)
    idx = idx[idx["file"].isin({p.name for p in snap_dir.glob("mrv_merged_*.parquet")})]
    idx.to_csv(_index_path(snap_dir), index=False, encoding=config.CSV_ENCODING)
    msg = f"스냅샷: {name} 저장 (보관 {len(idx)}개)"
    return msg + (f", 오래된 스냅샷 삭제 {removed}" if removed else "")
