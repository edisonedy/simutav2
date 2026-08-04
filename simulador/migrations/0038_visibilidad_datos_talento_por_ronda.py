from django.db import migrations


def ajustar_visibilidad(apps, schema_editor):
    Simulacion = apps.get_model('simulador', 'Simulacion')
    simulacion = Simulacion.objects.filter(
        titulo__icontains='Contratar 1 de 3 desarrolladores Django',
    ).first()
    if not simulacion:
        return
    parametros = dict(simulacion.parametros or {})
    rondas = list(parametros.get('rondas') or [])
    for indice, item in enumerate(rondas):
        if not isinstance(item, dict):
            continue
        numero = int(item.get('numero') or indice + 1)
        item = dict(item)
        item['mostrar_datos_caso'] = numero == 2
        item['mostrar_resultados_alternativas'] = numero == 2
        rondas[indice] = item
    parametros['rondas'] = rondas
    simulacion.parametros = parametros
    simulacion.save(update_fields=['parametros'])


class Migration(migrations.Migration):

    dependencies = [
        ('simulador', '0037_accion_vinculada_a_opcion_caso'),
    ]

    operations = [
        migrations.RunPython(ajustar_visibilidad, migrations.RunPython.noop),
    ]
