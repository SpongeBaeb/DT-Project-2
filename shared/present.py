"""결과 표 ↔ 화면용 모양(DiagnosisResult) 변환. 웹 정적 JSON 과 API 가 **이 함수 하나**를 쓴다.

  요청(DiagnoseRequest) ─request_to_frame─▶ SHIP_YEAR 행 ─derive─▶ ModelBundle.run ─▶ 결과 행 ─row_to_result─▶ 응답
  스냅샷 SHIP_YEAR ────────────────────────────────────▶ ModelBundle.run ─▶ 결과 표 ─row_to_result─▶ 정적 JSON
"""
from __future__ import annotations

import math
from typing import Any

import pandas as pd

from contracts.api import (
    BerthBlock, Cause, Check, DiagnoseRequest, DiagnosisResult, ForecastPoint, PositionBlock, SeaBlock, ShipInputs,
    ShipStatic, Signal, TypeBlock, YearInput,
)
from contracts.tables import CAUSE_FACTORS, HORIZONS, SIGNAL_COLS, SIGNAL_LABELS
from shared.checks import rule_label, run_rules
from shared.preprocess import derive, ensure_schema_columns

PLACEHOLDER_IMO = 1_000_000   # IMO 없이 입력한 배의 내부 키 (응답에서는 null)
USER_SOURCE = "user_input"


def _f(v: Any) -> float | None:
    if v is None or (isinstance(v, float) and math.isnan(v)) or v is pd.NA:
        return None
    return float(v)


# ───────────────────────── 요청 → 표 ─────────────────────────
def request_to_frame(req: DiagnoseRequest) -> pd.DataFrame:
    s = req.ship
    rows = []
    for y in req.years:
        rows.append({
            "imo": s.imo or PLACEHOLDER_IMO, "year": y.year, "name": s.name, "former_names": None,
            "ship_type": s.ship_type, "company": None,
            "fuel_t": y.fuel_t, "co2_t": y.co2_t, "berth_co2_t": y.berth_co2_t, "distance_nm": y.distance_nm,
            "sea_hours": y.sea_hours, "co2_intra_eu_t": y.co2_intra_eu_t, "ets_co2_t": y.ets_co2_t, "cargo_t": y.cargo_t,
            "dwt": s.dwt, "gt": s.gt, "length_m": s.length_m, "build_year": s.build_year,
            "ice_class": s.ice_class, "eedi": s.eedi, "source_version": USER_SOURCE,
        })
    df = pd.DataFrame(rows)
    for c in ("fuel_t", "co2_intra_eu_t", "ets_co2_t", "cargo_t", "gt", "length_m", "eedi"):
        df[c] = df[c].astype(float)
    for c in ("name", "former_names", "company", "ice_class"):
        df[c] = df[c].astype(object)
    return derive(ensure_schema_columns(df))


def frame_to_inputs(ship_rows: pd.DataFrame) -> ShipInputs:
    """스냅샷의 한 배 행들 → '불러오기' 값 (DiagnoseRequest 에 그대로 넣을 수 있는 모양)."""
    last = ship_rows.sort_values("year").iloc[-1]
    ship = ShipStatic(
        imo=int(last["imo"]), name=last["name"], ship_type=last["ship_type"], dwt=float(last["dwt"]),
        build_year=int(last["build_year"]), gt=_f(last["gt"]), length_m=_f(last["length_m"]),
        ice_class=last["ice_class"], eedi=_f(last["eedi"]),
    )
    years = [
        YearInput(
            year=int(r.year), co2_t=float(r.co2_t), berth_co2_t=float(r.berth_co2_t), distance_nm=float(r.distance_nm),
            sea_hours=float(r.sea_hours), fuel_t=_f(r.fuel_t), co2_intra_eu_t=_f(r.co2_intra_eu_t),
            ets_co2_t=_f(r.ets_co2_t), cargo_t=_f(r.cargo_t),
        )
        for r in ship_rows.sort_values("year").itertuples()
    ]
    return ShipInputs(ship=ship, years=years)


# ───────────────────────── 결과 행 → 화면 모양 ─────────────────────────
def row_to_result(
    row: pd.Series, inputs_row: pd.Series, meta: dict, thresholds: dict, *, imo_known: bool = True, mrv_confirmed: bool = True,
) -> DiagnosisResult:
    """row = 결과 표 한 행, inputs_row = 같은 배·연도의 SHIP_YEAR 행 (데이터 점검 표시용)."""
    rules = run_rules(inputs_row.to_frame().T.infer_objects(), thresholds).iloc[0]
    checks = [Check(rule=rule_label(code, thresholds), ok=bool(ok)) for code, ok in rules.items()]
    if inputs_row["source_version"] == USER_SOURCE:
        checks.append(Check(rule="EU MRV 보고 기준 값", ok=mrv_confirmed,
                            detail="" if mrv_confirmed else "확인하지 않음: 학습 데이터와 기준이 다를 수 있음"))

    causes = [Cause(factor=f, label=lbl, log_contrib=float(row[f"contrib_{f}"]), pct_points=float(row[f"contrib_{f}"]) * 100)
              for f, lbl in CAUSE_FACTORS.items()]

    n = int(row["position_n_years"])
    note = "" if n >= 2 else "한 해만 있어 위치는 참고용 (여러 해를 넣으면 더 믿을 만함)"

    y = int(row["year"])
    forecast = [ForecastPoint(year=y + h, p10=_f(row[f"fc_h{h}_p10"]), p50=_f(row[f"fc_h{h}_p50"]), p90=_f(row[f"fc_h{h}_p90"]))
                for h in HORIZONS]

    return DiagnosisResult(
        model_version=meta["model_version"], data_hash=meta["data_hash"],
        imo=int(row["imo"]) if imo_known else None, year=y, ship_type=row["ship_type"], size_bin=int(row["size_bin"]),
        checks=checks,
        sea=SeaBlock(actual=float(row["sea_eff_actual"]), expected=float(row["sea_eff_expected"]),
                     peer_median=float(row["sea_eff_peer_median"]), vs_peer_pct=float(row["vs_peer_pct"]),
                     vs_expected_pct=float(row["vs_expected_pct"]), causes=causes),
        berth=BerthBlock(actual_t=float(row["berth_actual_t"]), expected_t=float(row["berth_expected_t"]),
                         ratio=float(row["berth_ratio"]), z=float(row["berth_z"]), hist_min=_f(row["berth_ratio_hist_min"]),
                         hist_max=_f(row["berth_ratio_hist_max"]), hist_z=_f(row["berth_hist_z"])),
        position=PositionBlock(z=_f(row["position_z"]), n_years=n, cls=row["position_class"], note=note),
        signals=[Signal(code=c, label=SIGNAL_LABELS[c], on=bool(row[c])) for c in SIGNAL_COLS],
        types=TypeBlock(exposure=None if pd.isna(row["type_exposure"]) else int(row["type_exposure"]),
                        age_design=None if pd.isna(row["type_age_design"]) else int(row["type_age_design"]),
                        ops_outlier=bool(row["ops_outlier"])),
        forecast=forecast,
        warnings=[w for w in str(row["warnings"]).split(" | ") if w],
    )
