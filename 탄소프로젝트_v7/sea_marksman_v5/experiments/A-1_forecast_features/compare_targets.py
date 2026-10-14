"""예측 목표 비교: 정박 포함 거리당 CO₂(co2_per_nm_kg) vs 해상 효율(sea_eff_kg_nm), 같은 조건의 MAE.

    uv run python experiments/A-1_forecast_features/compare_targets.py --config config/mrv_pipeline.yaml --seeds 0 1 2

절차 = 팀 04_final_v4.ipynb 와 같다 (분위수 LightGBM 7개 + 보정 연도 z 표로 중심 보정, 대표값 = 중앙값).
엄격한 검증: 출발 연도 t 의 예측은 목표 연도 ≤ t 인 쌍만 알 때의 모델로 만든다 (보정 연도 = t).
  시험: h=1 → t ∈ {2023, 2024}, h=2 → t ∈ {2022, 2023}, h=3 → t = 2022.

두 목표는 단위가 달라 MAE 를 바로 비교할 수 없으므로 세 가지로 본다.
  ① 각자 목표에서 '변화 없음'(Δ=0) 대비 MAE 개선률
  ② 정박 포함 총량(co2_per_nm_kg)으로 환산해 같은 잣대로: 해상 효율 모델은 정박을 t 년 값으로 고정 (총 = 해상효율_t·e^Δ + 정박/nm_t)
  ③ 해상 효율로 환산해 같은 잣대로: 총량 모델은 정박을 t 년 값으로 고정 (해상효율 = 총_t·e^Δ − 정박/nm_t)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from models.forecast import quantile as Q  # noqa: E402
from models.forecast.features import CAT, NUM, build_features, delta_clip_bounds, make_pairs  # noqa: E402
from pipeline.run import load_snapshot  # noqa: E402
from shared.config import load_config  # noqa: E402

TESTS = {1: (2023, 2024), 2: (2022, 2023), 3: (2022,)}
TOTAL, SEA = "co2_per_nm_kg", "sea_eff_kg_nm"


def prepare(df: pd.DataFrame, level: str) -> tuple[pd.DataFrame, list[str]]:
    clip = delta_clip_bounds(make_pairs(build_features(df, (-np.inf, np.inf), level), 1), 2021)
    f = build_features(df, clip, level)
    types = sorted(f["ship_type"].astype(str).unique())
    f["ship_type"] = pd.Categorical(f["ship_type"].astype(str), categories=types)
    return f, types


def run_target(df: pd.DataFrame, level: str, seed: int) -> pd.DataFrame:
    """테스트마다 출발 연도 t 의 모든 배에 대한 대표값 Δ(중앙값) 예측과 실제 Δ."""
    f, types = prepare(df, level)
    feats = NUM + CAT
    params = {**Q.PW, "random_state": seed}
    rows = []
    for h, ts in TESTS.items():
        p = make_pairs(f, h)
        p["ship_type"] = pd.Categorical(p["ship_type"].astype(str), categories=types)
        for t in ts:
            (Qc,) = Q.qfit(p[p["target_year"] <= t - 1], [p[p["target_year"] == t]], feats, params=params)
            zq_raw = Q.ztable(Qc, p.loc[p["target_year"] == t, "delta"])
            x = p[p["year"] == t]
            (Qf,) = Q.qfit(p[p["target_year"] <= t], [x], feats, params=params)
            m, _, _ = Q.center(Qf, zq_raw)
            rows.append(pd.DataFrame({"imo": x["imo"].to_numpy(), "t": t, "h": h, "delta": x["delta"].to_numpy(), "m": m, "level_t": x["level"].to_numpy()}))
    return pd.concat(rows, ignore_index=True)


def evaluate(df: pd.DataFrame, seed: int) -> pd.DataFrame:
    tot = run_target(df, TOTAL, seed).rename(columns={"delta": "d_tot", "m": "m_tot", "level_t": "tot_t"})
    sea = run_target(df, SEA, seed).rename(columns={"delta": "d_sea", "m": "m_sea", "level_t": "sea_t"})
    r = tot.merge(sea, on=["imo", "t", "h"], validate="one_to_one")
    d = df.assign(berth_nm=df["berth_co2_t"] * 1000 / df["distance_nm"]).sort_values(["imo", "year"])[["imo", "year", TOTAL, SEA, "berth_nm"]]
    d["berth_avg"] = d.groupby("imo")["berth_nm"].transform(lambda s: s.expanding().mean())          # t 년까지 정박/nm 평균 (미래 연도 없음)
    r = r.merge(d[["imo", "year", "berth_nm", "berth_avg"]].rename(columns={"year": "t"}), on=["imo", "t"], how="left")
    r["tot_act"] = r["tot_t"] * np.exp(r["d_tot"])                       # t+h 년 실제 총량 (kg/nm)
    r["sea_act"] = r["sea_t"] * np.exp(r["d_sea"])
    # ① 각자 목표
    r["e_tot"], r["e_sea"] = (r["d_tot"] - r["m_tot"]).abs(), (r["d_sea"] - r["m_sea"]).abs()
    r["p_tot"], r["p_sea"] = r["d_tot"].abs(), r["d_sea"].abs()
    # ② 총량으로: 해상 효율 모델 + 정박 t 년 고정
    pred_tot_from_sea = r["sea_t"] * np.exp(r["m_sea"]) + r["berth_nm"]
    r["x_tot_by_sea"] = (np.log(pred_tot_from_sea) - np.log(r["tot_act"])).abs()
    # ②' 정박을 t 년 값이 아니라 t 년까지의 평균으로 두면 (평균 회귀를 단순하게 반영)
    r["x_tot_by_sea_avg"] = (np.log(r["sea_t"] * np.exp(r["m_sea"]) + r["berth_avg"]) - np.log(r["tot_act"])).abs()
    # ③ 해상 효율로: 총량 모델 + 정박 t 년 고정 (음수가 되면 해상 효율의 5% 로 바닥)
    pred_sea_from_tot = (r["tot_t"] * np.exp(r["m_tot"]) - r["berth_nm"]).clip(lower=0.05 * r["sea_t"])
    r["x_sea_by_tot"] = (np.log(pred_sea_from_tot) - np.log(r["sea_act"])).abs()
    r["seed"] = seed
    return r


def summarize(r: pd.DataFrame) -> pd.DataFrame:
    out = []
    for (seed, h, t), g in r.groupby(["seed", "h", "t"]):
        out.append({
            "seed": seed, "h": h, "t": t, "n": len(g),
            "총량 MAE": g.e_tot.mean(), "총량 변화없음": g.p_tot.mean(), "총량 개선률%": (1 - g.e_tot.mean() / g.p_tot.mean()) * 100,
            "해상 MAE": g.e_sea.mean(), "해상 변화없음": g.p_sea.mean(), "해상 개선률%": (1 - g.e_sea.mean() / g.p_sea.mean()) * 100,
            "[총량 잣대] 총량모델": g.e_tot.mean(), "[총량 잣대] 해상모델": g.x_tot_by_sea.mean(), "[총량 잣대] 해상모델(정박 평균)": g.x_tot_by_sea_avg.mean(), "[총량 잣대] 변화없음": g.p_tot.mean(),
            "[해상 잣대] 해상모델": g.e_sea.mean(), "[해상 잣대] 총량모델": g.x_sea_by_tot.mean(), "[해상 잣대] 변화없음": g.p_sea.mean(),
        })
    return pd.DataFrame(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="config/mrv_pipeline.yaml")
    ap.add_argument("--seeds", type=int, nargs="+", default=[0])
    ap.add_argument("--out", default=None, help="시험 결과 CSV 저장 경로")
    a = ap.parse_args()
    cfg = load_config(a.config)
    df = load_snapshot(cfg)
    df = df.sort_values(["imo", "year"]).reset_index(drop=True)
    print(f"스냅샷 {len(df):,}행 {df['imo'].nunique():,}척, 시드 {a.seeds}")
    res = []
    for seed in a.seeds:
        res.append(evaluate(df, seed))
        print(f"시드 {seed} 완료", flush=True)
    r = pd.concat(res, ignore_index=True)
    s = summarize(r)
    pd.set_option("display.width", 250)
    pd.set_option("display.float_format", lambda v: f"{v:.4f}")
    print("\n[시험별 · 시드별]")
    print(s[["seed", "h", "t", "n", "총량 MAE", "총량 개선률%", "해상 MAE", "해상 개선률%"]].to_string(index=False))
    m = s.groupby(["h", "t"]).agg(n=("n", "first"), **{c: (c, "mean") for c in s.columns if c not in ("seed", "h", "t", "n")}).reset_index()
    sd = s.groupby(["h", "t"])[["총량 개선률%", "해상 개선률%"]].std().rename(columns=lambda c: c + "(시드 표준편차)").reset_index()
    print("\n[① 각자 목표에서 '변화 없음' 대비 개선률 (시드 평균)]")
    print(m.merge(sd, on=["h", "t"])[["h", "t", "n", "총량 변화없음", "총량 MAE", "총량 개선률%", "총량 개선률%(시드 표준편차)", "해상 변화없음", "해상 MAE", "해상 개선률%", "해상 개선률%(시드 표준편차)"]].to_string(index=False))
    print("\n[② 정박 포함 총량 잣대 (정박 t 년 고정)]  MAE: 총량모델 / 해상모델 / 변화없음")
    print(m[["h", "t", "[총량 잣대] 총량모델", "[총량 잣대] 해상모델", "[총량 잣대] 해상모델(정박 평균)", "[총량 잣대] 변화없음"]].to_string(index=False))
    print("\n[③ 해상 효율 잣대 (정박 t 년 고정)]  MAE: 해상모델 / 총량모델 / 변화없음")
    print(m[["h", "t", "[해상 잣대] 해상모델", "[해상 잣대] 총량모델", "[해상 잣대] 변화없음"]].to_string(index=False))
    # 기간별 합산 (시드 평균 예측 대신 시드별 평균) + 배 단위 쌍 차이의 표준오차
    print("\n[기간별 합산]")
    for h, g in r.groupby("h"):
        for lab, c1, c2 in (("총량 잣대: 해상모델(정박 고정) − 총량모델", "x_tot_by_sea", "e_tot"), ("총량 잣대: 해상모델(정박 평균) − 총량모델", "x_tot_by_sea_avg", "e_tot"), ("해상 잣대: 총량모델 − 해상모델", "x_sea_by_tot", "e_sea")):
            per = g.groupby(["seed", "imo", "t"]).apply(lambda t: (t[c1] - t[c2]).mean(), include_groups=False).groupby(level=["imo", "t"]).mean()
            print(f"  h={h} {lab}: 평균 {per.mean():+.4f}  표준오차 {per.std() / np.sqrt(len(per)):.4f}  (음수면 앞의 모델이 더 좋음)")
    if a.out:
        s.to_csv(a.out, index=False, encoding="utf-8-sig")
        print("저장:", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
