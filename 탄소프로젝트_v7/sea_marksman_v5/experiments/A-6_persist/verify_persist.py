"""유지 확률 이식 검증 (models/forecast/persist.py ← 방현수 08_유지확률 persist-1.2).

    uv run python experiments/A-6_persist/verify_persist.py --config config/mrv_pipeline.yaml [--strict]

원본 절차 (README 3절, 합격 기준 4개는 결과를 보기 전에 정한 것):
  검증 = 2021·2022·2023 롤링 (각 연도 t 를 t−1 이하 라벨로 학습), 시험 = 2024 (한 번만). 평가 대상 = t년 점검 필요(z ≥ 2) 배
  기준 A = 학습 기간 점검 필요 배 유지율 하나, 기준 B = z 하나 로지스틱
  합격: Brier 가 A 보다 10% 이상 낮음 · 보정 오차(5구간) 5%p 이하 · AUC 가 B 보다 높음 · 확률 상위 20% 와 하위 20% 의 실제 유지율 차이 20%p 이상
원본 결과 (구 공통잔차 입력, 점검 필요 262척): 시험 Brier 0.146 (A 대비 −19%), AUC 0.784, 보정 9.6%p(미통과), 상위−하위 48.1%p, 검증 Brier 0.175

기본: 앞 Stage 4개(기준·잔차·정박·위치)를 전 연도로 학습한 표를 쓴다 (원본과 같은 한계: 잔차 모델에 미래 자료가 조금 섞임).
--strict: 연도 t 마다 앞 Stage 를 t 까지로 다시 학습한다 (t+1년 잔차도 그 모델로 계산 = 표본 밖).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from models.base import FitContext  # noqa: E402
from models.bundle import ModelBundle  # noqa: E402
from models.forecast.persist import PersistProbability  # noqa: E402
from pipeline.run import load_snapshot  # noqa: E402
from shared.config import load_config  # noqa: E402

UPTO = 4        # 앞 Stage 4개: PeerGroup, CommonResidualBaseline, BerthCompare, EmpiricalBayesPosition


def metrics(p, y) -> dict:
    p, y = np.asarray(p, float), np.asarray(y, float)
    q = pd.Series(p).rank(method="first")
    b = pd.qcut(q, 5, labels=False)
    cal = max(abs(p[b == i].mean() - y[b == i].mean()) for i in range(5))
    r = pd.Series(p).rank(pct=True, method="first").to_numpy()
    return {"n": len(y), "실제 유지": y.mean(), "예측 평균": p.mean(), "Brier": brier_score_loss(y, p), "AUC": roc_auc_score(y, p) if 0 < y.mean() < 1 else np.nan,
            "보정 오차%p": cal * 100, "상위20": y[r > 0.8].mean(), "하위20": y[r <= 0.2].mean()}


def labels(work: pd.DataFrame, lift: float) -> pd.Series:
    nxt = work[["imo", "year", "contrib_unexplained"]].assign(year=lambda x: x["year"] - 1).rename(columns={"contrib_unexplained": "nr"})
    m = work[["imo", "year"]].merge(nxt, on=["imo", "year"], how="left")
    return pd.Series(np.where(m["nr"].notna(), (m["nr"] > np.log(lift)).astype(float), np.nan), index=work.index)


def one_year(work: pd.DataFrame, t: int, ctx: FitContext, y_all: pd.Series) -> pd.DataFrame:
    """연도 t 의 점검 필요 배 확률: t−1 이하 라벨로 학습 → t 예측."""
    st = PersistProbability().fit(work[work["year"] <= t].copy(), ctx)
    cur = work[(work["year"] == t) & (work["position_z"] >= 2.0)]
    out = st.transform(work.loc[cur.index])
    res = cur[["imo", "year", "position_z"]].join(out).assign(y=y_all.loc[cur.index])
    # 기준 B: z 하나 로지스틱 (같은 학습 쌍)
    X, y = st.pairs(work[work["year"] <= t].sort_values(["imo", "year"], kind="mergesort"))
    b = LogisticRegression(max_iter=2000).fit(X[["z"]], y)
    res["pB"] = b.predict_proba(cur[["position_z"]].rename(columns={"position_z": "z"}))[:, 1]
    res["pA"] = float(y[X["z"] >= 2.0].mean())     # 기준 A: 학습 쌍 중 점검 필요 배 유지율
    return res.dropna(subset=["y", "persist_prob"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="config/mrv_pipeline.yaml")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    cfg = load_config(a.config)
    df = load_snapshot(cfg).sort_values(["imo", "year"]).reset_index(drop=True)
    ctx = FitContext(cutoff_year=None, seed=0, thresholds=cfg["thresholds"], config=cfg)
    lift = 1.10
    rows = []
    if not a.strict:
        b = ModelBundle.train(df, cfg, until_stage=UPTO)
        work = b.run(df)
        y_all = labels(work, lift)
    for t in (2021, 2022, 2023, 2024):
        if a.strict:
            b = ModelBundle.train(df, cfg, cutoff_year=t, until_stage=UPTO)
            work = b.run(df)
            y_all = labels(work, lift)
        r = one_year(work, t, ctx, y_all)
        r["t"] = t
        rows.append(r)
        print(f"t={t}: 점검 필요 {len(r)}척 (라벨 있음), 실제 유지 {r['y'].mean():.1%}, 예측 평균 {r['persist_prob'].mean():.1%}", flush=True)
    R = pd.concat(rows)
    val, test = R[R["t"] <= 2023], R[R["t"] == 2024]
    for name, g in (("검증 2021~2023", val), ("시험 2024", test)):
        m, mA, mB = metrics(g["persist_prob"], g["y"]), metrics(g["pA"], g["y"]), metrics(g["pB"], g["y"])
        print(f"\n[{name}] 점검 필요 {m['n']}척")
        print(f"  모델  Brier {m['Brier']:.3f}  AUC {m['AUC']:.3f}  보정 {m['보정 오차%p']:.1f}%p  상위20 {m['상위20']:.1%}  하위20 {m['하위20']:.1%}  (실제 {m['실제 유지']:.1%}, 예측 평균 {m['예측 평균']:.1%})")
        print(f"  기준A Brier {mA['Brier']:.3f}   기준B Brier {mB['Brier']:.3f} AUC {mB['AUC']:.3f}")
        if name.startswith("시험"):
            gain = 1 - m["Brier"] / mA["Brier"]
            print(f"  판정: Brier A 대비 {gain:.1%} 낮음 {'통과' if gain >= .10 else '미통과'} · 보정 {m['보정 오차%p']:.1f}%p {'통과' if m['보정 오차%p'] <= 5 else '미통과'} · "
                  f"AUC B 보다 {'높음 통과' if m['AUC'] > mB['AUC'] else '낮음 미통과'} · 상위−하위 {(m['상위20'] - m['하위20']) * 100:.1f}%p {'통과' if m['상위20'] - m['하위20'] >= .2 else '미통과'}")
    if a.out:
        R.to_csv(a.out, index=False, encoding="utf-8-sig")
    return 0


if __name__ == "__main__":
    sys.exit(main())
