import json, os, sys, time
from decimal import Decimal
from pathlib import Path

os.environ['DJANGO_SETTINGS_MODULE'] = 'settings'
sys.path.insert(0, os.path.dirname(__file__))
import django; django.setup()

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from academico.models import MateriaMalla
from simulador.models import (
    AccionSugeridaSimulacion, ConceptoEsperadoRonda,
    CriterioEvaluacion, IndicadorSimulacion, RestriccionSimulacion, Simulacion,
)

INDICADORES_MAPA = {
    "Administracion de la Produccion": "defectos_produccion, entregas_tardias, capacidad_utilizada, inventario, productividad, tiempo_ciclo",
    "Administracion de Operaciones": "defectos_produccion, entregas_tardias, capacidad_utilizada, inventario, productividad, tiempo_ciclo",
    "Administracion Estrategica": "participacion_mercado, crecimiento_ventas, ventaja_competitiva, cumplimiento_objetivos, posicionamiento, rentabilidad_estrategica",
    "Auditoria Administrativa": "hallazgos_auditoria, cumplimiento_procesos, observaciones_pendientes, mejora_implementada, riesgos_detectados, evidencias_revisadas",
    "Comercio Exterior e Integracion": "volumen_exportacion, costos_logisticos, documentos_aduaneros, acuerdos_aprovechados, cumplimiento_normativas, barreras_comerciales",
    "Desarrollo de Proyectos": "avance_proyecto, cumplimiento_hitos, desviacion_presupuesto, recursos_asignados, riesgos_proyecto, entregables_completados",
    "Diseno de Proyectos": "problema_definido, objetivos_planteados, metodologia_elegida, cronograma, presupuesto_estimado, viabilidad",
    "Diseno, Desarrollo de Productos y Gestion de Productos y Servicios": "tiempo_desarrollo, prototipos_validados, costo_desarrollo, aceptacion_mercado, lanzamiento_cumplido, retroalimentacion_usuario",
    "Emprendimiento": "inversion_inicial, demanda_estimada, margen_estimado, punto_equilibrio, validacion_mercado, costo_adquisicion_cliente",
    "Etica Empresarial y Responsabilidad Social": "riesgo_etico, impacto_social, cumplimiento_ambiental, reputacion_empresa, proveedores_evaluados, quejas_comunidad",
    "Gerencia de la Calidad": "tasa_defectos, reclamos_clientes, reprocesos, cumplimiento_estandares, satisfaccion_cliente, auditorias_calidad",
    "Habilidades Gerenciales": "comunicacion_equipo, resolucion_conflictos, liderazgo_percibido, delegacion_tareas, motivacion_equipo, cumplimiento_metas",
    "Investigacion Operativa": "costo_transporte, capacidad_recurso, tiempo_ruta, demanda_atendida, solucion_optima, recursos_utilizados",
    "MIPYMES, Marcas y Patentes": "marcas_registradas, patentes_tramite, proteccion_legal, costos_registro, competencia_informal, activos_intangibles",
    "Nuevas Tendencias en Administracion": "digitalizacion_procesos, automatizacion, adopcion_innovacion, eficiencia_tecnologica, ventas_digitales, procesos_modernizados",
    "Practicas de Servicio Comunitario": "horas_ejecutadas, beneficiarios_atendidos, plan_trabajo, evaluacion_impacto, materiales_gestionados, cumplimiento_convenio",
    "Practicas Laborales": "cumplimiento_actividades, horas_practica, evidencias_entregadas, mejora_propuesta, desempeno_practica, asistencia_practica",
    "Programacion Web con Django": "tiempo_respuesta, errores_500, consultas_sql, disponibilidad, seguridad, cobertura_pruebas",
    "Simulacion de Negocios": "utilidad, ventas, inventario, cuota_mercado, flujo_caja, satisfaccion_cliente",
    "Sistemas de Informacion Gerencial": "tiempo_reporte, errores_informacion, calidad_datos, disponibilidad_reportes, uso_tablero_gerencial, decisiones_sustentadas",
    "Titulacion": "avance_investigacion, cumplimiento_cronograma, revision_bibliografica, metodologia_definida, tutor_asignado, producto_entregable",
    "Valoracion de Empresas": "flujo_caja_proyectado, tasa_descuento, valor_empresa, activos_netos, pasivos, rentabilidad_futura",
}

base_prompt = Path('prompt_masivo.txt').read_text(encoding='utf-8')

from openai import OpenAI
client = OpenAI(api_key=settings.OPENAI_API_KEY)
model = getattr(settings, 'OPENAI_MODEL', 'gpt-5.5')
User = get_user_model()
profesor = User.objects.filter(is_staff=True, is_active=True).first() or User.objects.filter(is_active=True).first()

