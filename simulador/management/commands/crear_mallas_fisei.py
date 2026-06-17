"""Crea las mallas de informatica de la FISEI-UTA (Software y Tecnologias de la
Informacion) con materias nucleo reales y una simulacion 100% realista por malla
con indicadores propios bien medidos. Tambien crea los usuarios de prueba:

  - bpalate  (Byron Palate)  -> PROFESOR  (clave 12345)
  - jnunez18 (Jenrry Nunez)  -> ESTUDIANTE (clave 12345)

y los asigna a las mallas FISEI (bpalate como profesor de las materias, jnunez18
inscrito como estudiante). Tambien inscribe a emoyolema. Idempotente.

Uso: python manage.py crear_mallas_fisei
"""
import json
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from academico.models import (
    Carrera, Malla, NivelMalla, Materia, MateriaMalla, PeriodoAcademico,
    ProfesorMateria, InscripcionMalla,
)
from core.models import Institucion, PerfilUsuario
from simulador.models import (
    AccionSugeridaSimulacion, ConceptoEsperadoRonda, CondicionExitoSimulacion,
    CriterioEvaluacion, IndicadorSimulacion, RestriccionSimulacion, Simulacion,
)

User = get_user_model()


# --- Malla SOFTWARE (FISEI) ---
MATERIAS_SOFTWARE = [
    (1, 'SW-101', 'Fundamentos de Programacion'),
    (1, 'SW-102', 'Matematica Discreta'),
    (2, 'SW-201', 'Estructura de Datos'),
    (2, 'SW-202', 'Bases de Datos'),
    (3, 'SW-301', 'Programacion Web'),
    (3, 'SW-302', 'Ingenieria de Software'),
    (4, 'SW-401', 'Arquitectura de Software'),
    (4, 'SW-402', 'Calidad y Pruebas de Software'),
]

# Indicadores propios de calidad/rendimiento de software.
IND_SW = [
    ('disponibilidad', 'Disponibilidad del servicio', Decimal('98.5'), 90, 100, 'ALTO', '%', True),
    ('tiempo_respuesta_ms', 'Tiempo de respuesta', 4200, 100, 6000, 'BAJO', 'ms', True),
    ('errores_500', 'Errores HTTP 500 por dia', 15, 0, 50, 'BAJO', 'err/dia', True),
    ('consultas_lentas', 'Tiempo en consultas SQL lentas', 60, 0, 100, 'BAJO', '%', False),
    ('cobertura_pruebas', 'Cobertura de pruebas', 18, 0, 100, 'ALTO', '%', False),
    ('deuda_tecnica', 'Deuda tecnica', 70, 0, 100, 'BAJO', 'pts', False),
]
RES_SW = [
    ('El SLA exige disponibilidad >= 99.9%.', 'disponibilidad', '>=', Decimal('99.9'), 12),
    ('El tiempo de respuesta debe ser <= 800 ms.', 'tiempo_respuesta_ms', '<=', 800, 10),
    ('Los errores 500 deben reducirse a <= 1 por dia.', 'errores_500', '<=', 1, 12),
    ('La cobertura de pruebas debe ser >= 70%.', 'cobertura_pruebas', '>=', 70, 8),
]
ACC_SW = [
    ('Optimizar consultas SQL: indices, paginacion y resolver N+1',
     'Ataca el 60% del tiempo gastado en la base de datos y baja el tiempo de respuesta.',
     {'tiempo_respuesta_ms': -1800, 'consultas_lentas': -35, 'disponibilidad': 0.6}),
    ('Agregar pruebas automatizadas y pipeline CI/CD con despliegue controlado',
     'Sube la cobertura y evita romper produccion en cada despliegue.',
     {'cobertura_pruebas': 45, 'errores_500': -8, 'deuda_tecnica': -15}),
    ('Implementar cache y manejo de errores con logs estructurados (APM)',
     'Reduce carga, da visibilidad a los errores 500 y acelera respuestas.',
     {'tiempo_respuesta_ms': -1200, 'errores_500': -6, 'disponibilidad': 0.8}),
    ('Reescribir todo el sistema desde cero sin pruebas para ir mas rapido',
     'Suena radical: alto riesgo, rompe produccion y dispara los errores.',
     {'errores_500': 10, 'disponibilidad': -1.5, 'deuda_tecnica': 10}),
]


def _regla(*p):
    return json.dumps({'any': list(p)}, ensure_ascii=False)


