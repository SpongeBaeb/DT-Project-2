"""팀원 사이에 주고받는 표 2개의 약속 (기획서 7-4절).

  파이프라인 ──SHIP_YEAR──▶ 모델들 ──RESULT_TABLE──▶ 웹 JSON / API

규칙
- 열 추가: 버전 x.(y+1)   이름·단위·뜻 변경: (x+1).0   → 바꾸면 받는 사람에게 알린다.
- 단위는 열 이름 끝에 붙인다: _t(톤), _kg_nm(kg CO₂/해리), _nm(해리), _kn(노트), _pct(%)
"""
from __future__ import annotations

from contracts.schema import Column as C
from contracts.schema import TableSchema

# ───────────────────────────── 원인 막대 (기획서 3-1 ②) ─────────────────────────────
# 해상 효율의 동급 대비 차이 ln(실제/동급 중간)을 아래 요인별로 나눈다.
# 약속: 모든 contrib_* 의 합 == ln(sea_eff_actual / sea_eff_peer_median)  (오차 1e-9)
#   - unexplained = ln(실제 / 같은 조건 예측)
#   - 나머지 요인 합 = ln(같은 조건 예측 / 동급 중간)
#   - other = 모델이 특정 요인에 배분하지 못한 나머지 (모델 상수·동급 기준 차이 등)
CAUSE_FACTORS: dict[str, str] = {
    "size": "크기(같은 4분위 안)",
    "speed_pattern": "평균 속력(대기 포함)",
    "sea_time": "해상 시간",
    "eu_exposure": "EU 역내 비중",
    "age_design": "선령·설계",
    "fuel": "대체연료",
    "ice": "내빙 등급",
    "other": "기타 보정",
    "unexplained": "설명되지 않는 부분",
}
CONTRIB_COLS = [f"contrib_{f}" for f in CAUSE_FACTORS]

SIGNAL_COLS = ["sig_berth", "sig_short", "sig_fuel", "sig_report", "sig_special"]
SIGNAL_LABELS = {
    "sig_berth": "정박 배출이 같은 조건·예년보다 2σ 이상",
    "sig_short": "EU 해상 시간 500시간 미만",
    "sig_fuel": "연료 1톤당 CO₂가 화석연료 범위 밖",
    "sig_report": "보고 값이 물리적으로 불가능",
    "sig_special": "특수 운항 집단",
}

HORIZONS = (1, 2, 3)
QUANTILES = (10, 50, 90)
FORECAST_COLS = [f"fc_h{h}_p{q}" for h in HORIZONS for q in QUANTILES]
# 전체 효율(정박 포함 거리당 CO₂) 예측 — 비용·CII D·E 확률용. 선택 열: 이 예측 부품이 없는 설정에서는 빈칸으로 채워진다
TOTAL_FORECAST_COLS = [f"fct_h{h}_p{q}" for h in HORIZONS for q in QUANTILES]
# CII 등급이 h 년 뒤 D·E 일 확률 (전체 효율 예측 + 등급 경계·감축률). 선택 열
P_DE_COLS = [f"p_de_h{h}" for h in HORIZONS]


