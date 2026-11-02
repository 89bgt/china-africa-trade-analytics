-- Parses the raw Comtrade JSON and keeps only the latest extraction per partner-year
-- (the raw table is append-only, so earlier extractions = earlier Comtrade revisions).

with source as (

    select * from {{ source('comtrade_raw', 'comtrade_records') }}

),

latest_extraction as (

    select *
    from source
    where true  -- BigQuery requires a WHERE/GROUP BY alongside QUALIFY
    qualify extracted_at = max(extracted_at) over (partition by partner_code, period)

)

select
    int64(record.refYear)                       as year,
    int64(record.reporterCode)                  as reporter_code,
    int64(record.partnerCode)                   as partner_code,
    string(record.cmdCode)                      as hs_chapter,
    string(record.classificationCode)           as hs_revision,
    cast(float64(record.primaryValue) as numeric)
                                                as export_value_usd,
    nullif(lax_float64(record.netWgt), 0)       as net_weight_kg,
    lax_bool(record.isReported)                 as is_reported,
    extracted_at,
    loaded_at

from latest_extraction
-- Totals only: exports, no second partner, all customs procedures, all transport modes.
where string(record.flowCode) = 'X'
  and int64(record.partner2Code) = 0
  and string(record.customsCode) = 'C00'
  and int64(record.motCode) = 0
