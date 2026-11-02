{#- Fails for every combination of `columns` that appears more than once (no dbt_utils dependency). -#}
{% test unique_combination(model, columns) %}

select {{ columns | join(', ') }}, count(*) as n_rows
from {{ model }}
group by {{ columns | join(', ') }}
having count(*) > 1

{% endtest %}
