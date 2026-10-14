# MRV 전처리 자동화 파이프라인

`01_merge_preprocess_v10.ipynb`(v10, 최종)의 규칙 — 1~8단계 정제, 9단계 선박 제원 통합, 10단계 CII 등급, 11단계 통합 저장 — 을 그대로 옮기고, MRV 파일이 업데이트될 때마다 다시 돌릴 수 있게 만든 파이프라인이다.
실행하면 **THETIS-MRV 사이트에서 새 버전을 직접 확인해 내려받고**, (선택) 제원이 없는 선박을 크롤링한 뒤, 정제·제원 통합·CII 등급까지 이어서 한다.
노트북과 결과가 같은지는 합성 데이터로 확인했다(`tests/check_port.py`, 정제 61열·통합 82열 전체 행 일치).

## 0. 변경 이력

| 판 | 바뀐 점 | 기존 사용자가 할 일 |
|---|---|---|
| **2026-10-08** | **연료 그룹 열 `fuel_group` 추가** (8-4, 파이프라인 추가 열 — 노트북에 없음): 석유계 / LNG 계열 / LPG 추정 / 기타 대체연료 / 대체연료(구분 불가). CO2 ÷ 연료 3.05 미만인 해를 2024년분부터 CH4·N2O 몫(≥ 0.05) 또는 LNG선 여부로 LNG 계열로 가르고, CH4가 적은 가스선 중 계수 2.95-3.05는 LPG로 추정 (`rules_mrv.fuel_group`, 36.연료타입분류.md 4장). 비용 계산(FuelEU·연료비)용<br>통합 파일 **85열** (노트북 82열 + 파이프라인 추가 3열). 기존 열의 값은 하나도 바뀌지 않음 (`fuel_group`을 빼면 이전 스냅샷과 같음). 새 스냅샷 해시 **`19f6e319`**<br>리포트의 열 수 문구를 추가 열 목록에서 읽도록 수정, `tests/test_fresh_setup.py`의 열 수 기대값 84 → 85 | 코드만 덮어쓰기 후 `run_version.bat` 한 번 (rules_mrv.py가 바뀐 것을 감지해 전체 규칙을 다시 적용, 10초 안팎). 스냅샷 `3183d290`으로 고정한 노트북(회귀 v1-v4)은 그대로 돌아감 (스냅샷은 최근 10개 보관) |
| **2026-10-07 (2차)** | **seed 제원 자동 반영**: 제원 파일이 이미 있어도 seed에서 '제원 값이 없는 IMO'(파일에 없거나 크롤링 실패로 IMO만 남은 행)의 행을 덧붙임. 제원 값이 있는 기존 행은 그대로 둠 (`enrich.ensure_spec_file`)<br>**되돌리기 안전장치**: 처음 실행처럼 완성된 이전 결과가 없으면 백업을 만들지 않고, `--rollback`은 백업에 `_manifest.json`이 없으면 멈춤 — 이전에는 처음 실행 직후 `--rollback`을 하면 결과 파일이 지워졌음<br>테스트: 합성 데이터 테스트에 실제 seed가 섞이지 않게 막고, 위 두 동작 검사 추가 (전처리 결과는 그대로, 해시 `3183d290`) | 코드만 덮어쓰기. 첫 실행 때 `enrich.py`가 바뀐 것을 감지해 제원 결합만 다시 함 (몇 초, 결과 동일). seed에 있는 제원은 다음 실행부터 자동으로 들어오므로 크롤링을 따로 돌릴 필요 없음 |
| 2026-10-07 | **로그 정리**: `run.py`가 끝날 때 로그 핸들러(`run.log`)를 닫도록 수정 — Windows에서 `tests/test_snapshot.py` 정리 단계의 `PermissionError`, 같은 프로세스에서 다시 부를 때 로그가 중복으로 찍히던 문제 해결 (전처리 결과는 그대로)<br>**seed 제원 갱신**: `pipeline/seed/ship_data_detailed.csv` 22,899척 → **22,905척** (2025 v60에서 새로 들어온 6척을 VesselFinder에서 크롤링해 추가: 9347736, 9622837, 9960033, 9969766, 9977153, 9977177) | 코드만 덮어쓰기 (`data`·`.venv`·`reports`는 지우지 않음). seed는 `data/raw/vesselfinder/ship_data_detailed.csv`가 **없을 때만** 복사되므로, 이미 제원 파일이 있으면 6척은 `run_version_crawl.bat`을 한 번 돌려 크롤링하거나, 기존 파일을 손대지 않았다면 새 seed로 바꿔 넣는다 |
| 2026-10-06 | `mrv_reader.py`(피처·회귀 노트북에서 결과를 읽고 원본 버전·내용 해시를 기록·대조, 4-1)와 최종 파일 스냅샷(`data/processed/snapshots/`) 추가 | 코드만 덮어쓰기 후 `run_version.bat --no-fetch` 한 번 실행 → 첫 스냅샷 생성 |
| 첫 배포 | 노트북 v10 규칙(1-11단계)을 옮긴 파이프라인, MRV 사이트 자동 다운로드, VesselFinder 크롤링(`--crawl`) | - |

