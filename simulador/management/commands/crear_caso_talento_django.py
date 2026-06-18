"""Caso REAL de Talento Humano: la empresa debe contratar UN desarrollador Django
entre 3 candidatos con perfiles casi identicos en papel. El reto es definir
criterios medibles y una prueba tecnica para diferenciarlos (no decidir por
'intuicion'). Indicadores propios de seleccion de talento. Idempotente.

Uso: python manage.py crear_caso_talento_django
"""
import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from academico.models import MateriaMalla
from simulador.management.commands.crear_mallas_fisei import _crear_simulacion
from simulador.models import (
    AccionSugeridaSimulacion,
    ConceptoEsperadoRonda,
    MatrizEvaluacionCaso,
    OpcionCasoSimulacion,
    RecursoSimulacion,
    Simulacion,
)

User = get_user_model()


def _r(*p):
    return json.dumps({'any': list(p)}, ensure_ascii=False)


def _regla(obligatorias=None, alternativas=None, prohibidas=None):
    regla = {}
    if obligatorias:
        regla['all'] = list(obligatorias)
    if alternativas:
        regla['any'] = list(alternativas)
    if prohibidas:
        regla['none'] = list(prohibidas)
    return json.dumps(regla, ensure_ascii=False)


# Indicadores propios de seleccion/talento (nada generico).
IND = [
    ('ajuste_perfil', 'Ajuste al perfil del puesto', 50, 0, 100, 'ALTO', '%', True),
    ('competencia_tecnica', 'Competencia tecnica (Django)', 50, 0, 100, 'ALTO', '%', True),
    ('riesgo_rotacion', 'Riesgo de rotacion', 55, 0, 100, 'BAJO', '%', True),
    ('tiempo_productividad', 'Tiempo a productividad', 10, 1, 16, 'BAJO', 'sem', False),
    ('costo_contratacion', 'Costo de contratacion', 1350, 800, 2000, 'BAJO', 'USD', False),
    ('clima_equipo', 'Encaje con el equipo', 50, 0, 100, 'ALTO', '%', False),
]
RES = [
    ('El candidato debe ajustarse al perfil (>= 70%).', 'ajuste_perfil', '>=', 70, 12),
    ('La competencia tecnica en Django debe ser >= 70%.', 'competencia_tecnica', '>=', 70, 12),
    ('El riesgo de rotacion debe quedar <= 40%.', 'riesgo_rotacion', '<=', 40, 10),
    ('El tiempo a productividad debe ser <= 6 semanas.', 'tiempo_productividad', '<=', 6, 6),
]
ACC = [
    (1, 'Aplicar prueba integral: code review, mini feature Django, ORM, testing y entrevista por competencias',
     'Evalua evidencia tecnica real y competencias del puesto.',
     {'competencia_tecnica': 18, 'ajuste_perfil': 15, 'riesgo_rotacion': -8, 'tiempo_productividad': -2},
     {'tiempo': 2, 'presupuesto': 12, 'capacidad_equipo': 8}),
    (1, 'Hacer solo entrevista informal con preguntas generales',
     'No genera evidencia tecnica suficiente para comparar candidatos.',
     {'ajuste_perfil': -8, 'competencia_tecnica': -10, 'riesgo_rotacion': 8},
     {'tiempo': 1, 'presupuesto': 2, 'capacidad_equipo': 2}),
    (1, 'Aplicar solo ejercicios teoricos de Python en pizarra',
     'Mide parte de la base tecnica, pero no valida Django aplicado al puesto.',
     {'competencia_tecnica': 6, 'ajuste_perfil': -2, 'tiempo_productividad': 1},
     {'tiempo': 1, 'presupuesto': 4, 'capacidad_equipo': 3}),

    (2, 'Contratar a Ana Reyes',
     'Perfil equilibrado: testing fuerte, comunicacion estable y riesgo bajo.',
     {'ajuste_perfil': 25, 'competencia_tecnica': 20, 'riesgo_rotacion': -20, 'clima_equipo': 10, 'tiempo_productividad': -4},
     {'tiempo': 1, 'presupuesto': 14, 'capacidad_equipo': 4}),
    (2, 'Contratar a Luis Carrion',
     'Muy fuerte en DRF y velocidad, pero con deuda en testing/documentacion.',
     {'ajuste_perfil': 10, 'competencia_tecnica': 18, 'riesgo_rotacion': 8, 'clima_equipo': -4, 'tiempo_productividad': -2, 'costo_contratacion': -50},
     {'tiempo': 1, 'presupuesto': 13, 'capacidad_equipo': 4}),
    (2, 'Contratar a Marta Sanchez',
     'Muy fuerte en BD/ORM, pero requiere acompanamiento en comunicacion.',
     {'ajuste_perfil': 8, 'competencia_tecnica': 14, 'riesgo_rotacion': 4, 'clima_equipo': -8, 'tiempo_productividad': -1, 'costo_contratacion': 50},
     {'tiempo': 1, 'presupuesto': 15, 'capacidad_equipo': 5}),
    (2, 'Contratar al candidato de menor salario sin ponderar la prueba tecnica',
     'Prioriza costo inmediato por encima de evidencia tecnica y ajuste.',
     {'ajuste_perfil': -12, 'competencia_tecnica': -10, 'riesgo_rotacion': 18, 'costo_contratacion': -50},
     {'tiempo': 1, 'presupuesto': 10, 'capacidad_equipo': 2}),

    (3, 'Ejecutar onboarding 30-60-90 con mentor, objetivos, feedback y plan de carrera',
     'Acelera productividad y reduce riesgo de salida temprana.',
     {'tiempo_productividad': -4, 'riesgo_rotacion': -16, 'clima_equipo': 12, 'ajuste_perfil': 8},
     {'tiempo': 4, 'presupuesto': 18, 'capacidad_equipo': 10}),
    (3, 'Hacer una induccion de un dia y asignar tareas sin seguimiento',
     'Arranca rapido, pero deja brechas de acompanamiento y medicion.',
     {'tiempo_productividad': 2, 'riesgo_rotacion': 8, 'clima_equipo': -5},
     {'tiempo': 1, 'presupuesto': 4, 'capacidad_equipo': 2}),
    (3, 'Ofrecer aumento salarial sin mentor ni metas de desempeno',
     'Ayuda parcialmente a retencion, pero no resuelve productividad ni seguimiento.',
     {'riesgo_rotacion': -4, 'costo_contratacion': 120, 'tiempo_productividad': 1},
     {'tiempo': 1, 'presupuesto': 25, 'capacidad_equipo': 1}),
]
CONC = [
    (1, 'Definicion del perfil y criterios medibles', 35, True,
     _r('perfil', 'criterios', 'requisitos', 'competencias', 'medible', 'rubrica', 'descripcion del puesto', 'ponderado'),
     {'ajuste_perfil': 15, 'riesgo_rotacion': -5}, {'ajuste_perfil': -8}),
    (1, 'Metodo de evaluacion objetivo', 30, True,
     _r('prueba tecnica', 'code review', 'entrevista', 'estructurada', 'competencias', 'evidencia', 'evaluacion'),
     {'competencia_tecnica': 12, 'ajuste_perfil': 5}, {'competencia_tecnica': -6}),
    (1, 'Identificar diferenciadores reales', 20, False,
     _r('diferencia', 'testing', 'escalabilidad', 'drf', 'consultas', 'documentacion', 'comunicacion', 'django'),
     {'competencia_tecnica': 6}, {}),
    (1, 'Justificacion con datos del puesto', 15, False,
     _r('porque', 'dato', 'requisito', 'negocio', 'necesidad'),
     {'ajuste_perfil': 3}, {}),

    (2, 'Decision basada en criterios', 30, True,
     _regla(
         obligatorias=['elijo'],
         alternativas=['criterio', 'perfil', 'resultado', 'prueba', 'cumple', 'seleccion'],
         prohibidas=['mas barato sin ponderar'],
     ),
     {'ajuste_perfil': 20, 'competencia_tecnica': 8}, {'ajuste_perfil': -10}),
    (2, 'Evaluacion tecnica (Django)', 30, True,
     _regla(
         obligatorias=['django'],
         alternativas=['testing', 'drf', 'orm', 'code review', 'mini feature', 'prueba tecnica', 'calidad'],
     ),
     {'competencia_tecnica': 18, 'tiempo_productividad': -2}, {'competencia_tecnica': -6}),
    (2, 'Gestion de costo y riesgo de rotacion', 20, False,
     _regla(
         obligatorias=['riesgo'],
         alternativas=['rotacion', 'salario', 'costo', 'presupuesto', 'retencion'],
     ),
     {'costo_contratacion': -120, 'riesgo_rotacion': -8}, {}),
    (2, 'Justificacion objetiva sin sesgo', 20, False,
     _regla(
         obligatorias=['compar'],
         alternativas=['evidencia', 'objetivo', 'criterio', 'resultado', 'puntaje', 'datos'],
     ),
     {'clima_equipo': 8}, {}),

    (3, 'Plan de onboarding', 30, True,
     _r('onboarding', 'induccion', 'mentor', 'plan', 'primeras semanas', 'objetivos', 'acompanamiento'),
     {'tiempo_productividad': -3, 'ajuste_perfil': 8}, {'tiempo_productividad': 2}),
    (3, 'Retencion y plan de carrera', 25, True,
     _r('retencion', 'plan de carrera', 'crecimiento', 'feedback', 'salario', 'clima', 'reconocimiento'),
     {'riesgo_rotacion': -12, 'clima_equipo': 10}, {'riesgo_rotacion': 5}),
    (3, 'Seguimiento del desempeno', 25, False,
     _r('seguimiento', 'kpi', 'objetivos', 'evaluacion', 'periodo de prueba', 'metas'),
     {'competencia_tecnica': 6, 'ajuste_perfil': 5}, {}),
    (3, 'Mejora del proceso de seleccion', 20, False,
     _r('mejora', 'leccion', 'documentacion', 'proceso', 'correctiva'),
     {'clima_equipo': 5}, {}),
]