CONC_SW = [
    (1, 'Diagnostico de rendimiento', 35, True,
     _regla('tiempo de respuesta', 'lentitud', 'consultas', 'sql', 'base de datos', 'errores 500', 'cuello de botella', 'profiling'),
     {'tiempo_respuesta_ms': -300, 'disponibilidad': 0.5}, {'disponibilidad': -1}),
    (1, 'Uso de herramientas de medicion', 30, True,
     _regla('profiling', 'apm', 'logs', 'monitoreo', 'metricas', 'baseline', 'explain', 'trazas'),
     {'consultas_lentas': -5}, {'errores_500': 2}),
    (1, 'Identificacion de causas', 20, False,
     _regla('causa', 'n+1', 'indice', 'consulta', 'memoria', 'concurrencia', 'configuracion'),
     {'tiempo_respuesta_ms': -150}, {}),
    (1, 'Justificacion con datos', 15, False,
     _regla('porque', 'dato', 'metrica', 'sla', 'evidencia'),
     {'disponibilidad': 0.3}, {}),

    (2, 'Solucion tecnica adecuada', 30, True,
     _regla('indice', 'cache', 'paginacion', 'optimizar', 'refactor', 'asincrono', 'consulta', 'query'),
     {'tiempo_respuesta_ms': -1500, 'consultas_lentas': -30, 'disponibilidad': 0.8}, {'tiempo_respuesta_ms': 300}),
    (2, 'Calidad y pruebas', 30, True,
     _regla('pruebas', 'test', 'cobertura', 'ci/cd', 'integracion continua', 'unitaria', 'automatizada'),
     {'cobertura_pruebas': 35, 'errores_500': -5, 'deuda_tecnica': -10}, {'cobertura_pruebas': -5}),
    (2, 'Comparacion de alternativas', 20, False,
     _regla('alternativa', 'comparar', 'costo', 'beneficio', 'opcion', 'escalabilidad'),
     {'deuda_tecnica': -5}, {}),
    (2, 'Justificacion tecnica', 20, False,
     _regla('porque', 'rendimiento', 'escalabilidad', 'mantenibilidad', 'sla'),
     {'disponibilidad': 0.3}, {}),

    (3, 'Plan de implementacion', 30, True,
     _regla('plan', 'cronograma', 'fases', 'responsable', 'rollback', 'despliegue', 'ci/cd'),
     {'errores_500': -4, 'tiempo_respuesta_ms': -400}, {'disponibilidad': -1}),
    (3, 'Monitoreo y observabilidad', 25, True,
     _regla('monitoreo', 'observabilidad', 'apm', 'alertas', 'logs', 'metricas', 'sla', 'dashboard'),
     {'disponibilidad': 1, 'errores_500': -3}, {'disponibilidad': -0.5}),
    (3, 'Reduccion de deuda tecnica', 25, False,
     _regla('refactor', 'deuda', 'limpieza', 'mantenibilidad', 'documentacion', 'estandar'),
     {'deuda_tecnica': -15}, {}),
    (3, 'Mejora continua', 20, False,
     _regla('mejora', 'retro', 'correctiva', 'auditoria', 'lecciones', 'iteracion'),
     {'cobertura_pruebas': 5}, {}),
]

CONTEXTO_SW = (
    'TiendaYa es una plataforma de e-commerce con 30.000 usuarios. En campañas presenta caidas y lentitud. '
    'Estado actual: disponibilidad 98.5% (SLA exige 99.9%), tiempo de respuesta promedio 4.2 s, 15 errores HTTP 500 '
    'por dia, el 60% del tiempo de cada peticion se gasta en consultas SQL lentas, cobertura de pruebas 18% y deuda '
    'tecnica alta. Actuas como Lider Tecnico y debes diagnosticar, decidir e implementar una solucion medible.'
)
SIT_SW = (
    'La gerencia de TiendaYa pide un informe en tres etapas. Primero: como Lider Tecnico, identifica el problema '
    'principal de rendimiento/calidad, sus causas (consultas SQL, errores 500, falta de pruebas) y los indicadores '
    'que usarias para medirlo. Justifica con datos.'
)
RONDAS_SW = [
    {'numero': 1, 'titulo': 'Diagnostico tecnico', 'situacion': SIT_SW,
     'espera_estudiante': 'Diagnosticar el rendimiento con metricas y herramientas.'},
    {'numero': 2, 'titulo': 'Decision tecnica',
     'situacion': ('Con el diagnostico hecho, decide la solucion: optimizar SQL/indices/cache, agregar pruebas y CI/CD, '
                   'observabilidad. Compara alternativas y elige una concreta justificando su impacto en tiempo de '
                   'respuesta, errores y disponibilidad.'),
     'espera_estudiante': 'Elegir solucion tecnica viable y justificar impacto.'},
    {'numero': 3, 'titulo': 'Plan e implementacion',
     'situacion': ('Implementa sin romper produccion: define fases, despliegue con rollback, monitoreo/observabilidad '
                   'del SLA, reduccion de deuda tecnica y mejora continua.'),
     'espera_estudiante': 'Plan con despliegue seguro, monitoreo y mejora continua.'},
]


