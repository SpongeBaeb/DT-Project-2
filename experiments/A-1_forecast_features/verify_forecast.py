"""예측 재현 검증: features.py + quantile.py 로 만든 2026~2028 예측이 팀의 forecast_v4.csv 와 같은지 대조.

    uv run python experiments/A-1_forecast_features/verify_forecast.py \
        --merged <...>/mrv_merged_2026-10-06_3183d290.parquet --v1 <...>/03_regression/v1 \
        --team-forecast <...>/회귀_v4_공유/.../v4/forecast_v4.csv

팀 04_final_v4.ipynb 셀 [2] 와 같은 절차 (보정 연도 2025):
  (1) 목표 연도 ≤ 2024 쌍으로 학습 → 2025 쌍 오차로 z 표   (2) 목표 연도 ≤ 2025 전체로 다시 학습 → 2025년 값에서 예측 → z 표로 중심 보정
수준은 팀 원본과 같은 정박 포함 거리당 CO₂, 선종 표기는 팀 원본(영문 원본 이름)으로 맞춘다 (범주 순서까지 같게).

판정 기준 = '잡음 바닥'. LightGBM 은 학습표의 마지막 자리 반올림(1e-15)에도 예측이 평균 3e-3 쯤 달라진다 (행 뽑기·동률 처리).
컴퓨터·numpy 가 다르면 같은 코드도 이만큼 달라지므로, 내 예측이 팀 예측과 다른 정도가 내 학습표에 1e-15 잡음만 넣었을 때의
변화(잡음 바닥)와 같은 크기면 '재현'으로 본다 (평균 차이 ≤ 잡음 바닥의 2배, 상관 ≥ 0.995).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from models.forecast import quantile as Q  # noqa: E402
from models.forecast.features import CAT, COVID, NUM, build_features, delta_clip_bounds, make_pairs  # noqa: E402
from pipeline import mrv_source  # noqa: E402
from pipeline.run import Report  # noqa: E402
from shared.config import load_yaml  # noqa: E402
from shared.preprocess import derive, ensure_schema_columns  # noqa: E402

TYPES13 = ["container", "tanker", "chemical_tanker", "bulk", "general_cargo", "vehicle_carrier", "ro_pax", "gas_carrier",
           "lng_carrier", "ro_ro", "reefer", "cruise", "container_ro_ro"]
BASE, HS = 2025, (1, 2, 3)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--merged", required=True)
    ap.add_argument("--v1", required=True)
    ap.add_argument("--team-forecast", required=True)
    a = ap.parse_args()

    raw = mrv_source.read_merged(Path(a.merged))
    d = mrv_source.to_ship_year_input(raw, load_yaml("config/column_map.yaml"), TYPES13, Report(), min_gt=5000)
    d = derive(ensure_schema_columns(d))
    d = d.assign(co2_per_nm=d["co2_per_nm_kg"])
    clip = delta_clip_bounds(make_pairs(build_features(d, (-np.inf, np.inf), "co2_per_nm_kg"), 1), 2021)
    f = build_features(d, clip, "co2_per_nm_kg")

    # 팀 원본과 같은 범주 순서(영문 원본 선종명, 알파벳순)
    ref_all = pd.read_csv(Path(a.v1) / "features_all_v1.csv", dtype={"imo": str}, encoding="utf-8-sig", usecols=["imo", "year", "ship_type"])
    f["imo"] = f["imo"].astype(str)
    f["ship_type"] = f[["imo", "year"]].merge(ref_all, on=["imo", "year"], how="left")["ship_type"].to_numpy()
    types = sorted(f["ship_type"].unique())
    f["ship_type"] = pd.Categorical(f["ship_type"], categories=types)
    feats = NUM + CAT
    team = pd.read_csv(a.team_forecast, dtype={"imo": str}, encoding="utf-8-sig")
    x25 = f[f["year"] == BASE].reset_index(drop=True)
    print(f"2025년분 {len(x25):,}척 / 팀 예측 {len(team):,}척 / 피처 {len(feats)}개")

    allok = True
    for h in HS:
        y = BASE + h
        p = make_pairs(f, h)
        p["ship_type"] = pd.Categorical(p["ship_type"].astype(str), categories=types)
        (Qc,) = Q.qfit(p[p["target_year"] <= BASE - 1], [p[p["target_year"] == BASE]], feats)
        zq_raw = Q.ztable(Qc, p.loc[p["target_year"] == BASE, "delta"])
        xh = x25.assign(covid_next=int(y in COVID))
        (Qf,) = Q.qfit(p[p["target_year"] <= BASE], [xh], feats)
        m, s, zq = Q.center(Qf, zq_raw)
        mine = pd.DataFrame({"imo": xh["imo"], f"med_{y}": m, f"s_{y}": s, f"q10_{y}": Q.quantile_at(zq, m, s, 0.10), f"q90_{y}": Q.quantile_at(zq, m, s, 0.90)})
        # 잡음 바닥: 내 학습표에 1e-15 상대 잡음만 넣고 같은 절차를 다시 → 그 정도 차이는 '같은 코드'에서도 생긴다
        rng = np.random.default_rng(0)
        pn = p.copy()
        for c in [*NUM, "delta"]:
            v = pn[c].astype(float).to_numpy()
            pn[c] = v * (1 + 1e-15 * rng.standard_normal(len(v)))
        (Qcn,) = Q.qfit(pn[pn["target_year"] <= BASE - 1], [pn[pn["target_year"] == BASE]], feats)
        zqn = Q.ztable(Qcn, pn.loc[pn["target_year"] == BASE, "delta"])
        (Qfn,) = Q.qfit(pn[pn["target_year"] <= BASE], [xh], feats)
        mn, sn, zqn = Q.center(Qfn, zqn)
        noisy = {"med": mn, "s": sn, "q10": Q.quantile_at(zqn, mn, sn, 0.10), "q90": Q.quantile_at(zqn, mn, sn, 0.90)}
        j = mine.merge(team[["imo", f"med_{y}", f"s_{y}", f"q10_{y}", f"q90_{y}"]], on="imo", suffixes=("", "_team"))
        print(f"\n[{y}년, h={h}] 학습 쌍 {int((p['target_year'] <= BASE).sum()):,} / 맞춤 {len(j):,}")
        for c in ("med", "s", "q10", "q90"):
            col = f"{c}_{y}"
            diff = (j[col] - j[col + "_team"]).abs()
            floor = float(np.abs(mine[col].to_numpy() - noisy[c]).mean())
            corr = float(np.corrcoef(j[col], j[col + "_team"])[0, 1])
            ok = diff.mean() <= max(2 * floor, 1e-9) and corr >= 0.995
            allok &= bool(ok)
            print(f"  {col:10s} 팀과 평균 차이 {diff.mean():.2e} (최대 {diff.max():.2e}, 상관 {corr:.5f}) | 잡음 바닥 평균 {floor:.2e}  {'✅' if ok else '❌'}")
    print("\n결과:", "✅ 재현 (팀과의 차이가 잡음 바닥 이내)" if allok else "❌ 잡음 바닥을 넘는 차이가 있음")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
