"""Caso REAL de compra de equipos: la empresa debe adquirir 30 computadoras con
3 cotizaciones que tienen trade-offs (barato sin garantia / marca con soporte /
gama alta cara). Indicadores propios de una decision de compra (TCO, garantia,
compatibilidad, riesgo de proveedor). Idempotente.

Uso: python manage.py crear_caso_compra_computadoras
"""
import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from academico.models import MateriaMalla
from simulador.management.commands.crear_mallas_fisei import _crear_simulacion
from simulador.models import MatrizEvaluacionCaso, OpcionCasoSimulacion, Simulacion

User = get_user_model()


def _r(*p):
    return json.dumps({'any': list(p)}, ensure_ascii=False)


IND = [
    ('desempeno_equipos', 'Desempeno vs necesidades', 50, 0, 100, 'ALTO', '%', True),
    ('costo_total', 'Costo total (TCO)', 30000, 15000, 50000, 'BAJO', 'USD', True),
    ('soporte_garantia', 'Cobertura de soporte/garantia', 40, 0, 100, 'ALTO', '%', True),
    ('compatibilidad', 'Compatibilidad con sistemas', 55, 0, 100, 'ALTO', '%', False),
    ('vida_util', 'Vida util estimada', 3, 1, 7, 'ALTO', 'anios', False),
    ('riesgo_proveedor', 'Riesgo del proveedor', 50, 0, 100, 'BAJO', '%', False),
]
RES = [
    ('Los equipos deben cubrir las necesidades (desempeno >= 70%).', 'desempeno_equipos', '>=', 70, 12),
    ('No exceder el presupuesto aprobado (TCO <= 36000).', 'costo_total', '<=', 36000, 12),
    ('Debe haber soporte/garantia adecuado (>= 60%).', 'soporte_garantia', '>=', 60, 10),
    ('Compatibilidad con los sistemas actuales (>= 70%).', 'compatibilidad', '>=', 70, 8),
]
ACC = [
    ('Comprar equipos de marca con garantia 3 anios y soporte en sitio',
     'Mas caro, pero cubre necesidades, baja el riesgo y dura mas.',
     {'desempeno_equipos': 25, 'soporte_garantia': 45, 'vida_util': 2, 'riesgo_proveedor': -20, 'costo_total': 4000}),
    ('Comprar la cotizacion mas barata (ensamblados, sin garantia)',
     'Ahorra hoy, pero sin soporte sube el riesgo y dura menos.',
     {'costo_total': -7000, 'soporte_garantia': -30, 'riesgo_proveedor': 25, 'vida_util': -1}),
    ('Opcion intermedia: marca media con garantia 1 anio',
     'Equilibra costo, desempeno y soporte de forma razonable.',
     {'desempeno_equipos': 12, 'soporte_garantia': 18, 'compatibilidad': 10, 'costo_total': -500}),
    ('Comprar la gama mas alta sin analizar las necesidades reales',
     'Sobredimensionado: excede el presupuesto y desperdicia recursos.',
     {'costo_total': 12000, 'desempeno_equipos': 8, 'riesgo_proveedor': 5}),
]
CONC = [
    (1, 'Definir requisitos y especificaciones', 35, True,
     _r('requisitos', 'especificaciones', 'necesidades', 'uso', 'software', 'rendimiento', 'memoria', 'procesador'),
     {'desempeno_equipos': 12, 'compatibilidad': 8}, {'desempeno_equipos': -8}),
    (1, 'Criterios y comparacion de cotizaciones', 30, True,
     _r('tco', 'costo total', 'cotizacion', 'comparar', 'criterios', 'garantia', 'proveedor', 'presupuesto'),
     {'riesgo_proveedor': -8, 'soporte_garantia': 8}, {'riesgo_proveedor': 6}),
    (1, 'Compatibilidad y soporte', 20, False,
     _r('compatibilidad', 'sistemas', 'soporte', 'garantia', 'mantenimiento', 'drivers'),
     {'compatibilidad': 10}, {}),
    (1, 'Justificacion con datos', 15, False,
     _r('porque', 'dato', 'presupuesto', 'necesidad', 'requisito'),
     {'desempeno_equipos': 3}, {}),

    (2, 'Decision de compra (costo-beneficio)', 30, True,
     _r('elijo', 'recomiendo', 'cotizacion', 'proveedor', 'costo beneficio', 'tco', 'presupuesto', 'porque'),
     {'desempeno_equipos': 18, 'costo_total': -1500}, {'costo_total': 2000}),
    (2, 'Garantia, soporte y riesgo del proveedor', 30, True,
     _r('garantia', 'soporte', 'sla', 'riesgo', 'proveedor', 'reputacion', 'respaldo'),
     {'soporte_garantia': 25, 'riesgo_proveedor': -15}, {'riesgo_proveedor': 10}),
    (2, 'Compatibilidad y escalabilidad', 20, False,
     _r('compatibilidad', 'escalabilidad', 'sistemas', 'integracion', 'futuro'),
     {'compatibilidad': 15, 'vida_util': 1}, {}),
    (2, 'Justificacion objetiva', 20, False,
     _r('porque', 'criterio', 'evidencia', 'comparacion', 'objetivo'),
     {'desempeno_equipos': 4}, {}),

    (3, 'Plan de adquisicion e implementacion', 30, True,
     _r('plan', 'cronograma', 'fases', 'instalacion', 'migracion', 'responsable', 'entrega'),
     {'desempeno_equipos': 8, 'compatibilidad': 8}, {'desempeno_equipos': -5}),
    (3, 'Garantia, mantenimiento y soporte', 25, True,
     _r('garantia', 'mantenimiento', 'soporte', 'sla', 'preventivo', 'contrato'),
     {'soporte_garantia': 20, 'vida_util': 1}, {'soporte_garantia': -10}),
    (3, 'Capacitacion y adopcion', 25, False,
     _r('capacitacion', 'induccion', 'usuarios', 'adopcion', 'manual'),
     {'desempeno_equipos': 6}, {}),
    (3, 'Seguimiento y mejora', 20, False,
     _r('seguimiento', 'inventario', 'kpi', 'mejora', 'evaluacion'),
     {'riesgo_proveedor': -5}, {}),
]
COTIZACIONES = [
    {'nombre': 'Proveedor A - Ensamblados', 'edad': '-', 'experiencia': 'Sin garantia',
     'salario_pretendido': 23000, 'fortalezas': 'Precio bajo (USD 23.000)', 'debilidades': 'Sin soporte ni garantia, mayor riesgo',
     'resultados': [
         {'criterio': 'TCO', 'valor': '23.000'},
         {'criterio': 'Garantia', 'valor': '0 anios'},
         {'criterio': 'Compat.', 'valor': 'Media'},
         {'criterio': 'Vida util', 'valor': '2 anios'},
         {'criterio': 'Riesgo', 'valor': 'Alto'},
     ]},
    {'nombre': 'Proveedor B - Marca con soporte', 'edad': '-', 'experiencia': 'Garantia 3 anios',
     'salario_pretendido': 34000, 'fortalezas': 'Soporte en sitio, robustos, durables', 'debilidades': 'Mas caro (USD 34.000)',
     'resultados': [
         {'criterio': 'TCO', 'valor': '34.000'},
         {'criterio': 'Garantia', 'valor': '3 anios'},
         {'criterio': 'Compat.', 'valor': 'Alta'},
         {'criterio': 'Vida util', 'valor': '5 anios'},
         {'criterio': 'Riesgo', 'valor': 'Bajo'},
     ]},
    {'nombre': 'Proveedor C - Marca media', 'edad': '-', 'experiencia': 'Garantia 1 anio',
     'salario_pretendido': 29000, 'fortalezas': 'Equilibrio costo/soporte (USD 29.000)', 'debilidades': 'Soporte limitado a 1 anio',
     'resultados': [
         {'criterio': 'TCO', 'valor': '29.000'},
         {'criterio': 'Garantia', 'valor': '1 anio'},
         {'criterio': 'Compat.', 'valor': 'Alta'},
         {'criterio': 'Vida util', 'valor': '4 anios'},
         {'criterio': 'Riesgo', 'valor': 'Medio'},
     ]},
]
MATRIZ_EVALUACION = [
    {'criterio': 'Costo total de propiedad (TCO)', 'peso': 30, 'evalua': 'precio de compra, garantia, mantenimiento y vida util esperada'},
    {'criterio': 'Garantia y soporte', 'peso': 25, 'evalua': 'anios de garantia, soporte en sitio, SLA y respaldo del proveedor'},
    {'criterio': 'Compatibilidad con sistemas', 'peso': 20, 'evalua': 'ERP, ofimatica, drivers, perifericos y sistemas actuales'},
    {'criterio': 'Desempeno segun necesidad', 'peso': 15, 'evalua': 'procesador, memoria, almacenamiento y rendimiento para el uso real'},
    {'criterio': 'Riesgo del proveedor', 'peso': 10, 'evalua': 'reputacion, continuidad, tiempos de entrega y cumplimiento'},
]
LABELS_CASO = {
    'participantes_titulo': 'Cotizaciones recibidas',
    'matriz_titulo': 'Matriz de evaluacion de compra',
    'valor_titulo': 'Costo total',
    'fortalezas_titulo': 'Ventaja',
    'riesgo_titulo': 'Riesgo',
    'participante_col': 'Proveedor',
    'valor_col': 'Costo',
    'fortalezas_col': 'Ventaja',
    'riesgo_col': 'Riesgo',
    'fase_criterios': 'Criterios de compra',
    'fase_resultados': 'Comparacion de cotizaciones',
    'fase_plan': 'Plan de adquisicion',
}
COLUMNAS_RESULTADOS = ['TCO', 'Garantia', 'Compat.', 'Vida util', 'Riesgo']