def _crear_usuario(username, first, last, rol, institucion):
    u, _ = User.objects.get_or_create(username=username)
    u.first_name = first
    u.last_name = last
    u.is_staff = (rol == PerfilUsuario.PROFESOR)
    u.is_active = True
    u.set_password('12345')
    u.save()
    PerfilUsuario.objects.update_or_create(
        usuario=u, defaults={'rol': rol, 'institucion': institucion},
    )
    return u


def _crear_simulacion(materia_malla, profesor, titulo, tema, rol, contexto, objetivo,
                      resultado, sit_inicial, rondas, indicadores, restricciones,
                      acciones, conceptos, condiciones, empresa, area):
    if Simulacion.objects.filter(materia_malla=materia_malla, titulo=titulo).exists():
        return None
    sim = Simulacion.objects.create(
        materia_malla=materia_malla, profesor=profesor,
        tipo_simulacion=Simulacion.TIPO_CON_IA_DINAMICA,
        titulo=titulo, tema=tema, nivel_dificultad=Simulacion.DIFICULTAD_AVANZADA,
        maximo_decisiones=3, tiempo_estimado=30, rol_estudiante=rol,
        contexto=contexto, objetivo=objetivo, resultado_aprendizaje=resultado,
        situacion_inicial=sit_inicial,
        instrucciones_ia='Evalua solo contra la rubrica configurada. No inventes puntos. La nota la calcula SimutaV2.',
        parametros={'empresa': empresa, 'rondas': rondas, 'area': area},
        estado=Simulacion.PUBLICADA, fecha_publicacion=timezone.now(),
        activo=True, usuario_creacion=profesor,
    )
    for codigo, nombre, ini, vmin, vmax, dirc, unidad, crit in indicadores:
        IndicadorSimulacion.objects.create(
            simulacion=sim, codigo=codigo, nombre=nombre, valor_inicial=ini,
            valor_minimo=vmin, valor_maximo=vmax, direccion_optima=dirc,
            es_critico=crit, unidad=unidad, usuario_creacion=profesor,
        )
    for desc, ind, op, lim, pen in restricciones:
        RestriccionSimulacion.objects.create(
            simulacion=sim, descripcion=desc, codigo_indicador=ind, operador=op,
            valor_limite=lim, penalizacion=pen, usuario_creacion=profesor,
        )
    for desc, ind, op, obj, bon in condiciones:
        CondicionExitoSimulacion.objects.create(
            simulacion=sim, descripcion=desc, codigo_indicador=ind, operador=op,
            valor_objetivo=obj, bonificacion=bon, usuario_creacion=profesor,
        )
    for nombre, peso in [('Diagnostico', 30), ('Decision', 30), ('Plan', 25), ('Justificacion', 15)]:
        CriterioEvaluacion.objects.create(
            simulacion=sim, nombre=nombre, descripcion=f'Criterio orientativo: {nombre}.',
            peso=peso, usuario_creacion=profesor,
        )
    for texto, desc, imp in acciones:
        AccionSugeridaSimulacion.objects.create(
            simulacion=sim, texto=texto, descripcion=desc, impacto_base=imp, usuario_creacion=profesor,
        )
    for ronda, nombre, peso, crit, regla, imp_ok, imp_fail in conceptos:
        ConceptoEsperadoRonda.objects.create(
            simulacion=sim, numero_ronda=ronda, nombre=nombre, descripcion=f'{nombre} en {empresa}.',
            palabras_clave=regla, peso=peso, impacto_si_cumple=imp_ok, impacto_si_falta=imp_fail,
            retroalimentacion_si_cumple=f'Cumple: {nombre}.', retroalimentacion_si_falta=f'Falta: {nombre}.',
            es_critico=crit, usuario_creacion=profesor,
        )
    return sim


