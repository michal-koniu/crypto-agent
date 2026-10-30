"""Statistics for the improvement loop (FROZEN).

From the course (en/self-improving-agents, tools/rare_event_stats.py, MIT): exact binomial tail, McNemar,
Poisson CUSUM, Page-Hinkley, minimum shadow-mode wins. Added for trading (deviation D3 in docs/SELF_IMPROVEMENT.md):
the deflated Sharpe ratio (Bailey & Lopez de Prado 2014) to discount for the number of variants tried, a
moving-block bootstrap for heavy-tailed, autocorrelated returns, and a paired sign test across independent periods.
"""
from __future__ import annotations

import math
import random
from statistics import NormalDist

import numpy as np

N = NormalDist()
EULER = 0.5772156649


# ------------------------------------------------------------------ from the course (rare_event_stats.py)
def binom_sf(c: int, n: int, p: float) -> float:
    """P(X >= c) for X ~ Binomial(n, p)."""
    if c <= 0:
        return 1.0
    if c > n:
        return 0.0
    return sum(math.comb(n, k) * p**k * (1 - p) ** (n - k) for k in range(c, n + 1))


def mcnemar_p(b: int, c: int) -> float:
    """One-sided exact McNemar: b = only champion right, c = only challenger right."""
    return binom_sf(c, b + c, 0.5) if b + c else 1.0


def shadow_min_wins(n: int, alpha: float = 0.05) -> int | None:
    for c in range(n + 1):
        if binom_sf(c, n, 0.5) <= alpha:
            return c
    return None


def cusum_step(s: float, hits: int, lam0: float, lam1: float) -> float:
    """Poisson CUSUM for a drop in a rate from lam0 to lam1 (course 02 §5)."""
    return max(0.0, s + hits * math.log(lam1 / lam0) - (lam1 - lam0))


class PageHinkley:
    """Page-Hinkley test for a downward shift in a continuous metric (course 02 §5).

    We watch for a *drop*, so we feed it the negated metric: an alarm fires when the cumulative upward deviation
    of (-x) exceeds lam."""

    def __init__(self, delta: float, lam: float):
        self.delta, self.lam = delta, lam
        self.n, self.mean, self.m, self.m_min = 0, 0.0, 0.0, 0.0

    def update(self, x: float) -> bool:
        y = -x
        self.n += 1
        self.mean += (y - self.mean) / self.n
        self.m += y - self.mean - self.delta
        self.m_min = min(self.m_min, self.m)
        return (self.m - self.m_min) > self.lam

    def state(self) -> dict:
        return {"n": self.n, "mean": self.mean, "m": self.m, "m_min": self.m_min}

    @classmethod
    def from_state(cls, delta: float, lam: float, st: dict) -> "PageHinkley":
        ph = cls(delta, lam)
        ph.n, ph.mean, ph.m, ph.m_min = st["n"], st["mean"], st["m"], st["m_min"]
        return ph


# ------------------------------------------------------------------ added for trading
def sign_test(diffs: list[float]) -> dict:
    """Paired sign test over independent periods (cycles or years): how many periods the challenger won."""
    d = [x for x in diffs if abs(x) > 1e-12]
    wins = sum(1 for x in d if x > 0)
    return {"n": len(d), "wins": wins, "p_one_sided": binom_sf(wins, len(d), 0.5) if d else 1.0}


def block_bootstrap_p(diff_series: np.ndarray, block: int = 13, n_boot: int = 2000, seed: int = 7) -> float:
    """P(mean difference <= 0) by moving-block bootstrap (weekly series, ~quarter blocks)."""
    x = np.asarray(diff_series, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) < 2 * block:
        return 1.0
    rng = random.Random(seed)
    starts = range(len(x) - block + 1)
    k = math.ceil(len(x) / block)
    worse = 0
    for _ in range(n_boot):
        sample = np.concatenate([x[s:s + block] for s in (rng.choice(starts) for _ in range(k))])[: len(x)]
        if sample.mean() <= 0:
            worse += 1
    return worse / n_boot


def deflated_sharpe(returns: np.ndarray, n_trials: int, sr_trials_var: float | None = None) -> dict:
    """Deflated Sharpe ratio (Bailey & Lopez de Prado 2014) on per-period excess returns.

    SR0 is the Sharpe a best-of-N search would reach by luck; DSR = P(true SR > SR0)."""
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    t = len(r)
    if t < 10 or r.std() == 0:
        return {"sr": 0.0, "sr0": 0.0, "dsr": 0.0, "t": t}
    sr = r.mean() / r.std(ddof=1)
    skew = float(((r - r.mean()) ** 3).mean() / r.std() ** 3)
    kurt = float(((r - r.mean()) ** 4).mean() / r.std() ** 4)
    var_sr = sr_trials_var if sr_trials_var is not None else (1 + 0.5 * sr**2) / (t - 1)
    n = max(n_trials, 1)
    if n == 1:
        sr0 = 0.0
    else:
        sr0 = math.sqrt(var_sr) * ((1 - EULER) * N.inv_cdf(1 - 1 / n) + EULER * N.inv_cdf(1 - 1 / (n * math.e)))
    denom = math.sqrt(max(1 - skew * sr + (kurt - 1) / 4 * sr**2, 1e-12))
    dsr = N.cdf((sr - sr0) * math.sqrt(t - 1) / denom)
    return {"sr": round(sr, 4), "sr0": round(sr0, 4), "dsr": round(dsr, 4), "t": t}


def min_detectable_years(edge_per_year: float, vol_per_year: float, z: float = 1.64) -> float:
    """Years of track record needed before an annual edge is distinguishable from zero (one-sided, ~95 %).
    Used by the controller's 'plausible gain < minimum detectable effect' maintenance rule (course 04 §5)."""
    if edge_per_year <= 0:
        return math.inf
    return (z * vol_per_year / edge_per_year) ** 2
