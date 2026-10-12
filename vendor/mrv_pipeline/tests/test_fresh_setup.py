"""새 폴더에서 한 번에 돌아가는지 테스트 — 인터넷 없이 가짜 MRV 사이트·가짜 VesselFinder로 확인.

빈 폴더(엑셀도, 제원 파일도 없음)에서 run_version_crawl과 같은 명령 하나로
MRV 다운로드 → 번들 제원 파일 배치 → 정제 → 크롤링 → 제원 통합·CII까지 끝나는지 본다.

    python tests/test_fresh_setup.py
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import config, crawl, download, run  # noqa: E402
from tests.test_crawl import FakeVF  # noqa: E402
from tests.test_download import FakeSite  # noqa: E402


def check(name, cond):
    print(("  ✅ " if cond else "  ❌ ") + name)
    return bool(cond)


def main():
    ok = True
    download.MIN_FILE_BYTES = 1000          # 합성 엑셀은 작음 (실제 파일은 수 MB)
    download.time.sleep = crawl.time.sleep = lambda s: None
    with tempfile.TemporaryDirectory() as t:
        side, fresh, seed = Path(t) / "side", Path(t) / "fresh", Path(t) / "seed"
        subprocess.run([sys.executable, ROOT / "tests" / "make_synthetic_raw.py", side], check=True, capture_output=True)
        files, listing = {}, {"results": [], "total": 8}
        for p in sorted((side / "data/raw").glob("*.xlsx")):
            m = re.match(r"(\d{4})-v(\d+)-(\d{8})", p.name)
            files[(int(m[1]), int(m[2]))] = p.read_bytes()
            listing["results"].append({"reportingPeriod": int(m[1]), "version": int(m[2]),
                                       "generationDate": f"{m[3][:2]}-{m[3][2:4]}-{m[3][4:]} 05:00:00", "fileName": p.stem})
        seed.mkdir()
        shutil.copy(side / "data/raw/vesselfinder/ship_data_detailed.csv", seed)      # 번들 제원 파일 역할
        config.SEED_DIR = seed
        download._session = lambda: FakeSite(files, listing=listing)
        crawl._session = lambda: FakeVF()

        # 1) 완전히 빈 폴더에서 명령 하나
        fresh.mkdir()
        code = run.main(["--mode", "version", "--crawl", "--root", str(fresh)])
        spec = fresh / "data/raw/vesselfinder/ship_data_detailed.csv"
        mg = pd.read_csv(fresh / "data/processed/mrv_merged.csv", dtype={"imo": str}, low_memory=False)
        ok &= check("빈 폴더에서 명령 하나로 성공 (종료 코드 0)", code == 0)
        ok &= check("MRV 엑셀 8개를 사이트에서 받음", len(list((fresh / "data/raw").glob("*.xlsx"))) == 8)
        ok &= check("번들 제원 파일을 data/raw/vesselfinder/에 복사", spec.exists())
        ok &= check("제원 없는 선박은 크롤링해서 채움", mg["gross_tonnage"].notna().mean() > 0.97)
        ok &= check("최종 파일까지 생성 (CII 등급 포함)", mg.shape[1] == 85 and mg["cii_rating_2026basis"].notna().any())

        # 2) 이미 제원 파일이 있으면 기존 값은 그대로 두고, 제원 값이 없는 IMO만 번들 파일에서 덧붙임
        vals = ["Built", "Gross Tonnage", "Summer DWT", "Length", "Beam"]
        mine = pd.read_csv(spec, dtype={"IMO": str})
        mine = mine[mine[vals].notna().any(axis=1)].head(50).copy()
        mine.iloc[0, mine.columns.get_loc("Gross Tonnage")] = 123456.0               # 팀원이 고친 값 역할
        mine.to_csv(spec, index=False)
        (fresh / "data/processed/_manifest.json").unlink()                          # 처음부터 다시 처리하게
        run.main(["--mode", "version", "--no-fetch", "--root", str(fresh)])
        after = pd.read_csv(spec, dtype={"IMO": str})
        sd = pd.read_csv(seed / "ship_data_detailed.csv", dtype={"IMO": str})
        seed_ok = set(sd.loc[sd[vals].notna().any(axis=1), "IMO"])
        kept = after.set_index("IMO").loc[mine["IMO"], mine.columns[1:]].reset_index()
        ok &= check("기존 제원 행은 값까지 그대로 (덮어쓰지 않음)", kept.equals(mine.reset_index(drop=True)))
        ok &= check("번들 파일에만 있던 선박은 덧붙음", seed_ok <= set(after.loc[after[vals].notna().any(axis=1), "IMO"]))
        ok &= check("IMO 중복 없음 (노트북 9-4 조건)", not after["IMO"].duplicated().any())
        before = spec.read_bytes()
        run.main(["--mode", "version", "--no-fetch", "--root", str(fresh)])
        ok &= check("다시 실행해도 제원 파일은 그대로 (덧붙일 것이 없으면 손대지 않음)", spec.read_bytes() == before)

        # 3) 처음 실행 직후처럼 완성된 백업이 없으면 --rollback은 멈추고 현재 결과를 그대로 둠
        shutil.rmtree(fresh / "data/processed/_previous", ignore_errors=True)
        code = run.main(["--rollback", "--root", str(fresh)])
        ok &= check("완성된 백업이 없으면 --rollback은 멈춤 (결과 파일 그대로)",
                    code == 1 and (fresh / "data/processed/mrv_merged.csv").exists())

    print("새 폴더 한 번에 실행:", "✅ 모두 통과" if ok else "❌ 실패 있음")
    return 0 if ok else 1


if __name__ == "__main__":
    import logging
    logging.disable(logging.CRITICAL)
    sys.exit(main())
