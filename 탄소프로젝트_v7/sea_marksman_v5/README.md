# Sea Marksman

EU MRV 공개 데이터로 배마다 **같은 조건의 보통 배보다 얼마나 더 쓰는지, 왜 그런지, 앞으로 어떻게 될지**를 보여 주는 서비스.
(기획서: `SeaMarksman_기획서.html`)

> ⚠ 지금 `data.source: sample` 은 **합성 표본**입니다. 뼈대가 끝까지 도는지 확인하는 용도이며, 숫자를 분석·발표에 쓰면 안 됩니다.

## 처음 한 번

```bash
uv sync                       # Python 3.13 + 패키지 (uv 설치: https://docs.astral.sh/uv/)
cd web && npm install && cd ..
```

## 매일 쓰는 명령

```bash
uv run python tasks.py all        # 데이터 → 학습 → 산출물 → 약속 문서 → 테스트 (표본 기준 약 15초)
uv run python tasks.py evaluate   # 5-2절 합격 기준 판정표
uv run python tasks.py dev        # API + 웹 함께 켜기 → http://localhost:5173 (끄기: Ctrl+C)
```

## 전체 구조 (기획서 그림 3)

```
pipeline/ ──SHIP_YEAR──▶ models/ (config 의 stages 순서대로) ──RESULT_TABLE──▶ publish/ ──▶ artifacts/<버전>/
   ①~⑤                     PeerGroup → 기준 모델 → 정박 → 위치                        model.joblib ──▶ api/ (POST /diagnose)
                           → 착시 신호 → 유형 → 예측                                  web/*.json  ──▶ web/ (찾기·진단)
                                   ▲                                                                  ▲
                            shared/preprocess.py (학습·API 공용)                     contracts/ → TS 타입 자동 생성
```

| 폴더 | 내용 | 담당 |
|---|---|---|
| `contracts/` | **약속**: 표 2개(`tables.py`), API·정적 JSON(`api.py`), 비용 기준 사례(`golden/`) | 모두 (바꿀 때 합의) |
| `shared/` | 공유 전처리, 점검 규칙, 영수증(해시), 결과→화면 변환 | 배성우·박준재 |
| `pipeline/` | 내려받기 → 열 맞추기 → 제원 → 파생 → 스냅샷 | 차희성 |
| `models/common/` | 동급, 같은 조건 기준 모델·원인 분해, 정박 비교, 위치(z) | 배성우 |
| `models/forecast/` | 1~3년 예측 | 장원우 |
| `models/cluster/`, `models/quality/` | 선박 유형, 착시 신호 | 차희성 |
| `models/physics.py` | 속력 가정 계산 물리 규칙 | 방현수 |
| `evaluation/` | 합격 기준 계산 (배 단위 교차 검증, 시간 분할) | 방현수 |
| `api/` | FastAPI 진단 API | 박준재 |
| `web/` | React 화면, `src/calc.ts` 비용 계산 | 장원우, 최재희 |
| `config/` | 부품 선택, 모든 숫자 기준, 열 대응표, 합격 기준 | 모두 |

**내 부품을 끼우는 법 → [docs/PLUGIN_GUIDE.md](docs/PLUGIN_GUIDE.md)** · 형식 약속서 → [docs/contracts.md](docs/contracts.md) (자동 생성)

## 지켜지고 있는 것 (테스트가 확인)

- API에 데이터 속 배를 넣으면 결과 표·정적 JSON과 같다 (오차 1e-9) — `tests/parity`
- 원인 막대 합 = ln(실제/동급 중간) — 어기면 `run()` 이 바로 오류
- 미래 연도를 지워도 과거 결과가 같다 (미래 정보 누수 없음)
- 한 배의 결과는 다른 배가 있든 없든 같다
- 비용 계산이 독립 계산한 기준 사례와 같고, 비용 변화 분해 합 = 변화 — `web/src/calc.test.ts`
- 모든 산출물에 원본 판 번호·데이터 해시·코드 버전·패키지 버전 (`manifest.json`)
