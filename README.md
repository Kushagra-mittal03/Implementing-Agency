# ISTS Transmission Charges Dashboard

An internal web dashboard for analysing Inter-State Transmission System (ISTS)
charges billed by POSOCO/NLDC to Designated ISTS Customers (DICs) across all
five regional grids of India.

Built with **Python / Flask** (backend) and **plain HTML + Chart.js** (frontend).
All data is stored in a local **SQLite** database. No internet connection is
required once set up.

---

## What It Shows

- **₹2,43,305 Cr** of transmission charges across **66 months** (Jan 2021 – Jun 2026)
- **135 unique DICs** across NR, WR, SR, ER and NER regions
- Charge breakdown by component: AC-UBC, AC-BC, NC-RE, NC-HVDC, RC, Transformers, Bilateral
- Month-by-month trends, region comparisons, and data coverage heatmap

---

## Folder Structure

Place every file exactly as shown below. The names and locations matter —
Flask resolves the database and templates relative to `app.py`.

```
dashboard\
│
├── app.py                      ← Flask API server  (run this to start)
│
├── db\
│   ├── schema.sql              ← Table definitions (run once automatically)
│   └── ists.db                 ← SQLite database   (created by load_data.py)
│
├── parser\
│   └── excel_parser.py         ← Reads POSOCO Excel workbooks
│
├── scripts\
│   ├── load_data.py            ← Loads Excel files into ists.db
│   ├── merge_duplicates.py     ← Fixes duplicate DIC names in the database
│   ├── verify_db.py            ← Quick health-check of the database
│   └── diagnose.py             ← Tests whether the Flask API is responding
│
├── data\                       ← Put your Excel workbooks here
│   └── 2025_combined.xlsx      ← (example — any POSOCO billing workbook)
│
└── templates\
    └── index.html              ← The dashboard (served by Flask at localhost:5000)
```

---

## Requirements

| Software | Version | Notes |
|---|---|---|
| Python | 3.9 or later | Download from python.org — tick "Add to PATH" during install |
| Flask | any | Installed via pip |
| pandas | any | Installed via pip |
| openpyxl | any | Installed via pip |

No other software is needed. SQLite is built into Python.

---

## First-Time Setup

Open **Command Prompt** and run these commands in order.

### Step 1 — Install Python packages

```cmd
pip install flask pandas openpyxl
```

If you are behind a corporate proxy or get an SSL error, use:

```cmd
pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org flask pandas openpyxl
```

### Step 2 — Navigate to your project folder

```cmd
cd C:\Users\kush3\OneDrive\Documents\NLDC\dashboard
```

### Step 3 — Load your Excel data into the database

```cmd
python scripts\load_data.py data\2025_combined.xlsx
```

To load multiple files at once, point it at the folder:

```cmd
python scripts\load_data.py data\
```

Expected output:
```
  Loading 1 file(s)...

  File: 2025_combined.xlsx
  Month          DICs   Total (Cr)
  -------------- -----  -----------
  January 2025      59        3774
  February 2025     60        3906
  ...

  ✅ Inserted 715  |  Skipped 0  |  Errors 0
```

### Step 4 — Fix duplicate DIC names

Some older data loaded from PDFs contains DIC names with embedded line-breaks
(e.g. `Adani Power\nLimited` instead of `Adani Power Limited`). This script
merges all 120 known variants into their canonical forms and also consolidates
historical name changes such as Essar Steel → ArcelorMittal.

```cmd
python scripts\merge_duplicates.py
```

Expected output:
```
  Before: 237 unique DICs, 4172 records
  After:  135 unique DICs, 4162 records
  Merged 120 duplicate name variants into canonical forms.
```

Only needs to be run **once** after the initial data load, or again after
loading historical data that was originally parsed from PDFs.

### Step 5 — Start the server

```cmd
python app.py
```

Expected output:
```
 * Running on http://127.0.0.1:5000
 * Running on http://0.0.0.0:5000
```

Leave this window open. The server runs until you close it or press `Ctrl + C`.

### Step 6 — Open the dashboard

Open your browser and go to:

```
http://localhost:5000
```

> **Important:** always open the dashboard via `http://localhost:5000`.
> Do not open `index.html` directly as a file — the charts will not load
> because all data comes from the Flask API.

---

## Adding New Data

### From an Excel workbook (recommended)

