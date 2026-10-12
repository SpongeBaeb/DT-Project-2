"""실제 MRV 파일 양식(구양식 62열 계열 / 신양식 Full·Partial ERs)을 흉내 낸 합성 원본 생성.

노트북 규칙이 다루는 경우를 일부러 넣는다: Division by zero, CO2·연료 0, 거리당 CO2 극단값, 속력 이상,
해상시간 72시간 미만·1년 초과·거리와 같은 값, 총 CO2 2배 오류(보정 가능/불가), 2025년 신규 일반화물선,
크루즈/비크루즈/판별 불가 여객선, Other ship types, 겸용선, 기술효율 표기 변형·극단값, 선사명 변형,
회사 IMO 앞자리 0, Partial ERs, 항해 유형 합 오류, Ro-pax 적재량 오류, ETS 파일값 > 총량.

    python tests/make_synthetic_raw.py <프로젝트 폴더>            # 2018~2025 기본 8개 + data_sources.yaml
    python tests/make_synthetic_raw.py <폴더> --add-version 2025  # 2025년 새 버전(v59) 추가
    python tests/make_synthetic_raw.py <폴더> --add-year 2026     # 새 보고연도
    python tests/make_synthetic_raw.py <폴더> --add-year 2026 --break-schema  # 열 이름을 바꾼 새 연도
"""
import argparse
import random
import sys
from pathlib import Path

from openpyxl import Workbook

TW = [("mass", "m tonnes"), ("volume", "m³"), ("dwt", "dwt carried"), ("pax", "pax"), ("freight", "m tonnes")]
PARTS_H = ["CO₂ emissions from all voyages between ports under a MS jurisdiction [m tonnes]",
           "CO₂ emissions from all voyages which departed from ports under a MS jurisdiction [m tonnes]",
           "CO₂ emissions from all voyages to ports under a MS jurisdiction [m tonnes]",
           "CO₂ emissions which occurred within ports under a MS jurisdiction at berth [m tonnes]"]
VERSIONS = {2018: (275, "29032026"), 2019: (228, "13082026"), 2020: (210, "25092026"), 2021: (219, "25092026"),
            2022: (241, "06022026"), 2023: (92, "29092026"), 2024: (246, "01102026"), 2025: (58, "15092026")}


def old_headers(year):
    t = "Annual Total time spent at sea [hours]" if year <= 2019 else "Annual Time spent at sea [hours]"
    tt = "Total time spent at sea [hours]" if year <= 2019 else "Time spent at sea [hours]"
    return (["IMO Number", "Name", "Ship type", "Reporting Period", "Technical efficiency", "Port of Registry",
             "Home Port", "Ice Class", "DoC issue date", "DoC expiry date", "Verifier Name",
             "Verifier Accreditation number", "Verifier Country", "A", "B", "C", "D",
             "Total fuel consumption [m tonnes]", "Fuel consumptions assigned to On laden [m tonnes]",
             "Total CO₂ emissions [m tonnes]", *PARTS_H, "CO₂ emissions assigned to Passenger transport [m tonnes]",
             t, "Annual average Fuel consumption per distance [kg / n mile]",
             "Annual average CO₂ emissions per distance [kg CO₂ / n mile]"]
            + [f"Annual average CO₂ emissions per transport work ({b}) [g CO₂ / {u} · n miles]" for b, u in TW]
            + ["Through ice [n miles]", tt, "Total time spent at sea through ice [hours]"])


def new_headers():
    return (["IMO Number", "Name", "Ship type", "Reporting Period", "Technical efficiency", "Port of Registry",
             "Home Port", "Ice Class", "Name", "IMO Number", "DoC issue date", "DoC expiry date", "Verifier Name",
             "Verifier Accreditation number", "Verifier Country", "A", "B", "C", "D",
             "Total fuel consumption [m tonnes]", "Total CO₂ emissions [m tonnes]", "Total CH₄ emissions [m tonnes]",
             "Total N₂O emissions [m tonnes]", "Total CO₂eq emissions [m tonnes]",
             "CO2 emissions to be reported under Directive 2003/87/EC [m tonnes]",
             "CH₄ emissions to be reported under Directive 2003/87/EC [m tonnes]",
             "N₂O emissions to be reported under Directive 2003/87/EC [m tonnes]",
             "CO₂eq emissions to be reported under Directive 2003/87/EC [m tonnes]", *PARTS_H,
             "CO₂ emissions assigned to Passenger transport [m tonnes]", "Time spent at sea [hours]",
             "Distance through ice [n miles]", "Time spent at sea through ice [hours]",
             "Fuel consumption per distance [kg / n mile]", "CO₂ emissions per distance [kg CO₂ / n mile]",
             "CO₂eq emissions per distance [kg CO₂eq / n mile]"]
            + [f"CO₂ emissions per transport work ({b}) [g CO₂ / {u} · n miles]" for b, u in TW])


