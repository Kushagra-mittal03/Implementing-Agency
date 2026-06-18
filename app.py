"""
app.py  —  ISTS Transmission Charges Dashboard (Flask)
Run:  python app.py
Open: http://localhost:5000
"""

import os
import sqlite3
from flask import Flask, jsonify, request, render_template, g

app = Flask(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'db', 'ists.db')

MONTH_LABELS = [
    "Jan'21","Feb'21","Mar'21","Apr'21","May'21","Jun'21",
    "Jul'21","Aug'21","Sep'21","Oct'21","Nov'21","Dec'21",
    "Jan'22","Feb'22","Mar'22","Apr'22","May'22","Jun'22",
    "Jul'22","Aug'22","Sep'22","Oct'22","Nov'22","Dec'22",
    "Jan'23","Feb'23","Mar'23","Apr'23","May'23","Jun'23",
    "Jul'23","Aug'23","Sep'23","Oct'23","Nov'23","Dec'23",
    "Jan'24","Feb'24","Mar'24","Apr'24","May'24","Jun'24",
    "Jul'24","Aug'24","Sep'24","Oct'24","Nov'24","Dec'24",
    "Jan'25","Feb'25","Mar'25","Apr'25","May'25","Jun'25",
    "Jul'25","Aug'25","Sep'25","Oct'25","Nov'25","Dec'25",
    "Jan'26","Feb'26","Mar'26","Apr'26","May'26","Jun'26",
]

# ── Database connection ───────────────────────────────────────────────────────

def get_db():
    if 'db' not in g:
        if not os.path.exists(DB_PATH):
            raise FileNotFoundError(
                f"Database not found at: {DB_PATH}\n"
                "Run: python scripts\\load_data.py data\\2025_combined.xlsx"
            )
        try:
            g.db = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA journal_mode=WAL")
            g.db.execute("PRAGMA busy_timeout=5000")
        except sqlite3.OperationalError as e:
            raise RuntimeError(
                f"Cannot open database: {e}\n"
                "If the DB is in OneDrive, pause OneDrive sync and try again."
            )
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def month_idx(year, month):
    """Convert year+month to index in MONTH_LABELS (Jan 2021 = 0)."""
    return (year - 2021) * 12 + (month - 1)

def rows_to_list(rows):
    return [dict(r) for r in rows]


# ── Frontend ──────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


# ── API: metadata ─────────────────────────────────────────────────────────────

@app.route('/api/meta')
def api_meta():
    """
    Returns everything the frontend needs on load:
    - list of all DICs with region and gnash
    - list of all (year, month) combos present in DB
    - month labels array
    """
    db = get_db()

    dics = rows_to_list(db.execute(
        "SELECT name, region, gnash FROM dics ORDER BY region, name"
    ).fetchall())

    months = rows_to_list(db.execute(
        "SELECT DISTINCT year, month FROM charges ORDER BY year, month"
    ).fetchall())

    # Add month index (position in MONTH_LABELS) to each month
    for m in months:
        m['mi'] = month_idx(m['year'], m['month'])

    return jsonify({
        'dics':         dics,
        'months':       months,
        'monthLabels':  MONTH_LABELS,
        'firstMi':      months[0]['mi']  if months else 0,
        'lastMi':       months[-1]['mi'] if months else 0,
    })


# ── API: overview chart ───────────────────────────────────────────────────────

