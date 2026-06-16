from django.db import migrations


OPCIONES_POR_RONDA = {
    1: [
        {
            'texto': 'Analizar causas con datos de {materia} antes de intervenir',
            'descripcion': 'Levantar datos, linea base e indicadores para identificar el problema principal.',
            'impacto': {'calidad_analisis': 10, 'claridad': 5, 'riesgo': -4},
        },
        {
            'texto': 'Priorizar el indicador critico con mayor riesgo',
            'descripcion': 'Enfocar el diagnostico en el indicador que mas amenaza el resultado del caso.',
            'impacto': {'calidad_analisis': 8, 'riesgo': -6},
        },
        {
            'texto': 'Solicitar datos complementarios y definir linea base',
            'descripcion': 'Validar informacion faltante antes de proponer una accion de fondo.',
            'impacto': {'claridad': 6, 'viabilidad': 5, 'riesgo': -3},
        },
    ],
    2: [
        {
            'texto': 'Comparar alternativas y seleccionar la opcion mas viable',
            'descripcion': 'Contrastar ventajas, desventajas, costo, impacto y riesgo antes de decidir.',
            'impacto': {'calidad_analisis': 8, 'viabilidad': 8, 'riesgo': -5},
        },
        {
            'texto': 'Implementar una accion de bajo riesgo con control inmediato',
            'descripcion': 'Elegir una decision ejecutable en corto plazo y medir sus efectos.',
            'impacto': {'viabilidad': 10, 'impacto': 6, 'riesgo': -6},
        },
        {
            'texto': 'Escalar una decision de alto impacto con plan de mitigacion',
            'descripcion': 'Tomar una accion fuerte si se justifica con controles y responsables.',
            'impacto': {'impacto': 10, 'calidad_analisis': 5, 'riesgo': 4},
        },
    ],
    3: [
        {
            'texto': 'Ejecutar plan con responsables, fechas e indicadores',
            'descripcion': 'Convertir la decision en actividades verificables y medibles.',
            'impacto': {'viabilidad': 10, 'impacto': 6, 'claridad': 5},
        },
        {
            'texto': 'Ajustar la decision segun resultados de seguimiento',
            'descripcion': 'Revisar indicadores y corregir la accion si no produce el resultado esperado.',
            'impacto': {'calidad_analisis': 6, 'riesgo': -6, 'viabilidad': 5},
        },
        {
            'texto': 'Cerrar la simulacion con evidencia y acciones correctivas',
            'descripcion': 'Presentar resultados, aprendizajes y controles para sostener la mejora.',
            'impacto': {'claridad': 8, 'impacto': 5, 'riesgo': -4},
        },
    ],
}


def forwards(apps, schema_editor):
    PlantillaSimulacion = apps.get_model('simulador', 'PlantillaSimulacion')
    plantilla = PlantillaSimulacion.objects.filter(codigo='global-decision-3rondas-v1').first()
    if not plantilla:
        return

    for ronda in plantilla.rondas.filter(numero__in=OPCIONES_POR_RONDA):
        if ronda.opciones_decision:
            continue
        ronda.opciones_decision = OPCIONES_POR_RONDA[ronda.numero]
        ronda.save(update_fields=['opciones_decision'])


def backwards(apps, schema_editor):
    PlantillaSimulacion = apps.get_model('simulador', 'PlantillaSimulacion')
    plantilla = PlantillaSimulacion.objects.filter(codigo='global-decision-3rondas-v1').first()
    if not plantilla:
        return
    plantilla.rondas.filter(numero__in=OPCIONES_POR_RONDA).update(opciones_decision=[])


class Migration(migrations.Migration):

    dependencies = [
        ('simulador', '0015_alter_accionsugeridasimulacion_options_and_more'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
