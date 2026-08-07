from django.db import migrations


TITULO = 'Evaluación de la efectividad de un nuevo fármaco oncológico - BioPharma Solutions S.A.'


def corregir_opciones_por_ronda(apps, schema_editor):
    Simulacion = apps.get_model('simulador', 'Simulacion')
    Accion = apps.get_model('simulador', 'AccionSugeridaSimulacion')
    simulacion = Simulacion.objects.filter(titulo=TITULO).first()
    if not simulacion:
        return

    # Las alternativas existentes son decisiones sobre la fase III. El
    # diagnostico y el plan requieren desarrollo escrito contra sus rubricas.
    Accion.objects.filter(simulacion_id=simulacion.pk, activo=True).update(
        numero_ronda=2,
        maximo_ejecuciones=1,
    )

    parametros = dict(simulacion.parametros or {})
    rondas = [dict(item) for item in (parametros.get('rondas') or []) if isinstance(item, dict)]
    configuracion = {
        1: {
            'modo': 'escribir',
            'proposito': 'Diagnosticar la evidencia estadistica, los sesgos y la validez del estudio.',
        },
        2: {
            'modo': 'hibrido',
            'proposito': 'Elegir y justificar el diseño de la fase III con criterios estadisticos y eticos.',
        },
        3: {
            'modo': 'escribir',
            'proposito': 'Construir el plan de ejecucion, analisis, logistica y regulacion de la fase III.',
        },
    }
    for indice, ronda in enumerate(rondas):
        numero = int(ronda.get('numero') or indice + 1)
        if numero in configuracion:
            ronda.update(configuracion[numero])
    parametros['rondas'] = rondas
    simulacion.parametros = parametros
    simulacion.save(update_fields=['parametros'])


def restaurar_opciones_globales(apps, schema_editor):
    Simulacion = apps.get_model('simulador', 'Simulacion')
    Accion = apps.get_model('simulador', 'AccionSugeridaSimulacion')
    simulacion = Simulacion.objects.filter(titulo=TITULO).first()
    if not simulacion:
        return
    Accion.objects.filter(simulacion_id=simulacion.pk, activo=True).update(
        numero_ronda=None,
        maximo_ejecuciones=0,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('simulador', '0047_simulacion_peso_resultado'),
    ]

    operations = [
        migrations.RunPython(corregir_opciones_por_ronda, restaurar_opciones_globales),
    ]
