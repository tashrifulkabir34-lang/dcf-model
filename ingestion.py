"""
data/ingestion.py
Pulls all required data from Yahoo Finance via yfinance.
No API key required. No daily call limits.

S&P 500 ticker list is fetched from Wikipedia via pandas.
"""

import time
import logging
import pandas as pd
import yfinance as yf
from typing import Optional

from config.settings import (
    YEARS_OF_HISTORY,
    REQUEST_DELAY_SEC,
)
from db.database import (
    upsert_company,
    upsert_financials,
    upsert_assumptions,
    init_db,
)

log = logging.getLogger(__name__)


# ── S&P 500 ticker list ────────────────────────────────────────────────────

def fetch_sp500_tickers() -> list[str]:
    """
    Returns the S&P 500 ticker list (hardcoded — no internet call needed).
    BRK.B / BF.B converted to BRK-B / BF-B for yfinance compatibility.
    """
    tickers = [
        "MMM","AOS","ABT","ABBV","ACN","ADBE","AMD","AES","AFL","A","APD","ABNB",
        "AKAM","ALB","ARE","ALGN","ALLE","LNT","ALL","GOOGL","GOOG","MO","AMZN",
        "AMCR","AEE","AAL","AEP","AXP","AIG","AMT","AWK","AMP","AME","AMGN",
        "APH","ADI","ANSS","AON","APA","AAPL","AMAT","APTV","ACGL","ADM","ANET",
        "AJG","AIZ","T","ATO","ADSK","ADP","AZO","AVB","AVY","AXON","BKR","BALL",
        "BAC","BK","BBWI","BAX","BDX","BRK-B","BBY","BIO","TECH","BIIB","BLK",
        "BX","BA","BCR","BSX","BMY","AVGO","BR","BRO","BF-B","BLDR","BG","CDNS",
        "CZR","CPT","CPB","COF","CAH","KMX","CCL","CARR","CTLT","CAT","CBOE",
        "CBRE","CDW","CE","COR","CNC","CNX","CDAY","CF","CRL","SCHW","CHTR",
        "CVX","CMG","CB","CHD","CI","CINF","CTAS","CSCO","C","CFG","CLX","CME",
        "CMS","KO","CTSH","CL","CMCSA","CMA","CAG","COP","ED","STZ","CEG","COO",
        "CPRT","GLW","CTVA","CSGP","COST","CTRA","CCI","CSX","CMI","CVS","DHI",
        "DHR","DRI","DVA","DAY","DE","DAL","XRAY","DVN","DXCM","FANG","DLR",
        "DFS","DG","DLTR","D","DPZ","DOV","DOW","DHC","DTE","DUK","DD","EMN",
        "ETN","EBAY","ECL","EIX","EW","EA","ELV","EMR","ENPH","ETR","EOG","EPAM",
        "EQT","EFX","EQIX","EQR","ESS","EL","ETSY","EG","EVRG","ES","EXC","EXPE",
        "EXPD","EXR","XOM","FFIV","FDS","FICO","FAST","FRT","FDX","FIS","FITB",
        "FSLR","FE","FI","FLT","FMC","F","FTNT","FTV","FOXA","FOX","BEN","FCX",
        "GRMN","IT","GE","GEHC","GEV","GEN","GNRC","GD","GIS","GM","GPC","GILD",
        "GS","HAL","HIG","HAS","HCA","DOC","HSIC","HSY","HES","HPE","HLT","HOLX",
        "HD","HON","HRL","HST","HWM","HPQ","HUBB","HUM","HBAN","HII","IBM","IEX",
        "IDXX","ITW","INCY","IR","PODD","INTC","ICE","IFF","IP","IPG","INTU",
        "ISRG","IVZ","INVH","IQV","IRM","JBHT","JBL","JKHY","J","JNJ","JCI",
        "JPM","JNPR","K","KVUE","KDP","KEY","KEYS","KMB","KIM","KMI","KLAC","KHC",
        "KR","LHX","LH","LRCX","LW","LVS","LDOS","LEN","LLY","LIN","LYV","LKQ",
        "LMT","L","LOW","LULU","LYB","MTB","MRO","MPC","MKTX","MAR","MMC","MLM",
        "MAS","MA","MTCH","MKC","MCD","MCK","MDT","MRK","META","MET","MTD","MGM",
        "MCHP","MU","MSFT","MAA","MRNA","MHK","MOH","TAP","MDLZ","MPWR","MNST",
        "MCO","MS","MOS","MSI","MSCI","NDAQ","NTAP","NFLX","NEM","NWSA","NWS",
        "NEE","NKE","NI","NDSN","NSC","NTRS","NOC","NCLH","NRG","NUE","NVDA",
        "NVR","NXPI","ORLY","OXY","ODFL","OMC","ON","OKE","ORCL","OTIS","PCAR",
        "PKG","PLTR","PANW","PARA","PH","PAYX","PAYC","PYPL","PNR","PEP","PFE",
        "PCG","PM","PSX","PNW","PNC","POOL","PPG","PPL","PFG","PG","PGR","PLD",
        "PRU","PEG","PTC","PSA","PHM","QRVO","PWR","QCOM","DGX","RL","RJF","RTX",
        "O","REG","REGN","RF","RSG","RMD","RVTY","ROK","ROL","ROP","ROST","RCL",
        "SPGI","CRM","SBAC","SLB","STX","SRE","NOW","SHW","SPG","SWKS","SJM",
        "SNA","SOLV","SO","LUV","SWK","SBUX","STT","STLD","STE","SYK","SYF",
        "SNPS","SYY","TMUS","TROW","TTWO","TPR","TRGP","TGT","TEL","TDY","TFX",
        "TER","TSLA","TXN","TXT","TMO","TJX","TSCO","TT","TDG","TRV","TRMB",
        "TFC","TYL","TSN","USB","UBER","UDR","ULTA","UNP","UAL","UPS","URI","UNH",
        "UHS","VLO","VTR","VLTO","VRSN","VRSK","VZ","VRTX","VTRS","VICI","V",
        "VST","VMC","WRB","GWW","WAB","WBA","WMT","DIS","WBD","WM","WAT","WEC",
        "WFC","WELL","WST","WDC","WY","WHR","WMB","WTW","WYNN","XEL","XYL","YUM",
        "ZBRA","ZBH","ZTS",
    ]
    log.info("Using hardcoded S&P 500 list: %d tickers", len(tickers))
    return tickers


