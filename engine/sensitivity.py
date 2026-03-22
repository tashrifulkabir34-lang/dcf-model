"""
engine/sensitivity.py
Generates a 5x5 sensitivity table of intrinsic price
varying WACC (±2%) and terminal growth rate (±1%).
Stores result as JSON in dcf_results.sensitivity_json.
"""

import json
import logging
from db.database import fetch_assumptions, upsert_results
from engine.dcf import run_dcf
from config.settings import WACC_DELTAS, TG_DELTAS

log = logging.getLogger(__name__)


def run_sensitivity(ticker: str, market_price: float = None) -> dict | None:
    """
    Build sensitivity grid and persist to dcf_results.
    Returns dict: { "wacc_delta,tg_delta": intrinsic_price, ... }
    """
    a = fetch_assumptions(ticker)
    if not a:
        return None

    base_wacc = a.get("wacc")
    base_tg   = a.get("terminal_growth", 0.025)

    if not base_wacc:
        log.warning("%s: no WACC for sensitivity", ticker)
        return None

    grid = {}
    for wd in WACC_DELTAS:
        for td in TG_DELTAS:
            w_adj = base_wacc + wd
            t_adj = base_tg  + td
            if w_adj <= t_adj:
                # Mathematically invalid — terminal growth ≥ WACC
                grid[f"{wd},{td}"] = None
                continue
            result = run_dcf(
                ticker,
                market_price=market_price,
                wacc_override=round(w_adj, 4),
                tg_override=round(t_adj, 4),
            )
            price = result["intrinsic_price"] if result else None
            grid[f"{wd},{td}"] = price

    # Persist JSON to dcf_results
    upsert_results(ticker, {"sensitivity_json": json.dumps(grid)})
    log.debug("%s: sensitivity grid computed (%d cells)", ticker, len(grid))
    return grid


def grid_to_matrix(grid: dict) -> dict:
    """
    Convert flat grid dict to a structured matrix for Excel rendering.
    Returns:
    {
      "wacc_labels":  ["-2%", "-1%", "Base", "+1%", "+2%"],
      "tg_labels":    ["-1%", "-0.5%", "Base", "+0.5%", "+1%"],
      "matrix":       [[price, ...], ...]   # rows = WACC, cols = TG
    }
    """
    wacc_labels = [f"{int(d*100):+d}%" for d in WACC_DELTAS]
    tg_labels   = [f"{d*100:+.1f}%" for d in TG_DELTAS]

    matrix = []
    for wd in WACC_DELTAS:
        row = []
        for td in TG_DELTAS:
            key = f"{wd},{td}"
            row.append(grid.get(key))
        matrix.append(row)

    return {
        "wacc_labels": wacc_labels,
        "tg_labels":   tg_labels,
        "matrix":      matrix,
    }
