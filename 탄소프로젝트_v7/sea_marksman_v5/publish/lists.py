"""다음 해 리스트 산출물 (영업 타깃 · 관찰): 순위를 매겨 표와 요약으로 내보낸다. `python tasks.py list`

판정(list_h1)은 모델의 ListRule Stage 가 결과 표에 이미 넣어 두었다 (한 배의 값과 학습 때 고정한 기준 p* 만으로 정해짐).
순위(list_rank)는 같은 리스트 안 배끼리 비교해야 해서 여기서 매긴다: 다음 해 D·E 확률이 높은 순 (같으면 IMO 순).
출력 (artifacts/<버전>/list/): 리스트_<연도>.csv·.parquet, summary.md
신뢰 등급 표시(선종×기간 검증 등급이 '참고용'인 선종)는 아직 붙이지 않았다 → summary.md 에 명시.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from models.forecast.lists import LISTS

KEEP = ["imo", "name", "company", "cii_rating"]                    # 결과 표에 이미 있는 열(ship_type 등)은 스냅샷에서 다시 가져오지 않는다 (병합 때 이름이 겹침)


def build_list(results: pd.DataFrame, snapshot: pd.DataFrame, year: int | None = None) -> tuple[pd.DataFrame, int]:
    """기준 연도(기본 결과의 마지막 해) 리스트. 반환: (리스트 표, 기준 연도)."""
    if "list_h1" not in results.columns or results["list_h1"].isna().all():
        raise ValueError("결과 표에 list_h1 이 없습니다. 설정에 ListRule 부품(앞에 CII 확률 QuantileForecast)이 필요합니다")
    year = int(year or results["year"].max())
    r = results[(results["year"] == year) & results["list_h1"].isin(LISTS)].sort_values("imo", kind="mergesort")
    s = snapshot[snapshot["year"] == year][[*KEEP, "co2_per_nm_kg"]]
    t = r.merge(s, on="imo", how="left", validate="one_to_one")
    t["list_rank"] = t.groupby("list_h1")["p_de_h1"].rank(ascending=False, method="first").astype(int)
    t["다음해_변화_pct"] = (t["fct_h1_p50"] / t["co2_per_nm_kg"] - 1) * 100
    out = pd.DataFrame({
        "리스트": t["list_h1"].map(LISTS), "순위": t["list_rank"], "IMO": t["imo"], "선박명": t["name"], "선종": t["ship_type"], "회사": t["company"],
        "지금 등급": t["cii_rating"], f"{year + 1}년 D·E 확률": t["p_de_h1"], f"{year + 2}년 D·E 확률": t["p_de_h2"], f"{year + 3}년 D·E 확률": t["p_de_h3"],
        f"{year + 1}년 감축 요구 미달 확률": t["p_miss_h1"], f"{year + 1}년 거리당 CO₂ 변화(대표값, %)": t["다음해_변화_pct"],
        "list_code": t["list_h1"],
    })
    order = {v: i for i, v in enumerate(LISTS.values())}
    out = out.sort_values(["리스트", "순위"], key=lambda c: c.map(order) if c.name == "리스트" else c).reset_index(drop=True)
    return out, year


def md_table(df: pd.DataFrame) -> str:
    lines = ["| " + " | ".join(map(str, df.columns)) + " |", "|" + "---|" * len(df.columns)]
    return "\n".join(lines + ["| " + " | ".join(str(v) for v in r) + " |" for r in df.itertuples(index=False)])


def write_summary(out: Path, table: pd.DataFrame, year: int, detail: dict | None, results: pd.DataFrame) -> None:
    ry = results[results["year"] == year]
    L = [f"# {year + 1}년 리스트 요약 (기준 연도 {year})", "",
         "규칙 (팀 회귀 v4 04_final 셀 [3]와 같음): 영업 타깃 = 다음 해 D·E 확률 ≥ 0.8. 관찰 = 타깃이 아니고, 지금 등급이 A~C 이며 다음 해 감축 요구 미달 확률이 기준 p* 이상.", ""]
    if detail:
        L += [f"- 기준 p* (학습 마지막 연도 {detail['base_year']} 배들의 미달 확률 {detail['watch_quantile'] * 100:.0f}% 분위수): **{detail['p_star']:.3f}**",
              f"- 영업 타깃 기준 D·E 확률: {detail['de_cut']}", f"- 관찰 대상 현재 등급: {', '.join(detail['watch_ratings'])}"]
    cnt = table["리스트"].value_counts()
    L += ["", "## 척수", "", f"- 영업 타깃 {int(cnt.get('영업 타깃', 0)):,}척, 관찰 {int(cnt.get('관찰', 0)):,}척 (기준 연도 보고 선박 {len(ry):,}척 중)", "",
          "### 지금 등급 × 리스트", "",
          md_table(pd.crosstab(table["지금 등급"], table["리스트"]).reindex(columns=[v for v in LISTS.values() if v in table["리스트"].unique()]).reset_index())]
    top = table.groupby(["선종", "리스트"]).size().unstack(fill_value=0)
    L += ["", "### 선종별 척수", "", md_table(top.reset_index())]
    L += ["", "## 알아 둘 점", "",
          "- 신뢰 등급 표시가 아직 없습니다. 팀 v4 는 선종 × 기간별 검증 등급(값·순위)을 두고 순위 등급이 '참고용'인 선종의 리스트 배에 `list_note` 를 붙였지만, 그 검증은 구판 목표(정박 포함 거리당 CO₂) 기준이라 새 모델로 다시 계산해야 합니다.",
          "- '관찰'은 지금 효율이 좋은 배(A~C) 중 다음 해 감축 요구를 못 채울 가능성이 큰 배입니다. 비효율을 뜻하지 않습니다.",
          "- 순위는 같은 리스트 안에서 다음 해 D·E 확률이 높은 순입니다."]
    (out / "summary.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def run(results: pd.DataFrame, snapshot: pd.DataFrame, out_dir: Path, model_meta: dict | None = None) -> pd.DataFrame:
    table, year = build_list(results, snapshot)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    num = table.select_dtypes("number").columns.difference(["순위", "IMO"])
    t = table.copy()
    t[num] = t[num].round(4)
    t.to_csv(out / f"리스트_{year + 1}.csv", index=False, encoding="utf-8-sig")
    t.to_parquet(out / f"리스트_{year + 1}.parquet", index=False)
    detail = next((s["detail"] for s in (model_meta or {}).get("stages", []) if s.get("detail", {}).get("p_star") is not None), None)
    write_summary(out, table, year, detail, results)
    return table
