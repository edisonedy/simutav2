"""Crea una malla REAL del area de Tecnologias de la Informacion con una
simulacion 100% realista de Redes y sus indicadores propios (latencia, perdida
de paquetes, disponibilidad/SLA, saturacion del enlace, incidentes de seguridad,
MTTR). Idempotente: se puede correr varias veces sin duplicar.

Uso: python manage.py crear_malla_ti_redes
"""
import json
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from academico.models import (
    Carrera, Malla, NivelMalla, Materia, MateriaMalla, PeriodoAcademico, ProfesorMateria,
)
from core.models import Institucion
from simulador.models import (
    AccionSugeridaSimulacion, ConceptoEsperadoRonda, CondicionExitoSimulacion,
    CriterioEvaluacion, IndicadorSimulacion, RestriccionSimulacion, Simulacion,
)


# Materias de la malla (nivel, codigo, nombre)
MATERIAS_TI = [
    (1, 'TI-101', 'Fundamentos de Redes'),
    (1, 'TI-102', 'Sistemas Operativos'),
    (2, 'TI-201', 'Redes de Computadoras'),
    (2, 'TI-202', 'Administracion de Servidores'),
    (3, 'TI-301', 'Seguridad de Redes'),
    (3, 'TI-302', 'Infraestructura y Cloud'),
    (4, 'TI-401', 'Gestion de Redes y Telecomunicaciones'),
]

# Indicadores propios de redes: (codigo, nombre, inicial, min, max, direccion, unidad, critico)
INDICADORES_REDES = [
    ('disponibilidad', 'Disponibilidad / SLA', Decimal('97.2'), 90, 100, 'ALTO', '%', True),
    ('latencia_ms', 'Latencia', 180, 5, 300, 'BAJO', 'ms', True),
    ('perdida_paquetes', 'Perdida de paquetes', 4, 0, 15, 'BAJO', '%', True),
    ('saturacion_wan', 'Saturacion del enlace WAN', 88, 0, 100, 'BAJO', '%', False),
    ('incidentes_seguridad', 'Incidentes de seguridad / mes', 12, 0, 30, 'BAJO', 'inc', False),
    ('mttr_horas', 'MTTR (tiempo medio de reparacion)', 6, 0, 24, 'BAJO', 'h', False),
]

# Restricciones tipo SLA: (descripcion, indicador, operador, limite, penalizacion)
RESTRICCIONES_REDES = [
    ('El SLA exige disponibilidad de al menos 99.5%.', 'disponibilidad', '>=', Decimal('99.5'), 12),
    ('La latencia para servicios criticos debe mantenerse <= 80 ms.', 'latencia_ms', '<=', 80, 10),
    ('La perdida de paquetes debe ser <= 1%.', 'perdida_paquetes', '<=', 1, 10),
    ('El enlace WAN no debe superar 70% de uso sostenido.', 'saturacion_wan', '<=', 70, 8),
    ('Los incidentes de seguridad deben reducirse a <= 3 al mes.', 'incidentes_seguridad', '<=', 3, 10),
]

# Decisiones de ejemplo (texto, descripcion, impacto). Incluye una riesgosa.
ACCIONES_REDES = [
    ('Aplicar QoS y segmentar la red por VLAN para priorizar trafico critico',
     'Prioriza voz/datos criticos y reduce congestion sin cambiar el enlace.',
     {'latencia_ms': -25, 'saturacion_wan': -12, 'disponibilidad': 1}),
    ('Desplegar enlaces redundantes con failover automatico (HSRP/VRRP)',
     'Da alta disponibilidad: si un enlace cae, otro toma el trafico.',
     {'disponibilidad': 2, 'mttr_horas': -2, 'latencia_ms': -5}),
    ('Reforzar seguridad con firewall de nueva generacion, IDS/IPS y segmentacion',
     'Reduce los incidentes y contiene el movimiento lateral de ataques.',
     {'incidentes_seguridad': -7, 'disponibilidad': 1}),
    ('Solo ampliar el ancho de banda del enlace WAN sin rediseniar la red',
     'Alivia la saturacion hoy, pero es caro y no ataca la causa ni la seguridad.',
     {'saturacion_wan': -20, 'incidentes_seguridad': 3, 'disponibilidad': -0.5}),
]


def _regla(*palabras):
    return json.dumps({'any': list(palabras)}, ensure_ascii=False)


