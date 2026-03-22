"""
output/batch_summary.py
Generates a single master Excel workbook with ALL tickers ranked by upside.
Includes:
  Sheet 1 — Full ranked table (all tickers, color-coded)
  Sheet 2 — Top 50 undervalued
  Sheet 3 — Sector breakdown summary
  Sheet 4 — Verdict distribution chart data

Run standalone:
  python -m output.batch_summary
"""

import logging
from pathlib import Path
from collections import defaultdict

from openpyxl import Workbook
from openpyxl.styles import (
    Font, PatternFill, Alignment, Border, Side, numbers
)
from openpyxl.utils import get_column_letter
from openpyxl.chart import BarChart, Reference
from openpyxl.formatting.rule import ColorScaleRule, CellIsRule, FormulaRule
from openpyxl.chart.series import SeriesLabel

from config.settings import REPORTS_DIR
from db.database import fetch_results_summary, get_conn

log = logging.getLogger(__name__)

# ── Styles ──────────────────────────────────────────────────────────────────

DARK_BLUE   = "1F3864"
MID_BLUE    = "2E75B6"
LIGHT_BLUE  = "D6E4F0"

H_FILL  = PatternFill("solid", fgColor=DARK_BLUE)
H_FONT  = Font(bold=True, color="FFFFFF", size=11)
SH_FILL = PatternFill("solid", fgColor=MID_BLUE)
SH_FONT = Font(bold=True, color="FFFFFF", size=10)

GREEN_FILL  = PatternFill("solid", fgColor="C6EFCE")
GREEN_FONT  = Font(color="276221", bold=True)
RED_FILL    = PatternFill("solid", fgColor="FFC7CE")
RED_FONT    = Font(color="9C0006", bold=True)
YELLOW_FILL = PatternFill("solid", fgColor="FFEB9C")
YELLOW_FONT = Font(color="7D6608")
ALT_FILL    = PatternFill("solid", fgColor="F2F7FD")

