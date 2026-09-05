"""
점수 산정 — 백분위 정규화, P·V 결합, 민감도

분석 단위에 의존하지 않는다. 구간이든 격자든 '행 하나가 하나의 대상'이면 그대로 쓴다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import rankdata, spearmanr

from config import P_WEIGHTS, V_KEYS, SENSITIVITY_EXPONENTS


def pct(x) -> np.ndarray:
    """백분위 순위로 0~1에 넣는다.

    최소최대 정규화를 쓰지 않는 이유: 이상치 하나가 척도를 지배한다.
    관로 매설연수 하나가 80년이면 나머지가 전부 0 근처로 눌린다.
    원값의 절대 크기가 아니라 부산 안에서의 상대 위치를 쓰는 것이 이 분석의 목적에도 맞는다.

    결측은 순위에서 제외하고 NaN으로 남긴다. 0으로 채우면 '가장 안전함'이 되어버린다.
    """
    x = np.asarray(x, dtype=float)
    out = np.full(x.shape, np.nan)
    m = ~np.isnan(x)
    n = m.sum()
    if n == 0:
        return out
    if n == 1:
        out[m] = 0.5
        return out
    out[m] = (rankdata(x[m]) - 1) / (n - 1)
    return out


def build_P(df: pd.DataFrame, weights: dict | None = None,
            cols: dict | None = None) -> pd.Series:
    """P항(발생 가능성) 산출.

    cols: 논리 변수명 -> 실제 컬럼명 매핑. 데이터 확정 후 넘긴다.
          예) {"pipe_age": "mean_install_year", "rain": "rain_annual", ...}
    """
    weights = weights or P_WEIGHTS
    cols = cols or {k: k for k in weights}

    missing = [k for k in weights if cols.get(k) not in df.columns]
    if missing:
        raise KeyError(f"P항 변수 누락: {missing}")

    acc = np.zeros(len(df))
    wsum = np.zeros(len(df))
    for key, w in weights.items():
        p = pct(df[cols[key]].to_numpy())
        ok = ~np.isnan(p)
        acc[ok] += w * p[ok]
        wsum[ok] += w
    # 일부 변수가 결측인 행은 남은 변수만으로 가중평균한다(가중치 재정규화).
    with np.errstate(invalid="ignore", divide="ignore"):
        raw = np.where(wsum > 0, acc / wsum, np.nan)
    return pd.Series(pct(raw), index=df.index, name="P")  # 곱하기 직전 한 번 더 백분위


def build_V(df: pd.DataFrame, keys: list | None = None,
            cols: dict | None = None, weights: dict | None = None) -> pd.Series:
    """V항(사회적 취약도) 산출. 기본은 동일 가중."""
    keys = keys or V_KEYS
    cols = cols or {k: k for k in keys}
    weights = weights or {k: 1.0 / len(keys) for k in keys}

    acc = np.zeros(len(df))
    wsum = np.zeros(len(df))
    for key in keys:
        col = cols.get(key)
        if col not in df.columns:
            raise KeyError(f"V항 변수 누락: {key} -> {col}")
        p = pct(df[col].to_numpy())
        ok = ~np.isnan(p)
        acc[ok] += weights[key] * p[ok]
        wsum[ok] += weights[key]
    with np.errstate(invalid="ignore", divide="ignore"):
        raw = np.where(wsum > 0, acc / wsum, np.nan)
    return pd.Series(pct(raw), index=df.index, name="V")


def score(P, V, alpha: float = 1.0, beta: float = 1.0) -> pd.Series:
    """우선순위 점수 = P^alpha x V^beta.

    합이 아니라 곱인 이유: 합으로 계산하면 한쪽이 0에 가까워도 다른 쪽이 크면
    점수가 남는다. 관로가 새것이고 굴착 이력도 없어 침하 위험이 사실상 없는 구간이,
    주변에 사람이 많다는 이유만으로 상위에 오를 수 있다. 탐사 순서를 정하는 목록에
    그런 구간이 들어가면 목록 자체를 못 쓴다. 곱은 두 조건이 같이 있어야 커진다.
    """
    P = np.asarray(P, dtype=float)
    V = np.asarray(V, dtype=float)
    return pd.Series(np.power(P, alpha) * np.power(V, beta), name="score")


def weighted_sum_score(P, V, wP: float = 0.5) -> pd.Series:
    """가중합 방식. 곱하기 결과와 순위 상관을 비교하기 위한 대조군."""
    return pd.Series(wP * np.asarray(P, float) + (1 - wP) * np.asarray(V, float),
                     name="score_wsum")


def sensitivity(P, V, exponents: list | None = None, top_n: int = 30) -> pd.DataFrame:
    """alpha, beta를 바꿔가며 상위 top_n 구간이 얼마나 유지되는지 센다."""
    exps = exponents or SENSITIVITY_EXPONENTS
    base = set(score(P, V, 1.0, 1.0).nlargest(top_n).index)
    rows = []
    for a in exps:
        for b in exps:
            s = score(P, V, a, b)
            keep = set(s.nlargest(top_n).index)
            rows.append({
                "alpha": a, "beta": b,
                "유지율": len(base & keep) / top_n,
                "이탈수": top_n - len(base & keep),
            })
    return pd.DataFrame(rows)


def rank_agreement(a, b) -> float:
    """두 점수 체계의 순위 상관(Spearman). 곱 vs 가중합 비교에 쓴다."""
    a = np.asarray(a, float); b = np.asarray(b, float)
    m = ~(np.isnan(a) | np.isnan(b))
    return float(spearmanr(a[m], b[m]).statistic)


def variable_influence(df: pd.DataFrame, cols: dict, drop: list,
                       top_n: int = 100) -> dict:
    """탐색 변수를 뺐을 때 상위 top_n이 얼마나 달라지는지.

    관경·지질처럼 근거가 약한 변수를 존치할지 판단하는 데 쓴다.
    차이가 없으면 최종본에서 뺀다. 판단 근거 없이 변수를 늘리지 않는다.
    """
    full = build_P(df, cols=cols)
    w = {k: v for k, v in P_WEIGHTS.items() if k not in drop}
    total = sum(w.values())
    w = {k: v / total for k, v in w.items()}
    reduced = build_P(df, weights=w, cols={k: cols[k] for k in w})

    a = set(full.nlargest(top_n).index)
    b = set(reduced.nlargest(top_n).index)
    return {
        "뺀변수": drop,
        "상위{}겹침".format(top_n): len(a & b),
        "겹침비율": len(a & b) / top_n,
        "순위상관": rank_agreement(full, reduced),
    }