# Conceptos por ronda: (ronda, nombre, peso, critico, regla, impacto_cumple, impacto_falta)
CONCEPTOS_REDES = [
    (1, 'Diagnostico tecnico de la red', 35, True,
     _regla('latencia', 'perdida de paquetes', 'paquetes', 'disponibilidad', 'saturacion', 'ancho de banda', 'congestion', 'jitter'),
     {'latencia_ms': -10, 'disponibilidad': 1}, {'disponibilidad': -1}),
    (1, 'Uso de herramientas de monitoreo', 30, True,
     _regla('monitoreo', 'snmp', 'ping', 'traceroute', 'wireshark', 'netflow', 'baseline', 'dashboard'),
     {'saturacion_wan': -3, 'mttr_horas': -0.5}, {'mttr_horas': 1}),
    (1, 'Identificacion de causas', 20, False,
     _regla('causa', 'cuello de botella', 'broadcast', 'bucle', 'configuracion', 'hardware', 'enlace'),
     {'mttr_horas': -1}, {}),
    (1, 'Justificacion con metricas', 15, False,
     _regla('porque', 'datos', 'metrica', 'metricas', 'sla', 'evidencia'),
     {'disponibilidad': 0.5}, {}),

    (2, 'Solucion de red adecuada', 30, True,
     _regla('qos', 'vlan', 'segmentacion', 'balanceo', 'redundancia', 'enlace', 'ancho de banda', 'mpls', 'sd-wan'),
     {'latencia_ms': -30, 'saturacion_wan': -15, 'disponibilidad': 1}, {'latencia_ms': 10}),
    (2, 'Seguridad de la red', 30, True,
     _regla('firewall', 'vpn', 'segmentacion', 'acl', 'ids', 'ips', 'hardening', 'cifrado'),
     {'incidentes_seguridad': -6, 'disponibilidad': 0.5}, {'incidentes_seguridad': 4}),
    (2, 'Comparacion de alternativas', 20, False,
     _regla('alternativa', 'comparar', 'costo', 'beneficio', 'opcion', 'escalabilidad'),
     {'mttr_horas': -1}, {}),
    (2, 'Justificacion tecnica', 20, False,
     _regla('porque', 'sla', 'rendimiento', 'escalabilidad', 'disponibilidad'),
     {'disponibilidad': 0.5}, {}),

    (3, 'Plan de implementacion', 30, True,
     _regla('plan', 'cronograma', 'ventana de mantenimiento', 'responsable', 'fases', 'rollback'),
     {'saturacion_wan': -10, 'latencia_ms': -10}, {'disponibilidad': -1}),
    (3, 'Redundancia y alta disponibilidad', 25, True,
     _regla('redundancia', 'failover', 'hsrp', 'vrrp', 'balanceo', 'respaldo', 'alta disponibilidad'),
     {'disponibilidad': 1.5, 'mttr_horas': -2}, {'disponibilidad': -1}),
    (3, 'Monitoreo y SLA continuo', 25, False,
     _regla('monitoreo', 'sla', 'kpi', 'alertas', 'dashboard', 'snmp'),
     {'incidentes_seguridad': -3, 'mttr_horas': -1}, {}),
    (3, 'Mejora continua y documentacion', 20, False,
     _regla('mejora', 'auditoria', 'correctiva', 'documentacion', 'lecciones'),
     {'disponibilidad': 0.5}, {}),
]


