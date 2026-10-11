"""합성 표본 데이터 (뼈대 확인용). ⚠ 실제 MRV 가 아니다. 숫자를 발표·분석에 쓰지 말 것.

실제 MRV 파일과 같은 '불편함'을 일부러 넣었다 → 파이프라인이 그 상황을 처리하는지 확인용:
  - 연도마다 열 이름이 다름 (2022년까지 'CO2', 2023년부터 'CO₂'), 회사명은 2024년부터만
  - 거리 없음 (거리당 CO₂만), 제원은 별도 파일
  - 개명 (ANFA → LEOPOLD → NEXUS), 불가능한 적재량, LNG 추정 배, 셔틀 탱커 운영사, 정박 급증(TIGANI형), 짧은 해상 시간
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

SAMPLE_VERSION = "sample-v1"
TYPES = {  # 표시 이름(원본), 척수, dwt 중간, 속력 기준, 효율 배수
    "container": ("Container ship", 60, 60_000, 15.0, 1.30),
    "tanker": ("Oil tanker", 60, 100_000, 11.5, 1.00),
    "bulk": ("Bulk carrier", 60, 75_000, 11.5, 0.85),
    "ro_pax": ("Ro-pax ship", 30, 8_000, 17.0, 3.00),
}
OLD = {  # 2018~2022 원본 열 이름
    "imo": "IMO Number", "name": "Name", "ship_type_raw": "Ship type", "year": "Reporting Period",
    "fuel_t": "Total fuel consumption [m tonnes]", "co2_t": "Total CO2 emissions [m tonnes]",
    "berth_co2_t": "CO2 emissions at berth [m tonnes]",
    "co2_per_nm_kg": "Annual average CO2 emissions per distance [kg CO2 / n mile]",
    "sea_hours": "Annual Total time spent at sea [hours]", "co2_intra_eu_t": "CO2 emissions intra-EU [m tonnes]",
    "cargo_t": "Annual average cargo carried [m tonnes]",
}
NEW = {  # 2023~ 원본 열 이름
    **OLD,
    "co2_t": "Total CO₂ emissions [m tonnes]",
    "berth_co2_t": "CO₂ emissions which occurred within ports under a MS jurisdiction at berth [m tonnes]",
    "co2_per_nm_kg": "Annual average CO₂ emissions per distance [kg CO₂ / n mile]",
    "co2_intra_eu_t": "CO₂ emissions from all voyages between ports under a MS jurisdiction [m tonnes]",
    "company": "Company name", "ets_co2_t": "Total CO₂ emissions subject to ETS [m tonnes]",
}


def generate(out_dir: str | Path, years: list[int], seed: int = 7) -> list[Path]:
    rng = np.random.default_rng(seed)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    ships, rows = [], []
    imo = 9_300_001
    for t, (raw, n, dwt_mid, v0, mult) in TYPES.items():
        for i in range(n):
            ships.append({
                "imo": imo, "type": t, "raw": raw, "v0": v0, "mult": mult,
                "dwt": float(round(dwt_mid * np.exp(rng.normal(0, 0.45)))),
                "build_year": int(rng.integers(2000, 2018)),
                "u": rng.normal(0, 0.08), "drift": rng.normal(0, 0.01),
                "company": f"{t.title()} Line {i % 7 + 1}", "name": f"{t.upper()[:3]} STAR {i + 1}",
                "ice": "1A" if rng.random() < 0.08 else None, "fuel_ratio": 3.15, "special": None,
            })
            imo += 13

    # 이야기가 있는 배들 (기획서 사례를 흉내만 낸 합성)
    tanker = [s for s in ships if s["type"] == "tanker"]
    tanker[0].update(name="TIGANI", dwt=112_763.0, build_year=2017, u=-0.10, drift=0.025, special="berth_spike")
    tanker[1].update(name="NEXUS", special="cargo_error", rename={2018: "ANFA", 2019: "ANFA", 2020: "LEOPOLD", 2021: "LEOPOLD"})
    for s in tanker[2:6]:
        s.update(company="Shuttle Tankers AS", u=0.35)
    [s for s in ships if s["type"] == "container"][0].update(name="LNG PIONEER", fuel_ratio=2.75)

    for s in ships:
        for y in years:
            if y <= s["build_year"] or rng.random() < 0.08:
                continue
            age = y - s["build_year"]
            speed = s["v0"] * np.exp(rng.normal(0, 0.08))
            sea_hours = float(rng.uniform(300, 6500)) if rng.random() < 0.12 else float(rng.uniform(1500, 6500))
            dist = speed * sea_hours
            noise = rng.normal(0, 0.06) * (2.0 if sea_hours < 500 else 1.0)
            ln_eff = (np.log(0.65 * s["mult"]) + 0.55 * np.log(s["dwt"]) + s["u"] + s["drift"] * (y - 2018)
                      - 0.012 * (y - 2018) + 0.004 * age + 0.6 * np.log(speed / s["v0"]) + noise)
            sea_co2 = np.exp(ln_eff) * dist / 1000
            berth = float(np.exp(rng.normal(np.log(0.06 * sea_co2 + 40), 0.35)))
            if s["special"] == "berth_spike" and y == years[-1]:
                berth = 1.17 * sea_co2
            co2 = sea_co2 + berth
            cargo = s["dwt"] * rng.uniform(0.4, 0.8)
            if s["special"] == "cargo_error" and y == years[-1]:
                cargo = s["dwt"] * 26
            rows.append({
                "imo": s["imo"], "year": y, "name": s.get("rename", {}).get(y, s["name"]), "ship_type_raw": s["raw"],
                "fuel_t": round(co2 / s["fuel_ratio"], 2), "co2_t": round(co2, 2), "berth_co2_t": round(berth, 2),
                "co2_per_nm_kg": round(co2 * 1000 / dist, 4), "sea_hours": round(sea_hours, 1),
                "co2_intra_eu_t": round(co2 * rng.uniform(0.0, 0.9 if s["type"] != "ro_pax" else 1.0), 2),
                "cargo_t": round(cargo, 1), "company": s["company"] if y >= 2024 else None,
                "ets_co2_t": round(co2 * rng.uniform(0.5, 1.0), 2) if y >= 2024 else None,
            })

    raw = pd.DataFrame(rows)
    files = []
    for y, g in raw.groupby("year"):
        names = NEW if y >= 2023 else OLD
        g = g[[c for c in names if c in g.columns]].rename(columns=names)
        p = out / f"mrv_{y}.csv"
        g.to_csv(p, index=False, encoding="utf-8")
        files.append(p)

    specs = pd.DataFrame([{
        "imo": s["imo"], "dwt": s["dwt"], "gt": round(s["dwt"] * 0.6), "length_m": round(6.0 * s["dwt"] ** (1 / 3), 1),
        "build_year": s["build_year"], "ice_class": s["ice"], "eedi": None,
    } for s in ships])
    specs.to_csv(out / "specs.csv", index=False, encoding="utf-8")
    (out / "VERSION").write_text(SAMPLE_VERSION, encoding="utf-8")
    return files