class Command(BaseCommand):
    help = 'Crea mallas FISEI (Software y TI) con simulaciones reales y usuarios de prueba.'

    @transaction.atomic
    def handle(self, *args, **options):
        admin = User.objects.filter(is_superuser=True).first() or User.objects.filter(is_staff=True).first()
        institucion = Institucion.objects.first() or Institucion.objects.create(
            nombre='Universidad Tecnica de Ambato', usuario_creacion=admin)

        # Usuarios solicitados
        bpalate = _crear_usuario('bpalate', 'Byron', 'Palate', PerfilUsuario.PROFESOR, institucion)
        jnunez = _crear_usuario('jnunez18', 'Jenrry', 'Nunez', PerfilUsuario.ESTUDIANTE, institucion)

        # Carrera + malla Software (FISEI)
        carrera_sw, _ = Carrera.objects.get_or_create(
            institucion=institucion, codigo='SW-FISEI',
            defaults={'nombre': 'Software', 'modalidad': 'Presencial', 'duracion_periodos': 9,
                      'titulo_otorga': 'Ingeniero en Software', 'usuario_creacion': bpalate})
        malla_sw, _ = Malla.objects.get_or_create(
            carrera=carrera_sw, codigo='FISEI-SW-2026',
            defaults={'nombre': 'Malla Software FISEI 2026', 'vigente': True,
                      'fecha_inicio': date(2026, 1, 1), 'usuario_creacion': bpalate})

        mm_flagship = None
        for nivel_num, codigo, nombre in MATERIAS_SOFTWARE:
            nivel, _ = NivelMalla.objects.get_or_create(
                malla=malla_sw, numero=nivel_num,
                defaults={'nombre': f'Nivel {nivel_num}', 'usuario_creacion': bpalate})
            materia, _ = Materia.objects.get_or_create(
                institucion=institucion, codigo=codigo,
                defaults={'nombre': nombre, 'creditos': 4, 'horas': 64, 'usuario_creacion': bpalate})
            mm, _ = MateriaMalla.objects.get_or_create(
                malla=malla_sw, materia=materia,
                defaults={'nivel': nivel, 'orden': nivel_num, 'usuario_creacion': bpalate})
            if codigo == 'SW-402':
                mm_flagship = mm

        sim_sw = _crear_simulacion(
            mm_flagship, bpalate,
            titulo='Crisis de rendimiento en TiendaYa: SLA, errores 500 y pruebas',
            tema='calidad y rendimiento de software, SLA y pruebas',
            rol='Lider Tecnico de TiendaYa',
            contexto=CONTEXTO_SW,
            objetivo=('Diagnosticar la causa de la lentitud y los errores, elegir una solucion (SQL, cache, pruebas, '
                      'CI/CD, observabilidad) y planificar su despliegue seguro con SLA.'),
            resultado=('El estudiante entrega una decision tecnica sustentada con metricas (tiempo de respuesta, '
                       'errores 500, cobertura, disponibilidad) y un plan con monitoreo y mejora continua.'),
            sit_inicial=SIT_SW, rondas=RONDAS_SW, indicadores=IND_SW, restricciones=RES_SW,
            acciones=ACC_SW, conceptos=CONC_SW,
            condiciones=[('Cumplir SLA de disponibilidad', 'disponibilidad', '>=', Decimal('99.9'), 5),
                         ('Respuesta rapida', 'tiempo_respuesta_ms', '<=', 500, 5)],
            empresa='TiendaYa', area='Software')

        # Periodo + asignaciones (bpalate profesor, jnunez + emoyolema estudiantes)
        periodo, _ = PeriodoAcademico.objects.get_or_create(
            institucion=institucion, nombre='Periodo Pruebas SimutaV2',
            defaults={'fecha_inicio': date(2026, 1, 1), 'fecha_fin': date(2026, 12, 31),
                      'activo_matricula': True, 'usuario_creacion': admin})
        periodo.activo = True
        periodo.activo_matricula = True
        periodo.save()

        # Mallas FISEI a las que asignar: Software (nueva) + TI (si existe la del comando anterior)
        mallas_fisei = list(Malla.objects.filter(codigo__in=['FISEI-SW-2026', 'TI-UTA-2026'], activo=True))
        estudiantes = [jnunez]
        if admin and not admin.is_anonymous:
            estudiantes.append(admin)

        asignadas = 0
        for malla in mallas_fisei:
            for mm in MateriaMalla.objects.filter(malla=malla, activo=True):
                ProfesorMateria.objects.get_or_create(
                    profesor=bpalate, materia_malla=mm, periodo=periodo,
                    defaults={'usuario_creacion': bpalate})
                asignadas += 1
            for est in estudiantes:
                InscripcionMalla.objects.get_or_create(
                    estudiante=est, malla=malla, periodo=periodo,
                    defaults={'estado': InscripcionMalla.ACTIVA, 'usuario_creacion': admin})

        self.stdout.write(self.style.SUCCESS('Mallas FISEI listas.'))
        self.stdout.write(f'  Software: {malla_sw.codigo} ({len(MATERIAS_SOFTWARE)} materias)')
        self.stdout.write(f'  Mallas asignadas: {", ".join(m.codigo for m in mallas_fisei)}')
        self.stdout.write(f'  Materias asignadas a bpalate (profesor): {asignadas}')
        self.stdout.write('  Usuarios: bpalate / 12345 (PROFESOR), jnunez18 / 12345 (ESTUDIANTE)')
        if sim_sw:
            self.stdout.write(self.style.SUCCESS(f'  Simulacion Software: "{sim_sw.titulo}" con {len(IND_SW)} indicadores propios.'))
        else:
            self.stdout.write('  Simulacion Software ya existia.')
