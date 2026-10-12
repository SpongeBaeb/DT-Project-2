"""MRV 전처리 규칙 — notebooks/01_merge_preprocess_v10.ipynb (v10, 최종)을 그대로 옮긴 파일.

노트북이 바뀌면 이 파일만 고치면 된다. 각 함수 위의 [셀 번호]가 노트북 셀과 1:1로 대응한다.
옮기지 않은 셀: 분석·확인용 출력만 하는 셀 (1-2~1-4, 2-4~2-6, 2-8, 3-1 일부, 3-3, 4-1, 4-2, 4-4, 4-6,
5-1, 5-4, 7-1~7-3, 8-4). 이 셀들은 값을 바꾸지 않는다.

노트북과 다른 점 (자동화를 위해 일반화한 부분, 규칙 내용은 같음)
- 1-5 Partial ERs 읽기: 노트북은 (2024, 2025)로 고정 → 신양식 연도 전체(NEW_FORMAT_FROM 이후)로 확장
- 2-3 매핑 점검: 노트북은 출력만 → 예상과 다르면 예외를 내서 파이프라인을 멈춤
- 노트북의 assert(3-4 계수 반올림 연도, ⑤-6 예외 목록, 8-1 연료 중복 판정)는 RuleCheckFailed로 바꿈
  → 노트북이 멈췄을 상황에서 파이프라인도 '확인 필요'(종료 코드 2)로 멈추고 이유를 리포트에 남김
- 출력/로그 문장은 대부분 생략하고, 숫자는 stats 딕셔너리로 모아 실행 리포트에 기록

변경 이력: v7 → v8 (3-4 두 근거 확인·계수 반올림 보정, ⑤-5·⑤-6 추가, 8-1 단일 연료 톤 기준, 8-7 설명)
          v8 → v10 (1~8단계 코드 변경 없음. 9단계 제원 통합, 10단계 CII 등급, 11단계 통합 열 사전 추가)
          노트북 assert 추가분(9-4 행 순서·MRV 열 보존, 10-1 선종 대응, 10-3 내빙 등급 대응, 10-4 달성값 확인,
          11-1 열 사전)도 RuleCheckFailed로 바꿈
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", message="Workbook contains no default style")   # 노트북 1-1과 같음


class RuleCheckFailed(Exception):
    """노트북의 assert에 해당하는 점검이 실패함 — 데이터가 바뀌어 규칙을 다시 검토해야 함"""

# ════════════════════════════════════════════════════════════════════
# [2-1] 컬럼 매핑 표: 표준 이름 → (구양식 2018~2023 헤더, 신양식 2024~ 헤더)
# ════════════════════════════════════════════════════════════════════
NEW_FORMAT_FROM = 2024

COLUMN_MAP = {
    # 선박 식별
    "imo":            ("IMO Number", "IMO Number"),
    "name":           ("Name", "Name"),
    "ship_type_raw":  ("Ship type", "Ship type"),
    "tech_eff_raw":   ("Technical efficiency", "Technical efficiency"),
    "company_name":   (None, "Name.1"),   # 신양식은 선박·회사 모두 'Name' → 두 번째에 pandas가 .1을 붙임
    "company_imo":    (None, "IMO Number.1"),   # 회사 IMO (같은 이유로 .1), 회사 단위 집계의 키
    "ice_class":      ("Ice Class", "Ice Class"),   # 내빙 등급
    # 측정 방식 (Yes / 빈칸)
    "mm_a": ("A", "A"),
    "mm_b": ("B", "B"),
    "mm_c": ("C", "C"),
    # 연료·배출 총량 [t]
    "fuel_t": ("Total fuel consumption [m tonnes]", "Total fuel consumption [m tonnes]"),
    "co2_t":  ("Total CO₂ emissions [m tonnes]", "Total CO₂ emissions [m tonnes]"),
    "co2_between_eu_t": ("CO₂ emissions from all voyages between ports under a MS jurisdiction [m tonnes]",) * 2,
    "co2_from_eu_t":    ("CO₂ emissions from all voyages which departed from ports under a MS jurisdiction [m tonnes]",) * 2,
    "co2_to_eu_t":      ("CO₂ emissions from all voyages to ports under a MS jurisdiction [m tonnes]",) * 2,
    "co2_berth_t":      ("CO₂ emissions which occurred within ports under a MS jurisdiction at berth [m tonnes]",) * 2,
    # ETS 대상 배출량 (신양식만)
    "co2_ets_t":   (None, "CO2 emissions to be reported under Directive 2003/87/EC [m tonnes]"),
    "co2eq_ets_t": (None, "CO₂eq emissions to be reported under Directive 2003/87/EC [m tonnes]"),
    # CO2 외 온실가스 (신양식만)
    "ch4_t":       (None, "Total CH₄ emissions [m tonnes]"),
    "n2o_t":       (None, "Total N₂O emissions [m tonnes]"),
    "co2eq_t":     (None, "Total CO₂eq emissions [m tonnes]"),
    "ch4_ets_t":   (None, "CH₄ emissions to be reported under Directive 2003/87/EC [m tonnes]"),
    "n2o_ets_t":   (None, "N₂O emissions to be reported under Directive 2003/87/EC [m tonnes]"),
    # 시간
    "time_at_sea_h": ("Annual Time spent at sea [hours]", "Time spent at sea [hours]"),
    # 얼음 항해
    "ice_distance_nm": ("Through ice [n miles]", "Distance through ice [n miles]"),
    "ice_time_h":      ("Total time spent at sea through ice [hours]", "Time spent at sea through ice [hours]"),
    # Ro-pax: 여객 몫으로 배분한 CO2
    "co2_passenger_t": ("CO₂ emissions assigned to Passenger transport [m tonnes]",) * 2,
    # 효율 지표
    "fuel_per_nm": ("Annual average Fuel consumption per distance [kg / n mile]",
                    "Fuel consumption per distance [kg / n mile]"),
    "co2_per_nm":  ("Annual average CO₂ emissions per distance [kg CO₂ / n mile]",
                    "CO₂ emissions per distance [kg CO₂ / n mile]"),
    "co2eq_per_nm": (None, "CO₂eq emissions per distance [kg CO₂eq / n mile]"),
}
# 운송작업당 CO2: 기준 5종
for basis, unit in [("mass", "m tonnes"), ("volume", "m³"), ("dwt", "dwt carried"),
                    ("pax", "pax"), ("freight", "m tonnes")]:
    COLUMN_MAP[f"co2_per_tw_{basis}"] = (
        f"Annual average CO₂ emissions per transport work ({basis}) [g CO₂ / {unit} · n miles]",
        f"CO₂ emissions per transport work ({basis}) [g CO₂ / {unit} · n miles]",
    )

# 2018~2019년분은 해상시간 열 이름에 'Total'이 붙어 있음 (1-4)
OLD_HEADER_ALIASES = {"Annual Total time spent at sea [hours]": "Annual Time spent at sea [hours]"}

TEXT_COLS = ["imo", "name", "ship_type_raw", "tech_eff_raw", "company_name", "company_imo", "ice_class",
             "mm_a", "mm_b", "mm_c"]
NUM_COLS = [c for c in COLUMN_MAP if c not in TEXT_COLS]
DIV_ZERO = "Division by zero!"


def sheet_for(year: int):
    """신양식은 Full ERs만, 구양식은 첫 시트 (1-5, 2-2)"""
    return f"{year} Full ERs" if year >= NEW_FORMAT_FROM else 0


# ════════════════════════════════════════════════════════════════════
# [2-2] 연도 1개를 읽어 표준 열로 바꾸는 함수
# ════════════════════════════════════════════════════════════════════
def read_year(year, path):
    new = year >= NEW_FORMAT_FROM
    sheet = sheet_for(year)
    df = pd.read_excel(path, sheet_name=sheet, header=2, dtype=str)   # 헤더 = 3번째 줄, 일단 전부 문자로
    df = df.rename(columns=OLD_HEADER_ALIASES)

    out = pd.DataFrame(index=df.index)
    for std, (old_h, new_h) in COLUMN_MAP.items():
        h = new_h if new else old_h
        if h is None:
            out[std] = pd.NA
        elif h not in df.columns:
            raise KeyError(f"{year}년분에 '{h}' 열이 없음 (표준명 {std})")   # 매핑 오류는 바로 멈춤
        else:
            out[std] = df[h]

    out["co2_per_nm_div0"] = out["co2_per_nm"].eq(DIV_ZERO)
    for c in NUM_COLS:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    for c in TEXT_COLS:
        out[c] = out[c].astype("string").str.strip()
    out["company_imo"] = out["company_imo"].str.replace(r"\.0$", "", regex=True).str.zfill(7)

    out.insert(0, "year", year)
    out["source_file"] = path.name
    return out


# ════════════════════════════════════════════════════════════════════
# [1-5] Partial ERs 선박 목록 (그해 관리 회사가 바뀐 배 표시용)
# ════════════════════════════════════════════════════════════════════
def read_partial_imos(year, path):
    if year < NEW_FORMAT_FROM:
        return None
    part = pd.read_excel(path, sheet_name=f"{year} Partial ERs", header=2, usecols=["IMO Number"], dtype=str)
    return set(part["IMO Number"].dropna().str.strip())


# ════════════════════════════════════════════════════════════════════
# [2-3] 연도 통합 + 그해 회사 변경 표시 + 매핑 점검
# ════════════════════════════════════════════════════════════════════
def combine_years(frames: dict, partial_imos: dict):
    raw = pd.concat([frames[y] for y in sorted(frames)], ignore_index=True)

    raw["company_changed"] = pd.array([pd.NA] * len(raw), dtype="boolean")
    for y, imos in partial_imos.items():
        if imos is None:
            continue
        in_year = raw["year"].eq(y)
        raw.loc[in_year, "company_changed"] = raw.loc[in_year, "imo"].isin(imos)

    # 매핑 점검: 그 양식에 있어야 할 열이 통째로 비어 있으면 헤더 매핑이 틀린 것
    old_only_missing = {std for std, (old_h, _) in COLUMN_MAP.items() if old_h is None}
    problems = {}
    for y, g in raw.groupby("year"):
        empty = {c for c in COLUMN_MAP if g[c].isna().all()}
        expected = old_only_missing if y < NEW_FORMAT_FROM else set()
        if empty - expected:
            problems[int(y)] = sorted(empty - expected)

    stats = {
        "rows_by_year": raw.groupby("year").size().to_dict(),
        "ships": int(raw["imo"].nunique()),
        "dup_imo_year": int(raw.duplicated(["imo", "year"]).sum()),
        "imo_missing": int(raw["imo"].isna().sum()),
        "div0_by_year": raw.groupby("year")["co2_per_nm_div0"].sum().astype(int).to_dict(),
        "company_changed_by_year": raw[raw["company_changed"].fillna(False)].groupby("year").size().to_dict(),
        "unexpected_empty_columns": problems,
    }
    return raw, stats


# [3-1] IMO 번호 형식: 7자리 + 마지막 자리는 검증자리 (점검만, 값은 바꾸지 않음)
def imo_check_ok(s):
    d = [int(c) for c in s]
    return sum(d[i] * (7 - i) for i in range(6)) % 10 == d[6]


def check_keys(raw):
    imo = raw["imo"].astype(str)
    is7 = imo.str.fullmatch(r"\d{7}")
    bad = imo[is7][~imo[is7].map(imo_check_ok)]
    return {"imo_not_7digits": int((~is7).sum()), "imo_checksum_failed": int(len(bad)),
            "exact_duplicate_rows": int(raw.drop(columns="source_file").astype(str).duplicated().sum())}


# ════════════════════════════════════════════════════════════════════
# [3-2] 선사명 통일: 이중 공백 → 한 칸, 대소문자만 다른 표기 → 가장 많이 쓰인 표기
# ════════════════════════════════════════════════════════════════════
def unify_company_names(raw):
    before = int(raw["company_name"].dropna().nunique())
    cn = raw["company_name"].str.replace(r"\s+", " ", regex=True)
    key = cn.str.lower()
    most_common = cn.groupby(key).agg(lambda s: s.value_counts().index[0])
    raw["company_name"] = key.map(most_common).astype("string")
    return {"company_names_before": before, "company_names_after": int(raw["company_name"].dropna().nunique())}


# ════════════════════════════════════════════════════════════════════
# [3-4] 총 CO2 계산 오류 보정: CO2 ÷ 연료가 물리적 상한 44/12(= 3.67)를 넘는 행  + 계수 반올림(3.21) 보정 (v8)
# ════════════════════════════════════════════════════════════════════
PARTS = ["co2_between_eu_t", "co2_from_eu_t", "co2_to_eu_t", "co2_berth_t"]
TW_COLS = [f"co2_per_tw_{b}" for b in ["mass", "volume", "dwt", "pax", "freight"]]
CO2_PER_FUEL_MAX = 44 / 12
RECOVER_GAP = 0.001                       # v8: 두 근거(4종 합, 보고값 ÷ 2)가 0.1% 이내일 때만 보정
MGO_EF, ROUNDED_EF = 3.206, 3.21          # 경유 = 선박 연료 중 가장 큰 배출계수


def tol(ef):
    """반올림 최대 오차 = CO2 0.005t + 연료 0.005t × 계수 (공개값 소수 둘째 자리 기준)"""
    return 0.005 + ef * 0.005


def fix_total_co2(raw):
    over = (raw["co2_t"] / raw["fuel_t"]).gt(CO2_PER_FUEL_MAX)
    parts = raw[PARTS].sum(axis=1)
    cand = over & (parts / raw["fuel_t"]).between(2.5, 3.21)
    gap = (parts / (raw["co2_t"] / 2) - 1).abs()
    fix = cand & gap.le(RECOVER_GAP)
    k = parts[fix] / raw.loc[fix, "co2_t"]

    raw["co2_t_reported"] = raw["co2_t"].where(fix)
    for c in ["co2_t", "co2_per_nm", *TW_COLS]:
        raw.loc[fix, c] = raw.loc[fix, c] * k
    pax_fix = fix & raw["co2_passenger_t"].gt(raw["co2_t"])
    raw.loc[pax_fix, "co2_passenger_t"] = raw.loc[pax_fix, "co2_passenger_t"] * k[pax_fix[fix]]
    raw["co2_recovered"] = fix
    raw["co2_over_fuel"] = over & ~fix

    # ── 계수 반올림 보정 (v8): 경유 계수 3.206을 3.21로 반올림해 계산한 행 → 3.206으로 되돌림
    fix321 = (~over & (raw["co2_t"] - MGO_EF * raw["fuel_t"]).gt(tol(MGO_EF))
              & (raw["co2_t"] - ROUNDED_EF * raw["fuel_t"]).abs().le(tol(ROUNDED_EF)))
    if not raw.loc[fix321, "year"].lt(2024).all():   # 노트북 assert: CO2eq·ETS 파일값이 없는 연도에서만 성립
        rows = raw.loc[fix321 & raw["year"].ge(2024), ["imo", "year", "name"]].values.tolist()
        raise RuleCheckFailed(f"3-4 계수 반올림(3.21) 보정 대상이 2024년분 이후에도 생김 {rows} — "
                              "CO2eq·ETS 열도 함께 고쳐야 하는지 팀 검토 필요 (노트북 3-4 assert)")
    raw.loc[fix321, "co2_t_reported"] = raw.loc[fix321, "co2_t"]
    for c in ["co2_t", *PARTS, "co2_per_nm", *TW_COLS, "co2_passenger_t"]:
        raw.loc[fix321, c] = raw.loc[fix321, c] * (MGO_EF / ROUNDED_EF)
    raw.loc[fix321, "co2_recovered"] = True
    return {"co2_over_fuel_max": int(over.sum()), "co2_fix_candidates": int(cand.sum()), "co2_fixed": int(fix.sum()),
            "co2_fix_ratio_median": float(k.median()) if len(k) else None,
            "co2_passenger_fixed": int(pax_fix.sum()), "co2_not_recovered": int(raw["co2_over_fuel"].sum()),
            "co2_rounded_321_fixed": raw.loc[fix321, ["imo", "year", "name"]].values.tolist()}


# ════════════════════════════════════════════════════════════════════
# [4-3] 행 제거 규칙 ①~⑤  +  [4-5] ⑤-2, ⑤-3, ⑤-3b, ⑤-4
# ════════════════════════════════════════════════════════════════════
CO2_PER_NM_RANGE = (50, 2000)   # kg/nm (계획서)
SPEED_RANGE = (0.5, 40)         # kn (추가 규칙)
MIN_TIME_AT_SEA_H = 72
EXCEPT = {("9481685", 2018)}    # ⑤-6 예외 (v8): KISHORE 2018 — 경유 계수 + 반올림 오차 초과, 원인 불명


class StepLog:
    """노트북의 step() — 단계별 남은 행·선박 수 기록 (cleaning_log)"""
    def __init__(self):
        self.log, self.by_year = [], {}

    def __call__(self, name, d):
        self.log.append({"단계": name, "행": len(d), "선박": d["imo"].nunique()})
        self.by_year[name] = d.groupby("year").size()


def apply_row_rules(raw, step: StepLog):
    df = raw.copy()
    step("원본 (Full ERs)", df)

    df = df.dropna(subset=["imo"]).drop_duplicates(["imo", "year"], keep=False)      # ①
    step("① IMO 결측·중복 제거", df)

    df = df[~df["co2_per_nm_div0"] & (df["time_at_sea_h"] > 0)]                      # ②
    step("② 해상시간 0 / Division by zero 제외", df)

    df = df[(df["co2_t"] > 0) & (df["fuel_t"] > 0) & df["co2_per_nm"].notna()]        # ③
    step("③ CO2·연료 0/결측 제외", df)

    lo, hi = CO2_PER_NM_RANGE                                                          # ④
    df = df[df["co2_per_nm"].between(lo, hi)]
    step(f"④ 거리당 CO2 {lo}~{hi} kg/nm 밖 제외", df)

    speed = df["co2_t"] * 1000 / df["co2_per_nm"] / df["time_at_sea_h"]               # ⑤
    s_lo, s_hi = SPEED_RANGE
    df = df[speed.between(s_lo, s_hi)].copy()
    step(f"⑤ 평균 속력 {s_lo}~{s_hi} kn 밖 제외", df)

    df = df[df["time_at_sea_h"] >= MIN_TIME_AT_SEA_H].copy()                           # ⑤-2
    step(f"⑤-2 해상시간 {MIN_TIME_AT_SEA_H}시간 미만 제외", df)

    hours_in_year = np.where(df["year"] % 4 == 0, 8784, 8760)                          # ⑤-3
    over_year = df["time_at_sea_h"] > hours_in_year
    df = df[~over_year].copy()
    step("⑤-3 해상시간 1년 초과 제외", df)

    dist = df["co2_t"] * 1000 / df["co2_per_nm"]                                       # ⑤-3b
    gap = (dist - df["time_at_sea_h"]).abs() / df["time_at_sea_h"]
    same_num = gap.lt(1e-4)
    df = df[~same_num].copy()
    step("⑤-3b 해상시간 = 거리 제외", df)

    df = df[~df["co2_over_fuel"]].drop(columns="co2_over_fuel")                         # ⑤-4
    step("⑤-4 CO2 ÷ 연료 3.67 초과(보정 못 한 행) 제외", df)

    ratio = df["co2_t"] / df["fuel_t"]                                                 # ⑤-5 (v8)
    r55 = ~df["co2_recovered"] & ratio.gt(MGO_EF * 1.005)
    removed55 = df.loc[r55, ["imo", "year", "name"]].values.tolist()
    df = df[~r55].copy()
    step("⑤-5 CO2 ÷ 연료 3.206 × 1.005 초과 제외", df)

    over_round = ~df["co2_recovered"] & (df["co2_t"] - MGO_EF * df["fuel_t"]).gt(tol(MGO_EF))   # ⑤-6 (v8)
    r_ex = pd.Series([(i, y) in EXCEPT for i, y in zip(df["imo"], df["year"])], index=df.index)
    if not (r_ex.sum() == len(EXCEPT) and over_round[r_ex].all()):   # 노트북 assert
        raise RuleCheckFailed(
            f"⑤-6 예외 목록 {sorted(EXCEPT)} 점검 실패 — 해당 행이 없어졌거나(새 버전에서 정정·철회) 더 이상 "
            f"비율 초과가 아님. 현재 초과 행: {df.loc[over_round, ['imo', 'year', 'name']].values.tolist()} "
            "(노트북 4-5 assert, 예외 목록 EXCEPT를 팀에서 다시 정해야 함)")
    over_round_kept = df.loc[over_round & ~r_ex, ["imo", "year", "name"]].values.tolist()
    df = df[~r_ex].copy()
    step("⑤-6 예외: 원인 불명 비율 초과 (KISHORE 2018) 제외", df)
    return df, {"rule55_removed": removed55, "rule56_over_round_kept": over_round_kept}


# ════════════════════════════════════════════════════════════════════
# [5-2] ⑥ 5,000GT 이상: 2025년 신규 보고 일반화물선 제외
# [5-3] ⑦ CII 적용 선종
# ════════════════════════════════════════════════════════════════════
SCOPE_EXPANSION_YEAR = 2025      # MRV 대상 확대(400~5,000GT 일반화물선·offshore) 시작 연도

CII_SHIP_TYPES = {
    "Bulk carrier", "Chemical tanker", "Oil tanker", "Combination carrier", "Container ship",
    "Container/ro-ro cargo ship", "Gas carrier", "LNG carrier", "General cargo ship",
    "Refrigerated cargo carrier", "Ro-ro ship", "Vehicle carrier", "Ro-pax ship",
}
CRUISE_LABEL = "Passenger ship (Cruise Passenger ship)"


def limit_scope(df, raw, step: StepLog):
    y0 = SCOPE_EXPANSION_YEAR
    reported_before = set(raw.loc[raw["year"] < y0, "imo"])                             # ⑥
    new_gc = ((df["year"] == y0) & ~df["imo"].isin(reported_before)
              & df["ship_type_raw"].eq("General cargo ship"))
    n6 = int(new_gc.sum())
    df = df[~new_gc].copy()
    step(f"⑥ {y0}년 신규 일반화물선 제외", df)

    cruise_ships = set(raw.loc[raw["ship_type_raw"] == CRUISE_LABEL, "imo"])            # ⑦
    is_passenger = df["ship_type_raw"].str.startswith("Passenger ship")
    in_cii = df["ship_type_raw"].isin(CII_SHIP_TYPES) | (is_passenger & df["imo"].isin(cruise_ships))
    removed7 = df[~in_cii]
    df = df[in_cii].copy()
    step("⑦ CII 비대상 선종 제외", df)
    return df, {"rule6_removed": n6,
                "rule7_removed_by_type": removed7["ship_type_raw"].value_counts().to_dict()}


# ════════════════════════════════════════════════════════════════════
# [6-1]~[6-4] 값 정리
# ════════════════════════════════════════════════════════════════════
SHIP_TYPE_NORMALIZE = {
    "Passenger ship (Cruise Passenger ship)": "Cruise passenger ship",
    "Passenger ship": "Cruise passenger ship",       # ⑦ 이후 남은 여객선은 모두 크루즈
    "Combination carrier": "Bulk carrier",
}
TECH_EFF_FACTOR = 10


def tidy_values(df):
    df["ship_type"] = df["ship_type_raw"].replace(SHIP_TYPE_NORMALIZE)                 # 6-1

    m = df["tech_eff_raw"].str.extract(r"^\s*(EEDI|EIV|EEXI)?\s*\(?\s*([\d.]+)?")       # 6-2
    df["tech_eff_kind"] = m[0].astype("string")
    df["tech_eff_value"] = pd.to_numeric(m[1], errors="coerce")

    v = df["tech_eff_value"].where(df["tech_eff_value"] > 0)                          # 6-3
    n_zero = int((df["tech_eff_value"] == 0).sum())
    no_kind = v.notna() & df["tech_eff_kind"].isna()
    v = v.where(~no_kind)
    grp = [df["ship_type"], df["tech_eff_kind"]]
    med = v.groupby(grp).transform("median")
    extreme = (v.notna() & ~v.between(med / TECH_EFF_FACTOR, med * TECH_EFF_FACTOR)).fillna(False)
    df["tech_eff_value"] = v.where(~extreme)

    for c in ["mm_a", "mm_b", "mm_c"]:                                                  # 6-4
        df[c] = df[c].str.lower().eq("yes").fillna(False).astype("int8")

    return {"ship_types": int(df["ship_type"].nunique()), "tech_eff_zero": n_zero,
            "tech_eff_no_kind": int(no_kind.sum()), "tech_eff_extreme": int(extreme.sum()),
            "tech_eff_missing_rate": round(float(df["tech_eff_value"].isna().mean()), 4)}


# ════════════════════════════════════════════════════════════════════
# [8-1] 운항거리, 평균 속력, 정박·EU 역내 비중, 배출계수, 연료 추측
# ════════════════════════════════════════════════════════════════════
EMISSION_FACTORS = {
    "MGO/MDO": 3.206, "LFO": 3.151, "HFO": 3.114, "LPG(butane)": 3.030, "LPG(propane)": 3.000,
    "LNG": 2.750, "ethanol": 1.913, "methanol": 1.375,
}
# [8-2] 선종별 운송작업 기준
TW_BASIS = {
    "LNG carrier": "volume",
    "Container/ro-ro cargo ship": "volume",
    "General cargo ship": "dwt",
    "Cruise passenger ship": "pax",
    "Ro-pax ship": "pax",
}


FUEL_GROUP_ALT_MAX = 3.05      # 이 계수 미만이면 대체연료가 섞인 해 (fuel_alt와 같은 경계)
FUEL_GROUP_CH4_MIN = 0.05      # CO2eq 중 CH4·N2O 몫이 이 이상이면 LNG 계열 (LNG 0.09-0.25, 그 외 0.015 안팎)
FUEL_GROUP_LPG = (2.95, 3.05)  # 가스선이 이 계수 범위이고 CH4가 적으면 LPG 추정


def fuel_group(df):
    """석유계 / LNG 계열 / LPG 추정 / 기타 대체연료 / 대체연료(구분 불가). 계수가 없으면 결측"""
    cpf, ns = df["co2_per_fuel"], df["nonco2_share"]
    alt = cpf.lt(FUEL_GROUP_ALT_MAX)
    lng = alt & (ns.ge(FUEL_GROUP_CH4_MIN) | df["ship_type"].eq("LNG carrier"))      # LNG선은 증발가스를 연료로 씀
    lpg = alt & ~lng & df["ship_type"].eq("Gas carrier") & cpf.between(*FUEL_GROUP_LPG) & ns.lt(FUEL_GROUP_CH4_MIN)
    unknown = alt & ~lng & ns.isna()                                                 # 2023년분까지 (CH4 열 없음)
    g = np.select([cpf.isna(), ~alt, lng, lpg, unknown], [None, "석유계", "LNG 계열", "LPG 추정", "대체연료(구분 불가)"], "기타 대체연료")
    return pd.Series(g, index=df.index, dtype="string")


def derive(df):
    st = {}
    # ── 8-1
    df["distance_nm"] = df["co2_t"] * 1000 / df["co2_per_nm"]
    df["speed_kn"] = df["distance_nm"] / df["time_at_sea_h"]
    df["berth_share"] = (df["co2_berth_t"] / df["co2_t"]).clip(0, 1)
    df["intra_eu_share"] = (df["co2_between_eu_t"] / df["co2_t"]).clip(0, 1)
    df["co2_parts_bad"] = (df[PARTS].sum(axis=1) / df["co2_t"]).gt(1.05)
    df.loc[df["co2_parts_bad"], ["berth_share", "intra_eu_share"]] = np.nan
    st["co2_parts_bad"] = int(df["co2_parts_bad"].sum())

    df["co2_per_fuel"] = df["co2_t"] / df["fuel_t"]
    # 단일 연료 (v8, 톤 기준): |CO2 − 계수 × 연료| ≤ tol(계수)
    fuel_single = pd.Series(pd.NA, index=df.index, dtype="string")
    n_hits = pd.Series(0, index=df.index)
    for fuel, ef in EMISSION_FACTORS.items():
        r = df["co2_t"] - ef * df["fuel_t"]
        hit = r.abs().le(tol(ef))
        fuel_single[hit] = fuel
        n_hits += hit
    if n_hits.max() > 1:                                                             # 노트북 assert
        raise RuleCheckFailed("8-1 두 연료에 동시에 걸리는 행이 있음 — 단일 연료 판정 기준 검토 필요")
    df["fuel_single"] = fuel_single
    df["fuel_alt"] = df["co2_per_fuel"].lt(3.05)
    st["fuel_single"] = df["fuel_single"].value_counts().to_dict()
    st["fuel_alt"] = int(df["fuel_alt"].sum())

    # ── 8-2 평균 적재 톤수
    df["avg_load_basis"] = df["ship_type"].map(TW_BASIS).fillna("mass")
    tw = pd.Series(np.nan, index=df.index)
    for b in df["avg_load_basis"].unique():
        rows = df["avg_load_basis"].eq(b)
        tw[rows] = df.loc[rows, f"co2_per_tw_{b}"]
    tw = tw.where(tw > 0)
    co2_per_nm_load = df["co2_per_nm"].copy()
    ropax = df["ship_type"].eq("Ro-pax ship")
    pax_share = (df["co2_passenger_t"] / df["co2_t"]).where(lambda s: s.between(0, 1) & (s > 0))
    co2_per_nm_load[ropax] = df.loc[ropax, "co2_per_nm"] * pax_share[ropax]
    df["avg_load"] = co2_per_nm_load / tw * 1000
    df["co2_per_tw"] = tw

    med_load = df.groupby("ship_type")["avg_load"].transform("median")
    too_big = df["avg_load"] > med_load * 10
    ropax_err = ropax & pax_share.ge(0.05) & df["avg_load"].lt(1)
    bad_load = too_big | ropax_err
    df.loc[bad_load, ["avg_load", "co2_per_tw"]] = np.nan
    df["avg_load_invalid"] = bad_load
    st.update(avg_load_too_big=int(too_big.sum()), avg_load_ropax_err=int(ropax_err.sum()),
              avg_load_missing_rate=round(float(df["avg_load"].isna().mean()), 4))

    # ── 8-3 ETS 대상 배출량
    approx = (df["co2_between_eu_t"].fillna(0) + df["co2_berth_t"].fillna(0)
              + 0.5 * (df["co2_from_eu_t"].fillna(0) + df["co2_to_eu_t"].fillna(0)))
    approx = approx.where(~df["co2_parts_bad"]).clip(upper=df["co2_t"])
    df["ets_co2_approx"] = df["co2_ets_t"].isna()
    df["ets_co2_t"] = df["co2_ets_t"].fillna(approx)
    st["ets_over_total"] = int((df["ets_co2_t"] > df["co2_t"]).sum())
    df["ets_co2_t"] = df["ets_co2_t"].clip(upper=df["co2_t"])

    df["nonco2_share"] = (df["co2eq_t"] - df["co2_t"]) / df["co2eq_t"]
    for ets, tot in [("ch4_ets_t", "ch4_t"), ("n2o_ets_t", "n2o_t"), ("co2eq_ets_t", "co2eq_t")]:
        st[f"{ets}_clipped"] = int((df[ets] > df[tot] * 1.01).sum())
        df[ets] = df[ets].clip(upper=df[tot])
    df["ets_co2eq_t"] = df["ets_co2_t"] * df["co2eq_t"] / df["co2_t"]

    # ── 8-4 연료 그룹 (파이프라인 추가, 노트북에 없음 — 36.연료타입분류.md 4장, 비용 계산용)
    #   계수(CO2 ÷ 연료) 3.05 이상 = 석유계. 그 아래(대체연료)는 2024년분부터 CH4·N2O 비중으로 LNG 계열을 가르고,
    #   CH4가 적은 가스선 중 계수 2.95-3.05(프로판 3.000·부탄 3.030 근처)는 LPG로 추정. 2023년분까지는 CH4 열이 없어 구분 불가
    df["fuel_group"] = fuel_group(df)
    st["fuel_group"] = df["fuel_group"].value_counts().to_dict()

    # ── 8-5 최종 정리
    df["is_covid_year"] = df["year"].isin([2020, 2021]).astype("int8")
    df = df.sort_values(["imo", "year"]).reset_index(drop=True)
    return df, st


# ════════════════════════════════════════════════════════════════════
# 전체 실행: 노트북 2-3 → 3-2 → 3-4 → 4 → 5 → 6 → 8 순서
# ════════════════════════════════════════════════════════════════════
def run_rules(frames: dict, partial_imos: dict):
    """frames: {연도: read_year 결과}, partial_imos: {연도: set 또는 None}
    반환: (raw 통합 원본[2-7 저장본], 최종 df, 정제 로그 DataFrame, 연도별 남은 행 DataFrame, stats)"""
    stats = {}
    raw, stats["combine"] = combine_years(frames, partial_imos)
    raw_saved = raw.copy()                       # 노트북 2-7 저장 시점 (3단계 이전)
    stats["keys"] = check_keys(raw)
    stats["company"] = unify_company_names(raw)
    stats["co2_fix"] = fix_total_co2(raw)

    step = StepLog()
    df, stats["row_rules"] = apply_row_rules(raw, step)
    df, stats["scope"] = limit_scope(df, raw, step)
    stats["tidy"] = tidy_values(df)
    df, stats["derive"] = derive(df)

    by_year = pd.DataFrame(step.by_year)
    by_year["남은 비율"] = (by_year.iloc[:, -1] / by_year.iloc[:, 0]).round(3)
    return raw_saved, df, pd.DataFrame(step.log), by_year, stats


# ════════════════════════════════════════════════════════════════════
# [8-7] 열 사전 (파이프라인이 추가한 열 2개 포함)
# ════════════════════════════════════════════════════════════════════
COLUMN_DICT = {
    "year":               ("보고연도", "년", "2"),
    "imo":                ("IMO 선박 번호 (키 = imo + year)", "-", "2"),
    "name":               ("선박명 (연도별로 바뀔 수 있음, 개명)", "-", "2"),
    "ship_type_raw":      ("원본 선종 표기", "-", "2"),
    "ship_type":          ("분석 선종 (13개, 여객선 → 크루즈·겸용선 → 벌크 통일). 공식 CII 계산에는 ship_type_raw 사용", "-", "6"),
    "company_name":       ("선사명 (2024년분부터, 표기 통일)", "-", "2·3"),
    "company_imo":        ("회사 IMO 번호 (2024년분부터, 7자리) — 회사 단위 집계의 키", "-", "2"),
    "company_changed":    ("그해 관리 회사가 바뀌었는지 (Partial ERs에도 있음, 2024년분부터, 이전은 결측)", "True/False", "2"),
    "ice_class":          ("내빙 등급 (빈칸 = 없음)", "-", "2"),
    "source_file":        ("원본 파일명 (버전 포함)", "-", "2"),
    "tech_eff_raw":       ("기술효율 지표 원문", "-", "2"),
    "tech_eff_kind":      ("기술효율 지표 종류 (EEDI / EIV / EEXI, 결측 = 미상)", "-", "6"),
    "tech_eff_value":     ("기술효율 지표 값 (0·극단값은 결측)", "gCO2/t·nm", "6"),
    "mm_a":               ("측정 방식 A 사용 여부", "0/1", "6"),
    "mm_b":               ("측정 방식 B 사용 여부", "0/1", "6"),
    "mm_c":               ("측정 방식 C 사용 여부", "0/1", "6"),
    "fuel_t":             ("연간 연료 소모량", "t", "2"),
    "co2_t":              ("연간 총 CO2 배출량 (3-4에서 2배 계산 오류·계수 반올림 3.21 보정)", "t", "2·3"),
    "co2_t_reported":     ("보정 전 원래 보고된 총 CO2 (보정한 행만, 나머지 결측)", "t", "3"),
    "co2_recovered":      ("총 CO2를 보정한 행인지: 2배 오류 중 두 근거(4종 합 = 보고값 ÷ 2, 0.1% 이내)로 확인된 행 + 계수 반올림(3.21) 행. 거리당·운송작업당 CO2도 같은 비율로 보정", "True/False", "3"),
    "co2_between_eu_t":   ("EU 항구 간 항해 CO2", "t", "2"),
    "co2_from_eu_t":      ("EU 항구 출항 항해 CO2", "t", "2"),
    "co2_to_eu_t":        ("EU 항구 입항 항해 CO2", "t", "2"),
    "co2_berth_t":        ("EU 항구 정박 중 CO2", "t", "2"),
    "co2_ets_t":          ("ETS 대상 CO2 (파일 값, 2024년분부터)", "t", "2"),
    "co2eq_ets_t":        ("ETS 대상 CO2eq 파일값 (2024년분부터, 총량 상한). 2025년분은 CH4·N2O 미포함 → 비용에는 ets_co2eq_t 사용", "tCO2e", "2·8"),
    "ch4_t":              ("총 CH4 배출량 (2024년분부터, 연료 × 기본 배출계수)", "t", "2"),
    "n2o_t":              ("총 N2O 배출량 (2024년분부터, 연료 × 기본 배출계수)", "t", "2"),
    "co2eq_t":            ("총 온실가스 배출량 CO2eq = CO2 + 28·CH4 + 265·N2O (2024년분부터)", "tCO2e", "2"),
    "ch4_ets_t":          ("ETS 대상 CH4 파일값 (2024년분부터, 총량 상한, 연도마다 보고 방식 다름)", "t", "2·8"),
    "n2o_ets_t":          ("ETS 대상 N2O 파일값 (2024년분부터, 총량 상한, 연도마다 보고 방식 다름)", "t", "2·8"),
    "time_at_sea_h":      ("해상시간", "시간", "2"),
    "ice_distance_nm":    ("얼음 항해 거리", "nm", "2"),
    "ice_time_h":         ("얼음 항해 시간", "시간", "2"),
    "co2_passenger_t":    ("여객 몫으로 배분한 CO2 (Ro-pax)", "t", "2"),
    "fuel_per_nm":        ("거리당 연료 소모량", "kg/nm", "2"),
    "co2_per_nm":         ("거리당 CO2 (예측 대상 지표, EU 항해 기준 탄소집약도)", "kg CO2/nm", "2"),
    "co2eq_per_nm":       ("거리당 온실가스 CO2eq (2024년분부터)", "kg CO2e/nm", "2"),
    "co2_per_tw_mass":    ("운송작업당 CO2 — 화물 톤 기준", "g CO2/t·nm", "2"),
    "co2_per_tw_volume":  ("운송작업당 CO2 — 부피 기준", "g CO2/m³·nm", "2"),
    "co2_per_tw_dwt":     ("운송작업당 CO2 — 재화중량 기준 (배의 DWT가 아닌 dwt carried)", "g CO2/dwt·nm", "2"),
    "co2_per_tw_pax":     ("운송작업당 CO2 — 여객 기준 (Ro-pax는 여객 몫 CO2로 계산된 값)", "g CO2/명·nm", "2"),
    "co2_per_tw_freight": ("운송작업당 CO2 — 화물(Ro-pax) 기준", "g CO2/t·nm", "2"),
    "co2_per_nm_div0":    ("원본 거리당 값이 'Division by zero!'였는지", "True/False", "2"),
    "distance_nm":        ("운항거리 = 총CO2 × 1000 ÷ 거리당CO2", "nm", "8"),
    "speed_kn":           ("평균 속력 = 운항거리 ÷ 해상시간", "kn", "8"),
    "berth_share":        ("정박 배출 비중 = 정박 CO2 ÷ 총CO2 (항해 유형 합 오류 행은 결측)", "0~1", "8"),
    "intra_eu_share":     ("EU 역내 항해 비중 = EU 항구 간 CO2 ÷ 총CO2 (항해 유형 합 오류 행은 결측)", "0~1", "8"),
    "co2_parts_bad":      ("항해 유형 4종 CO2 합이 총량의 1.05배 초과 (세부 항목 오류)", "True/False", "8"),
    "co2_per_fuel":       ("실제 배출계수 = 총CO2 ÷ 연료 (그해 연료 조합의 간접 지표)", "t CO2/t 연료", "8"),
    "fuel_single":        ("그해 한 가지 연료만 쓴 경우 그 연료 (|CO2 − 계수 × 연료| ≤ 0.005 + 계수 × 0.005 t, 공개값 반올림 최대 오차 안). 결측 = 혼합 연료. "
                           "신뢰도: MGO/MDO·LNG 높음, HFO 보통, LFO 낮음(중유+경유 혼합값과 겹침). LFO ≠ 저유황 중유. 참고용, 모델 피처로 쓰지 않음 (36.연료타입분류.md)",
                           "MGO/MDO / LFO / HFO / LNG 등", "8"),
    "fuel_alt":           ("대체연료(LNG·LPG·메탄올·바이오연료 등)가 섞인 해 (CO2 ÷ 연료 < 3.05)", "True/False", "8"),
    "avg_load_basis":     ("평균 적재 톤수 계산에 쓴 운송작업 기준", "mass/volume/dwt/pax", "8"),
    "avg_load_invalid":   ("원본 운송작업 지표가 틀려 avg_load·co2_per_tw를 결측으로 바꾼 행 (False인 결측은 미보고)", "True/False", "8"),
    "avg_load":           ("평균 적재량 (선종 안에서만 비교). Ro-pax는 여객 몫 CO2 기준 평균 승객 수, 일반화물선은 DWT 아님", "기준별: t / m³ / 명", "8"),
    "co2_per_tw":         ("선종별 기준의 운송작업당 CO2 (현재 수준 축에 사용, 극단값은 결측)", "기준별 g CO2/단위·nm", "8"),
    "ets_co2_approx":     ("ETS 대상 배출량이 근사값인지 (2018~2023년분 True)", "True/False", "8"),
    "ets_co2_t":          ("ETS 대상 CO2 (2024년분부터 파일 값, 이전은 근사. 총CO2 상한, 근사의 항해 유형 합 오류 행은 결측)", "t", "8"),
    "nonco2_share":       ("CO2eq 중 CH4·N2O 몫 (2024년분부터, LNG·이중연료 사용의 간접 지표)", "0~1", "8"),
    "ets_co2eq_t":        ("2026년 기준 ETS 대상 CO2eq 추정 = ETS 대상 CO2 × CO2eq ÷ CO2 (2024년분부터, CH4·N2O 합산 비용 계산용)", "tCO2e", "8"),
    "is_covid_year":      ("코로나 기간(2020~2021) 여부", "0/1", "8"),
    # ── 파이프라인이 추가한 열 (노트북에 없음)
    "mrv_file_version":   ("이 행을 만든 원본 파일 버전 (파이프라인 추가)", "-", "P"),
    "mrv_file_date":      ("원본 파일 생성일 (파일명 기준, 파이프라인 추가)", "YYYY-MM-DD", "P"),
    "fuel_group":         ("연료 그룹 (파이프라인 추가, 비용 계산용). 석유계 = CO2 ÷ 연료 ≥ 3.05 / LNG 계열 = 그 아래이면서 CH4·N2O 몫 ≥ 0.05 또는 LNG선 / "
                           "LPG 추정 = 그 아래이면서 가스선·계수 2.95-3.05·CH4 몫 < 0.05 / 기타 대체연료 = 메탄올·바이오 혼합 등 / "
                           "대체연료(구분 불가) = 2023년분까지의 대체연료(CH4 열 없음). 계수 기반 추정 (36.연료타입분류.md 4장)",
                           "5개 범주", "P"),
}
PIPELINE_ADDED_COLS = ["mrv_file_version", "mrv_file_date", "fuel_group"]


def column_dictionary(df):
    missing = [c for c in df.columns if c not in COLUMN_DICT]
    extra = [c for c in COLUMN_DICT if c not in df.columns]
    assert not missing and not extra, f"사전에 없는 열 {missing} / 파일에 없는 열 {extra}"
    col_dict = pd.DataFrame(COLUMN_DICT, index=["뜻", "단위", "단계"]).T
    col_dict["타입"] = df.dtypes.astype(str)
    col_dict["결측률"] = df.isna().mean().round(3)
    return col_dict.reindex(df.columns)


# ════════════════════════════════════════════════════════════════════
# [9-1]~[9-4] 선박 제원 통합 (원래 02_merge_specs_v3) — MRV 행 기준 left join
# ════════════════════════════════════════════════════════════════════
SPEC_COLS = {"IMO": "imo", "Built": "built_year", "Gross Tonnage": "gross_tonnage",
             "Summer DWT": "dwt", "Length": "length_m", "Beam": "beam_m"}
SPEC_NEW = ["built_year", "gross_tonnage", "dwt", "length_m", "beam_m", "ship_age", "gt_below_5000"]


def merge_specs(df, spec_path):
    """df: 8단계 결과(노트북 61열). 반환 (mg, stats)"""
    spec = pd.read_csv(spec_path, dtype={"IMO": str})                                   # 9-1
    st = {"spec_ships": int(len(spec)), "spec_dup_imo": int(spec["IMO"].duplicated().sum()),
          "spec_bad_imo": int((~spec["IMO"].str.fullmatch(r"\d{7}")).sum())}
    mrv_ships, spec_ships = set(df["imo"]), set(spec["IMO"])                              # 9-2
    st.update(matched_ships=len(mrv_ships & spec_ships), mrv_only_ships=len(mrv_ships - spec_ships),
              spec_only_ships=len(spec_ships - mrv_ships), row_match_rate=round(float(df["imo"].isin(spec_ships).mean()), 4))

    spec_std = spec.drop(columns="Age").rename(columns=SPEC_COLS)                         # 9-3
    lb = spec_std["length_m"] / spec_std["beam_m"]
    bad_beam = lb.gt(12)
    st["beam_set_missing"] = spec_std.loc[bad_beam, "imo"].tolist()
    spec_std.loc[bad_beam, "beam_m"] = np.nan

    spec_std["built_year"] = spec_std["built_year"].astype("Int64")                       # 9-4
    spec_std["imo"] = spec_std["imo"].astype(df["imo"].dtype)
    try:
        mg = df.merge(spec_std, on="imo", how="left", validate="many_to_one")
    except pd.errors.MergeError as e:
        raise RuleCheckFailed(f"9-4 제원 파일에 같은 IMO가 여러 행 있음 — {spec_path.name} 확인 ({e})")
    mg["ship_age"] = mg["year"] - mg["built_year"]
    mg["gt_below_5000"] = mg["gross_tonnage"].lt(5000).astype("boolean").mask(mg["gross_tonnage"].isna())
    if not (len(mg) == len(df) and mg[["imo", "year"]].equals(df[["imo", "year"]])):
        raise RuleCheckFailed("9-4 통합 후 행 수나 순서가 바뀜 (노트북 assert)")
    if not mg[df.columns].equals(df):
        raise RuleCheckFailed("9-4 통합 후 MRV 열 값이 바뀜 (노트북 assert)")
    st.update(built_after_report_rows=int((mg["built_year"] > mg["year"]).sum()),          # 9-5 점검
              gt_below_5000_ships=int(mg.loc[mg["gt_below_5000"].fillna(False), "imo"].nunique()),
              no_spec_rows=int(mg["gross_tonnage"].isna().sum()))
    return mg, st


# ════════════════════════════════════════════════════════════════════
# [10-1]~[10-6] CII 등급 — EU 항해 기준 추정 (원래 02_cii_rating_v6)
# ════════════════════════════════════════════════════════════════════
CII_TYPE = {
    "Bulk carrier": "Bulk carrier", "Gas carrier": "Gas carrier", "LNG carrier": "LNG carrier",
    "Oil tanker": "Tanker", "Chemical tanker": "Tanker", "Container ship": "Container ship",
    "General cargo ship": "General cargo ship", "Refrigerated cargo carrier": "Refrigerated cargo carrier",
    "Combination carrier": "Combination carrier",
    "Vehicle carrier": "Ro-ro cargo ship (vehicle carrier)", "Ro-ro ship": "Ro-ro cargo ship",
    "Container/ro-ro cargo ship": "Ro-ro cargo ship", "Ro-pax ship": "Ro-ro passenger ship",
    "Passenger ship": "Cruise passenger ship",
    "Passenger ship (Cruise Passenger ship)": "Cruise passenger ship",
}
GT_TYPES = ["Ro-ro cargo ship (vehicle carrier)", "Ro-ro cargo ship", "Ro-ro passenger ship",
            "Ro-ro passenger ship (high-speed craft)", "Cruise passenger ship"]
ICE_EQUIV = {"IC": "IC", "IB": "IB", "IA": "IA", "IA Super": "IAS",
             "PC7": "IA", "PC6": "IAS", "PC5": "IAS", "PC4": "IAS", "PC3": "IAS", "PC2": "IAS", "PC1": "IAS"}
FI = {"IC": (1.0041, 58.5), "IB": (1.0067, 62.7), "IA": (1.0099, 95.1), "IAS": (1.0151, 228.7)}
Z = {2019: 0, 2020: 1, 2021: 2, 2022: 3, 2023: 5, 2024: 7, 2025: 9, 2026: 11}
BASIS_YEAR = 2026


def cii_params(t, dwt, gt):
    """[10-2] 반환: (달성 CII 용량, 기준선 용량, a, c, (exp d1, d2, d3, d4)) — G2 표 1, G4 표 1"""
    if t == "Bulk carrier":
        return dwt, min(dwt, 279000), 4745, 0.622, (0.86, 0.94, 1.06, 1.18)
    if t == "Gas carrier":
        return (dwt, dwt, 14405e7, 2.071, (0.81, 0.91, 1.12, 1.44)) if dwt >= 65000 else \
               (dwt, dwt, 8104, 0.639, (0.85, 0.95, 1.06, 1.25))
    if t == "Tanker":
        return dwt, dwt, 5247, 0.610, (0.82, 0.93, 1.08, 1.28)
    if t == "Container ship":
        return dwt, dwt, 1984, 0.489, (0.83, 0.94, 1.07, 1.19)
    if t == "General cargo ship":
        return (dwt, dwt, 31948, 0.792, (0.83, 0.94, 1.06, 1.19)) if dwt >= 20000 else \
               (dwt, dwt, 588, 0.3885, (0.83, 0.94, 1.06, 1.19))
    if t == "Refrigerated cargo carrier":
        return dwt, dwt, 4600, 0.557, (0.78, 0.91, 1.07, 1.20)
    if t == "Combination carrier":
        return dwt, dwt, 5119, 0.622, (0.87, 0.96, 1.06, 1.14)
    if t == "LNG carrier":
        if dwt >= 100000:
            return dwt, dwt, 9.827, 0.000, (0.89, 0.98, 1.06, 1.13)
        if dwt >= 65000:
            return dwt, dwt, 14479e10, 2.673, (0.78, 0.92, 1.10, 1.37)
        return dwt, 65000, 14779e10, 2.673, (0.78, 0.92, 1.10, 1.37)
    if t == "Ro-ro cargo ship (vehicle carrier)":
        if gt >= 57700:
            return gt, 57700, 3627, 0.590, (0.86, 0.94, 1.06, 1.16)
        return (gt, gt, 3627, 0.590, (0.86, 0.94, 1.06, 1.16)) if gt >= 30000 else \
               (gt, gt, 330, 0.329, (0.86, 0.94, 1.06, 1.16))
    if t == "Ro-ro cargo ship":
        return gt, gt, 1967, 0.485, (0.76, 0.89, 1.08, 1.27)
    if t == "Ro-ro passenger ship":
        return gt, gt, 2023, 0.460, (0.76, 0.92, 1.14, 1.30)
    if t == "Ro-ro passenger ship (high-speed craft)":
        return gt, gt, 4196, 0.460, (0.76, 0.92, 1.14, 1.30)
    if t == "Cruise passenger ship":
        return gt, gt, 930, 0.383, (0.87, 0.95, 1.06, 1.16)
    raise ValueError(t)


def cii_rating(mg):
    st = {}
    # ── 10-1 CII 선종 + 고속선 근사 판별
    unmapped = set(mg["ship_type_raw"]) - set(CII_TYPE)
    if unmapped:
        raise RuleCheckFailed(f"10-1 CII 선종에 대응 안 된 원본 선종 {sorted(unmapped)} — CII_TYPE에 추가 필요 (노트북 assert)")
    cii_type = mg["ship_type_raw"].map(CII_TYPE)
    dwt, gt = mg["dwt"], mg["gross_tonnage"]
    rp = cii_type.eq("Ro-ro passenger ship")
    hsc_ship = (pd.DataFrame({"imo": mg["imo"], "name": mg["name"], "spd": mg["speed_kn"], "dg": dwt / gt, "gt": gt})[rp]
                .groupby("imo").agg(name=("name", "last"), spd=("spd", "median"), dg=("dg", "first"), gt=("gt", "first"), n=("spd", "size")))
    hsc_ships = hsc_ship[(hsc_ship["spd"] >= 20) & (hsc_ship["dg"] < 0.13) & (hsc_ship["gt"] < 15000)]
    hsc = rp & mg["imo"].isin(hsc_ships.index)
    cii_type = cii_type.where(~hsc, "Ro-ro passenger ship (high-speed craft)")
    st["hsc_ships"] = int(len(hsc_ships))

    # ── 10-2 용량·기준선·등급 경계
    CP = pd.DataFrame([cii_params(t, d, g) for t, d, g in zip(cii_type, dwt, gt)],
                      columns=["cap", "cap_ref", "a", "c", "expd"], index=mg.index)
    cii_ref = CP["a"] * CP["cap_ref"] ** (-CP["c"])

    # ── 10-3 내빙 보정
    ice_eq = mg["ice_class"].map(ICE_EQUIV)
    if ice_eq.notna().sum() != mg["ice_class"].notna().sum():
        extra = sorted(set(mg["ice_class"].dropna()) - set(ICE_EQUIV))
        raise RuleCheckFailed(f"10-3 대응 안 된 내빙 등급 {extra} — ICE_EQUIV에 추가 필요 (노트북 assert)")
    dwt_based = ~cii_type.isin(GT_TYPES)
    fi = pd.Series(1.0, index=mg.index)
    for k_ice, (b0, b1) in FI.items():
        rows = ice_eq.eq(k_ice) & dwt_based
        fi[rows] = b0 + b1 / dwt[rows]
    fm = np.where(ice_eq.isin(["IA", "IAS"]), 1.05, 1.0)
    ice_factor = fi * fm

    # ── 10-4 달성·요구 CII와 등급
    year = mg["year"]
    applicable = (mg["gt_below_5000"].eq(False)).fillna(False).astype(bool)
    rated = applicable & year.isin(Z)
    attained = (mg["co2_t"] * 1e6 / (CP["cap"] * mg["distance_nm"])).where(applicable)
    attained_corr = attained / ice_factor
    required = (cii_ref * (1 - year.map(Z) / 100)).where(rated)
    cii_ratio = attained_corr / required
    expd = pd.DataFrame(CP["expd"].tolist(), index=mg.index, columns=["d1", "d2", "d3", "d4"])

    def grade(r, mask):
        out = pd.Series(pd.NA, index=mg.index, dtype="string")
        out[mask] = np.select([r < expd["d1"], r < expd["d2"], r < expd["d3"], r < expd["d4"]],
                              ["A", "B", "C", "D"], default="E")[mask.to_numpy()]
        return out

    rating = grade(cii_ratio, rated)
    chk = (mg["co2_per_nm"] * 1000 / CP["cap"]).where(applicable)
    if not np.allclose(attained.dropna(), chk.dropna(), rtol=1e-9):
        raise RuleCheckFailed("10-4 달성 CII 확인 계산 불일치 (노트북 assert)")
    required_26 = (cii_ref * (1 - Z[BASIS_YEAR] / 100)).where(applicable)
    ratio_26 = attained_corr / required_26
    rating_26 = grade(ratio_26, applicable)
    st.update(rated_rows=int(rated.sum()), rated_2026basis_rows=int(applicable.sum()),
              rating_latest_year=rating[year.eq(year.max())].value_counts().sort_index().to_dict())

    # ── 10-5 열 추가
    mg["cii_ship_type"] = cii_type
    mg["cii_hsc_proxy"] = hsc
    mg["cii_capacity"] = CP["cap"].where(applicable)
    mg["cii_ice_factor"] = ice_factor
    mg["cii_attained"] = attained
    mg["cii_attained_corr"] = attained_corr
    mg["cii_required"] = required
    mg["cii_ratio"] = cii_ratio
    mg["cii_rating"] = rating
    mg["cii_official_year"] = year.ge(2023)
    mg["cii_ratio_2026basis"] = ratio_26
    mg["cii_rating_2026basis"] = rating_26

    # ── 10-6 CII 선종 변경 표시 (직전 보고 연도와 비교)
    order = mg.sort_values(["imo", "year"]).index
    by_ship = lambda s: s[order].groupby(mg.loc[order, "imo"])          # noqa: E731
    type_prev = pd.Series(pd.NA, index=mg.index, dtype="string")
    type_prev[order] = by_ship(cii_type).shift().astype("string")
    type_changed = pd.Series(pd.NA, index=mg.index, dtype="boolean")
    has_prev = type_prev.notna()
    type_changed[has_prev] = (type_prev[has_prev] != cii_type[has_prev]).to_numpy()
    mg["cii_ship_type_prev"] = type_prev
    mg["cii_type_changed"] = type_changed
    st["cii_type_changed_rows"] = int(type_changed.fillna(False).sum())
    return mg, st


def build_merged(df, spec_path):
    """9~10단계: (통합 df, stats)"""
    mg, st9 = merge_specs(df, spec_path)
    mg, st10 = cii_rating(mg)
    return mg, {"specs": st9, "cii": st10}


# ════════════════════════════════════════════════════════════════════
# [11-1] 통합 파일 열 사전
# ════════════════════════════════════════════════════════════════════
NEW_DICT = {
    "built_year":    ("건조연도 (선박 제원 파일)", "년", "9"),
    "gross_tonnage": ("총톤수 GT (선박 제원 파일). 5,000 미만인 배도 남겨 둠 (분석 범위 적용은 모델 단계에서 결정)", "-", "9"),
    "dwt":           ("재화중량 Summer DWT (선박 제원 파일). avg_load·co2_per_tw_dwt의 dwt carried와 다름", "t", "9"),
    "length_m":      ("선박 길이 (선박 제원 파일). 결측 = 제원 미등록 (대부분 2025년 신조선)", "m", "9"),
    "beam_m":        ("선박 폭 (선박 제원 파일). 길이/폭 > 12로 오기재가 분명한 3척은 결측", "m", "9"),
    "ship_age":      ("그해 기준 선령 = year − built_year (제원 파일의 2026년 기준 Age는 사용하지 않음)", "년", "9"),
    "gt_below_5000": ("총톤수 5,000 미만인 배 (분석 범위 밖일 수 있음). 행은 남기고 표시만 — 모델 단계에서 넣고/빼고 비교해 결정. 제원이 없으면 결측", "True/False", "9"),
    "cii_ship_type":     ("CII 선종 (MARPOL 부속서 VI 제2규칙). ship_type_raw에서 대응, Container/ro-ro는 로로 화물선, 고속 Ro-pax는 고속선(HSC)", "-", "10"),
    "cii_hsc_proxy":     ("고속선(SOLAS 제X장)으로 판별한 Ro-pax인지 — 근사 (중앙 속력 20kn 이상 · DWT/GT 0.13 미만 · GT 15,000 미만). True면 G2 고속선 기준선(a = 4196) 적용", "True/False", "10"),
    "cii_capacity":      ("달성 CII 계산에 쓴 용량 (벌크·탱커·컨테이너·가스·LNG·일반화물·냉동·겸용 = DWT, 로로·자동차운반·로팩스·크루즈 = GT). CII 대상 아니면 결측", "DWT 또는 GT", "10"),
    "cii_ice_factor":    ("내빙 보정 계수 fi × fm (G5, MEPC.308(73) 표 2, fm = 1.05). 블록 계수가 없어 fiCb = 1.0, 극지 등급은 근사 대응. 내빙선 아니면 1.0", "-", "10"),
    "cii_attained":      ("달성 CII (보정 전) = CO2 ÷ (용량 × 거리) = 거리당 CO2 × 1000 ÷ 용량. EU 항해 기준. 총톤수 5,000 미만·제원 없음은 결측", "g CO2/용량·nm", "10"),
    "cii_attained_corr": ("달성 CII (내빙 보정 후) = cii_attained ÷ cii_ice_factor. 등급 판정에 사용", "g CO2/용량·nm", "10"),
    "cii_required":      ("요구 CII = 2019년 기준값 a × 용량^(−c) × (1 − Z/100). 2018년분·CII 대상 아님은 결측", "g CO2/용량·nm", "10"),
    "cii_ratio":         ("cii_attained_corr ÷ cii_required. 1 미만이면 요구값보다 좋음. 등급 경계(선종별 exp(d))와 비교해 등급 결정", "-", "10"),
    "cii_rating":        ("CII 등급 A~E — EU 항해 기준 추정, 공식 등급 아님 (MRV는 EU 관련 항해만 집계). 2019~2025년분, 총톤수 5,000 이상만", "A~E", "10"),
    "cii_official_year": ("CII가 공식 적용되는 연도인지 (2023년분부터 True). 2019~2022년분 등급은 참고용", "True/False", "10"),
    "cii_ratio_2026basis":  ("달성 CII(보정 후) ÷ 2026년 요구 CII(2019년 기준값 × 0.89). 모든 해를 같은 잣대로 비교", "-", "10"),
    "cii_rating_2026basis": ("2026년 규제 기준으로 환산한 CII 등급 A~E (그해 실제 적용 기준 아님, EU 항해 기준 추정). 2018~2025년분, 총톤수 5,000 이상", "A~E", "10"),
    "cii_ship_type_prev":   ("직전 보고 연도의 CII 선종. 첫 보고 연도는 결측", "-", "10"),
    "cii_type_changed":     ("직전 보고 연도와 CII 선종이 다른지 (True = 선종 표기 변경으로 기준선이 바뀜 → 효율과 무관하게 등급이 튈 수 있음). 첫 보고 연도는 결측. 과거만 비교", "True/False", "10"),
}


def merged_column_dictionary(mg, col_dict):
    """col_dict: 정제 파일 열 사전(8-7). 파이프라인 추가 열도 포함해 통합 파일 열 순서대로"""
    mg_dict = pd.DataFrame(NEW_DICT, index=["뜻", "단위", "단계"]).T
    mg_dict["타입"] = mg[list(NEW_DICT)].dtypes.astype(str)
    mg_dict["결측률"] = mg[list(NEW_DICT)].isna().mean().round(3)
    merged_dict = pd.concat([col_dict, mg_dict]).reindex(mg.columns)
    if not (merged_dict.index.tolist() == mg.columns.tolist() and merged_dict["뜻"].notna().all()):
        raise RuleCheckFailed("11-1 열 사전과 통합 파일 열이 다름 (노트북 assert)")
    return merged_dict
