"""
db/database.py
SQLite connection manager + query helpers.
Swap sqlite3 for psycopg2 to move to PostgreSQL — only this file changes.
"""

import sqlite3
import logging
from contextlib import contextmanager
from pathlib import Path

from config.settings import DB_PATH

log = logging.getLogger(__name__)


def init_db() -> None:
    """Create all tables from schema.sql if they don't exist."""
    schema_path = Path(__file__).parent.parent / "data" / "schema.sql"
    sql = schema_path.read_text()
    with get_conn() as conn:
        conn.executescript(sql)
    log.info("Database initialised at %s", DB_PATH)


@contextmanager
def get_conn():
    """Yield a SQLite connection with WAL mode and row_factory set."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def upsert_company(ticker: str, data: dict) -> None:
    sql = """
        INSERT INTO companies (ticker, name, sector, industry, exchange,
                               market_cap, shares_outstanding)
        VALUES (:ticker, :name, :sector, :industry, :exchange,
                :market_cap, :shares_outstanding)
        ON CONFLICT(ticker) DO UPDATE SET
            name               = excluded.name,
            sector             = excluded.sector,
            industry           = excluded.industry,
            market_cap         = excluded.market_cap,
            shares_outstanding = excluded.shares_outstanding,
            last_updated       = datetime('now')
    """
    with get_conn() as conn:
        conn.execute(sql, {"ticker": ticker, **data})


def upsert_financials(ticker: str, year: int, data: dict) -> None:
    sql = """
        INSERT INTO financials (
            ticker, fiscal_year, revenue, gross_profit, ebit, ebitda,
            net_income, eps, total_assets, total_debt, cash_and_equiv,
            total_equity, operating_cf, capex, free_cash_flow,
            depreciation, income_tax_exp, effective_tax_rate
        ) VALUES (
            :ticker, :fiscal_year, :revenue, :gross_profit, :ebit, :ebitda,
            :net_income, :eps, :total_assets, :total_debt, :cash_and_equiv,
            :total_equity, :operating_cf, :capex, :free_cash_flow,
            :depreciation, :income_tax_exp, :effective_tax_rate
        )
        ON CONFLICT(ticker, fiscal_year, period) DO UPDATE SET
            revenue           = excluded.revenue,
            gross_profit      = excluded.gross_profit,
            ebit              = excluded.ebit,
            ebitda            = excluded.ebitda,
            net_income        = excluded.net_income,
            operating_cf      = excluded.operating_cf,
            capex             = excluded.capex,
            free_cash_flow    = excluded.free_cash_flow,
            total_debt        = excluded.total_debt,
            cash_and_equiv    = excluded.cash_and_equiv,
            effective_tax_rate= excluded.effective_tax_rate
    """
    with get_conn() as conn:
        conn.execute(sql, {"ticker": ticker, "fiscal_year": year, **data})


def upsert_assumptions(ticker: str, data: dict) -> None:
    cols = ", ".join(data.keys())
    placeholders = ", ".join(f":{k}" for k in data.keys())
    updates = ", ".join(f"{k} = excluded.{k}" for k in data.keys()
                        if k != "ticker")
    sql = f"""
        INSERT INTO dcf_assumptions (ticker, {cols})
        VALUES (:ticker, {placeholders})
        ON CONFLICT(ticker) DO UPDATE SET {updates},
            last_updated = datetime('now')
    """
    with get_conn() as conn:
        conn.execute(sql, {"ticker": ticker, **data})


def upsert_results(ticker: str, data: dict) -> None:
    cols = ", ".join(data.keys())
    placeholders = ", ".join(f":{k}" for k in data.keys())
    updates = ", ".join(f"{k} = excluded.{k}" for k in data.keys()
                        if k != "ticker")
    sql = f"""
        INSERT INTO dcf_results (ticker, {cols})
        VALUES (:ticker, {placeholders})
        ON CONFLICT(ticker) DO UPDATE SET {updates},
            calculated_at = datetime('now')
    """
    with get_conn() as conn:
        conn.execute(sql, {"ticker": ticker, **data})


def fetch_financials(ticker: str) -> list[dict]:
    sql = """
        SELECT * FROM financials
        WHERE ticker = ?
        ORDER BY fiscal_year ASC
    """
    with get_conn() as conn:
        rows = conn.execute(sql, (ticker,)).fetchall()
    return [dict(r) for r in rows]


def fetch_assumptions(ticker: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM dcf_assumptions WHERE ticker = ?", (ticker,)
        ).fetchone()
    return dict(row) if row else None


def fetch_all_tickers() -> list[str]:
    with get_conn() as conn:
        rows = conn.execute("SELECT ticker FROM companies ORDER BY ticker").fetchall()
    return [r["ticker"] for r in rows]


def fetch_results_summary() -> list[dict]:
    """Return all DCF results joined with company metadata, sorted by upside."""
    sql = """
        SELECT c.ticker, c.name, c.sector,
               r.intrinsic_price, r.market_price, r.upside_pct,
               r.verdict, r.calculated_at
        FROM dcf_results r
        JOIN companies c ON c.ticker = r.ticker
        ORDER BY r.upside_pct DESC
    """
    with get_conn() as conn:
        rows = conn.execute(sql).fetchall()
    return [dict(r) for r in rows]
