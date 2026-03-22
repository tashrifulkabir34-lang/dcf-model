"""
engine/dcf.py
Core DCF valuation:
  - Discounts projected FCFs to present value
  - Adds terminal value (Gordon Growth Model)
  - Subtracts net debt to get equity value
  - Divides by shares outstanding → intrinsic price per share
"""

import logging
from db.database import fetch_assumptions, upsert_results
from engine.fcf import project_fcfs
from config.settings import UNDERVALUED_THRESHOLD, OVERVALUED_THRESHOLD

log = logging.getLogger(__name__)


def discount_fcfs(fcfs: list[float], wacc: float) -> tuple[list[float], float]:
    """Return (list of PV per year, sum of PVs)."""
    pv_list = []
    for t, fcf in enumerate(fcfs, start=1):
        pv = fcf / (1 + wacc) ** t
        pv_list.append(pv)
    return pv_list, sum(pv_list)


def terminal_value(fcf_year5: float, wacc: float, terminal_growth: float) -> float:
    """Gordon Growth Model terminal value (at end of year 5)."""
    if wacc <= terminal_growth:
        raise ValueError(f"WACC ({wacc:.2%}) must exceed terminal growth ({terminal_growth:.2%})")
    return fcf_year5 * (1 + terminal_growth) / (wacc - terminal_growth)


def run_dcf(ticker: str, market_price: float = None,
            wacc_override: float = None,
            tg_override: float = None) -> dict | None:
    """
    Full DCF for a single ticker.
    Returns result dict and persists to dcf_results.

    Args:
        ticker: stock symbol
        market_price: current share price (for upside calc)
        wacc_override: override stored WACC (used in sensitivity)
        tg_override: override terminal growth rate
    """
    a = fetch_assumptions(ticker)
    if not a:
        log.warning("%s: no assumptions, skipping DCF", ticker)
        return None

    wacc     = wacc_override if wacc_override is not None else a.get("wacc")
    term_g   = tg_override   if tg_override is not None   else a.get("terminal_growth", 0.025)
    net_debt = a.get("net_debt", 0) or 0
    shares   = a.get("shares_outstanding") or 1

    if not wacc or wacc <= 0:
        log.warning("%s: invalid WACC %.4f", ticker, wacc or 0)
        return None

    fcfs = project_fcfs(ticker)
    if not fcfs or len(fcfs) < 5:
        log.warning("%s: could not project FCFs", ticker)
        return None

    try:
        pv_list, pv_sum = discount_fcfs(fcfs, wacc)
        tv              = terminal_value(fcfs[-1], wacc, term_g)
        pv_tv           = tv / (1 + wacc) ** 5
        ev              = pv_sum + pv_tv
        eq_value        = ev - net_debt
        intrinsic       = eq_value / shares
    except ValueError as e:
        log.error("%s: DCF math error — %s", ticker, e)
        return None

    # Verdict
    upside = None
    if market_price and market_price > 0:
        upside = (intrinsic - market_price) / market_price * 100

    if upside is None:
        verdict = "UNKNOWN"
    elif upside > UNDERVALUED_THRESHOLD:
        verdict = "UNDERVALUED"
    elif upside < OVERVALUED_THRESHOLD:
        verdict = "OVERVALUED"
    else:
        verdict = "FAIRLY_VALUED"

    result = {
        "pv_fcf_sum":       round(pv_sum, 2),
        "pv_terminal_value":round(pv_tv, 2),
        "enterprise_value": round(ev, 2),
        "equity_value":     round(eq_value, 2),
        "intrinsic_price":  round(intrinsic, 4),
        "market_price":     round(market_price, 4) if market_price else None,
        "upside_pct":       round(upside, 2) if upside is not None else None,
        "margin_of_safety": round(max(upside, 0), 2) if upside is not None else None,
        "verdict":          verdict,
    }

    # Only persist base-case (no overrides) to avoid polluting the results table
    if wacc_override is None and tg_override is None:
        upsert_results(ticker, {k: v for k, v in result.items()
                                if k != "sensitivity_json"})

    return result
