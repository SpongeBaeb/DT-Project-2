"""노트북 규칙이 파이프라인에 그대로 옮겨졌는지 한 번에 확인 (합성 데이터 사용, 실제 데이터 불필요).

    python tests/check_port.py notebooks/01_merge_preprocess_v10.ipynb

순서: 합성 원본 생성 → 노트북 실행 → 파이프라인 실행 → 비교
      → 2025년 새 버전 추가 → 파이프라인 버전 모드 → 노트북 재실행 → 다시 비교
노트북을 고쳤거나 rules_mrv.py를 고친 뒤 이 스크립트가 '✅ 일치'를 두 번 내면 이식이 맞는 것이다.
(노트북이 새 연도·새 파일 구조를 쓰도록 바뀌면 tests/make_synthetic_raw.py도 맞춰야 할 수 있다)
"""
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def sh(*args):
    r = subprocess.run([sys.executable, *map(str, args)], cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, r.stdout + r.stderr


def main(nb):
    nb = Path(nb).resolve()
    with tempfile.TemporaryDirectory() as tmp:
        proj = Path(tmp) / "proj"
        (proj / "data" / "interim").mkdir(parents=True)
        results = []
        for label, extra in [("기준 데이터", None), ("2025년 새 버전 반영 후", ["--add-version", "2025"])]:
            code, out = sh(HERE / "make_synthetic_raw.py", proj, *(extra or []))
            assert code == 0, out
            code, out = sh("-m", "pipeline.run", "--mode", "version", "--root", proj, "--no-fetch")   # 합성 데이터라 사이트 확인 안 함
            assert code == 0, out
            code, out = sh(HERE / "run_notebook_reference.py", nb, proj, Path(tmp) / "ref.pkl")
            errs = [line for line in out.splitlines() if line.startswith("[오류]")
                    and "[8-6]" not in line and "[11-1]" not in line]           # 저장 후 파일 크기 출력만 실패 (parquet 대체)
            if errs:
                print("\n".join(errs))
            for key, state in [("df", "mrv_clean"), ("mg", "mrv_merged")]:
                code, out = sh(ROOT / "tools" / "compare_with_notebook.py", Path(tmp) / "ref.pkl",
                               proj / "data" / "processed" / "_state" / f"{state}.pkl", key)
                print(f"── {label} · {'정제(1~8단계)' if key == 'df' else '통합(9~11단계)'}\n{out}")
                results.append(code == 0)
    print("이식 확인:", "✅ 모두 일치" if all(results) else "❌ 차이 있음 — 위 내용을 확인")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
