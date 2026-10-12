"""분위수 회귀 예측 (회귀 v4) — 팀 `03_regression/reg_common.py` 의 v4 함수(qfit, w_*)를 그대로 옮긴 것.

방법 (원우 님 forecast_v6 → 회귀 v4):
  Δ = m + s·z.  m = 50% 분위 예측, s = (90% − 10%) ÷ Z80 (배별 폭),
  z = 보정 연도의 표준화 오차 (실제 − 50%) ÷ 폭 의 경험분포(50개 분위).
  z 중앙값이 0 이 되게 옮기고 그만큼 m 을 옮겨 → 대표값 = 분포의 중앙값.
기간 h 마다 (1) 목표 연도 ≤ 보정 연도−1 쌍으로 학습해 보정 연도 오차로 z 표를 만들고,
            (2) 목표 연도 ≤ 보정 연도 전체로 다시 학습해 예측한 뒤 z 표로 중심을 보정한다.

원본과 같은 값을 내는지는 experiments/A-1_forecast_features/verify_forecast.py 가 팀의 forecast_v4.csv 와 대조한다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

QW = (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95)
QC = ["q05", "q10", "q25", "q50", "q75", "q90", "q95"]
PW = dict(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=50, subsample=0.8, subsample_freq=1,
          colsample_bytree=0.8, random_state=0, verbose=-1, n_jobs=-1)
Z80 = 2.5631                     # 정규분포 10%·90% 분위 사이 폭 ÷ σ
LV = (np.arange(50) + 0.5) / 50  # z 표의 분위 수준 50개


def qfit(trn: pd.DataFrame, Xs: list[pd.DataFrame], feats: list[str], *, params: dict | None = None, return_models: bool = False):
    """분위수(QW)마다 LightGBM 을 따로 학습 → 각 X 에 대해 (n, 7) 예측. 행마다 오름차순 정렬(분위수 교차 제거)."""
    import lightgbm as lgb
    outs = [np.zeros((len(X), len(QW))) for X in Xs]
    models = []
    for j, q in enumerate(QW):
        m = lgb.LGBMRegressor(objective="quantile", alpha=q, **(params or PW)).fit(trn[feats], trn["delta"].to_numpy())
        models.append(m)
        for o, X in zip(outs, Xs):
            o[:, j] = m.predict(X[feats])
    outs = [np.sort(o, axis=1) for o in outs]
    return (outs, models) if return_models else outs


def scale(Q: np.ndarray) -> np.ndarray:
    """배별 폭 s = (90% − 10%) ÷ Z80. 너무 좁은 폭은 1e-3 으로 바닥."""
    return np.maximum((Q[:, 5] - Q[:, 1]) / Z80, 1e-3)


def ztable(Qc: np.ndarray, y_calib) -> np.ndarray:
    """보정 연도의 표준화 오차 (실제 − 50%) ÷ 폭 → 50개 분위."""
    return np.quantile((np.asarray(y_calib) - Qc[:, 3]) / scale(Qc), LV)


def center(Q: np.ndarray, zq: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """대표값 m(분포 중앙값), 폭 s, 중앙값을 0 으로 옮긴 z 표."""
    m, s = Q[:, 3], scale(Q)
    z50 = float(np.interp(0.5, LV, zq))
    return m + s * z50, s, zq - z50


def cdf(zq: np.ndarray, m: np.ndarray, s: np.ndarray, x) -> np.ndarray:
    """P(Δ ≤ x). 표 밖은 1%·99% 로 자른다."""
    return np.interp((np.asarray(x, float) - m) / s, zq, LV, left=0.01, right=0.99)


def quantile_at(zq: np.ndarray, m: np.ndarray, s: np.ndarray, p: float) -> np.ndarray:
    return m + s * float(np.interp(p, LV, zq))


def mean_factor(zq: np.ndarray, s: np.ndarray) -> np.ndarray:
    """E[exp(Δ)] ÷ exp(m) = 평균(exp(s·z)) (z 표 50개 분위를 고르게). 합계·기댓값용."""
    return np.exp(np.outer(s, zq)).mean(axis=1)