CONTEXTO = (
    'DataNet Soluciones S.A. opera una red corporativa que conecta su matriz y 4 sucursales. '
    'En las ultimas semanas los usuarios reportan lentitud y caidas. Estado actual: disponibilidad 97.2% '
    '(SLA exige 99.5%), latencia promedio 180 ms a servicios criticos, perdida de paquetes 4%, el enlace '
    'WAN principal opera al 88% de uso sostenido, 12 incidentes de seguridad en el ultimo mes y un MTTR de 6 horas. '
    'Actuas como Administrador de Redes y debes diagnosticar, decidir e implementar una solucion medible.'
)
SITUACION_INICIAL = (
    'La gerencia de DataNet te pide un informe en tres etapas. Primero: como Administrador de Redes, '
    'identifica el problema principal de la red, sus causas probables y los indicadores que usarias para '
    'medirlo (latencia, perdida de paquetes, disponibilidad, saturacion del enlace, incidentes). Justifica con datos.'
)
RONDAS = [
    {'numero': 1, 'titulo': 'Diagnostico de la red',
     'situacion': SITUACION_INICIAL,
     'espera_estudiante': 'Diagnosticar con metricas de red y herramientas de monitoreo.'},
    {'numero': 2, 'titulo': 'Decision tecnica',
     'situacion': ('Con el diagnostico hecho, la gerencia pide una decision en 48 horas. Compara alternativas '
                   '(QoS/VLAN, enlaces redundantes, seguridad, ampliar ancho de banda), elige una solucion concreta '
                   'y justifica su impacto en latencia, disponibilidad y seguridad.'),
     'espera_estudiante': 'Elegir una solucion de red viable y justificar impacto y riesgo.'},
    {'numero': 3, 'titulo': 'Plan de implementacion',
     'situacion': ('La solucion elegida debe implementarse sin afectar la operacion. Define fases, ventana de '
                   'mantenimiento, responsables, redundancia/alta disponibilidad, monitoreo continuo del SLA y '
                   'acciones correctivas si algo falla.'),
     'espera_estudiante': 'Plan ejecutable con redundancia, monitoreo de SLA y mejora continua.'},
]


