-- ============================================================
-- DCF Model Schema
-- ============================================================

-- S&P 500 constituent metadata
CREATE TABLE IF NOT EXISTS companies (
    ticker          TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    sector          TEXT,
    industry        TEXT,
    exchange        TEXT,
    market_cap      REAL,
    shares_outstanding REAL,
    last_updated    TEXT DEFAULT (datetime('now'))
);

-- Raw annual financial statements (income + balance + cash flow merged)
CREATE TABLE IF NOT EXISTS financials (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT NOT NULL,
    fiscal_year     INTEGER NOT NULL,
    period          TEXT DEFAULT 'FY',               -- FY, Q1..Q4

    -- Income Statement
    revenue         REAL,
    gross_profit    REAL,
    ebit            REAL,
    ebitda          REAL,
    net_income      REAL,
    eps             REAL,

    -- Balance Sheet
    total_assets    REAL,
    total_debt      REAL,
    cash_and_equiv  REAL,
    total_equity    REAL,

    -- Cash Flow Statement
    operating_cf    REAL,
    capex           REAL,
    free_cash_flow  REAL,        -- operating_cf - capex (or as reported)
    depreciation    REAL,

    -- Tax
    income_tax_exp  REAL,
    effective_tax_rate REAL,

    created_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (ticker) REFERENCES companies(ticker),
    UNIQUE(ticker, fiscal_year, period)
);

-- WACC and DCF assumption inputs per ticker
CREATE TABLE IF NOT EXISTS dcf_assumptions (
    ticker              TEXT PRIMARY KEY,

    -- WACC inputs
    risk_free_rate      REAL DEFAULT 0.045,   -- 10-yr Treasury yield
    equity_risk_premium REAL DEFAULT 0.055,   -- Damodaran ERP
    beta                REAL,
    cost_of_equity      REAL,                 -- CAPM: rf + beta * ERP
    cost_of_debt        REAL,
    tax_rate            REAL,
    debt_weight         REAL,
    equity_weight       REAL,
    wacc                REAL,

    -- FCF projection
    revenue_growth_y1   REAL,    -- Year 1 growth rate
    revenue_growth_y2   REAL,
    revenue_growth_y3   REAL,
    revenue_growth_y4   REAL,
    revenue_growth_y5   REAL,
    fcf_margin          REAL,    -- Average FCF / Revenue margin
    terminal_growth     REAL DEFAULT 0.025,   -- Perpetuity growth rate

    -- Capital structure
    net_debt            REAL,    -- total_debt - cash
    shares_outstanding  REAL,

    last_updated        TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (ticker) REFERENCES companies(ticker)
);

-- Final DCF outputs and sensitivity grid
CREATE TABLE IF NOT EXISTS dcf_results (
    ticker              TEXT PRIMARY KEY,

    -- Intrinsic value components
    pv_fcf_sum          REAL,       -- PV of 5-year FCFs
    pv_terminal_value   REAL,       -- PV of terminal value
    enterprise_value    REAL,       -- pv_fcf_sum + pv_terminal_value
    equity_value        REAL,       -- enterprise_value - net_debt
    intrinsic_price     REAL,       -- equity_value / shares_outstanding
    market_price        REAL,       -- current market price
    upside_pct          REAL,       -- (intrinsic - market) / market * 100
    margin_of_safety    REAL,       -- same as upside but floored at 0

    -- Verdict
    verdict             TEXT,       -- UNDERVALUED / FAIRLY_VALUED / OVERVALUED

    -- Sensitivity grid stored as JSON
    -- keys: "wacc_delta,tg_delta" -> intrinsic_price
    sensitivity_json    TEXT,

    calculated_at       TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (ticker) REFERENCES companies(ticker)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_financials_ticker ON financials(ticker);
CREATE INDEX IF NOT EXISTS idx_financials_year   ON financials(ticker, fiscal_year);
CREATE INDEX IF NOT EXISTS idx_results_upside    ON dcf_results(upside_pct DESC);
