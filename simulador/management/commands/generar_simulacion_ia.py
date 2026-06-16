import json
import logging
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from academico.models import MateriaMalla
from simulador.models import (
    AccionSugeridaSimulacion,
    ConceptoEsperadoRonda,
    CriterioEvaluacion,
    IndicadorSimulacion,
    RestriccionSimulacion,
    Simulacion,
)

logger = logging.getLogger(__name__)

PROMPT_TEMPLATE = """
Eres un generador experto de simulaciones académicas universitarias para SimutaV2.

Debes crear una simulación realista para una materia específica de una malla académica.

DATOS DE ENTRADA:
Materia: {materia}
Carrera: {carrera}
Malla: {malla}
Nivel: {nivel}
Dificultad: {dificultad}
Rondas máximas: 3

OBJETIVO:
Crear una simulación académica realista, aplicada y evaluable. La simulación debe parecer un caso real de empresa, institución, emprendimiento, área técnica o proceso profesional relacionado directamente con la materia.

REGLAS GENERALES:

* No hagas preguntas teóricas.
* No uses el mismo caso para todas las materias.
* No uses siempre los mismos indicadores.
* Los indicadores deben ser propios de la materia.
* El caso debe tener datos concretos: porcentajes, costos, tiempos, ventas, errores, defectos, clientes, empleados, liquidez, productividad, reclamos, riesgos o resultados.
* El texto debe ser corto, claro y realista.
* No des la solución al estudiante.
* El estudiante debe diagnosticar, decidir e implementar.
* La simulación debe tener 3 rondas:

  1. Diagnóstico
  2. Decisión
  3. Implementación
* Cada ronda debe tener una pregunta clara.
* Cada ronda debe tener conceptos esperados con peso total 100.
* Las palabras clave deben ser específicas de la materia.
* Devuelve solo JSON válido. No agregues explicación fuera del JSON.

INDICADORES:
Debes crear indicadores propios según la materia. Ejemplos:

* Administración Financiera: liquidez_corriente, flujo_caja, rentabilidad, endeudamiento, capital_trabajo, cartera_vencida.
* Contabilidad de Costos: costo_unitario, costos_sobre_ventas, margen_bruto, margen_contribucion, punto_equilibrio, rotacion_inventario.
* Administración de la Producción: defectos_produccion, entregas_tardias, capacidad_utilizada, inventario, productividad, tiempo_ciclo.
* Talento Humano: rotacion_personal, ausentismo, desempeno_laboral, clima_laboral, capacitacion, retencion_talento.
* Django: tiempo_respuesta, errores_500, consultas_sql, disponibilidad, seguridad, cobertura_pruebas.
* Derecho Laboral: reclamos_laborales, contratos_incompletos, horas_extra_pendientes, riesgo_legal, cumplimiento_normativo.
* Estadística Descriptiva: promedio, mediana, desviacion_estandar, rango_datos, variacion_datos.
* Gerencia de la Calidad: tasa_defectos, reclamos_clientes, reprocesos, cumplimiento_estandares, satisfaccion_cliente.
* Investigación Operativa: costo_transporte, capacidad_recurso, tiempo_ruta, demanda_atendida, solucion_optima.
* Marketing: conversion_clientes, ventas, alcance_campana, costo_adquisicion_cliente, satisfaccion_cliente.

ESTRUCTURA JSON OBLIGATORIA:

{{
"titulo": "",
"tema": "",
"rol_estudiante": "",
"contexto": "",
"objetivo": "",
"resultado_aprendizaje": "",
"situacion_inicial": "",

"indicadores": [
{{
"codigo": "",
"nombre": "",
"valor_inicial": 50,
"valor_minimo": 0,
"valor_maximo": 100,
"direccion_optima": "ALTO",
"unidad": "",
"descripcion": ""
}}
],

"restricciones": [
{{
"descripcion": "",
"codigo_indicador": "",
"operador": ">=",
"valor_limite": 0,
"penalizacion": 10
}}
],

"rondas": [
{{
"numero": 1,
"titulo": "Diagnóstico",
"pregunta": "",
"placeholder_respuesta": "Describe el problema principal, causas e indicadores.",
"placeholder_justificacion": "Explica por qué ese diagnóstico es importante.",
"conceptos_esperados": [
{{
"nombre": "Diagnóstico del problema",
"descripcion": "",
"peso": 35,
"critico": true,
"palabras_clave": ""
}},
{{
"nombre": "Indicadores y datos",
"descripcion": "",
"peso": 20,
"critico": false,
"palabras_clave": ""
}},
{{
"nombre": "Justificación inicial",
"descripcion": "",
"peso": 15,
"critico": false,
"palabras_clave": ""
}},
{{
"nombre": "Uso de conceptos de la materia",
"descripcion": "",
"peso": 30,
"critico": true,
"palabras_clave": ""
}}
]
}},
{{
"numero": 2,
"titulo": "Decisión",
"pregunta": "",
"placeholder_respuesta": "Compara alternativas y elige una decisión concreta.",
"placeholder_justificacion": "Explica por qué esa decisión es viable.",
"conceptos_esperados": [
{{
"nombre": "Alternativas comparadas",
"descripcion": "",
"peso": 30,
"critico": true,
"palabras_clave": ""
}},
{{
"nombre": "Decisión concreta",
"descripcion": "",
"peso": 30,
"critico": true,
"palabras_clave": ""
}},
{{
"nombre": "Gestión de riesgos",
"descripcion": "",
"peso": 20,
"critico": false,
"palabras_clave": ""
}},
{{
"nombre": "Justificación de la decisión",
"descripcion": "",
"peso": 20,
"critico": false,
"palabras_clave": ""
}}
]
}},
{{
"numero": 3,
"titulo": "Implementación",
"pregunta": "",
"placeholder_respuesta": "Describe el plan de acción, responsables, tiempos y controles.",
"placeholder_justificacion": "Explica cómo se controlará y corregirá el plan.",
"conceptos_esperados": [
{{
"nombre": "Plan de acción",
"descripcion": "",
"peso": 30,
"critico": true,
"palabras_clave": ""
}},
{{
"nombre": "Indicadores de seguimiento",
"descripcion": "",
"peso": 25,
"critico": true,
"palabras_clave": ""
}},
{{
"nombre": "Control y corrección",
"descripcion": "",
"peso": 25,
"critico": false,
"palabras_clave": ""
}},
{{
"nombre": "Cierre justificable",
"descripcion": "",
"peso": 20,
"critico": false,
"palabras_clave": ""
}}
]
}}
],

"decisiones_sugeridas": [
{{
"texto": "",
"descripcion": "",
"impacto_base": {{}}
}}
],

"respuestas_prueba": {{
"mala": {{
"ronda_1": "",
"ronda_2": "",
"ronda_3": ""
}},
"media": {{
"ronda_1": "",
"ronda_2": "",
"ronda_3": ""
}},
"buena": {{
"ronda_1": "",
"ronda_2": "",
"ronda_3": ""
}}
}}
}}

REGLAS PARA INDICADORES:

* Genera entre 4 y 6 indicadores propios de la materia.
* Cada indicador debe tener código en minúsculas y sin espacios.
* Cada indicador debe tener valor inicial realista.
* La unidad debe ser clara: %, USD, días, horas, pts, ratio, cantidad.
* La dirección óptima debe ser "ALTO" si mientras más alto mejor, o "BAJO" si mientras más bajo mejor.
* Las restricciones deben usar esos indicadores propios.
* El contexto y la situación inicial deben mencionar los valores iniciales de los indicadores.

REGLAS PARA PALABRAS CLAVE:

* Las palabras clave deben estar separadas por comas.
* No uses solo palabras genéricas como: administración, gestión, porque, teoría.
* Usa palabras propias de la materia y del caso.
* Incluye variantes importantes: indicador, indicadores, control, controles, corregir, corrección, mejora, mejorar.
* Cada concepto debe tener entre 6 y 12 palabras clave.

REGLAS PARA LAS RESPUESTAS DE PRUEBA:

* La respuesta mala debe ser muy general.
* La respuesta media debe mencionar algunos datos e indicadores.
* La respuesta buena debe mencionar problema, causas, indicadores, decisión, riesgos, plan, responsables y control.
* Estas respuestas servirán para probar que la rúbrica no sea demasiado fácil ni demasiado dura.

IMPORTANTE:
La simulación debe quedar lista para guardarse en Django como una simulación real por materia de la malla.
"""


