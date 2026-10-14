"""데이터 점검 규칙 (기획서 2-3 착시 신호, 5-7 불가능한 보고 값, 6장 입력 점검).

임계값은 config/default.yaml thresholds 에서 받는다. 규칙을 추가하면 RULES 에 한 줄 더한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd


@dataclass(frozen=True)
class Rule:
    code: str
    label: str
    ok: Callable[[pd.DataFrame, dict], pd.Series]   # True = 통과


def _speed_ok(df, t):
    return df["avg_speed_kn"] >= t["min_speed_kn"]


def _cargo_ok(df, t):
    return ~(df["cargo_t"].astype(float) > df["dwt"] * t["cargo_dwt_ratio_max"])


def _fuel_ok(df, t):
    r = df["co2_per_fuel"]
    return r.isna() | (r >= t["co2_per_fuel_min"])


def _sea_time_ok(df, t):
    return df["sea_hours"] >= t["short_sea_hours"]


RULES: tuple[Rule, ...] = (
    Rule("speed", "평균 속력 ≥ {min_speed_kn}노트", _speed_ok),
    Rule("cargo", "적재량 ≤ 재화중량×{cargo_dwt_ratio_max}", _cargo_ok),
    Rule("fuel", "연료 1톤당 CO₂ ≥ {co2_per_fuel_min} (화석연료 범위)", _fuel_ok),
    Rule("sea_time", "EU 해상 시간 ≥ {short_sea_hours}시간", _sea_time_ok),
)


def run_rules(df: pd.DataFrame, thresholds: dict) -> pd.DataFrame:
    """규칙별 통과 여부 표 (열 = rule code, 값 = bool)."""
    return pd.DataFrame({r.code: r.ok(df, thresholds).fillna(True).astype(bool) for r in RULES}, index=df.index)


def rule_label(code: str, thresholds: dict) -> str:
    for r in RULES:
        if r.code == code:
            return r.label.format(**thresholds)
    raise KeyError(code)


def illusion_signals(df: pd.DataFrame, thresholds: dict) -> pd.DataFrame:
    """착시 신호 5종 (sig_berth 는 정박 비교 결과 berth_z / berth_hist_z 가 있어야 함)."""
    rules = run_rules(df, thresholds)
    s = thresholds["berth_sigma"]
    sig = pd.DataFrame(index=df.index)
    sig["sig_berth"] = (df["berth_z"] >= s) | (df["berth_hist_z"].fillna(-float("inf")) >= s)
    sig["sig_short"] = ~rules["sea_time"]
    sig["sig_fuel"] = ~rules["fuel"]
    sig["sig_report"] = ~(rules["cargo"] & rules["speed"])
    ops = set(thresholds.get("special_operators", []))
    company = df["company"] if "company" in df.columns else pd.Series(None, index=df.index, dtype=object)
    sig["sig_special"] = company.isin(ops)
    sig = sig.astype(bool)
    sig["sig_any"] = sig.any(axis=1)
    return sig
