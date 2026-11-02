-- Growth of each HS chapter between start_year and end_year, per partner and for the
-- three partners combined (partner_code = 0).
--   CAGR = (value_end / value_start) ^ (1 / years) - 1
-- CAGR is only computed when the start-year base is at least min_base_value_usd.

{% set start_year = var('start_year') %}
{% set end_year = var('end_year') %}

with yearly as (

    select partner_code, partner_name, hs_chapter, chapter_name, section_name, year, export_value_usd
    from {{ ref('fct_exports_yearly') }}

    union all

    select 0, 'All three partners', hs_chapter, chapter_name, section_name, year, sum(export_value_usd)
    from {{ ref('fct_exports_yearly') }}
    group by hs_chapter, chapter_name, section_name, year

),

endpoints as (

    select
        partner_code,
        partner_name,
        hs_chapter,
        chapter_name,
        section_name,
        sum(if(year = {{ start_year }}, export_value_usd, 0))   as value_start_usd,
        sum(if(year = {{ end_year }}, export_value_usd, 0))     as value_end_usd

    from yearly
    group by partner_code, partner_name, hs_chapter, chapter_name, section_name

)

select
    *,
    {{ start_year }}                                        as start_year,
    {{ end_year }}                                          as end_year,
    value_end_usd - value_start_usd                         as abs_change_usd,
    value_start_usd >= {{ var('min_base_value_usd') }}      as is_material_base,
    if(
        value_start_usd >= {{ var('min_base_value_usd') }} and value_end_usd > 0,
        pow(
            cast(value_end_usd as float64) / cast(value_start_usd as float64),
            1 / {{ end_year - start_year }}
        ) - 1,
        null
    )                                                       as cagr,
    safe_divide(
        value_end_usd,
        sum(value_end_usd) over (partition by partner_code)
    )                                                       as share_of_partner_total_end

from endpoints