def imo_with_check(six):
    return six + str(sum(int(d) * w for d, w in zip(six, range(7, 1, -1))) % 10)


TYPES = (["Bulk carrier"] * 8 + ["Oil tanker"] * 5 + ["Chemical tanker"] * 4 + ["Container ship"] * 5
         + ["General cargo ship"] * 3 + ["LNG carrier", "Gas carrier", "Vehicle carrier", "Ro-ro ship",
                                         "Ro-pax ship", "Refrigerated cargo carrier", "Container/ro-ro cargo ship"])
BASIS = {"LNG carrier": "volume", "Container/ro-ro cargo ship": "volume", "General cargo ship": "dwt",
         "Ro-pax ship": "pax", "Passenger ship": "pax", "Passenger ship (Cruise Passenger ship)": "pax"}
COMPANIES = ["MSC Shipmanagement Ltd", "Zodiac Maritime Ltd", "Arab Maritime Petroleum Transport Company",
             "Eidsvaag AS", "Synergy Ocean Maritime Inc.", "Peter Dohle Schiffahrts-KG"]


def build_fleet(rng):
    ships = []
    for i in range(320):
        imo = imo_with_check(str(rng.randint(910000, 989999)))
        t = rng.choice(TYPES)
        first = rng.choice([2018] * 6 + [2019, 2020, 2021, 2022, 2023, 2024, 2025])
        ships.append({"imo": imo, "name": f"SHIP {i:03d}", "type": t, "first": first,
                      "last": rng.choice([2025] * 8 + [2021, 2023]), "eedi": rng.random() < 0.3})
    # 특별 선박
    S = lambda imo, t, first, last, **k: {"imo": imo, "name": k.pop("name", f"SPECIAL {imo}"), "type": t,
                                          "first": first, "last": last, "eedi": False, **k}
    ships += [
        S(imo_with_check("930001"), "Passenger ship", 2018, 2025, cruise_from=2023, name="CRUISE ONE"),
        S(imo_with_check("930002"), "Passenger ship", 2018, 2025, name="FERRY NONCRUISE"),
        S(imo_with_check("930003"), "Passenger ship", 2019, 2021, name="OLD PASSENGER"),
        S(imo_with_check("930004"), "Other ship types", 2018, 2025, name="TUG X"),
        S(imo_with_check("930005"), "Combination carrier", 2018, 2025, name="COMBO"),
        S(imo_with_check("930006"), "General cargo ship", 2022, 2025, name="GC OLD DIV0 2022", div0_years=[2022, 2023, 2024]),
    ]
    for k in range(12):   # 2025년 신규 소형 일반화물선
        ships.append(S(imo_with_check(str(940000 + k)), "General cargo ship", 2025, 2025, name=f"SMALL GC {k}"))
    ships.append(S("9481685", "Bulk carrier", 2018, 2018, name="KISHORE"))   # ⑤-6 예외 (v8)
    ships.append(S(imo_with_check("930007"), "Ro-pax ship", 2018, 2025, name="HSC JET"))             # 10-1 고속선 근사
    ships.append(S(imo_with_check("930008"), "Bulk carrier", 2018, 2025, name="SWITCHER",             # 10-6 CII 선종 변경
                   switch={2021: "General cargo ship", 2022: "General cargo ship", 2024: "Oil tanker"}))
    for k, ice in enumerate(["IA Super", "IB", "PC5", "PC7"]):                                       # 10-3 내빙 등급 대응
        ships.append(S(imo_with_check(str(930010 + k)), "Bulk carrier", 2019, 2025, name=f"ICE {ice}", ice=ice))
    for k in range(4):    # 2025년 신규 offshore
        ships.append(S(imo_with_check(str(950000 + k)), "Other ship types (Offshore)", 2025, 2025, name=f"OFFSHORE {k}"))
    return ships