**정상 결과 확인** (2026-10-08 기준 원본 2018 v275 · 2019 v228 · 2020 v210 · 2021 v219 · 2022 v241 · 2023 v92 · 2024 v247 · 2025 v60): `reports/pipeline/latest_summary.md`가 "성공", 최종 파일 96,382행 × 85열 · 22,712척, 스냅샷 해시 `19f6e319` (`data/processed/snapshots/mrv_merged_*_19f6e319.parquet`). 2026-10-07 판(84열, `fuel_group` 없음)의 해시는 `3183d290`. 원본에 새 버전이 나오면 행 수와 해시는 달라진다.

## 1. 설치

**새 PC·새 폴더라면 명령 두 번이면 된다.** 압축을 푼 폴더에서:

```bat
setup.bat                 ← 처음 한 번: .venv를 만들고 필요한 패키지 설치
run_version_crawl.bat     ← MRV 다운로드 → 정제 → 제원 크롤링 → 제원 통합·CII → 결과 저장
```

MRV 엑셀은 사이트에서 자동으로 받고, 선박 제원 파일은 파이프라인 안에 들어 있는 파일(`pipeline/seed/ship_data_detailed.csv`, 2026-10-06 수집 22,905척)을 `data/raw/vesselfinder/`에 복사해 쓴다 (이미 제원 파일이 있으면 제원 값이 없는 선박의 행만 seed에서 덧붙임). 그 뒤 새로 생긴 선박만 크롤링한다. 따로 준비할 파일이 없다.

**기존 프로젝트(`ship-carbon-ml/`)에서 쓸 때**는 이 폴더의 내용물을 프로젝트 루트에 복사한다. 이미 있는 `data/raw/`의 엑셀과 `data/raw/vesselfinder/ship_data_detailed.csv`를 그대로 쓰고, 번들 제원 파일로 덮어쓰지 않는다 (제원 값이 없는 선박의 행만 덧붙임).

```
ship-carbon-ml/  (또는 압축을 푼 폴더)
├─ pipeline/            ← 파이프라인 코드 (전처리 규칙은 rules_mrv.py 한 파일)
│   └─ seed/ship_data_detailed.csv   ← 번들 제원 파일 (제원 파일이 없으면 복사, 있으면 빠진 선박만 덧붙임)
├─ tools/  tests/
├─ mrv_reader.py        ← 분석 노트북에서 결과를 읽고 버전·해시를 기록·대조하는 도우미 (4-1)
├─ setup.bat  run_version.bat  run_version_crawl.bat  run_annual.bat  run_status.bat
├─ data/raw/            ← 연도별 MRV xlsx (없으면 자동 다운로드, 노트북과 같은 폴더)
│   └─ vesselfinder/ship_data_detailed.csv   ← 선박 제원 (노트북 9단계 입력, 크롤링 결과가 여기에 쌓임)
├─ config/data_sources.yaml   ← 있으면 버전 기록을 맞춰 줌 (없어도 됨)
└─ notebooks/                 ← 파이프라인은 쓰지 않음 (노트북과 비교할 때만)
```