Drop the new workbook into the `data\` folder and run:

```cmd
python scripts\load_data.py data\2026_combined.xlsx
```

The script skips any month/DIC combination already in the database, so
running it multiple times is safe.

### From within the dashboard

Click the **+ Add Data** tab in the dashboard. You can:

- **Upload an Excel file** directly in the browser — the file is parsed
  client-side, merged into the charts, and saved to the database automatically.
- **Enter values manually** — choose a DIC, month, and type in each charge
  component. Data is saved to the database immediately.

### Adding a new charge component column

Click **+ Add Component** in the toggle bar above the charts. Enter a column
ID (e.g. `rldc_charges`) and a display label (e.g. `RLDC Charges`). The column
is added to the database and appears across all charts. Use the
**Enter Values** modal to input data per DIC per month.

---

## Making It Accessible to Others (Local Network)

To share the dashboard with colleagues on the same office WiFi:

1. Find your machine's IP address:
   ```cmd
   ipconfig
   ```
   Look for `IPv4 Address` — e.g. `192.168.1.45`

2. The server already listens on `0.0.0.0` so no change is needed.

3. Ask your colleague to open:
   ```
   http://192.168.1.45:5000
   ```

Your machine must stay on and `app.py` must be running.

---

## Troubleshooting

### Dashboard stuck on "Loading data…"

- Make sure you opened `http://localhost:5000` and not the HTML file directly.
- Check the terminal where `app.py` is running for any Python error.
- Run `python diagnose.py` in a second terminal to test the API directly.

### 500 error or "Database not found"

- Confirm `ists.db` exists at `db\ists.db` inside the dashboard folder.
- If the `db\` folder is on OneDrive, **pause OneDrive sync** before running Flask — OneDrive can lock SQLite files.
- Run `python scripts\load_data.py data\2025_combined.xlsx` to create the database.

### "Module not found: flask" or "Module not found: pandas"

```cmd
pip install flask pandas openpyxl
```

### Port 5000 already in use

Change the port in the last line of `app.py`:
```python
app.run(debug=False, port=5001, use_reloader=False, threaded=True)
```
Then open `http://localhost:5001`.

### pip install fails (SSL error)

```cmd
pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org flask pandas openpyxl
```

---

## Dashboard Tabs

| Tab | What it shows |
|---|---|
| **Overview** | Total charges, metric cards, region bar chart, component donut, top 20 DICs |
| **DIC Breakdown** | Per-DIC monthly chart, component pie, summary stats |
| **Monthly Trends** | Region trend lines, stacked area chart, component split |
| **Data Coverage** | Heatmap showing which DICs have data for which months |
| **+ Add Data** | Upload Excel files or enter charges manually |
| **Audit Trail** | Log of all data additions with timestamps |

---

## Script Reference

| Script | Command | What it does |
|---|---|---|
| `load_data.py` | `python scripts\load_data.py data\file.xlsx` | Parse Excel workbook and insert into database |
| `merge_duplicates.py` | `python scripts\merge_duplicates.py` | Fix 120 known duplicate DIC name variants |
| `verify_db.py` | `python scripts\verify_db.py` | Print database stats and flag anomalies |
| `diagnose.py` | `python diagnose.py` | Test Flask API endpoints directly |

---

## Data Source

Excel workbooks are the monthly ISTS billing statements published by POSOCO.
Each workbook contains one sheet per month. The parser handles:

- Indian number format strings (`17,52,25,228`)
- Bilateral-only DICs (Northern Railways, North Central Railways)
- Newlines embedded in DIC names from older PDF-converted files

---

## File Descriptions

| File | Purpose |
|---|---|
| `app.py` | Flask web server. Serves the dashboard and all `/api/*` endpoints. |
| `templates/index.html` | The complete dashboard UI — HTML, CSS, and JavaScript in one file. |
| `parser/excel_parser.py` | Parses POSOCO ISTS Excel workbooks into Python records. |
| `scripts/load_data.py` | Loads parsed records into `ists.db`. Skips duplicates. |
| `scripts/merge_duplicates.py` | 120 merge operations to consolidate duplicate DIC names. |
| `scripts/verify_db.py` | Prints record counts, date range, and region breakdown. |
| `scripts/diagnose.py` | Calls each Flask API endpoint and reports status. |
| `db/schema.sql` | SQL definitions for the `charges`, `dics` tables and views. |
| `db/ists.db` | SQLite database. Created automatically on first run. |

---

*Developed for NLDC internal use. Data sourced from POSOCO ISTS billing statements.*