# ── Helpers ────────────────────────────────────────────────────────────────

def _safe_val(val, default=None):
    """Extract a scalar safely from a pandas Series or plain value."""
    try:
        if val is None:
            return default
        if hasattr(val, "iloc"):
            v = val.iloc[0] if len(val) > 0 else default
        else:
            v = val
        if pd.isna(v):
            return default
        return float(v)
    except Exception:
        return default


def _get_row(df: pd.DataFrame, *keys):
    """Try multiple row name variants; return the row Series or None."""
    for k in keys:
        if k in df.index:
            return df.loc[k]
    return None


def _col_val(df: pd.DataFrame, col, *keys):
    """Get a scalar value from df at (row_key, col)."""
    row = _get_row(df, *keys)
    if row is None or col not in df.columns:
        return None
    return _safe_val(row[col])


# ── Profile ────────────────────────────────────────────────────────────────

def fetch_and_store_profile(ticker: str, tk: yf.Ticker) -> Optional[dict]:
    try:
        info = tk.info
    except Exception as e:
        log.warning("%s: could not fetch info — %s", ticker, e)
        return None

    if not info or info.get("quoteType") not in ("EQUITY",):
        log.warning("%s: not an equity, skipping", ticker)
        return None

    profile = {
        "name":               info.get("longName") or info.get("shortName", ""),
        "sector":             info.get("sector", ""),
        "industry":           info.get("industry", ""),
        "exchange":           info.get("exchange", ""),
        "market_cap":         info.get("marketCap"),
        "shares_outstanding": info.get("sharesOutstanding"),
    }
    upsert_company(ticker, profile)
    return profile


