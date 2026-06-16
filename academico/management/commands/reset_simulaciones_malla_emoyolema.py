import json
import re
import unicodedata
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from academico.models import InscripcionMalla, MateriaMalla, PeriodoAcademico, ProfesorMateria
from core.models import PerfilUsuario
from simulador.models import (
    AccionSugeridaSimulacion,
    ConceptoEsperadoRonda,
    CondicionExitoSimulacion,
    CriterioEvaluacion,
    IndicadorSimulacion,
    IntentoSimulacion,
    PasoSimulacion,
    RestriccionSimulacion,
    Simulacion,
)


PROMPT_GENERADOR_CASOS = """
Eres un generador de casos academicos para simulaciones universitarias.
Genera una situacion realista, breve y aplicada segun la materia indicada.
Usa empresa ficticia, datos concretos, rondas de analisis inicial, decision e implementacion,
indicadores iniciales, restricciones y conceptos esperados. Devuelve solo JSON valido.
"""


CASOS_POR_MATERIA = {
    'estadistica': {
        'empresa': 'Datos y Metricas Cia. Ltda.',
        'tema': 'analisis estadistico de datos de ventas y satisfaccion',
        'datos': 'ventas mensuales con media $38.500, desviacion $6.200, satisfaccion 68%, tendencia a la baja en 3 meses y coeficiente de variacion 16%.',
    },
    'contabilidad': {
        'empresa': 'Costos Controlados S.A.',
        'tema': 'costos de produccion, margen y punto de equilibrio',
        'datos': 'costo unitario $45, margen bruto 22%, inventario lento 45 dias rotacion, punto de equilibrio 1.200 unidades y costos fijos $28.000.',
    },
    'financ': {
        'empresa': 'Liquidez Inmediata S.A.S.',
        'tema': 'liquidez, cartera vencida y financiamiento',
        'datos': 'liquidez corriente 0.85, cartera vencida 38%, deuda total 62%, flujo de caja libre negativo $4.200 y necesidad de financiamiento $25.000.',
    },
    'derecho': {
        'empresa': 'Cumplimiento Legal Abogados S.A.S.',
        'tema': 'riesgos laborales, contratos y cumplimiento normativo',
        'datos': 'horas extra no pagadas 240 al mes, 12 liquidaciones mal aplicadas, 3 demandas en curso, riesgo legal alto y multas acumuladas $8.500.',
    },
    'programacion': {
        'empresa': 'DevSolutions Cia. Ltda.',
        'tema': 'rendimiento, seguridad y calidad del codigo',
        'datos': 'errores 500 en produccion 15/dia, tiempo de respuesta 4.2s, consultas pesadas 60%, sin logs estructurados y despliegue manual con errores frecuentes.',
    },
    'marketing': {
        'empresa': 'Clientes Estrategicos S.A.',
        'tema': 'conversion de ventas y campanas digitales',
        'datos': 'tasa de conversion 1.2%, ventas mensuales $22.000 (caida 18% interanual), costo por lead $45, retencion 62% y segmentacion de clientes desactualizada.',
    },
    'talento': {
        'empresa': 'Personas y Resultados S.A.S.',
        'tema': 'rotacion, clima laboral y desempeno',
        'datos': 'rotacion anual 32%, ausentismo 14%, bajo desempeno en 40% del equipo, clima laboral 58/100 y 9 quejas por acoso laboral sin resolver.',
    },
    'produccion': {
        'empresa': 'Industrias Eficientes Cia. Ltda.',
        'tema': 'calidad, capacidad y tiempos de produccion',
        'datos': 'defectos 11%, entregas tardias 28%, capacidad utilizada 68%, inventario en proceso $22.000 y tiempo de ciclo 14 dias sobre lo planificado.',
    },
    'emprendimiento': {
        'empresa': 'Innovacion y Mercado S.A.S.',
        'tema': 'plan de negocio y viabilidad de mercado',
        'datos': 'inversion necesaria $18.000, ventas proyectadas $8.200/mes, TIR estimada 11%, periodo de recuperacion 14 meses y competencia creciendo 25% anual.',
    },
    'sistemas': {
        'empresa': 'Tecnologia Empresarial S.A.',
        'tema': 'sistemas de informacion, continuidad y seguridad',
        'datos': '32 tickets abiertos criticos, 7 horas de caida mensual, errores de integracion 12%, sin plan de continuidad y satisfaccion de usuarios 62%.',
    },
    'investigacion': {
        'empresa': 'Metodo Cientifico Consultores',
        'tema': 'metodologia de investigacion y analisis de datos',
        'datos': 'muestra de 320 sujetos, error muestral 7%, tasa de respuesta 45%, datos incompletos 18% y sesgo de seleccion identificado en la muestra.',
    },
    'proyectos': {
        'empresa': 'Gestion de Proyectos Integral S.A.',
        'tema': 'planificacion, cronograma y control de proyectos',
        'datos': 'cronograma retrasado 23%, presupuesto ejecutado 82%, riesgos no mitigados 5, alcance mal definido y stakeholders desalineados con los objetivos.',
    },
    'etica': {
        'empresa': 'Integridad Corporativa S.A.S.',
        'tema': 'etica organizacional y responsabilidad social',
        'datos': '14 quejas eticas sin resolver, codigo de etica desactualizado, 3 conflictos de interes detectados, clima etico 52/100 y capacitacion pendiente al 70% del personal.',
    },
}


