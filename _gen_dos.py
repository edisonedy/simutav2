import os, sys, json, django
os.environ['DJANGO_SETTINGS_MODULE'] = 'settings'
sys.path.insert(0, os.path.dirname(__file__))
django.setup()

from decimal import Decimal
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from academico.models import MateriaMalla
from simulador.models import (
    AccionSugeridaSimulacion, ConceptoEsperadoRonda,
    CriterioEvaluacion, IndicadorSimulacion, RestriccionSimulacion, Simulacion,
)

PROMPT = open(os.path.join(os.path.dirname(__file__), 'prompt_dos.txt'), encoding='utf-8').read()

from openai import OpenAI
client = OpenAI(api_key=settings.OPENAI_API_KEY)
model = getattr(settings, 'OPENAI_MODEL', 'gpt-5.5')

respuesta = client.responses.create(
    model=model,
    input=PROMPT,
    text={
        'format': {
            'type': 'json_schema',
            'name': 'simulaciones_dobles',
            'schema': {
                'type': 'object',
                'properties': {
                    'simulaciones': {
                        'type': 'array', 'items': {'$ref': '#/$defs/simulacion'}
                    }
                },
                'required': ['simulaciones'],
                'additionalProperties': False,
                '$defs': {
                    'simulacion': {
                        'type': 'object',
                        'properties': {
                            'titulo': {'type': 'string'},
                            'materia': {'type': 'string'},
                            'tema': {'type': 'string'},
                            'nivel_dificultad': {'type': 'string', 'enum': ['BAJA', 'MEDIA', 'ALTA']},
                            'tiempo_estimado': {'type': 'number'},
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
                                        'codigo': {'type': 'string'}, 'nombre': {'type': 'string'},
                                        'valor_inicial': {'type': 'number'}, 'valor_minimo': {'type': 'number'},
                                        'valor_maximo': {'type': 'number'}, 'direccion_optima': {'type': 'string', 'enum': ['ALTO', 'BAJO']},
                                        'unidad': {'type': 'string'}, 'descripcion': {'type': 'string'},
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
                                        'descripcion': {'type': 'string'}, 'codigo_indicador': {'type': 'string'},
                                        'operador': {'type': 'string', 'enum': ['>', '>=', '<', '<=', '=']},
                                        'valor_limite': {'type': 'number'}, 'penalizacion': {'type': 'number'},
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
                                        'numero': {'type': 'number'}, 'titulo': {'type': 'string'}, 'pregunta': {'type': 'string'},
                                        'conceptos_esperados': {
                                            'type': 'array',
                                            'items': {
                                                'type': 'object',
                                                'properties': {
                                                    'nombre': {'type': 'string'}, 'descripcion': {'type': 'string'},
                                                    'peso': {'type': 'number'}, 'critico': {'type': 'boolean'},
                                                    'palabras_clave': {'type': 'string'},
                                                },
                                                'required': ['nombre', 'descripcion', 'peso', 'critico', 'palabras_clave'],
                                                'additionalProperties': False,
                                            },
                                        },
                                    },
                                    'required': ['numero', 'titulo', 'pregunta', 'conceptos_esperados'],
                                    'additionalProperties': False,
                                },
                            },
                            'decisiones_sugeridas': {
                                'type': 'array',
                                'items': {
                                    'type': 'object',
                                    'properties': {
                                        'texto': {'type': 'string'}, 'descripcion': {'type': 'string'},
                                    },
                                    'required': ['texto', 'descripcion'],
                                    'additionalProperties': False,
                                },
                            },
                        },
                        'required': ['titulo', 'materia', 'tema', 'nivel_dificultad', 'tiempo_estimado', 'rol_estudiante', 'contexto', 'objetivo', 'resultado_aprendizaje', 'situacion_inicial', 'indicadores', 'restricciones', 'rondas', 'decisiones_sugeridas'],
                        'additionalProperties': False,
                    },
                },
            },
            'strict': True,
        }
    },
    reasoning={'effort': 'low'},
    store=False,
    timeout=120,
)

data = json.loads(respuesta.output_text)
simulaciones_data = data['simulaciones']
print(f'Recibidas {len(simulaciones_data)} simulaciones de OpenAI')

