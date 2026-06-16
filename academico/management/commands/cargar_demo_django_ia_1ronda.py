from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from academico.models import (
    Carrera,
    Malla,
    Materia,
    MateriaMalla,
    NivelMalla,
    PeriodoAcademico,
    ProfesorMateria,
)
from core.models import Institucion
from simulador.models import (
    ConceptoEsperadoRonda,
    CriterioEvaluacion,
    IndicadorSimulacion,
    RestriccionSimulacion,
    Simulacion,
)


class Command(BaseCommand):
    help = 'Carga una simulacion Django con IA dinamica de una sola ronda.'

    def handle(self, *args, **options):
        usuario = User.objects.filter(username='emoyolema').first() or User.objects.filter(is_superuser=True).first()

        institucion, _ = Institucion.objects.get_or_create(
            nombre='Universidad Tecnica de Ambato',
            defaults={'siglas': 'UTA', 'direccion': 'Ambato, Ecuador', 'usuario_creacion': usuario},
        )
        carrera, _ = Carrera.objects.get_or_create(
            institucion=institucion,
            codigo='SOFT-DEMO',
            defaults={
                'nombre': 'Ingenieria de Software',
                'titulo_otorga': 'Ingeniero/a de Software',
                'modalidad': 'Presencial',
                'duracion_periodos': 8,
                'usuario_creacion': usuario,
            },
        )
        malla, _ = Malla.objects.get_or_create(
            carrera=carrera,
            codigo='SOFT-DJANGO-2026',
            defaults={'nombre': 'Malla Demo Django 2026', 'vigente': True, 'usuario_creacion': usuario},
        )
        nivel, _ = NivelMalla.objects.get_or_create(
            malla=malla,
            numero=5,
            defaults={'nombre': '5 Periodo', 'usuario_creacion': usuario},
        )
        materia, _ = Materia.objects.get_or_create(
            institucion=institucion,
            codigo='WEB-DJANGO',
            defaults={
                'nombre': 'Programacion Web con Django',
                'descripcion': 'Modelos, vistas, formularios, validaciones y transacciones en Django.',
                'creditos': 4,
                'horas': 64,
                'usuario_creacion': usuario,
            },
        )
        materia_malla, _ = MateriaMalla.objects.get_or_create(
            malla=malla,
            materia=materia,
            defaults={'nivel': nivel, 'orden': 1, 'obligatoria': True, 'usuario_creacion': usuario},
        )
        periodo, _ = PeriodoAcademico.objects.get_or_create(
            institucion=institucion,
            nombre='Demo 2026',
            defaults={
                'fecha_inicio': timezone.datetime(2026, 1, 1).date(),
                'fecha_fin': timezone.datetime(2026, 12, 31).date(),
                'activo_matricula': True,
                'usuario_creacion': usuario,
            },
        )
        ProfesorMateria.objects.get_or_create(
            profesor=usuario,
            materia_malla=materia_malla,
            periodo=periodo,
            defaults={'usuario_creacion': usuario},
        )

        simulacion, _ = Simulacion.objects.update_or_create(
            materia_malla=materia_malla,
            titulo='Ronda unica IA: validar inscripcion a evento Django',
            defaults={
                'profesor': usuario,
                'tipo_simulacion': Simulacion.TIPO_CON_IA_DINAMICA,
                'tema': 'Validaciones y transacciones en inscripciones Django',
                'nivel_dificultad': Simulacion.DIFICULTAD_BASICA,
                'maximo_decisiones': 1,
                'tiempo_estimado': 10,
                'rol_estudiante': 'Desarrollador backend Django',
                'contexto': (
                    'La universidad necesita evitar que un estudiante se inscriba dos veces '
                    'al mismo evento y que se supere el cupo disponible.'
                ),
                'objetivo': (
                    'Proponer una decision tecnica concreta para controlar duplicados y cupos '
                    'en un modulo Django.'
                ),
                'resultado_aprendizaje': (
                    'El estudiante justifica el uso de modelos, restricciones, validaciones '
                    'y transacciones para mantener integridad de datos.'
                ),
                'situacion_inicial': (
                    'Ronda unica: Debes decidir como impedir inscripciones duplicadas y evitar '
                    'que dos estudiantes tomen el ultimo cupo al mismo tiempo.'
                ),
                'instrucciones_ia': (
                    'Evaluar solo una decision. Premiar respuestas que mencionen unique_together, '
                    'constraints, validaciones, transaction.atomic o select_for_update. No premiar '
                    'respuestas vagas o sin justificacion tecnica.'
                ),
                'estado': Simulacion.PUBLICADA,
                'fecha_publicacion': timezone.now(),
                'usuario_creacion': usuario,
            },
        )

        indicadores = [
            ('calidad_codigo', 'Calidad de codigo', 50, 0, 100, True),
            ('seguridad', 'Seguridad', 50, 0, 100, True),
            ('rendimiento', 'Rendimiento', 50, 0, 100, False),
            ('mantenibilidad', 'Mantenibilidad', 50, 0, 100, False),
            ('riesgo_errores', 'Riesgo de errores', 50, 0, 100, True),
        ]
        for codigo, nombre, inicial, minimo, maximo, critico in indicadores:
            IndicadorSimulacion.objects.update_or_create(
                simulacion=simulacion,
                codigo=codigo,
                defaults={
                    'nombre': nombre,
                    'valor_inicial': inicial,
                    'valor_minimo': minimo,
                    'valor_maximo': maximo,
                    'es_critico': critico,
                    'usuario_creacion': usuario,
                },
            )

        restricciones = [
            ('No superar el cupo.', 'riesgo_errores', '<=', 75, 8),
            ('Mantener seguridad minima.', 'seguridad', '>=', 40, 8),
            ('Mantener calidad minima.', 'calidad_codigo', '>=', 40, 8),
        ]
        for descripcion, indicador, operador, limite, penalizacion in restricciones:
            RestriccionSimulacion.objects.update_or_create(
                simulacion=simulacion,
                descripcion=descripcion,
                defaults={
                    'codigo_indicador': indicador,
                    'operador': operador,
                    'valor_limite': limite,
                    'penalizacion': penalizacion,
                    'usuario_creacion': usuario,
                },
            )

        criterios = [
            ('Integridad de datos', 'Evita duplicados y sobrecupos con reglas robustas.', 35),
            ('Manejo de concurrencia', 'Considera transaction.atomic o select_for_update.', 35),
            ('Justificacion tecnica', 'Explica por que la solucion evita el problema.', 30),
        ]
        for nombre, descripcion, peso in criterios:
            CriterioEvaluacion.objects.update_or_create(
                simulacion=simulacion,
                nombre=nombre,
                defaults={'descripcion': descripcion, 'peso': peso, 'usuario_creacion': usuario},
            )

        conceptos = [
            {
                'nombre': 'Evitar duplicados',
                'descripcion': 'Define una regla para impedir que un estudiante se inscriba dos veces al mismo evento.',
                'palabras_clave': 'unique, unique_together, uniqueconstraint, duplicado, único, no repetir, constraint',
                'peso': 30,
                'impacto': {'seguridad': 6, 'calidad_codigo': 4, 'riesgo_errores': -8},
                'cumple': 'Identificas la necesidad de evitar inscripciones duplicadas.',
                'falta': 'Falta definir cómo impedir inscripciones duplicadas.',
                'critico': False,
            },
            {
                'nombre': 'Control de cupo',
                'descripcion': 'Controla que el evento no supere su capacidad disponible.',
                'palabras_clave': 'cupo, límite, disponibilidad, inscritos, capacidad',
                'peso': 25,
                'impacto': {'seguridad': 4, 'riesgo_errores': -6},
                'cumple': 'Consideras el límite de cupos del evento.',
                'falta': 'Falta controlar que no se supere el cupo disponible.',
                'critico': False,
            },
            {
                'nombre': 'Concurrencia',
                'descripcion': 'Evita que dos usuarios tomen el último cupo al mismo tiempo.',
                'palabras_clave': 'transaction.atomic, atomic, select_for_update, concurrencia, bloqueo, transacción, simultáneo',
                'peso': 35,
                'impacto': {'seguridad': 10, 'rendimiento': 3, 'riesgo_errores': -15},
                'cumple': 'Consideras concurrencia y consistencia cuando dos usuarios actúan al mismo tiempo.',
                'falta': 'Falta controlar concurrencia para evitar que dos estudiantes tomen el último cupo.',
                'critico': True,
            },
            {
                'nombre': 'Justificación técnica',
                'descripcion': 'Explica el razonamiento técnico de la decisión.',
                'palabras_clave': 'integridad, consistencia, base de datos, validación, validaria, validaría, regla de negocio',
                'peso': 10,
                'impacto': {'calidad_codigo': 2},
                'cumple': 'Tu justificación explica la razón técnica de la decisión.',
                'falta': 'Falta explicar mejor el razonamiento técnico.',
                'critico': False,
            },
        ]
        for concepto in conceptos:
            ConceptoEsperadoRonda.objects.update_or_create(
                simulacion=simulacion,
                escenario=None,
                numero_ronda=1,
                nombre=concepto['nombre'],
                defaults={
                    'descripcion': concepto['descripcion'],
                    'palabras_clave': concepto['palabras_clave'],
                    'peso': concepto['peso'],
                    'impacto_si_cumple': concepto['impacto'],
                    'retroalimentacion_si_cumple': concepto['cumple'],
                    'retroalimentacion_si_falta': concepto['falta'],
                    'es_critico': concepto['critico'],
                    'usuario_creacion': usuario,
                },
            )

        self.stdout.write(
            self.style.SUCCESS(
                f'Simulacion IA de una ronda cargada. ID: {simulacion.id}. Profesor: {usuario.username}.'
            )
        )
