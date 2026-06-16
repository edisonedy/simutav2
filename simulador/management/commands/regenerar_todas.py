import json
import logging
import os
import time
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from academico.models import MateriaMalla
from simulador.models import (
    AccionSugeridaSimulacion,
    ConceptoEsperadoRonda,
    CriterioEvaluacion,
    IndicadorSimulacion,
    IntentoSimulacion,
    RestriccionSimulacion,
    Simulacion,
)

logger = logging.getLogger(__name__)

INDICADORES_MAPA = {
    "Estadistica Descriptiva": "promedio_ventas, mediana_ventas, desviacion_estandar, rango_datos, coeficiente_variacion, datos_atipicos",
    "Contabilidad de Costos": "costo_unitario, costos_sobre_ventas, margen_bruto, margen_contribucion, punto_equilibrio, rotacion_inventario",
    "Procesos Administrativos": "tiempo_proceso, tareas_duplicadas, cumplimiento_actividades, eficiencia_operativa, responsables_definidos, retrasos_internos",
    "Derecho Laboral": "reclamos_laborales, contratos_incompletos, horas_extra_pendientes, riesgo_legal_laboral, cumplimiento_normativo, multas_potenciales",
    "Desarrollo y Comportamiento Organizacional": "clima_laboral, rotacion_personal, ausentismo, conflictos_internos, satisfaccion_colaboradores, liderazgo_equipo",
    "Metodologia de la Investigacion": "problema_definido, variables_identificadas, muestra_calculada, instrumentos_recoleccion, validez_datos, confiabilidad_instrumento",
    "Derecho Empresarial": "contratos_riesgosos, clausulas_incumplidas, multas_potenciales, cumplimiento_legal, riesgo_contractual, documentos_regularizados",
    "Administracion Financiera": "liquidez_corriente, flujo_caja, rentabilidad, endeudamiento, capital_trabajo, cartera_vencida",
    "Gestion y Administracion del Talento Humano": "rotacion_anual, ausentismo_laboral, clima_laboral, bajo_desempeno, quejas_laborales, retencion_talento",
    "Tecnologias de la Informacion y Comunicacion": "errores_datos, tiempo_reporte, procesos_manualizados, disponibilidad_sistema, adopcion_tecnologica, usuarios_capacitados",
    "Gerencia de la Calidad": "tasa_defectos, reclamos_clientes, reprocesos, cumplimiento_estandares, satisfaccion_cliente, auditorias_calidad",
    "Administracion de la Produccion": "defectos_produccion, entregas_tardias, capacidad_utilizada, inventario, productividad, tiempo_ciclo",
    "Etica Empresarial y Responsabilidad Social": "riesgo_etico, impacto_social, cumplimiento_ambiental, reputacion_empresa, proveedores_evaluados, quejas_comunidad",
    "Nuevas Tendencias en Administracion": "digitalizacion_procesos, automatizacion, adopcion_innovacion, eficiencia_tecnologica, ventas_digitales, procesos_modernizados",
    "Emprendimiento": "inversion_inicial, demanda_estimada, margen_estimado, punto_equilibrio, validacion_mercado, costo_adquisicion_cliente",
    "Investigacion Operativa": "costo_transporte, capacidad_recurso, tiempo_ruta, demanda_atendida, solucion_optima, recursos_utilizados",
    "Administracion Estrategica": "participacion_mercado, crecimiento_ventas, ventaja_competitiva, cumplimiento_objetivos, posicionamiento, rentabilidad_estrategica",
    "Simulacion de Negocios": "utilidad, ventas, inventario, cuota_mercado, flujo_caja, satisfaccion_cliente",
    "Sistemas de Informacion Gerencial": "tiempo_reporte, errores_informacion, calidad_datos, disponibilidad_reportes, uso_tablero_gerencial, decisiones_sustentadas",
    "Practicas Laborales": "cumplimiento_actividades, horas_practica, evidencias_entregadas, mejora_propuesta, desempeno_practica, asistencia_practica",
    "Programacion Web con Django": "tiempo_respuesta, errores_500, consultas_sql, disponibilidad, seguridad, cobertura_pruebas",
    "Toma de Decisiones Tecnicas": "costo_solucion, tiempo_implementacion, riesgo_tecnico, eficiencia_operativa, fallas_reducidas, impacto_operativo",
    "Toma de decisiones tecnicas": "costo_solucion, tiempo_implementacion, riesgo_tecnico, eficiencia_operativa, fallas_reducidas, impacto_operativo",
}


