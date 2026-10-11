"""가정 계산용 물리 규칙 (6장). 회귀 계수가 아니라 이 규칙으로 '속력을 바꾸면?'을 계산한다.

거리당 연료 ∝ 주기관 비중 × r² + (1 − 주기관 비중) / r      (r = 바뀐 속력 ÷ 지금 속력)
  - 주기관: 출력 ∝ 속력³, 시간 ∝ 1/속력 → 거리당 ∝ 속력²
  - 보조기관·보일러: 시간에 비례 → 거리당 ∝ 1/속력

[담당: 방현수] 선종별 주기관 비중 기본값(config physics.main_engine_share)과 근거 문헌 정리.
"""
from __future__ import annotations


def speed_change_factor(speed_change_pct: float, main_engine_share: float) -> float:
    if not 0 < main_engine_share < 1:
        raise ValueError("주기관 비중은 0과 1 사이")
    r = 1 + speed_change_pct / 100
    if r <= 0:
        raise ValueError("속력 변화가 -100% 이하일 수 없습니다")
    return main_engine_share * r**2 + (1 - main_engine_share) / r


def what_if_speed(sea_eff_kg_nm: float, speed_change_pct: float, main_engine_share: float) -> float:
    return sea_eff_kg_nm * speed_change_factor(speed_change_pct, main_engine_share)