`pipeline` 폴더의 바로 위 폴더가 프로젝트 폴더로 인식된다. 다른 위치의 데이터를 쓰려면 `--root "경로"`를 붙인다.

## 2. 처음 한 번: 노트북 결과와 비교

노트북과 **같은 원본 파일**로 비교해야 하므로, 처음 실행은 사이트를 확인하지 않는 `--no-fetch`로 한다.

```bat
.venv\Scripts\python -m pipeline.run --mode version --no-fetch
.venv\Scripts\python tools\compare_with_notebook.py data\interim\mrv_2018_2025_clean.parquet data\processed\mrv_clean.parquet
.venv\Scripts\python tools\compare_with_notebook.py data\interim\mrv_2018_2025_merged.parquet data\processed\mrv_merged.parquet
```

첫 줄은 정제 결과(1~8단계), 둘째 줄은 통합 결과(제원·CII 포함)를 비교한다. 노트북도 같은 원본 버전(2025 = v60)과 같은 제원 파일로 돌린 결과여야 한다.

`✅ 일치`가 나오면 그다음부터 `run_version.bat`으로 사이트의 새 버전을 받아 처리한다. 노트북 결과(`data/interim/`)는 건드리지 않는다.

## 3. 평소 사용

| 상황 | 실행 | 하는 일 |
|---|---|---|
| 무엇이 바뀌었는지만 확인 | `run_status.bat` | 사이트의 새 버전과 로컬 파일 상태를 보여 줌 (아무것도 바꾸지 않음) |
| **수시 버전 업데이트** (기존 연도의 새 버전) | `run_version.bat` | 바뀐 연도만 엑셀을 다시 읽고, 규칙은 전체 연도에 다시 적용 |
| **6월 새 보고연도** | `run_annual.bat` | 새 연도 양식 점검 → 통과하면 전체 재처리 |
| 업데이트 + 제원 크롤링 | `run_version_crawl.bat` | 위 버전 모드 + 제원 없는 선박 크롤링(최대 200척) → 같은 실행에서 제원 통합·CII 등급 (5번) |
| 제원 파일만 바뀐 경우 | `run_version.bat` | MRV 변경이 없으면 9~10단계(제원 통합·CII)만 다시 함 |
| 결과가 이상해서 되돌리기 | `python -m pipeline.run --rollback` | 직전 결과로 복원 (완성된 백업이 없으면 멈추고 현재 결과를 그대로 둠 — 더 예전 데이터는 스냅샷 사용) |

**사이트에서 자동으로 받는다.** 버전·연간 모드는 먼저 사이트의 파일 목록을 조회하고(요청 1번), `data/raw/`보다 버전이 높은 연도와 새 연도만 내려받아 원래 파일명(`2025-v60-05102026-...xlsx`)으로 저장한다. 새 버전이 없으면 목록 조회 한 번으로 끝난다. 사이트에 접속할 수 없거나 엑셀이 아닌 응답이 오면, 저장하지 않고 리포트에 경고를 남긴 뒤 `data/raw/`의 파일로 계속 진행한다.

직접 받은 파일을 `data/raw/`에 넣어도 똑같이 처리된다. 사이트를 확인하지 않으려면 `--no-fetch`를 붙인다.

구버전은 실행이 성공한 뒤 `data/raw/archive/`로 옮겨지고, `config/data_sources.yaml`의 파일명도 새 버전으로 바뀐다. 그래서 노트북도 계속 그대로 돌릴 수 있다.

사이트에 새 보고연도가 올라오면 버전 모드도 파일은 받아 두지만, 양식 점검이 필요하므로 처리하지 않고 연간 모드로 실행하라고 안내한다.

**모드를 잘못 고르면 멈춘다.** 버전 모드에서 새 연도가 보이면 연간 모드로, 연간 모드에서 새 연도가 없으면 버전 모드로 실행하라고 안내하고 아무것도 바꾸지 않는다.

**종료 코드**: 0 성공(또는 변경 없음) / 1 오류 / 2 사람 확인 필요. 1·2일 때 출력 파일은 바뀌지 않는다.

## 4. 결과물

