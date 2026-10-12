"""배별 연료비·탄소 비용(2026~2028)과 2025년 대비 변화의 분해 — 최재희 님 `비용_계산.py` 이식.

식은 팀 스크립트 그대로이고, 바뀐 것은 입력뿐이다.
  - 예측: v6 예측 파일 대신 프레임워크의 전체 효율(정박 포함 거리당 CO₂) 예측 `fct_h*_p*` (회귀 v4 이식).
    연료 구성이 2025년과 같다고 보므로 연료 예측 비율 = 거리당 CO₂ 예측 비율 (팀 5절 전제와 같음).
  - 동급 기준값(표 3): 공통잔차의 동급 중간(해상 효율) + 이 배의 정박 → 항해분만 동급으로 바꾸고 정박은 그대로.

표 1 배별 비용 (배 × 연도 × 가격 시나리오): 연료비, 탄소 비용, 합계, 예측 80% 범위, 항목 비중
표 2 변화의 분해: 2025년 대비 변화를 효율·규제·가격으로 나눔 (곱으로 된 비용의 변화를 요인별 몫으로 — 몫의 합 = 변화)
표 3 동급 대비: 동급 기준만큼 썼다면 냈을 비용과의 차이
금액 단위는 설정 `unit` (기본 백만 원). 열 이름은 팀 표와 같게 한국어로 둔다.
"""
from __future__ import annotations

import itertools
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from shared.config import load_yaml, path

SCENARIOS = ["낮음", "기준", "높음"]
KINDS = {"대표": 50, "하한": 10, "상한": 90}          # 예측 분위 (p50 = 대표값, 80% 범위 = p10~p90)
TYPE_KO = {
    "container": "컨테이너선", "tanker": "유조선", "bulk": "벌크선", "chemical_tanker": "화학제품운반선", "general_cargo": "일반화물선",
    "vehicle_carrier": "자동차운반선", "ro_pax": "로팩스", "gas_carrier": "가스운반선", "lng_carrier": "LNG선", "ro_ro": "로로선",
    "reefer": "냉동화물선", "cruise": "크루즈선", "container_ro_ro": "컨테이너·로로선",
}


def load_settings(cfg_path: str | Path = "config/cost.yaml") -> tuple[dict[str, Any], dict[str, tuple[str, str]], dict]:
    """(값, {이름: (상태, 설명)}, 원본 설정). 값은 계산이 읽고, 상태·설명은 요약에 확정이 아닌 설정을 나열할 때 쓴다."""
    raw = load_yaml(cfg_path)
    s = {k: v["value"] for k, v in raw["settings"].items()}
    meta = {k: (v["status"], v.get("note", "")) for k, v in raw["settings"].items()}
    s["ets_share"] = {int(k): float(v) for k, v in s["ets_share"].items()}
    return s, meta, raw


def load_prices(file: str | Path) -> pd.DataFrame:
    p = pd.read_csv(path(file)).set_index("항목")
    return p.rename(columns={"기준연도_2025": "2025"})


# ═══════════════════════ 연료 단가 (달러/톤): 배마다 연료 구성으로 가중 ═══════════════════════
def fuel_unit_price(d: pd.DataFrame, prices: pd.DataFrame, col: str, mix: str, s: dict) -> pd.Series:
    """col: '2025' 또는 시나리오 이름.  mix: 'A' 또는 'B'.  LPG 추정은 NaN."""
    m = s["oil_mix"][mix]
    cpf = d["co2_per_fuel"]
    p_res, p_mgo, p_lng = prices.loc[m["resid_price"], col], prices.loc["경유(MGO)", col], prices.loc["LNG", col]
    mgo = ((cpf - m["resid_ef"]) / (s["mgo_ef"] - m["resid_ef"])).clip(0, 1)
    oil = mgo * p_mgo + (1 - mgo) * p_res
    lng = ((m["resid_ef"] - cpf) / (m["resid_ef"] - s["lng_ef"])).clip(0, 1) if s["lng_mix"] else 1.0
    lng_price = lng * p_lng + (1 - lng) * p_res
    g = d["fuel_group"]
    out = pd.Series(np.nan, index=d.index)
    out[g == "석유계"] = oil[g == "석유계"]
    out[g == "LNG 계열"] = lng_price[g == "LNG 계열"]
    if s["other_alt_as_oil"]:
        out[g == "기타 대체연료"] = oil[g == "기타 대체연료"]
    if s["lpg_price"] is not None:
        out[g == "LPG 추정"] = s["lpg_price"]
    return out


