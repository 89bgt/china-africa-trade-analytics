-- Dense partner x chapter x year grid: a chapter missing from Comtrade in a given year means
-- no recorded exports, so it becomes 0 instead of a gap (keeps YoY and CAGR honest).

with exports as (

    select * from {{ ref('stg_comtrade__exports') }}

),

years as (

    select year
    from unnest(generate_array({{ var('start_year') }}, {{ var('end_year') }})) as year

),

spine as (

    select partners.partner_code, chapters.hs_chapter, years.year
    from {{ ref('partners') }} as partners
    cross join {{ ref('hs_chapters') }} as chapters
    cross join years

)

select
    spine.partner_code,
    spine.hs_chapter,
    spine.year,
    coalesce(exports.export_value_usd, 0)   as export_value_usd,
    exports.export_value_usd is not null    as has_recorded_value

from spine
left join exports
    using (partner_code, hs_chapter, year)

where true  -- BigQuery requires a WHERE/GROUP BY alongside QUALIFY
-- Drop partner/chapter pairs with no trade at all over the whole window.
qualify sum(coalesce(exports.export_value_usd, 0))
    over (partition by spine.partner_code, spine.hs_chapter) > 0