CASO_DEFAULT = {
    'empresa': 'Gestion Integral Cia. Ltda.',
    'tema': 'gestion administrativa y mejora continua',
    'datos': 'ventas $42.000 mensuales, 18 reclamos activos, retraso promedio 6 dias en entregas y productividad 62%.',
}


# Decisiones realistas que el estudiante puede tomar (ejemplos de cosas reales que
# pueden pasar). Cada accion tiene consecuencias sobre los indicadores: hay
# opciones solidas y opciones riesgosas/apresuradas, como en un simulador real.
ACCIONES_POR_MATERIA = {
    'financ': [
        ('Renegociar la deuda y refinanciar a largo plazo',
         'Reestructura $25.000 de deuda para aliviar el flujo de caja sin frenar la operacion.',
         {'viabilidad': 12, 'riesgo': -8, 'impacto': 8}),
        ('Activar cobranza de la cartera vencida con descuento por pronto pago',
         'Recupera parte del 38% de cartera vencida y mejora la liquidez corriente.',
         {'calidad_analisis': 8, 'riesgo': -6, 'impacto': 10}),
        ('Tomar un credito bancario inmediato sin revisar el flujo de caja',
         'Cubre el deficit hoy, pero sube el endeudamiento y el riesgo financiero.',
         {'riesgo': 14, 'viabilidad': -8, 'impacto': -5}),
    ],
    'contabilidad': [
        ('Recalcular el costo unitario y depurar costos fijos innecesarios',
         'Ataca el costo de $45/unidad y los $28.000 de costos fijos para subir el margen.',
         {'calidad_analisis': 12, 'viabilidad': 8, 'impacto': 8}),
        ('Acelerar la rotacion del inventario lento (45 dias)',
         'Libera caja y reduce el costo de mantener inventario.',
         {'viabilidad': 8, 'riesgo': -6}),
        ('Subir precios de golpe para forzar el margen',
         'Mejora el margen en papel, pero arriesga perder ventas y clientes.',
         {'impacto': -8, 'riesgo': 12, 'viabilidad': -6}),
    ],
    'produccion': [
        ('Implementar control de calidad en linea para bajar el 11% de defectos',
         'Reduce defectos y entregas tardias con inspeccion por etapa.',
         {'calidad_analisis': 12, 'riesgo': -10, 'impacto': 8}),
        ('Reprogramar la capacidad (68% usada) y nivelar la carga',
         'Equilibra el cuello de botella y baja el tiempo de ciclo.',
         {'viabilidad': 10, 'impacto': 8}),
        ('Acelerar la produccion sin controles para cumplir entregas',
         'Cumple plazos hoy, pero dispara defectos y retrabajos.',
         {'riesgo': 14, 'calidad_analisis': -8}),
    ],
    'derecho': [
        ('Regularizar horas extra y liquidaciones segun la ley',
         'Paga las 240 horas extra y corrige las 12 liquidaciones mal aplicadas.',
         {'riesgo': -14, 'viabilidad': 8, 'impacto': 8}),
        ('Abrir conciliacion en las 3 demandas en curso',
         'Reduce el riesgo legal y las multas acumuladas con acuerdos.',
         {'riesgo': -10, 'calidad_analisis': 8}),
        ('Ignorar las demandas y seguir operando igual',
         'Ahorra esfuerzo hoy, pero el riesgo legal y las multas crecen.',
         {'riesgo': 16, 'impacto': -8, 'viabilidad': -6}),
    ],
    'programacion': [
        ('Optimizar las consultas SQL pesadas y agregar indices',
         'Ataca el 60% de consultas pesadas y el tiempo de respuesta de 4.2s.',
         {'calidad_analisis': 12, 'riesgo': -10, 'impacto': 10}),
        ('Agregar logs estructurados y manejo de errores 500',
         'Da visibilidad a los 15 errores 500 diarios para corregirlos.',
         {'calidad_analisis': 8, 'riesgo': -8}),
        ('Subir el cambio a produccion sin pruebas para ir rapido',
         'Despliega ya, pero el despliegue manual con errores sube el riesgo.',
         {'riesgo': 15, 'calidad_analisis': -8}),
    ],
    'estadistica': [
        ('Analizar la tendencia y la variabilidad antes de concluir',
         'Usa media $38.500, desviacion $6.200 y CV 16% para decidir con datos.',
         {'calidad_analisis': 12, 'claridad': 10, 'impacto': 8}),
        ('Segmentar los datos para encontrar la causa de la caida',
         'Aisla los 3 meses a la baja por grupo para actuar focalizado.',
         {'calidad_analisis': 10, 'riesgo': -6}),
        ('Concluir solo con el promedio e ignorar la dispersion',
         'Decision rapida pero sesgada: ignora la variabilidad real.',
         {'calidad_analisis': -8, 'riesgo': 10}),
    ],
}

