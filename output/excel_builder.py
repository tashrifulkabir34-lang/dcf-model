"""
output/excel_builder.py
Generates a 3-tab Excel workbook per ticker using openpyxl:
  Tab 1 — DCF Summary (value bridge + key metrics)
  Tab 2 — Financials (5-year historical table)
  Tab 3 — Sensitivity heatmap (WACC × terminal growth)
"""

import json
import logging
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import (
    Font, PatternFill, Alignment, Border, Side, numbers
)
from openpyxl.utils import get_column_letter
from openpyxl.chart import BarChart, Reference
from openpyxl.chart.series import SeriesLabel

from config.settings import REPORTS_DIR, WACC_DELTAS, TG_DELTAS
from db.database import (
    fetch_financials, fetch_assumptions,
    get_conn,
)
from engine.sensitivity import grid_to_matrix

log = logging.getLogger(__name__)

# ── Styles ─────────────────────────────────────────────────────────────────

HEADER_FILL   = PatternFill("solid", fgColor="1F3864")
HEADER_FONT   = Font(bold=True, color="FFFFFF", size=11)
SUBHEAD_FILL  = PatternFill("solid", fgColor="2E75B6")
SUBHEAD_FONT  = Font(bold=True, color="FFFFFF", size=10)
LABEL_FONT    = Font(bold=True, size=10)
VALUE_FONT    = Font(size=10)
ALT_FILL      = PatternFill("solid", fgColor="EEF3FB")
POSITIVE_FILL = PatternFill("solid", fgColor="C6EFCE")
NEGATIVE_FILL = PatternFill("solid", fgColor="FFC7CE")
NEUTRAL_FILL  = PatternFill("solid", fgColor="FFEB9C")

THIN = Side(style="thin", color="BFBFBF")
MED  = Side(style="medium", color="2E75B6")
THIN_BORDER   = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEADER_BORDER = Border(bottom=Side(style="medium", color="1F3864"))

FMT_DOLLAR  = '#,##0.00'
FMT_MILLION = '#,##0,,"M"'
FMT_PCT     = '0.00%'
FMT_INT     = '#,##0'


def _set_col_width(ws, col_letter: str, width: float):
    ws.column_dimensions[col_letter].width = width


def _header_row(ws, row: int, values: list, fill=HEADER_FILL, font=HEADER_FONT):
    for col, val in enumerate(values, 1):
        c = ws.cell(row=row, column=col, value=val)
        c.fill   = fill
        c.font   = font
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = HEADER_BORDER


def _fetch_result(ticker: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT r.*, c.name, c.sector FROM dcf_results r "
            "JOIN companies c ON c.ticker = r.ticker WHERE r.ticker = ?", (ticker,)
        ).fetchone()
    return dict(row) if row else None


# ── Tab 1: DCF Summary ─────────────────────────────────────────────────────

