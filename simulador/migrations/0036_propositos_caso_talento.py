from django.db import migrations


def completar_propositos(apps, schema_editor):
    Simulacion = apps.get_model('simulador', 'Simulacion')
    simulacion = Simulacion.objects.filter(
        titulo__icontains='Contratar 1 de 3 desarrolladores Django',
    ).first()
    if not simulacion:
        return
    parametros = dict(simulacion.parametros or {})
    rondas = list(parametros.get('rondas') or [])
    propositos = {
        1: 'Diseñar una evaluación que produzca evidencia confiable para comparar perfiles.',
        2: 'Seleccionar una persona usando evidencia técnica, costo, encaje y riesgo.',
        3: 'Diseñar una incorporación que mejore desempeño y retención sin alterar la selección histórica.',
    }
    for indice, item in enumerate(rondas):
        if not isinstance(item, dict):
            continue
        numero = int(item.get('numero') or indice + 1)
        item = dict(item)
        item['proposito'] = propositos.get(numero, item.get('proposito') or '')
        rondas[indice] = item
    parametros['rondas'] = rondas
    simulacion.parametros = parametros
    simulacion.save(update_fields=['parametros'])


class Migration(migrations.Migration):

    dependencies = [
        ('simulador', '0035_coherencia_caso_talento_por_fases'),
    ]

    operations = [
        migrations.RunPython(completar_propositos, migrations.RunPython.noop),
    ]