ACCIONES_DEFAULT = [
    ('Diagnosticar el problema con datos antes de decidir',
     'Levanta indicadores y causas raiz para sustentar la decision.',
     {'calidad_analisis': 10, 'claridad': 8}),
    ('Definir un plan con responsables, tiempos y controles',
     'Convierte la decision en acciones medibles y verificables.',
     {'viabilidad': 10, 'impacto': 8, 'riesgo': -6}),
    ('Actuar de inmediato sin analizar ni planificar',
     'Avanza rapido, pero sin control el riesgo se dispara.',
     {'riesgo': 14, 'viabilidad': -8}),
]


def acciones_del_caso(nombre_materia):
    materia = nombre_materia.lower()
    for clave, acciones in ACCIONES_POR_MATERIA.items():
        if clave in materia:
            return acciones
    return ACCIONES_DEFAULT


def palabras_materia(nombre):
    texto = unicodedata.normalize('NFKD', nombre).encode('ascii', 'ignore').decode('ascii')
    palabras = re.findall(r'[a-zA-Z]{4,}', texto.lower())
    return sorted(set(palabras))


def regla_any(*grupos):
    valores = []
    for grupo in grupos:
        valores.extend(grupo)
    return {'any': sorted(set(v for v in valores if v))}


def construir_caso(nombre_materia, nivel):
    materia = nombre_materia.lower()
    caso = CASO_DEFAULT
    for clave, datos_caso in CASOS_POR_MATERIA.items():
        if clave in materia:
            caso = datos_caso
            break

    empresa = caso['empresa']
    tema = caso['tema']
    datos = caso['datos']

    contexto = (
        f'{empresa} necesita resolver un problema de {tema}. '
        f'Estado actual: {datos} El estudiante actua como responsable tecnico de {nombre_materia} '
        'y debe proponer una respuesta breve, concreta y medible.'
    )
    objetivo = (
        f'Aplicar {nombre_materia} para analizar el problema, comparar alternativas '
        'y definir una implementacion viable con indicadores de control.'
    )
    resultado = (
        'El estudiante entrega una decision profesional sustentada con datos, riesgos, '
        'indicadores y acciones verificables.'
    )
    rondas = [
        {
            'numero': 1,
            'titulo': 'Analisis inicial',
            'situacion': (
                f'{empresa} reporta este estado: {datos} Como analista de {nombre_materia}, '
                'identifica el problema principal, sus causas probables y los indicadores que usarias para medirlo.'
            ),
            'espera_estudiante': 'Diagnosticar con datos, conceptos de la materia e indicadores medibles.',
        },
        {
            'numero': 2,
            'titulo': 'Decision',
            'situacion': (
                f'La gerencia de {empresa} pide una decision en 48 horas. Compara al menos dos alternativas, '
                'estima riesgos y elige una opcion concreta que pueda ejecutarse con los recursos actuales.'
            ),
            'espera_estudiante': 'Comparar alternativas, elegir una y justificar viabilidad, impacto y riesgo.',
        },
        {
            'numero': 3,
            'titulo': 'Implementacion',
            'situacion': (
                f'La alternativa elegida debe implementarse en el nivel {nivel}. Define responsables, pasos, '
                'tiempos, controles, indicadores de seguimiento y acciones correctivas si el resultado falla.'
            ),
            'espera_estudiante': 'Plantear plan de accion, controles, KPI y mejora/correccion.',
        },
    ]
    return {
        'empresa': empresa,
        'tema': tema,
        'contexto': contexto,
        'objetivo': objetivo,
        'resultado_aprendizaje': resultado,
        'situacion_inicial': rondas[0]['situacion'],
        'rondas': rondas,
    }


