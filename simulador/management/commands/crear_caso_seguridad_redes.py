"""Agrega un caso REAL de Seguridad de Redes (incidente ransomware) a la materia
'Seguridad de Redes' (TI-301) de la malla TI-UTA-2026, con indicadores propios de
ciberseguridad bien medidos. Idempotente.

Uso: python manage.py crear_caso_seguridad_redes
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


IND = [
    ('sistemas_comprometidos', 'Sistemas comprometidos', 8, 0, 30, 'BAJO', 'eq', True),
    ('nivel_exposicion', 'Nivel de exposicion', 78, 0, 100, 'BAJO', '%', True),
    ('tiempo_deteccion_h', 'Tiempo de deteccion (MTTD)', 36, 0, 72, 'BAJO', 'h', True),
    ('copias_respaldo', 'Sistemas con respaldo valido', 40, 0, 100, 'ALTO', '%', False),
    ('cumplimiento_normativo', 'Cumplimiento normativo', 55, 0, 100, 'ALTO', '%', False),
    ('incidentes_mes', 'Incidentes del ultimo mes', 14, 0, 40, 'BAJO', 'inc', False),
]
RES = [
    ('La exposicion debe reducirse a <= 20%.', 'nivel_exposicion', '<=', 20, 12),
    ('No deben quedar sistemas comprometidos activos (<= 0).', 'sistemas_comprometidos', '<=', 0, 12),
    ('El tiempo de deteccion debe bajar a <= 8 h.', 'tiempo_deteccion_h', '<=', 8, 10),
    ('Al menos 90% de sistemas con respaldo valido.', 'copias_respaldo', '>=', 90, 8),
]
ACC = [
    ('Aislar y segmentar la red, revocar accesos y forzar MFA en todas las cuentas',
     'Contiene el movimiento lateral del ataque y cierra el acceso del atacante.',
     {'nivel_exposicion': -35, 'sistemas_comprometidos': -5, 'incidentes_mes': -4}),
    ('Restaurar desde respaldos inmutables y desplegar EDR + SIEM para deteccion',
     'Recupera la operacion limpia y baja el tiempo de deteccion futuro.',
     {'copias_respaldo': 45, 'tiempo_deteccion_h': -28, 'sistemas_comprometidos': -3}),
    ('Parchear vulnerabilidades, aplicar minimo privilegio y endurecer (hardening)',
     'Cierra las puertas que uso el atacante y sube el cumplimiento.',
     {'nivel_exposicion': -20, 'cumplimiento_normativo': 25, 'incidentes_mes': -3}),
    ('Pagar el rescate para recuperar los datos rapido',
     'Riesgoso: no garantiza recuperacion, financia el crimen y baja el cumplimiento.',
     {'cumplimiento_normativo': -20, 'nivel_exposicion': 5, 'incidentes_mes': 2}),
]
CONC = [
    (1, 'Analisis forense y alcance del incidente', 35, True,
     _r('forense', 'alcance', 'vector', 'bitacora', 'logs', 'indicadores de compromiso', 'ioc', 'sistemas afectados'),
     {'nivel_exposicion': -10, 'tiempo_deteccion_h': -4}, {'nivel_exposicion': 5}),
    (1, 'Uso de herramientas de deteccion', 30, True,
     _r('siem', 'edr', 'antivirus', 'monitoreo', 'trafico', 'wireshark', 'escaneo', 'deteccion'),
     {'tiempo_deteccion_h': -6}, {'sistemas_comprometidos': 2}),
    (1, 'Identificacion de causas', 20, False,
     _r('causa', 'phishing', 'vulnerabilidad', 'parche', 'credenciales', 'configuracion', 'puerto'),
     {'nivel_exposicion': -5}, {}),
    (1, 'Justificacion con evidencia', 15, False,
     _r('porque', 'evidencia', 'dato', 'bitacora', 'normativa'),
     {'cumplimiento_normativo': 3}, {}),

    (2, 'Contencion y aislamiento', 30, True,
     _r('aislar', 'segmentacion', 'contener', 'revocar', 'mfa', 'firewall', 'bloquear', 'cuarentena'),
     {'nivel_exposicion': -30, 'sistemas_comprometidos': -4}, {'nivel_exposicion': 10}),
    (2, 'Erradicacion del atacante', 30, True,
     _r('erradicar', 'eliminar', 'malware', 'parche', 'hardening', 'minimo privilegio', 'credenciales'),
     {'sistemas_comprometidos': -3, 'cumplimiento_normativo': 10}, {'sistemas_comprometidos': 2}),
    (2, 'Comparacion de alternativas', 20, False,
     _r('alternativa', 'comparar', 'costo', 'riesgo', 'opcion', 'impacto'),
     {'nivel_exposicion': -3}, {}),
    (2, 'Justificacion tecnica', 20, False,
     _r('porque', 'riesgo', 'normativa', 'continuidad', 'negocio'),
     {'cumplimiento_normativo': 5}, {}),

    (3, 'Recuperacion desde respaldos', 30, True,
     _r('respaldo', 'backup', 'inmutable', 'restaurar', 'recuperacion', 'continuidad', 'rto', 'rpo'),
     {'copias_respaldo': 40, 'sistemas_comprometidos': -2}, {'copias_respaldo': -10}),
    (3, 'Monitoreo y respuesta continua', 25, True,
     _r('siem', 'soc', 'monitoreo', 'alertas', 'edr', 'plan de respuesta', 'deteccion'),
     {'tiempo_deteccion_h': -10, 'incidentes_mes': -3}, {'tiempo_deteccion_h': 5}),
    (3, 'Endurecimiento y cumplimiento', 25, False,
     _r('hardening', 'politica', 'cumplimiento', 'normativa', 'capacitacion', 'concientizacion', 'auditoria'),
     {'cumplimiento_normativo': 20, 'nivel_exposicion': -10}, {}),
    (3, 'Mejora continua y lecciones', 20, False,
     _r('mejora', 'lecciones', 'documentacion', 'simulacro', 'correctiva'),
     {'incidentes_mes': -2}, {}),
]

CONTEXTO = (
    'MediCare, una clinica con 12 sucursales, sufrio un ataque de ransomware que cifro parte de sus sistemas. '
    'Estado actual: 8 sistemas comprometidos, nivel de exposicion 78%, el ataque tardo 36 h en detectarse, solo el '
    '40% de los sistemas tiene respaldo valido, cumplimiento normativo 55% y 14 incidentes en el ultimo mes. No hay '
    'MFA ni segmentacion. Actuas como Analista de Seguridad y debes contener, erradicar, recuperar y endurecer.'
)
SIT = (
    'La direccion de MediCare exige un informe en tres etapas. Primero: como Analista de Seguridad, realiza el '
    'analisis forense, define el alcance del incidente (sistemas afectados, vector de entrada, IoCs) y los indicadores '
    'que usarias para medir la exposicion. Justifica con evidencia.'
)
RONDAS = [
    {'numero': 1, 'titulo': 'Analisis forense', 'situacion': SIT},
    {'numero': 2, 'titulo': 'Contencion y erradicacion',
     'situacion': ('Con el alcance claro, decide como contener y erradicar: aislar/segmentar, revocar accesos, MFA, '
                   'parcheo y minimo privilegio. Compara alternativas (incluido el dilema del rescate) y justifica.')},
    {'numero': 3, 'titulo': 'Recuperacion y endurecimiento',
     'situacion': ('Recupera la operacion desde respaldos inmutables, implementa monitoreo continuo (SIEM/EDR/SOC), '
                   'endurece la infraestructura, sube el cumplimiento y define mejora continua.')},
]


class Command(BaseCommand):
    help = 'Agrega un caso real de Seguridad de Redes (ransomware) con indicadores propios.'

    @transaction.atomic
    def handle(self, *args, **options):
        profesor = User.objects.filter(username='bpalate').first() or User.objects.filter(is_staff=True).first()
        mm = MateriaMalla.objects.filter(malla__codigo='TI-UTA-2026', materia__codigo='TI-301').first()
        if not mm:
            self.stderr.write(self.style.ERROR('No existe la materia Seguridad de Redes (TI-301). Corre antes crear_malla_ti_redes.'))
            return

        sim = _crear_simulacion(
            mm, profesor,
            titulo='Ataque ransomware en MediCare: contener, recuperar y endurecer',
            tema='ciberseguridad, respuesta a incidentes y cumplimiento',
            rol='Analista de Seguridad de MediCare',
            contexto=CONTEXTO,
            objetivo=('Aplicar respuesta a incidentes para contener el ransomware, erradicar al atacante, recuperar '
                      'la operacion desde respaldos y endurecer la seguridad cumpliendo la normativa.'),
            resultado=('El estudiante entrega una respuesta sustentada con metricas de seguridad (exposicion, sistemas '
                       'comprometidos, MTTD, respaldos, cumplimiento) y un plan de recuperacion y mejora continua.'),
            sit_inicial=SIT, rondas=RONDAS, indicadores=IND, restricciones=RES, acciones=ACC, conceptos=CONC,
            condiciones=[('Erradicar al atacante', 'sistemas_comprometidos', '<=', 0, 5),
                         ('Reducir exposicion', 'nivel_exposicion', '<=', 15, 5)],
            empresa='MediCare', area='Tecnologias de la Informacion')

        if sim:
            self.stdout.write(self.style.SUCCESS(f'Caso creado: "{sim.titulo}" con {len(IND)} indicadores propios de ciberseguridad.'))
        else:
            self.stdout.write('El caso de Seguridad de Redes ya existia.')
