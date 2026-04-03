# Automated DCF Model — S&P 500

A fully automated Discounted Cash Flow (DCF) valuation engine covering the entire S&P 500 universe. Built with Python, SQL (SQLite/PostgreSQL), and Excel output via openpyxl.

---

## Architecture

```
FMP API → SQL (SQLite) → Python DCF Engine → Excel Dashboard (per ticker)
```

| Layer | Files | Purpose |
|-------|-------|---------|
| Ingestion | `data/ingestion.py` | Pulls financials, profiles, WACC inputs from FMP |
| Storage | `data/schema.sql`, `db/database.py` | Normalised 4-table schema |
| Engine | `engine/wacc.py`, `fcf.py`, `dcf.py`, `sensitivity.py` | DCF math |
| Output | `output/excel_builder.py` | 3-tab Excel workbook per ticker |
| Orchestrator | `pipeline.py` | End-to-end runner |

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/tashrifulkabir34-lang/dcf-model.git
cd dcf-model
pip install -r requirements.txt
```

### 2. Configure API key

Get a free API key from [financialmodelingprep.com](https://financialmodelingprep.com/).

```bash
export FMP_API_KEY="your_key_here"
```

Or edit `config/settings.py` directly:

```python
FMP_API_KEY = "your_key_here"
```

### 3. Run

**Full S&P 500 run** (500 tickers, ~30–60 min depending on API tier):
```bash
python pipeline.py
```

**Quick test with specific tickers:**
```bash
python pipeline.py AAPL MSFT GOOGL AMZN NVDA
```

**Re-run model only (skip API calls, use cached DB data):**
```bash
python pipeline.py --skip-ingest AAPL MSFT
```

**Skip Excel generation:**
```bash
python pipeline.py --no-excel AAPL
```

**Ingestion only:**
```bash
python -m data.ingestion AAPL MSFT
```

---

## Output

Reports are saved to `reports/` as `{TICKER}_DCF.xlsx`.

Each workbook contains three tabs:

### Tab 1 — DCF Summary
- Intrinsic price, market price, upside/downside %
- Enterprise value, equity value, PV of FCFs, PV of terminal value
- WACC breakdown (beta, cost of equity, cost of debt, weights)
- 5-year FCF projection table
- Colour-coded verdict: 🟢 UNDERVALUED / 🟡 FAIRLY_VALUED / 🔴 OVERVALUED

### Tab 2 — Financials
- 5-year historical table: revenue, gross profit, EBIT, EBITDA, net income,
  operating CF, capex, FCF, total debt, cash, equity, effective tax rate
- 5Y CAGR column per metric, colour-coded green/red

### Tab 3 — Sensitivity Heatmap
- 5×5 grid of intrinsic price
- Rows: WACC ±2% in 1% steps
- Columns: Terminal growth ±1% in 0.5% steps
- Green = price above market, Red = below market, Yellow = base case

---

## Database Schema

```sql
companies       -- ticker metadata
financials      -- 5-year annual statements
dcf_assumptions -- WACC inputs + growth projections
dcf_results     -- intrinsic price, upside, sensitivity JSON
```

SQLite by default (`db/dcf.db`). To use PostgreSQL, swap the `sqlite3` calls in `db/database.py` for `psycopg2` — only that file changes.

---

## DCF Methodology

| Item | Approach |
|------|---------|
| Revenue growth | Historical CAGR, decaying linearly to terminal growth by year 5 |
| FCF margin | 5-year average (FCF / Revenue) |
| WACC | CAPM cost of equity + after-tax cost of debt, book-value weights |
| Terminal value | Gordon Growth Model: FCF₅ × (1+g) / (WACC − g) |
| Terminal growth | Default 2.5% (configurable in `settings.py`) |
| Equity value | Enterprise value − net debt |
| Intrinsic price | Equity value / diluted shares outstanding |

---

## Configuration

All constants are in `config/settings.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `RISK_FREE_RATE` | 4.5% | US 10-yr Treasury yield |
| `EQUITY_RISK_PREMIUM` | 5.5% | Damodaran implied ERP |
| `DEFAULT_TERMINAL_GROWTH` | 2.5% | Long-run GDP proxy |
| `YEARS_OF_HISTORY` | 5 | Years of annual statements to pull |
| `WACC_DELTAS` | ±2% | Sensitivity grid WACC range |
| `TG_DELTAS` | ±1% | Sensitivity grid terminal growth range |
| `UNDERVALUED_THRESHOLD` | +10% | Upside % to classify as undervalued |

---

## Project Structure

```
dcf-model/
├── config/
│   └── settings.py          # API key, constants, thresholds
├── data/
│   ├── ingestion.py         # FMP API client + storage
│   └── schema.sql           # Database DDL
├── db/
│   └── database.py          # SQLite helpers, upserts, queries
├── engine/
│   ├── wacc.py              # CAPM + WACC computation
│   ├── fcf.py               # Historical analysis + FCF projection
│   ├── dcf.py               # Discounting + terminal value
│   └── sensitivity.py       # WACC × TG sensitivity grid
├── output/
│   └── excel_builder.py     # 3-tab openpyxl workbook
├── reports/                 # Generated Excel files (git-ignored)
├── db/
│   └── dcf.db               # SQLite database (git-ignored)
├── pipeline.py              # Master orchestrator
├── requirements.txt
└── README.md
```

---

## Limitations & Caveats

- DCF models are highly sensitive to growth and discount rate assumptions — treat outputs as a starting framework, not a buy/sell signal.
- FMP free tier has rate limits (~250 requests/day). Use `--skip-ingest` to re-run the model without hitting the API.
- Terminal growth is capped at WACC − 0.5% to avoid mathematical singularities.
- Growth rates are clamped to [−20%, +40%] to prevent outlier distortions.

---

## License

MIT