User = get_user_model()
profesor = User.objects.filter(is_staff=True, is_active=True).first() or User.objects.filter(is_active=True).first()

mm = MateriaMalla.objects.filter(materia__nombre__icontains='talento humano', activo=True).first()
if not mm:
    mm = MateriaMalla.objects.filter(activo=True).first()

for i, sim_data in enumerate(simulaciones_data):
    with transaction.atomic():
        rondas_data = sim_data.get('rondas', [])
        max_rondas = max((r['numero'] for r in rondas_data), default=3)
        dif = sim_data.get('nivel_dificultad', 'MEDIA')

        s = Simulacion.objects.create(
            materia_malla=mm, profesor=profesor,
            tipo_simulacion=Simulacion.TIPO_CON_IA_DINAMICA,
            titulo=sim_data['titulo'], tema=sim_data.get('tema', ''),
            nivel_dificultad=dif, maximo_decisiones=max_rondas,
            tiempo_estimado=sim_data.get('tiempo_estimado', 25),
            rol_estudiante=sim_data.get('rol_estudiante', ''),
            contexto=sim_data.get('contexto', ''),
            objetivo=sim_data.get('objetivo', ''),
            resultado_aprendizaje=sim_data.get('resultado_aprendizaje', ''),
            situacion_inicial=sim_data.get('situacion_inicial', ''),
            estado=Simulacion.BORRADOR,
            parametros={'modo': 'toma_decisiones', 'rondas': [{'numero': r['numero'], 'titulo': r['titulo'], 'proposito': r.get('pregunta', ''), 'situacion': r.get('pregunta', '')} for r in rondas_data]},
            metadata_generacion={'origen': 'gen_dos', 'materia_malla_id': mm.id},
            version_configuracion=1, api_ia='responses',
            modelo_ia=model, usuario_creacion=profesor,
        )

        for ind in sim_data.get('indicadores', []):
            IndicadorSimulacion.objects.create(
                simulacion=s, codigo=ind['codigo'], nombre=ind['nombre'],
                valor_inicial=Decimal(str(ind.get('valor_inicial', 50))),
                valor_minimo=Decimal(str(ind.get('valor_minimo', 0))),
                valor_maximo=Decimal(str(ind.get('valor_maximo', 100))),
                direccion_optima=ind.get('direccion_optima', 'ALTO'),
                es_critico=False, unidad=ind.get('unidad', ''),
                usuario_creacion=profesor,
            )

        for res in sim_data.get('restricciones', []):
            RestriccionSimulacion.objects.create(
                simulacion=s, descripcion=res['descripcion'],
                codigo_indicador=res['codigo_indicador'],
                operador=res.get('operador', '>='),
                valor_limite=Decimal(str(res.get('valor_limite', 0))),
                penalizacion=Decimal(str(res.get('penalizacion', 10))),
                usuario_creacion=profesor,
            )

        for ronda in rondas_data:
            CriterioEvaluacion.objects.create(
                simulacion=s, nombre=ronda.get('titulo', f'Ronda {ronda["numero"]}'),
                descripcion=ronda.get('pregunta', ''),
                peso=Decimal('100') / Decimal(max(1, max_rondas)),
                puntaje_maximo=100, usuario_creacion=profesor,
            )
            for conc in ronda.get('conceptos_esperados', []):
                palabras = conc.get('palabras_clave', '')
                ConceptoEsperadoRonda.objects.create(
                    simulacion=s, numero_ronda=ronda['numero'],
                    nombre=conc['nombre'], descripcion=conc.get('descripcion', ''),
                    palabras_clave=palabras,
                    regla_evaluacion={'any': [p.strip() for p in palabras.split(',') if p.strip()]},
                    peso=Decimal(str(conc['peso'])), impacto_si_cumple={}, impacto_si_falta={},
                    es_critico=conc.get('critico', False), usuario_creacion=profesor,
                )

        for dec in sim_data.get('decisiones_sugeridas', []):
            AccionSugeridaSimulacion.objects.create(
                simulacion=s, numero_ronda=1,
                texto=dec.get('texto', ''), descripcion=dec.get('descripcion', ''),
                impacto_base={}, usuario_creacion=profesor,
            )

    print(f'  [{i+1}] Creada: ID={s.pk} - "{sim_data["titulo"]}"')

print('Listo.')