def row_for(ship, year, rng, new_fmt):
    t = ship.get("switch", {}).get(year, ship["type"])                     # 해마다 선종 표기가 바뀌는 배 (10-6)
    if ship.get("cruise_from") and year >= ship["cruise_from"]:
        t = "Passenger ship (Cruise Passenger ship)"
    speed = rng.uniform(8, 16)
    time_h = round(rng.uniform(400, 7000), 2)
    dist = speed * time_h
    fuel = round(dist * rng.uniform(30, 380) / 1000, 2)          # 거리당 연료 30~380 kg/nm
    ef = 2.785 if t == "LNG carrier" else rng.choice([3.114, 3.151, 3.206, round(rng.uniform(3.114, 3.206), 4)])
    co2 = round(fuel * ef, 4)
    shares = [rng.random() for _ in range(4)]
    tot = sum(shares)
    parts = [round(co2 * s / tot, 2) for s in shares]
    b = BASIS.get(t, "mass")
    load = {"mass": rng.uniform(3000, 60000), "volume": rng.uniform(40000, 90000), "dwt": rng.uniform(3000, 12000),
            "pax": rng.uniform(150, 2000)}[b]
    co2_per_nm = co2 * 1000 / dist
    pax_share = rng.uniform(0.3, 0.6) if t == "Ro-pax ship" else None
    tw_val = (co2_per_nm * (pax_share or 1)) / load * 1000
    tw = {k: None for k, _ in TW}
    tw[b] = round(tw_val, 2)
    if t == "Ro-pax ship":
        tw["freight"] = round(rng.uniform(20, 80), 2)
    if ship["eedi"]:
        tech = f"EEDI ({rng.uniform(2, 15):.2f} gCO₂/t·nm)"
    elif year >= 2023 and rng.random() < 0.7:
        tech = f"EEXI ({rng.uniform(3, 20):.2f} gCO₂/t·nm)"
    else:
        tech = f"EIV ({rng.uniform(4, 25):.2f} gCO₂/t·nm)"
    if rng.random() < 0.03:
        tech = rng.choice(["Not Applicable", None, "Not Applicable (0 gCO₂/t·nm)", "0 gCO₂/t·nm"])
    r = {"imo": ship["imo"], "name": ship["name"], "type": t, "year": year, "tech": tech, "fuel": fuel, "co2": co2,
         "parts": parts, "pax_co2": round(co2 * pax_share, 2) if pax_share else None, "time": time_h,
         "fuel_per_nm": round(fuel * 1000 / dist, 2), "co2_per_nm": round(co2_per_nm, 2), "tw": tw,
         "ice": ship.get("ice", rng.choice([None] * 6 + ["IA", "IC"])), "mm": [rng.choice(["Yes", None]) for _ in range(3)],
         "company": rng.choice(COMPANIES), "company_imo": str(rng.randint(1000000, 9999999))}
    r["ice_dist"] = round(rng.uniform(0, 300), 1) if r["ice"] and rng.random() < 0.5 else (0 if rng.random() < 0.3 else None)
    r["ice_time"] = round(r["ice_dist"] / 8, 1) if r["ice_dist"] is not None else None
    if new_fmt:
        ch4 = fuel * (0.0172 if t == "LNG carrier" else 0.00005)
        n2o = fuel * 0.00018
        ets_share = rng.uniform(0.2, 0.9)
        r.update(ch4=round(ch4, 5), n2o=round(n2o, 5), co2eq=round(co2 + 28 * ch4 + 265 * n2o, 4),
                 co2_ets=round(co2 * ets_share, 4), ch4_ets=round(ch4 * ets_share, 5),
                 n2o_ets=round(n2o * ets_share, 5))
        r["co2eq_ets"] = r["co2_ets"] if year >= 2025 else round(r["co2_ets"] + 28 * r["ch4_ets"] + 265 * r["n2o_ets"], 4)
        r["co2eq_per_nm"] = round(r["co2eq"] * 1000 / dist, 2)
    if year in ship.get("div0_years", []):
        r.update(time=0, co2_per_nm="Division by zero!", fuel_per_nm="Division by zero!")
    return r


