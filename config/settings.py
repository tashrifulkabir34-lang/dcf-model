"""
config/settings.py
Central configuration — edit API_KEY and DB_PATH before running.
"""

import os
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR  = Path(__file__).resolve().parent.parent
DB_PATH   = BASE_DIR / "db" / "dcf.db"
REPORTS_DIR = BASE_DIR / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

# ── Data source ────────────────────────────────────────────────────────────
# yfinance pulls from Yahoo Finance — no API key required.
# S&P 500 tickers are scraped from Wikipedia automatically.

# ── Ingestion settings ─────────────────────────────────────────────────────
YEARS_OF_HISTORY   = 5        # Annual statements to pull per ticker
REQUEST_DELAY_SEC  = 0.25     # Polite delay between API calls
MAX_RETRIES        = 3        # Exponential back-off retries
RETRY_BACKOFF_SEC  = 2.0      # Base wait on retry

# ── DCF Model constants ────────────────────────────────────────────────────
RISK_FREE_RATE      = 0.045   # US 10-yr Treasury (update periodically)
EQUITY_RISK_PREMIUM = 0.055   # Damodaran implied ERP
DEFAULT_TERMINAL_GROWTH = 0.025   # Long-run GDP growth proxy
DEFAULT_TAX_RATE    = 0.21    # US corporate statutory rate fallback

# Sensitivity grid deltas applied to base WACC and terminal growth
WACC_DELTAS = [-0.02, -0.01, 0.00, +0.01, +0.02]   # ± 2 %
TG_DELTAS   = [-0.01, -0.005, 0.00, +0.005, +0.01]  # ± 1 %

# Verdict thresholds (upside %)
UNDERVALUED_THRESHOLD  =  10   # upside > 10 % → UNDERVALUED
OVERVALUED_THRESHOLD   = -10   # upside < -10 % → OVERVALUED

# ── Logging ────────────────────────────────────────────────────────────────
LOG_LEVEL = "INFO"
