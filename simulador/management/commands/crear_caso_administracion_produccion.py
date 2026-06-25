"""Crea un caso real de Administracion de la Produccion con indicadores propios.

Uso: python manage.py crear_caso_administracion_produccion
"""
import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from academico.models import MateriaMalla
from simulador.management.commands.crear_mallas_fisei import _crear_simulacion
from simulador.models import Simulacion

User = get_user_model()


def _r(*palabras):
    return json.dumps({'any': list(palabras)}, ensure_ascii=False)


IND = [
    ('defectos_produccion', 'Defectos de produccion', 12, 0, 30, 'BAJO', '%', True),
    ('entregas_tardias', 'Entregas tardias', 22, 0, 50, 'BAJO', '%', True),
    ('capacidad_utilizada', 'Capacidad utilizada', 62, 0, 100, 'ALTO', '%', True),
    ('inventario_proceso', 'Inventario en proceso', 18, 0, 40, 'BAJO', 'dias', False),
    ('productividad_linea', 'Productividad de linea', 58, 0, 100, 'ALTO', 'u/h', True),
    ('tiempo_ciclo_min', 'Tiempo de ciclo', 42, 5, 90, 'BAJO', 'min', False),
]

RES = [
    ('Los defectos de produccion deben quedar en <= 4%.', 'defectos_produccion', '<=', 4, 12),
    ('Las entregas tardias deben bajar a <= 5%.', 'entregas_tardias', '<=', 5, 12),
    ('La capacidad utilizada debe llegar al menos a 80%.', 'capacidad_utilizada', '>=', 80, 10),
    ('El inventario en proceso debe quedar en <= 7 dias.', 'inventario_proceso', '<=', 7, 8),
    ('La productividad de linea debe subir a >= 80 u/h.', 'productividad_linea', '>=', 80, 10),
]

ACC = [
    (
        'Balancear la linea y redisenar la programacion de produccion',
        'Reduce cuellos de botella, mejora capacidad y baja entregas tardias.',
        {'capacidad_utilizada': 18, 'entregas_tardias': -12, 'tiempo_ciclo_min': -10, 'productividad_linea': 12},
    ),
    (
        'Aplicar control de calidad en proceso con Pareto y causa raiz',
        'Ataca defectos recurrentes antes de que lleguen al producto final.',
        {'defectos_produccion': -8, 'productividad_linea': 6, 'entregas_tardias': -4},
    ),
    (
        'Implementar Kanban para limitar WIP y ordenar abastecimiento',
        'Disminuye inventario en proceso y estabiliza el flujo de materiales.',
        {'inventario_proceso': -10, 'tiempo_ciclo_min': -8, 'capacidad_utilizada': 8},
    ),
    (
        'Aumentar horas extra sin corregir cuellos de botella',
        'Sube el costo y puede empeorar defectos sin resolver la causa.',
        {'defectos_produccion': 4, 'productividad_linea': -3, 'entregas_tardias': -3},
    ),
]

CONC = [
    (1, 'Diagnostico del cuello de botella', 40, True,
     _r('cuello de botella', 'capacidad', 'linea', 'flujo', 'restriccion', 'tiempo de ciclo', 'balanceo'),
     {'capacidad_utilizada': 8, 'tiempo_ciclo_min': -4}, {'entregas_tardias': 5}),
    (1, 'Analisis de calidad y desperdicio', 30, True,
     _r('defecto', 'rechazo', 'reproceso', 'pareto', 'causa raiz', 'calidad', 'desperdicio'),
     {'defectos_produccion': -3, 'productividad_linea': 4}, {'defectos_produccion': 3}),
    (1, 'Uso de indicadores de produccion', 30, False,
     _r('capacidad', 'productividad', 'inventario', 'wip', 'entrega', 'ciclo', 'indicador', 'dato'),
     {'productividad_linea': 4, 'inventario_proceso': -2}, {}),

    (2, 'Seleccion de mejora operativa', 40, True,
     _r('balanceo', 'programacion', 'kanban', 'calidad en proceso', 'mantenimiento', 'estandarizar'),
     {'capacidad_utilizada': 12, 'productividad_linea': 8}, {'capacidad_utilizada': -6}),
    (2, 'Comparacion de alternativas', 30, True,
     _r('alternativa', 'comparar', 'costo', 'beneficio', 'impacto', 'priorizar', 'opcion'),
     {'entregas_tardias': -5, 'tiempo_ciclo_min': -4}, {'entregas_tardias': 6}),
    (2, 'Control de restricciones productivas', 30, False,
     _r('restriccion', 'cuello', 'capacidad', 'materiales', 'turno', 'maquina', 'orden'),
     {'inventario_proceso': -4, 'defectos_produccion': -2}, {}),

    (3, 'Plan de implementacion en planta', 40, True,
     _r('plan', 'responsable', 'cronograma', 'turno', 'piloto', 'estandar', 'procedimiento'),
     {'productividad_linea': 8, 'capacidad_utilizada': 8}, {'productividad_linea': -5}),
    (3, 'Seguimiento con tablero de produccion', 30, True,
     _r('tablero', 'kpi', 'indicador', 'seguimiento', 'meta', 'control', 'oee', 'reporte'),
     {'entregas_tardias': -5, 'defectos_produccion': -2}, {'defectos_produccion': 3}),
    (3, 'Acciones correctivas y mejora continua', 30, False,
     _r('accion correctiva', 'mejora continua', 'kaizen', 'auditoria', 'ajustar', 'corregir'),
     {'tiempo_ciclo_min': -5, 'inventario_proceso': -3}, {}),
]

