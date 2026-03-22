"""
engine/wacc.py
Recalculate or validate WACC from stored assumptions.
Can be re-run standalone to update WACC if macro inputs change.
"""

import logging
from db.database import fetch_assumptions, upsert_assumptions
from config.settings import RISK_FREE_RATE, EQUITY_RISK_PREMIUM

log = logging.getLogger(__name__)


def compute_wacc(ticker: str, override: dict = None) -> float | None:
    """
    Load stored assumptions for ticker, optionally apply overrides,
    recompute WACC, persist, and return the value.

    override keys (all optional):
        risk_free_rate, equity_risk_premium, beta,
        cost_of_debt, tax_rate, debt_weight, equity_weight
    """
    a = fetch_assumptions(ticker)
    if not a:
        log.warning("No assumptions found for %s", ticker)
        return None

    # Apply any caller overrides
    if override:
        a.update(override)

    beta       = a.get("beta", 1.0) or 1.0
    rf         = a.get("risk_free_rate", RISK_FREE_RATE)
    erp        = a.get("equity_risk_premium", EQUITY_RISK_PREMIUM)
    cod        = a.get("cost_of_debt", 0.05) or 0.05
    tax        = a.get("tax_rate", 0.21) or 0.21
    d_weight   = a.get("debt_weight", 0.3) or 0.3
    e_weight   = 1 - d_weight

    coe  = rf + beta * erp
    wacc = e_weight * coe + d_weight * cod * (1 - tax)

    updates = {
        "cost_of_equity": round(coe, 4),
        "wacc":           round(wacc, 4),
        "equity_weight":  round(e_weight, 4),
    }
    upsert_assumptions(ticker, updates)
    log.debug("%s WACC = %.2f%%", ticker, wacc * 100)
    return wacc
