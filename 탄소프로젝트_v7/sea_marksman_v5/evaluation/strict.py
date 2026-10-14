"""엄격한 시간 분할 검증 — 예측 시점에 아는 정보만으로 만든 과거 예측을 저장하고, 선종 × 기간별 지표표를 만든다.

신뢰 등급·예측 성적 평가의 입력이다. 절차는 팀 회귀 v4 의 '엄격한 검증'과 같다 (compare_targets.py 와 같은 절차를 결과를 저장하도록 일반화):
  출발 연도 t 의 예측은 목표 연도 ≤ t 인 쌍만 알 때의 정보로 만든다 (보정 연도 = t).
    목표 연도 ≤ t−1 쌍으로 학습한 모델 하나로 (1) 목표 연도 t 쌍의 오차 → z 표, (2) 출발 연도 t 의 배들 예측 → z 표로 중심 보정.  보정 연도를 학습에서 따로 뗀 절차라 최종(운영) 모델보다 학습 쌍이 적다.
    retrain=True 면 보정 뒤 목표 연도 ≤ t 로 다시 학습해 예측한다 (운영 때의 최종 모델 절차).
  시험: h=1 → t ∈ {2023, 2024}, h=2 → t ∈ {2022, 2023}, h=3 → t = 2022   (목표 연도 2024·2025, 3년 뒤는 2025 하나)

strict_predictions(...)  → 배 × 시험 한 줄 (실제 변화, 대표값, 분위, 선형·변화 없음 기준, CII D·E 확률)
type_table(preds)        → 선종 × 기간 표 (팀 type_eval_v4.csv 와 같은 지표)
overall_table(preds)     → 기간별 전체 지표 (팀 test_metrics_v4.csv 의 '엄격' 행과 같은 지표)

Δ = ln(목표 연도 수준 ÷ 출발 연도 수준). 수준은 level 열 (sea_eff_kg_nm 해상 효율, co2_per_nm_kg 정박 포함 거리당 CO₂).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import roc_auc_score

from models.forecast import cii as cii_rules
from models.forecast import quantile as Q
from models.forecast.features import CAT, NUM, build_features, delta_clip_bounds, make_pairs

TESTS = {1: (2023, 2024), 2: (2022, 2023), 3: (2022,)}
QUANTILE_LEVELS = (5, 10, 25, 50, 75, 90, 95)


def _prepare(df: pd.DataFrame, level: str) -> tuple[pd.DataFrame, list[str]]:
    clip = delta_clip_bounds(make_pairs(build_features(df, (-np.inf, np.inf), level), 1), 2021)
    f = build_features(df, clip, level)
    types = sorted(f["ship_type"].astype(str).unique())
    f["ship_type"] = pd.Categorical(f["ship_type"].astype(str), categories=types)
    return f, types


def _mr_x(d: pd.DataFrame) -> np.ndarray:
    """평균 회귀 선형 기준의 입력 (팀 reg_common.mr_X): 작년 변화, 작년 보고 여부, 선종 내 효율 백분위."""
    return np.column_stack([d["delta_prev_clip"].fillna(0), d["has_prev"], d["level_pct"].fillna(0.5)])    # 백분위가 없으면(설계값 없는 표본) 중간값


def strict_predictions(df: pd.DataFrame, level: str, *, seed: int = 0, tests: dict[int, tuple[int, ...]] = TESTS, cii: bool = False,
                       retrain: bool = False, ship_types: dict[str, str] | None = None, verbose: bool = False) -> pd.DataFrame:
    """df: 배·연도 표 (SHIP_YEAR 모양, derive 가 끝난 것). cii=True 면 D·E 확률과 실제 D·E 도 붙인다 (정박 포함 총량 level 에서만 뜻이 맞다)."""
    f, types = _prepare(df, level)
    feats = NUM + CAT
    params = {**Q.PW, "random_state": int(seed)}
    side = df[["imo", "year", "cii_ship_type", "dwt", "gt", "cii_ratio_2026basis", "cii_rating"]]
    rating_at = side.set_index(["imo", "year"])["cii_rating"]
    out = []
    for h, ts in tests.items():
        p = make_pairs(f, h)
        p["ship_type"] = pd.Categorical(p["ship_type"].astype(str), categories=types)
        for t in ts:
            calib, x, trn = p[p["target_year"] == t], p[p["year"] == t], p[p["target_year"] <= t]
            # 시험 절차(팀 '보정 연도를 따로 뗌'): 목표 연도 ≤ t−1 로 학습한 모델 하나로 보정(목표 연도 t 쌍의 오차)과 예측(출발 연도 t 의 배들)을 다 한다.
            # retrain=True 면 보정 뒤 목표 연도 ≤ t 로 다시 학습해 예측한다 (운영 때의 최종 모델 절차 — 학습 쌍이 더 많아 성적이 조금 좋다)
            Qc, Qx = Q.qfit(p[p["target_year"] <= t - 1], [calib, x], feats, params=params)
            zq_raw = Q.ztable(Qc, calib["delta"])
            if retrain:
                (Qx,) = Q.qfit(trn, [x], feats, params=params)
            m, s, zq = Q.center(Qx, zq_raw)
            r = pd.DataFrame({"imo": x["imo"].to_numpy(), "ship_type": x["ship_type"].astype(str).to_numpy(), "h": h, "t": t, "target_year": t + h,
                              "level_t": x["level"].to_numpy(), "level_target": x["level_next"].to_numpy(), "delta": x["delta"].to_numpy(), "m": m, "s": s})
            for q in QUANTILE_LEVELS:
                r[f"q{q}"] = Q.quantile_at(zq, m, s, q / 100)
            lo, hi = np.quantile(trn["delta"], [0.01, 0.99])
            r["pred_linear"] = LinearRegression().fit(_mr_x(trn), trn["delta"].clip(lo, hi)).predict(_mr_x(x))
            if cii:
                rows = r[["imo"]].assign(year=t).merge(side[side["year"] == t].drop(columns="year"), on="imo", how="left")
                thr = cii_rules.threshold(rows, np.full(len(rows), t + h))
                rating = rating_at.reindex(pd.MultiIndex.from_arrays([r["imo"], np.full(len(r), t + h)])).to_numpy()
                r["thr_de"] = thr
                r["p_de"] = 1 - Q.cdf(zq, m, s, thr)
                r["p_de_nochange"] = 1 - Q.cdf(zq, np.zeros(len(r)), s, thr)               # 예측 변화를 0 으로 둔 확률 ('현재 수준' 기준)
                r["de_target"] = np.where(pd.isna(rating), np.nan, np.isin(rating, ["D", "E"]).astype(float))
            out.append(r)
            if verbose:
                print(f"  h={h} t={t}: {len(r):,}쌍", flush=True)
    res = pd.concat(out, ignore_index=True)
    if ship_types:
        res["ship_type"] = res["ship_type"].map(lambda v: ship_types.get(v, v))
    res["level"] = level
    return res


# ───────────────────────── 지표표 ─────────────────────────
def _top_hit(score: np.ndarray, y: np.ndarray, k: int) -> float:
    """점수 상위 k 개 중 y=1 비율 (%). 같은 점수는 앞쪽을 먼저 (안정 정렬)."""
    if k <= 0 or len(y) < k:
        return float("nan")
    return float(np.nanmean(y[np.argsort(-score, kind="stable")[:k]]) * 100)


def type_table(preds: pd.DataFrame, rule: str = "thr") -> pd.DataFrame:
    """선종 × 기간 표. 열은 팀 type_eval_v4.csv 와 같다 (등급 열 제외).
    rule: '현재 수준 규칙' 점수 — 'thr'(D·E 임계값이 낮을수록 위험) 또는 'nochange'(예측 변화를 0 으로 둔 D·E 확률)."""
    rows = []
    for (t, h), g in preds.groupby(["ship_type", "h"], sort=True):
        e = g["delta"] - g["m"]
        ye = g["target_year"]
        row = {
            "선종": t, "기간": h, "쌍": len(g), "연평균 척수": len(g) / g["t"].nunique(),
            "MAE 변화 없음": float(g["delta"].abs().mean()), "MAE 선형": float((g["delta"] - g["pred_linear"]).abs().mean()), "MAE v4": float(e.abs().mean()),
            "치우침 2024": float(e[ye == 2024].mean()) if (ye == 2024).any() else np.nan,
            "치우침 2025": float(e[ye == 2025].mean()) if (ye == 2025).any() else np.nan,
            "구간 포함률%": float(((g["delta"] >= g["q10"]) & (g["delta"] <= g["q90"])).mean() * 100),
        }
        if "p_de" in g.columns:
            y = g["de_target"].to_numpy(float)
            k = int(round(len(g) * 0.1))
            score_rule = -g["thr_de"].to_numpy(float) if rule == "thr" else g["p_de_nochange"].to_numpy(float)
            row.update({
                "실제 D·E%": float(np.nanmean(y) * 100), "D·E 예측−실제 %p": float((g["p_de"].mean() - np.nanmean(y)) * 100),
                "상위10% 규칙": _top_hit(np.nan_to_num(score_rule, nan=-9e9), y, k), "상위10% v4": _top_hit(np.nan_to_num(g["p_de"].to_numpy(float), nan=-9e9), y, k),
            })
        row["변화 없음 대비%"] = (1 - row["MAE v4"] / row["MAE 변화 없음"]) * 100
        row["선형 대비%"] = (1 - row["MAE v4"] / row["MAE 선형"]) * 100
        if "상위10% v4" in row:
            row["상위10% 차이 %p"] = row["상위10% v4"] - row["상위10% 규칙"]
        rows.append(row)
    return pd.DataFrame(rows)


def overall_table(preds: pd.DataFrame) -> pd.DataFrame:
    """기간별 전체 지표 (팀 test_metrics_v4.csv 의 '엄격' 행과 같은 이름)."""
    rows = []
    for h, g in preds.groupby("h", sort=True):
        e = g["delta"] - g["m"]
        row = {"h": h, "쌍": len(g), "MAE v4": float(e.abs().mean()), "MAE 선형": float((g["delta"] - g["pred_linear"]).abs().mean()), "MAE 변화없음": float(g["delta"].abs().mean()),
               "치우침 v4": float(e.mean()), "80% 포함 v4": float(((g["delta"] >= g["q10"]) & (g["delta"] <= g["q90"])).mean() * 100),
               "50% 포함 v4": float(((g["delta"] >= g["q25"]) & (g["delta"] <= g["q75"])).mean() * 100)}
        if "p_de" in g.columns:
            ok = g["de_target"].notna() & g["p_de"].notna()
            y, p = g.loc[ok, "de_target"].to_numpy(), g.loc[ok, "p_de"].to_numpy()
            row.update({"D·E AUC v4": float(roc_auc_score(y, p)) if 0 < y.sum() < len(y) else np.nan, "D·E 상위200 v4": _top_hit(p, y, 200),
                        "D·E 예측−실제 %p": float((p.mean() - y.mean()) * 100), "Brier D·E": float(np.mean((p - y) ** 2))})
        rows.append(row)
    return pd.DataFrame(rows)