# ═══════════════════════ 분해: 곱으로 된 비용의 변화를 요인별로 나눈다 ═══════════════════════
def split_product(f0, f1, order=None):
    """f0, f1: 요인별 배열 목록(기준 시점, 비교 시점). 곱의 변화를 요인별 몫으로 나눠 목록으로 돌려준다. 몫의 합 = 곱의 변화.
    order 가 없으면 모든 순서의 평균(겹치는 몫을 똑같이 나눔), 있으면 그 순서대로 하나씩 바꾼다."""
    n = len(f0)
    orders = [order] if order is not None else list(itertools.permutations(range(n)))
    out = [0.0] * n
    for od in orders:
        cur = list(f0)
        for i in od:
            before = np.prod(np.array(cur, dtype=float), axis=0)
            cur[i] = f1[i]
            out[i] = out[i] + (np.prod(np.array(cur, dtype=float), axis=0) - before)
    return [o / len(orders) for o in out]


def carbon_factors(d: pd.DataFrame, r: np.ndarray, year: int, eua: float, fx: float, s: dict) -> list[np.ndarray]:
    """탄소 비용(원) = 배출량 × 규제(적용률 × 가스 범위) × 배출권 가격 × 환율.  (배출량, 규제, 가격) 요인 배열을 돌려준다."""
    q = d["ets_co2_t"].to_numpy() * r
    ets, eq = d["ets_co2_t"], d["ets_co2eq_t"]
    gas = np.where(ets > 0, eq / ets.where(ets > 0, 1), 1.0) if year >= s["ghg_from"] else 1.0
    reg = s["ets_share"][year] * gas * np.ones(len(d))
    return [q, reg, np.full(len(d), eua * fx)]


