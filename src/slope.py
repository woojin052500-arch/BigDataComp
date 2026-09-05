"""
경사 보정 보행속도와 도달시간

Tobler hiking function은 연령별 모델이 아니다. Imhof가 정리한 등산 자료에서 나온
일반 보행속도와 경사의 관계식이고, 나이를 변수로 갖고 있지 않다.
그래서 경사에 따라 속도가 떨어지는 '모양'만 Tobler를 쓰고,
평지 기준속도 ALPHA만 연령에 맞게 낮춘다.

결과는 '70대의 실제 도달시간'이 아니라 '70대 평지 보행속도를 기준으로 정규화한
상대 도달시간'이다. 개인차와 건강 상태를 반영하지 않은 값이므로 절대 시간을
주장할 근거가 없다. 이 분석에 필요한 것은 구간 사이의 상대적 차이지 절대값이 아니다.
"""
from __future__ import annotations

import numpy as np

from config import ALPHA_KMH, TOBLER_K, TOBLER_OFFSET


def walking_speed_kmh(slope, alpha: float = ALPHA_KMH) -> np.ndarray:
    """경사에 따른 보행속도(km/h).

    W = alpha * exp(-3.5 * |S + 0.05|)
    S는 rise/run (탄젠트). 각도가 아니다.
    S = -0.05 (완만한 내리막)에서 최대가 되고 양쪽으로 지수적으로 떨어진다.
    """
    s = np.asarray(slope, dtype=float)
    return alpha * np.exp(-TOBLER_K * np.abs(s + TOBLER_OFFSET))


def travel_minutes(length_m, slope, alpha: float = ALPHA_KMH) -> np.ndarray:
    """구간 통과시간(분). length_m은 미터, slope는 rise/run."""
    length_m = np.asarray(length_m, dtype=float)
    v = walking_speed_kmh(slope, alpha)
    v = np.maximum(v, 1e-6)
    return (length_m / 1000.0) / v * 60.0


def slope_from_elevation(z_start, z_end, length_m) -> np.ndarray:
    """시점·종점 표고차를 구간 길이로 나눠 평균 경사를 낸다.

    주의: DEM의 격자 해상도로는 계단 한 단이 잡히지 않는다. 잡히는 것은 구간의
    평균 경사이고, 계단이 있는 구간과 그냥 가파른 비탈은 DEM 위에서 거의 같아 보인다.
    계단은 별도 자료(OSM highway=steps)로 분리해서 다룬다.
    """
    dz = np.asarray(z_end, float) - np.asarray(z_start, float)
    L = np.maximum(np.asarray(length_m, float), 1e-6)
    return dz / L


def apply_step_penalty(minutes, has_steps, factor: float = 1.0) -> np.ndarray:
    """계단 보정.

    계단을 단순 페널티로 처리하는 게 맞는지는 확실하지 않다. 선행 연구는 도시의
    계단이 가파른 구간에서 오히려 보행속도를 높인다고 보고했다 — 계단이 없으면
    크게 우회해야 하기 때문이다. 그래서 factor의 부호를 바꿔가며 결과가 어떻게
    달라지는지 확인하는 쪽으로 둔다.

    factor > 1 : 계단을 불리하게 (감속)
    factor = 1 : 계단 무시
    factor < 1 : 계단을 유리하게 (우회 회피)
    """
    m = np.asarray(minutes, float)
    has = np.asarray(has_steps).astype(bool)
    out = m.copy()
    out[has] = out[has] * factor
    return out


def summarize_speed_curve(slopes=None) -> "list[tuple[float, float]]":
    """보고서·발표용 참조표. 경사별 보행속도를 뽑아둔다."""
    if slopes is None:
        slopes = [-0.20, -0.15, -0.10, -0.05, 0.0, 0.05, 0.10, 0.15, 0.20, 0.30]
    return [(s, round(float(walking_speed_kmh(s)), 2)) for s in slopes]


if __name__ == "__main__":
    print(f"평지 기준속도 ALPHA = {ALPHA_KMH} km/h (Bohannon 1997, 70대 여성 기준)")
    print(f"{'경사(rise/run)':>16} {'속도(km/h)':>12} {'100m 통과(분)':>14}")
    for s, v in summarize_speed_curve():
        t = travel_minutes(100, s)
        print(f"{s:>16.2f} {v:>12.2f} {float(t):>14.2f}")
