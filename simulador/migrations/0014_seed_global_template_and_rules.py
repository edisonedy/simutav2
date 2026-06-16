import json
from decimal import Decimal

from django.db import migrations


def parse_rule(raw):
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    text = str(raw).strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
        if isinstance(data, list):
            return {'any': data}
    except json.JSONDecodeError:
        pass
    return {'any': [item.strip() for item in text.split(',') if item.strip()]}


def forwards(apps, schema_editor):
    ConceptoEsperadoRonda = apps.get_model('simulador', 'ConceptoEsperadoRonda')
    PlantillaSimulacion = apps.get_model('simulador', 'PlantillaSimulacion')
    PlantillaRonda = apps.get_model('simulador', 'PlantillaRonda')
    PlantillaIndicador = apps.get_model('simulador', 'PlantillaIndicador')
    PlantillaRestriccion = apps.get_model('simulador', 'PlantillaRestriccion')
    PlantillaConcepto = apps.get_model('simulador', 'PlantillaConcepto')

    for concepto in ConceptoEsperadoRonda.objects.filter(regla_evaluacion={}):
        concepto.regla_evaluacion = parse_rule(concepto.palabras_clave)
        concepto.save(update_fields=['regla_evaluacion'])

    plantilla, created = PlantillaSimulacion.objects.get_or_create(
        codigo='global-decision-3rondas-v1',
        defaults={
            'nombre': 'Simulacion global por materia - 3 rondas',
            'tipo': 'GLOBAL',
            'descripcion': 'Plantilla base para generar simulaciones con analisis, decision e implementacion en cualquier materia.',
            'maximo_decisiones': 3,
            'tiempo_estimado': 30,
            'nivel_dificultad': 'MEDIA',
            'rol_base': 'Analista en {materia}',
            'contexto_base': (
                'La organizacion necesita resolver un problema relacionado con {materia}. '
                'El estudiante actua como {rol} y debe responder con datos, conceptos de la materia, '
                'criterios de decision e indicadores verificables.'
            ),
            'objetivo_base': (
                'Aplicar {materia} para analizar el problema, comparar alternativas y definir '
                'una implementacion viable con indicadores de control.'
            ),
            'resultado_base': (
                'El estudiante entrega una decision profesional sustentada con datos, riesgos, '
                'conceptos de {materia}, indicadores y acciones verificables.'
            ),
            'instrucciones_ia': (
                'Evalua solo contra la rubrica configurada por el docente. No inventes conceptos, '
                'indicadores, impactos ni puntos. La nota la calcula SimutaV2.'
            ),
            'version': 1,
            'es_predeterminada': True,
        },
    )
    if not created:
        return

    indicadores = [
        ('calidad_analisis', 'Calidad del analisis', 50, 0, 100, 'ALTO', True),
        ('claridad', 'Claridad de la justificacion', 50, 0, 100, 'ALTO', False),
        ('viabilidad', 'Viabilidad de la decision', 50, 0, 100, 'ALTO', True),
        ('impacto', 'Impacto esperado', 50, 0, 100, 'ALTO', False),
        ('riesgo', 'Riesgo de la decision', 50, 0, 100, 'BAJO', True),
    ]
    for codigo, nombre, inicial, minimo, maximo, direccion, critico in indicadores:
        PlantillaIndicador.objects.create(
            plantilla=plantilla,
            codigo=codigo,
            nombre=nombre,
            valor_inicial=Decimal(inicial),
            valor_minimo=Decimal(minimo),
            valor_maximo=Decimal(maximo),
            direccion_optima=direccion,
            es_critico=critico,
            unidad='pts',
        )

    restricciones = [
        ('La propuesta no debe quedar sin analisis suficiente.', 'calidad_analisis', '>=', 40, 15),
        ('La justificacion debe ser clara y defendible.', 'claridad', '>=', 40, 10),
        ('La decision debe ser viable para ejecutarse.', 'viabilidad', '>=', 40, 15),
        ('El riesgo no debe quedar en zona critica.', 'riesgo', '<=', 80, 20),
    ]
    for descripcion, codigo, operador, limite, penalizacion in restricciones:
        PlantillaRestriccion.objects.create(
            plantilla=plantilla,
            descripcion=descripcion,
            codigo_indicador=codigo,
            operador=operador,
            valor_limite=Decimal(limite),
            penalizacion=Decimal(penalizacion),
        )

    rondas = [
        (1, 'Analisis inicial', 'Identificar problema, causas, datos e indicadores.', 'Describe el problema principal de {materia}, sus causas probables y los indicadores que usarias para medirlo.'),
        (2, 'Alternativas y decision', 'Comparar alternativas y elegir una decision concreta.', 'Compara al menos dos alternativas, selecciona la mas viable y justifica la decision con criterios de {materia}.'),
        (3, 'Implementacion y control', 'Definir plan, responsables, control y correccion.', 'Propone un plan de implementacion con acciones, responsables, indicadores de seguimiento y medidas correctivas.'),
    ]
    rondas_creadas = {}
    for numero, titulo, proposito, consigna in rondas:
        rondas_creadas[numero] = PlantillaRonda.objects.create(
            plantilla=plantilla,
            numero=numero,
            titulo=titulo,
            proposito=proposito,
            consigna_base=consigna,
            etiqueta_decision=titulo,
            etiqueta_justificacion='Justificacion',
        )

    conceptos = [
        (1, 'Analisis del problema', 35, True, {'any': ['analisis', 'problema', 'causa', 'situacion', 'datos']}, {'calidad_analisis': 18, 'riesgo': -8}, {'riesgo': 12}),
        (1, 'Uso de datos e indicadores', 25, False, {'any': ['dato', 'indicador', 'medir', 'resultado', 'evidencia']}, {'claridad': 10, 'calidad_analisis': 8}, {}),
        (1, 'Conceptos de la materia', 25, True, {'any': ['concepto', 'metodo', 'modelo', 'herramienta', '{materia}']}, {'calidad_analisis': 12}, {'calidad_analisis': -10}),
        (1, 'Justificacion inicial', 15, False, {'any': ['porque', 'permite', 'evita', 'razon', 'beneficio']}, {'claridad': 8}, {}),
        (2, 'Alternativas comparadas', 30, True, {'any': ['alternativa', 'comparar', 'opcion', 'ventaja', 'desventaja']}, {'calidad_analisis': 12, 'riesgo': -8}, {'riesgo': 15}),
        (2, 'Decision concreta', 30, True, {'any': ['decido', 'propongo', 'recomiendo', 'seleccionar', 'implementar']}, {'viabilidad': 18, 'impacto': 10}, {'viabilidad': -12}),
        (2, 'Gestion de riesgos', 20, False, {'any': ['riesgo', 'control', 'mitigar', 'prevenir', 'validar']}, {'riesgo': -12}, {}),
        (2, 'Justificacion de la decision', 20, False, {'any': ['porque', 'impacto', 'resultado', 'beneficio', 'razon']}, {'claridad': 12}, {}),
        (3, 'Plan de accion', 30, True, {'any': ['plan', 'accion', 'actividad', 'responsable', 'cronograma']}, {'viabilidad': 15, 'impacto': 8}, {'viabilidad': -10}),
        (3, 'Indicadores de seguimiento', 25, True, {'any': ['indicador', 'kpi', 'meta', 'seguimiento', 'medir']}, {'calidad_analisis': 10, 'riesgo': -8}, {'riesgo': 12}),
        (3, 'Control y correccion', 25, False, {'any': ['control', 'corregir', 'ajustar', 'mejora', 'retroalimentacion']}, {'viabilidad': 8, 'riesgo': -10}, {}),
        (3, 'Cierre justificable', 20, False, {'any': ['porque', 'resultado', 'evidencia', 'beneficio', 'aprendizaje']}, {'claridad': 10, 'impacto': 8}, {}),
    ]
    for ronda, nombre, peso, critico, regla, impacto_ok, impacto_falta in conceptos:
        PlantillaConcepto.objects.create(
            ronda=rondas_creadas[ronda],
            nombre=nombre,
            descripcion=f'{nombre} aplicado a {{materia}}.',
            regla_evaluacion=regla,
            peso=Decimal(peso),
            impacto_si_cumple=impacto_ok,
            impacto_si_falta=impacto_falta,
            retroalimentacion_si_cumple=f'Cumple {nombre}.',
            retroalimentacion_si_falta=f'Falta {nombre}.',
            es_critico=critico,
        )


def backwards(apps, schema_editor):
    PlantillaSimulacion = apps.get_model('simulador', 'PlantillaSimulacion')
    PlantillaSimulacion.objects.filter(codigo='global-decision-3rondas-v1').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('simulador', '0013_perfilmateriaia_plantillaconcepto_plantillaindicador_and_more'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
