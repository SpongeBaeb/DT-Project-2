# 내 부품 끼우는 법

지금 뼈대의 모든 칸에는 **임시 부품**이 꽂혀 있어서 처음부터 끝까지 돈다.
각자 임시 부품을 진짜로 바꾸면 되고, **약속(입력·출력 열)만 지키면 다른 사람 코드는 깨지지 않는다.**

## 공통 순서 (모든 모델 담당)

1. 기존 실험 코드는 `experiments/<이름>/` 에 두고 거기서 자유롭게 실험한다.
2. 채택할 것을 `models/...` 에 `Stage` 클래스로 옮긴다 (`models/base.py` 맨 위 설명 참고).
   - `requires` = 필요한 열, `produces` = 돌려줄 열 (**임시 부품과 똑같이**)
   - `fit(train, ctx)` 에서 배우고, `transform(df)` 에서 같은 index 의 표를 돌려준다
3. `config/default.yaml` 의 `stages` 에서 `use:` 를 내 클래스로 바꾼다.
4. `uv run python tasks.py all` → 테스트 통과 확인. `uv run python tasks.py evaluate` → 합격 기준 확인.

> 비교 실험은 `config/default.yaml` 을 복사해 `config/exp_xxx.yaml` 로 만들고 `--config` 로 돌린다. 기본 설정은 팀이 채택한 것만.

### 꼭 지킬 규칙 5개 (테스트가 잡는다)
1. `transform` 은 행 순서·개수·index 를 유지한다.
2. 한 배의 값은 그 배 행만으로 계산한다 → API(한 척) = 결과 표(전체).
3. 같은 배의 **이전** 연도는 써도 되지만 **미래** 연도는 쓰지 않는다.
4. 연도 효과는 `year` 대신 `year_eff` (학습에 없는 연도 → 마지막 학습 연도).
5. 숫자 기준은 `self.thresholds` / 생성자 인자로 받는다 (코드에 박지 않기).

## 담당별

### 차희성 — 파이프라인·군집
- **실제 MRV**: `config/default.yaml` 에서 `data.source: mrv`. 연도별 파일을 `data/raw/mrv/mrv_<연도>_v<판>.xlsx` 로 두면 `pipeline/run.py: download_mrv()` 가 읽는다. 자동 다운로드는 이 함수에 구현.
- **열 이름**: 새 판에서 바뀌면 `config/column_map.yaml` 에 한 줄 추가 (코드 수정 없음). 엑셀 제목 행은 `read_options` 의 `header_row`.
- **제원**: `pipeline/specs.py: fetch_one()` 만 구현. 캐시·요청 간격·실패 목록은 이미 있다. 약관·robots.txt 먼저 확인.
- **군집**: `models/cluster/stub.py` 의 `TertileTypes` 와 같은 `produces` 로 K-평균·이상 운항 부품을 만든다.
- 확인: `data/snapshots/ship_year.manifest.json` 의 `steps` 에 단계별 행 수·버린 이유가 남는다.

### 배성우 — 같은 조건 기준 모델·정박·위치
- 변수만 늘릴 거면 **설정만** 바꾸면 된다:
  ```yaml
  - use: models.common.linear_baseline:LinearBaseline
    params:
      features: {ln_dwt: size, ln_avg_speed_kn: speed_pattern, ln_sea_hours: sea_time,
                 eu_share: eu_exposure, age: age_design, alt_fuel: fuel, has_ice_class: ice}
  ```
  (표본에서 R² 0.832 → 0.854 확인됨. 원인 막대 합은 자동 보장)
- 경험적 베이즈·군집 오차는 `models/common/_linear.py` 의 `fit_by_type` 을 바꾸거나 새 클래스로.
- 위치(z)의 EU 구간 가중치는 `models/common/position.py`.
- 원인 이름(`size`, `speed_pattern` …)은 `contracts/tables.py: CAUSE_FACTORS`. 새 요인이 필요하면 거기 추가 → 결과 표 형식 2.1.

