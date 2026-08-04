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

# El esquema de la simulación es genérico: la secuencia y el tipo de interacción
# nacen del aprendizaje que se desea evidenciar, no de fases heredadas.
PROMPT_TEMPLATE = """
Eres un diseñador de simulaciones universitarias de toma de decisiones para SimutaV2.

Materia: {materia}
Carrera: {carrera}
Malla: {malla}
Nivel: {nivel}
Dificultad: {dificultad}

Crea un caso profesional realista en el que el estudiante deba interpretar información,
elegir entre alternativas con ventajas y costos, justificar con conceptos de la materia y
observar consecuencias. No es un examen de preguntas teóricas ni existe una secuencia
universal de diagnóstico, decisión y plan.

Reglas:
- Define únicamente las rondas necesarias según el aprendizaje y el caso. Puede ser una o
  varias; nunca agregues rondas de relleno. Sus títulos deben describir la acción real de esa
  ronda (por ejemplo: comparar ofertas, responder a una variación,
  priorizar controles); no reutilices fases genéricas por costumbre.
- Cada ronda representa una decisión o aplicación distinta. Agrega datos o consecuencias
  nuevas para que no se repitan las mismas alternativas sin motivo.
- Configura el modo de cada ronda: "elegir", "escribir" o "hibrido". Usa "hibrido" cuando
  corresponda elegir y justificar; "escribir" solo cuando una respuesta construida sea
  indispensable para demostrar el aprendizaje.
- En las rondas de modo "elegir" o "hibrido", las decisiones sugeridas deben indicar
  "numero_ronda" y ofrecer 3 o 4 alternativas comparables. Ninguna puede ser superior en
  todos los criterios. Una ronda de escritura puede no tener alternativas predefinidas.
- Los cálculos y conceptos son evidencia para decidir, no ejercicios aislados.
- Usa entre 4 y 6 indicadores propios de la materia. Todo impacto debe usar exclusivamente
  sus códigos y ser determinista.
- En cada ronda incluye propósito de aprendizaje, situación, etiquetas de los campos,
  si la justificación es obligatoria y qué bloques de interfaz deben mostrarse.
- Activa pronóstico, trade-off, reflexión o investigación solo si aportan al aprendizaje de
  esa ronda; de forma predeterminada deben estar desactivados.
- Los conceptos esperados de cada ronda deben tener pesos que sumen 100 y describir evidencia
  observable, no palabras genéricas.
- El objetivo y el resultado de aprendizaje deben indicar qué decisión profesional podrá
  tomar el estudiante y con qué evidencia se comprobará.
- Devuelve únicamente JSON válido conforme al esquema solicitado, sin texto adicional.
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
                        'direccion_optima': {'type': 'string', 'enum': ['ALTO', 'BAJO', 'OBJETIVO', 'RANGO']},
                        'valor_objetivo': {'type': ['number', 'null']},
                        'valor_objetivo_min': {'type': ['number', 'null']},
                        'valor_objetivo_max': {'type': ['number', 'null']},
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
                        'numero': {'type': 'integer'},
                        'titulo': {'type': 'string'},
                        'proposito': {'type': 'string'},
                        'situacion': {'type': 'string'},
                        'modo': {'type': 'string', 'enum': ['elegir', 'escribir', 'hibrido']},
                        'etiqueta_decision': {'type': 'string'},
                        'etiqueta_justificacion': {'type': 'string'},
                        'justificacion_obligatoria': {'type': 'boolean'},
                        'mostrar_objetivos': {'type': 'boolean'},
                        'mostrar_rubrica': {'type': 'boolean'},
                        'mostrar_datos_caso': {'type': 'boolean'},
                        'mostrar_resultados_alternativas': {'type': 'boolean'},
                        'mostrar_indicadores': {'type': 'boolean'},
                        'mostrar_recursos': {'type': 'boolean'},
                        'mostrar_investigaciones': {'type': 'boolean'},
                        'pedir_pronostico': {'type': 'boolean'},
                        'pedir_tradeoff': {'type': 'boolean'},
                        'pedir_reflexion': {'type': 'boolean'},
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
                    'required': [
                        'numero', 'titulo', 'proposito', 'situacion', 'modo',
                        'etiqueta_decision', 'etiqueta_justificacion',
                        'justificacion_obligatoria', 'mostrar_objetivos',
                        'mostrar_rubrica', 'mostrar_datos_caso',
                        'mostrar_resultados_alternativas', 'mostrar_indicadores',
                        'mostrar_recursos', 'mostrar_investigaciones',
                        'pedir_pronostico', 'pedir_tradeoff', 'pedir_reflexion',
                        'conceptos_esperados',
                    ],
                    'additionalProperties': False,
                },
            },
            'decisiones_sugeridas': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                        'numero_ronda': {'type': 'integer'},
                        'texto': {'type': 'string'},
                        'descripcion': {'type': 'string'},
                        'impacto_base': {'type': 'object'},
                    },
                    'required': ['numero_ronda', 'texto', 'descripcion', 'impacto_base'],
                    'additionalProperties': False,
                },
            },
        },
        'required': [
            'titulo', 'tema', 'rol_estudiante', 'contexto', 'objetivo',
            'resultado_aprendizaje', 'situacion_inicial',
            'indicadores', 'restricciones', 'rondas', 'decisiones_sugeridas',
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

    rondas_data = [
        {**ronda, 'numero': numero}
        for numero, ronda in enumerate(data.get('rondas') or [], 1)
        if isinstance(ronda, dict)
    ]
    if not rondas_data:
        raise ValueError('La IA no genero ninguna ronda util.')
    cantidad_rondas = len(rondas_data)
    numeros_ronda = set(range(1, cantidad_rondas + 1))

    simulacion = Simulacion.objects.create(
        materia_malla=materia_malla,
        profesor=profesor,
        tipo_simulacion=Simulacion.TIPO_CON_IA_DINAMICA,
        titulo=data['titulo'],
        tema=data.get('tema', ''),
        nivel_dificultad=dificultad,
        maximo_decisiones=cantidad_rondas,
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
                    'numero': int(r['numero']),
                    'titulo': r['titulo'],
                    'proposito': r.get('proposito') or r.get('pregunta', ''),
                    'situacion': r.get('situacion') or r.get('pregunta', ''),
                    'modo': r.get('modo', 'hibrido'),
                    'etiqueta_decision': r.get('etiqueta_decision', 'Tu respuesta'),
                    'etiqueta_justificacion': r.get(
                        'etiqueta_justificacion', 'Explica tu razonamiento',
                    ),
                    'justificacion_obligatoria': bool(
                        r.get('justificacion_obligatoria', True)
                    ),
                    'mostrar_objetivos': bool(r.get('mostrar_objetivos', True)),
                    'mostrar_rubrica': bool(r.get('mostrar_rubrica', True)),
                    'mostrar_datos_caso': bool(r.get('mostrar_datos_caso', True)),
                    'mostrar_resultados_alternativas': bool(
                        r.get('mostrar_resultados_alternativas', False)
                    ),
                    'mostrar_indicadores': bool(r.get('mostrar_indicadores', True)),
                    'mostrar_recursos': bool(r.get('mostrar_recursos', True)),
                    'mostrar_investigaciones': bool(
                        r.get('mostrar_investigaciones', False)
                    ),
                    'pedir_pronostico': bool(r.get('pedir_pronostico', False)),
                    'pedir_tradeoff': bool(r.get('pedir_tradeoff', False)),
                    'pedir_reflexion': bool(r.get('pedir_reflexion', False)),
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
            valor_objetivo=(
                Decimal(str(ind['valor_objetivo']))
                if ind.get('valor_objetivo') is not None else None
            ),
            valor_objetivo_min=(
                Decimal(str(ind['valor_objetivo_min']))
                if ind.get('valor_objetivo_min') is not None else None
            ),
            valor_objetivo_max=(
                Decimal(str(ind['valor_objetivo_max']))
                if ind.get('valor_objetivo_max') is not None else None
            ),
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

    total_rondas = max(1, len(rondas_data))
    peso_base = Decimal('100') // Decimal(total_rondas)
    peso_acumulado = Decimal('0')
    for indice, ronda in enumerate(rondas_data):
        peso_criterio = (
            Decimal('100') - peso_acumulado
            if indice == total_rondas - 1
            else peso_base
        )
        CriterioEvaluacion.objects.create(
            simulacion=simulacion,
            nombre=ronda.get('titulo', f'Ronda {ronda["numero"]}'),
            descripcion=ronda.get('proposito') or ronda.get('pregunta', ''),
            peso=peso_criterio,
            puntaje_maximo=100,
            usuario_creacion=profesor,
        )
        peso_acumulado += peso_criterio

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
        numero_ronda = int(decision.get('numero_ronda') or 1)
        if numero_ronda not in numeros_ronda:
            continue
        AccionSugeridaSimulacion.objects.create(
            simulacion=simulacion,
            numero_ronda=numero_ronda,
            texto=decision.get('texto', ''),
            descripcion=decision.get('descripcion', ''),
            impacto_base=decision.get('impacto_base', {}),
            usuario_creacion=profesor,
        )

    return simulacion