class Command(BaseCommand):
    help = 'Genera una simulacion realista desde OpenAI usando el prompt de simulaciones academicas.'

    def add_arguments(self, parser):
        parser.add_argument('materia_malla_id', type=int, help='ID de MateriaMalla')
        parser.add_argument('--profesor-id', type=int, default=None, help='ID del usuario profesor (opcional)')

    def handle(self, *args, **options):
        materia_malla_id = options['materia_malla_id']
        profesor_id = options.get('profesor_id')

        try:
            mm = MateriaMalla.objects.select_related(
                'materia', 'nivel', 'malla__carrera'
            ).get(pk=materia_malla_id, activo=True)
        except MateriaMalla.DoesNotExist:
            self.stderr.write(self.style.ERROR(f'MateriaMalla con id={materia_malla_id} no encontrada.'))
            return

        materia = mm.materia.nombre
        carrera = mm.malla.carrera.nombre
        malla = mm.malla.nombre
        nivel = mm.nivel.numero

        dificultad = input(f'Dificultad para "{materia}" (BAJA/MEDIA/ALTA) [MEDIA]: ').strip().upper() or 'MEDIA'
        if dificultad not in ('BAJA', 'MEDIA', 'ALTA'):
            dificultad = 'MEDIA'

        self.stdout.write(f'Generando simulacion para {materia} ({carrera} - Nivel {nivel})...')

        prompt = PROMPT_TEMPLATE.format(
            materia=materia,
            carrera=carrera,
            malla=malla,
            nivel=nivel,
            dificultad=dificultad,
        )

        api_key = getattr(settings, 'OPENAI_API_KEY', '') or ''
        if not api_key:
            self.stderr.write(self.style.ERROR('OPENAI_API_KEY no configurada en settings.'))
            return

        model = getattr(settings, 'OPENAI_MODEL', 'gpt-5.5')

        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            respuesta_openai = client.responses.create(
                model=model,
                input=prompt,
                text={
                    'format': {
                        'type': 'json_schema',
                        'name': 'simulacion_academica',
                        'schema': _schema_simulacion(),
                        'strict': True,
                    }
                },
                reasoning={'effort': 'low'},
                store=False,
                timeout=120,
            )
            contenido = respuesta_openai.output_text
            data = json.loads(contenido)
        except Exception as e:
            logger.error(f'Error llamando a OpenAI: {e}')
            self.stderr.write(self.style.ERROR(f'Error llamando a OpenAI: {e}'))
            return

        try:
            simulacion = _crear_simulacion(data, mm, profesor_id)
            self.stdout.write(self.style.SUCCESS(
                f'Simulacion creada: ID={simulacion.pk} - "{simulacion.titulo}"'
            ))
        except Exception as e:
            logger.error(f'Error creando simulacion en BD: {e}')
            self.stderr.write(self.style.ERROR(f'Error creando simulacion en BD: {e}'))
            import traceback
            self.stderr.write(traceback.format_exc())


