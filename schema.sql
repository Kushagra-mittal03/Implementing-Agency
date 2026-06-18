-- ISTS Transmission Charges Database Schema
-- Run once to initialise: sqlite3 ists.db < schema.sql

-- One row per DIC per month. UNIQUE on (dic_name, year, month) prevents duplicates.
CREATE TABLE IF NOT EXISTS charges (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    dic_name  TEXT    NOT NULL,
    region    TEXT    NOT NULL CHECK(region IN ('NR','WR','SR','ER','NER')),
    gnash     INTEGER NOT NULL DEFAULT 0,
    year      INTEGER NOT NULL,
    month     INTEGER NOT NULL CHECK(month BETWEEN 1 AND 12),
    ac_ubc    INTEGER NOT NULL DEFAULT 0,   -- Usage Based AC system charges
    ac_bc     INTEGER NOT NULL DEFAULT 0,   -- Balance AC system charges
    nc_re     INTEGER NOT NULL DEFAULT 0,   -- National Component - RE
    nc_hvdc   INTEGER NOT NULL DEFAULT 0,   -- National Component - HVDC
    rc        INTEGER NOT NULL DEFAULT 0,   -- Regional Component
    trx       INTEGER NOT NULL DEFAULT 0,   -- Transformers component (TC)
    bil       INTEGER NOT NULL DEFAULT 0,   -- Bilateral charges
    UNIQUE(dic_name, year, month)
);

-- DIC master table - one row per unique DIC name
CREATE TABLE IF NOT EXISTS dics (
    name      TEXT    PRIMARY KEY,
    region    TEXT    NOT NULL CHECK(region IN ('NR','WR','SR','ER','NER')),
    gnash     INTEGER NOT NULL DEFAULT 0    -- latest known GNAsh (MW)
);

-- Useful indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_charges_dic   ON charges(dic_name);
CREATE INDEX IF NOT EXISTS idx_charges_month ON charges(year, month);
CREATE INDEX IF NOT EXISTS idx_charges_region ON charges(region);
CREATE INDEX IF NOT EXISTS idx_charges_dic_month ON charges(dic_name, year, month);

-- Handy view: total charges per month across all DICs
CREATE VIEW IF NOT EXISTS monthly_totals AS
SELECT
    year, month,
    SUM(ac_ubc)                               AS ac_ubc,
    SUM(ac_bc)                                AS ac_bc,
    SUM(nc_re)                                AS nc_re,
    SUM(nc_hvdc)                              AS nc_hvdc,
    SUM(rc)                                   AS rc,
    SUM(trx)                                  AS trx,
    SUM(bil)                                  AS bil,
    SUM(ac_ubc+ac_bc+nc_re+nc_hvdc+rc+trx+bil) AS total
FROM charges
GROUP BY year, month
ORDER BY year, month;

-- Handy view: total charges per DIC across all months
CREATE VIEW IF NOT EXISTS dic_totals AS
SELECT
    dic_name,
    region,
    COUNT(*)                                   AS months_present,
    SUM(ac_ubc+ac_bc+nc_re+nc_hvdc+rc+trx+bil) AS lifetime_total,
    SUM(bil)                                   AS lifetime_bilateral,
    MAX(year*100+month)                        AS latest_ym
FROM charges
GROUP BY dic_name, region
ORDER BY lifetime_total DESC;