# ── Financials ─────────────────────────────────────────────────────────────

def fetch_and_store_financials(ticker: str, tk: yf.Ticker) -> bool:
    try:
        income   = tk.financials      # rows=line items, cols=dates (newest first)
        balance  = tk.balance_sheet
        cashflow = tk.cashflow
    except Exception as e:
        log.warning("%s: statement fetch failed — %s", ticker, e)
        return False

    if income is None or income.empty:
        log.warning("%s: no income data", ticker)
        return False

    # Limit to YEARS_OF_HISTORY columns (newest → oldest)
    cols = income.columns[:YEARS_OF_HISTORY]

    for col in cols:
        year = col.year

        # Income
        revenue    = _col_val(income, col, "Total Revenue")
        gross_p    = _col_val(income, col, "Gross Profit")
        ebit       = _col_val(income, col, "EBIT", "Operating Income")
        ebitda     = _col_val(income, col, "EBITDA", "Normalized EBITDA")
        net_income = _col_val(income, col, "Net Income")
        eps        = _col_val(income, col, "Diluted EPS", "Basic EPS")
        tax_exp    = _col_val(income, col, "Tax Provision", "Income Tax Expense")
        pretax     = _col_val(income, col, "Pretax Income") or 1

        eff_tax = (tax_exp / pretax) if tax_exp and pretax else 0.21
        eff_tax = max(0.0, min(eff_tax, 0.50))

        # Balance sheet
        if balance is not None and not balance.empty and col in balance.columns:
            total_assets = _col_val(balance, col, "Total Assets")
            total_debt   = _col_val(balance, col, "Total Debt",
                                    "Long Term Debt And Capital Lease Obligation")
            cash         = _col_val(balance, col, "Cash And Cash Equivalents",
                                    "Cash Cash Equivalents And Short Term Investments")
            total_equity = _col_val(balance, col, "Stockholders Equity",
                                    "Total Equity Gross Minority Interest")
        else:
            total_assets = total_debt = cash = total_equity = None

        # Cash flow
        if cashflow is not None and not cashflow.empty and col in cashflow.columns:
            op_cf = _col_val(cashflow, col, "Operating Cash Flow",
                             "Cash Flow From Operations")
            capex = _col_val(cashflow, col, "Capital Expenditure")
            dep   = _col_val(cashflow, col, "Depreciation And Amortization",
                             "Depreciation Amortization Depletion")
            if capex is not None:
                capex = abs(capex)
        else:
            op_cf = capex = dep = None

        fcf = (op_cf - capex) if (op_cf is not None and capex is not None) else None

        upsert_financials(ticker, year, {
            "revenue":            revenue,
            "gross_profit":       gross_p,
            "ebit":               ebit,
            "ebitda":             ebitda,
            "net_income":         net_income,
            "eps":                eps,
            "total_assets":       total_assets,
            "total_debt":         total_debt,
            "cash_and_equiv":     cash,
            "total_equity":       total_equity,
            "operating_cf":       op_cf,
            "capex":              capex,
            "free_cash_flow":     fcf,
            "depreciation":       dep,
            "income_tax_exp":     tax_exp,
            "effective_tax_rate": round(eff_tax, 4),
        })

    return True


# ── WACC inputs ────────────────────────────────────────────────────────────

