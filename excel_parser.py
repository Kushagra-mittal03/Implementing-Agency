#!/usr/bin/env python3
"""
excel_parser.py  —  Parse Grid India ISTS billing Excel workbooks.

Each workbook has one sheet per month (e.g. "Jan'25", "Feb'25" ...).
Each sheet has:
  - Row 0: "Annexure-III"
  - Row 1: Title with month/year
  - Row 2: Column headers (multi-row headers)
  - Row 3: Sub-headers (AC-UBC, AC-BC, NC-RE, NC-HVDC, RC, TC)
  - Row 4+: DIC data rows
  - Last row: TOTAL row

Column layout (0-indexed):
  0  S.No.
  1  DIC Name (Zone)
  2  Region
  3  GNAsh (MW)
  4  AC-UBC
  5  AC-BC
  6  NC-RE
  7  NC-HVDC
  8  RC
  9  TC  (Transformers component)
 10  Bilateral Charges
 11  Total

Usage:
    from excel_parser import parse_excel

    records = parse_excel("2025_combined.xlsx")
    for r in records:
        print(r)

    # Or from command line:
    python excel_parser.py 2025_combined.xlsx
"""

import os
import sys
import re

try:
    import pandas as pd
except ImportError:
    print("pandas not installed. Run: pip install pandas openpyxl")
    sys.exit(1)


# ── Month name → integer mapping ─────────────────────────────────────────────
MONTH_MAP = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
    'may': 5, 'jun': 6, 'jul': 7, 'aug': 8,
    'sep': 9, 'oct': 10,'nov': 11,'dec': 12,
}

def month_idx(year, month):
    """Position in ALL_MONTH_LABELS (Jan 2021 = 0)."""
    return (year - 2021) * 12 + (month - 1)


def parse_sheet_name(sheet_name):
    """
    Parse sheet name like "Jan'25" → (2025, 1).
    Also handles "January 2025", "Jan-25", "Jan_25".
    Returns (year, month) as ints, or (None, None) if unparseable.
    """
    s = sheet_name.strip().lower()

    # Pattern: "Jan'25" or "Jan'2025"
    m = re.match(r"([a-z]{3})'?[\s\-_]?(\d{2,4})", s)
    if m:
        mon_str = m.group(1)
        yr_str  = m.group(2)
        if mon_str in MONTH_MAP:
            yr = int(yr_str)
            if yr < 100:
                yr += 2000
            return yr, MONTH_MAP[mon_str]

    # Pattern: "January 2025"
    for mon_str, mon_int in MONTH_MAP.items():
        if s.startswith(mon_str):
            yr_match = re.search(r'(\d{4})', s)
            if yr_match:
                return int(yr_match.group(1)), mon_int

    return None, None


def safe_int(val, default=0):
    """
    Convert a cell value to int, returning default if NaN or non-numeric.
    Handles both plain integers, floats, and Indian-format strings like '17,52,25,228'.
    """
    if val is None:
        return default
    import math
    if isinstance(val, float):
        if math.isnan(val):
            return default
        return int(val)
    if isinstance(val, int):
        return val
    # Handle string with commas (Indian number format: 17,52,25,228 = 175225228)
    s = str(val).strip().replace(',', '')
    if not s or s.lower() == 'nan':
        return default
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return default


def is_total_row(row):
    """Return True if this row is the grand TOTAL row (not a DIC record)."""
    first = str(row.iloc[0]).strip().upper() if row.iloc[0] is not None else ''
    return first.startswith('TOTAL')


def is_data_row(row):
    """Return True if this row has a valid S.No (integer) and a DIC name."""
    sno = row.iloc[0]
    name = row.iloc[1]
    try:
        import math
        if isinstance(sno, float) and math.isnan(sno):
            return False
        int(sno)
        return True
    except (ValueError, TypeError):
        return False


