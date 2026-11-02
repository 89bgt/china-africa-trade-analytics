-- Top N fastest-growing HS chapters (by CAGR) per partner, among chapters with a material base.

select
    *,
    row_number() over (partition by partner_code order by cagr desc) as growth_rank

from {{ ref('mart_chapter_growth') }}
where cagr is not null
qualify growth_rank <= {{ var('top_n') }}