def inject_edge_cases(rows_by_year, rng):
    """노트북 규칙을 건드리는 행을 몇 개씩 만든다"""
    for year, rows in rows_by_year.items():
        normal = [r for r in rows if r["type"] in ("Bulk carrier", "Oil tanker", "Container ship")
                  and isinstance(r["co2_per_nm"], float)]
        rng.shuffle(normal)
        it = iter(normal)
        r = next(it); r.update(time=0, co2_per_nm="Division by zero!", fuel_per_nm="Division by zero!")   # ②
        r = next(it); r.update(fuel=0, co2=0)                                                              # ③
        r = next(it); r.update(co2_per_nm=40200235.55)                                                     # ④
        r = next(it); r["time"] = round(r["time"] / 6, 2)                                                  # ⑤ 속력 > 40
        r = next(it); r.update(fuel=20.0, co2=62.28, co2_per_nm=124.56, time=50.0)                        # ⑤-2 (거리 500nm, 10kn)
        r = next(it); r.update(fuel=3000.0, co2=9342.0, co2_per_nm=1557.0, time=6000.0)                   # ⑤-3b (거리 = 해상시간)
        r = next(it); r.update(fuel=5000.0, co2=15570.0, co2_per_nm=1112.14, time=9500.0)                 # ⑤-3 (1년 초과, 1.5kn)
        r = next(it)                                                                                       # 3-4 보정 가능 (2배)
        k = 2 * sum(r["parts"]) / r["co2"]
        r["co2"] = round(2 * sum(r["parts"]), 4)
        r["co2_per_nm"] = round(r["co2_per_nm"] * k, 2)
        r["tw"] = {b: (v * k if v else v) for b, v in r["tw"].items()}
        r = next(it); r["co2"] = round(r["fuel"] * 4.5, 4); r["parts"] = [p * 2 for p in r["parts"]]      # 3-4 보정 불가 (세부도 틀림)
        r["parts"] = [r["co2"] * 0.4] * 4
        r = next(it); r["parts"][0] = r["co2"] * 100                                                       # 8-1 항해 유형 합 오류
        r = next(it)                                                                                       # 3-4 2배 오류지만 두 근거 불일치 (v8 → ⑤-4)
        r["co2"] = round(2.02 * sum(r["parts"]), 4)
        r = next(it); r["co2"] = round(r["fuel"] * 3.25, 4)                                                # ⑤-5 (v8): 경유 계수 + 0.5% 초과
        if year < 2024:                                                                                    # 3-4 계수 반올림 3.21 (v8)
            r = next(it); r["co2"] = round(r["fuel"] * 3.21, 2)
            r["parts"] = [round(r["co2"] * w, 2) for w in (0.4, 0.3, 0.2, 0.1)]
        r = next(it); r["tech"] = "EIV (5857 gCO₂/t·nm)"                                                    # 6-3 극단값
        r = next(it); r["co2"] = round(r["fuel"] * 2.1, 4)                                                 # 대체연료
        if year >= 2024:
            r = next(it); r["co2_ets"] = r["co2"] * 4.2                                                    # 8-3 ETS > 총량
            r = next(it); r["ch4_ets"] = (r["ch4"] or 0) * 3                                               # CH4 ETS > 총량
            r = next(it); r["company"] = "Arab Maritime Petroleum Transport company"                       # 3-2 대소문자
            r = next(it); r["company"] = "Zodiac  Maritime Ltd"                                            # 3-2 이중 공백
            r = next(it); r["company_imo"] = "123456"                                                      # 앞자리 0 빠짐
            r = next(it); r["company_imo"] = "1234567.0"
        ropax = [x for x in rows if x["type"] == "Ro-pax ship" and isinstance(x["co2_per_nm"], float)]
        if len(ropax) >= 2:
            ropax[0]["tw"]["pax"] = ropax[0]["tw"]["pax"] * 2000                                           # 8-2 Ro-pax 1,000배 오류
            ropax[1]["tw"]["pax"] = ropax[1]["tw"]["pax"] / 50                                             # 8-2 적재량 10배 초과


