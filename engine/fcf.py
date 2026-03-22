"""
engine/fcf.py
Derives historical FCF margins and growth rates, then projects
5 years of Free Cash Flow for DCF discounting.
"""

import logging
import statistics
from db.database import fetch_financials, fetch_assumptions, upsert_assumptions

log = logging.getLogger(__name__)


def _cagr(start: float, end: float, years: int) -> float:
    """Compound annual growth rate. Returns 0 if inputs are invalid."""
    if not start or not end or years <= 0 or start <= 0:
        return 0.0
    return (end / start) ** (1 / years) - 1


def derive_growth_assumptions(ticker: str) -> dict | None:
    """
    From the last N years of financials:
    - Compute historical revenue CAGR
    - Compute average FCF margin (FCF / Revenue)
    - Project 5 forward growth rates (decay toward terminal)
    - Persist to dcf_assumptions
    """
    rows = fetch_financials(ticker)
    if len(rows) < 2:
        log.warning("%s: not enough financial history", ticker)
        return None

    # Sort ascending
    rows = sorted(rows, key=lambda r: r["fiscal_year"])

    revenues = [r["revenue"] for r in rows if r["revenue"] and r["revenue"] > 0]
    fcfs     = [r["free_cash_flow"] for r in rows if r["free_cash_flow"] is not None]

    if len(revenues) < 2:
        log.warning("%s: insufficient revenue data", ticker)
        return None

    # Historical revenue CAGR
    hist_cagr = _cagr(revenues[0], revenues[-1], len(revenues) - 1)

    # Clamp CAGR to a sensible range: -20 % to +40 %
    hist_cagr = max(-0.20, min(hist_cagr, 0.40))

    # FCF margin: average of available years
    margins = []
    for r in rows:
        rev = r.get("revenue")
        fcf = r.get("free_cash_flow")
        if rev and rev > 0 and fcf is not None:
            margins.append(fcf / rev)

    avg_fcf_margin = statistics.mean(margins) if margins else 0.08
    avg_fcf_margin = max(-0.05, min(avg_fcf_margin, 0.50))   # clamp

    # Project growth rates: year 1-3 at hist_cagr, decay to terminal in y4-5
    assumptions = fetch_assumptions(ticker) or {}
    terminal_g  = assumptions.get("terminal_growth", 0.025) or 0.025

    # Linear decay from hist_cagr → terminal over 5 years
    def blend(start, end, steps, step_i):
        return start + (end - start) * (step_i / steps)

    growth_rates = {
        "revenue_growth_y1": round(hist_cagr, 4),
        "revenue_growth_y2": round(blend(hist_cagr, terminal_g, 4, 1), 4),
        "revenue_growth_y3": round(blend(hist_cagr, terminal_g, 4, 2), 4),
        "revenue_growth_y4": round(blend(hist_cagr, terminal_g, 4, 3), 4),
        "revenue_growth_y5": round(terminal_g, 4),
        "fcf_margin":        round(avg_fcf_margin, 4),
    }

    upsert_assumptions(ticker, growth_rates)
    log.debug("%s: hist CAGR=%.1f%%, FCF margin=%.1f%%",
              ticker, hist_cagr * 100, avg_fcf_margin * 100)
    return growth_rates


def project_fcfs(ticker: str) -> list[float] | None:
    """
    Return 5 projected annual FCFs based on:
    - Latest reported revenue as base
    - Growth rates from dcf_assumptions
    - FCF margin applied to projected revenue
    """
    rows = fetch_financials(ticker)
    if not rows:
        return None
    rows = sorted(rows, key=lambda r: r["fiscal_year"])
    base_revenue = rows[-1].get("revenue")
    if not base_revenue or base_revenue <= 0:
        log.warning("%s: invalid base revenue", ticker)
        return None

    a = fetch_assumptions(ticker)
    if not a:
        return None

    growth_keys = ["revenue_growth_y1", "revenue_growth_y2",
                   "revenue_growth_y3", "revenue_growth_y4",
                   "revenue_growth_y5"]
    growth_rates = [a.get(k, 0.025) or 0.025 for k in growth_keys]
    fcf_margin   = a.get("fcf_margin", 0.08) or 0.08

    projected_fcfs = []
    rev = base_revenue
    for g in growth_rates:
        rev *= (1 + g)
        projected_fcfs.append(rev * fcf_margin)

    return projected_fcfs