def _build_summary_tab(ws, ticker: str):
    res  = _fetch_result(ticker)
    asmp = fetch_assumptions(ticker)
    if not res or not asmp:
        ws.title = "DCF Summary"
        ws["A1"] = "No data available"
        return

    ws.title = "DCF Summary"

    # Title block
    ws.merge_cells("A1:F1")
    title = ws["A1"]
    title.value     = f"DCF Valuation — {ticker}  |  {res.get('name', '')}"
    title.font      = Font(bold=True, size=14, color="1F3864")
    title.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 28

    ws.merge_cells("A2:F2")
    sub = ws["A2"]
    sub.value = res.get("sector", "")
    sub.font  = Font(italic=True, size=10, color="595959")

    # Section: Valuation summary
    _header_row(ws, 4, ["Metric", "Value", "", "WACC Inputs", "Value", ""])
    rows_left = [
        ("Intrinsic price",    res.get("intrinsic_price"),   FMT_DOLLAR),
        ("Market price",       res.get("market_price"),      FMT_DOLLAR),
        ("Upside / downside",  (res.get("upside_pct") or 0) / 100, FMT_PCT),
        ("Enterprise value",   res.get("enterprise_value"),  FMT_MILLION),
        ("Equity value",       res.get("equity_value"),      FMT_MILLION),
        ("PV of FCFs",         res.get("pv_fcf_sum"),        FMT_MILLION),
        ("PV terminal value",  res.get("pv_terminal_value"), FMT_MILLION),
        ("Net debt",           asmp.get("net_debt"),         FMT_MILLION),
        ("Shares outstanding", asmp.get("shares_outstanding"), FMT_INT),
        ("Verdict",            res.get("verdict"),           None),
    ]
    rows_right = [
        ("WACC",               asmp.get("wacc"),             FMT_PCT),
        ("Cost of equity",     asmp.get("cost_of_equity"),   FMT_PCT),
        ("Cost of debt",       asmp.get("cost_of_debt"),     FMT_PCT),
        ("Beta",               asmp.get("beta"),             '0.00'),
        ("Risk-free rate",     asmp.get("risk_free_rate"),   FMT_PCT),
        ("Equity risk premium",asmp.get("equity_risk_premium"), FMT_PCT),
        ("Debt weight",        asmp.get("debt_weight"),      FMT_PCT),
        ("Tax rate",           asmp.get("tax_rate"),         FMT_PCT),
        ("Terminal growth",    asmp.get("terminal_growth"),  FMT_PCT),
        ("FCF margin",         asmp.get("fcf_margin"),       FMT_PCT),
    ]

    for i, ((lbl, val, fmt), (rlbl, rval, rfmt)) in enumerate(
            zip(rows_left, rows_right), start=5):
        fill = ALT_FILL if i % 2 == 0 else PatternFill()

        lc = ws.cell(row=i, column=1, value=lbl)
        lc.font = LABEL_FONT; lc.fill = fill; lc.border = THIN_BORDER

        vc = ws.cell(row=i, column=2, value=val)
        vc.font = VALUE_FONT; vc.fill = fill; vc.border = THIN_BORDER
        if fmt:
            vc.number_format = fmt
        if lbl == "Verdict":
            if val == "UNDERVALUED":   vc.fill = POSITIVE_FILL
            elif val == "OVERVALUED":  vc.fill = NEGATIVE_FILL
            else:                       vc.fill = NEUTRAL_FILL
        elif lbl == "Upside / downside":
            vc.fill = POSITIVE_FILL if (val or 0) >= 0 else NEGATIVE_FILL

        rc = ws.cell(row=i, column=4, value=rlbl)
        rc.font = LABEL_FONT; rc.fill = fill; rc.border = THIN_BORDER

        rvc = ws.cell(row=i, column=5, value=rval)
        rvc.font = VALUE_FONT; rvc.fill = fill; rvc.border = THIN_BORDER
        if rfmt:
            rvc.number_format = rfmt

    # Column widths
    for col, w in zip("ABCDEF", [28, 18, 4, 28, 16, 4]):
        _set_col_width(ws, col, w)

    # FCF projection table
    proj_row = 17
    ws.cell(row=proj_row, column=1).value = "FCF Projections"
    ws.cell(row=proj_row, column=1).font  = Font(bold=True, size=11, color="1F3864")

    _header_row(ws, proj_row + 1,
                ["Year", "Growth rate", "Projected FCF ($M)"], SUBHEAD_FILL, SUBHEAD_FONT)

    g_keys = ["revenue_growth_y1","revenue_growth_y2","revenue_growth_y3",
              "revenue_growth_y4","revenue_growth_y5"]
    for yr, gk in enumerate(g_keys, 1):
        r = proj_row + 1 + yr
        ws.cell(row=r, column=1, value=f"Year {yr}").font = VALUE_FONT
        gc = ws.cell(row=r, column=2, value=asmp.get(gk))
        gc.number_format = FMT_PCT; gc.font = VALUE_FONT
        if r % 2 == 0:
            for c in range(1, 4):
                ws.cell(row=r, column=c).fill = ALT_FILL


def _build_financials_tab(ws, ticker: str):
    ws.title = "Financials"
    rows = sorted(fetch_financials(ticker), key=lambda r: r["fiscal_year"])
    if not rows:
        ws["A1"] = "No financial data"
        return

    years = [r["fiscal_year"] for r in rows]
    _header_row(ws, 1, ["Metric ($M)"] + [str(y) for y in years] + ["5Y CAGR"])

    metrics = [
        ("Revenue",          "revenue"),
        ("Gross profit",     "gross_profit"),
        ("EBIT",             "ebit"),
        ("EBITDA",           "ebitda"),
        ("Net income",       "net_income"),
        ("Operating CF",     "operating_cf"),
        ("Capex",            "capex"),
        ("Free cash flow",   "free_cash_flow"),
        ("Total debt",       "total_debt"),
        ("Cash & equiv",     "cash_and_equiv"),
        ("Total equity",     "total_equity"),
        ("Eff. tax rate",    "effective_tax_rate"),
    ]

    for i, (label, key) in enumerate(metrics, 2):
        fill = ALT_FILL if i % 2 == 0 else PatternFill()
        lc = ws.cell(row=i, column=1, value=label)
        lc.font = LABEL_FONT; lc.fill = fill; lc.border = THIN_BORDER

        vals = [r.get(key) for r in rows]
        for j, v in enumerate(vals, 2):
            c = ws.cell(row=i, column=j, value=v)
            c.fill = fill; c.border = THIN_BORDER; c.font = VALUE_FONT
            if key == "effective_tax_rate":
                c.number_format = FMT_PCT
            else:
                c.number_format = FMT_MILLION

        # 5Y CAGR
        v0 = vals[0]; vn = vals[-1]; n = len(vals) - 1
        if v0 and vn and n > 0 and v0 > 0 and key != "effective_tax_rate":
            try:
                cagr = (vn / v0) ** (1 / n) - 1
                # Skip if result is complex, infinite, or NaN
                if isinstance(cagr, complex) or not isinstance(cagr, float):
                    cagr = float('nan')
                import math
                if math.isnan(cagr) or math.isinf(cagr):
                    cagr = None
            except Exception:
                cagr = None
            if cagr is not None:
                cc = ws.cell(row=i, column=len(years) + 2, value=round(cagr, 4))
                cc.number_format = FMT_PCT; cc.font = VALUE_FONT
                cc.fill = (POSITIVE_FILL if cagr >= 0 else NEGATIVE_FILL)

    _set_col_width(ws, "A", 22)
    for j in range(len(years) + 2):
        _set_col_width(ws, get_column_letter(j + 2), 14)


