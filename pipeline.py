"""
pipeline.py
Master orchestrator. Runs the full DCF pipeline:
  1. Ingest (or skip if data is fresh)
  2. Derive FCF/growth assumptions
  3. Run DCF valuation
  4. Run sensitivity analysis
  5. Generate Excel report

Usage:
  python pipeline.py                     # Full S&P 500 run
  python pipeline.py AAPL MSFT GOOGL     # Specific tickers only
  python pipeline.py --skip-ingest AAPL  # Skip API fetch, re-run model only
  python pipeline.py --no-excel AAPL     # Skip Excel generation
"""

import argparse
import logging
import sys
from pathlib import Path

from config.settings import LOG_LEVEL
from db.database import init_db, fetch_all_tickers
from data.ingestion import run_ingestion, fetch_sp500_tickers, fetch_market_price
from engine.fcf import derive_growth_assumptions
from engine.dcf import run_dcf
from engine.sensitivity import run_sensitivity
from output.excel_builder import build_excel_report
from output.batch_summary import build_batch_summary

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("pipeline")


def run(tickers: list[str], skip_ingest: bool = False,
        generate_excel: bool = True) -> None:

    init_db()

    # ── Step 1: Ingestion ──────────────────────────────────────────────────
    if not skip_ingest:
        log.info("=== STEP 1: Ingestion ===")
        run_ingestion(tickers if tickers else None)
    else:
        log.info("Skipping ingestion (--skip-ingest)")

    # If no tickers provided, operate on everything in DB
    if not tickers:
        tickers = fetch_all_tickers()

    total = len(tickers)
    log.info("Running model for %d tickers", total)

    results_summary = []

    for i, ticker in enumerate(tickers, 1):
        log.info("[%d/%d] Processing %s", i, total, ticker)

        # ── Step 2: FCF / growth assumptions ──────────────────────────────
        growth = derive_growth_assumptions(ticker)
        if not growth:
            log.warning("%s: skipping — could not derive growth assumptions", ticker)
            continue

        # ── Step 3: Market price ───────────────────────────────────────────
        mkt_price = fetch_market_price(ticker)
        if not mkt_price:
            log.warning("%s: no market price — upside calc will be skipped", ticker)

        # ── Step 4: DCF base case ──────────────────────────────────────────
        result = run_dcf(ticker, market_price=mkt_price)
        if not result:
            log.warning("%s: DCF failed", ticker)
            continue

        log.info(
            "%s → intrinsic=$%.2f  market=$%.2f  upside=%.1f%%  [%s]",
            ticker,
            result.get("intrinsic_price", 0),
            mkt_price or 0,
            result.get("upside_pct") or 0,
            result.get("verdict", ""),
        )

        # ── Step 5: Sensitivity grid ───────────────────────────────────────
        run_sensitivity(ticker, market_price=mkt_price)

        # ── Step 6: Excel report ───────────────────────────────────────────
        if generate_excel:
            build_excel_report(ticker)

        results_summary.append({
            "ticker":  ticker,
            "intrinsic": result.get("intrinsic_price"),
            "market":    mkt_price,
            "upside":    result.get("upside_pct"),
            "verdict":   result.get("verdict"),
        })

    # Print summary table
    log.info("\n%s", "=" * 70)
    log.info("%-8s %-12s %-12s %-10s %-15s", "Ticker", "Intrinsic", "Market", "Upside%", "Verdict")
    log.info("-" * 70)
    for r in sorted(results_summary, key=lambda x: x["upside"] or -999, reverse=True):
        log.info(
            "%-8s %-12.2f %-12.2f %-10.1f %-15s",
            r["ticker"],
            r["intrinsic"] or 0,
            r["market"] or 0,
            r["upside"] or 0,
            r["verdict"] or "",
        )
    log.info("=" * 70)

    # ── Step 7: Batch summary Excel ────────────────────────────────────────
    if generate_excel and results_summary:
        log.info("=== STEP 7: Building batch summary Excel ===")
        build_batch_summary()

    log.info("Done. Reports saved to: %s", Path("reports").resolve())
    log.info("Launch dashboard:  streamlit run dashboard.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Automated DCF Pipeline")
    parser.add_argument("tickers", nargs="*", help="Ticker symbols (leave blank for full S&P 500)")
    parser.add_argument("--skip-ingest", action="store_true", help="Skip API ingestion step")
    parser.add_argument("--no-excel",    action="store_true", help="Skip Excel report generation")
    args = parser.parse_args()

    run(
        tickers=args.tickers,
        skip_ingest=args.skip_ingest,
        generate_excel=not args.no_excel,
    )
