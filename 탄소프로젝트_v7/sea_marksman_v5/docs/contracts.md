# 형식 약속서 (자동 생성: python tasks.py schema — 직접 고치지 말 것)

원본: `contracts/tables.py`, `contracts/api.py`. 바꾸면 버전을 올리고 받는 사람에게 알린다.

## ship_year (형식 1.4)

MRV 연도별 보고 + 선박 제원을 IMO로 이은 배·연도 표. 파생 변수는 shared/preprocess.derive() 가 만든다.

키: `imo, year`

| 열 | 종류 | 단위 | 빈칸 | 범위 | 뜻 |
|---|---|---|---|---|---|
| `imo` | int |  | 금지 | 1000000 ~ 9999999 | IMO 번호 |
| `year` | int |  | 금지 | 2018 ~ 2100 | 보고 연도 |
| `name` | str |  | 허용 |  | 그해 보고 선박명 |
| `former_names` | str |  | 허용 |  | 이전 이름들, ' | ' 로 연결 (검색용) |
| `ship_type` | str |  | 금지 |  | 표준 선종 (config data.ship_types) |
| `company` | str |  | 허용 |  | 관리회사 (2024 보고분부터, 과거 연도는 최근 값 연결) |
| `fuel_t` | float | t | 허용 | 0 ~  | 연간 연료 소비량 |
| `co2_t` | float | t | 금지 | 0 ~  | 연간 CO₂ 총량 |
| `berth_co2_t` | float | t | 금지 | 0 ~  | 정박 중 CO₂ |
| `co2_per_nm_kg` | float | kg/nm | 금지 | 0 ~  | 보고된 거리당 CO₂ |
| `sea_hours` | float | h | 금지 | 0 ~  | EU 관련 해상 시간 |
| `co2_intra_eu_t` | float | t | 허용 |  | EU 역내 항해 CO₂ |
| `co2_from_eu_t` | float | t | 허용 | 0 ~  | EU 항구에서 출항해 EU 밖으로 가는 항해 CO₂ (이상 운항 지표용) |
| `co2_to_eu_t` | float | t | 허용 | 0 ~  | EU 밖에서 EU 항구로 입항하는 항해 CO₂ (이상 운항 지표용) |
| `ets_co2_t` | float | t | 허용 |  | ETS 대상 CO₂ (2024~) |
| `ets_co2eq_t` | float | t | 허용 | 0 ~  | ETS 대상 CO₂eq (CH₄·N₂O 포함, 2026년 비용부터 사용) |
| `cargo_t` | float | t | 허용 |  | 평균 적재량 |
| `dwt` | float | t | 금지 | 0 ~  | 재화중량 |
| `gt` | float |  | 허용 |  | 총톤수 |
| `length_m` | float | m | 허용 |  | 길이 |
| `build_year` | int |  | 금지 | 1950 ~ 2100 | 건조연도 |
| `ice_class` | str |  | 허용 |  | 내빙 등급 (없으면 빈칸) |
| `eedi` | float | gCO₂/t·nm | 허용 |  | 설계 효율 지표 값 (종류는 eedi_kind) |
| `eedi_kind` | str |  | 허용 |  | 설계 효율 지표 종류: EEDI | EEXI | EIV 등 (값이 없으면 빈칸). 값의 수준이 종류마다 달라 모델이 구분해 쓴다 |
| `cii_ship_type` | str |  | 허용 |  | CII 선종 구분 (팀 파이프라인 10단계) |
| `cii_capacity` | float |  | 허용 | 0 ~  | CII 용량: 선종에 따라 재화중량 또는 총톤수 (팀 파이프라인 10단계) |
| `hsc_proxy` | bool |  | 금지 |  | 고속선 추정 (로팩스 등, 팀 파이프라인 10단계) |
| `fuel_group` | str |  | 허용 |  | 연료 그룹: 석유계 | LNG 계열 | LPG 추정 | 기타 대체연료 | 대체연료(구분 불가) (팀 파이프라인 8-4) |
| `mm_a` | bool |  | 금지 |  | 측정 방식 A (MRV 모니터링 방식) |
| `mm_b` | bool |  | 금지 |  | 측정 방식 B |
| `mm_c` | bool |  | 금지 |  | 측정 방식 C |
| `co2_recovered` | bool |  | 금지 |  | 총 CO₂ 보정 이력 (팀 파이프라인 3-4) |
| `co2_parts_bad` | bool |  | 금지 |  | 항해 유형별 CO₂ 합이 총량과 안 맞음 |
| `cii_type_changed` | bool |  | 금지 |  | 전년 대비 CII 선종 구분이 바뀜 |
| `cii_ratio_2026basis` | float |  | 허용 | 0 ~  | 2026년 기준선 대비 달성 CII 비율 (1 = 기준선, 낮을수록 좋음) |
| `cii_rating` | str |  | 허용 |  | 그해 기준 CII 등급 A~E |
| `cii_rating_2026basis` | str |  | 허용 |  | 2026년 기준 CII 등급 A~E |
| `avg_load` | float |  | 허용 | 0 ~  | 평균 적재량 (기준은 avg_load_basis: 톤, 부피, 인원 등) |
| `avg_load_basis` | str |  | 허용 |  | avg_load 의 기준: mass | dwt | volume 등 |
| `avg_load_invalid` | bool |  | 금지 |  | 적재량이 실을 수 있는 양을 넘는 등 유효하지 않음 |
| `distance_nm` | float | nm | 금지 | 0 ~  | 항해 거리 = co2_t×1000 ÷ co2_per_nm_kg (역산) |
| `sea_eff_kg_nm` | float | kg/nm | 금지 | 0 ~  | 해상 효율 = (CO₂−정박 CO₂)×1000 ÷ 거리. 핵심 지표 |
| `avg_speed_kn` | float | kn | 금지 | 0 ~  | 평균 속력 = 거리 ÷ 해상 시간 (대기 포함, 역산) |
| `berth_share` | float |  | 금지 | 0 ~ 1 | 정박 CO₂ ÷ 전체 CO₂ |
| `eu_share` | float |  | 허용 | 0 ~ 1 | EU 역내 CO₂ ÷ 전체 CO₂ |
| `co2_per_fuel` | float | t/t | 허용 |  | 연료 1톤당 CO₂ (연료 추정용) |
| `alt_fuel` | float |  | 금지 | 0 ~  | 대체연료 추정 변수 = max(0, 3.11 − co2_per_fuel) |
| `age` | int | 년 | 금지 | 0 ~  | 선령 = year − build_year |
| `ln_dwt` | float |  | 금지 |  | ln(재화중량) |
| `ln_sea_hours` | float |  | 금지 |  | ln(해상 시간) |
| `has_ice_class` | bool |  | 금지 |  | 내빙 등급 보유 |
| `cii_attained` | float | g/(t·nm) | 허용 |  | CII 근사 = CO₂ ÷ (재화중량 × 거리). 배경 비교용 |
| `source_version` | str |  | 금지 |  | 원본 파일 판 번호 |

