"""1~3년 예측 — 기준 모델 '변화 없음' (5-2절 비교 기준).

p50 = 올해 해상 효율 그대로, p10/p90 = 학습 데이터에서 같은 선종 배들이 h년 동안 변한 비율의 10·90% 분위.

[담당: 장원우] LightGBM 분위 회귀는 models/forecast/ 에 새 클래스로 만들고 같은 produces 를 지킨다.
  - 입력: 같은 배의 올해·지난 해 값만 (미래 연도 금지)
  - 분위 교차 방지: 마지막에 enforce_monotone() 을 꼭 거친다
  - 결정성: LightGBM(deterministic=True, num_threads=1, seed=ctx.seed) — 결과 일치 테스트용
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from contracts.tables import FORECAST_COLS, HORIZONS, QUANTILES
from models.base import FitContext, Stage


def enforce_monotone(out: pd.DataFrame) -> pd.DataFrame:
    """각 h 에서 p10 ≤ p50 ≤ p90 이 되도록 정렬 (분위 교차 방지)."""
    out = out.copy()
    for h in HORIZONS:
        cols = [f"fc_h{h}_p{q}" for q in QUANTILES]
        out[cols] = np.sort(out[cols].to_numpy(dtype=float), axis=1)
    return out


class PersistenceForecast(Stage):
    requires = ("imo", "year", "ship_type", "sea_eff_kg_nm")
    produces = tuple(FORECAST_COLS)

    def fit(self, train: pd.DataFrame, ctx: FitContext) -> "PersistenceForecast":
        super().fit(train, ctx)
        ln = np.log(train.set_index(["imo", "year"])["sea_eff_kg_nm"])
        types = train.set_index(["imo", "year"])["ship_type"]
        self.q: dict[tuple[str, int], np.ndarray] = {}
        for h in HORIZONS:
            later = ln.copy()
            later.index = pd.MultiIndex.from_arrays([later.index.get_level_values(0), later.index.get_level_values(1) - h])
            change = (later - ln).dropna()
            t = types.reindex(change.index)
            for typ, ch in change.groupby(t):
                self.q[(typ, h)] = ch.quantile([q / 100 for q in QUANTILES]).to_numpy()
        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        base = df["sea_eff_kg_nm"].to_numpy(dtype=float)
        out = pd.DataFrame(index=df.index, columns=list(self.produces), dtype=float)
        for h in HORIZONS:
            qs = np.array([self.q.get((t, h), [np.nan] * len(QUANTILES)) for t in df["ship_type"]], dtype=float)
            for j, q in enumerate(QUANTILES):
                out[f"fc_h{h}_p{q}"] = base * (1.0 if q == 50 else np.exp(qs[:, j]))
        return enforce_monotone(out)