def _schema_simulacion():
    return {
        'type': 'object',
        'properties': {
            'titulo': {'type': 'string'},
            'tema': {'type': 'string'},
            'rol_estudiante': {'type': 'string'},
            'contexto': {'type': 'string'},
            'objetivo': {'type': 'string'},
            'resultado_aprendizaje': {'type': 'string'},
            'situacion_inicial': {'type': 'string'},
            'indicadores': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                        'codigo': {'type': 'string'},
                        'nombre': {'type': 'string'},
                        'valor_inicial': {'type': 'number'},
                        'valor_minimo': {'type': 'number'},
                        'valor_maximo': {'type': 'number'},
                        'direccion_optima': {'type': 'string', 'enum': ['ALTO', 'BAJO']},
                        'unidad': {'type': 'string'},
                        'descripcion': {'type': 'string'},
                    },
                    'required': ['codigo', 'nombre', 'valor_inicial', 'valor_minimo', 'valor_maximo', 'direccion_optima', 'unidad', 'descripcion'],
                    'additionalProperties': False,
                },
            },
            'restricciones': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                        'descripcion': {'type': 'string'},
                        'codigo_indicador': {'type': 'string'},
                        'operador': {'type': 'string', 'enum': ['>', '>=', '<', '<=', '=']},
                        'valor_limite': {'type': 'number'},
                        'penalizacion': {'type': 'number'},
                    },
                    'required': ['descripcion', 'codigo_indicador', 'operador', 'valor_limite', 'penalizacion'],
                    'additionalProperties': False,
                },
            },
            'rondas': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                        'numero': {'type': 'number'},
                        'titulo': {'type': 'string'},
                        'pregunta': {'type': 'string'},
                        'placeholder_respuesta': {'type': 'string'},
                        'placeholder_justificacion': {'type': 'string'},
                        'conceptos_esperados': {
                            'type': 'array',
                            'items': {
                                'type': 'object',
                                'properties': {
                                    'nombre': {'type': 'string'},
                                    'descripcion': {'type': 'string'},
                                    'peso': {'type': 'number'},
                                    'critico': {'type': 'boolean'},
                                    'palabras_clave': {'type': 'string'},
                                },
                                'required': ['nombre', 'descripcion', 'peso', 'critico', 'palabras_clave'],
                                'additionalProperties': False,
                            },
                        },
                    },
                    'required': ['numero', 'titulo', 'pregunta', 'placeholder_respuesta', 'placeholder_justificacion', 'conceptos_esperados'],
                    'additionalProperties': False,
                },
            },
            'decisiones_sugeridas': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                        'texto': {'type': 'string'},
                        'descripcion': {'type': 'string'},
                        'impacto_base': {'type': 'object'},
                    },
                    'required': ['texto', 'descripcion', 'impacto_base'],
                    'additionalProperties': False,
                },
            },
            'respuestas_prueba': {
                'type': 'object',
                'properties': {
                    'mala': {
                        'type': 'object',
                        'properties': {
                            'ronda_1': {'type': 'string'},
                            'ronda_2': {'type': 'string'},
                            'ronda_3': {'type': 'string'},
                        },
                        'required': ['ronda_1', 'ronda_2', 'ronda_3'],
                        'additionalProperties': False,
                    },
                    'media': {
                        'type': 'object',
                        'properties': {
                            'ronda_1': {'type': 'string'},
                            'ronda_2': {'type': 'string'},
                            'ronda_3': {'type': 'string'},
                        },
                        'required': ['ronda_1', 'ronda_2', 'ronda_3'],
                        'additionalProperties': False,
                    },
                    'buena': {
                        'type': 'object',
                        'properties': {
                            'ronda_1': {'type': 'string'},
                            'ronda_2': {'type': 'string'},
                            'ronda_3': {'type': 'string'},
                        },
                        'required': ['ronda_1', 'ronda_2', 'ronda_3'],
                        'additionalProperties': False,
                    },
                },
                'required': ['mala', 'media', 'buena'],
                'additionalProperties': False,
            },
        },
        'required': [
            'titulo', 'tema', 'rol_estudiante', 'contexto', 'objetivo',
            'resultado_aprendizaje', 'situacion_inicial',
            'indicadores', 'restricciones', 'rondas', 'decisiones_sugeridas',
            'respuestas_prueba',
        ],
        'additionalProperties': False,
    }