creadas_ids = set(Simulacion.objects.filter(activo=True).values_list('materia_malla_id', flat=True))
materias_pendientes = MateriaMalla.objects.filter(activo=True).exclude(pk__in=creadas_ids).select_related('materia').order_by('materia__nombre')

total = materias_pendientes.count()
print(f'Materias pendientes: {total}')

SCHEMA = {
    'type': 'object',
    'properties': {
        'simulaciones': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'titulo': {'type': 'string'}, 'materia': {'type': 'string'}, 'tema': {'type': 'string'},
                    'nivel_dificultad': {'type': 'string', 'enum': ['BAJA', 'MEDIA', 'ALTA']},
                    'tiempo_estimado': {'type': 'number'}, 'maximo_decisiones': {'type': 'number'},
                    'rol_estudiante': {'type': 'string'}, 'contexto': {'type': 'string'},
                    'objetivo': {'type': 'string'}, 'resultado_aprendizaje': {'type': 'string'},
                    'situacion_inicial': {'type': 'string'},
                    'indicadores': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'codigo': {'type': 'string'}, 'nombre': {'type': 'string'},
                                'valor_inicial': {'type': 'number'}, 'valor_minimo': {'type': 'number'},
                                'valor_maximo': {'type': 'number'},
                                'direccion_optima': {'type': 'string', 'enum': ['ALTO', 'BAJO']},
                                'unidad': {'type': 'string'}, 'es_critico': {'type': 'boolean'},
                            },
                            'required': ['codigo', 'nombre', 'valor_inicial', 'valor_minimo', 'valor_maximo', 'direccion_optima', 'unidad', 'es_critico'],
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
                                'etiqueta_decision': {'type': 'string'}, 'etiqueta_justificacion': {'type': 'string'},
                                'placeholder_respuesta': {'type': 'string'}, 'placeholder_justificacion': {'type': 'string'},
                                'conceptos_esperados': {
                                    'type': 'array',
                                    'items': {
                                        'type': 'object',
                                        'properties': {
                                            'nombre': {'type': 'string'}, 'descripcion': {'type': 'string'},
                                            'peso': {'type': 'number'}, 'es_critico': {'type': 'boolean'},
                                            'palabras_clave': {'type': 'string'},
                                        },
                                        'required': ['nombre', 'descripcion', 'peso', 'es_critico', 'palabras_clave'],
                                        'additionalProperties': False,
                                    },
                                },
                            },
                            'required': ['numero', 'titulo', 'pregunta', 'etiqueta_decision', 'etiqueta_justificacion', 'placeholder_respuesta', 'placeholder_justificacion', 'conceptos_esperados'],
                            'additionalProperties': False,
                        },
                    },
                    'decisiones_sugeridas': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'numero_ronda': {'type': 'number'}, 'texto': {'type': 'string'}, 'descripcion': {'type': 'string'},
                            },
                            'required': ['numero_ronda', 'texto', 'descripcion'],
                            'additionalProperties': False,
                        },
                    },
                    'respuestas_prueba': {
                        'type': 'object',
                        'properties': {
                            'mala': {'type': 'object', 'properties': {'ronda_1': {'type': 'string'}, 'ronda_2': {'type': 'string'}, 'ronda_3': {'type': 'string'}}, 'required': ['ronda_1', 'ronda_2', 'ronda_3'], 'additionalProperties': False},
                            'media': {'type': 'object', 'properties': {'ronda_1': {'type': 'string'}, 'ronda_2': {'type': 'string'}, 'ronda_3': {'type': 'string'}}, 'required': ['ronda_1', 'ronda_2', 'ronda_3'], 'additionalProperties': False},
                            'buena': {'type': 'object', 'properties': {'ronda_1': {'type': 'string'}, 'ronda_2': {'type': 'string'}, 'ronda_3': {'type': 'string'}}, 'required': ['ronda_1', 'ronda_2', 'ronda_3'], 'additionalProperties': False},
                        },
                        'required': ['mala', 'media', 'buena'], 'additionalProperties': False,
                    },
                },
                'required': ['titulo', 'materia', 'tema', 'nivel_dificultad', 'tiempo_estimado', 'maximo_decisiones', 'rol_estudiante', 'contexto', 'objetivo', 'resultado_aprendizaje', 'situacion_inicial', 'indicadores', 'restricciones', 'rondas', 'decisiones_sugeridas', 'respuestas_prueba'],
                'additionalProperties': False,
            },
        },
    },
    'required': ['simulaciones'],
    'additionalProperties': False,
}

if Simulacion.objects.filter(activo=True).count() >= 28:
    ids_ok = set(Simulacion.objects.filter(activo=True).values_list('materia_malla_id', flat=True))
    materias_pendientes = MateriaMalla.objects.filter(activo=True).exclude(pk__in=ids_ok).select_related('materia').order_by('materia__nombre')