THIN   = Side(style="thin",   color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

FMT_DOLLAR = '$#,##0.00'
FMT_PCT    = '0.0%'
FMT_PCT2   = '0.00%'


def _hrow(ws, row, values, fill=H_FILL, font=H_FONT, height=22):
    ws.row_dimensions[row].height = height
    for col, val in enumerate(values, 1):
        c = ws.cell(row=row, column=col, value=val)
        c.fill = fill; c.font = font
        c.alignment = Alignment(horizontal="center", vertical="center",
                                wrap_text=True)


def _set_widths(ws, widths: dict):
    for col_letter, w in widths.items():
        ws.column_dimensions[col_letter].width = w


def _fetch_full_results() -> list[dict]:
    """Full result rows joined with company + assumptions."""
    sql = """
        SELECT
            c.ticker, c.name, c.sector, c.industry,
            r.intrinsic_price, r.market_price, r.upside_pct,
            r.pv_fcf_sum, r.pv_terminal_value, r.enterprise_value,
            r.equity_value, r.verdict, r.calculated_at,
            a.wacc, a.beta, a.terminal_growth, a.fcf_margin,
            a.revenue_growth_y1
        FROM dcf_results r
        JOIN companies    c ON c.ticker = r.ticker
        LEFT JOIN dcf_assumptions a ON a.ticker = r.ticker
        ORDER BY r.upside_pct DESC
    """
    with get_conn() as conn:
        rows = conn.execute(sql).fetchall()
    return [dict(r) for r in rows]


# ── Sheet 1: Full ranked table ──────────────────────────────────────────────

COLS = [
    ("Rank",            "A",  7),
    ("Ticker",          "B",  9),
    ("Company",         "C",  32),
    ("Sector",          "D",  20),
    ("Intrinsic ($)",   "E",  14),
    ("Market ($)",      "F",  13),
    ("Upside %",        "G",  12),
    ("Verdict",         "H",  16),
    ("WACC",            "I",  10),
    ("Beta",            "J",  8),
    ("FCF Margin",      "K",  12),
    ("Term. Growth",    "L",  13),
    ("Y1 Rev Growth",   "M",  13),
    ("EV ($M)",         "N",  14),
    ("Calculated",      "O",  18),
]


def _build_ranked_sheet(ws, rows: list[dict], title: str = "All tickers — ranked by upside"):
    ws.title = "All Tickers"

    # Title
    last_col = get_column_letter(len(COLS))
    ws.merge_cells(f"A1:{last_col}1")
    t = ws["A1"]
    t.value = title
    t.font  = Font(bold=True, size=14, color=DARK_BLUE)
    t.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 26

    ws.merge_cells(f"A2:{last_col}2")
    ws["A2"].value = (f"{len(rows)} companies | "
                      "Green = undervalued (>10%)  "
                      "Red = overvalued (<-10%)  "
                      "Yellow = fairly valued")
    ws["A2"].font  = Font(italic=True, size=9, color="595959")

    _hrow(ws, 3, [c[0] for c in COLS])

    for i, r in enumerate(rows, 1):
        row = i + 3
        fill = ALT_FILL if i % 2 == 0 else PatternFill()
        verdict = r.get("verdict", "")

        if verdict == "UNDERVALUED":
            vfill, vfont = GREEN_FILL,  GREEN_FONT
        elif verdict == "OVERVALUED":
            vfill, vfont = RED_FILL,    RED_FONT
        else:
            vfill, vfont = YELLOW_FILL, YELLOW_FONT

        upside_raw = (r.get("upside_pct") or 0) / 100

        vals = [
            i,
            r.get("ticker"),
            r.get("name"),
            r.get("sector"),
            r.get("intrinsic_price"),
            r.get("market_price"),
            upside_raw,
            verdict,
            r.get("wacc"),
            r.get("beta"),
            r.get("fcf_margin"),
            r.get("terminal_growth"),
            r.get("revenue_growth_y1"),
            (r.get("enterprise_value") or 0) / 1e6,
            r.get("calculated_at", "")[:10] if r.get("calculated_at") else "",
        ]
        fmts = [None, None, None, None,
                FMT_DOLLAR, FMT_DOLLAR, FMT_PCT,
                None,
                FMT_PCT2, "0.00", FMT_PCT, FMT_PCT, FMT_PCT,
                '#,##0,,"M"', None]

        for col_i, (val, fmt) in enumerate(zip(vals, fmts), 1):
            c = ws.cell(row=row, column=col_i, value=val)
            c.border = BORDER
            c.alignment = Alignment(vertical="center")
            if fmt:
                c.number_format = fmt
            # Verdict cell gets color
            if col_i == 8:
                c.fill = vfill; c.font = vfont
                c.alignment = Alignment(horizontal="center", vertical="center")
            elif col_i == 7:
                # Upside % — color based on sign
                c.fill = GREEN_FILL if upside_raw >= 0.1 else (
                    RED_FILL if upside_raw <= -0.1 else YELLOW_FILL)
            elif col_i in (1, 2):
                c.alignment = Alignment(horizontal="center", vertical="center")
            else:
                c.fill = fill

    # Set column widths
    for label, col_letter, width in COLS:
        ws.column_dimensions[col_letter].width = width

    # Freeze panes below header
    ws.freeze_panes = "A4"


# ── Sheet 2: Top 50 undervalued ─────────────────────────────────────────────

def _build_top50_sheet(ws, rows: list[dict]):
    ws.title = "Top 50 Undervalued"
    top50 = [r for r in rows if (r.get("upside_pct") or 0) > 0][:50]

    ws.merge_cells("A1:J1")
    ws["A1"].value = "Top 50 Most Undervalued Companies"
    ws["A1"].font  = Font(bold=True, size=14, color=DARK_BLUE)
    ws.row_dimensions[1].height = 26

    headers = ["Rank", "Ticker", "Company", "Sector",
               "Intrinsic ($)", "Market ($)", "Upside %",
               "WACC", "Beta", "FCF Margin"]
    _hrow(ws, 2, headers)

    for i, r in enumerate(top50, 1):
        row = i + 2
        upside_raw = (r.get("upside_pct") or 0) / 100
        vals = [
            i,
            r.get("ticker"),
            r.get("name"),
            r.get("sector"),
            r.get("intrinsic_price"),
            r.get("market_price"),
            upside_raw,
            r.get("wacc"),
            r.get("beta"),
            r.get("fcf_margin"),
        ]
        fmts = [None, None, None, None,
                FMT_DOLLAR, FMT_DOLLAR, FMT_PCT,
                FMT_PCT2, "0.00", FMT_PCT]

        fill = ALT_FILL if i % 2 == 0 else PatternFill()
        for col_i, (val, fmt) in enumerate(zip(vals, fmts), 1):
            c = ws.cell(row=row, column=col_i, value=val)
            c.border = BORDER
            c.alignment = Alignment(vertical="center")
            c.fill = fill
            if fmt:
                c.number_format = fmt
            if col_i == 7:
                c.fill = GREEN_FILL
                c.font = GREEN_FONT

    widths = {"A": 7, "B": 9, "C": 32, "D": 20,
              "E": 14, "F": 13, "G": 12,
              "H": 10, "I": 8, "J": 12}
    _set_widths(ws, widths)
    ws.freeze_panes = "A3"


# ── Sheet 3: Sector breakdown ───────────────────────────────────────────────

def _build_sector_sheet(ws, rows: list[dict]):
    ws.title = "Sector Breakdown"

    # Aggregate by sector
    sectors = defaultdict(lambda: {"count": 0, "undervalued": 0,
                                    "overvalued": 0, "fairly": 0,
                                    "avg_upside": [], "avg_wacc": []})
    for r in rows:
        s = r.get("sector") or "Unknown"
        sectors[s]["count"] += 1
        v = r.get("verdict", "")
        if v == "UNDERVALUED":   sectors[s]["undervalued"] += 1
        elif v == "OVERVALUED":  sectors[s]["overvalued"]  += 1
        else:                     sectors[s]["fairly"]      += 1
        if r.get("upside_pct") is not None:
            sectors[s]["avg_upside"].append(r["upside_pct"])
        if r.get("wacc") is not None:
            sectors[s]["avg_wacc"].append(r["wacc"])

    # Sort by avg upside desc
    sector_list = []
    for s, d in sectors.items():
        avg_up   = sum(d["avg_upside"]) / len(d["avg_upside"]) if d["avg_upside"] else 0
        avg_wacc = sum(d["avg_wacc"])   / len(d["avg_wacc"])   if d["avg_wacc"]   else 0
        sector_list.append((s, d["count"], d["undervalued"],
                             d["fairly"], d["overvalued"],
                             avg_up, avg_wacc))
    sector_list.sort(key=lambda x: x[5], reverse=True)

    ws.merge_cells("A1:G1")
    ws["A1"].value = "Sector Breakdown"
    ws["A1"].font  = Font(bold=True, size=14, color=DARK_BLUE)
    ws.row_dimensions[1].height = 26

    headers = ["Sector", "Companies", "Undervalued",
               "Fairly Valued", "Overvalued",
               "Avg Upside %", "Avg WACC"]
    _hrow(ws, 2, headers)

    for i, (s, cnt, und, fair, ovr, avg_up, avg_wacc) in enumerate(sector_list, 1):
        row = i + 2
        fill = ALT_FILL if i % 2 == 0 else PatternFill()
        data = [s, cnt, und, fair, ovr, avg_up / 100, avg_wacc]
        fmts = [None, None, None, None, None, FMT_PCT, FMT_PCT2]

        for col_i, (val, fmt) in enumerate(zip(data, fmts), 1):
            c = ws.cell(row=row, column=col_i, value=val)
            c.border = BORDER
            c.fill = fill
            c.alignment = Alignment(vertical="center")
            if fmt:
                c.number_format = fmt
            if col_i == 6:
                c.fill = GREEN_FILL if avg_up > 5 else (
                    RED_FILL if avg_up < -5 else YELLOW_FILL)

    _set_widths(ws, {"A": 28, "B": 12, "C": 14,
                     "D": 14, "E": 13, "F": 14, "G": 12})
    ws.freeze_panes = "A3"

    # Bar chart: avg upside by sector
    chart_data_start = 3
    chart_data_end   = 2 + len(sector_list)

    chart = BarChart()
    chart.type    = "bar"
    chart.title   = "Average Upside % by Sector"
    chart.y_axis.title = "Sector"
    chart.x_axis.title = "Avg Upside %"
    chart.width = 20; chart.height = 14

    data_ref  = Reference(ws, min_col=6, min_row=chart_data_start,
                          max_row=chart_data_end)
    cats_ref  = Reference(ws, min_col=1, min_row=chart_data_start,
                          max_row=chart_data_end)
    chart.add_data(data_ref)
    chart.set_categories(cats_ref)
    chart.series[0].title = SeriesLabel(v="Avg Upside %")

    ws.add_chart(chart, "I2")


# ── Sheet 4: Verdict distribution ──────────────────────────────────────────

def _build_verdict_sheet(ws, rows: list[dict]):
    ws.title = "Verdict Distribution"

    counts = {"UNDERVALUED": 0, "FAIRLY_VALUED": 0, "OVERVALUED": 0}
    for r in rows:
        v = r.get("verdict", "FAIRLY_VALUED")
        if v in counts:
            counts[v] += 1
        else:
            counts["FAIRLY_VALUED"] += 1

    ws["A1"].value = "Verdict"; ws["A1"].font = Font(bold=True)
    ws["B1"].value = "Count";   ws["B1"].font = Font(bold=True)

    labels = ["Undervalued", "Fairly Valued", "Overvalued"]
    keys   = ["UNDERVALUED", "FAIRLY_VALUED", "OVERVALUED"]
    fills  = [GREEN_FILL, YELLOW_FILL, RED_FILL]

    for i, (label, key, fill) in enumerate(zip(labels, keys, fills), 2):
        ws.cell(row=i, column=1, value=label).fill = fill
        ws.cell(row=i, column=2, value=counts[key]).fill = fill

    from openpyxl.chart import PieChart
    chart = PieChart()
    chart.title  = f"S&P 500 DCF Verdict Distribution (n={len(rows)})"
    chart.width  = 18; chart.height = 14

    data = Reference(ws, min_col=2, min_row=1, max_row=4)
    cats = Reference(ws, min_col=1, min_row=2, max_row=4)
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(cats)
    ws.add_chart(chart, "D1")

    _set_widths(ws, {"A": 18, "B": 10})


# ── Master builder ──────────────────────────────────────────────────────────

def build_batch_summary() -> Path | None:
    rows = _fetch_full_results()
    if not rows:
        log.error("No DCF results in database. Run pipeline.py first.")
        return None

    wb = Workbook()
    ws1 = wb.active
    _build_ranked_sheet(ws1, rows)

    ws2 = wb.create_sheet()
    _build_top50_sheet(ws2, rows)

    ws3 = wb.create_sheet()
    _build_sector_sheet(ws3, rows)

    ws4 = wb.create_sheet()
    _build_verdict_sheet(ws4, rows)

    out = REPORTS_DIR / "SP500_DCF_Summary.xlsx"
    wb.save(out)
    log.info("Saved batch summary: %s", out)
    return out


if __name__ == "__main__":
    import logging
    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(message)s")
    path = build_batch_summary()
    if path:
        print(f"Saved → {path}")