- **공통잔차 모델(연결됨)**: 기존 `공통잔차/common_residual.py` 는 `experiments/A-0_common_residual/` 에 보관하고, Stage 로 옮긴 것이 `models/common/common_residual.py: CommonResidualBaseline` 이다. `config/exp_common_residual.yaml`(합성 표본) 또는 `config/mrv_pipeline.yaml`(팀 전처리 파이프라인 결과)로 돌려 본다.
  - 실제 데이터(팀 전처리 파이프라인 결과): 이미 만든 `mrv_merged.parquet`(또는 csv)가 있으면 `MRV_MERGED_PATH=<경로> uv run python tasks.py pipeline --config config/mrv_pipeline.yaml`. 없으면 같은 명령이 `vendor/mrv_pipeline` 을 실행해 만든다 (MRV 사이트 다운로드는 설정 `data.team_pipeline.fetch: true` 일 때만). 이어서 `build`/`evaluate` 에 같은 `--config`.
  - 줄여 잡은 평균 위치: `models/common/position.py: EmpiricalBayesPosition`.
  - 신판(형식 1.0) 반영: 내빙 둘, 설계 종류(EEDI/EEXI/없음), 선종 간 기울기 공유(`pooling`, 끄려면 `params: {pooling: false}`), 크기 변수는 `size`(기본 `ln_dwt`, 팀 설정 `ln_cii_capacity`)와 `PeerGroup` 의 `size_col` 을 같이 바꾼다.
  - 막대 오차 `cause_se(df)`, 부호 점검용 계수표 `coefficient_table()` 는 결과 표 약속에 없는 보조 출력이다 (화면에 쓰려면 결과 표 2.1 합의).
  - 속력 막대를 "대기 추정"으로 부를 선종은 `type_info[선종]["speed_is_wait"]` (탄력성 ≤ 0.1).

### 장원우 — 예측·화면
- **예측**: `models/forecast/persistence.py` 가 비교 기준(변화 없음). LightGBM 분위 회귀는 같은 파일 설명대로 새 클래스. `enforce_monotone()` 을 꼭 통과, `deterministic=True`.
  - **예측(구현됨)**: `models/forecast/quantile_stage.py: QuantileForecast` (회귀 v4 이식). 팀 설정 `config/mrv_pipeline.yaml` 은 이 부품을 두 번 쓴다 — `{level: sea_eff_kg_nm, prefix: fc}`(해상 효율, 진단·위치·'앞으로') 와 `{level: co2_per_nm_kg, prefix: fct, cii: true}`(전체 효율, 비용·CII D·E 확률 `p_de_h*`. 등급 경계·감축률은 `models/forecast/cii.py`). 피처는 `features.py`(팀 `features_v1.csv` 와 대조 검증), 분위수·보정 함수는 `quantile.py`. 검증·비교 스크립트는 `experiments/A-1_forecast_features/`. LightGBM 은 학습표의 마지막 자리 반올림에도 예측이 평균 3e-3 쯤 달라지는 잡음이 있어 재현 기준은 '잡음 바닥 이내'다.
- **화면**: `web/src/components/DiagnosisView.tsx` 의 ①~⑥ 칸. 타입은 `web/src/api/types.ts` (자동 생성)만 쓴다. 약속이 바뀌면 `uv run python tasks.py schema` → 타입 오류가 고칠 곳을 알려 준다.

### 박준재 — API
- `api/main.py` 는 `shared/present.py` 와 `ModelBundle.run` 만 부른다. **계산을 API 안에 새로 쓰지 않는다** (결과 일치가 깨짐).
- 파일 업로드(`POST /diagnose/batch`)는 `request_to_frame` 을 여러 척으로 늘리면 된다.
- 확인: `uv run pytest tests/parity`

### 최재희 — 비용
- `web/src/calc.ts` 는 5-5절 식의 초안 (연간 비용, 동급 대비 차이, LMDI 분해, 회수 시점). 검토 후 고친다.
- 사례를 추가하려면 `contracts/golden/cost_cases.json` 에 넣는다 (기대값은 **calc.ts 가 아닌 다른 방법**으로 계산). `cd web && npm test`.

### 방현수 — 도메인 검증
- 합격 기준 값: `config/acceptance.yaml`, 계산: `evaluation/report.py`.
- 물리 규칙 기본값: `config/default.yaml` 의 `physics.main_engine_share` (선종별 근거를 `docs/decisions.md` 에).
- 점검 임계값(500시간, 3.05, 1.2배, 3노트, 2σ): `config/default.yaml` 의 `thresholds`.

## 지금 합격 기준 상태 (합성 표본, 임시 부품)

| 기준 | 상태 | 이유 |
|---|---|---|
| 같은 조건 R² 향상 | ❌ 0.00 | 임시 부품 = 비교 기준(크기만) 이라 차이 0 → 배성우 |
| 위치 유지율 vs 한 해 | ❌ | 단순 축소 평균 → 배성우 |
| 위치 유지율 vs 무작위 | ✅ | |
| 예측 MAE 개선 | ❌ 0.00 | 임시 부품 = 비교 기준(변화 없음) → 장원우 |
| 예측 구간 적중률 | ✅ 0.80 | |
| 유형 ARI | ✅ 1.00 | 3등분은 항상 같음 (K-평균으로 바꾸면 의미 있어짐) → 차희성 |

❌ 는 "틀이 고장났다"가 아니라 **각자 넘어야 할 목표**다. 숫자는 합성 표본 기준이므로 실제 MRV 로 바꾸면 다시 잰다.
