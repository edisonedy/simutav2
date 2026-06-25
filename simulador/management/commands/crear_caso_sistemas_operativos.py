"""Crea un caso real de Sistemas Operativos con indicadores propios.

Uso: python manage.py crear_caso_sistemas_operativos
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
    ('tiempo_espera_cpu_ms', 'Tiempo de espera en CPU', 240, 0, 500, 'BAJO', 'ms', True),
    ('throughput_procesos', 'Throughput de procesos', 38, 0, 120, 'ALTO', 'proc/s', True),
    ('uso_memoria', 'Uso de memoria principal', 88, 0, 100, 'BAJO', '%', True),
    ('paginacion_swap_mb', 'Paginacion a swap', 5200, 0, 8000, 'BAJO', 'MB', False),
    ('procesos_bloqueados', 'Procesos bloqueados', 18, 0, 50, 'BAJO', 'proc', True),
    ('iowait_disco', 'Espera por E/S de disco', 32, 0, 80, 'BAJO', '%', False),
]

RES = [
    ('El tiempo de espera en CPU debe quedar en <= 80 ms.', 'tiempo_espera_cpu_ms', '<=', 80, 12),
    ('El throughput debe llegar al menos a 80 procesos por segundo.', 'throughput_procesos', '>=', 80, 12),
    ('La paginacion a swap debe bajar a <= 500 MB.', 'paginacion_swap_mb', '<=', 500, 10),
    ('No deben quedar mas de 3 procesos bloqueados.', 'procesos_bloqueados', '<=', 3, 10),
    ('La espera por E/S de disco debe quedar en <= 10%.', 'iowait_disco', '<=', 10, 8),
]

ACC = [
    (
        'Ajustar el planificador: quantum, prioridades y politica MLFQ',
        'Reduce espera en CPU y evita inanicion de procesos interactivos.',
        {'tiempo_espera_cpu_ms': -120, 'throughput_procesos': 25, 'procesos_bloqueados': -4},
    ),
    (
        'Optimizar memoria virtual: working set, fugas y reduccion de swap',
        'Ataca la presion de memoria y baja la paginacion que frena al sistema.',
        {'uso_memoria': -25, 'paginacion_swap_mb': -4300, 'tiempo_espera_cpu_ms': -40},
    ),
    (
        'Corregir bloqueos de E/S y concurrencia con orden de locks y timeouts',
        'Disminuye deadlocks, procesos bloqueados y espera por disco.',
        {'procesos_bloqueados': -12, 'iowait_disco': -20, 'throughput_procesos': 20},
    ),
    (
        'Agregar mas hilos y procesos sin diagnosticar el cuello de botella',
        'Satura CPU, memoria y E/S; aumenta contencion y bloqueos.',
        {'tiempo_espera_cpu_ms': 80, 'uso_memoria': 10, 'procesos_bloqueados': 8, 'iowait_disco': 8},
    ),
]

CONC = [
    (1, 'Diagnostico de planificacion de CPU', 30, True,
     _r('planificador', 'scheduler', 'quantum', 'prioridad', 'round robin', 'mlfq', 'tiempo de espera', 'turnaround'),
     {'tiempo_espera_cpu_ms': -35, 'throughput_procesos': 8}, {'tiempo_espera_cpu_ms': 30}),
    (1, 'Diagnostico de memoria virtual', 30, True,
     _r('memoria virtual', 'paginacion', 'swap', 'page fault', 'working set', 'thrashing', 'ram'),
     {'uso_memoria': -8, 'paginacion_swap_mb': -600}, {'paginacion_swap_mb': 500}),
    (1, 'Analisis de bloqueos y concurrencia', 25, True,
     _r('bloqueo', 'deadlock', 'mutex', 'semaforo', 'lock', 'recurso critico', 'espera circular'),
     {'procesos_bloqueados': -3, 'iowait_disco': -3}, {'procesos_bloqueados': 3}),
    (1, 'Justificacion con metricas del sistema', 15, False,
     _r('cpu', 'memoria', 'disco', 'iowait', 'throughput', 'latencia', 'metrica', 'monitor'),
     {'throughput_procesos': 4}, {}),

    (2, 'Seleccion de politica de planificacion', 30, True,
     _r('mlfq', 'round robin', 'sjf', 'prioridad', 'quantum', 'inanicion', 'preemptivo'),
     {'tiempo_espera_cpu_ms': -70, 'throughput_procesos': 16}, {'tiempo_espera_cpu_ms': 35}),
    (2, 'Decision sobre memoria y swapping', 30, True,
     _r('swap', 'paginacion', 'working set', 'thrashing', 'memoria', 'page fault', 'fuga'),
     {'paginacion_swap_mb': -2300, 'uso_memoria': -12}, {'paginacion_swap_mb': 700}),
    (2, 'Control de concurrencia y E/S', 25, True,
     _r('deadlock', 'lock', 'timeout', 'orden de locks', 'semaforo', 'cola de e/s', 'disco'),
     {'procesos_bloqueados': -7, 'iowait_disco': -10}, {'procesos_bloqueados': 4}),
    (2, 'Comparacion de alternativas tecnicas', 15, False,
     _r('alternativa', 'comparar', 'costo', 'impacto', 'riesgo', 'opcion'),
     {'throughput_procesos': 5}, {}),

    (3, 'Plan de despliegue controlado', 30, True,
     _r('plan', 'piloto', 'rollback', 'ventana', 'responsable', 'cronograma', 'monitoreo'),
     {'throughput_procesos': 8, 'tiempo_espera_cpu_ms': -20}, {'iowait_disco': 4}),
    (3, 'Monitoreo de kernel y rendimiento', 25, True,
     _r('top', 'htop', 'perf', 'vmstat', 'iostat', 'sar', 'logs', 'alerta', 'kernel'),
     {'iowait_disco': -4, 'paginacion_swap_mb': -400}, {'tiempo_espera_cpu_ms': 20}),
    (3, 'Prevencion de regresiones', 25, False,
     _r('prueba de carga', 'baseline', 'sla', 'capacidad', 'regresion', 'validacion'),
     {'procesos_bloqueados': -2, 'throughput_procesos': 6}, {}),
    (3, 'Indicadores de seguimiento', 20, False,
     _r('kpi', 'indicador', 'seguimiento', 'umbral', 'tablero', 'alerta', 'medir'),
     {'tiempo_espera_cpu_ms': -15}, {}),
]

CONTEXTO = (
    'ServiPagos procesa transacciones en un servidor Linux. Despues de crecer la carga, el sistema se vuelve lento: '
    'tiempo de espera en CPU 240 ms, throughput 38 procesos/s, uso de memoria 88%, swap 5.200 MB, '
    '18 procesos bloqueados y 32% de espera por E/S de disco. Actuas como administrador de Sistemas Operativos '
    'y debes diagnosticar planificacion, memoria virtual, concurrencia y E/S antes de intervenir.'
)

SIT = (
    'La gerencia de ServiPagos te pide un diagnostico tecnico. Identifica el cuello de botella principal del sistema '
    'operativo: planificacion de CPU, memoria virtual/swap, bloqueos de concurrencia y espera por E/S. Sustenta con '
    'los indicadores actuales.'
)

RONDAS = [
    {'numero': 1, 'titulo': 'Diagnostico del SO', 'situacion': SIT,
     'etiqueta_decision': 'Diagnostico tecnico', 'etiqueta_justificacion': 'Justificacion con metricas'},
    {'numero': 2, 'titulo': 'Decision de ajuste',
     'situacion': ('Con el diagnostico hecho, decide que ajustar: politica de planificacion, memoria virtual/swap, '
                   'o control de concurrencia y E/S. Compara alternativas y explica el impacto esperado en espera, '
                   'throughput, memoria y procesos bloqueados.'),
     'etiqueta_decision': 'Decision de ajuste', 'etiqueta_justificacion': 'Justificacion tecnica'},
    {'numero': 3, 'titulo': 'Implementacion y monitoreo',
     'situacion': ('Implementa el cambio con piloto, ventana de despliegue, rollback y monitoreo con herramientas '
                   'del sistema operativo. Define umbrales para CPU, memoria, swap, bloqueos e iowait.'),
     'etiqueta_decision': 'Plan de implementacion', 'etiqueta_justificacion': 'Control y seguimiento'},
]


class Command(BaseCommand):
    help = 'Crea un caso real de Sistemas Operativos con indicadores propios.'

    @transaction.atomic
    def handle(self, *args, **options):
        profesor = (
            User.objects.filter(is_staff=True, is_active=True).first()
            or User.objects.filter(is_active=True).first()
        )
        mm = MateriaMalla.objects.filter(materia__nombre__icontains='Sistemas Operativos', activo=True).first()
        if not mm:
            self.stderr.write(self.style.ERROR('No encontre la materia Sistemas Operativos.'))
            return

        titulo = 'ServiPagos: cuello de botella en CPU, memoria y E/S'
        sim = _crear_simulacion(
            mm, profesor,
            titulo=titulo,
            tema='planificacion de CPU, memoria virtual, concurrencia y entrada/salida',
            rol='Administrador de Sistemas Operativos de ServiPagos',
            contexto=CONTEXTO,
            objetivo=('Diagnosticar y corregir un problema de rendimiento del sistema operativo usando planificacion '
                      'de CPU, memoria virtual, control de concurrencia y monitoreo de E/S.'),
            resultado=('El estudiante toma una decision tecnica sustentada con indicadores propios del sistema '
                       'operativo: espera de CPU, throughput, memoria, swap, bloqueos e iowait.'),
            sit_inicial=SIT, rondas=RONDAS, indicadores=IND, restricciones=RES, acciones=ACC, conceptos=CONC,
            condiciones=[('Respuesta de CPU aceptable', 'tiempo_espera_cpu_ms', '<=', 60, 5),
                         ('Throughput recuperado', 'throughput_procesos', '>=', 95, 5),
                         ('Swap controlado', 'paginacion_swap_mb', '<=', 250, 5)],
            empresa='ServiPagos', area='Sistemas Operativos',
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
                f'Caso creado en "{mm.materia.nombre}": "{sim.titulo}" con {len(IND)} indicadores propios.'
            ))
        else:
            self.stdout.write('El caso de Sistemas Operativos ya existia; simulaciones genericas archivadas.')