def _recrear_datos_caso(simulacion, profesor):
    simulacion.matriz_caso.all().delete()
    for idx, item in enumerate(MATRIZ_EVALUACION, start=1):
        MatrizEvaluacionCaso.objects.create(
            simulacion=simulacion,
            criterio=item['criterio'],
            peso=item['peso'],
            evalua=item['evalua'],
            orden=idx,
            usuario_creacion=profesor,
        )
    simulacion.opciones_caso.all().delete()
    for idx, item in enumerate(COTIZACIONES, start=1):
        OpcionCasoSimulacion.objects.create(
            simulacion=simulacion,
            nombre=item['nombre'],
            subtitulo=item['experiencia'],
            valor_referencia=str(item['salario_pretendido']),
            fortaleza=item['fortalezas'],
            riesgo=item['debilidades'],
            resultados=item.get('resultados', []),
            orden=idx,
            usuario_creacion=profesor,
        )

CONTEXTO = (
    'La empresa LogiPlus debe comprar 30 computadoras para su area de operaciones (uso ofimatico, sistema ERP y '
    'reportes). Tiene 3 cotizaciones con trade-offs: Proveedor A (ensamblados, USD 23.000, sin garantia), Proveedor B '
    '(marca, USD 34.000, garantia 3 anios y soporte), Proveedor C (marca media, USD 29.000, garantia 1 anio). '
    'Presupuesto aprobado: USD 36.000. Actuas como responsable de TI/compras y debes definir requisitos, elegir con '
    'criterios (no solo el precio) y planificar la adquisicion.'
)
SIT = (
    'LogiPlus te pide un informe en tres etapas. Primero: define los requisitos reales de los equipos segun el uso '
    '(ERP, ofimatica), los criterios de evaluacion (TCO, garantia, compatibilidad, riesgo del proveedor) y compara '
    'las 3 cotizaciones. Justifica con datos, no solo por el precio.'
)
RONDAS = [
    {'numero': 1, 'titulo': 'Requisitos y criterios', 'situacion': SIT},
    {'numero': 2, 'titulo': 'Decision de compra',
     'situacion': ('Con los requisitos claros, decide a QUE proveedor comprar y justifica con costo-beneficio (TCO), '
                   'garantia/soporte, compatibilidad y riesgo del proveedor. Revisa las 3 cotizaciones y elige con criterios.')},
    {'numero': 3, 'titulo': 'Plan de adquisicion',
     'situacion': ('Ya elegiste. Planifica la adquisicion: cronograma de compra e instalacion, migracion, garantia y '
                   'mantenimiento, capacitacion de usuarios y seguimiento del inventario.')},
]