# ───────────────────── 약속 1: 통합 데이터 (파이프라인 → 모델) ─────────────────────
SHIP_YEAR = TableSchema(
    name="ship_year",
    version="1.2",
    key=("imo", "year"),
    desc="MRV 연도별 보고 + 선박 제원을 IMO로 이은 배·연도 표. 파생 변수는 shared/preprocess.derive() 가 만든다.",
    columns=(
        # 식별
        C("imo", "int", desc="IMO 번호", nullable=False, min=1_000_000, max=9_999_999),
        C("year", "int", desc="보고 연도", nullable=False, min=2018, max=2100),
        C("name", "str", desc="그해 보고 선박명"),
        C("former_names", "str", desc="이전 이름들, ' | ' 로 연결 (검색용)"),
        C("ship_type", "str", desc="표준 선종 (config data.ship_types)", nullable=False),
        C("company", "str", desc="관리회사 (2024 보고분부터, 과거 연도는 최근 값 연결)"),
        # 원본 보고값
        C("fuel_t", "float", "t", "연간 연료 소비량", min=0),
        C("co2_t", "float", "t", "연간 CO₂ 총량", nullable=False, min=0),
        C("berth_co2_t", "float", "t", "정박 중 CO₂", nullable=False, min=0),
        C("co2_per_nm_kg", "float", "kg/nm", "보고된 거리당 CO₂", nullable=False, min=0),
        C("sea_hours", "float", "h", "EU 관련 해상 시간", nullable=False, min=0),
        C("co2_intra_eu_t", "float", "t", "EU 역내 항해 CO₂"),
        C("ets_co2_t", "float", "t", "ETS 대상 CO₂ (2024~)"),
        C("cargo_t", "float", "t", "평균 적재량"),
        # 제원 (외부 수집)
        C("dwt", "float", "t", "재화중량", nullable=False, min=0),
        C("gt", "float", "", "총톤수"),
        C("length_m", "float", "m", "길이"),
        C("build_year", "int", desc="건조연도", nullable=False, min=1950, max=2100),
        C("ice_class", "str", desc="내빙 등급 (없으면 빈칸)"),
        C("eedi", "float", "gCO₂/t·nm", "설계 효율 지표 값 (종류는 eedi_kind)"),
        C("eedi_kind", "str", desc="설계 효율 지표 종류: EEDI | EEXI | EIV 등 (값이 없으면 빈칸). 값의 수준이 종류마다 달라 모델이 구분해 쓴다"),
        C("cii_ship_type", "str", desc="CII 선종 구분 (팀 파이프라인 10단계)"),
        C("cii_capacity", "float", desc="CII 용량: 선종에 따라 재화중량 또는 총톤수 (팀 파이프라인 10단계)", min=0),
        C("hsc_proxy", "bool", desc="고속선 추정 (로팩스 등, 팀 파이프라인 10단계)", nullable=False),
        C("fuel_group", "str", desc="연료 그룹: 석유계 | LNG 계열 | LPG 추정 | 기타 대체연료 | 대체연료(구분 불가) (팀 파이프라인 8-4)"),
        # 예측 모델이 쓰는 품질·CII·적재량 열 (팀 파이프라인 결과)
        C("mm_a", "bool", desc="측정 방식 A (MRV 모니터링 방식)", nullable=False),
        C("mm_b", "bool", desc="측정 방식 B", nullable=False),
        C("mm_c", "bool", desc="측정 방식 C", nullable=False),
        C("co2_recovered", "bool", desc="총 CO₂ 보정 이력 (팀 파이프라인 3-4)", nullable=False),
        C("co2_parts_bad", "bool", desc="항해 유형별 CO₂ 합이 총량과 안 맞음", nullable=False),
        C("cii_type_changed", "bool", desc="전년 대비 CII 선종 구분이 바뀜", nullable=False),
        C("cii_ratio_2026basis", "float", desc="2026년 기준선 대비 달성 CII 비율 (1 = 기준선, 낮을수록 좋음)", min=0),
        C("cii_rating", "str", desc="그해 기준 CII 등급 A~E"),
        C("cii_rating_2026basis", "str", desc="2026년 기준 CII 등급 A~E"),
        C("avg_load", "float", desc="평균 적재량 (기준은 avg_load_basis: 톤, 부피, 인원 등)", min=0),
        C("avg_load_basis", "str", desc="avg_load 의 기준: mass | dwt | volume 등"),
        C("avg_load_invalid", "bool", desc="적재량이 실을 수 있는 양을 넘는 등 유효하지 않음", nullable=False),
        # 파생 (shared/preprocess.derive)
        C("distance_nm", "float", "nm", "항해 거리 = co2_t×1000 ÷ co2_per_nm_kg (역산)", nullable=False, min=0),
        C("sea_eff_kg_nm", "float", "kg/nm", "해상 효율 = (CO₂−정박 CO₂)×1000 ÷ 거리. 핵심 지표", nullable=False, min=0),
        C("avg_speed_kn", "float", "kn", "평균 속력 = 거리 ÷ 해상 시간 (대기 포함, 역산)", nullable=False, min=0),
        C("berth_share", "float", "", "정박 CO₂ ÷ 전체 CO₂", nullable=False, min=0, max=1),
        C("eu_share", "float", "", "EU 역내 CO₂ ÷ 전체 CO₂", min=0, max=1),
        C("co2_per_fuel", "float", "t/t", "연료 1톤당 CO₂ (연료 추정용)"),
        C("alt_fuel", "float", "", "대체연료 추정 변수 = max(0, 3.11 − co2_per_fuel)", nullable=False, min=0),
        C("age", "int", "년", "선령 = year − build_year", nullable=False, min=0),
        C("ln_dwt", "float", "", "ln(재화중량)", nullable=False),
        C("ln_sea_hours", "float", "", "ln(해상 시간)", nullable=False),
        C("has_ice_class", "bool", desc="내빙 등급 보유", nullable=False),
        C("cii_attained", "float", "g/(t·nm)", "CII 근사 = CO₂ ÷ (재화중량 × 거리). 배경 비교용"),
        # 출처
        C("source_version", "str", desc="원본 파일 판 번호", nullable=False),
    ),
)

# 모델·API 입력으로 반드시 있어야 하는 원본 열 (파생 열은 derive()가 만든다)
SHIP_YEAR_INPUT_COLS = [
    "imo", "year", "ship_type", "co2_t", "berth_co2_t", "co2_per_nm_kg", "sea_hours", "dwt", "build_year",
]


