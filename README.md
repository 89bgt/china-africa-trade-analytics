# China–Africa Trade Flows Analytics

Which Chinese product categories are growing fastest in French-speaking African markets?

This project tracks **China's exports to Morocco, Senegal and Côte d'Ivoire by HS 2-digit product
chapter, 2015–2025**, and ranks the chapters by compound annual growth. It is a small, end-to-end
analytics pipeline (API → BigQuery → dbt → Looker Studio) and the data foundation for a planned
master's thesis on data-driven risk in China–Francophone Africa supply chains.

![Dashboard overview](docs/img/dashboard_overview.png)
<!-- TODO: add screenshot after building the Looker Studio dashboard -->

## Questions

1. How have China's exports to each of the three markets evolved since 2015?
2. Which product chapters grew fastest (CAGR 2015–2025), excluding negligible bases?
3. How concentrated is each market's import basket from China, and is it shifting?

## Data source

[UN Comtrade](https://comtradeplus.un.org/) public API (`/public/v1/preview`, no API key needed),
annual data, HS classification, China (M49 code 156) as reporter, flow = exports.

| Partner | M49 code |
|---|---|
| Morocco | 504 |
| Senegal | 686 |
| Côte d'Ivoire | 384 |

About 2,800 rows: 3 partners × 11 years × 76–94 chapters with recorded trade.

## Architecture

```
UN Comtrade API ──► ingest/comtrade_to_bq.py ──► BigQuery  comtrade_raw.comtrade_records
                     (extract, then append)        raw JSON + extracted_at, append-only
                                                       │
                     dbt ─────────────────────────────┘
                       staging       stg_comtrade__exports        parse JSON, latest extraction
                                                                  per partner-year, typed
                       intermediate  int_exports__chapter_year    dense partner × chapter × year grid
                       marts         fct_exports_yearly           values, YoY, share, rank
                                     mart_chapter_growth          start/end value, CAGR
                                     mart_top_growing_chapters    top 10 by CAGR per partner
                                     mart_partner_concentration   HHI, top-3 share per partner-year
                       seeds         hs_chapters, partners        names, HS sections
                                                       │
                                               Looker Studio dashboard
```

## Method

- **Raw layer (ELT):** BigQuery is the record of the raw data. Each API record is stored untouched
  as JSON with `extracted_at` and the request parameters. Every run *appends* instead of
  overwriting, so Comtrade's revisions to past years are kept. Reloading the same extraction is
  skipped, so re-runs stay idempotent. dbt parses the JSON and uses the latest extraction. The local
  `data/raw/` folder is only a developer cache for reloading without calling the API. (Cloud
  Storage would be the usual landing zone, but it needs billing; this setup runs in the free
  BigQuery sandbox.)
- **Values** are Comtrade's `primaryValue` (FOB, current USD), as reported by China.
- **Dense grid:** a chapter with no record in a year is set to 0, so YoY and CAGR aren't skewed by gaps.
- **CAGR** = (value 2025 / value 2015)^(1/10) − 1, per partner and for the three partners combined.
- **Materiality filter:** a chapter is only ranked if it exceeded **USD 1M in 2015**
  (`min_base_value_usd` var), so tiny bases don't produce misleading 1000%+ growth rates.
- **Concentration** = Herfindahl-Hirschman index over chapter shares of each partner's yearly total
  (0–10,000), plus the share of the top 3 chapters.
- Window, threshold and top-N are dbt vars in `dbt/dbt_project.yml`. `dbt build` runs 19 data tests
  (uniqueness of grain, not-null, referential integrity to the seeds).

## Key findings (2015 → 2025)

1. **All three markets grew fast, Côte d'Ivoire fastest.** China's exports rose from USD 1.6bn to
   6.1bn to Côte d'Ivoire (**+14.7%/yr**), 2.9bn to 9.9bn to Morocco (**+13.0%/yr**) and 2.2bn to 5.5bn
   to Senegal (**+9.5%/yr**). 2025 alone added +47% (Côte d'Ivoire) and +28% (Morocco), so the
   endpoint flatters the CAGR. Whether this reflects China redirecting exports in 2025 is a hypothesis
   worth testing, not a conclusion.
2. **Capital goods drive the volume.** Machinery (HS 84), electrical equipment (85) and vehicles (87)
   are the top three chapters by absolute growth in every market, except Senegal, where iron and steel
   (72) is third. Machinery alone added USD 2.6bn across the three.
3. **Morocco's vehicles chapter is the standout.** HS 87 went from USD 95M to 1.23bn (**+29%/yr**),
   alongside inorganic chemicals (28, +30%/yr) and organic chemicals (29, +22%/yr). This is consistent
   with Chinese supply into Morocco's automotive and battery-materials industries.
4. **Consumer niches growing 20–30%/yr from a USD 1M+ base:**
   - Côte d'Ivoire: knitted apparel (61: USD 10M → 153M) and coffee/tea/spices (09).
   - Senegal: fabrics (58: USD 10M → 119M) and toys and sports goods (95).
   - All three markets: cosmetics and perfumery (33).

   These are candidate niches for China–West Africa sourcing.
5. **Baskets are concentrating in Morocco and Côte d'Ivoire.** Chapter-level HHI rose from 610 to 813
   (Morocco) and 472 to 748 (Côte d'Ivoire). Their top-3 chapters went from 35% to 45% and from 26% to
   40% of the total. Senegal stayed broadly stable (HHI 489 → 533). Rising dependence on Chinese
   capital goods is a supply-chain risk angle for the thesis.

## Limitations

- **Reporter-side data only.** China's export figures can differ from partners' import figures
  (CIF vs FOB, transit via third countries, timing). A mirror comparison is a natural next step.
- **HS revisions:** Comtrade reports 2015–16 in HS2012, 2017–21 in HS2017 and 2022+ in HS2022.
  The impact is small at the 2-digit level but not zero.
- **2025** is the latest release and may still be revised. Re-running the ingestion appends the
  new figures, and older extractions stay in the raw table for comparison.
- Current USD, not adjusted for inflation or exchange rates.
- Endpoint CAGR is sensitive to unusual start or end years. Use the yearly series for context.

## Run it

Prerequisites: Python 3.10+, a GCP project with BigQuery (the free sandbox works), and the
Google Cloud CLI logged in with Application Default Credentials. See [docs/gcp_setup.md](docs/gcp_setup.md).

```bash
python -m venv .venv && .venv\Scripts\activate      # Windows (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt

# optional: point at your own project (defaults: china-africa-trade, EU)
set GCP_PROJECT_ID=your-project-id

python ingest/comtrade_to_bq.py                     # extract (~33 API calls, ~2 min) + append to BigQuery
# --dry-run: extract to data/raw/ only    --from-cache: load data/raw/ without calling the API

cd dbt
dbt build --profiles-dir .                          # seeds + models + tests
```

Dashboard design and queries: [docs/dashboard.md](docs/dashboard.md).

## Repository layout

```
ingest/comtrade_to_bq.py   API extraction + append-only BigQuery load
dbt/                       dbt project (models, seeds, tests, project-local profile)
data/raw/                  local developer cache of the last extraction (git-ignored)
docs/                      setup guide, dashboard spec, screenshots
```

## Tech

Python · UN Comtrade API · Google BigQuery · dbt · Looker Studio
