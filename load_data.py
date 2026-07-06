#!/usr/bin/env python3
"""
load_data.py  —  Load Grid India ISTS Excel workbooks into SQLite database.

Adds new data each time. Skips months already in the database.

Usage:
    python scripts\load_data.py data\2025_combined.xlsx
    python scripts\load_data.py data\2026_combined.xlsx
    python scripts\load_data.py data\
"""

import os, sys, sqlite3, glob

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "parser"))

from excel_parser import parse_excel

DB_PATH     = os.path.join(PROJECT_ROOT, "db", "ists.db")
SCHEMA_PATH = os.path.join(PROJECT_ROOT, "db", "schema.sql")

MONTH_NAMES = ["January","February","March","April","May","June",
               "July","August","September","October","November","December"]


def get_db():
    """Open or create the database and ensure tables exist."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())
    conn.commit()
    return conn


def insert_records(conn, records):
    inserted = skipped = errors = 0
    for r in records:
        if not r.get("name") or not r.get("region"):
            errors += 1
            continue
        try:
            conn.execute("""
                INSERT OR IGNORE INTO charges
                    (dic_name, region, gnash, year, month,
                     ac_ubc, ac_bc, nc_re, nc_hvdc, rc, trx, bil)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (r["name"], r["region"], r.get("gnash",0),
                  r["year"], r["month"],
                  r.get("ac_ubc",0), r.get("ac_bc",0),
                  r.get("nc_re",0),  r.get("nc_hvdc",0),
                  r.get("rc",0),     r.get("trx",0),
                  r.get("bil",0)))

            if conn.execute("SELECT changes()").fetchone()[0]:
                inserted += 1
                conn.execute("""
                    INSERT INTO dics (name, region, gnash) VALUES (?,?,?)
                    ON CONFLICT(name) DO UPDATE SET
                        region = excluded.region,
                        gnash  = CASE WHEN excluded.gnash > 0
                                      THEN excluded.gnash ELSE dics.gnash END
                """, (r["name"], r["region"], r.get("gnash",0)))
            else:
                skipped += 1

        except sqlite3.Error as e:
            print(f"    ⚠  {r['name']} {r['year']}/{r['month']}: {e}")
            errors += 1

    conn.commit()
    return inserted, skipped, errors


def print_summary(records):
    from collections import Counter
    counts = Counter((r["year"], r["month"]) for r in records)
    print(f"\n  {'Month':<14} {'DICs':>5}  {'Total (Cr)':>11}")
    print(f"  {'-'*14} {'-'*5}  {'-'*11}")
    for (yr, mon) in sorted(counts):
        recs  = [r for r in records if r["year"]==yr and r["month"]==mon]
        total = sum(r.get("ac_ubc",0)+r.get("ac_bc",0)+r.get("nc_re",0)+
                    r.get("nc_hvdc",0)+r.get("rc",0)+r.get("trx",0)+r.get("bil",0)
                    for r in recs) / 1e7
        print(f"  {MONTH_NAMES[mon-1]:<8} {yr}  {counts[(yr,mon)]:>5}  {total:>10.0f}")


def print_db_stats(conn):
    total  = conn.execute("SELECT COUNT(*) FROM charges").fetchone()[0]
    n_dics = conn.execute("SELECT COUNT(*) FROM dics").fetchone()[0]
    dr     = conn.execute("SELECT MIN(year*100+month), MAX(year*100+month) FROM charges").fetchone()
    print(f"\n  {'='*45}")
    print(f"  Database : {DB_PATH}")
    print(f"  Records  : {total:,}")
    print(f"  DICs     : {n_dics:,}")
    if dr[0]:
        ym = lambda n: f"{MONTH_NAMES[n%100-1]} {n//100}"
        print(f"  Range    : {ym(dr[0])} → {ym(dr[1])}")
    rows = conn.execute(
        "SELECT region, COUNT(DISTINCT name) FROM dics GROUP BY region ORDER BY region"
    ).fetchall()
    if rows:
        print("  By region: " + "  ".join(f"{r[0]}: {r[1]}" for r in rows))
    print(f"  {'='*45}\n")


def resolve_files(args):
    paths = []
    for p in args:
        if os.path.isdir(p):
            paths.extend(sorted(glob.glob(os.path.join(p, "*.xlsx"))))
        elif os.path.isfile(p):
            paths.append(p)
        else:
            print(f"  ⚠  Not found: {p}")
    return paths


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    files = resolve_files(sys.argv[1:])
    if not files:
        print("No .xlsx files found.")
        sys.exit(1)

    print(f"\n  Loading {len(files)} file(s)...\n")
    conn = get_db()
    total_inserted = total_skipped = total_errors = 0

    for file_path in files:
        print(f"  File: {os.path.basename(file_path)}")
        print(f"  {'-'*45}")
        try:
            records = parse_excel(file_path, verbose=False)
        except Exception as e:
            print(f"  ❌ Failed: {e}")
            continue
        if not records:
            print("  ⚠  No records found.")
            continue
        print_summary(records)
        ins, skp, err = insert_records(conn, records)
        total_inserted += ins
        total_skipped  += skp
        total_errors   += err
        print(f"\n  ✅ Inserted {ins:,}  |  Skipped {skp:,} (already in DB)  |  Errors {err}\n")

    print_db_stats(conn)
    conn.close()


if __name__ == "__main__":
    main()