| 위치 | 내용 |
|---|---|
| `data/processed/mrv_merged.parquet` `.csv` | **최종 사용 파일.** 노트북 `mrv_2018_2025_merged`와 같은 82열(정제 61 + 제원 7 + CII 14) + 출처 버전 2열(`mrv_file_version`, `mrv_file_date`) |
| `data/processed/mrv_clean.parquet` `.csv` | 노트북 `mrv_2018_2025_clean`과 같은 정제 결과 61열 + 출처 버전 2열 |
| `data/processed/column_dictionary_merged.csv` | 통합 파일 열 사전 (노트북 11-1) |
| `data/processed/cleaning_log.csv`, `cleaning_by_year.csv`, `column_dictionary.csv` | 노트북 8-6·4-6·8-7과 같은 표 |
| `data/processed/missing_spec_imo_list.txt` | 제원을 아직 크롤링하지 않은 IMO (크롤러 입력 형식) |
| `data/processed/snapshots/` | 최종 파일 스냅샷 `mrv_merged_날짜_해시8자리.parquet` — 내용이 바뀔 때만 생기고 최근 10개 보관(`SNAPSHOT_KEEP`), 목록은 `index.csv`. 되돌리기·백업 대상 아님 |
| `data/processed/_previous/` | 직전 결과 1개 (덮어쓰기 전 백업, 처음 실행 때는 만들지 않음) |
| `reports/pipeline/<시각>_<모드>/summary.md` | 실행 리포트: 바뀐 파일, 원본 행 변화, 연도별 행·CO2 변화, 단계별 남은 행, 확인할 것 |
| `reports/pipeline/<시각>_<모드>/row_changes.csv`, `value_changes.csv` | 추가·삭제된 (IMO, 연도)와 값이 바뀐 칸 |
| `reports/pipeline/latest_summary.md` | 가장 최근 리포트 |

결과는 항상 최신으로 **덮어쓴다**. 파일 이름에 연도 범위를 넣지 않아서(`mrv_2018_2025_merged` → `mrv_merged`) 새 연도가 추가돼도 피처 단계 코드의 경로를 바꿀 필요가 없다.

선사명 통일, 기술효율·적재량 기준 중앙값처럼 **여러 연도를 함께 보는 규칙**이 있어서, 한 연도 파일만 바뀌어도 다른 연도 행의 값이 조금 바뀔 수 있다. 변경 리포트에 그것까지 나온다.

## 4-1. 피처·회귀 노트북에서 결과 읽기 (`mrv_reader.py`)

결과 파일은 실행할 때마다 같은 이름으로 덮어써진다. 그래서 분석 노트북은 **읽을 때 어떤 데이터였는지 기록하고, 다음 단계에서 같은지 대조**한다.
판정은 내용 해시(값·열·타입이 하나라도 바뀌면 달라짐)로 하고, 원본 버전(`mrv_file_version`)은 사람이 읽는 용도로 함께 남긴다.
크롤링으로 제원이 채워지거나 규칙이 바뀌면 원본 버전은 그대로여도 내용이 바뀌기 때문이다. csv는 열 타입이 깨지므로 **parquet만 읽는다.**

```python
# 노트북 첫 셀: 파이프라인 폴더를 찾아 경로에 추가 (노트북 위치와 상관없이 위쪽 폴더를 차례로 찾음)
import sys
from pathlib import Path
PIPE = next(c for p in [Path.cwd(), *Path.cwd().parents] for c in (p, p / "mrv_pipeline") if (c / "mrv_reader.py").exists())
sys.path.insert(0, str(PIPE))
from mrv_reader import load_merged, check_same, save_meta, list_snapshots
```

```python
# 1단계 노트북: 읽으면서 기록
df, meta = load_merged()                     # 행·열·원본 버전·내용 해시를 출력하고 meta로 돌려줌
...                                          # 학습 쌍 만들기
save_meta(meta, OUT / "target_meta.json")    # 이미 있는 target_meta.json이면 mrv_source 항목만 추가
```

```python
# 2단계 이후 노트북: 맨 위에서 대조 (다르면 DataChanged로 멈춤)
check_same(OUT / "target_meta.json")
```