def _schema_simulacion_array():
    return {
        'type': 'object',
        'properties': {
            'simulaciones': {
                'type': 'array',
                'items': {
                    'type': 'object',
            'properties': {
                'titulo': {'type': 'string'},
                'materia': {'type': 'string'},
                'tema': {'type': 'string'},
                'nivel_dificultad': {'type': 'string', 'enum': ['BAJA', 'MEDIA', 'ALTA']},
                'tiempo_estimado': {'type': 'number'},
                'maximo_decisiones': {'type': 'number'},
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
                            'numero_ronda': {'type': 'number'},
                            'texto': {'type': 'string'}, 'descripcion': {'type': 'string'},
                        },
                        'required': ['numero_ronda', 'texto', 'descripcion'],
                        'additionalProperties': False,
                    },
                },
                'respuestas_prueba': {
                    'type': 'object',
                    'properties': {
                        'mala': {
                            'type': 'object',
                            'properties': {'ronda_1': {'type': 'string'}, 'ronda_2': {'type': 'string'}, 'ronda_3': {'type': 'string'}},
                            'required': ['ronda_1', 'ronda_2', 'ronda_3'], 'additionalProperties': False,
                        },
                        'media': {
                            'type': 'object',
                            'properties': {'ronda_1': {'type': 'string'}, 'ronda_2': {'type': 'string'}, 'ronda_3': {'type': 'string'}},
                            'required': ['ronda_1', 'ronda_2', 'ronda_3'], 'additionalProperties': False,
                        },
                        'buena': {
                            'type': 'object',
                            'properties': {'ronda_1': {'type': 'string'}, 'ronda_2': {'type': 'string'}, 'ronda_3': {'type': 'string'}},
                            'required': ['ronda_1', 'ronda_2', 'ronda_3'], 'additionalProperties': False,
                        },
                    },
                    'required': ['mala', 'media', 'buena'],
                    'additionalProperties': False,
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


class Command(BaseCommand):
    help = 'Elimina todas las simulaciones y regenera 2 por materia desde OpenAI con indicadores propios.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Solo muestra que se hara')
        parser.add_argument('--quick', action='store_true', help='Solo 1 simulacion por materia (mas rapido)')
        parser.add_argument('--force', action='store_true', help='Ejecuta sin confirmacion')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        quick = options['quick']
        force = options.get('force')

        api_key = getattr(settings, 'OPENAI_API_KEY', '') or ''
        if not api_key and not dry_run:
            self.stderr.write(self.style.ERROR('OPENAI_API_KEY no configurada'))
            return

        User = get_user_model()
        profesor = User.objects.filter(is_staff=True, is_active=True).first()
        if not profesor:
            profesor = User.objects.filter(is_active=True).first()
        if not profesor and not dry_run:
            self.stderr.write(self.style.ERROR('No hay usuarios activos'))
            return

        prompt_path = Path(__file__).resolve().parent.parent.parent.parent / 'prompt_masivo.txt'
        if not prompt_path.exists() and not dry_run:
            self.stderr.write(self.style.ERROR(f'No se encuentra prompt_masivo.txt en {prompt_path}'))
            return

        base_prompt = prompt_path.read_text(encoding='utf-8') if not dry_run else ''

        materias = MateriaMalla.objects.filter(activo=True).select_related(
            'materia', 'nivel', 'malla__carrera'
        ).order_by('malla__carrera__nombre', 'nivel__numero', 'materia__nombre')

        total = materias.count()
        sims_por_materia = 1 if quick else 2
        total_sims = total * sims_por_materia
        self.stdout.write(f'Materias: {total} | Simulaciones por materia: {sims_por_materia} | Total: {total_sims}')

        if dry_run:
            for mm in materias:
                ics = INDICADORES_MAPA.get(mm.materia.nombre, 'indicadores propios')
                self.stdout.write(f'  ID={mm.pk}: {mm.materia.nombre} -> {ics}')
            self.stdout.write(self.style.WARNING('Modo dry-run.'))
            return

        if not force:
            confirm = input(f'Se eliminaran intentos+simulaciones y se crearan {total_sims} nuevas. Confirmar? (si/N): ').strip().lower()
            if confirm != 'si':
                self.stdout.write('Cancelado.')
                return

        IntentoSimulacion.objects.all().delete()
        total_del = Simulacion.objects.count()
        Simulacion.objects.all().delete()
        self.stdout.write(self.style.SUCCESS(f'Eliminados intentos y {total_del} simulaciones.'))

        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        model = getattr(settings, 'OPENAI_MODEL', 'gpt-5.5')

        ok = 0
        errors = 0

        for idx, mm in enumerate(materias, 1):
            materia_nombre = mm.materia.nombre
            indicadores_mapa = INDICADORES_MAPA.get(materia_nombre, 'indicadores propios de la materia')

            prompt = base_prompt.format(materia=materia_nombre, indicadores_mapa=indicadores_mapa)
            prompt = prompt.replace('genera:\n1.', 'genera:\n1.')

            self.stdout.write(f'[{idx}/{total}] {materia_nombre}... ', ending='')
            self.stdout.flush()

            try:
                respuesta = client.responses.create(
                    model=model,
                    input=prompt,
                    text={
                        'format': {
                            'type': 'json_schema',
                            'name': 'simulaciones_materia',
                            'schema': _schema_simulacion_array(),
                            'strict': True,
                        }
                    },
                    reasoning={'effort': 'low'},
                    store=False,
                    timeout=120,
                )
                parsed = json.loads(respuesta.output_text)
                sims_list = parsed.get('simulaciones', [])
                if not isinstance(sims_list, list):
                    sims_list = [sims_list]
                sims_list = sims_list[:sims_por_materia]

                for sim_data in sims_list:
                    _crear_simulacion(sim_data, mm, profesor, model)

                ok += len(sims_list)
                self.stdout.write(self.style.SUCCESS(f'{len(sims_list)} creadas'))
            except Exception as e:
                errors += 1
                self.stdout.write(self.style.ERROR(f'ERROR: {e}'))
                logger.error(f'Error en {materia_nombre}: {e}')
                time.sleep(2)

            time.sleep(1)

        self.stdout.write('---')
        self.stdout.write(self.style.SUCCESS(f'OK: {ok}, Errores: {errors}'))


@transaction.atomic
def _crear_simulacion(data, materia_malla, profesor, model=''):
    rondas_data = data.get('rondas', [])
    max_rondas = max((r['numero'] for r in rondas_data), default=3)
    dif = data.get('nivel_dificultad', 'MEDIA')
    max_dec = data.get('maximo_decisiones', 3)

    s = Simulacion.objects.create(
        materia_malla=materia_malla,
        profesor=profesor,
        tipo_simulacion=Simulacion.TIPO_CON_IA_DINAMICA,
        titulo=data.get('titulo', ''),
        tema=data.get('tema', ''),
        nivel_dificultad=dif,
        maximo_decisiones=max_dec,
        tiempo_estimado=data.get('tiempo_estimado', 25),
        rol_estudiante=data.get('rol_estudiante', ''),
        contexto=data.get('contexto', ''),
        objetivo=data.get('objetivo', ''),
        resultado_aprendizaje=data.get('resultado_aprendizaje', ''),
        situacion_inicial=data.get('situacion_inicial', ''),
        estado=Simulacion.PUBLICADA,
        fecha_publicacion=timezone.now(),
        parametros={
            'modo': 'toma_decisiones',
            'rondas': [
                {
                    'numero': r['numero'], 'titulo': r['titulo'],
                    'proposito': r.get('pregunta', ''),
                    'situacion': r.get('pregunta', ''),
                    'etiqueta_decision': r.get('etiqueta_decision', 'Decision'),
                    'etiqueta_justificacion': r.get('etiqueta_justificacion', 'Justificacion'),
                    'placeholder_respuesta': r.get('placeholder_respuesta', ''),
                    'placeholder_justificacion': r.get('placeholder_justificacion', ''),
                }
                for r in rondas_data
            ],
        },
        metadata_generacion={'origen': 'regenerar_todas_v2', 'materia_malla_id': materia_malla.id},
        version_configuracion=1, api_ia='responses',
        modelo_ia=model, usuario_creacion=profesor,
    )

    for ind in data.get('indicadores', []):
        IndicadorSimulacion.objects.create(
            simulacion=s, codigo=ind['codigo'], nombre=ind['nombre'],
            valor_inicial=Decimal(str(ind.get('valor_inicial', 50))),
            valor_minimo=Decimal(str(ind.get('valor_minimo', 0))),
            valor_maximo=Decimal(str(ind.get('valor_maximo', 100))),
            direccion_optima=ind.get('direccion_optima', 'ALTO'),
            es_critico=bool(ind.get('es_critico', False)),
            unidad=ind.get('unidad', ''),
            usuario_creacion=profesor,
        )

    for res in data.get('restricciones', []):
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
            simulacion=s,
            nombre=ronda.get('titulo', f'Ronda {ronda["numero"]}'),
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
                es_critico=conc.get('es_critico', False), usuario_creacion=profesor,
            )

    for dec in data.get('decisiones_sugeridas', []):
        AccionSugeridaSimulacion.objects.create(
            simulacion=s, numero_ronda=dec.get('numero_ronda', 2),
            texto=dec.get('texto', ''), descripcion=dec.get('descripcion', ''),
            impacto_base={}, usuario_creacion=profesor,
        )

    return s
