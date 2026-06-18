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


def _num(v):
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


@register.filter
def dict_legible(valor):
    """Muestra un dict {codigo: valor} como texto claro, sin JSON.
    Ej: {'riesgo': -5, 'viabilidad': 8} -> 'riesgo -5, viabilidad +8'."""
    if not isinstance(valor, dict) or not valor:
        return 'sin cambios'
    partes = []
    for clave, v in valor.items():
        nombre = str(clave).replace('_', ' ')
        if isinstance(v, (int, float)):
            signo = '+' if v >= 0 else ''
            partes.append(f'{nombre} {signo}{_num(v)}')
        else:
            partes.append(f'{nombre}: {v}')
    return ', '.join(partes)


@register.filter
def lista_legible(valor):
    """Muestra una lista como texto separado por comas, sin corchetes ni comillas."""
    if isinstance(valor, (list, tuple)):
        items = [str(x).strip() for x in valor if str(x).strip()]
        return ', '.join(items) if items else '—'
    if not valor:
        return '—'
    return str(valor)
