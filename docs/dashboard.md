# Looker Studio dashboard

Built in [Looker Studio](https://lookerstudio.google.com) (free) on the dbt marts in BigQuery
project `china-africa-trade`, dataset `analytics_marts`. Sign in with the same personal Google account.

## Data sources

Add each table with **Create → Data source → BigQuery → china-africa-trade → analytics_marts**:

| Data source | Table | Used for |
|---|---|---|
| Yearly exports | `fct_exports_yearly` | page 1 |
| Chapter growth | `mart_chapter_growth` | page 2 |
| Top growing | `mart_top_growing_chapters` | page 2 |
| Concentration | `mart_partner_concentration` | pages 1, 3 |

In each data source, change `year` to type **Date → Year**, and set `cagr`, `yoy_growth`,
`share_*` and `top3_share` to **Percent**.

Theme: one colour per partner, used on every page. Suggested: Morocco red `#C1272D`,
Senegal green `#00853F`, Côte d'Ivoire orange `#F77F00`, All three partners grey `#6B7280`.

## Page 1: Overview

- **Controls:** partner (drop-down on `partner_name`), year range.
- **Scorecards (Concentration, year = 2025):** `total_exports_usd` per partner, with comparison
  to 2015 shown as % change.
- **Line chart (Concentration):** dimension `year`, breakdown `partner_name`, metric `total_exports_usd`.
- **Stacked area (Yearly exports):** dimension `year`, breakdown `section_name`, metric
  `SUM(export_value_usd)`, 100% stacked. Shows how the basket shifts across HS sections.

## Page 2: Growth

- **Control:** partner drop-down (`partner_name`, include "All three partners").
- **Bar chart (Top growing):** dimension `chapter_name`, metric `cagr`, sorted by `growth_rank`
  ascending. Tooltip: `value_start_usd`, `value_end_usd`.
- **Bubble chart (Chapter growth, filter `is_material_base = true`):** x = `value_end_usd`
  (log scale), y = `cagr`, size = `abs_change_usd`, dimension `chapter_name`. Top-right = large
  *and* fast-growing chapters.
- **Table (Chapter growth):** `hs_chapter`, `chapter_name`, `value_start_usd`, `value_end_usd`,
  `abs_change_usd`, `cagr`, with a heatmap on `cagr`.

## Page 3: Concentration and risk

- **Line chart (Concentration):** `year` × `hhi` by `partner_name`.
- **Line chart (Concentration):** `year` × `top3_share` by `partner_name`.
- **Text box:** HHI > 1,500 is usually read as "moderately concentrated". These baskets are below
  that but rising in Morocco and Côte d'Ivoire.

## Screenshots

Export each page (**File → Download → PNG**, or a screen capture) to `docs/img/`:
`dashboard_overview.png`, `dashboard_growth.png`, `dashboard_concentration.png`.
The README already references `docs/img/dashboard_overview.png`. Add the public dashboard link
there too (**Share → Manage access → Anyone with the link can view**).

## Example query (BigQuery console)

```sql
-- Large and fast: chapters above USD 50M in 2025 growing >15%/yr
select partner_name, hs_chapter, chapter_name,
       round(value_end_usd / 1e6) as value_2025_musd,
       round(cagr * 100, 1)       as cagr_pct
from `china-africa-trade.analytics_marts.mart_chapter_growth`
where value_end_usd >= 50e6 and cagr > 0.15
order by partner_name, cagr desc;
```
