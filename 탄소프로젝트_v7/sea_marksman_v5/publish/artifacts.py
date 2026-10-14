"""산출물 만들기 (그림 3 ④): 모델 파일 · 결과 표 · 웹용 JSON · 영수증.

artifacts/<모델 버전>/
  model.joblib, model_meta.json      ← API 가 읽음
  result_table.parquet               ← 분석·발표용 결과 표 (약속 RESULT_TABLE)
  web/meta.json, index.json, ships/<imo>.json   ← 웹이 읽음 (web/public/data 로 복사)
  manifest.json                      ← 어떤 데이터·코드·설정으로 만들었나
artifacts/LATEST                     ← 가장 최근 버전 이름
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd

from contracts.api import IndexEntry, Meta, ShipFile
from contracts.tables import RESULT_TABLE
from models.bundle import ModelBundle
from pipeline.run import load_snapshot
from shared.config import path
from shared.manifest import now_iso, read_manifest, write_manifest
from shared.present import frame_to_inputs, row_to_result

ARTIFACTS = path("artifacts")


def latest_dir() -> Path:
    p = ARTIFACTS / "LATEST"
    if not p.exists():
        raise FileNotFoundError("artifacts/LATEST 가 없습니다. 먼저 python tasks.py build")
    return ARTIFACTS / p.read_text(encoding="utf-8").strip()


def build(cfg: dict) -> Path:
    snap = load_snapshot(cfg)
    bundle = ModelBundle.train(snap, cfg)
    results = bundle.run(snap)

    out = ARTIFACTS / bundle.meta["model_version"]
    if out.exists():
        shutil.rmtree(out)
    bundle.save(out)
    results.to_parquet(out / "result_table.parquet", index=False)
    n_ships = export_web(results, snap, bundle.meta, cfg, out / "web")

    snap_manifest = read_manifest(path(cfg["data"]["snapshot_dir"]) / "ship_year.manifest.json")
    write_manifest(
        out / "manifest.json",
        model_version=bundle.meta["model_version"], data_hash=bundle.meta["data_hash"],
        result_table_version=RESULT_TABLE.version, rows=len(results), ships=n_ships,
        snapshot=snap_manifest, stages=bundle.meta["stages"], thresholds=cfg["thresholds"],
    )
    (ARTIFACTS / "LATEST").write_text(bundle.meta["model_version"], encoding="utf-8")

    public = path(cfg["web"]["public_data_dir"])
    if public.exists():
        shutil.rmtree(public)
    shutil.copytree(out / "web", public)
    return out


def export_web(results: pd.DataFrame, snap: pd.DataFrame, meta: dict, cfg: dict, out: Path) -> int:
    (out / "ships").mkdir(parents=True, exist_ok=True)
    thresholds = cfg["thresholds"]
    snap_idx = snap.set_index(["imo", "year"], drop=False)
    index: list[dict] = []

    for imo, res in results.groupby("imo", sort=True):
        rows = snap[snap["imo"] == imo].sort_values("year")
        last = rows.iloc[-1]
        former = sorted({n for n in rows["name"].dropna() if n != last["name"]})
        file = ShipFile(
            imo=int(imo), name=last["name"], former_names=former, ship_type=last["ship_type"], company=last["company"],
            inputs=frame_to_inputs(rows),
            results=[row_to_result(r, snap_idx.loc[(imo, int(r["year"]))], meta, thresholds) for _, r in res.iterrows()],
        )
        _write(out / "ships" / f"{int(imo)}.json", file.model_dump(mode="json"))
        lr = res.iloc[-1]
        index.append(IndexEntry(
            imo=int(imo), name=last["name"], former_names=former, ship_type=last["ship_type"], dwt=float(last["dwt"]),
            build_year=int(last["build_year"]), last_year=int(lr["year"]), vs_peer_pct=round(float(lr["vs_peer_pct"]), 2),
            position_class=lr["position_class"], sig_any=bool(lr["sig_any"]),
        ).model_dump(mode="json"))

    _write(out / "index.json", index)
    _write(out / "meta.json", Meta(
        model_version=meta["model_version"], data_hash=meta["data_hash"], result_table_version=RESULT_TABLE.version,
        ship_types=meta["ship_types"], train_years=meta["train_years"], created_at=now_iso(),
    ).model_dump(mode="json"))
    return len(index)


def _write(p: Path, obj) -> None:
    p.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