## result_table (형식 2.6)

배·연도별 기준·원인·위치·신호·예측. 웹 JSON과 진단 API는 이 표에서 만들어진다.

키: `imo, year`

| 열 | 종류 | 단위 | 빈칸 | 범위 | 뜻 |
|---|---|---|---|---|---|
| `imo` | int |  | 금지 |  | IMO 번호 |
| `year` | int |  | 금지 |  | 보고 연도 |
| `ship_type` | str |  | 금지 |  | 표준 선종 |
| `size_bin` | int |  | 금지 | 1 ~ 4 | 같은 선종·연도 안 재화중량 4분위 (1~4, 학습 때 경계 고정) |
| `sea_eff_actual` | float | kg/nm | 금지 | 0 ~  | 해상 효율 실제 |
| `sea_eff_expected` | float | kg/nm | 금지 | 0 ~  | 같은 조건 예측값 |
| `sea_eff_peer_median` | float | kg/nm | 금지 | 0 ~  | 동급 중간 (선종·연도·4분위) |
| `vs_peer_pct` | float | % | 금지 |  | 동급 중간 대비 (실제/동급−1)×100 |
| `vs_expected_pct` | float | % | 금지 |  | 같은 조건 대비 (실제/예측−1)×100 |
| `contrib_size` | float | log | 금지 |  | 원인 막대: 크기(같은 4분위 안) |
| `contrib_speed_pattern` | float | log | 금지 |  | 원인 막대: 평균 속력(대기 포함) |
| `contrib_sea_time` | float | log | 금지 |  | 원인 막대: 해상 시간 |
| `contrib_eu_exposure` | float | log | 금지 |  | 원인 막대: EU 역내 비중 |
| `contrib_age_design` | float | log | 금지 |  | 원인 막대: 선령·설계 |
| `contrib_fuel` | float | log | 금지 |  | 원인 막대: 대체연료 |
| `contrib_ice` | float | log | 금지 |  | 원인 막대: 내빙 등급 |
| `contrib_other` | float | log | 금지 |  | 원인 막대: 기타 보정 |
| `contrib_unexplained` | float | log | 금지 |  | 원인 막대: 설명되지 않는 부분 |
| `berth_actual_t` | float | t | 금지 | 0 ~  | 정박 CO₂ 실제 |
| `berth_expected_t` | float | t | 금지 | 0 ~  | 같은 조건 정박 CO₂ 예측 |
| `berth_ratio` | float | 배 | 금지 | 0 ~  | 실제 ÷ 예측 |
| `berth_z` | float | σ | 금지 |  | 같은 조건 대비 정박 배출 표준 점수 (선종 안) |
| `berth_ratio_hist_min` | float | 배 | 허용 |  | 이 배의 지난 해들 배수 최소 (지난 해 없으면 빈칸) |
| `berth_ratio_hist_max` | float | 배 | 허용 |  | 이 배의 지난 해들 배수 최대 |
| `berth_hist_z` | float | σ | 허용 |  | 이 배 예년 대비 표준 점수 (지난 해 2개 미만이면 빈칸) |
| `position_z` | float | σ | 허용 |  | 같은 조건 대비 차이를 그해까지 누적·축소한 선종 내 표준 점수 |
| `position_n_years` | int | 년 | 금지 | 1 ~  | 위치 계산에 쓴 연수 |
| `position_class` | str |  | 금지 |  | consistently_high | typical | consistently_low |
| `sig_berth` | bool |  | 금지 |  | 정박 배출이 같은 조건·예년보다 2σ 이상 |
| `sig_short` | bool |  | 금지 |  | EU 해상 시간 500시간 미만 |
| `sig_fuel` | bool |  | 금지 |  | 연료 1톤당 CO₂가 화석연료 범위 밖 |
| `sig_report` | bool |  | 금지 |  | 보고 값이 물리적으로 불가능 |
| `sig_special` | bool |  | 금지 |  | 특수 운항 집단 |
| `sig_any` | bool |  | 금지 |  | 착시 신호 하나 이상 |
| `type_exposure` | int |  | 허용 | 1 ~ 3 | EU 규제 노출도 유형 1~3 (1 역내 운항선, 2 정기 기항선, 3 비정기 기항선) |
| `type_age_design` | int |  | 허용 | 1 ~ 3 | 선령·설계 유형 1~3 (1 고효율형, 2 일반형, 3 고선령형). 설계 효율 값이 없으면 빈칸 |
| `ops_outlier` | bool |  | 금지 |  | 운항 군집 어느 중심에서도 먼 배 |
| `fc_h1_p10` | float | kg/nm | 허용 | 0 ~  | 1년 뒤 해상 효율 p10 |
| `fc_h1_p50` | float | kg/nm | 허용 | 0 ~  | 1년 뒤 해상 효율 p50 |
| `fc_h1_p90` | float | kg/nm | 허용 | 0 ~  | 1년 뒤 해상 효율 p90 |
| `fc_h2_p10` | float | kg/nm | 허용 | 0 ~  | 2년 뒤 해상 효율 p10 |
| `fc_h2_p50` | float | kg/nm | 허용 | 0 ~  | 2년 뒤 해상 효율 p50 |
| `fc_h2_p90` | float | kg/nm | 허용 | 0 ~  | 2년 뒤 해상 효율 p90 |
| `fc_h3_p10` | float | kg/nm | 허용 | 0 ~  | 3년 뒤 해상 효율 p10 |
| `fc_h3_p50` | float | kg/nm | 허용 | 0 ~  | 3년 뒤 해상 효율 p50 |
| `fc_h3_p90` | float | kg/nm | 허용 | 0 ~  | 3년 뒤 해상 효율 p90 |
| `fct_h1_p10` | float | kg/nm | 허용 | 0 ~  | 1년 뒤 전체 효율(정박 포함 거리당 CO₂) p10 |
| `fct_h1_p50` | float | kg/nm | 허용 | 0 ~  | 1년 뒤 전체 효율(정박 포함 거리당 CO₂) p50 |
| `fct_h1_p90` | float | kg/nm | 허용 | 0 ~  | 1년 뒤 전체 효율(정박 포함 거리당 CO₂) p90 |
| `fct_h2_p10` | float | kg/nm | 허용 | 0 ~  | 2년 뒤 전체 효율(정박 포함 거리당 CO₂) p10 |
| `fct_h2_p50` | float | kg/nm | 허용 | 0 ~  | 2년 뒤 전체 효율(정박 포함 거리당 CO₂) p50 |
| `fct_h2_p90` | float | kg/nm | 허용 | 0 ~  | 2년 뒤 전체 효율(정박 포함 거리당 CO₂) p90 |
| `fct_h3_p10` | float | kg/nm | 허용 | 0 ~  | 3년 뒤 전체 효율(정박 포함 거리당 CO₂) p10 |
| `fct_h3_p50` | float | kg/nm | 허용 | 0 ~  | 3년 뒤 전체 효율(정박 포함 거리당 CO₂) p50 |
| `fct_h3_p90` | float | kg/nm | 허용 | 0 ~  | 3년 뒤 전체 효율(정박 포함 거리당 CO₂) p90 |
| `p_de_h1` | float |  | 허용 | 0 ~ 1 | 1년 뒤 CII 등급이 D·E 일 확률 |
| `p_de_h2` | float |  | 허용 | 0 ~ 1 | 2년 뒤 CII 등급이 D·E 일 확률 |
| `p_de_h3` | float |  | 허용 | 0 ~ 1 | 3년 뒤 CII 등급이 D·E 일 확률 |
| `p_miss_h1` | float |  | 허용 | 0 ~ 1 | 1년 뒤 CII 감축 요구를 채우지 못할 확률 (해당 해 기준선 하락분보다 덜 줄이거나 늘림) |
| `type_exposure_prob` | float |  | 허용 | 0 ~ 1 | 노출도 유형의 가장 높은 소속 확률 (0.6 미만 = 경계) |
| `type_age_design_prob` | float |  | 허용 | 0 ~ 1 | 선령·설계 유형의 가장 높은 소속 확률 (0.6 미만 = 경계, 유형이 없으면 빈칸) |
| `list_h1` | str |  | 허용 |  | 다음 해 리스트: target(영업 타깃) | watch(관찰) | 빈칸 (팀 04_final 셀 [3] 규칙, 기준 p* 는 학습 때 고정) |
| `persist_prob` | float |  | 허용 | 0 ~ 1 | 이듬해에도 같은 조건 예상보다 10% 넘게 더 쓸 확률 (점검 필요 배용. 순서는 믿을 수 있고 값은 해마다 몇 %p 흔들림) |
| `persist_up` | str |  | 허용 |  | 확률을 가장 높이는 요인 이름 (없으면 빈칸) |
| `persist_down` | str |  | 허용 |  | 확률을 가장 낮추는 요인 이름 (없으면 빈칸) |
| `warnings` | str |  | 금지 |  | 이 행의 경고, ' | ' 로 연결 (없으면 빈 문자열) |

## 원인 막대 요인

| 코드 | 화면 이름 |
|---|---|
| `size` | 크기(같은 4분위 안) |
| `speed_pattern` | 평균 속력(대기 포함) |
| `sea_time` | 해상 시간 |
| `eu_exposure` | EU 역내 비중 |
| `age_design` | 선령·설계 |
| `fuel` | 대체연료 |
| `ice` | 내빙 등급 |
| `other` | 기타 보정 |
| `unexplained` | 설명되지 않는 부분 |

## API

`contracts/generated/openapi.json` 또는 서버 실행 후 http://localhost:8000/docs
