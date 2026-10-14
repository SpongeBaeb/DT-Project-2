"""사용자 입력 배(API)의 CII 열: 팀 파이프라인 10단계(vendor/mrv_pipeline/pipeline/rules_mrv.py cii_rating)와 같은 식.

결과 표의 배는 팀 파이프라인이 CII 선종·용량·2026년 기준 비율을 채운다. API 입력에는 이 열이 없어서
크기 4분위·1~3년 예측(cii_ratio_2026basis 사용)이 결과 표와 달라지므로, 같은 규칙으로 채운다 (웹 통합 때 추가).
팀 파이프라인 패키지 이름(pipeline)이 이 프레임워크와 겹쳐 import 하지 않고 식만 옮겼다. 규칙이 바뀌면 함께 고친다.
다르게 둔 점: 고속 로팩스(HSC) 판별은 여러 해 평균 속력이 필요해 하지 않는다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# 표준 선종 → CII 선종 (팀 CII_TYPE 을 표준 선종 이름으로 옮긴 것)
CII_TYPE = {
    "bulk": "Bulk carrier", "gas_carrier": "Gas carrier", "lng_carrier": "LNG carrier", "tanker": "Tanker", "chemical_tanker": "Tanker",
    "container": "Container ship", "general_cargo": "General cargo ship", "reefer": "Refrigerated cargo carrier",
    "vehicle_carrier": "Ro-ro cargo ship (vehicle carrier)", "ro_ro": "Ro-ro cargo ship", "container_ro_ro": "Ro-ro cargo ship",
    "ro_pax": "Ro-ro passenger ship", "cruise": "Cruise passenger ship",
}
GT_TYPES = {"Ro-ro cargo ship (vehicle carrier)", "Ro-ro cargo ship", "Ro-ro passenger ship", "Cruise passenger ship"}
ICE_EQUIV = {"IC": "IC", "IB": "IB", "IA": "IA", "IA Super": "IAS",
             "PC7": "IA", "PC6": "IAS", "PC5": "IAS", "PC4": "IAS", "PC3": "IAS", "PC2": "IAS", "PC1": "IAS"}
FI = {"IC": (1.0041, 58.5), "IB": (1.0067, 62.7), "IA": (1.0099, 95.1), "IAS": (1.0151, 228.7)}
Z_2026 = 11
GRADES = "ABCDE"


def cii_params(t, dwt, gt):
    """(달성 CII 용량, 기준선 용량, a, c, (exp d1..d4)) — 팀 rules_mrv.cii_params 그대로"""
    if t == "Bulk carrier":
        return dwt, min(dwt, 279000), 4745, 0.622, (0.86, 0.94, 1.06, 1.18)
    if t == "Gas carrier":
        return (dwt, dwt, 14405e7, 2.071, (0.81, 0.91, 1.12, 1.44)) if dwt >= 65000 else (dwt, dwt, 8104, 0.639, (0.85, 0.95, 1.06, 1.25))
    if t == "Tanker":
        return dwt, dwt, 5247, 0.610, (0.82, 0.93, 1.08, 1.28)
    if t == "Container ship":
        return dwt, dwt, 1984, 0.489, (0.83, 0.94, 1.07, 1.19)
    if t == "General cargo ship":
        return (dwt, dwt, 31948, 0.792, (0.83, 0.94, 1.06, 1.19)) if dwt >= 20000 else (dwt, dwt, 588, 0.3885, (0.83, 0.94, 1.06, 1.19))
    if t == "Refrigerated cargo carrier":
        return dwt, dwt, 4600, 0.557, (0.78, 0.91, 1.07, 1.20)
    if t == "LNG carrier":
        if dwt >= 100000:
            return dwt, dwt, 9.827, 0.000, (0.89, 0.98, 1.06, 1.13)
        if dwt >= 65000:
            return dwt, dwt, 14479e10, 2.673, (0.78, 0.92, 1.10, 1.37)
        return dwt, 65000, 14779e10, 2.673, (0.78, 0.92, 1.10, 1.37)
    if t == "Ro-ro cargo ship (vehicle carrier)":
        if gt >= 57700:
            return gt, 57700, 3627, 0.590, (0.86, 0.94, 1.06, 1.16)
        return (gt, gt, 3627, 0.590, (0.86, 0.94, 1.06, 1.16)) if gt >= 30000 else (gt, gt, 330, 0.329, (0.86, 0.94, 1.06, 1.16))
    if t == "Ro-ro cargo ship":
        return gt, gt, 1967, 0.485, (0.76, 0.89, 1.08, 1.27)
    if t == "Ro-ro passenger ship":
        return gt, gt, 2023, 0.460, (0.76, 0.92, 1.14, 1.30)
    if t == "Cruise passenger ship":
        return gt, gt, 930, 0.383, (0.87, 0.95, 1.06, 1.16)
    raise ValueError(t)


def fill_cii(df: pd.DataFrame) -> pd.DataFrame:
    """cii_ship_type, cii_capacity, cii_ratio_2026basis, cii_rating_2026basis 를 채운다 (용량 정보가 없으면 빈칸)."""
    out = df.copy()
    for c in ("cii_ship_type", "cii_rating_2026basis"):
        out[c] = pd.Series(None, index=out.index, dtype=object)
    for c in ("cii_capacity", "cii_ratio_2026basis"):
        out[c] = np.nan
    for i, r in out.iterrows():
        t = CII_TYPE.get(r["ship_type"])
        dwt, gt = r.get("dwt"), r.get("gt")
        if t is None:
            continue
        gt_ok = pd.notna(gt) and float(gt) >= 5000
        need_gt = t in GT_TYPES
        if (need_gt and not gt_ok) or (not need_gt and not (pd.notna(dwt) and dwt > 0)) or (pd.notna(gt) and float(gt) < 5000):
            out.at[i, "cii_ship_type"] = t
            continue
        cap, cap_ref, a, c, expd = cii_params(t, float(dwt) if pd.notna(dwt) else 0.0, float(gt) if pd.notna(gt) else 0.0)
        ref = a * cap_ref ** (-c)
        eq = ICE_EQUIV.get(r.get("ice_class") or "")
        fi = FI[eq][0] + FI[eq][1] / dwt if eq and not need_gt else 1.0
        ice_factor = fi * (1.05 if eq in ("IA", "IAS") else 1.0)
        attained = r["co2_t"] * 1e6 / (cap * r["distance_nm"]) / ice_factor
        ratio = attained / (ref * (1 - Z_2026 / 100))
        out.at[i, "cii_ship_type"] = t
        out.at[i, "cii_capacity"] = cap
        out.at[i, "cii_ratio_2026basis"] = ratio
        out.at[i, "cii_rating_2026basis"] = GRADES[int(np.searchsorted(np.array(expd), ratio, side="right"))]
    return out