# ═══════════════════════ 표 1·2 ═══════════════════════
def build(d: pd.DataFrame, ratios: dict[tuple[int, str], np.ndarray], prices: pd.DataFrame, s: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """d: 기준 연도 배 한 줄씩 (imo, 선박명, 선종, fuel_group, fuel_t, co2_per_fuel, ets_co2_t, ets_co2eq_t).
    ratios[(연도, '대표'|'하한'|'상한')] = 그해 거리당 효율 예측 ÷ 기준 연도 값 (배열, d 와 같은 순서)."""
    fxu, fxe = prices.loc["환율 USD", "기준"], prices.loc["환율 EUR", "기준"]
    y0, U = s["base_year"], s["unit"]
    ones = np.ones(len(d))
    base_c = carbon_factors(d, ones, y0, prices.loc["배출권(EUA)", "2025"], fxe, s)
    c0 = np.prod(base_c, axis=0)
    u0 = {mx: fuel_unit_price(d, prices, "2025", mx, s).to_numpy() * fxu for mx in "AB"}
    f0 = {mx: d["fuel_t"].to_numpy() * u0[mx] for mx in "AB"}

    t1, t2 = [], []
    for year in s["years"]:
        r = {k: ratios[(year, k)] for k in KINDS}
        for sc in SCENARIOS:
            eua = prices.loc["배출권(EUA)", sc]
            u1 = {mx: fuel_unit_price(d, prices, sc, mx, s).to_numpy() * fxu for mx in "AB"}
            row = pd.DataFrame({"imo": d["imo"], "선박명": d["선박명"], "선종": d["선종"], "연료그룹": d["fuel_group"], "연도": year, "시나리오": sc})
            dec = {}
            for k in KINDS:
                cf = carbon_factors(d, r[k], year, eua, fxe, s)
                c1 = np.prod(cf, axis=0)
                fuel_t = d["fuel_t"].to_numpy() * r[k]
                fa = fuel_t * u1["A"]
                row[f"연료량_t_{k}"] = fuel_t
                row[f"ETS배출량_t_{k}"] = cf[0] * cf[1] / s["ets_share"][year]
                row[f"연료비_{k}"] = fa / U
                row[f"탄소비용_{k}"] = c1 / U
                row[f"총비용_{k}"] = (fa + c1) / U
                ce, cr, cp = split_product(base_c, cf)
                fe, fp = split_product([d["fuel_t"].to_numpy(), u0["A"]], [fuel_t, u1["A"]])
                dec[k] = {"총변화": fa + c1 - f0["A"] - c0, "효율": ce + fe, "규제": cr, "가격_연료": fp, "가격_배출권": cp}
            fb = d["fuel_t"].to_numpy() * r["대표"] * u1["B"]
            row["연료비_가정B_대표"] = fb / U
            row["총비용_가정B_대표"] = (fb + np.prod(carbon_factors(d, r["대표"], year, eua, fxe, s), axis=0)) / U
            row["적용률"] = s["ets_share"][year]
            row["연료비_비중_pct"] = row["연료비_대표"] / row["총비용_대표"] * 100
            row["탄소비용_비중_pct"] = row["탄소비용_대표"] / row["총비용_대표"] * 100
            row["연료비_2025"], row["탄소비용_2025"] = f0["A"] / U, c0 / U
            row["총비용_2025"] = (f0["A"] + c0) / U
            row["표시"] = d["fuel_group"].map({"LPG 추정": "연료비 없음(LPG 가격 미정)", "기타 대체연료": "연료비 근사(석유계 가격)"}).fillna("")
            t1.append(row)

            m = dec["대표"]
            price = m["가격_연료"] + m["가격_배출권"]
            parts = np.vstack([m["효율"], m["규제"], price])
            tot_abs = np.abs(parts).sum(axis=0)
            share = np.where(tot_abs > 0, np.abs(parts) / np.where(tot_abs > 0, tot_abs, 1) * 100, np.nan)
            nz = np.where(np.abs(parts) > 1e-6, np.sign(parts), 0)
            mixed = (nz.max(axis=0) > 0) & (nz.min(axis=0) < 0)
            t2.append(pd.DataFrame({
                "imo": d["imo"], "선박명": d["선박명"], "선종": d["선종"], "연도": year, "시나리오": sc,
                "총변화_대표": m["총변화"] / U, "총변화_하한": dec["하한"]["총변화"] / U, "총변화_상한": dec["상한"]["총변화"] / U,
                "효율몫_대표": m["효율"] / U, "효율몫_하한": dec["하한"]["효율"] / U, "효율몫_상한": dec["상한"]["효율"] / U,
                "규제몫": m["규제"] / U, "가격몫": price / U, "가격몫_연료": m["가격_연료"] / U, "가격몫_배출권": m["가격_배출권"] / U,
                "효율_크기비중_pct": share[0], "규제_크기비중_pct": share[1], "가격_크기비중_pct": share[2],
                "효율_방향": np.where(m["효율"] > 0, "늘림", np.where(m["효율"] < 0, "줄임", "변화 없음")),
                "가격_방향": np.where(price > 0, "늘림", np.where(price < 0, "줄임", "변화 없음")),
                "방향_혼재": mixed,
                "검산_합빼기총변화": (m["효율"] + m["규제"] + price - m["총변화"]) / U,
            }))
    return pd.concat(t1, ignore_index=True), pd.concat(t2, ignore_index=True)


# ═══════════════════════ 표 3: 동급 대비 ═══════════════════════
def peer_fuel_per_nm(d: pd.DataFrame, sea_peer_kg_nm: pd.Series, berth_kg_nm: pd.Series) -> tuple[pd.Series, pd.Series]:
    """동급이라면 썼을 거리당 연료(kg/nm). 항해분은 공통잔차의 동급 중간(해상 효율, kg CO₂/nm)으로 바꾸고 정박분은 이 배 값 그대로.
    연료로 바꾸는 계수는 이 배의 연료 1톤당 CO₂ (연료 구성은 그대로라는 전제)."""
    peer = (sea_peer_kg_nm + berth_kg_nm) / d["co2_per_fuel"]
    note = pd.Series("공통잔차 동급 중간(해상) + 이 배의 정박", index=d.index).where(sea_peer_kg_nm.notna(), "기준값 없음")
    return peer, note


def build_t3(d: pd.DataFrame, t1: pd.DataFrame, peer: pd.Series, note: pd.Series, s: dict) -> pd.DataFrame:
    actual = d["fuel_t"] * 1000 / d["distance_nm"]
    k = d[["imo"]].assign(동급기준_거리당연료_2025=peer, 실제_거리당연료_2025=actual, 동급대비_2025_pct=(actual / peer - 1) * 100,
                          기준값_출처=note, 연료량_2025_t=d["fuel_t"], ETS적용_2025=s["ets_share"][s["base_year"]])
    t = t1[["imo", "선박명", "선종", "연도", "시나리오", "연료량_t_대표", "연료비_대표", "탄소비용_대표", "총비용_대표"]].merge(k, on="imo")
    # 동급 기준 비용: 이 배가 2025년 동급 기준만큼만 썼을 때의 비용 (그 해의 가격·규제 적용). 비용은 연료량에 비례
    ratio = t["동급기준_거리당연료_2025"] * (t["연료량_2025_t"] / t["실제_거리당연료_2025"]) / t["연료량_t_대표"]
    t["동급기준_총비용"] = t["총비용_대표"] * ratio
    t["동급대비_차이"] = t["총비용_대표"] - t["동급기준_총비용"]
    t["동급대비_차이_pct"] = (t["총비용_대표"] / t["동급기준_총비용"] - 1) * 100
    return t.drop(columns=["연료량_2025_t", "ETS적용_2025", "연료량_t_대표"])
