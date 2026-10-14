"""노트북 코드 셀을 그대로 실행해 '노트북이 만든 결과'를 만든다 (파이프라인과 비교하기 위한 기준).

    python tests/run_notebook_reference.py <노트북.ipynb> <프로젝트 폴더> <저장할 pkl>

- 노트북 코드는 고치지 않고 순서대로 exec 한다. 작업 폴더만 프로젝트 폴더로 바꾼다.
- parquet 엔진(pyarrow)이 없는 환경이면 to_parquet/read_parquet을 pickle로 대신한다.
- 최종 df와 정제 로그(log)를 pkl로 저장한다.
"""
import contextlib
import io
import json
import os
import pickle
import sys
import time
import traceback
from pathlib import Path

import pandas as pd


def _patch_parquet():
    try:
        import pyarrow  # noqa: F401
        return
    except ImportError:
        pass
    pd.DataFrame.to_parquet = lambda self, path, index=False, **k: self.to_pickle(str(path) + ".pkl")
    pd.read_parquet = lambda path, **k: pd.read_pickle(str(path) + ".pkl")


def run(nb_path, project, out_pkl):
    nb = json.loads(Path(nb_path).read_text(encoding="utf-8"))
    _patch_parquet()
    ns = {"__name__": "__notebook__"}
    cwd = os.getcwd()
    os.chdir(project)
    failed = []
    try:
        for i, cell in enumerate(nb["cells"]):
            if cell["cell_type"] != "code":
                continue
            src = "".join(cell["source"])
            t0 = time.time()
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf):
                    exec(compile(src, f"<cell {i}>", "exec"), ns)
            except Exception:
                failed.append((i, src.splitlines()[0], traceback.format_exc(limit=1).strip().splitlines()[-1]))
            print(f"  셀 {i:>2} {src.splitlines()[0][:60]:<60} {time.time() - t0:5.1f}s"
                  + ("  ← 오류" if failed and failed[-1][0] == i else ""))
    finally:
        os.chdir(cwd)
    for i, head, err in failed:
        print(f"[오류] 셀 {i} {head}: {err}")
    with open(out_pkl, "wb") as f:
        pickle.dump({"df": ns["df"], "mg": ns.get("mg"), "log": pd.DataFrame(ns["log"]), "failed": failed}, f)
    print("저장:", out_pkl, ns["df"].shape)
    return failed


if __name__ == "__main__":
    sys.exit(1 if run(*sys.argv[1:4]) else 0)