class Command(BaseCommand):
    help = 'Crea la malla de Tecnologias de la Informacion con una simulacion real de Redes.'

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        profesor = (User.objects.filter(is_staff=True, is_active=True).first()
                    or User.objects.filter(is_active=True).first())
        if not profesor:
            self.stderr.write(self.style.ERROR('No hay usuarios activos.'))
            return

        institucion = Institucion.objects.first()
        if not institucion:
            institucion = Institucion.objects.create(nombre='Universidad Tecnica de Ambato', usuario_creacion=profesor)

        carrera, _ = Carrera.objects.get_or_create(
            institucion=institucion, codigo='TI-UTA',
            defaults={'nombre': 'Tecnologias de la Informacion', 'modalidad': 'Presencial',
                      'duracion_periodos': 8, 'titulo_otorga': 'Ingeniero en Tecnologias de la Informacion',
                      'usuario_creacion': profesor},
        )
        malla, _ = Malla.objects.get_or_create(
            carrera=carrera, codigo='TI-UTA-2026',
            defaults={'nombre': 'Malla TI 2026', 'vigente': True,
                      'fecha_inicio': date(2026, 1, 1), 'usuario_creacion': profesor},
        )

        materia_malla_redes = None
        for nivel_num, codigo, nombre in MATERIAS_TI:
            nivel, _ = NivelMalla.objects.get_or_create(
                malla=malla, numero=nivel_num,
                defaults={'nombre': f'Nivel {nivel_num}', 'usuario_creacion': profesor},
            )
            materia, _ = Materia.objects.get_or_create(
                institucion=institucion, codigo=codigo,
                defaults={'nombre': nombre, 'creditos': 4, 'horas': 64, 'usuario_creacion': profesor},
            )
            mm, _ = MateriaMalla.objects.get_or_create(
                malla=malla, materia=materia,
                defaults={'nivel': nivel, 'orden': nivel_num, 'usuario_creacion': profesor},
            )
            if codigo == 'TI-201':
                materia_malla_redes = mm

        # Periodo + inscripcion + asignacion para que el usuario de prueba pueda jugar.
        periodo, _ = PeriodoAcademico.objects.get_or_create(
            institucion=institucion, nombre='Periodo Pruebas SimutaV2',
            defaults={'fecha_inicio': date(2026, 1, 1), 'fecha_fin': date(2026, 12, 31),
                      'activo_matricula': True, 'usuario_creacion': profesor},
        )

        sim = self._crear_simulacion_redes(materia_malla_redes, profesor)
        ProfesorMateria.objects.get_or_create(
            profesor=profesor, materia_malla=materia_malla_redes, periodo=periodo,
            defaults={'usuario_creacion': profesor},
        )

        self.stdout.write(self.style.SUCCESS('Malla TI creada/actualizada.'))
        self.stdout.write(f'  Carrera: {carrera.nombre} | Malla: {malla.codigo} | Materias: {len(MATERIAS_TI)}')
        if sim:
            self.stdout.write(self.style.SUCCESS(
                f'  Simulacion REAL de Redes: "{sim.titulo}" (publicada) con {len(INDICADORES_REDES)} indicadores propios.'))
        else:
            self.stdout.write('  La simulacion de Redes ya existia (no se duplico).')

    def _crear_simulacion_redes(self, materia_malla, profesor):
        titulo = 'Crisis de red en DataNet: SLA, latencia y seguridad'
        if Simulacion.objects.filter(materia_malla=materia_malla, titulo=titulo).exists():
            return None

        sim = Simulacion.objects.create(
            materia_malla=materia_malla, profesor=profesor,
            tipo_simulacion=Simulacion.TIPO_CON_IA_DINAMICA,
            titulo=titulo, tema='gestion de redes, SLA, rendimiento y seguridad',
            nivel_dificultad=Simulacion.DIFICULTAD_AVANZADA,
            maximo_decisiones=3, tiempo_estimado=30,
            rol_estudiante='Administrador de Redes de DataNet Soluciones',
            contexto=CONTEXTO,
            objetivo=('Aplicar conceptos de redes para diagnosticar la causa de la baja disponibilidad y la '
                      'alta latencia, elegir una solucion viable y planificar su implementacion con SLA y seguridad.'),
            resultado_aprendizaje=('El estudiante entrega una decision tecnica de redes sustentada con metricas '
                                   '(latencia, perdida, disponibilidad, SLA), seguridad y un plan con redundancia y monitoreo.'),
            situacion_inicial=SITUACION_INICIAL,
            instrucciones_ia=('Evalua solo contra la rubrica configurada de redes. No inventes puntos. La nota la '
                              'calcula SimutaV2 con conceptos, impactos y restricciones (SLA).'),
            parametros={'empresa': 'DataNet Soluciones S.A.', 'rondas': RONDAS,
                        'materia': 'Redes de Computadoras', 'nivel': 2, 'area': 'Tecnologias de la Informacion'},
            estado=Simulacion.PUBLICADA, fecha_publicacion=timezone.now(),
            activo=True, usuario_creacion=profesor,
        )

        for codigo, nombre, inicial, vmin, vmax, direccion, unidad, critico in INDICADORES_REDES:
            IndicadorSimulacion.objects.create(
                simulacion=sim, codigo=codigo, nombre=nombre,
                valor_inicial=inicial, valor_minimo=vmin, valor_maximo=vmax,
                direccion_optima=direccion, es_critico=critico, unidad=unidad, usuario_creacion=profesor,
            )

        for descripcion, indicador, operador, limite, penalizacion in RESTRICCIONES_REDES:
            RestriccionSimulacion.objects.create(
                simulacion=sim, descripcion=descripcion, codigo_indicador=indicador,
                operador=operador, valor_limite=limite, penalizacion=penalizacion, usuario_creacion=profesor,
            )

        for descripcion, indicador, operador, objetivo, bonificacion in [
            ('Cumplir el SLA de disponibilidad', 'disponibilidad', '>=', Decimal('99.5'), 5),
            ('Latencia optima para servicios criticos', 'latencia_ms', '<=', 60, 5),
        ]:
            CondicionExitoSimulacion.objects.create(
                simulacion=sim, descripcion=descripcion, codigo_indicador=indicador,
                operador=operador, valor_objetivo=objetivo, bonificacion=bonificacion, usuario_creacion=profesor,
            )

        for nombre, peso in [('Diagnostico de red', 30), ('Decision y seguridad', 30),
                             ('Plan e implementacion', 25), ('Justificacion tecnica', 15)]:
            CriterioEvaluacion.objects.create(
                simulacion=sim, nombre=nombre, descripcion=f'Criterio orientativo de Redes: {nombre}.',
                peso=peso, usuario_creacion=profesor,
            )

        for texto, descripcion, impacto in ACCIONES_REDES:
            AccionSugeridaSimulacion.objects.create(
                simulacion=sim, texto=texto, descripcion=descripcion, impacto_base=impacto, usuario_creacion=profesor,
            )

        for ronda, nombre, peso, critico, regla, impacto_ok, impacto_fail in CONCEPTOS_REDES:
            ConceptoEsperadoRonda.objects.create(
                simulacion=sim, numero_ronda=ronda, nombre=nombre,
                descripcion=f'{nombre} en la red de DataNet.', palabras_clave=regla, peso=peso,
                impacto_si_cumple=impacto_ok, impacto_si_falta=impacto_fail,
                retroalimentacion_si_cumple=f'Cumple: {nombre}.', retroalimentacion_si_falta=f'Falta: {nombre}.',
                es_critico=critico, usuario_creacion=profesor,
            )

        return sim
