"""Deja un solo NivelPeriodo por periodo y nivel.

Va en su propia migracion a proposito: PostgreSQL no deja borrar filas y
cambiar el indice de la misma tabla dentro de la misma transaccion
("pending trigger events").
"""

from django.db import migrations
from django.db.models import Count


def quitar_niveles_repetidos(apps, schema_editor):
    """Al dejar de existir el paralelo, un mismo nivel podia estar varias veces
    en el periodo (uno por paralelo). Se conserva el registro mas antiguo."""
    NivelPeriodo = apps.get_model('academico', 'NivelPeriodo')
    repetidos = NivelPeriodo.objects.values('periodo_id', 'nivel_id').annotate(
        cuantos=Count('id'),
    ).filter(cuantos__gt=1)
    for grupo in repetidos:
        sobrantes = list(
            NivelPeriodo.objects.filter(
                periodo_id=grupo['periodo_id'], nivel_id=grupo['nivel_id'],
            ).order_by('id').values_list('pk', flat=True)
        )[1:]
        NivelPeriodo.objects.filter(pk__in=sobrantes).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('academico', '0005_materiamallapredecesora_nivelperiodo_recordacademico'),
    ]

    operations = [
        migrations.RunPython(quitar_niveles_repetidos, migrations.RunPython.noop),
    ]