def to_cells(r, year, new_fmt, rng):
    tw = [r["tw"][b] for b, _ in TW]
    if not new_fmt:
        return [r["imo"], r["name"], r["type"], year, r["tech"], "Monrovia", None, r["ice"],
                f"{year + 1}-04-30", f"{year + 2}-06-30", "DNV", "ACC-1", "Norway", *r["mm"], None,
                r["fuel"], r["fuel"] * 0.5, r["co2"], *r["parts"], r["pax_co2"], r["time"],
                r["fuel_per_nm"], r["co2_per_nm"], *tw, r["ice_dist"], None, r["ice_time"]]
    return [r["imo"], r["name"], r["type"], year, r["tech"], "Panama", None, r["ice"], r["company"],
            int(r["company_imo"]) if r["company_imo"].isdigit() else r["company_imo"],
            f"{year + 1}-04-30", f"{year + 2}-06-30", "DNV", "ACC-1", "Norway", *r["mm"], None,
            r["fuel"], r["co2"], r["ch4"], r["n2o"], r["co2eq"], r["co2_ets"], r["ch4_ets"], r["n2o_ets"],
            r["co2eq_ets"], *r["parts"], r["pax_co2"], r["time"], r["ice_dist"], r["ice_time"], r["fuel_per_nm"], r["co2_per_nm"],
            r["co2eq_per_nm"], *tw]


def write_year(raw_dir, year, version, date, rows, rng, break_schema=False, partial_imos=()):
    new_fmt = year >= 2024
    headers = new_headers() if new_fmt else old_headers(year)
    if break_schema:
        headers = [("Time at sea [hours]" if h == "Time spent at sea [hours]" else h) for h in headers]
    wb = Workbook(write_only=True)
    sheets = [f"{year} Full ERs", f"{year} Partial ERs"] if new_fmt else [str(year)]
    for sname in sheets:
        ws = wb.create_sheet(sname)
        ws.append(["Ship"] + [None] * (len(headers) - 1))
        ws.append([None] * len(headers))
        ws.append(headers)
        src = rows if "Partial" not in sname else [r for r in rows if r["imo"] in partial_imos]
        for r in src:
            ws.append(to_cells(r, year, new_fmt, rng))
        if "Partial" in sname:   # Partial에만 있는 선박
            ws.append([imo_with_check("960000"), "PARTIAL ONLY"] + [None] * (len(headers) - 2))
    path = raw_dir / f"{year}-v{version}-{date}-EU MRV Publication of information.xlsx"
    wb.save(path)
    return path


def generate_year(year, ships, rng):
    rows = [row_for(s, year, rng, year >= 2024) for s in ships
            if s["first"] <= year <= (s["last"] if s["last"] < 2025 else 2100) and (rng.random() < 0.92 or s["name"].startswith(("SPECIAL", "CRUISE", "FERRY", "OLD", "TUG", "COMBO", "GC", "SMALL", "OFFSHORE")))]
    return rows


def spec_for(ship, rng):
    """선종별로 그럴듯한 제원. CII 계산의 구간 경계(279,000 DWT, 65,000/100,000 DWT, 57,700/30,000 GT, 20,000 DWT)를 넘나들게"""
    t = ship["type"]
    if t.startswith("Passenger"):
        gt = rng.uniform(50000, 150000); dwt = gt * 0.1
    elif t == "Ro-pax ship":
        gt, dwt = (6000.0, 500.0) if ship["name"] == "HSC JET" else (rng.uniform(10000, 60000), 0)
        dwt = dwt or gt * 0.18
    elif t in ("Vehicle carrier",):
        gt = rng.choice([rng.uniform(20000, 29000), rng.uniform(30000, 57000), rng.uniform(58000, 75000)]); dwt = gt * 0.35
    elif t in ("Ro-ro ship", "Container/ro-ro cargo ship"):
        gt = rng.uniform(10000, 60000); dwt = gt * 0.5
    else:
        dwt = {"Bulk carrier": rng.choice([rng.uniform(30000, 200000), 300000.0]),
               "Oil tanker": rng.uniform(10000, 300000), "Chemical tanker": rng.uniform(5000, 50000),
               "Container ship": rng.uniform(10000, 200000), "General cargo ship": rng.uniform(3000, 25000),
               "LNG carrier": rng.choice([rng.uniform(8000, 60000), rng.uniform(70000, 95000), rng.uniform(100000, 120000)]),
               "Gas carrier": rng.uniform(5000, 85000), "Refrigerated cargo carrier": rng.uniform(5000, 15000),
               "Combination carrier": rng.uniform(50000, 100000)}.get(t, rng.uniform(5000, 50000))
        gt = dwt * (1.2 if t == "LNG carrier" else 0.7 if t == "General cargo ship" else 0.6)
    built = rng.randint(1995, min(ship["first"], 2022))
    length = round(rng.uniform(100, 350), 2)
    return {"IMO": ship["imo"], "Built": float(built), "Age": float(2026 - built), "Gross Tonnage": float(round(gt)),
            "Summer DWT": float(round(dwt)), "Length": length, "Beam": round(length / rng.uniform(4.5, 7.5), 2)}


