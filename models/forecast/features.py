"""예측 모델 피처 (회귀 v4) — 팀 노트북(v1 피처 단계)이 만든 `features_v1.csv` 의 36개 피처를 코드로 다시 만든 것.

정의는 `features_v1.csv` / `features_all_v1.csv`(스냅샷 3183d290 기준)와 열마다 수치를 대조해 확정했다
(experiments/A-1_forecast_features/verify_features.py). 한 배의 값은 그 배의 **같은 해와 이전 해** 행만으로 계산된다
(미래 연도 정보 없음) → 결과 표(전체)와 API(한 척)가 같다. 단 `level_pct`·`q_level_out` 은 같은 선종·연도의 다른 배와
비교한 값이라 학습 때의 선종·연도 분포를 고정해 쓰려면 Stage 에서 따로 다뤄야 한다 (모델 이식 단계에서 처리).

수준(level) 열
  - `sea_eff_kg_nm` (기본): 정박 제외 해상 효율. 기획서의 핵심 지표.
  - `co2_per_nm_kg`: 팀 v4 가 쓴 정박 포함 거리당 CO₂. 원본 재현 검증에만 쓴다.
  수준에 기대는 피처(ln_co2_per_nm, delta_prev_clip, trend3, dev_own, vol_past)가 이 열로 계산된다.
  이름은 원본과 맞추려고 `ln_co2_per_nm` 으로 둔다 (FEAT_KO 등 팀 코드와 호환).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

COVID = (2020, 2021)
SHORT_SEA_H = 336          # EU 해상 시간 14일 미만
SPEED_LOW_KN = 3.0         # 이 이하는 속력 이상
SPEED_HIGH_KN = 25.0       # 이 초과는 속력 이상 (고속선 근사 제외)
LEVEL_OUT_Z = 4.0          # (선종, 연도) 안에서 ln(CII 비율)의 MAD 기준 z
LOAD_FACTOR_CAP = 1.5

# 원본 features_meta.json 의 피처 순서 (31개) + 6단계 개선안에서 더한 5개
NUM_V1 = [
    "ship_age", "ln_dwt", "ln_gt", "ice_class_any", "hsc_proxy", "ln_co2_per_nm", "ln_fuel_t", "ln_distance", "ln_time_at_sea",
    "speed_kn", "berth_share", "intra_eu_share", "delta_prev_clip", "trend3", "speed_chg", "dist_chg", "ln_cii_ratio26",
    "level_pct", "covid_t", "covid_next", "mm_a", "mm_b", "mm_c", "q_short_sea", "q_speed_odd", "q_level_out",
    "co2_recovered", "co2_parts_bad", "type_changed", "has_prev", "has_trend3",
]
NUM_V2 = ["dev_own", "vol_past", "n_prev", "load_factor", "load_chg"]
NUM = NUM_V1 + NUM_V2
CAT = ["ship_type"]


def _ln(s: pd.Series) -> pd.Series:
    return np.log(s.where(s > 0).astype(float))


class CrossSection:
    """같은 선종·연도의 다른 배와 비교하는 두 피처(level_pct, q_level_out)를 학습 때 분포로 고정한다.

    cross 없이 build_features 를 부르면 넘겨받은 표 안에서 계산한다 (팀 원본 검증용). 모델(Stage)은 학습 때 이 분포를 저장해 두고
    한 척만 넣어도 같은 값이 나오게 한다 (API 한 척 = 결과 표). 학습에 없는 연도는 마지막 학습 연도 분포를 쓴다 (year_eff 규칙).
    학습 행 자신의 값은 pandas rank(pct=True)(평균 순위 ÷ n)와 같다.
    """

    def fit(self, df: pd.DataFrame) -> "CrossSection":
        yr = df["year_eff"] if "year_eff" in df.columns else df["year"]
        self.first, self.last = int(yr.min()), int(yr.max())
        ratio = df["cii_ratio_2026basis"].astype(float)
        self.sorted: dict[tuple, np.ndarray] = {}
        self.med: dict[tuple, float] = {}
        self.mad: dict[tuple, float] = {}
        ln = _ln(ratio)
        for k, g in ratio.groupby([df["ship_type"], yr]):
            self.sorted[k] = np.sort(g.dropna().to_numpy())
        for k, g in ln.groupby([df["ship_type"], yr]):
            med = float(g.median())
            self.med[k], self.mad[k] = med, float((g - med).abs().median())
        return self

    def _year(self, df: pd.DataFrame) -> pd.Series:
        yr = df["year_eff"] if "year_eff" in df.columns else df["year"]
        return yr.clip(lower=self.first, upper=self.last).astype(int)

    def level_pct(self, df: pd.DataFrame) -> pd.Series:
        out = pd.Series(np.nan, index=df.index)
        x = df["cii_ratio_2026basis"].astype(float)
        for k, idx in df.groupby([df["ship_type"], self._year(df)]).groups.items():
            arr = self.sorted.get(k)
            if arr is None or len(arr) == 0:
                continue
            v = x.loc[idx].to_numpy()
            less, right = np.searchsorted(arr, v, side="left"), np.searchsorted(arr, v, side="right")
            out.loc[idx] = np.where(np.isnan(v), np.nan, (less + (right - less + 1) / 2) / len(arr))
        return out

    def level_out(self, df: pd.DataFrame) -> pd.Series:
        lc = _ln(df["cii_ratio_2026basis"].astype(float))
        key = list(zip(df["ship_type"], self._year(df)))
        med = pd.Series([self.med.get(k, np.nan) for k in key], index=df.index)
        mad = pd.Series([self.mad.get(k, np.nan) for k in key], index=df.index)
        return (((lc - med).abs() / (1.4826 * mad)) > LEVEL_OUT_Z).astype(float)


def build_features(df: pd.DataFrame, clip: tuple[float, float], level: str = "sea_eff_kg_nm", cross: "CrossSection | None" = None) -> pd.DataFrame:
    """배·연도 표(SHIP_YEAR 모양, derive 가 끝난 것) → 배·연도마다 한 줄의 피처 표 (NUM + CAT 열과 수준 `level` 포함).

    clip = 직전 해 변화(delta_prev_clip, vol_past)를 자를 (하한, 상한). 학습 쌍 변화의 1%·99% 분위수로 학습 때 정한다.
    행은 (imo, year) 순으로 돌려준다. 행을 버리지 않는다.
    """
    d = df.sort_values(["imo", "year"], kind="mergesort").reset_index(drop=True).copy()
    lo, hi = clip
    lvl = d[level].astype(float)
    ln_c = _ln(lvl)
    d["_ln_c"] = ln_c
    g = d.groupby("imo", sort=False)
    gap1 = g["year"].diff() == 1
    gap2 = g["year"].diff(2) == 2

    out = pd.DataFrame({"imo": d["imo"], "year": d["year"], "ship_type": d["ship_type"], "level": lvl}, index=d.index)
    out["ship_age"] = d["age"].astype(float)
    out["ln_dwt"] = _ln(d["dwt"])
    out["ln_gt"] = _ln(d["gt"])
    ice = d["ice_class"].astype(object)
    out["ice_class_any"] = (ice.notna() & (ice.astype(str).str.strip() != "")).astype(float)
    out["hsc_proxy"] = d["hsc_proxy"].astype(float)
    out["ln_co2_per_nm"] = ln_c
    out["ln_fuel_t"] = _ln(d["fuel_t"])
    out["ln_distance"] = _ln(d["distance_nm"])
    out["ln_time_at_sea"] = _ln(d["sea_hours"])
    out["speed_kn"] = d["avg_speed_kn"].astype(float)
    # 항해 유형별 CO₂ 합이 총량과 안 맞는 행(co2_parts_bad)은 비중을 믿을 수 없어 비워 둔다 (팀 파이프라인과 같음)
    parts_bad = d["co2_parts_bad"].astype(bool)
    out["berth_share"] = d["berth_share"].astype(float).where(~parts_bad)
    out["intra_eu_share"] = d["eu_share"].astype(float).where(~parts_bad)

    prev_d = (ln_c - g["_ln_c"].shift(1)).where(gap1)                     # 직전 해 변화 (연속한 해일 때만)
    out["delta_prev_clip"] = prev_d.clip(lo, hi)
    out["trend3"] = ((ln_c - g["_ln_c"].shift(2)) / 2).where(gap2)        # 최근 두 번 변화의 평균 (3년 연속일 때만)
    ln_speed, ln_dist = _ln(out["speed_kn"]), out["ln_distance"]
    out["speed_chg"] = (ln_speed - ln_speed.groupby(d["imo"], sort=False).shift(1)).where(gap1)
    out["dist_chg"] = (ln_dist - ln_dist.groupby(d["imo"], sort=False).shift(1)).where(gap1)

    ratio = d["cii_ratio_2026basis"].astype(float)
    out["ln_cii_ratio26"] = _ln(ratio)
    out["level_pct"] = ratio.groupby([d["ship_type"], d["year"]]).rank(pct=True) if cross is None else cross.level_pct(d)     # 선종·연도 안 CII 비율 백분위
    out["covid_t"] = d["year"].isin(COVID).astype(int)
    out["covid_next"] = (d["year"] + 1).isin(COVID).astype(int)           # 기본은 1년 뒤. 다른 기간은 make_pairs 가 다시 채운다
    for c in ("mm_a", "mm_b", "mm_c"):
        out[c] = d[c].astype(float)

    out["q_short_sea"] = (d["sea_hours"] < SHORT_SEA_H).astype(float)
    out["q_speed_odd"] = ((out["speed_kn"] <= SPEED_LOW_KN) | ((out["speed_kn"] > SPEED_HIGH_KN) & (d["hsc_proxy"] == 0))).astype(float)
    lc = out["ln_cii_ratio26"]
    if cross is None:
        grp = lc.groupby([d["ship_type"], d["year"]])
        med = grp.transform("median")
        mad = (lc - med).abs().groupby([d["ship_type"], d["year"]]).transform("median")
        out["q_level_out"] = (((lc - med).abs() / (1.4826 * mad)) > LEVEL_OUT_Z).astype(float)
    else:
        out["q_level_out"] = cross.level_out(d)
    out["co2_recovered"] = d["co2_recovered"].astype(float)
    out["co2_parts_bad"] = d["co2_parts_bad"].astype(float)
    out["type_changed"] = d["cii_type_changed"].astype(float)
    out["has_prev"] = prev_d.notna().astype(int)
    out["has_trend3"] = out["trend3"].notna().astype(int)

    # 6단계 개선안 피처: 같은 배의 같은 해와 이전 해 값만 사용
    out["n_prev"] = g.cumcount()
    own_mean_prev = g["_ln_c"].transform(lambda s: s.expanding().mean().shift(1))
    out["dev_own"] = ln_c - own_mean_prev
    absd = prev_d.clip(lo, hi).abs()
    out["vol_past"] = absd.groupby(d["imo"], sort=False).transform(lambda s: s.expanding().mean())
    load = d["avg_load"].astype(float)
    ok = load.gt(0) & ~d["avg_load_invalid"].fillna(False).astype(bool)
    ln_load = _ln(load.where(ok))
    out["load_chg"] = (ln_load - ln_load.groupby(d["imo"], sort=False).shift(1)).where(gap1)
    basis = d["avg_load_basis"].astype(object)
    out["load_factor"] = (load / d["dwt"].astype(float)).where(ok & basis.isin(["mass", "dwt"])).clip(upper=LOAD_FACTOR_CAP)
    return out


def make_pairs(feat: pd.DataFrame, h: int) -> pd.DataFrame:
    """기간 h 의 학습 쌍: (배, 출발 연도 t, 목표 연도 t+h). delta = ln(목표 연도 수준) − ln(t 연도 수준).
    중간 연도 보고는 요구하지 않는다. 목표 연도 값이 없는 행(마지막 h 년)은 포함하지 않는다."""
    nxt = feat[["imo", "year", "level"]].assign(year=lambda t: t["year"] - h).rename(columns={"level": "level_next"})
    p = feat.merge(nxt, on=["imo", "year"], how="inner", validate="one_to_one")
    p["delta"] = np.log(p["level_next"]) - np.log(p["level"])
    p["h"], p["target_year"] = h, p["year"] + h
    p["covid_next"] = p["target_year"].isin(COVID).astype(int)
    return p.reset_index(drop=True)


def delta_clip_bounds(pairs: pd.DataFrame, train_until_year: int) -> tuple[float, float]:
    """직전 해 변화를 자를 범위 = 학습 쌍(출발 연도 ≤ train_until_year) 변화의 1%·99% 분위수 (원본 target_meta 의 clip)."""
    t = pairs.loc[pairs["year"] <= train_until_year, "delta"]
    lo, hi = np.quantile(t, [0.01, 0.99])
    return float(lo), float(hi)
