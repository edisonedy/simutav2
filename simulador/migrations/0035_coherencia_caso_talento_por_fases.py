import json

from django.db import migrations


def configurar_talento(apps, schema_editor):
    Simulacion = apps.get_model('simulador', 'Simulacion')
    Indicador = apps.get_model('simulador', 'IndicadorSimulacion')
    Accion = apps.get_model('simulador', 'AccionSugeridaSimulacion')
    Opcion = apps.get_model('simulador', 'OpcionCasoSimulacion')
    Matriz = apps.get_model('simulador', 'MatrizEvaluacionCaso')
    Concepto = apps.get_model('simulador', 'ConceptoEsperadoRonda')
    Intento = apps.get_model('simulador', 'IntentoSimulacion')

    simulacion = Simulacion.objects.filter(
        titulo__icontains='Contratar 1 de 3 desarrolladores Django',
    ).first()
    if not simulacion:
        return

    proceso = [
        ('calidad_evidencia', 'Calidad de la evidencia de selección', 50, 0, 100, 'ALTO', '%'),
        ('objetividad_proceso', 'Objetividad del proceso', 50, 0, 100, 'ALTO', '%'),
        ('riesgo_error_seleccion', 'Riesgo de error de selección', 50, 0, 100, 'BAJO', '%'),
    ]
    for codigo, nombre, inicial, minimo, maximo, direccion, unidad in proceso:
        Indicador.objects.update_or_create(
            simulacion=simulacion,
            codigo=codigo,
            defaults={
                'nombre': nombre, 'valor_inicial': inicial, 'valor_minimo': minimo,
                'valor_maximo': maximo, 'direccion_optima': direccion,
                'peso_salud': 0, 'es_critico': False, 'unidad': unidad, 'activo': True,
            },
        )

    pesos = {
        'ajuste_perfil': 25, 'competencia_tecnica': 20, 'costo_contratacion': 10,
        'clima_equipo': 15, 'riesgo_rotacion': 20, 'tiempo_productividad': 10,
    }
    for codigo, peso in pesos.items():
        Indicador.objects.filter(simulacion=simulacion, codigo=codigo).update(peso_salud=peso)
    Indicador.objects.filter(simulacion=simulacion, codigo='costo_contratacion').update(
        nombre='Costo salarial mensual (referencia inicial $1.350)', unidad='$',
    )

    parametros = dict(simulacion.parametros or {})
    parametros['caso_labels'] = {
        'alternativas_titulo': 'Candidatos finalistas',
        'alternativa_col': 'Candidato',
        'valor_titulo': 'Salario solicitado',
        'valor_col': 'Salario',
        'fortaleza_titulo': 'Evidencia favorable',
        'fortaleza_col': 'Evidencia favorable',
        'riesgo_titulo': 'Riesgo observado',
        'riesgo_col': 'Riesgo observado',
        'matriz_titulo': 'Criterios para comparar candidatos',
        'datos_titulo': 'Información del proceso de selección',
    }
    rondas = list(parametros.get('rondas') or [])
    permitidos = {
        1: ['calidad_evidencia', 'objetividad_proceso', 'riesgo_error_seleccion'],
        2: ['ajuste_perfil', 'competencia_tecnica', 'costo_contratacion', 'clima_equipo',
            'riesgo_rotacion', 'tiempo_productividad'],
        3: ['competencia_tecnica', 'clima_equipo', 'riesgo_rotacion', 'tiempo_productividad'],
    }
    while len(rondas) < 3:
        rondas.append({})
    for numero in (1, 2, 3):
        item = dict(rondas[numero - 1] or {})
        item.update({
            'numero': numero,
            'modo': 'hibrido',
            'justificacion_obligatoria': True,
            'indicadores_modificables': permitidos[numero],
        })
        rondas[numero - 1] = item
    parametros['rondas'] = rondas[:3]
    simulacion.parametros = parametros
    simulacion.version_configuracion = (simulacion.version_configuracion or 1) + 1
    simulacion.save(update_fields=['parametros', 'version_configuracion'])

    impactos_acciones = {
        'Aplicar prueba integral': {
            'calidad_evidencia': 35, 'objetividad_proceso': 30, 'riesgo_error_seleccion': -30,
        },
        'Aplicar solo ejercicios': {
            'calidad_evidencia': 10, 'objetividad_proceso': 8, 'riesgo_error_seleccion': -5,
        },
        'Hacer solo entrevista informal': {
            'calidad_evidencia': -10, 'objetividad_proceso': -15, 'riesgo_error_seleccion': 15,
        },
        'Contratar a Ana Reyes': {
            'ajuste_perfil': 34, 'competencia_tecnica': 34, 'costo_contratacion': 0,
            'clima_equipo': 32, 'riesgo_rotacion': -25, 'tiempo_productividad': -4,
        },
        'Contratar a Luis Carrion': {
            'ajuste_perfil': 24, 'competencia_tecnica': 36, 'costo_contratacion': -50,
            'clima_equipo': 18, 'riesgo_rotacion': -7, 'tiempo_productividad': -2,
        },
        'Contratar a Marta Sanchez': {
            'ajuste_perfil': 28, 'competencia_tecnica': 30, 'costo_contratacion': 50,
            'clima_equipo': 5, 'riesgo_rotacion': -13, 'tiempo_productividad': -2,
        },
        'Ejecutar onboarding 30-60-90': {
            'competencia_tecnica': 8, 'clima_equipo': 12,
            'riesgo_rotacion': -16, 'tiempo_productividad': -4,
        },
        'Hacer una induccion de un dia': {
            'competencia_tecnica': 2, 'clima_equipo': -5,
            'riesgo_rotacion': 8, 'tiempo_productividad': 2,
        },
        'Ofrecer aumento salarial': {
            'competencia_tecnica': 0, 'clima_equipo': 2,
            'riesgo_rotacion': -4, 'tiempo_productividad': 1,
        },
    }
    for prefijo, impacto in impactos_acciones.items():
        Accion.objects.filter(
            simulacion=simulacion, texto__startswith=prefijo,
        ).update(impacto_base={k: v for k, v in impacto.items() if v})
    Accion.objects.filter(
        simulacion=simulacion, texto__icontains='menor salario sin ponderar',
    ).update(activo=False)

    # La calidad de la explicación produce nota y feedback; no altera por sí
    # sola a la persona contratada. Las consecuencias salen de la opción.
    Concepto.objects.filter(simulacion=simulacion).update(
        impacto_si_cumple={}, impacto_si_falta={},
    )
    reglas = {
        'Decision basada en criterios': {
            'any': ['criterio', 'perfil', 'resultado', 'prueba', 'cumple', 'seleccion', 'contratar'],
            'none': ['solo por ser mas barato'],
        },
        'Evaluacion tecnica (Django)': {
            'any': ['django', 'testing', 'drf', 'orm', 'code review', 'mini feature', 'prueba tecnica'],
        },
        'Justificacion objetiva sin sesgo': {
            'any': ['compara', 'comparacion', 'evidencia', 'criterio', 'resultado', 'puntaje', 'datos'],
        },
    }
    for nombre, regla in reglas.items():
        Concepto.objects.filter(simulacion=simulacion, nombre=nombre).update(
            regla_evaluacion=regla,
            palabras_clave=json.dumps(regla, ensure_ascii=False),
        )

    Opcion.objects.filter(simulacion=simulacion).delete()
    candidatos = [
        ('Ana Reyes', 'Django intermedio · salario $1.350', '$1.350',
         'Mini feature 84, testing 88 y comunicación 82.',
         'DRF 70; requiere apoyo inicial en APIs avanzadas.',
         [('Competencia técnica', 84), ('Encaje con el equipo', 82), ('Riesgo de rotación', 30), ('Ajuste al presupuesto', 75)]),
        ('Luis Carrión', 'Django intermedio · salario $1.300', '$1.300',
         'Mini feature 86 y DRF 92.',
         'Testing 45, comunicación 68 y riesgo de rotación 48%.',
         [('Competencia técnica', 86), ('Encaje con el equipo', 68), ('Riesgo de rotación', 48), ('Ajuste al presupuesto', 85)]),
        ('Marta Sánchez', 'Django intermedio · salario $1.400', '$1.400',
         'ORM 90, code review 80 y testing 72.',
         'Comunicación 55 y riesgo de rotación 42%.',
         [('Competencia técnica', 80), ('Encaje con el equipo', 55), ('Riesgo de rotación', 42), ('Ajuste al presupuesto', 65)]),
    ]
    for orden, (nombre, subtitulo, valor, fortaleza, riesgo, resultados) in enumerate(candidatos, 1):
        Opcion.objects.create(
            simulacion=simulacion, nombre=nombre, subtitulo=subtitulo,
            valor_referencia=valor, fortaleza=fortaleza, riesgo=riesgo,
            resultados=[{'criterio': c, 'valor': v} for c, v in resultados],
            orden=orden, activo=True,
        )
    Matriz.objects.filter(simulacion=simulacion).delete()
    for orden, (criterio, peso, evalua) in enumerate([
        ('Competencia técnica Django', 35, 'mini feature, testing, ORM, DRF y code review'),
        ('Encaje con el equipo', 20, 'comunicación, colaboración y recepción de feedback'),
        ('Riesgo de rotación', 25, 'probabilidad de salida durante el primer año'),
        ('Ajuste al presupuesto', 20, 'salario solicitado frente al presupuesto del cargo'),
    ], 1):
        Matriz.objects.create(
            simulacion=simulacion, criterio=criterio, peso=peso,
            evalua=evalua, orden=orden, activo=True,
        )

    for intento in Intento.objects.filter(simulacion=simulacion):
        snapshot = dict(intento.configuracion_snapshot or {})
        snapshot['aviso_version'] = (
            'Este intento conserva la configuración histórica. Las partidas nuevas '
            'usan indicadores separados por fase y candidatos coherentes.'
        )
        intento.configuracion_snapshot = snapshot
        intento.save(update_fields=['configuracion_snapshot'])


class Migration(migrations.Migration):

    dependencies = [
        ('simulador', '0034_indicador_peso_salud'),
    ]

    operations = [
        migrations.RunPython(configurar_talento, migrations.RunPython.noop),
    ]