**실험 입력을 특정 시점에 고정하기 (스냅샷)**

파이프라인은 최종 파일의 내용이 바뀔 때마다 `data/processed/snapshots/`에 날짜와 내용 해시를 붙인 복사본을 남긴다. 실험을 한 시점의 데이터로 고정하려면 스냅샷을 읽는다.

```python
list_snapshots()                                  # 보관 중인 스냅샷: 파일, 저장 시각, 행 수, 원본 버전
df, meta = load_merged(snapshot="3183d290")       # 해시 앞자리(또는 날짜 "2026-10-06", 파일명 일부)로 지정
```

- 스냅샷으로 읽은 기록은 파이프라인이 몇 번을 다시 돌아도 `check_same`을 통과한다 → v1 결과를 나중에도 그대로 재현
- 최신 파일로 읽어도 `load_merged()`가 "같은 내용의 스냅샷" 이름을 알려 주고 meta에 남긴다. 나중에 데이터가 바뀌어 `check_same`이 멈추면, 그 스냅샷으로 이어 가는 방법을 안내한다
- 최근 10개만 보관하므로, 오래 쓸 실험 입력은 스냅샷 파일을 실험 폴더에 복사해 두고 `load_merged("그 경로")`로 읽는다

- 2단계부터는 가능하면 `mrv_merged`를 다시 읽지 말고 1단계가 저장한 학습 쌍 파일만 읽는다. 대조는 '1단계 산출물이 지금 데이터 기준인지' 확인하는 용도
- 데이터가 바뀌었다고 멈추면: 1단계부터 다시 돌리거나, 의도한 갱신이면 결과 폴더를 새 버전(v2 등)으로 만들어 이전 결과와 비교
- 실험하는 동안에는 작업 스케줄러 자동 실행을 꺼 두는 것이 좋다 (실험 도중 덮어쓰기 방지)
- `mrv_reader.py`는 파이프라인 코드에 의존하지 않아, 이 파일만 다른 프로젝트에 복사해 써도 된다 (`load_merged(경로)`로 파일 위치 지정)

## 5. VesselFinder 크롤링 (`--crawl`)

`run_version_crawl.bat`(또는 `python -m pipeline.run --mode version --crawl`)으로 실행하면, MRV 업데이트를 처리한 뒤 **제원이 없는 선박만 크롤링하고 같은 실행에서 9단계 제원 통합과 10단계 CII 등급까지 한다.** 연간 모드에도 `--crawl`을 붙일 수 있다. 크롤링하지 않으면 새로 들어온 선박은 제원이 비어 CII 등급도 비어 있다(노트북 9-2와 같음).

- **대상**: 최종 패널 선박 중 제원이 없는 IMO. 처음 시도하는 선박 → 최근 보고연도 선박 순
- **양**: 한 번에 최대 200척, 1초 간격(약 4~5분). 남은 선박은 다음 `--crawl` 실행에서 이어서 한다. `--crawl-max 500`처럼 바꿀 수 있고, 기본값은 `pipeline/config.py`의 `CRAWL_MAX_PER_RUN`
- **결과**: 성공한 선박만 `data/raw/vesselfinder/ship_data_detailed.csv`에 추가한다(기존 파일과 같은 열, 값은 숫자). 시도 기록은 같은 폴더의 `_crawl_log.csv`. 노트북 9-4는 같은 IMO가 두 번 있으면 멈추므로, 다시 시도해 성공한 선박의 옛 실패 행은 지워 IMO를 하나로 유지한다
- **실패**: 7일 뒤 다시 시도하고, 3번 실패하면 더 시도하지 않는다(VesselFinder에 없는 선박). 기존 크롤러가 남긴 'IMO만 있는 실패 행'도 다시 시도 대상이 된다
- **차단**: VesselFinder가 403·429로 막으면 그 자리에서 크롤링만 멈추고, 전처리는 기존 제원으로 계속한다. 리포트에 경고가 남는다
- 크롤링이 실패해도 MRV 전처리 결과에는 영향이 없다

