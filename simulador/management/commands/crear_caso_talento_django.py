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

User = get_user_model()


def _r(*p):
    return json.dumps({'any': list(p)}, ensure_ascii=False)


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
    ('Aplicar una prueba tecnica practica (code review + mini feature en Django)',
     'Revela la diferencia real entre candidatos que en papel se ven iguales.',
     {'competencia_tecnica': 18, 'ajuste_perfil': 12, 'tiempo_productividad': -2}),
    ('Usar entrevista por competencias con criterios y rubrica ponderada',
     'Reduce el sesgo y mide encaje tecnico y de equipo de forma objetiva.',
     {'ajuste_perfil': 15, 'riesgo_rotacion': -10, 'clima_equipo': 8}),
    ('Definir onboarding con mentor y plan de retencion/carrera',
     'Acelera la productividad y baja el riesgo de que se vaya pronto.',
     {'tiempo_productividad': -3, 'riesgo_rotacion': -12, 'clima_equipo': 10}),
    ('Elegir al mas barato sin prueba tecnica para ahorrar tiempo',
     'Riesgoso: decides a ciegas, sube el riesgo de rotacion y mala contratacion.',
     {'riesgo_rotacion': 15, 'ajuste_perfil': -10, 'competencia_tecnica': -8}),
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
     _r('elijo', 'recomiendo', 'candidato', 'criterio', 'cumple', 'porque', 'seleccion'),
     {'ajuste_perfil': 20, 'competencia_tecnica': 8}, {'ajuste_perfil': -10}),
    (2, 'Evaluacion tecnica (Django)', 30, True,
     _r('django', 'codigo', 'prueba tecnica', 'testing', 'drf', 'consultas', 'orm', 'calidad', 'arquitectura'),
     {'competencia_tecnica': 18, 'tiempo_productividad': -2}, {'competencia_tecnica': -6}),
    (2, 'Gestion de costo y riesgo de rotacion', 20, False,
     _r('costo', 'salario', 'presupuesto', 'rotacion', 'riesgo', 'retencion'),
     {'costo_contratacion': -120, 'riesgo_rotacion': -8}, {}),
    (2, 'Justificacion objetiva sin sesgo', 20, False,
     _r('porque', 'evidencia', 'objetivo', 'sesgo', 'criterio', 'comparacion'),
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
     'debilidades': 'Poca experiencia en escalabilidad'},
    {'nombre': 'Luis Carrion', 'edad': 28, 'experiencia': '3 anios, Django intermedio',
     'salario_pretendido': 1300, 'fortalezas': 'Rapido, domina Django REST Framework',
     'debilidades': 'Poco testing y documentacion floja'},
    {'nombre': 'Marta Sanchez', 'edad': 26, 'experiencia': '3 anios, Django intermedio',
     'salario_pretendido': 1400, 'fortalezas': 'Excelente diseno de BD y consultas (ORM)',
     'debilidades': 'Comunicacion y trabajo en equipo a mejorar'},
]

CONTEXTO = (
    'TechAndes, una startup de software, necesita contratar UN desarrollador Django para su equipo. Llegaron 3 '
    'finalistas con perfiles casi identicos en papel: los tres tienen 3 anios de experiencia y nivel "Django '
    'intermedio". Como Analista de Talento Humano, no puedes decidir por intuicion: debes definir criterios medibles '
    'y una prueba tecnica que revele las diferencias reales, elegir con evidencia y planificar su incorporacion. '
    'Indicadores iniciales del proceso: ajuste al perfil 50%, competencia tecnica 50%, riesgo de rotacion 55%.'
)
SIT = (
    'TechAndes te pide un informe en tres etapas. Primero: como Analista de Talento Humano, define el perfil real del '
    'puesto, los criterios medibles (tecnicos y de equipo) y el metodo de evaluacion (prueba tecnica en Django, '
    'entrevista por competencias) que usarias para diferenciar a 3 candidatos casi iguales. Justifica con datos del puesto.'
)
RONDAS = [
    {'numero': 1, 'titulo': 'Definir perfil y criterios', 'situacion': SIT},
    {'numero': 2, 'titulo': 'Elegir candidato',
     'situacion': ('Aplicaste la prueba tecnica. Ahora decide a QUE candidato contratar y justifica con los criterios '
                   '(competencia Django, encaje, costo, riesgo de rotacion). Revisa los 3 perfiles y elige con evidencia, '
                   'no por intuicion.')},
    {'numero': 3, 'titulo': 'Onboarding y retencion',
     'situacion': ('Ya elegiste. Disena el plan de incorporacion (onboarding con mentor), el seguimiento del desempeno '
                   'en el periodo de prueba y un plan de retencion/carrera para que no se vaya pronto.')},
]


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

        sim = _crear_simulacion(
            mm, profesor,
            titulo='Contratar 1 de 3 desarrolladores Django en TechAndes',
            tema='seleccion de talento por competencias y prueba tecnica',
            rol='Analista de Talento Humano de TechAndes',
            contexto=CONTEXTO,
            objetivo=('Definir criterios medibles y una evaluacion objetiva (prueba tecnica Django + competencias) para '
                      'elegir entre 3 candidatos casi identicos, gestionando costo y riesgo de rotacion, y planificar '
                      'su incorporacion.'),
            resultado=('El estudiante toma una decision de contratacion sustentada con criterios y evidencia (no sesgo), '
                       'midiendo ajuste al perfil, competencia tecnica, costo y riesgo, con un plan de onboarding y retencion.'),
            sit_inicial=SIT, rondas=RONDAS, indicadores=IND, restricciones=RES, acciones=ACC, conceptos=CONC,
            condiciones=[('Alto ajuste al perfil', 'ajuste_perfil', '>=', 85, 5),
                         ('Bajo riesgo de rotacion', 'riesgo_rotacion', '<=', 25, 5)],
            empresa='TechAndes', area='Gestion del Talento Humano')

        if sim:
            # Los 3 candidatos se muestran en la pantalla (parametros.candidatos).
            params = dict(sim.parametros or {})
            params['candidatos'] = CANDIDATOS
            sim.parametros = params
            sim.save(update_fields=['parametros'])
            self.stdout.write(self.style.SUCCESS(
                f'Caso creado en "{mm.materia.nombre}": "{sim.titulo}" con {len(IND)} indicadores propios y 3 candidatos.'))
        else:
            self.stdout.write('El caso de Talento (Django) ya existia.')