# ──────────────────── 약속 2: 결과 표 (모델 → 웹 JSON / API) ────────────────────
_result_cols = [
    C("imo", "int", desc="IMO 번호", nullable=False),
    C("year", "int", desc="보고 연도", nullable=False),
    C("ship_type", "str", desc="표준 선종", nullable=False),
    C("size_bin", "int", desc="같은 선종·연도 안 재화중량 4분위 (1~4, 학습 때 경계 고정)", nullable=False, min=1, max=4),
    # 해상 효율 비교
    C("sea_eff_actual", "float", "kg/nm", "해상 효율 실제", nullable=False, min=0),
    C("sea_eff_expected", "float", "kg/nm", "같은 조건 예측값", nullable=False, min=0),
    C("sea_eff_peer_median", "float", "kg/nm", "동급 중간 (선종·연도·4분위)", nullable=False, min=0),
    C("vs_peer_pct", "float", "%", "동급 중간 대비 (실제/동급−1)×100", nullable=False),
    C("vs_expected_pct", "float", "%", "같은 조건 대비 (실제/예측−1)×100", nullable=False),
    *[C(c, "float", "log", f"원인 막대: {CAUSE_FACTORS[c[8:]]}", nullable=False) for c in CONTRIB_COLS],
    # 정박 배출 비교 (5-1절)
    C("berth_actual_t", "float", "t", "정박 CO₂ 실제", nullable=False, min=0),
    C("berth_expected_t", "float", "t", "같은 조건 정박 CO₂ 예측", nullable=False, min=0),
    C("berth_ratio", "float", "배", "실제 ÷ 예측", nullable=False, min=0),
    C("berth_z", "float", "σ", "같은 조건 대비 정박 배출 표준 점수 (선종 안)", nullable=False),
    C("berth_ratio_hist_min", "float", "배", "이 배의 지난 해들 배수 최소 (지난 해 없으면 빈칸)"),
    C("berth_ratio_hist_max", "float", "배", "이 배의 지난 해들 배수 최대"),
    C("berth_hist_z", "float", "σ", "이 배 예년 대비 표준 점수 (지난 해 2개 미만이면 빈칸)"),
    # 위치 (여러 해 누적)
    C("position_z", "float", "σ", "같은 조건 대비 차이를 그해까지 누적·축소한 선종 내 표준 점수"),
    C("position_n_years", "int", "년", "위치 계산에 쓴 연수", nullable=False, min=1),
    C("position_class", "str", desc="consistently_high | typical | consistently_low", nullable=False),
    # 착시 신호 (2-3절)
    *[C(c, "bool", desc=SIGNAL_LABELS[c], nullable=False) for c in SIGNAL_COLS],
    C("sig_any", "bool", desc="착시 신호 하나 이상", nullable=False),
    # 선박 유형 (5-4절)
    C("type_exposure", "int", desc="EU 규제 노출도 유형 1~3", min=1, max=3),
    C("type_age_design", "int", desc="선령·설계 유형 1~3", min=1, max=3),
    C("ops_outlier", "bool", desc="운항 군집 어느 중심에서도 먼 배", nullable=False),
    # 1~3년 예측 (해상 효율, 분위 p10/p50/p90 은 p10 ≤ p50 ≤ p90 보장)
    *[C(c, "float", "kg/nm", f"{c[4]}년 뒤 해상 효율 {c[-3:]}", min=0) for c in FORECAST_COLS],
    # 1~3년 예측 (정박 포함 거리당 CO₂, 같은 분위). 선택 열 (비용·CII 용)
    *[C(c, "float", "kg/nm", f"{c[5]}년 뒤 전체 효율(정박 포함 거리당 CO₂) {c[-3:]}", min=0) for c in TOTAL_FORECAST_COLS],
    # CII 등급이 h 년 뒤 D·E 일 확률 (0.01~0.99: 예측 분포 양끝을 1%·99% 로 자름). 선택 열
    *[C(c, "float", "", f"{c[-1]}년 뒤 CII 등급이 D·E 일 확률", min=0, max=1) for c in P_DE_COLS],
    # 기록
    C("warnings", "str", desc="이 행의 경고, ' | ' 로 연결 (없으면 빈 문자열)", nullable=False),
]

RESULT_TABLE = TableSchema(
    name="result_table",
    version="2.2",
    key=("imo", "year"),
    desc="배·연도별 기준·원인·위치·신호·예측. 웹 JSON과 진단 API는 이 표에서 만들어진다.",
    columns=tuple(_result_cols),
)

ALL_TABLES = (SHIP_YEAR, RESULT_TABLE)