**처음 한 번**: 예전에 크롤링해 둔 `ship_data_detailed.csv`가 있으면 `data/raw/vesselfinder/`에 먼저 복사한다. 없으면 패널의 모든 선박(약 2만 척)이 대상이 되어, 하루 1회 200척씩이면 100일 넘게 걸린다. 이때는 `--crawl-max`를 늘리거나 며칠에 나눠 돌린다.

6월 연간 업데이트 뒤에는 신규 선박이 많으므로, 작업 스케줄러에 `--crawl`을 넣어 매일 조금씩 받게 해 두면 된다. VesselFinder는 이용약관상 자동 수집을 제한하므로, 한 번에 받는 양과 간격을 지금 수준 이상으로 늘리지 않는 것이 좋다.

기존처럼 크롤러(`vessel_scraper_new.py`)를 따로 돌려도 된다. 파이프라인은 매번 `missing_spec_imo_list.txt`(크롤러 입력 형식)를 만들어 두고, `data/raw/vesselfinder/`의 결과를 읽는다.

## 6. 노트북 완성본으로 바꿀 때

전처리 규칙은 `pipeline/rules_mrv.py` 한 파일에 있고, 함수마다 노트북 셀 번호가 붙어 있다.

| 노트북 셀 | rules_mrv.py |
|---|---|
| 2-1 컬럼 매핑 | `COLUMN_MAP`, `OLD_HEADER_ALIASES`, `TEXT_COLS`, `NUM_COLS` |
| 2-2 연도 읽기 / 1-5 Partial | `read_year` / `read_partial_imos` |
| 2-3 통합·매핑 점검 / 3-1 키 점검 | `combine_years` / `check_keys` |
| 3-2 선사명 통일 / 3-4 총 CO2 보정(2배 오류·계수 반올림 3.21) | `unify_company_names` / `fix_total_co2` |
| 4-3, 4-5 행 제거 ①~⑤-6 (⑤-6 예외 목록은 `EXCEPT`) | `apply_row_rules` |
| 5-2, 5-3 범위 한정 ⑥⑦ | `limit_scope` |
| 6-1~6-4 값 정리 | `tidy_values` |
| 8-1~8-3, 8-5 파생 변수 | `derive` |
| 8-7 열 사전 | `COLUMN_DICT` |
| 9-1~9-4 선박 제원 통합 | `merge_specs` |
| 10-1~10-6 CII 등급 (선종 대응, 계수, 내빙 보정, 등급, 선종 변경 표시) | `CII_TYPE`, `cii_params`, `ICE_EQUIV`, `Z`, `cii_rating` |
| 11-1 통합 열 사전 | `NEW_DICT`, `merged_column_dictionary` |

고친 뒤 확인:

```bat
.venv\Scripts\python tests\check_port.py notebooks\01_merge_preprocess_v10.ipynb
```

합성 데이터로 노트북과 파이프라인을 각각 돌려 정제·통합 결과를 비교한다. `✅ 모두 일치`가 나오면 이식이 맞다. 그다음 2번의 실제 데이터 비교를 한 번 더 한다. 매핑(`COLUMN_MAP`)을 바꾸면 캐시는 자동으로 무시되고 엑셀을 다시 읽는다.

## 7. 노트북과 다른 점

- **Partial ERs**: 노트북은 2024·2025년으로 고정 → 신양식 연도 전체로 확장
- **노트북의 assert 3개**(3-4 계수 반올림은 2023년분까지만, ⑤-6 예외 행 존재, 8-1 연료 중복 판정 없음): 노트북이 멈췄을 상황이면 파이프라인도 '확인 필요'(종료 코드 2)로 멈추고 이유를 리포트에 남김. 출력 파일은 바뀌지 않음
- **매핑 점검(2-3)**: 노트북은 출력만 → 예상 밖으로 비어 있는 열이 있으면 멈춤(`--accept-schema`로 넘길 수 있음)
- **추가 열**: `mrv_file_version`, `mrv_file_date` (덮어쓰기라서 각 행의 출처 버전 표시)
- **제원 통합은 노트북 9단계 그대로**: v8까지 쓰던 임시 결합 규칙은 버렸다. `enrich.py`는 제원 파일 위치와 크롤링 목록만 다룬다
- **노트북 9~11단계의 assert**(제원 IMO 중복, 행 순서·MRV 열 보존, 새 원본 선종·내빙 등급, 열 사전)도 같은 방식으로 '확인 필요'(종료 코드 2)로 멈춘다. 새 선종이나 내빙 등급이 나타나면 `CII_TYPE`·`ICE_EQUIV`에 추가하면 된다
- **OpenSanctions는 쓰지 않기로 함**(팀 결정, 2026-10): 처음 구상에는 있었으나 분석에 쓰지 않아 파이프라인에서 뺐다

