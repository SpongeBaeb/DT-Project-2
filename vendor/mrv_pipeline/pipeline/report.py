"""변경 리포트: 이전 결과 대비 무엇이 바뀌었는지.

- 원본 단위: 바뀐 연도 파일에서 추가·삭제·값이 바뀐 행 (정제 전, read_year 결과끼리 비교)
- 결과 단위: 최종 정제 결과에서 추가·삭제된 (IMO, 연도)와 값이 바뀐 칸
  ※ 선사명 통일, 기술효율·적재량 기준 중앙값처럼 여러 연도를 함께 보는 규칙이 있어서,
    한 연도 파일만 바뀌어도 다른 연도 행의 값이 바뀔 수 있다. 리포트에는 그것까지 나온다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline import config

KEY = ["imo", "year"]


def _changed_mask(a: pd.Series, b: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(a) and pd.api.types.is_numeric_dtype(b) \
            and not pd.api.types.is_bool_dtype(a):
        x, y = a.astype("Float64"), b.astype("Float64")
        both_na = x.isna() & y.isna()
        close = ((x - y).abs() <= config.VALUE_RTOL * np.maximum(x.abs().fillna(0), y.abs().fillna(0))).fillna(False)
        return ~(both_na | close)
    x, y = a.astype("string"), b.astype("string")
    return ~((x.isna() & y.isna()) | (x == y).fillna(False))


def compare_frames(old: pd.DataFrame, new: pd.DataFrame, key=KEY, ignore=()):
    """반환: (추가 행, 삭제 행, 값 변경 long 표, 열별 변경 수)"""
    # 키가 중복된 행(원본의 IMO+연도 중복 등)도 비교되도록 같은 키 안의 순번을 붙임
    old = old.assign(_n=old.groupby(key).cumcount())
    new = new.assign(_n=new.groupby(key).cumcount())
    key = [*key, "_n"]
    o, n = old.set_index(key), new.set_index(key)
    added = n.index.difference(o.index)
    removed = o.index.difference(n.index)
    common = o.index.intersection(n.index)
    cols = [c for c in n.columns if c in o.columns and c not in ignore]
    oc, nc = o.loc[common, cols], n.loc[common, cols]
    changes, per_col = [], {}
    for c in cols:
        m = _changed_mask(oc[c], nc[c])
        if m.any():
            per_col[c] = int(m.sum())
            idx = m[m].index
            changes.append(pd.DataFrame({"column": c, "old": oc.loc[idx, c].astype(str).values,
                                         "new": nc.loc[idx, c].astype(str).values}, index=idx))
    value_changes = (pd.concat(changes).reset_index() if changes
                     else pd.DataFrame(columns=[*key, "column", "old", "new"]))
    show = [c for c in ["name", "ship_type_raw", "co2_t"] if c in n.columns]
    out = [n.loc[added, show].reset_index(), o.loc[removed, show].reset_index(), value_changes]
    out = [d.drop(columns="_n") if "_n" in d and not (d["_n"] > 0).any() else d for d in out]
    return (*out, dict(sorted(per_col.items(), key=lambda kv: -kv[1])))


def year_summary(old: pd.DataFrame | None, new: pd.DataFrame) -> pd.DataFrame:
    g_new = new.groupby("year").agg(rows_new=("imo", "size"), co2_new_Mt=("co2_t", "sum"))
    if old is None:
        return g_new.assign(co2_new_Mt=lambda d: (d["co2_new_Mt"] / 1e6).round(3))
    g_old = old.groupby("year").agg(rows_old=("imo", "size"), co2_old_Mt=("co2_t", "sum"))
    t = g_old.join(g_new, how="outer")
    t["rows_diff"] = t["rows_new"].fillna(0) - t["rows_old"].fillna(0)
    t["rows_pct"] = (t["rows_diff"] / t["rows_old"] * 100).round(2)
    t["co2_pct"] = ((t["co2_new_Mt"] - t["co2_old_Mt"]) / t["co2_old_Mt"] * 100).round(2)
    for c in ["co2_old_Mt", "co2_new_Mt"]:
        t[c] = (t[c] / 1e6).round(3)
    t["확인 필요"] = (t["rows_pct"].abs() > config.ALERT_ROWS_PCT) | (t["co2_pct"].abs() > config.ALERT_CO2_PCT)
    return t


def _md_table(df: pd.DataFrame, index=True) -> str:
    d = df.reset_index() if index else df
    head = "| " + " | ".join(map(str, d.columns)) + " |"
    sep = "|" + "---|" * len(d.columns)
    rows = ["| " + " | ".join("" if pd.isna(v) else str(v) for v in r) + " |" for r in d.itertuples(index=False)]
    return "\n".join([head, sep, *rows])


def write_summary(path, ctx: dict):
    L = [f"# 파이프라인 실행 결과 — {ctx['mode_label']}", "",
         f"- 실행: {ctx['started']} · 소요 {ctx['elapsed']:.1f}초",
         f"- 결과: **{ctx['status']}**", ""]
    if ctx.get("fetch"):
        L += ["## MRV 사이트 확인", ""] + [f"- {line}" for line in ctx["fetch"]] + [""]
    det = ctx.get("detect")
    if det:
        L += ["## 원본 파일 변화", "",
              f"- 새 보고연도: {det['new'] or '없음'} / 새 버전: {det['changed'] or '없음'} / 그대로: {det['unchanged']}"]
        for y, (old, new) in ctx.get("file_changes", {}).items():
            L.append(f"- {y}년: `{old}` → `{new}`")
        L.append("")
    for title, key in [("양식 점검 (연간 모드)", "schema"), ("원본 행 변화 (바뀐 연도, 정제 전)", "raw_diff")]:
        if ctx.get(key):
            L += [f"## {title}", ""] + [f"- {line}" for line in ctx[key]] + [""]
    if ctx.get("year_table") is not None:
        L += ["## 연도별 정제 후 행 수·총 CO2", "", _md_table(ctx["year_table"]), ""]
    if ctx.get("result_diff"):
        rd = ctx["result_diff"]
        L += ["## 정제 결과 변화", "",
              f"- 추가된 (IMO, 연도): {rd['added']}행 / 삭제: {rd['removed']}행 / 값이 바뀐 칸: {rd['cells']}개",
              f"- 값이 바뀐 열 (상위): {rd['top_cols'] or '없음'}",
              "- 상세: `row_changes.csv`, `value_changes.csv`", ""]
    if ctx.get("rule_notes"):
        L += ["## CO2 ÷ 연료 관련 행 (v8 규칙, 새 버전에서 바뀌었는지 확인)", ""] + [f"- {x}" for x in ctx["rule_notes"]] + [""]
    if ctx.get("cleaning_log") is not None:
        L += ["## 정제 단계별 남은 행 (노트북 4-6과 같은 표)", "", _md_table(ctx["cleaning_log"], index=False), ""]
    if ctx.get("crawl"):
        L += ["## VesselFinder 크롤링 (--crawl)", ""] + [f"- {line}" for line in ctx["crawl"]] + [""]
    if ctx.get("enrich"):
        L += ["## 제원 통합·CII 등급 (노트북 9~10단계)", ""] + [f"- {line}" for line in ctx["enrich"]] + [""]
    if ctx.get("warnings"):
        L += ["## 확인할 것", ""] + [f"- {w}" for w in ctx["warnings"]] + [""]
    path.write_text("\n".join(L), encoding="utf-8")