@app.route('/api/overview')
def api_overview():
    """
    Monthly totals for the main trend chart.
    Optional: ?region=NR   filter by region
    Optional: ?mi_from=0&mi_to=65   filter by month index range
    Returns one row per month with all component totals.
    """
    db     = get_db()
    region = request.args.get('region')
    mi_from = request.args.get('mi_from', 0,  type=int)
    mi_to   = request.args.get('mi_to',   999, type=int)

    # Convert mi range back to year/month for the query
    conditions = []
    params     = []

    if region:
        conditions.append("region = ?")
        params.append(region)

    # year*12 + month - 1 - 12*2021 = mi  →  year*12+month-1 between mi+12*2021+1 and mi_to+same
    # Simpler: filter on (year-2021)*12 + (month-1)
    conditions.append("(year-2021)*12 + (month-1) BETWEEN ? AND ?")
    params += [mi_from, mi_to]

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    rows = db.execute(f"""
        SELECT year, month,
               (year-2021)*12 + (month-1) AS mi,
               SUM(ac_ubc)  ac_ubc,
               SUM(ac_bc)   ac_bc,
               SUM(nc_re)   nc_re,
               SUM(nc_hvdc) nc_hvdc,
               SUM(rc)      rc,
               SUM(trx)     trx,
               SUM(bil)     bil,
               SUM(ac_ubc+ac_bc+nc_re+nc_hvdc+rc+trx+bil) total
        FROM charges {where}
        GROUP BY year, month
        ORDER BY year, month
    """, params).fetchall()

    return jsonify(rows_to_list(rows))


# ── API: single DIC detail ────────────────────────────────────────────────────

@app.route('/api/dic/<path:dic_name>')
def api_dic(dic_name):
    """
    All monthly data for one DIC, with month index added.
    Optional: ?mi_from=0&mi_to=65
    """
    db      = get_db()
    mi_from = request.args.get('mi_from', 0,   type=int)
    mi_to   = request.args.get('mi_to',   999, type=int)

    rows = db.execute("""
        SELECT year, month,
               (year-2021)*12 + (month-1) AS mi,
               gnash, ac_ubc, ac_bc, nc_re, nc_hvdc, rc, trx, bil,
               (ac_ubc+ac_bc+nc_re+nc_hvdc+rc+trx+bil) AS total
        FROM charges
        WHERE dic_name = ?
          AND (year-2021)*12 + (month-1) BETWEEN ? AND ?
        ORDER BY year, month
    """, (dic_name, mi_from, mi_to)).fetchall()

    return jsonify(rows_to_list(rows))


# ── API: region breakdown ─────────────────────────────────────────────────────

@app.route('/api/region/<region>')
def api_region(region):
    """
    All DICs in a region summed over the requested month range.
    Optional: ?mi_from=0&mi_to=65
    """
    db      = get_db()
    mi_from = request.args.get('mi_from', 0,   type=int)
    mi_to   = request.args.get('mi_to',   999, type=int)

    rows = db.execute("""
        SELECT dic_name,
               SUM(ac_ubc)  ac_ubc,
               SUM(ac_bc)   ac_bc,
               SUM(nc_re)   nc_re,
               SUM(nc_hvdc) nc_hvdc,
               SUM(rc)      rc,
               SUM(trx)     trx,
               SUM(bil)     bil,
               SUM(ac_ubc+ac_bc+nc_re+nc_hvdc+rc+trx+bil) total
        FROM charges
        WHERE region = ?
          AND (year-2021)*12 + (month-1) BETWEEN ? AND ?
        GROUP BY dic_name
        ORDER BY total DESC
    """, (region, mi_from, mi_to)).fetchall()

    return jsonify(rows_to_list(rows))


# ── API: heatmap (data coverage) ─────────────────────────────────────────────

@app.route('/api/heatmap')
def api_heatmap():
    """
    Data coverage matrix.
    Returns list of {dic_name, region, mi, status}
    status: 'complete' | 'partial' | 'missing'
    'partial' = bilateral-only entry (bil > 0, all AC charges = 0)
    """
    db = get_db()

    rows = db.execute("""
        SELECT dic_name, region,
               (year-2021)*12 + (month-1) AS mi,
               (ac_ubc+ac_bc+nc_re+nc_hvdc+rc+trx+bil) AS total,
               bil,
               (ac_ubc+ac_bc+nc_re+nc_hvdc+rc+trx) AS ac_total
        FROM charges
        ORDER BY region, dic_name, year, month
    """).fetchall()

    result = []
    for r in rows:
        if r['total'] == 0:
            status = 'missing'
        elif r['ac_total'] == 0 and r['bil'] > 0:
            status = 'partial'   # bilateral only
        else:
            status = 'complete'
        result.append({
            'dic_name': r['dic_name'],
            'region':   r['region'],
            'mi':       r['mi'],
            'status':   status,
        })

    return jsonify(result)


