"""약속 3: 진단 결과 모양 (API 응답 = 웹 정적 JSON).

데이터에 있는 배(정적 JSON)와 사용자가 입력한 배(API 응답)가 **같은 DiagnosisResult** 를 쓴다.
그래서 웹 화면은 한 종류의 값만 그리면 되고, 결과 일치 테스트는 둘을 그대로 비교한다.
웹의 TypeScript 타입은 이 파일에서 자동 생성된다 (python tasks.py schema → web/src/api/schema.d.ts).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ─────────────────────────────── 요청 (내 선박 진단) ───────────────────────────────
class ShipStatic(_Model):
    imo: int | None = Field(None, description="있으면 기록용. 데이터 조회에는 쓰지 않음")
    name: str | None = None
    ship_type: str = Field(..., description="표준 선종 (GET /meta 의 ship_types)")
    dwt: float = Field(..., gt=0, description="재화중량 t")
    build_year: int = Field(..., ge=1950, le=2100)
    gt: float | None = Field(None, gt=0)
    length_m: float | None = Field(None, gt=0)
    ice_class: str | None = None
    eedi: float | None = Field(None, gt=0)
    eedi_kind: str | None = Field(None, description="설계 효율 지표 종류: EEDI | EEXI | EIV (값의 수준이 종류마다 달라 모델이 구분해 씀). 비우면 '없음'으로 처리")


class YearInput(_Model):
    year: int = Field(..., ge=2018, le=2100)
    co2_t: float = Field(..., gt=0, description="연간 CO₂ t (EU MRV 기준)")
    berth_co2_t: float = Field(..., ge=0, description="정박 중 CO₂ t")
    distance_nm: float = Field(..., gt=0, description="항해 거리 해리")
    sea_hours: float = Field(..., gt=0, description="해상 시간 h")
    fuel_t: float | None = Field(None, gt=0)
    co2_intra_eu_t: float | None = Field(None, ge=0)
    ets_co2_t: float | None = Field(None, ge=0)
    cargo_t: float | None = Field(None, ge=0)

    @model_validator(mode="after")
    def _berth_le_total(self):
        if self.berth_co2_t > self.co2_t:
            raise ValueError("정박 CO₂가 전체 CO₂보다 큽니다")
        return self


class DiagnoseRequest(_Model):
    ship: ShipStatic
    years: list[YearInput] = Field(..., min_length=1, description="1개 이상. 마지막 연도를 진단, 앞 연도는 이력(위치·예측)에 씀")
    mrv_basis_confirmed: bool = Field(False, description="입력값이 EU MRV 보고 기준임을 확인")

    @model_validator(mode="after")
    def _years_unique_sorted(self):
        ys = [y.year for y in self.years]
        if len(set(ys)) != len(ys):
            raise ValueError("연도가 중복되었습니다")
        self.years = sorted(self.years, key=lambda y: y.year)
        return self


# ─────────────────────────────── 결과 (공통) ───────────────────────────────
class Check(_Model):
    rule: str
    ok: bool
    detail: str = ""


class Cause(_Model):
    factor: str
    label: str
    log_contrib: float = Field(..., description="ln 단위 기여. 합 = ln(실제/동급 중간)")
    pct_points: float = Field(..., description="막대 표시용 근사 % (log_contrib×100)")


class SeaBlock(_Model):
    actual: float
    expected: float
    peer_median: float
    vs_peer_pct: float
    vs_expected_pct: float
    causes: list[Cause]


class BerthBlock(_Model):
    actual_t: float
    expected_t: float
    ratio: float
    z: float
    hist_min: float | None
    hist_max: float | None
    hist_z: float | None


class PositionBlock(_Model):
    z: float | None
    n_years: int
    cls: Literal["consistently_high", "typical", "consistently_low"]
    note: str = ""


class Signal(_Model):
    code: str
    label: str
    on: bool


class TypeBlock(_Model):
    exposure: int | None
    age_design: int | None
    ops_outlier: bool


class ForecastPoint(_Model):
    year: int
    p10: float | None
    p50: float | None
    p90: float | None


class DiagnosisResult(_Model):
    model_version: str
    data_hash: str
    imo: int | None
    year: int
    ship_type: str
    size_bin: int
    checks: list[Check]
    sea: SeaBlock
    berth: BerthBlock
    position: PositionBlock
    signals: list[Signal]
    types: TypeBlock
    forecast: list[ForecastPoint]
    warnings: list[str]


# ─────────────────────────────── 웹 정적 파일 ───────────────────────────────
class ShipInputs(_Model):
    """GET /ships/{imo}/inputs 와 정적 파일의 '불러오기' 값 = DiagnoseRequest 로 바로 보낼 수 있는 모양."""
    ship: ShipStatic
    years: list[YearInput]


class ShipFile(_Model):
    imo: int
    name: str | None
    former_names: list[str]
    ship_type: str
    company: str | None
    inputs: ShipInputs
    results: list[DiagnosisResult]


class IndexEntry(_Model):
    imo: int
    name: str | None
    former_names: list[str]
    ship_type: str
    dwt: float
    build_year: int
    last_year: int
    vs_peer_pct: float
    position_class: str
    sig_any: bool


class Meta(_Model):
    model_version: str
    data_hash: str
    result_table_version: str
    ship_types: list[str]
    train_years: list[int]
    created_at: str


class HealthResponse(_Model):
    status: Literal["ok"]
    model_version: str
    data_hash: str


class WhatIfSpeedRequest(_Model):
    ship_type: str
    sea_eff_kg_nm: float = Field(..., gt=0)
    speed_change_pct: float = Field(..., gt=-60, lt=60, description="예: -10 = 10% 감속")
    main_engine_share: float | None = Field(None, gt=0, lt=1, description="비우면 선종 기본값")


class WhatIfSpeedResponse(_Model):
    sea_eff_before: float
    sea_eff_after: float
    change_pct: float
    main_engine_share: float
    method: Literal["physics_rule"]
    note: str