CANDIDATOS = [
    {'nombre': 'Ana Reyes', 'edad': 27, 'experiencia': '3 anios, Django intermedio',
     'salario_pretendido': 1350, 'fortalezas': 'Ordenada, escribe pruebas (testing)',
     'debilidades': 'Poca experiencia en escalabilidad',
     'prueba': {'mini_feature': 84, 'code_review': 82, 'testing': 88, 'orm': 76, 'drf': 70, 'comunicacion': 82, 'riesgo_rotacion': 30}},
    {'nombre': 'Luis Carrion', 'edad': 28, 'experiencia': '3 anios, Django intermedio',
     'salario_pretendido': 1300, 'fortalezas': 'Rapido, domina Django REST Framework',
     'debilidades': 'Poco testing y documentacion floja',
     'prueba': {'mini_feature': 86, 'code_review': 78, 'testing': 45, 'orm': 72, 'drf': 92, 'comunicacion': 68, 'riesgo_rotacion': 48}},
    {'nombre': 'Marta Sanchez', 'edad': 26, 'experiencia': '3 anios, Django intermedio',
     'salario_pretendido': 1400, 'fortalezas': 'Excelente diseno de BD y consultas (ORM)',
     'debilidades': 'Comunicacion y trabajo en equipo a mejorar',
     'prueba': {'mini_feature': 78, 'code_review': 80, 'testing': 72, 'orm': 90, 'drf': 74, 'comunicacion': 55, 'riesgo_rotacion': 42}},
]

