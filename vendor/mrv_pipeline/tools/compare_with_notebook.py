"""노트북 결과와 파이프라인 결과가 같은지 비교 (규칙을 옮기다 빠진 게 없는지 확인).

    python tools/compare_with_notebook.py data/interim/mrv_2018_2025_clean.parquet data/processed/mrv_clean.parquet
    python tools/compare_with_notebook.py data/interim/mrv_2018_2025_merged.parquet data/processed/mrv_merged.parquet

- 두 파일 모두 .parquet / .csv / .pkl 가능
- 파이프라인이 추가한 열(mrv_file_version, mrv_file_date)은 비교에서 뺀다
- 숫자는 상대 오차 1e-9 안이면 같은 값으로 본다 (csv 저장 시 반올림 차이 대비)
- 두 결과가 같은 원본 파일 버전으로 만들어졌는지 먼저 확인할 것 (source_file 열 비교)
"""
import pickle
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.report import compare_frames  # noqa: E402
from pipeline.rules_mrv import PIPELINE_ADDED_COLS  # noqa: E402


def load(path, key="df"):
    p = Path(path)
    if p.suffix == ".parquet":
        return pd.read_parquet(p)
    if p.suffix == ".pkl":
        obj = pickle.load(open(p, "rb"))
        return obj[key] if isinstance(obj, dict) else obj
    return pd.read_csv(p, dtype={"imo": str, "company_imo": str}, encoding="utf-8-sig", low_memory=False)


def compare(nb_path, pl_path, key="df") -> bool:
    nb, pl = load(nb_path, key), load(pl_path, key)
    pl = pl.drop(columns=[c for c in PIPELINE_ADDED_COLS if c in pl.columns])
    nb["imo"], pl["imo"] = nb["imo"].astype(str), pl["imo"].astype(str)
    ok = True
    print(f"노트북 {nb.shape}  /  파이프라인 {pl.shape}")

    only_nb = [c for c in nb.columns if c not in pl.columns]
    only_pl = [c for c in pl.columns if c not in nb.columns]
    if only_nb or only_pl:
        ok = False
        print("열 차이 — 노트북에만:", only_nb, "/ 파이프라인에만:", only_pl)
    elif list(nb.columns) != list(pl.columns):
        print("열 순서만 다름 (값 비교에는 영향 없음)")

    src_nb = sorted(nb["source_file"].astype(str).unique())
    src_pl = sorted(pl["source_file"].astype(str).unique())
    if src_nb != src_pl:
        print("⚠ 두 결과의 원본 파일이 다름 → 같은 버전으로 다시 만든 뒤 비교할 것")
        print("  노트북:", src_nb, "\n  파이프라인:", src_pl)

    added, removed, vc, per_col = compare_frames(nb, pl, ignore=only_nb + only_pl)
    print(f"행: 파이프라인에만 {len(added)} / 노트북에만 {len(removed)}")
    print(f"값이 다른 칸: {len(vc)}" + (f" — 열별 {per_col}" if per_col else ""))
    if len(added) or len(removed) or len(vc):
        ok = False
        for title, d in [("파이프라인에만 있는 행", added), ("노트북에만 있는 행", removed), ("값이 다른 칸", vc)]:
            if len(d):
                print(f"  [{title} 예시]\n" + d.head(10).to_string(index=False))

    dt = {c: (str(nb[c].dtype), str(pl[c].dtype)) for c in nb.columns if c in pl.columns and str(nb[c].dtype) != str(pl[c].dtype)}
    if dt:
        print("(참고) 타입 표기가 다른 열 — 값이 같으면 문제 없음:", dt)
    print("✅ 일치" if ok else "❌ 차이 있음")
    return ok


if __name__ == "__main__":
    sys.exit(0 if compare(sys.argv[1], sys.argv[2], *(sys.argv[3:4])) else 1)
