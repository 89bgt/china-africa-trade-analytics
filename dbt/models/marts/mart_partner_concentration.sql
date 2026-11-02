-- How concentrated each partner's imports from China are, per year.
--   HHI = sum of squared chapter shares x 10,000 (0 = fully diversified, 10,000 = one chapter).

with yearly as (

    select * from {{ ref('fct_exports_yearly') }}

)

select
    partner_code,
    partner_name,
    year,
    sum(export_value_usd)                                           as total_exports_usd,
    round(sum(pow(share_of_partner_total, 2)) * 10000)              as hhi,
    sum(if(rank_in_partner_year <= 3, share_of_partner_total, 0))   as top3_share,
    countif(export_value_usd > 0)                                   as n_chapters_traded

from yearly
group by partner_code, partner_name, year