## 8. 팀에서 정해야 할 것

- **CII 감축률 `Z`는 2026년까지만 있다.** 2027년분 데이터가 들어오면(2028년 6월) 그해 기준 등급이 비어 있게 되고, 연간 모드 리포트가 알려 준다. IMO가 2027년 이후 감축률을 정하면 `rules_mrv.Z`에 추가한다. 2026년 기준 등급(`BASIS_YEAR`)도 예측 대상 연도가 바뀌면 함께 바꾼다.

- **⑤-6 예외 목록(KISHORE 2018)은 특정 행을 직접 적은 규칙이다.** 2018년 파일이 새 버전으로 바뀌어 그 행이 정정·철회되면 파이프라인이 멈추고 알려 준다. 리포트의 'CO2 ÷ 연료 관련 행'에는 ⑤-6 검토 대상(경유 계수 + 반올림 오차를 넘지만 남긴 행, 현재 RUBINO 2020)도 매번 나오므로, 새 행이 생기면 예외 목록에 넣을지 판단한다.

- **규칙 ⑥은 2025년분에만 적용된다.** 2026년분이 들어오면 2026년에 처음 보고된 소형 일반화물선(400~5,000GT)이 걸러지지 않는다. 연간 모드 리포트에 경고가 나온다. v10 9단계의 `gt_below_5000`(제원 총톤수 기준 표시)으로 5,000GT 기준을 직접 적용하는 방법도 있다.
- **`config/data_sources.yaml`에 새 연도 항목은 직접 추가**해야 한다(파이프라인은 기존 파일명만 바꿈, 원본은 `.bak`로 보관).
- 노트북 자체에도 연도가 고정된 곳이 있다(1-1 `YEARS = range(2018, 2026)`, 출력 파일명 `2018_2025`). 2026년분부터 노트북도 같이 돌리려면 그 부분을 고쳐야 한다.

## 9. 사이트 주소

`pipeline/download.py` 맨 위에 있다. 사이트 화면이 내부적으로 쓰는 요청이며 로그인은 필요 없다(2026-10 확인).

- 목록: `https://mrv.emsa.europa.eu/api/public-emission-report/downloadable-files?page=1&limit=50`
- 파일: `https://mrv.emsa.europa.eu/api/public-emission-report/reporting-period-document/binary/{연도}/{버전}`

사이트가 개편돼 주소가 바뀌면 다운로드만 실패하고(경고), 나머지는 로컬 파일로 계속 동작한다. 그때는 개발자 도구(F12 → Network)에서 새 주소를 확인해 이 두 줄을 고치면 된다. `python tests/test_download.py`로 다운로드 단계를, `python tests/test_crawl.py`로 크롤링 단계를, `python tests/test_fresh_setup.py`로 빈 폴더에서 한 번에 돌아가는지를 인터넷 없이 점검할 수 있다.

## 10. 자동 실행 (선택)

Windows 작업 스케줄러에 등록할 때는 `pause`가 없는 명령을 쓴다.

```
schtasks /create /tn "MRV daily update" /sc daily /st 09:00 ^
  /tr "cmd /c cd /d C:\Users\samsung\Desktop\ship-carbon-ml && .venv\Scripts\python -m pipeline.run --mode version --crawl"
```

사이트에 새 버전이 없는 날은 목록 조회 한 번 후 '변경 없음'으로 끝나고 결과도 그대로다. 공개 파일은 하루 한 번 이상 바뀌지 않으므로 하루 1회 이하로 충분하다. 결과는 `reports/pipeline/latest_summary.md`에서 확인한다.
