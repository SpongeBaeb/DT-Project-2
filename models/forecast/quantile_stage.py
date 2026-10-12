"""1~3년 예측 Stage — 회귀 v4(분위수 LightGBM + 배별 폭 + 보정 연도 z 표로 중심 보정)를 프레임워크 부품으로 옮긴 것.

같은 클래스를 목표 지표(level)만 바꿔 두 번 쓴다 (config 의 stages 에 두 줄):
  - level=sea_eff_kg_nm  prefix=fc    → 해상 효율(정박 제외) 예측. 진단·위치·'앞으로 어떻게 될지'용. 결과 표 `fc_h{h}_p{10,50,90}`
  - level=co2_per_nm_kg  prefix=fct   → 전체 효율(정박 포함) 예측. 비용·CII D·E 확률용.       결과 표 `fct_h{h}_p{10,50,90}`
왜 둘인가: 같은 조건 비교(엄격한 시간 분할)에서 각 모델은 자기 지표에서 가장 정확하다 (docs/decisions.md 2026-10-12,
experiments/A-1_forecast_features/compare_targets.py). 총량 모델의 해상 효율 환산은 '변화 없음' 수준이고,
해상 모델의 총량 환산은 정박 가정이 필요해 2~4.5% 나쁘다.

절차 (팀 04_final_v4.ipynb 셀 [2] 와 같음, 보정 연도 = 학습 데이터의 마지막 연도):
  기간 h 마다 (1) 목표 연도 ≤ 보정 연도−1 쌍으로 학습 → 보정 연도 쌍의 오차로 z 표
             (2) 목표 연도 ≤ 보정 연도 전체로 다시 학습 → 각 행에서 예측, z 표로 중심 보정. 대표값(p50) = 분포 중앙값.
규칙 지킴: 한 배의 값은 그 배의 같은 해·이전 해 행과 학습 때 고정한 분포(CrossSection)로만 계산 (한 척 = 전체, 미래 누수 없음).
          p10 ≤ p50 ≤ p90 은 구조상 보장 (z 표가 오름차순).
모델 파일은 번들(joblib)에 함께 저장된다. LightGBM 은 학습표의 마지막 자리 반올림에도 예측이 평균 3e-3 쯤 달라지는 잡음이 있다.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from contracts.tables import HORIZONS, P_DE_COLS, QUANTILES
from models.base import FitContext, Stage
from models.forecast import cii as cii_rules
from models.forecast import quantile as Q
from models.forecast.features import CAT, COVID, NUM, CrossSection, build_features, delta_clip_bounds, make_pairs

log = logging.getLogger("forecast")
MIN_PAIRS = 300            # 이보다 학습 쌍이 적은 기간은 예측하지 않는다 (결과는 빈칸)
CORE_REQUIRES = ("imo", "year", "year_eff", "ship_type", "dwt", "gt", "age", "fuel_t", "distance_nm", "sea_hours", "avg_speed_kn",
                 "berth_share", "eu_share", "cii_ratio_2026basis")


class QuantileForecast(Stage):
    def __init__(self, level: str = "sea_eff_kg_nm", prefix: str = "fc", clip_until_year: int = 2021, n_jobs: int | None = None,
                 cii: bool = False, **params):
        """n_jobs: LightGBM 스레드 수 (기본 전부). 표본처럼 작은 데이터는 1~2 가 훨씬 빠르다 (결과에는 영향 없음).
        cii: True 면 `p_de_h{h}` (h 년 뒤 CII 등급이 D·E 일 확률)도 만든다. CII 는 정박 포함 총량 기준이라
             level=co2_per_nm_kg 일 때만 뜻이 맞다 (아니면 ValueError)."""
        if cii and level != "co2_per_nm_kg":
            raise ValueError("CII D·E 확률은 정박 포함 거리당 CO₂(level=co2_per_nm_kg) 예측으로만 계산할 수 있다")
        super().__init__(level=level, prefix=prefix, clip_until_year=clip_until_year, n_jobs=n_jobs, cii=cii, **params)
        self.level, self.prefix, self.clip_until_year, self.n_jobs, self.cii = level, prefix, clip_until_year, n_jobs, cii
        self.requires = (*CORE_REQUIRES, level, *(("cii_ship_type",) if cii else ()))
        self.produces = (*(f"{prefix}_h{h}_p{q}" for h in HORIZONS for q in QUANTILES), *(P_DE_COLS if cii else ()))
        self.feats = NUM + CAT

    # ───────────────────────── 학습 ─────────────────────────
    def fit(self, train: pd.DataFrame, ctx: FitContext) -> "QuantileForecast":
        super().fit(train, ctx)
        df = train.sort_values(["imo", "year"], kind="mergesort").reset_index(drop=True)
        self.cross = CrossSection().fit(df)
        first = make_pairs(build_features(df, (-np.inf, np.inf), self.level, cross=self.cross), 1)
        upto = self.clip_until_year if (first["year"] <= self.clip_until_year).sum() >= MIN_PAIRS else int(first["year"].max())
        self.clip = delta_clip_bounds(first, upto)                      # 직전 해 변화를 자를 범위 (학습 쌍 변화의 1%·99%)
        f = build_features(df, self.clip, self.level, cross=self.cross)
        self.types = sorted(f["ship_type"].astype(str).unique())
        f["ship_type"] = pd.Categorical(f["ship_type"].astype(str), categories=self.types)
        self.base = int(df["year"].max())                                # 보정 연도
        params = {**Q.PW, "random_state": int(ctx.seed), **({"n_jobs": self.n_jobs} if self.n_jobs else {})}
        self.models: dict[int, list] = {}
        self.zq_raw: dict[int, np.ndarray] = {}
        self.n_pairs: dict[int, int] = {}
        for h in HORIZONS:
            p = make_pairs(f, h)
            p["ship_type"] = pd.Categorical(p["ship_type"].astype(str), categories=self.types)
            final = p[p["target_year"] <= self.base]
            calib_in, calib_at = p[p["target_year"] <= self.base - 1], p[p["target_year"] == self.base]
            self.n_pairs[h] = len(final)
            if len(final) < MIN_PAIRS or len(calib_in) < MIN_PAIRS or len(calib_at) < 20:
                log.warning("%s h=%d: 학습 쌍이 적어 예측하지 않음 (학습 %d, 보정 입력 %d, 보정 %d)", self.prefix, h, len(final), len(calib_in), len(calib_at))
                continue
            (Qc,) = Q.qfit(calib_in, [calib_at], self.feats, params=params)
            self.zq_raw[h] = Q.ztable(Qc, calib_at["delta"])
            _, self.models[h] = Q.qfit(final, [final.head(1)], self.feats, params=params, return_models=True)
        return self

    # ───────────────────────── 실행 ─────────────────────────
    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        out = pd.DataFrame(np.nan, index=df.index, columns=list(self.produces))
        if not self.models:
            return out
        d = df.sort_values(["imo", "year"], kind="mergesort")
        f = build_features(d, self.clip, self.level, cross=self.cross)
        f.index = d.index
        f["ship_type"] = pd.Categorical(f["ship_type"].astype(str), categories=self.types)
        lvl = f["level"].to_numpy(dtype=float)
        for h, models in self.models.items():
            x = f.assign(covid_next=f["year"].add(h).isin(COVID).astype(int))
            Qh = np.sort(np.column_stack([m.predict(x[self.feats]) for m in models]), axis=1)
            m, s, zq = Q.center(Qh, self.zq_raw[h])
            for q in QUANTILES:
                out.loc[f.index, f"{self.prefix}_h{h}_p{q}"] = lvl * np.exp(Q.quantile_at(zq, m, s, q / 100))
            if self.cii:                                                      # P(목표 연도 등급 ≥ D) = 1 − P(Δ ≤ 임계값)
                thr = cii_rules.threshold(d, f["year"].to_numpy() + h)
                out.loc[f.index, f"p_de_h{h}"] = 1 - Q.cdf(zq, m, s, thr)
        return out.loc[df.index]

    def describe(self) -> dict:
        d = super().describe()
        d["detail"] = {"level": self.level, "prefix": self.prefix, "base_year": self.base, "pairs": self.n_pairs, "horizons_fit": sorted(self.models)}
        return d
