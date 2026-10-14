"""예측 피처 재구현 검증: models/forecast/features.py 가 팀의 features_v1.csv / features_all_v1.csv 와 같은 값을 내는지 열마다 대조.

    uv run python experiments/A-1_forecast_features/verify_features.py \
        --merged <regression_v4_final>/mrv_pipeline/data/processed/snapshots/mrv_merged_2026-10-06_3183d290.parquet \
        --v1 <regression_v4_final>/03_regression/v1

정의 근거: 이 스냅샷(3183d290)의 열과 features_*.csv 를 수치로 맞춰 확정했다 (docs/decisions.md 2026-10-12).
수준은 팀 원본과 같은 정박 포함 거리당 CO₂(co2_per_nm_kg)로 둔다. 새 지표(해상 효율)는 여기서 검증하지 않는다.
V2 피처(dev_own, vol_past, n_prev, load_factor, load_chg)는 reg_common.load() 의 코드를 그대로 옮겨 만든 값과 대조한다.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from models.forecast.features import NUM_V1, NUM_V2, build_features, delta_clip_bounds, make_pairs  # noqa: E402
from pipeline import mrv_source  # noqa: E402
from pipeline.run import Report  # noqa: E402
from shared.config import load_yaml  # noqa: E402
from shared.preprocess import derive, ensure_schema_columns  # noqa: E402

TYPES13 = ["container", "tanker", "chemical_tanker", "bulk", "general_cargo", "vehicle_carrier", "ro_pax", "gas_carrier",
           "lng_carrier", "ro_ro", "reefer", "cruise", "container_ro_ro"]


def reg_common_v2(df: pd.DataFrame, clip: tuple[float, float]) -> pd.DataFrame:
    """03_regression/reg_common.py load() 안의 v2 피처 계산 (팀 코드 그대로)."""
    h = df[["imo", "year", "co2_per_nm", "avg_load", "avg_load_invalid", "avg_load_basis", "dwt"]].sort_values(["imo", "year"]).reset_index(drop=True)
    h["ln_c"] = np.log(h["co2_per_nm"])
    g_ = h.groupby("imo", sort=False)
    gap = g_["year"].diff()
    h["n_prev"] = g_.cumcount()
    h["own_mean_prev"] = g_["ln_c"].transform(lambda s: s.expanding().mean().shift(1))
    h["dev_own"] = h["ln_c"] - h["own_mean_prev"]
    h["absd"] = (h["ln_c"] - g_["ln_c"].shift(1)).where(gap == 1).clip(*clip).abs()
    h["vol_past"] = h.groupby("imo", sort=False)["absd"].transform(lambda s: s.expanding().mean())
    ok_ = h["avg_load"].gt(0) & ~h["avg_load_invalid"].fillna(False).astype(bool)
    ln_load = np.log(h["avg_load"].where(ok_))
    h["load_chg"] = (ln_load - ln_load.groupby(h["imo"]).shift(1)).where(gap == 1)
    h["load_factor"] = (h["avg_load"] / h["dwt"]).where(ok_ & h["avg_load_basis"].isin(["mass", "dwt"])).clip(upper=1.5)
    return h[["imo", "year", "dev_own", "vol_past", "n_prev", "load_factor", "load_chg"]]


def same(mine: pd.Series, ref: pd.Series, tol: float = 1e-6) -> tuple[float, int]:
    ok = np.isclose(mine.astype(float).to_numpy(), ref.astype(float).to_numpy(), atol=tol, rtol=1e-9, equal_nan=True)
    return float(ok.mean()), int((~ok).sum())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--merged", required=True)
    ap.add_argument("--v1", required=True)
    a = ap.parse_args()
    v1 = Path(a.v1)

    raw = mrv_source.read_merged(Path(a.merged))
    d = mrv_source.to_ship_year_input(raw, load_yaml("config/column_map.yaml"), TYPES13, Report(), min_gt=5000)
    d = derive(ensure_schema_columns(d))                         # 행을 버리지 않는다 (원본 96,242행과 같은 행 집합)
    d = d.assign(co2_per_nm=d["co2_per_nm_kg"])
    ref_all = pd.read_csv(v1 / "features_all_v1.csv", dtype={"imo": str}, encoding="utf-8-sig")
    ref_pairs = pd.read_csv(v1 / "features_v1.csv", dtype={"imo": str}, encoding="utf-8-sig")
    print(f"행 {len(d):,} (원본 features_all {len(ref_all):,})")

    # 학습 쌍 변화의 1%·99% 분위수 = 직전 해 변화를 자를 범위 (원본 target_meta 의 clip)
    clip = delta_clip_bounds(make_pairs(build_features(d, (-np.inf, np.inf), "co2_per_nm_kg"), 1), train_until_year=2021)
    import json
    meta = json.loads((v1 / "target_meta.json").read_text(encoding="utf-8"))["target"]
    print(f"clip 범위: 내 값 ({clip[0]:.10f}, {clip[1]:.10f}) / 원본 ({meta['clip_lo']:.10f}, {meta['clip_hi']:.10f})")
    clip_ok = np.allclose(clip, (meta["clip_lo"], meta["clip_hi"]), atol=1e-12)

    f = build_features(d, clip, "co2_per_nm_kg")
    f["imo"] = f["imo"].astype(str)
    m = f.merge(ref_all, on=["imo", "year"], suffixes=("", "_ref"), validate="one_to_one")
    print(f"행 맞춤 {len(m):,} / {len(ref_all):,}")
    bad = []
    print("\n[피처 대조: features_all_v1.csv]")
    for c in NUM_V1:
        if c == "covid_next":
            continue                                             # 기간 h 마다 다름 → 아래 쌍 대조에서 확인
        frac, n = same(m[c], m[c + "_ref"])
        print(f"  {c:16s} 일치 {frac * 100:7.3f}%  불일치 {n}")
        if n:
            bad.append(c)

    # V2 피처
    r2 = reg_common_v2(d.assign(imo=d["imo"].astype(int)), clip).assign(imo=lambda t: t["imo"].astype(str))
    m2 = f.merge(r2, on=["imo", "year"], suffixes=("", "_ref"), validate="one_to_one")
    print("\n[V2 피처: reg_common.load() 와 같은 계산]")
    for c in NUM_V2:
        frac, n = same(m2[c], m2[c + "_ref"])
        print(f"  {c:16s} 일치 {frac * 100:7.3f}%  불일치 {n}")
        if n:
            bad.append(c)

    # 학습 쌍 (h=1)
    p = make_pairs(f, 1)
    mp = p.merge(ref_pairs[["imo", "year", "delta", "covid_next", "co2_per_nm", "co2_per_nm_next"]], on=["imo", "year"], suffixes=("", "_ref"), validate="one_to_one")
    print(f"\n[학습 쌍 h=1] 내 쌍 {len(p):,} / 원본 {len(ref_pairs):,} / 맞춤 {len(mp):,}")
    for mine, ref in (("delta", "delta_ref"), ("covid_next", "covid_next_ref")):
        frac, n = same(mp[mine], mp[ref])
        print(f"  {mine:16s} 일치 {frac * 100:7.3f}%  불일치 {n}")
        if n:
            bad.append(mine)
    same_rows = len(p) == len(ref_pairs) == len(mp)
    print("\n결과:", "✅ 모두 일치" if not bad and clip_ok and same_rows else f"❌ 불일치 있음: {bad} clip_ok={clip_ok} rows_ok={same_rows}")
    return 0 if not bad and clip_ok and same_rows else 1


if __name__ == "__main__":
    sys.exit(main())
