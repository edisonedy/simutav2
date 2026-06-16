"""Puebla TODAS las materias con una simulacion viva y publicada, de forma
DETERMINISTA (sin necesidad de API). Reutiliza la logica probada del comando
de emoyolema: cada concepto lleva impactos (impacto_si_cumple / impacto_si_falta)
para que las decisiones muevan los indicadores y la empresa se sienta viva.

El profesor NUNCA edita JSON: todo se configura luego con los editores amigables.

Uso:
  python manage.py poblar_simulaciones_todas            # solo materias sin simulacion publicada
  python manage.py poblar_simulaciones_todas --reset    # borra y recrea todas
  python manage.py poblar_simulaciones_todas --malla ADM-UTA-2026
"""
import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from academico.models import MateriaMalla
from academico.management.commands.reset_simulaciones_malla_emoyolema import (
    construir_caso,
    palabras_materia,
    regla_any,
    acciones_del_caso,
    _restricciones_por_dificultad,
    _riesgo_minimo_por_dificultad,
    PROMPT_GENERADOR_CASOS,
)
from simulador.models import (
    AccionSugeridaSimulacion,
    ConceptoEsperadoRonda,
    CondicionExitoSimulacion,
    CriterioEvaluacion,
    IndicadorSimulacion,
    IntentoSimulacion,
    RestriccionSimulacion,
    Simulacion,
)


def _conceptos_estandar(claves_materia, riesgo_min):
    """Los 12 conceptos (4 por ronda) con impactos sobre los indicadores, igual
    que el generador de emoyolema. Devuelve tuplas listas para crear."""
    return [
        (1, 'Analisis del problema', 35, True,
         regla_any(['analisis', 'problema', 'causa', 'situacion', 'identificar', 'principal'], claves_materia),
         {'calidad_analisis': 18, 'riesgo': max(-riesgo_min * 2, -8)}, {'riesgo': 12}),
        (1, 'Uso de conceptos de la materia', 30, True,
         regla_any(['concepto', 'modelo', 'metodo', 'teoria', 'herramienta'], claves_materia),
         {'calidad_analisis': 12, 'claridad': 8}, {'calidad_analisis': -10}),
        (1, 'Indicadores y datos', 20, False,
         regla_any(['indicador', 'dato', 'medir', 'metrica', 'resultado', 'porcentaje', 'costo', 'tiempo', 'valor']),
         {'claridad': 10, 'riesgo': -5}, {}),
        (1, 'Justificacion inicial', 15, False,
         regla_any(['porque', 'justifica', 'razon', 'permite', 'evita', 'garantiza', 'beneficio']),
         {'claridad': 8}, {}),
        (2, 'Alternativas comparadas', 30, True,
         regla_any(['alternativa', 'comparar', 'opcion', 'versus', 'ventaja', 'desventaja', 'riesgo']),
         {'calidad_analisis': 12, 'riesgo': max(-riesgo_min * 2, -8)}, {'riesgo': 15}),
        (2, 'Decision concreta', 30, True,
         regla_any(['decido', 'recomiendo', 'propongo', 'implementar', 'seleccionar', 'priorizar', 'elegir'], claves_materia),
         {'viabilidad': 18, 'impacto': 10}, {'viabilidad': -12}),
        (2, 'Gestion de riesgos', 20, False,
         regla_any(['riesgo', 'control', 'mitigar', 'prevenir', 'seguimiento', 'validar']),
         {'riesgo': -12}, {}),
        (2, 'Justificacion de la decision', 20, False,
         regla_any(['porque', 'justifica', 'razon', 'beneficio', 'impacto', 'resultado']),
         {'claridad': 12}, {}),
        (3, 'Plan de accion', 30, True,
         regla_any(['plan', 'accion', 'actividad', 'paso', 'cronograma', 'responsable', 'tiempo', 'semana']),
         {'viabilidad': 15, 'impacto': 8}, {'viabilidad': -10}),
        (3, 'Indicadores de seguimiento', 25, True,
         regla_any(['indicador', 'kpi', 'seguimiento', 'medir', 'control', 'meta', 'resultado']),
         {'calidad_analisis': 10, 'riesgo': max(-riesgo_min * 2, -8)}, {'riesgo': 12}),
        (3, 'Control y correccion', 25, False,
         regla_any(['control', 'corregir', 'ajustar', 'mejora', 'retroalimentacion', 'auditoria', 'correctiva', 'seguimiento']),
         {'riesgo': -10, 'viabilidad': 8}, {}),
        (3, 'Cierre justificable', 20, False,
         regla_any(['porque', 'justifica', 'resultado', 'aprendizaje', 'evidencia', 'beneficio']),
         {'claridad': 10, 'impacto': 8}, {}),
    ]