PRUEBA_TECNICA = [
    {'criterio': 'Mini feature Django', 'peso': 25, 'evalua': 'modelo, vista/API, validaciones y entrega funcional'},
    {'criterio': 'Code review', 'peso': 20, 'evalua': 'legibilidad, arquitectura, manejo de errores y seguridad'},
    {'criterio': 'Testing', 'peso': 20, 'evalua': 'pruebas unitarias, casos borde e integracion basica'},
    {'criterio': 'ORM y base de datos', 'peso': 15, 'evalua': 'consultas, indices, relaciones y N+1'},
    {'criterio': 'DRF/API', 'peso': 10, 'evalua': 'serializers, permisos, endpoints y paginacion'},
    {'criterio': 'Comunicacion tecnica', 'peso': 10, 'evalua': 'explicar decisiones y recibir feedback'},
]

CONTEXTO = (
    'TechAndes, una startup de software, necesita contratar UN desarrollador Django para su equipo. Llegaron 3 '
    'finalistas con perfiles casi identicos en papel: los tres tienen 3 anios de experiencia y nivel "Django '
    'intermedio". Como Analista de Talento Humano, no puedes decidir por intuicion: debes definir criterios medibles '
    'y una prueba tecnica que revele las diferencias reales, elegir con evidencia y planificar su incorporacion. '
    'Indicadores iniciales del proceso: ajuste al perfil 50%, competencia tecnica 50%, riesgo de rotacion 55%.'
)
SIT = (
    'TechAndes te pide un informe en tres etapas. Primero: elige como evaluarias a los finalistas. El puesto requiere '
    'Django, DRF, ORM, testing y comunicacion con el equipo. Debes definir criterios medibles y una prueba tecnica real '
    'para diferenciar a candidatos parecidos. Justifica con datos del puesto.'
)
RONDAS = [
    {'numero': 1, 'titulo': 'Escoger prueba tecnica', 'situacion': SIT,
     'etiqueta_decision': 'Prueba de seleccion', 'etiqueta_justificacion': 'Justificacion de la prueba'},
    {'numero': 2, 'titulo': 'Elegir candidato',
     'situacion': ('Resultados de la prueba: Ana Reyes obtuvo mini feature 84, code review 82, testing 88, ORM 76, '
                   'DRF 70, comunicacion 82 y riesgo de rotacion 30. Luis Carrion obtuvo mini feature 86, code review 78, '
                   'testing 45, ORM 72, DRF 92, comunicacion 68 y riesgo 48. Marta Sanchez obtuvo mini feature 78, '
                   'code review 80, testing 72, ORM 90, DRF 74, comunicacion 55 y riesgo 42. Decide a quien contratar '
                   'y justifica con criterios, competencia Django, costo, encaje y riesgo de rotacion.'),
     'etiqueta_decision': 'Candidato elegido', 'etiqueta_justificacion': 'Justificacion de contratacion'},
    {'numero': 3, 'titulo': 'Onboarding y retencion',
     'situacion': ('Ya elegiste. Disena el plan de incorporacion (onboarding con mentor), el seguimiento del desempeno '
                   'en el periodo de prueba y un plan de retencion/carrera para que no se vaya pronto.'),
     'etiqueta_decision': 'Plan de incorporacion', 'etiqueta_justificacion': 'Justificacion del plan'},
]