# ── API: all DIC monthly data (for overview heatmap-style) ───────────────────

@app.route('/api/all_dics')
def api_all_dics():
    """
    Every DIC's totals per month in one call.
    Used for the DIC trend comparison chart.
    Optional: ?mi_from=0&mi_to=65
    Returns: [{dic_name, region, mi, total, bil}, ...]
    """
    db      = get_db()
    mi_from = request.args.get('mi_from', 0,   type=int)
    mi_to   = request.args.get('mi_to',   999, type=int)

    rows = db.execute("""
        SELECT dic_name, region,
               (year-2021)*12 + (month-1) AS mi,
               (ac_ubc+ac_bc+nc_re+nc_hvdc+rc+trx+bil) AS total,
               bil
        FROM charges
        WHERE (year-2021)*12 + (month-1) BETWEEN ? AND ?
        ORDER BY region, dic_name, year, month
    """, (mi_from, mi_to)).fetchall()

    return jsonify(rows_to_list(rows))


# ── API: upload new PDF or Excel ──────────────────────────────────────────────

@app.route('/api/upload', methods=['POST'])
def api_upload():
    """
    Upload a new PDF or Excel file, parse it, insert into DB.
    Returns summary of what was inserted vs skipped.
    """
    import sys, tempfile
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'parser'))

    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    f    = request.files['file']
    name = f.filename.lower()

    # Save to temp file
    suffix = '.pdf' if name.endswith('.pdf') else '.xlsx'
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        f.save(tmp.name)
        tmp_path = tmp.name

    try:
        if name.endswith('.pdf'):
            from posoco_parser import parse_pdf_text
            records = parse_pdf_text(tmp_path, verbose=False)
        elif name.endswith(('.xlsx', '.csv')):
            records = _parse_excel(tmp_path)
        else:
            return jsonify({'error': 'Unsupported file type. Use .pdf or .xlsx'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        os.unlink(tmp_path)

    if not records:
        return jsonify({'error': 'No records parsed from file'}), 400

    # Detect conflicts before inserting
    db         = get_db()
    conflicts  = []
    clean      = []
    overwrite  = request.form.get('overwrite', 'false').lower() == 'true'

    for r in records:
        existing = db.execute(
            "SELECT 1 FROM charges WHERE dic_name=? AND year=? AND month=?",
            (r['name'], r['year'], r['month'])
        ).fetchone()
        if existing:
            conflicts.append(r)
        else:
            clean.append(r)

    if conflicts and not overwrite:
        # Return conflicts for user to review
        return jsonify({
            'status':    'conflicts',
            'conflicts': [{'name': r['name'], 'year': r['year'], 'month': r['month']}
                          for r in conflicts],
            'clean_count': len(clean),
        })

    # Insert records (clean + conflicts if overwrite=true)
    to_insert  = clean + (conflicts if overwrite else [])
    inserted   = skipped = errors = 0

    for r in to_insert:
        try:
            db.execute("""
                INSERT INTO charges
                    (dic_name, region, gnash, year, month,
                     ac_ubc, ac_bc, nc_re, nc_hvdc, rc, trx, bil)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(dic_name, year, month) DO UPDATE SET
                    region=excluded.region, gnash=excluded.gnash,
                    ac_ubc=excluded.ac_ubc, ac_bc=excluded.ac_bc,
                    nc_re=excluded.nc_re,   nc_hvdc=excluded.nc_hvdc,
                    rc=excluded.rc,         trx=excluded.trx,
                    bil=excluded.bil
            """, (r['name'], r.get('region','NR'), r.get('gnash',0),
                  r['year'], r['month'],
                  r.get('ac_ubc',0), r.get('ac_bc',0),
                  r.get('nc_re',0),  r.get('nc_hvdc',0),
                  r.get('rc',0),     r.get('trx',0),
                  r.get('bil',0)))
            db.execute("""
                INSERT INTO dics (name, region, gnash) VALUES (?,?,?)
                ON CONFLICT(name) DO UPDATE SET
                    region=excluded.region,
                    gnash=CASE WHEN excluded.gnash>0 THEN excluded.gnash ELSE dics.gnash END
            """, (r['name'], r.get('region','NR'), r.get('gnash',0)))
            inserted += 1
        except Exception as e:
            errors += 1

    db.commit()
    return jsonify({
        'status':   'ok',
        'inserted': inserted,
        'skipped':  skipped,
        'errors':   errors,
    })


def _parse_excel(path):
    """Parse an ISTS upload template Excel file into records."""
    import openpyxl
    wb   = openpyxl.load_workbook(path)
    ws   = wb.active
    rows = []
    MONTH_MAP = {
        "jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
        "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12,
    }
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row[0]: continue
        try:
            # Month label like "Jan'25"
            label = str(row[3]).strip()
            mon   = MONTH_MAP[label[:3].lower()]
            yr    = 2000 + int(label[4:6])
            rows.append({
                'name':    str(row[0]).strip(),
                'region':  str(row[1]).strip(),
                'gnash':   int(row[2] or 0),
                'year':    yr, 'month': mon,
                'ac_ubc':  int(row[4]  or 0),
                'ac_bc':   int(row[5]  or 0),
                'nc_re':   int(row[6]  or 0),
                'nc_hvdc': int(row[7]  or 0),
                'rc':      int(row[8]  or 0),
                'trx':     int(row[9]  or 0),
                'bil':     int(row[10] or 0),
            })
        except Exception:
            continue
    return rows


# ── Run ───────────────────────────────────────────────────────────────────────


@app.route('/api/raw_data')
def api_raw_data():
    """
    Returns everything the dashboard needs in one call:
    - ALL_MONTH_LABELS: array of label strings from first to last month in DB
    - RAW: array of DIC objects, each with m0..mN slots matching the labels index
    
    Slot format: {ac_ubc, ac_bc, nc_re, nc_hvdc, rc, trx, bil}
    This matches the existing dashboard RAW array format exactly.
    """
    db = get_db()
    
    # Get month range from DB
    months_in_db = db.execute(
        "SELECT DISTINCT year, month FROM charges ORDER BY year, month"
    ).fetchall()
    
    if not months_in_db:
        return jsonify({'monthLabels': [], 'raw': []})
    
    # Build label array from first to last month in DB
    # Fill every month in range (even ones not in DB, so slider works smoothly)
    first = months_in_db[0]
    last  = months_in_db[-1]
    first_mi = (first['year'] - 2021) * 12 + (first['month'] - 1)
    last_mi  = (last['year']  - 2021) * 12 + (last['month']  - 1)
    
    month_names = ['Jan','Feb','Mar','Apr','May','Jun',
                   'Jul','Aug','Sep','Oct','Nov','Dec']
    
    labels = []
    for mi in range(first_mi, last_mi + 1):
        yr  = 2021 + mi // 12
        mon = mi % 12 + 1
        labels.append(f"{month_names[mon-1]}\'{str(yr)[2:]}")
    
    n_slots = len(labels)  # number of month slots in our label array
    
    # Get all DICs
    dics = db.execute(
        "SELECT name, region, gnash FROM dics ORDER BY region, name"
    ).fetchall()
    
    # Get custom columns and include them in the query
    custom_cols = get_custom_columns(db)
    all_cols = 'ac_ubc, ac_bc, nc_re, nc_hvdc, rc, trx, bil'
    if custom_cols:
        all_cols += ', ' + ', '.join(custom_cols)

    # Get all charges in one query
    charges = db.execute(f"""
        SELECT dic_name, year, month, {all_cols}
        FROM charges
        ORDER BY dic_name, year, month
    """).fetchall()
    
    # Index charges by (dic_name, mi)
    charge_index = {}
    for c in charges:
        mi = (c['year'] - 2021) * 12 + (c['month'] - 1)
        # Offset mi to be relative to first_mi (so m0 = first month in DB)
        slot = mi - first_mi
        if 0 <= slot < n_slots:
            charge_index[(c['dic_name'], slot)] = {
                'ac_ubc':  c['ac_ubc'],
                'ac_bc':   c['ac_bc'],
                'nc_re':   c['nc_re'],
                'nc_hvdc': c['nc_hvdc'],
                'rc':      c['rc'],
                'trx':     c['trx'],
                'bil':     c['bil'],
            }
    
    # Build RAW array
    base_keys = ['ac_ubc','ac_bc','nc_re','nc_hvdc','rc','trx','bil'] + custom_cols
    empty_slot = {k: 0 for k in base_keys}
    raw = []
    for dic in dics:
        obj = {
            'name':   dic['name'],
            'region': dic['region'],
            'gnash':  dic['gnash'] or 0,
        }
        for slot in range(n_slots):
            raw_slot = charge_index.get((dic['name'], slot))
            if raw_slot:
                obj[f'm{slot}'] = {k: raw_slot.get(k, 0) for k in base_keys}
            else:
                obj[f'm{slot}'] = dict(empty_slot)
        raw.append(obj)
    
    return jsonify({
        'monthLabels': labels,
        'firstMi': first_mi,
        'raw': raw,
        'customCols': custom_cols,   # extra columns beyond the 7 built-ins
        'allCols': ['ac_ubc','ac_bc','nc_re','nc_hvdc','rc','trx','bil'] + custom_cols,
    })


# ── Dynamic column management ─────────────────────────────────────────────────

# These are the fixed built-in columns — never modified
BUILTIN_COLS = {'ac_ubc', 'ac_bc', 'nc_re', 'nc_hvdc', 'rc', 'trx', 'bil'}

def get_custom_columns(db):
    """Return list of custom columns added beyond the built-ins."""
    cols = db.execute("PRAGMA table_info(charges)").fetchall()
    fixed = {'id','dic_name','region','gnash','year','month'} | BUILTIN_COLS
    return [c['name'] for c in cols if c['name'] not in fixed]


@app.route('/api/columns')
def api_columns():
    """Return all charge component columns (built-in + custom)."""
    db = get_db()
    custom = get_custom_columns(db)
    return jsonify({
        'builtin': sorted(BUILTIN_COLS),
        'custom':  custom,
        'all':     ['ac_ubc','ac_bc','nc_re','nc_hvdc','rc','trx','bil'] + custom,
    })


@app.route('/api/add_column', methods=['POST'])
def api_add_column():
    """
    Add a new numeric column to the charges table.
    Body: { "column": "rldc_charges", "label": "RLDC Charges" }
    """
    data = request.get_json()
    col  = data.get('column', '').strip().lower()
    label = data.get('label', '').strip()

    # Validate column name — alphanumeric + underscores only
    import re
    if not col or not re.match(r'^[a-z][a-z0-9_]{1,29}$', col):
        return jsonify({'error': 'Invalid column name. Use lowercase letters, numbers, underscores (2-30 chars).'}), 400

    if not label:
        label = col.replace('_', ' ').title()

    db = get_db()

    # Check if already exists
    existing = [c['name'] for c in db.execute("PRAGMA table_info(charges)").fetchall()]
    if col in existing:
        return jsonify({'error': f"Column '{col}' already exists."}), 400

    # Add column to charges table (default 0)
    try:
        db.execute(f"ALTER TABLE charges ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0")
        db.commit()
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    return jsonify({'ok': True, 'column': col, 'label': label})


@app.route('/api/set_value', methods=['POST'])
def api_set_value():
    """
    Set a value for a specific DIC + month + column.
    Body: { "dic_name": "Delhi", "year": 2025, "month": 1, "column": "rldc_charges", "value": 12345678 }
    """
    data    = request.get_json()
    dic     = data.get('dic_name')
    year    = data.get('year')
    month   = data.get('month')
    col     = data.get('column', '').strip().lower()
    value   = data.get('value', 0)

    import re
    if not re.match(r'^[a-z][a-z0-9_]{1,29}$', col):
        return jsonify({'error': 'Invalid column name'}), 400

    db = get_db()
    existing = [c['name'] for c in db.execute("PRAGMA table_info(charges)").fetchall()]
    if col not in existing or col in {'id','dic_name','region','gnash','year','month'}:
        return jsonify({'error': f"Column '{col}' does not exist or is protected"}), 400

    try:
        db.execute(
            f"UPDATE charges SET {col}=? WHERE dic_name=? AND year=? AND month=?",
            (int(value), dic, int(year), int(month))
        )
        db.commit()
        rows = db.execute("SELECT changes()").fetchone()[0]
        return jsonify({'ok': True, 'rows_updated': rows})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.after_request
def add_headers(r):
    r.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    r.headers['Pragma'] = 'no-cache'
    return r

@app.errorhandler(Exception)
def handle_exception(e):
    import traceback
    app.logger.error(traceback.format_exc())
    return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/save_rows', methods=['POST'])
def api_save_rows():
    """
    Persist pre-parsed rows (from client-side Excel/manual entry) to SQLite.
    Body: { "rows": [...], "overwrite": true/false }
    Each row: { dic_name, region, gnash, year, month,
                ac_ubc, ac_bc, nc_re, nc_hvdc, rc, trx, bil }
    """
    data      = request.get_json()
    rows      = data.get('rows', [])
    overwrite = data.get('overwrite', True)

    if not rows:
        return jsonify({'error': 'No rows provided'}), 400

    db = get_db()
    inserted = skipped = errors = 0

    for r in rows:
        try:
            if overwrite:
                db.execute("""
                    INSERT INTO charges
                        (dic_name, region, gnash, year, month,
                         ac_ubc, ac_bc, nc_re, nc_hvdc, rc, trx, bil)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(dic_name, year, month) DO UPDATE SET
                        region=excluded.region,  gnash=excluded.gnash,
                        ac_ubc=excluded.ac_ubc,  ac_bc=excluded.ac_bc,
                        nc_re=excluded.nc_re,    nc_hvdc=excluded.nc_hvdc,
                        rc=excluded.rc,          trx=excluded.trx,
                        bil=excluded.bil
                """, (
                    r.get('dicName') or r.get('dic_name'),
                    r.get('region', 'NR'),
                    int(r.get('gnash', 0)),
                    int(r['year']), int(r['month']),
                    int(r.get('ac_ubc',  0)), int(r.get('ac_bc',   0)),
                    int(r.get('nc_re',   0)), int(r.get('nc_hvdc',  0)),
                    int(r.get('rc',      0)), int(r.get('trx', 0) or r.get('tc', 0)),
                    int(r.get('bil',     0)),
                ))
            else:
                db.execute("""
                    INSERT OR IGNORE INTO charges
                        (dic_name, region, gnash, year, month,
                         ac_ubc, ac_bc, nc_re, nc_hvdc, rc, trx, bil)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    r.get('dicName') or r.get('dic_name'),
                    r.get('region', 'NR'),
                    int(r.get('gnash', 0)),
                    int(r['year']), int(r['month']),
                    int(r.get('ac_ubc',  0)), int(r.get('ac_bc',   0)),
                    int(r.get('nc_re',   0)), int(r.get('nc_hvdc',  0)),
                    int(r.get('rc',      0)), int(r.get('trx', 0) or r.get('tc', 0)),
                    int(r.get('bil',     0)),
                ))

            changed = db.execute('SELECT changes()').fetchone()[0]
            if changed:
                inserted += 1
                dic_name = r.get('dicName') or r.get('dic_name')
                db.execute("""
                    INSERT INTO dics (name, region, gnash) VALUES (?,?,?)
                    ON CONFLICT(name) DO UPDATE SET
                        region=excluded.region,
                        gnash=CASE WHEN excluded.gnash>0
                                   THEN excluded.gnash ELSE dics.gnash END
                """, (dic_name, r.get('region','NR'), int(r.get('gnash', 0))))
            else:
                skipped += 1

        except Exception as e:
            errors += 1
            app.logger.error(f"save_rows error on row {r}: {e}")

    db.commit()
    return jsonify({
        'status':   'ok',
        'inserted': inserted,
        'skipped':  skipped,
        'errors':   errors,
    })

if __name__ == '__main__':
    print(f"\n  ISTS Dashboard")
    print(f"  Database : {DB_PATH}")
    print(f"  Open     : http://localhost:5000\n")
    app.run(debug=False, port=5000, use_reloader=False, threaded=True)
