from decimal import Decimal

from django import template

register = template.Library()


@register.filter
def sum_attr(queryset, attr):
    total = Decimal('0')
    for item in queryset:
        val = getattr(item, attr, None)
        if val is not None:
            try:
                total += Decimal(str(val))
            except (ValueError, TypeError):
                pass
    return total
