"""
검증 — 상위 K% 포착률, 기준선 비교, 공간 블록 교차검증

128건은 학습 데이터가 아니라 정답지다. 이 모듈은 '매긴 순위가 맞았는가'만 채점한다.

주의할 점 두 가지 (완전히 해결되지 않으며, 알고 쓰는 것과 모르고 쓰는 것의 차이가 크다):

1. 발견된 것과 발생한 것은 다르다.
   탐사를 많이 한 구역에서 더 많이 발견된다. 도로가 실제로 꺼진 사고는 탐사 여부와
   무관하게 기록되지만, GPR로 찾아낸 공동은 탐사한 곳에서만 나온다.
   그래서 도로 함몰 사고를 정답지로 쓰고, GPR 공동 발견은 보조 지표로 따로 본다.

2. 사고 이후 정비됐을 수 있다.
   관로 노후도는 현재 상태인데 사고는 2018년부터 쌓인 것이다. 사고 지점이 그 뒤에
   정비됐다면 지금은 새 관로로 잡힌다. 정비 이력을 구할 수 있으면 붙이고,
   못 구하면 최근 사고만으로 검증해 시차를 줄인다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from config import TOP_K_PERCENTS, RANDOM_BASELINE_ITERS


def capture_rate(scores: pd.Series, hits: pd.Series, k_percent: float) -> dict:
    """상위 k% 구간이 실제 발생 사례를 얼마나 담고 있는지.

    scores : 구간별 우선순위 점수
    hits   : 구간별 실제 발생 건수 (0 이상 정수)
    """
    n = len(scores)
    k = max(1, int(round(n * k_percent / 100)))
    top = scores.nlargest(k).index
    total = float(hits.sum())
    caught = float(hits.loc[top].sum())
    return {
        "상위K%": k_percent,
        "구간수": k,
        "포착건수": caught,
        "전체건수": total,
        "포착률": caught / total if total else np.nan,
        "기대치(무작위)": k / n,
        "리프트": (caught / total) / (k / n) if total and k else np.nan,
    }


def random_baseline(hits: pd.Series, k_percent: float,
                    iters: int = RANDOM_BASELINE_ITERS, seed: int = 0) -> dict:
    """기준선 A — 무작위 선정. 순위를 매긴 것이 안 매긴 것보다 나은가.

    시드를 바꿔 반복하고 평균과 분산을 함께 낸다. 한 번 돌린 값과 비교하면
    운이 좋았는지 나쁜지 구별할 수 없다.
    """
    rng = np.random.default_rng(seed)
    n = len(hits)
    k = max(1, int(round(n * k_percent / 100)))
    total = float(hits.sum())
    vals = np.empty(iters)
    h = hits.to_numpy(dtype=float)
    for i in range(iters):
        pick = rng.choice(n, size=k, replace=False)
        vals[i] = h[pick].sum() / total if total else np.nan
    return {
        "상위K%": k_percent, "구간수": k,
        "포착률_평균": float(np.nanmean(vals)),
        "포착률_표준편차": float(np.nanstd(vals)),
        "포착률_95분위": float(np.nanpercentile(vals, 95)),
    }


def compare_baselines(df: pd.DataFrame, hits: pd.Series,
                      score_cols: dict, k_percents: list | None = None,
                      seed: int = 0) -> pd.DataFrame:
    """기준선 A·B·C와 본 점수를 나란히 놓는다.

    score_cols 예:
      {"본점수(PxV)": "score",
       "B_관로단독":   "pipe_age",
       "C_P만":       "P"}
    A(무작위)는 자동으로 추가된다.
    """
    ks = k_percents or TOP_K_PERCENTS
    rows = []
    for k in ks:
        base = random_baseline(hits, k, seed=seed)
        rows.append({
            "기준": "A_무작위", "상위K%": k, "구간수": base["구간수"],
            "포착률": base["포착률_평균"], "비고":
                f"sd={base['포착률_표준편차']:.3f}, p95={base['포착률_95분위']:.3f}",
        })
        for label, col in score_cols.items():
            r = capture_rate(df[col], hits, k)
            rows.append({
                "기준": label, "상위K%": k, "구간수": r["구간수"],
                "포착률": r["포착률"], "비고": f"리프트={r['리프트']:.2f}",
            })
    return pd.DataFrame(rows)


def spatial_block_cv(df: pd.DataFrame, hits: pd.Series, score_col: str,
                     block_col: str, k_percent: float = 10) -> pd.DataFrame:
    """구·군 단위 공간 블록 교차검증.

    사고가 특정 구에 몰려 있으면 전역 포착률이 부풀려진다. 무작위 분할 대신
    구·군으로 묶어, 한 블록을 빼고 나머지에서 잰 뒤 블록별 편차를 본다.
    """
    rows = []
    for blk, g in df.groupby(block_col):
        if len(g) < 10:
            continue
        h = hits.loc[g.index]
        if h.sum() == 0:
            rows.append({"블록": blk, "구간수": len(g), "발생건수": 0, "포착률": np.nan})
            continue
        r = capture_rate(g[score_col], h, k_percent)
        rows.append({"블록": blk, "구간수": len(g),
                     "발생건수": r["전체건수"], "포착률": r["포착률"],
                     "리프트": r["리프트"]})
    out = pd.DataFrame(rows)
    return out.sort_values("포착률", ascending=False, na_position="last")


def report_sentence(df: pd.DataFrame, hits: pd.Series, score_col: str,
                    k_percent: float = 10, seed: int = 0) -> str:
    """결과를 서술할 때 쓸 문장을 만든다.

    '같은 예산으로 사고를 몇 배 더 잡는다'고 쓰지 않는다. 구간마다 탐사 비용이
    다른데 그 비용을 계산에 넣지 않았기 때문이다. 무작위 대비 포함 정도로만 쓴다.
    """
    r = capture_rate(df[score_col], hits, k_percent)
    a = random_baseline(hits, k_percent, seed=seed)
    return (
        f"이 순위의 상위 {k_percent:.0f}%({r['구간수']}개 구간) 안에 "
        f"지난 7년간 실제 발생한 {int(r['전체건수'])}건 중 {int(r['포착건수'])}건, "
        f"즉 {r['포착률']:.1%}가 포함된다. "
        f"같은 수의 구간을 무작위로 골랐을 때는 평균 {a['포착률_평균']:.1%}"
        f"(표준편차 {a['포착률_표준편차']:.1%}, 상위 5% 시행에서도 "
        f"{a['포착률_95분위']:.1%})가 포함된다."
    )


def check_banned_phrases(text: str) -> list:
    """구간 6 교차검토용. 결과물에 남으면 안 되는 표현을 찾는다."""
    from config import BANNED_PHRASES
    return [p for p in BANNED_PHRASES if p in text]