def _recrear_acciones(simulacion, profesor):
    simulacion.acciones_sugeridas.all().delete()
    for ronda, texto, descripcion, impacto, costo in ACC:
        AccionSugeridaSimulacion.objects.create(
            simulacion=simulacion,
            numero_ronda=ronda,
            texto=texto,
            descripcion=descripcion,
            impacto_base=impacto,
            costo_recursos=costo,
            usuario_creacion=profesor,
        )


def _recrear_conceptos(simulacion, profesor):
    simulacion.conceptos_esperados.all().delete()
    for ronda, nombre, peso, critico, regla, impacto_ok, impacto_fail in CONC:
        ConceptoEsperadoRonda.objects.create(
            simulacion=simulacion,
            numero_ronda=ronda,
            nombre=nombre,
            descripcion=f'{nombre} aplicado a {simulacion.materia_malla.materia.nombre}.',
            palabras_clave=regla,
            regla_evaluacion=json.loads(regla),
            peso=peso,
            impacto_si_cumple=impacto_ok,
            impacto_si_falta=impacto_fail,
            retroalimentacion_si_cumple=f'Cumple: {nombre}.',
            retroalimentacion_si_falta=f'Falta: {nombre}.',
            es_critico=critico,
            usuario_creacion=profesor,
        )


def _recrear_recursos(simulacion, profesor):
    recursos = [
        ('presupuesto', 'Presupuesto del proceso', 100, 0, 100, 'pts', True),
        ('tiempo', 'Semanas disponibles', 12, 0, 12, 'sem', True),
        ('capacidad_equipo', 'Horas del equipo evaluador', 40, 0, 40, 'h', False),
    ]
    simulacion.recursos.exclude(codigo__in=[r[0] for r in recursos]).delete()
    for codigo, nombre, inicial, minimo, maximo, unidad, critico in recursos:
        RecursoSimulacion.objects.update_or_create(
            simulacion=simulacion,
            codigo=codigo,
            defaults={
                'nombre': nombre,
                'valor_inicial': inicial,
                'valor_minimo': minimo,
                'valor_maximo': maximo,
                'unidad': unidad,
                'es_critico': critico,
                'activo': True,
                'usuario_creacion': profesor,
            },
        )


def _resultados_candidato(item):
    prueba = item.get('prueba') or {}
    return [
        {'criterio': 'Mini', 'valor': prueba.get('mini_feature', '')},
        {'criterio': 'Review', 'valor': prueba.get('code_review', '')},
        {'criterio': 'Testing', 'valor': prueba.get('testing', '')},
        {'criterio': 'ORM', 'valor': prueba.get('orm', '')},
        {'criterio': 'DRF', 'valor': prueba.get('drf', '')},
        {'criterio': 'Com.', 'valor': prueba.get('comunicacion', '')},
        {'criterio': 'Rot.', 'valor': prueba.get('riesgo_rotacion', '')},
    ]