def write_specs(root, ships, rng):
    """노트북 9-1이 읽는 제원 파일 (기존 수집 파일처럼 숫자 형식). 일부러: 폭 오기재, 길이·폭 결측, 제원 없는 선박, MRV에 없는 선박"""
    import pandas as pd

    rows = [spec_for(s, rng) for s in ships if not s["name"].startswith("SHIP 00")]   # SHIP 000~009는 제원 없음
    rows[3]["Beam"] = round(rows[3]["Length"] / 20, 2)                                   # 9-3 길이/폭 > 12
    rows[4]["Length"], rows[4]["Beam"] = float("nan"), float("nan")                       # 길이·폭 결측
    rows += [{"IMO": imo_with_check(str(990000 + k)), "Built": 2010.0, "Age": 16.0, "Gross Tonnage": 30000.0,
              "Summer DWT": 50000.0, "Length": 190.0, "Beam": 32.0} for k in range(3)]   # 제원에만 있는 선박
    d = Path(root) / "data" / "raw" / "vesselfinder"
    d.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).drop_duplicates("IMO").to_csv(d / "ship_data_detailed.csv", index=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--add-version", type=int)
    ap.add_argument("--add-year", type=int)
    ap.add_argument("--break-schema", action="store_true")
    a = ap.parse_args()
    root = Path(a.root)
    raw = root / "data" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    rng = random.Random(7)
    ships = build_fleet(rng)
    rows_by_year = {y: generate_year(y, ships, random.Random(100 + y)) for y in range(2018, 2027)}
    inject_edge_cases(rows_by_year, random.Random(5))
    for rows in rows_by_year.values():
        for r in rows:
            if r["name"] == "HSC JET" and isinstance(r["co2_per_nm"], float):
                r["time"] = round(r["co2"] * 1000 / r["co2_per_nm"] / 30, 2)
    for r in rows_by_year[2018]:                                                   # KISHORE 2018: 비율 3.20753
        if r["imo"] == "9481685":
            r.update(fuel=1516.0, co2=round(1516.0 * 3.20753, 4), time=1000.0)
            r["co2_per_nm"] = round(r["co2"] * 1000 / 10000, 2)
            r["parts"] = [round(r["co2"] * w, 2) for w in (0.4, 0.3, 0.2, 0.1)]
    partial = {y: {r["imo"] for r in rows_by_year[y][:15]} for y in rows_by_year}

    if a.add_version:
        y = a.add_version
        rows = rows_by_year[y]
        rows[20]["co2"] = round(rows[20]["co2"] * 1.1, 4)       # 정정 보고
        rows[21]["fuel"] = round(rows[21]["fuel"] * 0.95, 2)
        del rows[22]                                            # 공개 철회
        extra = row_for({"imo": imo_with_check("970001"), "name": "LATE REPORT", "type": "Bulk carrier",
                         "eedi": True}, y, random.Random(1), y >= 2024)
        rows.append(extra)                                      # 늦게 제출된 보고
        v, d = VERSIONS.get(y, (1, "01072026"))
        print(write_year(raw, y, v + 1, "20102026", rows, rng, partial_imos=partial[y]))
        return
    if a.add_year:
        y = a.add_year
        print(write_year(raw, y, 1, "30062027", rows_by_year[y], rng, a.break_schema, partial[y]))
        return

    write_specs(root, ships, random.Random(11))
    lines = ["# 연도별 사용 파일 (노트북 1-1에서 대조)", "files:"]
    for y in range(2018, 2026):
        v, d = VERSIONS[y]
        p = write_year(raw, y, v, d, rows_by_year[y], rng, partial_imos=partial[y])
        lines += [f"  {y}:", f'    file: "{p.name}"']
    (root / "config").mkdir(exist_ok=True)
    (root / "config" / "data_sources.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("합성 원본 생성:", raw)


if __name__ == "__main__":
    sys.exit(main())