def crear_simulacion_viva(materia_malla, profesor, indice=0):
    """Crea una simulacion PUBLICADA y viva para una materia (deterministica)."""
    materia = materia_malla.materia
    nivel = materia_malla.nivel.numero if materia_malla.nivel else 1
    claves_materia = palabras_materia(materia.nombre)
    caso = construir_caso(materia.nombre, nivel)

    dificultad = [Simulacion.DIFICULTAD_BASICA, Simulacion.DIFICULTAD_MEDIA,
                  Simulacion.DIFICULTAD_AVANZADA][indice % 3]
    riesgo_min = _riesgo_minimo_por_dificultad(dificultad)

    simulacion = Simulacion.objects.create(
        materia_malla=materia_malla,
        profesor=profesor,
        tipo_simulacion=Simulacion.TIPO_CON_IA_DINAMICA,
        titulo=f'Simulacion - {materia.nombre}',
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
            'rondas': caso['rondas'],
            'materia': materia.nombre,
            'nivel': nivel,
            'prompt_generador': PROMPT_GENERADOR_CASOS,
        },
        estado=Simulacion.PUBLICADA,
        fecha_publicacion=timezone.now(),
        activo=True,
        usuario_creacion=profesor,
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
            simulacion=simulacion, codigo=codigo, nombre=nombre,
            valor_inicial=max(inicial, valor_minimo), valor_minimo=valor_minimo,
            valor_maximo=100, direccion_optima=direccion, es_critico=critico,
            unidad='pts', usuario_creacion=profesor,
        )

    for descripcion, indicador, operador, limite, penalizacion in _restricciones_por_dificultad(dificultad):
        RestriccionSimulacion.objects.create(
            simulacion=simulacion, descripcion=descripcion, codigo_indicador=indicador,
            operador=operador, valor_limite=limite, penalizacion=penalizacion,
            usuario_creacion=profesor,
        )

    for descripcion, indicador, operador, objetivo, bonificacion in [
        ('Mantener riesgo bajo', 'riesgo', '<=', 35, 5),
        ('Lograr alto impacto esperado', 'impacto', '>=', 75, 5),
    ]:
        CondicionExitoSimulacion.objects.create(
            simulacion=simulacion, descripcion=descripcion, codigo_indicador=indicador,
            operador=operador, valor_objetivo=objetivo, bonificacion=bonificacion,
            usuario_creacion=profesor,
        )

    for nombre, peso in [('Analisis inicial', 30), ('Decision y alternativas', 30),
                         ('Implementacion y control', 25), ('Justificacion', 15)]:
        CriterioEvaluacion.objects.create(
            simulacion=simulacion, nombre=nombre,
            descripcion=f'Criterio orientativo de {materia.nombre}: {nombre}.',
            peso=peso, usuario_creacion=profesor,
        )

    for texto, descripcion, impacto in acciones_del_caso(materia.nombre):
        AccionSugeridaSimulacion.objects.create(
            simulacion=simulacion, texto=texto, descripcion=descripcion,
            impacto_base=impacto, usuario_creacion=profesor,
        )

    for ronda, nombre, peso, critico, regla, impacto_ok, impacto_fail in _conceptos_estandar(claves_materia, riesgo_min):
        ConceptoEsperadoRonda.objects.create(
            simulacion=simulacion, numero_ronda=ronda, nombre=nombre,
            descripcion=f'{nombre} aplicado a {materia.nombre}.',
            palabras_clave=json.dumps(regla), peso=peso,
            impacto_si_cumple=impacto_ok, impacto_si_falta=impacto_fail,
            retroalimentacion_si_cumple=f'Cumple {nombre}.',
            retroalimentacion_si_falta=f'Falta {nombre}.',
            es_critico=critico, usuario_creacion=profesor,
        )

    return simulacion


class Command(BaseCommand):
    help = 'Puebla todas las materias con una simulacion viva (conceptos con impactos), sin API.'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='Borra simulaciones e intentos antes de crear.')
        parser.add_argument('--malla', type=str, default='', help='Limitar a una malla por codigo.')

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        profesor = (User.objects.filter(is_staff=True, is_active=True).first()
                    or User.objects.filter(is_active=True).first())
        if not profesor:
            self.stderr.write(self.style.ERROR('No hay usuarios activos para asignar como profesor.'))
            return

        materias = MateriaMalla.objects.filter(activo=True).select_related('materia', 'nivel', 'malla')
        if options['malla']:
            materias = materias.filter(malla__codigo=options['malla'])
        materias = materias.order_by('malla__codigo', 'nivel__numero', 'orden', 'materia__nombre')

        if options['reset']:
            IntentoSimulacion.objects.all().delete()
            n = Simulacion.objects.count()
            Simulacion.objects.all().delete()
            self.stdout.write(self.style.WARNING(f'Reset: eliminadas {n} simulaciones y sus intentos.'))

        con_sim = set(
            Simulacion.objects.filter(estado=Simulacion.PUBLICADA, activo=True)
            .values_list('materia_malla_id', flat=True)
        )

        creadas = 0
        saltadas = 0
        for idx, mm in enumerate(materias):
            if mm.pk in con_sim:
                saltadas += 1
                continue
            crear_simulacion_viva(mm, profesor, indice=idx)
            creadas += 1
            self.stdout.write(f'  + {mm.materia.nombre}')

        self.stdout.write('---')
        self.stdout.write(self.style.SUCCESS(f'Simulaciones creadas: {creadas} | materias ya con simulacion: {saltadas}'))
