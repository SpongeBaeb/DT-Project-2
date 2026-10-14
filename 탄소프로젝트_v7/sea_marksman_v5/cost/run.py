"""비용 표 만들기: 결과 표(예측)와 스냅샷(2025년 값) → 표 1·2·3 + 요약. `python tasks.py cost`

입력
  - 스냅샷(SHIP_YEAR): 기준 연도(2025) 행의 연료량·ETS 배출량·연료 그룹·정박 등
  - 결과 표(RESULT_TABLE ≥ 2.1): 전체 효율 예측 fct_h*_p*(정박 포함 거리당 CO₂), 동급 중간 해상 효율
출력 (artifacts/<버전>/cost/): 표1_배별_비용, 표2_변화_분해, 표3_동급_대비 (csv, parquet), summary.md
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from cost import model
from contracts.tables import TOTAL_FORECAST_COLS


def prepare_inputs(snapshot: pd.DataFrame, results: pd.DataFrame, s: dict) -> tuple[pd.DataFrame, dict]:
    """기준 연도 배 한 줄씩 + 연도·분위별 예측 비율. 예측이 빈칸인 배는 비용도 빈칸으로 남는다."""
    missing = [c for c in TOTAL_FORECAST_COLS if c not in results.columns or results[c].isna().all()]
    if missing:
        raise ValueError("결과 표에 전체 효율 예측(fct_h*_p*)이 없습니다. 설정에 QuantileForecast(level: co2_per_nm_kg, prefix: fct) 가 필요합니다")
    base = s["base_year"]
    sn = snapshot[snapshot["year"] == base]
    rs = results[results["year"] == base][["imo", "sea_eff_peer_median", *TOTAL_FORECAST_COLS]]
    d = sn.merge(rs, on="imo", how="inner", validate="one_to_one").reset_index(drop=True)
    d["선박명"] = d["name"]
    d["선종"] = d["ship_type"].map(model.TYPE_KO).fillna(d["ship_type"])
    d["fuel_group"] = d["fuel_group"].fillna("석유계")
    ratios = {}
    for year in s["years"]:
        h = year - base
        for kind, q in model.KINDS.items():
            ratios[(year, kind)] = (d[f"fct_h{h}_p{q}"] / d["co2_per_nm_kg"]).to_numpy(float)
    return d, ratios


def md_table(df: pd.DataFrame, floatfmt: str = "{:,.1f}") -> str:
    f = lambda v: floatfmt.format(v) if isinstance(v, (float, np.floating)) else str(v)   # noqa: E731
    lines = ["| " + " | ".join(map(str, df.columns)) + " |", "|" + "---|" * len(df.columns)]
    return "\n".join(lines + ["| " + " | ".join(f(v) for v in r) + " |" for r in df.itertuples(index=False)])


def write_summary(out: Path, d, info, prices, t1, t2, t3, meta, price_note) -> None:
    L = ["# 비용 계산 요약", "", "프레임워크 `python tasks.py cost` 가 만든 파일입니다. 숫자는 손으로 고치지 않고 설정(config/cost.yaml)을 바꿔 다시 실행합니다.", "",
         "## 확정되지 않은 설정", "", "| 설정 | 상태 | 내용 |", "|---|---|---|"]
    L += [f"| {k} | {st} | {note} |" for k, (st, note) in meta.items() if st != "확정"]
    L += ["", "## 입력", ""] + [f"- {k}: {v:,}" if isinstance(v, int) else f"- {k}: {v}" for k, v in info.items()]
    L += ["- 연료 그룹: " + ", ".join(f"{k} {v:,}척" for k, v in d["fuel_group"].value_counts().items()),
          f"- ETS 대상 배출량이 0인 배: {int((d['ets_co2_t'] <= 0).sum()):,}척 (탄소 비용 0)", "", f"## 가격 ({price_note})", "", md_table(prices.reset_index(), "{:,.1f}")]
    g = t1.groupby(["연도", "시나리오"], sort=False)
    tot = g[["연료비_대표", "탄소비용_대표", "총비용_대표", "총비용_하한", "총비용_상한", "총비용_가정B_대표"]].sum(min_count=1) / 100
    tot.insert(0, "총비용_2025", g["총비용_2025"].sum() / 100)
    L += ["", "## 전체 선박 합계 (억 원, 연료비가 없는 LPG 추정 배는 합계에서 빠짐)", "",
          "하한·상한은 배마다의 80% 범위를 그대로 더한 값이라 전체 합계의 80% 범위가 아닙니다. 참고용입니다.", "", md_table(tot.reset_index())]
    ok = t2.dropna(subset=["총변화_대표"])
    dg = ok.groupby(["연도", "시나리오"], sort=False)[["총변화_대표", "효율몫_대표", "규제몫", "가격몫_연료", "가격몫_배출권"]].sum() / 100
    L += ["", "## 2025년 대비 변화의 분해: 전체 선박 합계 (억 원)", "",
          "'효율몫'은 전체 효율(정박 포함) 예측의 변화에서 나온 몫입니다. 정박 변동도 섞여 있습니다.", "", md_table(dg.reset_index())]
    med = ok.groupby(["연도", "시나리오"], sort=False)[["효율_크기비중_pct", "규제_크기비중_pct", "가격_크기비중_pct"]].median()
    med["방향 혼재 배 비율_pct"] = ok.groupby(["연도", "시나리오"], sort=False)["방향_혼재"].mean() * 100
    L += ["", "## 원인 크기 비중: 배별 값의 중앙값 (%)", "", md_table(med.reset_index())]
    L += ["", "## 점검", "", f"- 분해 검산(몫의 합 − 총 변화)의 최대 절댓값: {ok['검산_합빼기총변화'].abs().max():.2e} 백만 원",
          f"- 총비용이 비어 있는 행: {int(t1['총비용_대표'].isna().sum()):,} (LPG 추정 {int((d['fuel_group'] == 'LPG 추정').sum())}척 × 연도 × 시나리오 + 예측이 없는 배)"]
    x = t3[(t3["연도"] == t3["연도"].min()) & (t3["시나리오"] == "기준")]
    L += [f"- {int(x['연도'].iloc[0])}년 기준 시나리오에서 동급보다 비용이 큰 배: {int((x['동급대비_차이'] > 0).sum()):,}척, 작은 배: {int((x['동급대비_차이'] < 0).sum()):,}척, 비어 있는 배: {int(x['동급대비_차이'].isna().sum()):,}척"]
    (out / "summary.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def run(snapshot: pd.DataFrame, results: pd.DataFrame, out_dir: Path, cfg_path: str = "config/cost.yaml") -> dict[str, pd.DataFrame]:
    s, meta, raw = model.load_settings(cfg_path)
    prices = model.load_prices(raw["prices_file"])
    d, ratios = prepare_inputs(snapshot, results, s)
    t1, t2 = model.build(d, ratios, prices, s)
    base_nm = d["co2_per_nm_kg"] - d["sea_eff_kg_nm"]                                      # 이 배의 정박/nm (kg CO₂/nm)
    peer, note = model.peer_fuel_per_nm(d, d["sea_eff_peer_median"], base_nm)
    t3 = model.build_t3(d, t1, peer, note, s)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    tables = {"표1_배별_비용": t1, "표2_변화_분해": t2, "표3_동급_대비": t3}
    for name, t in tables.items():
        num = t.select_dtypes("number").columns.difference(["연도", "적용률"])
        t = t.copy()
        t[num] = t[num].round(3)
        t.to_csv(out / f"{name}.csv", index=False, encoding="utf-8-sig")
        t.to_parquet(out / f"{name}.parquet", index=False)
    info = {"예측 척수(결과 표 2025년 행)": int((results["year"] == s["base_year"]).sum()), "기준 연도 행과 결합된 척수": len(d),
            "기준 연도 스냅샷 행": int((snapshot["year"] == s["base_year"]).sum())}
    price_note = "config/cost_prices.csv"
    write_summary(out, d, info, prices, t1, t2, t3, meta, price_note)
    (out / "settings.json").write_text(json.dumps({k: {"value": s[k], "status": meta[k][0]} for k in s}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return tables