def _restricciones_por_dificultad(dificultad):
    if dificultad == Simulacion.DIFICULTAD_BASICA:
        return [
            ('La propuesta no debe quedar sin analisis tecnico suficiente.', 'calidad_analisis', '>=', 40, 10),
            ('La decision debe ser viable para ejecutarse.', 'viabilidad', '>=', 40, 10),
            ('El riesgo no debe quedar en zona critica.', 'riesgo', '<=', 85, 15),
            ('La justificacion debe ser clara y defendible.', 'claridad', '>=', 40, 5),
        ]
    elif dificultad == Simulacion.DIFICULTAD_AVANZADA:
        return [
            ('La propuesta debe tener analisis tecnico profundo.', 'calidad_analisis', '>=', 60, 20),
            ('La decision debe ser altamente viable.', 'viabilidad', '>=', 60, 20),
            ('El riesgo debe mantenerse controlado.', 'riesgo', '<=', 70, 25),
            ('La justificacion debe ser clara y rigurosa.', 'claridad', '>=', 60, 15),
        ]
    # MEDIA (default)
    return [
        ('La propuesta no debe quedar sin analisis tecnico suficiente.', 'calidad_analisis', '>=', 50, 15),
        ('La decision debe ser viable para ejecutarse.', 'viabilidad', '>=', 50, 15),
        ('El riesgo no debe quedar en zona critica.', 'riesgo', '<=', 75, 20),
        ('La justificacion debe ser clara y defendible.', 'claridad', '>=', 50, 10),
    ]


def _riesgo_minimo_por_dificultad(dificultad):
    if dificultad == Simulacion.DIFICULTAD_BASICA:
        return 5
    elif dificultad == Simulacion.DIFICULTAD_AVANZADA:
        return 15
    return 10