ok = 0
for idx, mm in enumerate(materias_pendientes, 1):
    nombre = mm.materia.nombre
    indicadores = INDICADORES_MAPA.get(nombre, 'indicadores propios')
    prompt = base_prompt.format(materia=nombre, indicadores_mapa=indicadores)
    print(f'[{idx}/{total}] {nombre}... ', end='', flush=True)
    try:
        r = client.responses.create(model=model, input=prompt, text={'format': {'type': 'json_schema', 'name': 'sims', 'schema': SCHEMA, 'strict': True}}, reasoning={'effort': 'low'}, store=False, timeout=120)
        parsed = json.loads(r.output_text)
        sims_list = parsed.get('simulaciones', [])[:1]
        for sd in sims_list:
            with transaction.atomic():
                rd = sd.get('rondas', [])
                mr = max((x['numero'] for x in rd), default=3)
                s = Simulacion.objects.create(
                    materia_malla=mm, profesor=profesor,
                    tipo_simulacion=Simulacion.TIPO_CON_IA_DINAMICA,
                    titulo=sd.get('titulo',''), tema=sd.get('tema',''),
                    nivel_dificultad=sd.get('nivel_dificultad','MEDIA'),
                    maximo_decisiones=mr, tiempo_estimado=sd.get('tiempo_estimado',25),
                    rol_estudiante=sd.get('rol_estudiante',''),
                    contexto=sd.get('contexto',''), objetivo=sd.get('objetivo',''),
                    resultado_aprendizaje=sd.get('resultado_aprendizaje',''),
                    situacion_inicial=sd.get('situacion_inicial',''),
                    estado=Simulacion.PUBLICADA, fecha_publicacion=timezone.now(),
                    parametros={'modo': 'toma_decisiones', 'rondas': [{'numero': x['numero'], 'titulo': x['titulo'], 'proposito': x.get('pregunta',''), 'situacion': x.get('pregunta',''), 'etiqueta_decision': x.get('etiqueta_decision','Decision'), 'etiqueta_justificacion': x.get('etiqueta_justificacion','Justificacion'), 'placeholder_respuesta': x.get('placeholder_respuesta',''), 'placeholder_justificacion': x.get('placeholder_justificacion','')} for x in rd]},
                    metadata_generacion={'origen': 'completar'}, version_configuracion=1,
                    api_ia='responses', modelo_ia=model, usuario_creacion=profesor,
                )
                for i in sd.get('indicadores',[]):
                    IndicadorSimulacion.objects.create(simulacion=s, codigo=i['codigo'], nombre=i['nombre'],
                        valor_inicial=Decimal(str(i.get('valor_inicial',50))), valor_minimo=Decimal(str(i.get('valor_minimo',0))),
                        valor_maximo=Decimal(str(i.get('valor_maximo',100))), direccion_optima=i.get('direccion_optima','ALTO'),
                        es_critico=bool(i.get('es_critico',False)), unidad=i.get('unidad',''), usuario_creacion=profesor)
                for r in sd.get('restricciones',[]):
                    RestriccionSimulacion.objects.create(simulacion=s, descripcion=r['descripcion'], codigo_indicador=r['codigo_indicador'],
                        operador=r.get('operador','>='), valor_limite=Decimal(str(r.get('valor_limite',0))),
                        penalizacion=Decimal(str(r.get('penalizacion',10))), usuario_creacion=profesor)
                for ronda in rd:
                    CriterioEvaluacion.objects.create(simulacion=s, nombre=ronda.get('titulo',f'Ronda {ronda["numero"]}'),
                        descripcion=ronda.get('pregunta',''), peso=Decimal('100')/Decimal(max(1,mr)), puntaje_maximo=100, usuario_creacion=profesor)
                    for c in ronda.get('conceptos_esperados',[]):
                        palabras = c.get('palabras_clave','')
                        ConceptoEsperadoRonda.objects.create(simulacion=s, numero_ronda=ronda['numero'], nombre=c['nombre'],
                            descripcion=c.get('descripcion',''), palabras_clave=palabras,
                            regla_evaluacion={'any': [p.strip() for p in palabras.split(',') if p.strip()]},
                            peso=Decimal(str(c['peso'])), impacto_si_cumple={}, impacto_si_falta={},
                            es_critico=c.get('es_critico',False), usuario_creacion=profesor)
                for d in sd.get('decisiones_sugeridas',[]):
                    AccionSugeridaSimulacion.objects.create(simulacion=s, numero_ronda=d.get('numero_ronda',2),
                        texto=d.get('texto',''), descripcion=d.get('descripcion',''), impacto_base={}, usuario_creacion=profesor)
        ok += len(sims_list)
        print(f'OK (ID={s.pk})')
    except Exception as e:
        print(f'ERROR: {e}')
    time.sleep(1)

print(f'\nCompletado: {ok} nuevas, {len(creadas_ids)+ok} totales')
