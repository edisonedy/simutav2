"""Caso REAL de Sistemas de Informacion Gerencial: una empresa toma decisiones
a ciegas porque sus reportes tardan, los datos estan sucios y las integraciones
fallan. El estudiante implementa integracion/ETL, gobierno de datos y un tablero
gerencial (BI). Indicadores PROPIOS de sistemas de informacion. Idempotente.

Uso: python manage.py crear_caso_sistemas_informacion
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


# Indicadores propios de Sistemas de Informacion Gerencial.
IND = [
    ('calidad_datos', 'Calidad / integridad de datos', 55, 0, 100, 'ALTO', '%', True),
    ('tiempo_reporte', 'Tiempo para generar reportes', 48, 1, 72, 'BAJO', 'h', True),
    ('decisiones_con_datos', 'Decisiones sustentadas en datos', 40, 0, 100, 'ALTO', '%', True),
    ('errores_integracion', 'Errores de integracion entre modulos', 18, 0, 50, 'BAJO', '%', False),
    ('disponibilidad_sistema', 'Disponibilidad del sistema', 95, 80, 100, 'ALTO', '%', False),
    ('adopcion_tablero', 'Adopcion del tablero gerencial', 30, 0, 100, 'ALTO', '%', False),
]
RES = [
    ('La calidad de datos debe ser >= 85%.', 'calidad_datos', '>=', 85, 12),
    ('Los reportes gerenciales deben generarse en <= 4 h.', 'tiempo_reporte', '<=', 4, 12),
    ('Al menos 80% de decisiones deben sustentarse en datos.', 'decisiones_con_datos', '>=', 80, 10),
    ('Los errores de integracion deben quedar <= 3%.', 'errores_integracion', '<=', 3, 8),
]
ACC = [
    ('Implementar un tablero gerencial (BI) con integracion ETL automatizada',
     'Centraliza la informacion y entrega reportes en tiempo casi real.',
     {'tiempo_reporte': -40, 'decisiones_con_datos': 35, 'adopcion_tablero': 40, 'disponibilidad_sistema': 1}),
    ('Aplicar gobierno de datos: estandarizar, limpiar y validar antes de integrar',
     'Ataca la raiz: datos confiables y una sola fuente de verdad.',
     {'calidad_datos': 35, 'errores_integracion': -12, 'decisiones_con_datos': 15}),
    ('Seguir exportando a Excel manualmente para los reportes',
     'Parche: sigue lento, propenso a errores y sin trazabilidad.',
     {'tiempo_reporte': -5, 'errores_integracion': 6, 'calidad_datos': -5}),
    ('Comprar un ERP costoso sin definir requerimientos ni limpiar datos',
     'Riesgoso: caro, sin requerimientos y arrastra los datos sucios.',
     {'calidad_datos': -10, 'errores_integracion': 10, 'disponibilidad_sistema': -2}),
]
CONC = [
    (1, 'Mapeo de flujos y requerimientos gerenciales', 35, True,
     _r('requerimientos', 'flujo de informacion', 'procesos', 'fuentes de datos', 'indicadores de gestion', 'kpi', 'necesidades'),
     {'decisiones_con_datos': 8, 'calidad_datos': 5}, {'decisiones_con_datos': -8}),
    (1, 'Diagnostico de calidad de datos e integracion', 30, True,
     _r('calidad de datos', 'datos sucios', 'inconsistencia', 'integracion', 'modulos', 'duplicados', 'validacion'),
     {'calidad_datos': 8, 'errores_integracion': -3}, {'calidad_datos': -6}),
    (1, 'Identificacion de causas', 20, False,
     _r('causa', 'manual', 'silos', 'excel', 'sin integracion', 'fuentes dispersas'),
     {'errores_integracion': -2}, {}),
    (1, 'Justificacion con datos del negocio', 15, False,
     _r('porque', 'dato', 'gerencia', 'decision', 'reporte', 'tiempo'),
     {'decisiones_con_datos': 3}, {}),

    (2, 'Solucion de informacion adecuada', 30, True,
     _r('etl', 'data warehouse', 'integracion', 'tablero', 'dashboard', 'bi', 'business intelligence', 'tiempo real', 'api'),
     {'tiempo_reporte': -30, 'decisiones_con_datos': 20, 'adopcion_tablero': 20}, {'tiempo_reporte': 6}),
    (2, 'Gobierno y calidad de datos', 30, True,
     _r('gobierno de datos', 'calidad', 'estandarizar', 'limpiar', 'validar', 'single source of truth', 'maestro'),
     {'calidad_datos': 25, 'errores_integracion': -10}, {'calidad_datos': -8}),
    (2, 'Comparacion de alternativas', 20, False,
     _r('alternativa', 'comparar', 'costo', 'beneficio', 'opcion', 'escalabilidad'),
     {'decisiones_con_datos': 4}, {}),
    (2, 'Justificacion tecnica', 20, False,
     _r('porque', 'gerencia', 'oportuno', 'confiable', 'sla', 'valor'),
     {'decisiones_con_datos': 4}, {}),

    (3, 'Plan de implementacion por fases', 30, True,
     _r('plan', 'fases', 'cronograma', 'etl', 'piloto', 'responsable', 'migracion'),
     {'tiempo_reporte': -8, 'errores_integracion': -4}, {'disponibilidad_sistema': -1}),
    (3, 'Seguridad, respaldo y disponibilidad', 25, True,
     _r('seguridad', 'respaldo', 'backup', 'disponibilidad', 'accesos', 'continuidad', 'sla'),
     {'disponibilidad_sistema': 2, 'errores_integracion': -3}, {'disponibilidad_sistema': -2}),
    (3, 'Capacitacion y adopcion del tablero', 25, False,
     _r('capacitacion', 'adopcion', 'usuarios', 'induccion', 'cultura de datos'),
     {'adopcion_tablero': 25, 'decisiones_con_datos': 8}, {}),
    (3, 'Indicadores de seguimiento y mejora', 20, False,
     _r('kpi', 'seguimiento', 'indicadores', 'mejora', 'monitoreo', 'auditoria'),
     {'decisiones_con_datos': 6}, {}),
]

CONTEXTO = (
    'Comercial Andina (4 sucursales) toma decisiones gerenciales "a ciegas": los reportes de ventas, inventario y '
    'finanzas tardan 48 h en consolidarse, los datos no cuadran entre modulos (calidad 55%), hay 18% de errores de '
    'integracion y solo el 40% de las decisiones se sustenta en datos. El tablero gerencial casi no se usa (adopcion '
    '30%). Actuas como Analista de Sistemas de Informacion y debes diagnosticar, decidir e implementar una solucion.'
)
SIT = (
    'La gerencia de Comercial Andina te pide un informe en tres etapas. Primero: como Analista de Sistemas de '
    'Informacion, mapea los flujos de informacion y los requerimientos gerenciales (que indicadores/KPI necesita la '
    'gerencia), y diagnostica la calidad de datos y los problemas de integracion. Justifica con datos del negocio.'
)
RONDAS = [
    {'numero': 1, 'titulo': 'Diagnostico de informacion', 'situacion': SIT,
     'etiqueta_decision': 'Diagnostico', 'etiqueta_justificacion': 'Justificacion del diagnostico'},
    {'numero': 2, 'titulo': 'Decision de solucion',
     'situacion': ('Con el diagnostico hecho, decide la solucion (ETL/data warehouse, tablero BI, gobierno de datos) '
                   'frente a parches manuales o comprar un ERP. Compara alternativas y justifica su impacto en tiempo '
                   'de reporte, calidad de datos y decisiones sustentadas.'),
     'etiqueta_decision': 'Decision de solucion', 'etiqueta_justificacion': 'Justificacion de la decision'},
    {'numero': 3, 'titulo': 'Plan de implementacion',
     'situacion': ('Implementa por fases: ETL/integracion, gobierno y calidad de datos, seguridad/respaldo, '
                   'capacitacion y adopcion del tablero, e indicadores de seguimiento.'),
     'etiqueta_decision': 'Plan de implementacion', 'etiqueta_justificacion': 'Justificacion, control y seguimiento'},
]


class Command(BaseCommand):
    help = 'Crea un caso real de Sistemas de Informacion Gerencial con indicadores propios.'

    @transaction.atomic
    def handle(self, *args, **options):
        profesor = User.objects.filter(is_staff=True, is_active=True).first() or User.objects.filter(is_active=True).first()
        mm = (MateriaMalla.objects.filter(materia__nombre__icontains='Sistemas de Informacion', activo=True).first()
              or MateriaMalla.objects.filter(materia__nombre__icontains='Sistemas', activo=True).first()
              or MateriaMalla.objects.filter(materia__nombre__icontains='Tecnologias de la Informacion', activo=True).first())
        if not mm:
            self.stderr.write(self.style.ERROR('No encontre una materia de Sistemas/TIC.'))
            return

        sim = _crear_simulacion(
            mm, profesor,
            titulo='Comercial Andina: decisiones gerenciales sin datos (BI y gobierno de datos)',
            tema='sistemas de informacion gerencial, integracion, calidad de datos y BI',
            rol='Analista de Sistemas de Informacion de Comercial Andina',
            contexto=CONTEXTO,
            objetivo=('Aplicar sistemas de informacion para entregar a la gerencia datos oportunos y confiables: '
                      'integrar fuentes (ETL), asegurar calidad/gobierno de datos y desplegar un tablero gerencial.'),
            resultado=('El estudiante toma decisiones sustentadas con metricas de sistemas (tiempo de reporte, calidad '
                       'de datos, integracion, decisiones basadas en datos) y planifica la implementacion del BI.'),
            sit_inicial=SIT, rondas=RONDAS, indicadores=IND, restricciones=RES, acciones=ACC, conceptos=CONC,
            condiciones=[('Reportes oportunos', 'tiempo_reporte', '<=', 2, 5),
                         ('Datos confiables', 'calidad_datos', '>=', 95, 5)],
            empresa='Comercial Andina', area='Sistemas de Informacion')

        if sim:
            self.stdout.write(self.style.SUCCESS(
                f'Caso creado en "{mm.materia.nombre}": "{sim.titulo}" con {len(IND)} indicadores propios de sistemas.'))
        else:
            self.stdout.write('El caso de Sistemas de Informacion ya existia.')