def _buscar_profesor():
    from django.contrib.auth import get_user_model
    User = get_user_model()
    profesor = User.objects.filter(is_staff=True, is_active=True).first()
    if not profesor:
        profesor = User.objects.filter(is_active=True).first()
    return profesor


@transaction.atomic
def _crear_simulacion(data, materia_malla, profesor_id=None):
    from django.contrib.auth import get_user_model
    User = get_user_model()

    profesor = None
    if profesor_id:
        profesor = User.objects.filter(pk=profesor_id, is_active=True).first()
    if not profesor:
        profesor = _buscar_profesor()

    dificultad_map = {'BAJA': 'BAJA', 'MEDIA': 'MEDIA', 'ALTA': 'ALTA'}
    dificultad = dificultad_map.get(data.get('dificultad', 'MEDIA'), 'MEDIA')

    rondas_data = data.get('rondas', [])
    max_rondas = max((r['numero'] for r in rondas_data), default=3)

    simulacion = Simulacion.objects.create(
        materia_malla=materia_malla,
        profesor=profesor,
        tipo_simulacion=Simulacion.TIPO_CON_IA_DINAMICA,
        titulo=data['titulo'],
        tema=data.get('tema', ''),
        nivel_dificultad=dificultad,
        maximo_decisiones=max_rondas,
        tiempo_estimado=25,
        rol_estudiante=data.get('rol_estudiante', ''),
        contexto=data.get('contexto', ''),
        objetivo=data.get('objetivo', ''),
        resultado_aprendizaje=data.get('resultado_aprendizaje', ''),
        situacion_inicial=data.get('situacion_inicial', ''),
        estado=Simulacion.BORRADOR,
        parametros={
            'modo': 'toma_decisiones',
            'rondas': [
                {
                    'numero': r['numero'],
                    'titulo': r['titulo'],
                    'proposito': r.get('pregunta', ''),
                    'situacion': r.get('pregunta', ''),
                }
                for r in rondas_data
            ],
        },
        metadata_generacion={
            'origen': 'comando_generar_simulacion_ia',
            'materia_malla_id': materia_malla.id,
        },
        version_configuracion=1,
        api_ia='responses',
        modelo_ia=getattr(settings, 'OPENAI_MODEL', ''),
        usuario_creacion=profesor,
    )

    for ind in data.get('indicadores', []):
        IndicadorSimulacion.objects.create(
            simulacion=simulacion,
            codigo=ind['codigo'],
            nombre=ind['nombre'],
            valor_inicial=Decimal(str(ind.get('valor_inicial', 50))),
            valor_minimo=Decimal(str(ind.get('valor_minimo', 0))),
            valor_maximo=Decimal(str(ind.get('valor_maximo', 100))),
            direccion_optima=ind.get('direccion_optima', 'ALTO'),
            es_critico=False,
            unidad=ind.get('unidad', ''),
            usuario_creacion=profesor,
        )

    for res in data.get('restricciones', []):
        RestriccionSimulacion.objects.create(
            simulacion=simulacion,
            descripcion=res['descripcion'],
            codigo_indicador=res['codigo_indicador'],
            operador=res.get('operador', '>='),
            valor_limite=Decimal(str(res.get('valor_limite', 0))),
            penalizacion=Decimal(str(res.get('penalizacion', 10))),
            usuario_creacion=profesor,
        )

    for ronda in rondas_data:
        CriterioEvaluacion.objects.create(
            simulacion=simulacion,
            nombre=ronda.get('titulo', f'Ronda {ronda["numero"]}'),
            descripcion=ronda.get('pregunta', ''),
            peso=Decimal('100') / Decimal(max(1, max_rondas)),
            puntaje_maximo=100,
            usuario_creacion=profesor,
        )

        for concepto in ronda.get('conceptos_esperados', []):
            palabras = concepto.get('palabras_clave', '')
            ConceptoEsperadoRonda.objects.create(
                simulacion=simulacion,
                numero_ronda=ronda['numero'],
                nombre=concepto['nombre'],
                descripcion=concepto.get('descripcion', ''),
                palabras_clave=palabras,
                regla_evaluacion={'any': [p.strip() for p in palabras.split(',') if p.strip()]},
                peso=Decimal(str(concepto['peso'])),
                impacto_si_cumple={},
                impacto_si_falta={},
                es_critico=concepto.get('critico', False),
                usuario_creacion=profesor,
            )

    for decision in data.get('decisiones_sugeridas', []):
        AccionSugeridaSimulacion.objects.create(
            simulacion=simulacion,
            numero_ronda=1,
            texto=decision.get('texto', ''),
            descripcion=decision.get('descripcion', ''),
            impacto_base=decision.get('impacto_base', {}),
            usuario_creacion=profesor,
        )

    return simulacion