def _build_sensitivity_tab(ws, ticker: str):
    ws.title = "Sensitivity"
    res = _fetch_result(ticker)
    if not res or not res.get("sensitivity_json"):
        ws["A1"] = "No sensitivity data"
        return

    grid = json.loads(res["sensitivity_json"])
    mat  = grid_to_matrix(grid)

    base_price   = res.get("intrinsic_price") or 0
    market_price = res.get("market_price") or 0

    ws.cell(row=1, column=1).value = "Sensitivity: Intrinsic price vs WACC & terminal growth"
    ws.cell(row=1, column=1).font  = Font(bold=True, size=12, color="1F3864")

    # Column headers = TG deltas
    tg_labels = mat["tg_labels"]
    ws.cell(row=3, column=1).value = "WACC ↓  /  TG →"
    ws.cell(row=3, column=1).font  = Font(bold=True, size=9)
    for j, lbl in enumerate(tg_labels, 2):
        c = ws.cell(row=3, column=j, value=lbl)
        c.fill = SUBHEAD_FILL; c.font = SUBHEAD_FONT
        c.alignment = Alignment(horizontal="center")

    # Row headers = WACC deltas
    wacc_labels = mat["wacc_labels"]
    for i, (wlbl, row_vals) in enumerate(zip(wacc_labels, mat["matrix"]), 4):
        wc = ws.cell(row=i, column=1, value=wlbl)
        wc.fill = SUBHEAD_FILL; wc.font = SUBHEAD_FONT
        wc.alignment = Alignment(horizontal="center")

        for j, price in enumerate(row_vals, 2):
            c = ws.cell(row=i, column=j, value=price)
            c.number_format = FMT_DOLLAR
            c.alignment = Alignment(horizontal="center")
            c.border = THIN_BORDER
            if price is None:
                c.value = "N/A"
                continue
            # Color: green if > market, red if < market, yellow if base
            if abs(WACC_DELTAS[i - 4]) < 0.001 and abs(TG_DELTAS[j - 2]) < 0.001:
                c.fill = NEUTRAL_FILL   # base case
            elif market_price and price > market_price:
                c.fill = POSITIVE_FILL
            elif market_price and price < market_price:
                c.fill = NEGATIVE_FILL

    # Legend
    leg_row = 4 + len(wacc_labels) + 2
    ws.cell(row=leg_row, column=1, value="Green = price > market  |  Red = price < market  |  Yellow = base case")
    ws.cell(row=leg_row, column=1).font = Font(italic=True, size=9, color="595959")

    for col in range(1, 8):
        _set_col_width(ws, get_column_letter(col), 14)


# ── Master builder ─────────────────────────────────────────────────────────

def build_excel_report(ticker: str) -> Path | None:
    """Build 3-tab workbook for ticker and save to REPORTS_DIR."""
    try:
        import openpyxl
    except ImportError:
        log.error("openpyxl not installed. Run: pip install openpyxl")
        return None

    wb = Workbook()
    ws1 = wb.active
    _build_summary_tab(ws1, ticker)

    ws2 = wb.create_sheet()
    _build_financials_tab(ws2, ticker)

    ws3 = wb.create_sheet()
    _build_sensitivity_tab(ws3, ticker)

    out_path = REPORTS_DIR / f"{ticker}_DCF.xlsx"
    wb.save(out_path)
    log.info("Saved report: %s", out_path)
    return out_path
