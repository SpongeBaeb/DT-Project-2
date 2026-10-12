"""CII D·E 확률의 규칙 부분 — 등급 경계와 감축률 (팀 파이프라인 `rules_mrv.py` 의 값을 그대로 쓴다).

CII = CO₂ ÷ (용량 × 거리) ∝ 거리당 CO₂(정박 포함). 그래서 D·E 확률은 **전체 효율**(정박 포함) 예측으로 계산한다.
목표 연도 y 에 등급이 D 이상(D·E)일 조건 (달성 CII ÷ 그해 기준선 ≥ D 경계, 기준선 = 기준선₀ × (1 − Z(y))):

    Δ ≥ ln(D 경계) − ln(달성 CII ÷ 기준선₀) + ln(1 − Z(y)/100)          Δ = ln(거리당 CO₂ 의 h 년 뒤 ÷ 지금)

  - D 경계 = `cii_params(CII 선종, dwt, gt)` 의 네 경계 중 셋째 (A/B, B/C, C/D, D/E 가 아니라 d1~d4 의 d3: 비율 ≥ d3 이면 D 이상)
  - 달성 CII ÷ 기준선₀ = cii_ratio_2026basis × (1 − Z(2026)/100)   (cii_ratio_2026basis = 달성 ÷ 2026년 기준선)
  - Z(y) = 감축률(%). 2026년까지는 팀 파이프라인 규칙, 2027·2028 은 MEPC.400(83) 값 (팀 reg_common.Z_PCT 와 같음)
확률 = 1 − P(Δ ≤ 임계값) — 임계값에서의 예측 분포 누적 (quantile.cdf, 양끝은 1%·99% 로 자름).
미달 확률(p_miss_h1)도 같은 형태: 다음 해 감축 요구 ln((1−Z(t+1))÷(1−Z(t))) 를 임계값으로 해서 P(Δ > 임계값).

팀 규칙 파일은 numpy·pandas 만 쓰므로 패키지 이름 충돌 없이 파일 경로로 불러온다 (vendor 원본은 고치지 않는다).
"""
from __future__ import annotations

import importlib.util
from functools import lru_cache

import numpy as np
import pandas as pd

from shared.config import ROOT

RULES_FILE = ROOT / "vendor" / "mrv_pipeline" / "pipeline" / "rules_mrv.py"
EXTRA_Z = {2027: 13.625, 2028: 16.25}          # MEPC.400(83) — 팀 reg_common.Z_PCT 와 같은 값


@lru_cache(maxsize=1)
def rules():
    """팀 규칙 모듈 (cii_params, Z, BASIS_YEAR)."""
    spec = importlib.util.spec_from_file_location("mrv_cii_rules", RULES_FILE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def z_pct() -> dict[int, float]:
    return {**rules().Z, **EXTRA_Z}


def d_boundary(cii_ship_type: pd.Series, dwt: pd.Series, gt: pd.Series) -> np.ndarray:
    """배마다 D 경계(비율이 이 값 이상이면 D·E). CII 선종이 없거나 모르면 NaN."""
    cp = rules().cii_params
    cache: dict[tuple, float] = {}
    out = np.full(len(cii_ship_type), np.nan)
    for i, (t, d, g) in enumerate(zip(cii_ship_type.to_numpy(), dwt.to_numpy(float), gt.to_numpy(float))):
        key = (t, d, g)
        if key not in cache:
            try:
                cache[key] = float(cp(t, d, g)[4][2]) if isinstance(t, str) else np.nan
            except (ValueError, TypeError):
                cache[key] = np.nan
        out[i] = cache[key]
    return out


def ln_attained_over_line(cii_ratio_2026basis: pd.Series) -> np.ndarray:
    """ln(달성 CII ÷ 기준선₀) = ln(cii_ratio_2026basis) + ln(1 − Z(2026)/100)."""
    z0 = z_pct()[rules().BASIS_YEAR] / 100
    r = cii_ratio_2026basis.to_numpy(float)
    return np.where(r > 0, np.log(np.where(r > 0, r, 1.0)), np.nan) + np.log(1 - z0)


def threshold(df: pd.DataFrame, target_year: np.ndarray | pd.Series) -> np.ndarray:
    """목표 연도에 D·E 가 되기 위한 최소 Δ (로그 변화). 필요한 값이 없거나 감축률을 모르는 해면 NaN."""
    z = z_pct()
    ty = np.asarray(target_year, dtype=int)
    zy = np.array([z.get(int(y), np.nan) for y in ty]) / 100
    d3 = d_boundary(df["cii_ship_type"], df["dwt"], df["gt"])
    return np.log(d3) - ln_attained_over_line(df["cii_ratio_2026basis"]) + np.log(1 - zy)


def miss_threshold(year: np.ndarray | pd.Series) -> np.ndarray:
    """다음 해 감축 요구를 채우려면 거리당 CO₂ 의 로그 변화가 이 값 이하여야 한다: ln((1 − Z(t+1)) ÷ (1 − Z(t))).
    미달 = Δ 가 이 값보다 큼 (요구보다 덜 줄였거나 늘림). 팀 reg_common.thr_miss 와 같다.
    t 가 감축률 표 첫 해(2019)보다 이르면 Z(t) = 0 (팀과 같음). t+1 의 감축률을 모르면 NaN."""
    z = z_pct()
    first = min(z)
    out = []
    for t in np.asarray(year, dtype=int):
        z0 = z.get(int(t), 0.0 if t < first else np.nan) / 100
        z1 = z.get(int(t) + 1, np.nan) / 100
        out.append(np.log((1 - z1) / (1 - z0)))
    return np.array(out, dtype=float)