def fetch_and_store_wacc_inputs(ticker: str, tk: yf.Ticker, profile: dict) -> bool:
    from config.settings import RISK_FREE_RATE, EQUITY_RISK_PREMIUM, DEFAULT_TAX_RATE

    try:
        info     = tk.info
        income   = tk.financials
        balance  = tk.balance_sheet
    except Exception:
        info = {}; income = pd.DataFrame(); balance = pd.DataFrame()

    beta = float(info.get("beta") or 1.0)
    cost_of_equity = RISK_FREE_RATE + beta * EQUITY_RISK_PREMIUM

    def latest(df, *keys):
        row = _get_row(df, *keys)
        return _safe_val(row.iloc[0]) if row is not None and len(row) > 0 else None

    int_exp   = latest(income,  "Interest Expense")
    total_debt = latest(balance, "Total Debt",
                        "Long Term Debt And Capital Lease Obligation") or 0
    cash       = latest(balance, "Cash And Cash Equivalents",
                        "Cash Cash Equivalents And Short Term Investments") or 0
    equity_bv  = latest(balance, "Stockholders Equity",
                        "Total Equity Gross Minority Interest") or 1
    tax_exp    = latest(income,  "Tax Provision", "Income Tax Expense")
    pretax     = latest(income,  "Pretax Income") or 1

    cost_of_debt = abs(int_exp) / total_debt if (int_exp and total_debt > 0) else 0.05
    cost_of_debt = max(0.02, min(cost_of_debt, 0.15))

    tax_rate = (tax_exp / pretax) if (tax_exp and pretax) else DEFAULT_TAX_RATE
    tax_rate = max(0.05, min(tax_rate, 0.40))

    total_cap    = total_debt + equity_bv
    debt_weight  = total_debt / total_cap if total_cap > 0 else 0.3
    equity_weight = 1 - debt_weight
    wacc = equity_weight * cost_of_equity + debt_weight * cost_of_debt * (1 - tax_rate)

    upsert_assumptions(ticker, {
        "risk_free_rate":      RISK_FREE_RATE,
        "equity_risk_premium": EQUITY_RISK_PREMIUM,
        "beta":                round(beta, 4),
        "cost_of_equity":      round(cost_of_equity, 4),
        "cost_of_debt":        round(cost_of_debt, 4),
        "tax_rate":            round(tax_rate, 4),
        "debt_weight":         round(debt_weight, 4),
        "equity_weight":       round(equity_weight, 4),
        "wacc":                round(wacc, 4),
        "net_debt":            total_debt - cash,
        "shares_outstanding":  profile.get("shares_outstanding") or
                               info.get("sharesOutstanding") or 1,
    })
    return True


# ── Market price ───────────────────────────────────────────────────────────

def fetch_market_price(ticker: str, tk: yf.Ticker = None) -> Optional[float]:
    try:
        if tk is None:
            tk = yf.Ticker(ticker)
        info  = tk.info
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        return float(price) if price else None
    except Exception:
        return None


# ── Master runner ──────────────────────────────────────────────────────────

def run_ingestion(tickers: list[str] = None) -> None:
    """
    Full ingestion pipeline using yfinance.
    No API key. No daily limits. Pulls directly from Yahoo Finance.
    """
    init_db()

    if tickers is None:
        log.info("Fetching S&P 500 list from Wikipedia...")
        tickers = fetch_sp500_tickers()
        if not tickers:
            log.error("Could not retrieve tickers. Check internet connection.")
            return

    log.info("Starting yfinance ingestion for %d tickers", len(tickers))

    for i, ticker in enumerate(tickers, 1):
        log.info("[%d/%d] %s", i, len(tickers), ticker)
        try:
            tk      = yf.Ticker(ticker)
            profile = fetch_and_store_profile(ticker, tk)
            if not profile:
                continue
            fetch_and_store_financials(ticker, tk)
            fetch_and_store_wacc_inputs(ticker, tk, profile)
            time.sleep(REQUEST_DELAY_SEC)
        except Exception as exc:
            log.error("Error on %s: %s", ticker, exc, exc_info=True)

    log.info("Ingestion complete.")


if __name__ == "__main__":
    import sys
    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(message)s")
    run_ingestion(sys.argv[1:] or None)