class Command(BaseCommand):
    help = 'Borra simulaciones previas y crea examenes por materia para emoyolema.'

    @transaction.atomic
    def handle(self, *args, **options):
        usuario = User.objects.get(username='emoyolema')
        perfil, _ = PerfilUsuario.objects.get_or_create(usuario=usuario)

        malla = (
            MateriaMalla.objects
            .filter(malla__codigo='ADM-UTA-2026', activo=True, malla__activo=True)
            .values('malla')
            .annotate(total=Count('id'))
            .order_by('-total')
            .first()
        )
        if not malla:
            self.stderr.write(self.style.ERROR('No existe una malla activa ADM-UTA-2026 con materias.'))
            return

        materias_malla = list(
            MateriaMalla.objects
            .filter(malla_id=malla['malla'], activo=True)
            .select_related('malla__carrera__institucion', 'materia', 'nivel')
            .order_by('nivel__numero', 'orden', 'materia__nombre')
        )
        malla_obj = materias_malla[0].malla
        institucion = malla_obj.carrera.institucion

        perfil.institucion = institucion
        perfil.rol = PerfilUsuario.ADMIN
        perfil.usuario_creacion = perfil.usuario_creacion or usuario
        perfil.save()

        periodo, _ = PeriodoAcademico.objects.get_or_create(
            institucion=institucion,
            nombre='Periodo Pruebas SimutaV2',
            defaults={
                'fecha_inicio': timezone.datetime(2026, 1, 1).date(),
                'fecha_fin': timezone.datetime(2026, 12, 31).date(),
                'activo_matricula': True,
                'usuario_creacion': usuario,
            },
        )
        periodo.activo = True
        periodo.activo_matricula = True
        periodo.save()

        PasoSimulacion.objects.all().delete()
        IntentoSimulacion.objects.all().delete()
        Simulacion.objects.all().delete()

        InscripcionMalla.objects.update_or_create(
            estudiante=usuario,
            malla=malla_obj,
            periodo=periodo,
            defaults={
                'estado': InscripcionMalla.ACTIVA,
                'activo': True,
                'usuario_creacion': usuario,
            },
        )

        for materia_malla in materias_malla:
            ProfesorMateria.objects.update_or_create(
                profesor=usuario,
                materia_malla=materia_malla,
                periodo=periodo,
                defaults={'activo': True, 'usuario_creacion': usuario},
            )

        creadas = 0
        for materia_malla in materias_malla:
            materia = materia_malla.materia
            nivel = materia_malla.nivel.numero
            claves_materia = palabras_materia(materia.nombre)
            caso = construir_caso(materia.nombre, nivel)
            titulo = f'Examen SimutaV2 - {materia.nombre}'
            rondas = caso['rondas']

            # Alternate difficulties across subjects
            idx = creadas % 3
            if idx == 0:
                dificultad = Simulacion.DIFICULTAD_BASICA
            elif idx == 1:
                dificultad = Simulacion.DIFICULTAD_MEDIA
            else:
                dificultad = Simulacion.DIFICULTAD_AVANZADA

            riesgo_min = _riesgo_minimo_por_dificultad(dificultad)

            simulacion = Simulacion.objects.create(
                materia_malla=materia_malla,
                profesor=usuario,
                tipo_simulacion=Simulacion.TIPO_CON_IA_DINAMICA,
                titulo=titulo,
                tema=caso['tema'],
                nivel_dificultad=dificultad,
                maximo_decisiones=3,
                tiempo_estimado=25,
                rol_estudiante=f'Analista en {materia.nombre}',
                contexto=caso['contexto'],
                objetivo=caso['objetivo'],
                resultado_aprendizaje=caso['resultado_aprendizaje'],
                situacion_inicial=caso['situacion_inicial'],
                instrucciones_ia=(
                    'Evalua solo contra la rubrica configurada. No inventes puntos. '
                    'La nota la calcula SimutaV2 con conceptos esperados, impactos y restricciones.'
                ),
                parametros={
                    'empresa': caso['empresa'],
                    'rondas': rondas,
                    'materia': materia.nombre,
                    'nivel': nivel,
                    'prompt_generador': PROMPT_GENERADOR_CASOS,
                },
                estado=Simulacion.PUBLICADA,
                fecha_publicacion=timezone.now(),
                activo=True,
                usuario_creacion=usuario,
            )

            indicadores = [
                ('calidad_analisis', 'Calidad del analisis', 50, 'ALTO', True),
                ('viabilidad', 'Viabilidad de la propuesta', 50, 'ALTO', True),
                ('riesgo', 'Riesgo de la decision', 50, 'BAJO', True),
                ('impacto', 'Impacto esperado', 50, 'ALTO', False),
                ('claridad', 'Claridad de justificacion', 50, 'ALTO', False),
            ]
            for codigo, nombre, inicial, direccion, critico in indicadores:
                valor_minimo = riesgo_min if codigo == 'riesgo' else 0
                IndicadorSimulacion.objects.create(
                    simulacion=simulacion,
                    codigo=codigo,
                    nombre=nombre,
                    valor_inicial=max(inicial, valor_minimo),
                    valor_minimo=valor_minimo,
                    valor_maximo=100,
                    direccion_optima=direccion,
                    es_critico=critico,
                    unidad='pts',
                    usuario_creacion=usuario,
                )

            # Restrictions based on difficulty
            restricciones = _restricciones_por_dificultad(dificultad)
            for descripcion, indicador, operador, limite, penalizacion in restricciones:
                RestriccionSimulacion.objects.create(
                    simulacion=simulacion,
                    descripcion=descripcion,
                    codigo_indicador=indicador,
                    operador=operador,
                    valor_limite=limite,
                    penalizacion=penalizacion,
                    usuario_creacion=usuario,
                )

            condiciones = [
                ('Mantener riesgo bajo', 'riesgo', '<=', 35, 5),
                ('Lograr alto impacto esperado', 'impacto', '>=', 75, 5),
            ]
            for descripcion, indicador, operador, objetivo, bonificacion in condiciones:
                CondicionExitoSimulacion.objects.create(
                    simulacion=simulacion,
                    descripcion=descripcion,
                    codigo_indicador=indicador,
                    operador=operador,
                    valor_objetivo=objetivo,
                    bonificacion=bonificacion,
                    usuario_creacion=usuario,
                )

            criterios = [
                ('Analisis inicial', 30),
                ('Decision y alternativas', 30),
                ('Implementacion y control', 25),
                ('Justificacion', 15),
            ]
            for nombre, peso in criterios:
                CriterioEvaluacion.objects.create(
                    simulacion=simulacion,
                    nombre=nombre,
                    descripcion=f'Criterio orientativo de {materia.nombre}: {nombre}.',
                    peso=peso,
                    usuario_creacion=usuario,
                )

            # Decisiones realistas que el estudiante puede tomar (con consecuencias)
            for texto, descripcion, impacto in acciones_del_caso(materia.nombre):
                AccionSugeridaSimulacion.objects.create(
                    simulacion=simulacion,
                    texto=texto,
                    descripcion=descripcion,
                    impacto_base=impacto,
                    usuario_creacion=usuario,
                )

            conceptos = [
                (
                    1, 'Analisis del problema', 35, True,
                    regla_any(['analisis', 'problema', 'causa', 'situacion', 'identificar', 'principal'], claves_materia),
                    {'calidad_analisis': 18, 'riesgo': max(-riesgo_min * 2, -8)},
                    {'riesgo': 12},
                ),
                (
                    1, 'Uso de conceptos de la materia', 30, True,
                    regla_any(['concepto', 'modelo', 'metodo', 'teoria', 'herramienta'], claves_materia),
                    {'calidad_analisis': 12, 'claridad': 8},
                    {'calidad_analisis': -10},
                ),
                (
                    1, 'Indicadores y datos', 20, False,
                    regla_any(['indicador', 'dato', 'medir', 'metrica', 'resultado', 'porcentaje', 'costo', 'tiempo', 'valor']),
                    {'claridad': 10, 'riesgo': -5},
                    {},
                ),
                (
                    1, 'Justificacion inicial', 15, False,
                    regla_any(['porque', 'justifica', 'razon', 'permite', 'evita', 'garantiza', 'beneficio']),
                    {'claridad': 8},
                    {},
                ),
                (
                    2, 'Alternativas comparadas', 30, True,
                    regla_any(['alternativa', 'comparar', 'opcion', 'versus', 'ventaja', 'desventaja', 'riesgo']),
                    {'calidad_analisis': 12, 'riesgo': max(-riesgo_min * 2, -8)},
                    {'riesgo': 15},
                ),
                (
                    2, 'Decision concreta', 30, True,
                    regla_any(['decido', 'recomiendo', 'propongo', 'implementar', 'seleccionar', 'priorizar', 'elegir'], claves_materia),
                    {'viabilidad': 18, 'impacto': 10},
                    {'viabilidad': -12},
                ),
                (
                    2, 'Gestion de riesgos', 20, False,
                    regla_any(['riesgo', 'control', 'mitigar', 'prevenir', 'seguimiento', 'validar']),
                    {'riesgo': -12},
                    {},
                ),
                (
                    2, 'Justificacion de la decision', 20, False,
                    regla_any(['porque', 'justifica', 'razon', 'beneficio', 'impacto', 'resultado']),
                    {'claridad': 12},
                    {},
                ),
                (
                    3, 'Plan de accion', 30, True,
                    regla_any(['plan', 'accion', 'actividad', 'paso', 'cronograma', 'responsable', 'tiempo', 'semana']),
                    {'viabilidad': 15, 'impacto': 8},
                    {'viabilidad': -10},
                ),
                (
                    3, 'Indicadores de seguimiento', 25, True,
                    regla_any(['indicador', 'kpi', 'seguimiento', 'medir', 'control', 'meta', 'resultado']),
                    {'calidad_analisis': 10, 'riesgo': max(-riesgo_min * 2, -8)},
                    {'riesgo': 12},
                ),
                (
                    3, 'Control y correccion', 25, False,
                    regla_any(['control', 'corregir', 'ajustar', 'mejora', 'retroalimentacion', 'auditoria', 'correctiva', 'seguimiento']),
                    {'riesgo': -10, 'viabilidad': 8},
                    {},
                ),
                (
                    3, 'Cierre justificable', 20, False,
                    regla_any(['porque', 'justifica', 'resultado', 'aprendizaje', 'evidencia', 'beneficio']),
                    {'claridad': 10, 'impacto': 8},
                    {},
                ),
            ]
            for ronda, nombre, peso, critico, regla, impacto_ok, impacto_fail in conceptos:
                ConceptoEsperadoRonda.objects.create(
                    simulacion=simulacion,
                    numero_ronda=ronda,
                    nombre=nombre,
                    descripcion=f'{nombre} aplicado a {materia.nombre}.',
                    palabras_clave=json.dumps(regla),
                    peso=peso,
                    impacto_si_cumple=impacto_ok,
                    impacto_si_falta=impacto_fail,
                    retroalimentacion_si_cumple=f'Cumple {nombre}.',
                    retroalimentacion_si_falta=f'Falta {nombre}.',
                    es_critico=critico,
                    usuario_creacion=usuario,
                )

            creadas += 1

        self.stdout.write(self.style.SUCCESS('Reset completo de simulaciones terminado.'))
        self.stdout.write(f'Simulaciones nuevas creadas: {creadas}')
        self.stdout.write(f'Profesor y estudiante de prueba: {usuario.username}')
