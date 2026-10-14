"""공유 전처리 모듈: 학습(파이프라인·모델)과 API가 **같은 함수**를 쓴다 (기획서 6장, 7-5②).

여기 있는 계산을 다른 곳에서 다시 구현하지 않는다. 바꾸면 결과 일치 테스트(tests/parity)가 확인한다.
모든 함수는 순수 함수: 입력 표를 바꾸지 않고 새 표를 돌려준다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from contracts.tables import SHIP_YEAR, SHIP_YEAR_INPUT_COLS

FOSSIL_CO2_PER_FUEL_MIN = 3.11   # 화석 액체연료 연료 1톤당 CO₂ 최저값 (MGO 3.206, HFO 3.114, LNG 2.75)

DERIVED_COLS = [
    "distance_nm", "sea_eff_kg_nm", "avg_speed_kn", "berth_share", "eu_share", "co2_per_fuel",
    "alt_fuel", "age", "ln_dwt", "ln_sea_hours", "has_ice_class", "cii_attained",
]


def derive(df: pd.DataFrame) -> pd.DataFrame:
    """원본 보고값 + 제원 → 파생 변수. 결과는 SHIP_YEAR 약속의 파생 열을 채운다.

    distance_nm 이 이미 있으면(API 입력) 그대로 쓰고, 없으면 거리당 CO₂로 역산한다(MRV).
    """
    missing = [c for c in SHIP_YEAR_INPUT_COLS if c not in df.columns and not (c == "co2_per_nm_kg" and "distance_nm" in df.columns)]
    if missing:
        raise KeyError(f"derive() 입력에 필요한 열이 없습니다: {missing}")

    out = df.copy()
    co2 = out["co2_t"].astype(float)
    berth = out["berth_co2_t"].astype(float)

    if "distance_nm" in out.columns and out["distance_nm"].notna().all():
        dist = out["distance_nm"].astype(float)
        out["co2_per_nm_kg"] = co2 * 1000.0 / dist
    else:
        dist = co2 * 1000.0 / out["co2_per_nm_kg"].astype(float)
    out["distance_nm"] = dist

    out["sea_eff_kg_nm"] = (co2 - berth) * 1000.0 / dist
    out["avg_speed_kn"] = dist / out["sea_hours"].astype(float)
    out["berth_share"] = berth / co2

    intra = _col(out, "co2_intra_eu_t")
    out["eu_share"] = (intra / co2).clip(0, 1)

    fuel = _col(out, "fuel_t")
    out["co2_per_fuel"] = co2 / fuel
    out["alt_fuel"] = (FOSSIL_CO2_PER_FUEL_MIN - out["co2_per_fuel"]).clip(lower=0).fillna(0.0)

    out["age"] = (out["year"].astype(int) - out["build_year"].astype(int)).clip(lower=0).astype("int64")
    out["ln_dwt"] = np.log(out["dwt"].astype(float))
    out["ln_sea_hours"] = np.log(out["sea_hours"].astype(float))

    ice = _col(out, "ice_class", dtype=object)
    out["has_ice_class"] = ice.notna() & (ice.astype(str).str.strip() != "") & (ice.astype(str).str.lower() != "none")
    out["cii_attained"] = co2 * 1e6 / (out["dwt"].astype(float) * dist)
    return out


def ensure_schema_columns(df: pd.DataFrame) -> pd.DataFrame:
    """SHIP_YEAR 약속의 선택 열이 없으면 빈칸으로 채운다 (API 입력처럼 일부만 있는 경우)."""
    out = df.copy()
    for c in SHIP_YEAR.columns:
        if c.name not in out.columns:
            out[c.name] = {"float": np.nan, "int": pd.NA, "str": None, "bool": False}[c.kind]
            if c.kind == "float":
                out[c.name] = out[c.name].astype(float)
            elif c.kind == "str":
                out[c.name] = out[c.name].astype(object)
    return out


def _col(df: pd.DataFrame, name: str, dtype=float) -> pd.Series:
    if name in df.columns:
        return df[name].astype(dtype) if dtype is float else df[name]
    return pd.Series(np.nan if dtype is float else None, index=df.index, dtype=dtype)
