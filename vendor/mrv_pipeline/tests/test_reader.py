"""mrv_reader 테스트 — 읽기·기록·대조가 맞게 동작하는지 (합성 데이터, 인터넷 불필요).

    python tests/test_reader.py
"""
import json
import pickle
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import mrv_reader as R  # noqa: E402


def check(name, cond):
    print(("  ✅ " if cond else "  ❌ ") + name)
    return bool(cond)


def main():
    ok = True
    with tempfile.TemporaryDirectory() as t:
        proj = Path(t) / "proj"
        subprocess.run([sys.executable, ROOT / "tests" / "make_synthetic_raw.py", proj], check=True, capture_output=True)
        subprocess.run([sys.executable, "-m", "pipeline.run", "--mode", "version", "--root", proj, "--no-fetch"],
                       cwd=ROOT, check=True, capture_output=True)
        # 이 환경엔 parquet 엔진이 없을 수 있어 같은 내용의 pkl로 시험 (읽는 방식만 다르고 나머지는 동일)
        f = proj / "data" / "processed" / "_state" / "mrv_merged.pkl"
        df, meta = R.load_merged(f, quiet=True)
        ok &= check("읽기: 행·버전·해시 기록", meta["rows"] == len(df) and meta["versions"] and len(meta["data_hash"]) == 64
                    and json.dumps(meta))
        meta_file = Path(t) / "target_meta.json"
        R.save_meta(meta, meta_file, extra={"target": "co2_per_nm"})
        doc = json.loads(meta_file.read_text(encoding="utf-8"))
        ok &= check("저장: 기존 메타에 mrv_source로 함께 저장", doc["target"] == "co2_per_nm" and "mrv_source" in doc)
        ok &= check("그대로면 통과", R.check_same(meta_file) is True)

        with open(f, "wb") as fh:                                   # 같은 내용, 다른 저장 방식(바이트가 다름)
            pickle.dump(df, fh, protocol=4)
        ok &= check("저장 방식만 달라진 같은 내용은 통과 (내용 해시로 판정)", R.check_same(meta) is True)

        d2 = df.copy()
        d2.loc[d2.index[0], "gross_tonnage"] = 12345.0              # 크롤링·규칙 변경처럼 버전은 같고 값만 바뀜
        d2.to_pickle(f)
        try:
            R.check_same(meta_file)
            ok &= check("값이 바뀌면 멈춤", False)
        except R.DataChanged as e:
            ok &= check("값이 바뀌면 멈춤 (원본 버전은 같다고 안내)", "원본 버전은 같음" in str(e))

        d3 = df.copy()
        y = str(d3["year"].max())
        d3.loc[d3["year"] == int(y), "mrv_file_version"] = "v999"     # MRV 새 버전
        d3.to_pickle(f)
        ok &= check("strict=False면 경고만 하고 False", R.check_same(meta, strict=False) is False)
        try:
            R.check_same(meta)
        except R.DataChanged as e:
            ok &= check("원본 버전이 바뀌면 어느 연도가 바뀌었는지 안내", f"'{y}': (" in str(e) and "v999" in str(e))

        try:
            R.load_merged(proj / "data" / "processed" / "mrv_merged.csv")
            ok &= check("csv는 거부", False)
        except ValueError:
            ok &= check("csv를 읽으려 하면 parquet을 쓰라고 안내", True)

    print("mrv_reader:", "✅ 모두 통과" if ok else "❌ 실패 있음")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