def parse_sheet(df, year, month):
    """
    Parse one sheet's DataFrame into a list of DIC record dicts.

    Column mapping (determined from the header structure):
      col 0 = S.No
      col 1 = DIC name
      col 2 = Region
      col 3 = GNAsh
      col 4 = AC-UBC
      col 5 = AC-BC
      col 6 = NC-RE
      col 7 = NC-HVDC
      col 8 = RC
      col 9 = TC  (Transformers component)
     col 10 = Bilateral Charges
     col 11 = Total (ignored — can be recomputed)
    """
    records = []

    for _, row in df.iterrows():
        # Skip non-data rows
        if is_total_row(row):
            continue
        if not is_data_row(row):
            continue

        name    = re.sub(r'\s+', ' ', str(row.iloc[1]).replace('\n',' ')).strip() if row.iloc[1] is not None else ''
        region  = str(row.iloc[2]).strip() if row.iloc[2] is not None else ''
        gnash   = safe_int(row.iloc[3])

        # Charge columns — NaN means 0
        ac_ubc  = safe_int(row.iloc[4])
        ac_bc   = safe_int(row.iloc[5])
        nc_re   = safe_int(row.iloc[6])
        nc_hvdc = safe_int(row.iloc[7])
        rc      = safe_int(row.iloc[8])
        trx     = safe_int(row.iloc[9])    # TC column
        bil     = safe_int(row.iloc[10])   # Bilateral column

        # Some bilateral-only DICs (e.g. Northern Railways, North Central Railways)
        # have their charge in the TC column (col 9) rather than Bilateral (col 10).
        # Detect: if all AC charges are zero AND gnash is 0, it's bilateral-only.
        # In that case, treat whatever is in TC col as the bilateral charge.
        is_bilateral_only = (ac_ubc == 0 and ac_bc == 0 and nc_re == 0
                             and nc_hvdc == 0 and rc == 0 and gnash == 0)
        if is_bilateral_only and trx > 0 and bil == 0:
            bil = trx
            trx = 0

        # Skip rows with no name or invalid region
        if not name or name in ('nan', ''):
            continue
        if region not in ('NR', 'WR', 'SR', 'ER', 'NER'):
            continue

        records.append({
            'name':    name,
            'region':  region,
            'gnash':   gnash,
            'year':    year,
            'month':   month,
            'mi':      month_idx(year, month),
            'ac_ubc':  ac_ubc,
            'ac_bc':   ac_bc,
            'nc_re':   nc_re,
            'nc_hvdc': nc_hvdc,
            'rc':      rc,
            'trx':     trx,
            'bil':     bil,
        })

    return records


def parse_excel(filepath, verbose=True):
    """
    Parse a Grid India ISTS billing Excel workbook.

    Each sheet must be named with a month/year (e.g. "Jan'25", "Feb'25").
    Returns a list of dicts — one per DIC per month — with keys:
      name, region, gnash, year, month, mi,
      ac_ubc, ac_bc, nc_re, nc_hvdc, rc, trx, bil

    Args:
        filepath: Path to the .xlsx file
        verbose:  Print progress (default True)

    Returns:
        List of record dicts
    """
    xl = pd.ExcelFile(filepath)
    all_records = []

    if verbose:
        print(f"File   : {os.path.basename(filepath)}")
        print(f"Sheets : {xl.sheet_names}\n")

    for sheet_name in xl.sheet_names:
        year, month = parse_sheet_name(sheet_name)

        # Read sheet first (needed for title fallback)
        df = pd.read_excel(filepath, sheet_name=sheet_name, header=None)

        # If sheet name doesn't give month/year, try reading title from row 0
        if year is None:
            try:
                title = str(df.iloc[0, 0]).replace('\xa0', ' ')
                m = re.search(
                    r'billing\s+month\s+of\s+(\w+)[,\s]+(\d{4})',
                    title, re.IGNORECASE
                )
                if m:
                    mon_name = m.group(1).lower()[:3]
                    yr_num   = int(m.group(2))
                    if mon_name in MONTH_MAP:
                        month = MONTH_MAP[mon_name]
                        year  = yr_num
                        if verbose:
                            print(f"  Sheet '{sheet_name}' — month/year from title: {month}/{year}")
            except Exception:
                pass

        if year is None:
            if verbose:
                print(f"  ⚠  Skipping sheet '{sheet_name}' — cannot parse month/year")
            continue

        records = parse_sheet(df, year, month)
        all_records.extend(records)

        if verbose:
            n_ac  = sum(1 for r in records if r['ac_ubc'] or r['ac_bc'])
            n_bil = sum(1 for r in records if r['bil'] and not r['ac_ubc'] and not r['ac_bc'])
            total_cr = sum(
                r['ac_ubc']+r['ac_bc']+r['nc_re']+r['nc_hvdc']+r['rc']+r['trx']+r['bil']
                for r in records
            ) / 1e7
            print(f"  {sheet_name:<8}  {len(records):3d} DICs  "
                  f"(AC: {n_ac}  Bilateral-only: {n_bil})  "
                  f"Total: ₹{total_cr:,.0f} Cr")

    if verbose:
        print(f"\n  Total records : {len(all_records)}")

    return all_records


# ── Command-line usage ────────────────────────────────────────────────────────

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python excel_parser.py <path_to_xlsx> [<path_to_xlsx> ...]")
        sys.exit(1)

    for path in sys.argv[1:]:
        print(f"\n{'='*60}")
        records = parse_excel(path)

        # Quick validation — print a few sample records
        print("\nSample records:")
        for r in records[:3]:
            total = r['ac_ubc']+r['ac_bc']+r['nc_re']+r['nc_hvdc']+r['rc']+r['trx']+r['bil']
            print(f"  {r['name']:<45} {r['region']}  "
                  f"m{r['mi']}  ₹{total/1e7:.2f}Cr  "
                  f"tc={r['trx']:,}  bil={r['bil']:,}")
