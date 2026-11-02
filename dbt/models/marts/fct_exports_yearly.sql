-- One row per partner, HS chapter and year: the main table behind the dashboard.

with grid as (

    select * from {{ ref('int_exports__chapter_year') }}

),

enriched as (

    select
        grid.year,
        partners.partner_code,
        partners.partner_iso3,
        partners.partner_name,
        partners.subregion,
        grid.hs_chapter,
        chapters.chapter_name,
        chapters.hs_section,
        chapters.section_name,
        grid.export_value_usd,
        grid.has_recorded_value

    from grid
    inner join {{ ref('partners') }} as partners using (partner_code)
    inner join {{ ref('hs_chapters') }} as chapters using (hs_chapter)

)

select
    *,
    safe_divide(
        export_value_usd - lag(export_value_usd) over chapter_years,
        lag(export_value_usd) over chapter_years
    )                                                               as yoy_growth,
    safe_divide(
        export_value_usd,
        sum(export_value_usd) over (partition by partner_code, year)
    )                                                               as share_of_partner_total,
    rank() over (partition by partner_code, year order by export_value_usd desc)
                                                                    as rank_in_partner_year

from enriched
window chapter_years as (partition by partner_code, hs_chapter order by year)