class Command(BaseCommand):
    help = 'Crea el caso real de compra de computadoras (3 cotizaciones con trade-offs).'

    @transaction.atomic
    def handle(self, *args, **options):
        profesor = User.objects.filter(is_staff=True, is_active=True).first() or User.objects.filter(is_active=True).first()
        mm = (MateriaMalla.objects.filter(materia__nombre__icontains='Tecnologias de la Informacion', activo=True).first()
              or MateriaMalla.objects.filter(materia__nombre__icontains='Sistemas de Informacion', activo=True).first()
              or MateriaMalla.objects.filter(materia__nombre__icontains='Administracion', activo=True).first())
        if not mm:
            self.stderr.write(self.style.ERROR('No encontre una materia adecuada (TIC/Sistemas/Administracion).'))
            return

        titulo = 'Compra de 30 computadoras en LogiPlus: TCO, garantia y proveedor'
        sim = _crear_simulacion(
            mm, profesor,
            titulo=titulo,
            tema='decision de compra de equipos, TCO y evaluacion de proveedores',
            rol='Responsable de TI y Compras de LogiPlus',
            contexto=CONTEXTO,
            objetivo=('Definir requisitos, evaluar 3 cotizaciones con criterios (TCO, garantia, compatibilidad, riesgo) '
                      'y elegir la mejor compra dentro del presupuesto, con un plan de adquisicion.'),
            resultado=('El estudiante toma una decision de compra sustentada con costo total de propiedad, garantia y '
                       'riesgo del proveedor (no solo el precio), con un plan de adquisicion y mantenimiento.'),
            sit_inicial=SIT, rondas=RONDAS, indicadores=IND, restricciones=RES, acciones=ACC, conceptos=CONC,
            condiciones=[('Equipos a la medida', 'desempeno_equipos', '>=', 85, 5),
                         ('Buen soporte/garantia', 'soporte_garantia', '>=', 80, 5)],
            empresa='LogiPlus', area='Tecnologias de la Informacion')

        sim_actual = sim or Simulacion.objects.filter(materia_malla=mm, titulo=titulo).first()
        if sim_actual:
            params = dict(sim_actual.parametros or {})
            params['candidatos'] = COTIZACIONES
            params['prueba_tecnica'] = MATRIZ_EVALUACION
            params['caso_labels'] = LABELS_CASO
            params['columnas_resultados'] = COLUMNAS_RESULTADOS
            sim_actual.parametros = params
            sim_actual.save(update_fields=['parametros'])
            _recrear_datos_caso(sim_actual, profesor)

        if sim:
            self.stdout.write(self.style.SUCCESS(
                f'Caso creado en "{mm.materia.nombre}": "{sim.titulo}" con {len(IND)} indicadores propios y 3 cotizaciones.'))
        else:
            self.stdout.write('El caso de compra de computadoras ya existia; matriz de evaluacion actualizada.')
