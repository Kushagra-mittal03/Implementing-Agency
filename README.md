# ISTS Transmission Charges Dashboard

Internal dashboard for analysing Grid India ISTS charges billed to Designated ISTS Customers (DICs) across all five regional grids — NR, WR, SR, ER, and NER. Covers January 2021 onwards.

---

## Starting the Dashboard

1. Open Command Prompt and navigate to the dashboard folder
2. Run:
   ```
   python app.py
   ```
3. Open your browser and go to: **http://localhost:5000**

Keep the Command Prompt window open while using the dashboard. Closing it stops the server.

---

## Folder Structure

```
dashboard\
├── app.py                  ← Run this to start the dashboard
├── db\
│   └── ists.db             ← All charge data (do not move or rename)
├── parser\
│   └── excel_parser.py
├── scripts\
│   ├── load_data.py
│   ├── merge_duplicates.py
│   └── verify_db.py
├── data\                   ← Place Grid India Excel files here
└── templates\
    └── index.html          ← The dashboard interface
```

---

## Adding New Monthly Data

**Via the dashboard (easiest):**
1. Click the **+ Add Data** tab
2. Drag the Grid India monthly billing Excel file onto the upload area
3. Click **Confirm** — data is saved immediately and all charts update

**Via command line:**
```
python scripts\load_data.py data\filename.xlsx
```
Then restart the dashboard to see updated charts.

---

## Dashboard Tabs

| Tab | What it shows |
|---|---|
| Overview | Total charges, regional breakdown, component split, top DICs, monthly trends |
| DIC Breakdown | Detailed analysis for a specific DIC — filter by region and entity |
| Bilateral Charges | Entities with bilateral charges only (railways, NHPC, etc.) |
| Monthly Table | Full tabular view of all DICs for a selected billing month — downloadable |
| + Add Data | Upload new monthly Excel files or enter data manually |
| ▦ Coverage | Heatmap showing data availability across all months and DICs |
| ☰ Audit | Log of all data additions |

---

## Downloading Data

Every tab has **CSV** and **Excel** download buttons. Downloads reflect whatever filters (region, month range, entity) are currently applied.

---

## Common Issues

| Problem | Fix |
|---|---|
| Stuck on "Loading data" | Make sure `python app.py` is running and open `http://localhost:5000` — do not open the HTML file directly |
| Port already in use | Change `port=5000` to `port=5001` in `app.py` and visit `http://localhost:5001` |
| Upload says "No records parsed" | File must be the official Grid India monthly billing Excel |
| Data disappears after reload | Pause OneDrive sync while the dashboard is running |

---

## Online Access (PythonAnywhere)

The dashboard is also hosted at:
**https://implementingagency.pythonanywhere.com**

No setup needed — open the link in any browser.

---

*Developed at NLDC. Data sourced from Grid India ISTS monthly billing statements.*