def _recrear_datos_caso(simulacion, profesor):
    simulacion.matriz_caso.all().delete()
    for idx, item in enumerate(PRUEBA_TECNICA, start=1):
        MatrizEvaluacionCaso.objects.create(
            simulacion=simulacion,
            criterio=item['criterio'],
            peso=item['peso'],
            evalua=item['evalua'],
            orden=idx,
            usuario_creacion=profesor,
        )
    simulacion.opciones_caso.all().delete()
    for idx, item in enumerate(CANDIDATOS, start=1):
        OpcionCasoSimulacion.objects.create(
            simulacion=simulacion,
            nombre=item['nombre'],
            subtitulo=item['experiencia'],
            valor_referencia=str(item['salario_pretendido']),
            fortaleza=item['fortalezas'],
            riesgo=item['debilidades'],
            resultados=_resultados_candidato(item),
            orden=idx,
            usuario_creacion=profesor,
        )


class Command(BaseCommand):
    help = 'Crea el caso real de Talento Humano (contratar 1 de 3 desarrolladores Django).'

    @transaction.atomic
    def handle(self, *args, **options):
        profesor = User.objects.filter(is_staff=True, is_active=True).first() or User.objects.filter(is_active=True).first()
        mm = (MateriaMalla.objects.filter(materia__nombre__icontains='Talento', activo=True).first()
              or MateriaMalla.objects.filter(materia__nombre__icontains='Humano', activo=True).first())
        if not mm:
            self.stderr.write(self.style.ERROR('No encontre una materia de Talento Humano. Corre crear_simulaciones para la malla ADM.'))
            return

        titulo = 'Contratar 1 de 3 desarrolladores Django en TechAndes'
        sim = _crear_simulacion(
            mm, profesor,
            titulo=titulo,
            tema='seleccion de talento por competencias y prueba tecnica',
            rol='Analista de Talento Humano de TechAndes',
            contexto=CONTEXTO,
            objetivo=('Definir criterios medibles y una evaluacion objetiva (prueba tecnica Django + competencias) para '
                      'elegir entre 3 candidatos casi identicos, gestionando costo y riesgo de rotacion, y planificar '
                      'su incorporacion.'),
            resultado=('El estudiante toma una decision de contratacion sustentada con criterios y evidencia (no sesgo), '
                       'midiendo ajuste al perfil, competencia tecnica, costo y riesgo, con un plan de onboarding y retencion.'),
            sit_inicial=SIT, rondas=RONDAS, indicadores=IND, restricciones=RES, acciones=[], conceptos=CONC,
            condiciones=[('Alto ajuste al perfil', 'ajuste_perfil', '>=', 85, 5),
                         ('Bajo riesgo de rotacion', 'riesgo_rotacion', '<=', 25, 5)],
            empresa='TechAndes', area='Gestion del Talento Humano')

        sim_actual = sim or Simulacion.objects.filter(materia_malla=mm, titulo=titulo).first()
        if sim_actual:
            params = dict(sim_actual.parametros or {})
            params['candidatos'] = CANDIDATOS
            params['prueba_tecnica'] = PRUEBA_TECNICA
            params['rondas'] = RONDAS
            sim_actual.parametros = params
            sim_actual.contexto = CONTEXTO
            sim_actual.objetivo = (
                'Definir criterios medibles y una evaluacion objetiva (prueba tecnica Django + competencias) para '
                'elegir entre 3 candidatos casi identicos, gestionando costo y riesgo de rotacion, y planificar '
                'su incorporacion.'
            )
            sim_actual.resultado_aprendizaje = (
                'El estudiante toma una decision de contratacion sustentada con criterios y evidencia (no sesgo), '
                'midiendo ajuste al perfil, competencia tecnica, costo y riesgo, con un plan de onboarding y retencion.'
            )
            sim_actual.situacion_inicial = SIT
            sim_actual.estado = Simulacion.PUBLICADA
            sim_actual.activo = True
            sim_actual.save(update_fields=[
                'parametros', 'contexto', 'objetivo', 'resultado_aprendizaje',
                'situacion_inicial', 'estado', 'activo',
            ])
            _recrear_acciones(sim_actual, profesor)
            _recrear_conceptos(sim_actual, profesor)
            _recrear_recursos(sim_actual, profesor)
            _recrear_datos_caso(sim_actual, profesor)

        Simulacion.objects.filter(
            materia_malla=mm,
            activo=True,
            indicadores__codigo__in=['calidad_analisis', 'viabilidad', 'riesgo', 'impacto', 'claridad'],
        ).exclude(titulo=titulo).distinct().update(
            estado=Simulacion.ARCHIVADA,
            activo=False,
        )

        if sim:
            self.stdout.write(self.style.SUCCESS(
                f'Caso creado en "{mm.materia.nombre}": "{sim.titulo}" con {len(IND)} indicadores propios y 3 candidatos.'))
        else:
            self.stdout.write('El caso de Talento (Django) ya existia; simulaciones genericas archivadas.')
