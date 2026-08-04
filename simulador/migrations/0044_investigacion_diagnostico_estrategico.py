from django.db import migrations


def activar_investigacion_diagnostico(apps, schema_editor):
    Simulacion = apps.get_model('simulador', 'Simulacion')
    simulacion = Simulacion.objects.filter(
        titulo__icontains='Estrategia de diversificación y entrada a nuevos mercados',
    ).first()
    if not simulacion:
        return
    parametros = dict(simulacion.parametros or {})
    rondas = list(parametros.get('rondas') or [])
    for indice, ronda in enumerate(rondas):
        if not isinstance(ronda, dict):
            continue
        item = dict(ronda)
        numero = int(item.get('numero') or indice + 1)
        item['mostrar_investigaciones'] = numero == 1
        rondas[indice] = item
    parametros['rondas'] = rondas
    simulacion.parametros = parametros
    simulacion.save(update_fields=['parametros'])


class Migration(migrations.Migration):

    dependencies = [
        ('simulador', '0043_coherencia_caso_estrategia_mercado'),
    ]

    operations = [
        migrations.RunPython(activar_investigacion_diagnostico, migrations.RunPython.noop),
    ]
