with source as (

    select * from {{ source('comtrade_raw', 'comtrade_exports') }}

)

select
    cast(refYear as int64)                          as year,
    cast(reporterCode as int64)                     as reporter_code,
    cast(partnerCode as int64)                      as partner_code,
    cmdCode                                         as hs_chapter,
    classificationCode                              as hs_revision,
    cast(primaryValue as numeric)                   as export_value_usd,
    nullif(netWgt, 0)                               as net_weight_kg,
    isReported                                      as is_reported,
    _ingested_at                                    as ingested_at

from source
-- Totals only: exports, no second partner, all customs procedures, all transport modes.
where flowCode = 'X'
  and partner2Code = 0
  and customsCode = 'C00'
  and motCode = 0