CONTEXTO = (
    'Textiles Andina fabrica uniformes institucionales. En las ultimas 6 semanas la planta acumula 22% de entregas '
    'tardias, 12% de defectos de produccion, capacidad utilizada de 62%, inventario en proceso de 18 dias, '
    'productividad de 58 u/h y tiempo de ciclo de 42 min. Actuas como jefe de produccion y debes diagnosticar, '
    'priorizar mejoras e implementar control operativo.'
)

SIT = (
    'La gerencia de Textiles Andina te pide un diagnostico de planta. Identifica el cuello de botella principal, '
    'las causas de defectos y atrasos, y los indicadores de produccion que usarias para controlar la mejora.'
)

RONDAS = [
    {'numero': 1, 'titulo': 'Diagnostico de planta', 'situacion': SIT,
     'etiqueta_decision': 'Diagnostico operativo', 'etiqueta_justificacion': 'Justificacion con indicadores'},
    {'numero': 2, 'titulo': 'Decision de mejora',
     'situacion': ('Con el diagnostico hecho, decide la mejora prioritaria: balanceo de linea, control de calidad en '
                   'proceso, Kanban/WIP o programacion de produccion. Compara alternativas y explica el impacto.'),
     'etiqueta_decision': 'Decision de mejora', 'etiqueta_justificacion': 'Justificacion operativa'},
    {'numero': 3, 'titulo': 'Implementacion y control',
     'situacion': ('Implementa la mejora en planta con responsables, cronograma, piloto, tablero de indicadores y '
                   'acciones correctivas para sostener resultados.'),
     'etiqueta_decision': 'Plan de implementacion', 'etiqueta_justificacion': 'Control y seguimiento'},
]


class Command(BaseCommand):
    help = 'Crea un caso real de Administracion de la Produccion con indicadores propios.'

    @transaction.atomic
    def handle(self, *args, **options):
        profesor = (
            User.objects.filter(is_staff=True, is_active=True).first()
            or User.objects.filter(is_active=True).first()
        )
        mm = MateriaMalla.objects.filter(materia__nombre__icontains='Administracion de la Produccion', activo=True).first()
        if not mm:
            self.stderr.write(self.style.ERROR('No encontre la materia Administracion de la Produccion.'))
            return

        titulo = 'Textiles Andina: atrasos, defectos y cuello de botella en planta'
        sim = _crear_simulacion(
            mm, profesor,
            titulo=titulo,
            tema='capacidad, calidad, inventario en proceso y programacion de produccion',
            rol='Jefe de Produccion de Textiles Andina',
            contexto=CONTEXTO,
            objetivo=('Diagnosticar problemas de capacidad, calidad y flujo; elegir una mejora operativa viable; '
                      'e implementar control con indicadores de produccion.'),
            resultado=('El estudiante toma decisiones de administracion de la produccion usando indicadores propios: '
                       'defectos, entregas tardias, capacidad, inventario en proceso, productividad y tiempo de ciclo.'),
            sit_inicial=SIT, rondas=RONDAS, indicadores=IND, restricciones=RES, acciones=ACC, conceptos=CONC,
            condiciones=[('Defectos controlados', 'defectos_produccion', '<=', 3, 5),
                         ('Entregas a tiempo', 'entregas_tardias', '<=', 4, 5),
                         ('Productividad recuperada', 'productividad_linea', '>=', 85, 5)],
            empresa='Textiles Andina', area='Administracion de la Produccion',
        )

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
                f'Caso creado en "{mm.materia.nombre}": "{sim.titulo}" con {len(IND)} indicadores propios y {len(CONC)} conceptos.'
            ))
        else:
            self.stdout.write('El caso de Administracion de la Produccion ya existia; simulaciones genericas archivadas.')
