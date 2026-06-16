from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from academico.models import Carrera, Malla, Materia, MateriaMalla, NivelMalla, PeriodoAcademico
from core.models import Institucion
from simulador.models import (
    AccionSugeridaSimulacion,
    CriterioEvaluacion,
    IndicadorSimulacion,
    RestriccionSimulacion,
    Simulacion,
)


class Command(BaseCommand):
    help = 'Carga una simulacion demo realista para Programacion Web con Django.'

    def handle(self, *args, **options):
        usuario = User.objects.filter(is_superuser=True).first()

        institucion, _ = Institucion.objects.get_or_create(
            nombre='Universidad Tecnica de Ambato',
            defaults={
                'siglas': 'UTA',
                'direccion': 'Ambato, Ecuador',
                'usuario_creacion': usuario,
            },
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
            defaults={
                'nombre': 'Malla Demo Django 2026',
                'vigente': True,
                'usuario_creacion': usuario,
            },
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
            defaults={
                'nivel': nivel,
                'orden': 1,
                'obligatoria': True,
                'usuario_creacion': usuario,
            },
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

        simulacion, _ = Simulacion.objects.update_or_create(
            materia_malla=materia_malla,
            titulo='Inscripcion a eventos academicos con Django',
            defaults={
                'profesor': usuario,
                'tema': 'Diseño de modelos, vistas, formularios, validaciones y transacciones',
                'nivel_dificultad': Simulacion.DIFICULTAD_MEDIA,
                'maximo_decisiones': 5,
                'tiempo_estimado': 35,
                'rol_estudiante': 'Desarrollador backend Django',
                'contexto': (
                    'La universidad necesita un modulo para que los estudiantes se inscriban '
                    'a eventos academicos con cupo limitado. El sistema debe evitar duplicados, '
                    'permitir cancelaciones, mostrar inscritos al administrador y controlar '
                    'errores de concurrencia.'
                ),
                'objetivo': (
                    'Diseñar una solucion funcional, segura y mantenible para el modulo de '
                    'inscripcion a eventos academicos.'
                ),
                'resultado_aprendizaje': (
                    'El estudiante toma decisiones tecnicas sobre modelos, relaciones, '
                    'validaciones, permisos, transacciones y manejo de cupos, justificando '
                    'por que su solucion es adecuada.'
                ),
                'situacion_inicial': (
                    'Ronda 1: Define el modelo de datos para eventos academicos e inscripciones. '
                    'Explica que entidades, relaciones y restricciones usarias.'
                ),
                'instrucciones_ia': (
                    'Evaluar decisiones tecnicas de Django. No premiar respuestas vagas. '
                    'Valorar modelos, validaciones, permisos, transacciones y trazabilidad.'
                ),
                'parametros': {
                    'rondas': [
                        'Diseño del modelo de datos',
                        'Validación de inscripción duplicada',
                        'Control de cupos',
                        'Permisos y seguridad',
                        'Cancelación de inscripción y trazabilidad',
                    ]
                },
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
            ('experiencia_usuario', 'Experiencia de usuario', 50, 0, 100, False),
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
            ('No permitir inscripciones duplicadas.', 'riesgo_errores', '<=', 80, 8),
            ('No permitir superar el cupo del evento.', 'riesgo_errores', '<=', 75, 8),
            ('Validar permisos de usuario.', 'seguridad', '>=', 40, 8),
            ('No borrar registros fisicos; usar estado activo/inactivo.', 'mantenibilidad', '>=', 40, 5),
            ('Usar transacciones cuando exista riesgo de concurrencia.', 'calidad_codigo', '>=', 40, 8),
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
            ('Diseño de modelos', 'Define entidades, relaciones y restricciones de integridad.', 25),
            ('Validaciones de negocio', 'Evita duplicados, controla cupos y valida reglas en aplicación y base de datos.', 25),
            ('Seguridad y permisos', 'Distingue acciones permitidas por estudiante y administrador.', 20),
            ('Calidad de solución', 'Propone una solución mantenible, clara y segura.', 20),
            ('Justificación técnica', 'Argumenta por qué la decisión resuelve el problema.', 10),
        ]
        for nombre, descripcion, peso in criterios:
            CriterioEvaluacion.objects.update_or_create(
                simulacion=simulacion,
                nombre=nombre,
                defaults={
                    'descripcion': descripcion,
                    'peso': peso,
                    'usuario_creacion': usuario,
                },
            )

        acciones = [
            ('Crear modelos Evento e InscripcionEvento', 'Separar evento e inscripción para historial y reportes.', {'calidad_codigo': 8, 'mantenibilidad': 6, 'riesgo_errores': -5}),
            ('Agregar unique_together estudiante-evento', 'Evita inscripciones duplicadas a nivel de base de datos.', {'seguridad': 6, 'calidad_codigo': 6, 'riesgo_errores': -10}),
            ('Usar transaction.atomic y select_for_update', 'Controla concurrencia cuando se disputa el último cupo.', {'seguridad': 8, 'rendimiento': 4, 'riesgo_errores': -15}),
        ]
        for texto, descripcion, impacto in acciones:
            AccionSugeridaSimulacion.objects.update_or_create(
                simulacion=simulacion,
                texto=texto,
                defaults={
                    'descripcion': descripcion,
                    'impacto_base': impacto,
                    'usuario_creacion': usuario,
                },
            )

        self.stdout.write(
            self.style.SUCCESS(
                f'Simulacion Django cargada correctamente. ID: {simulacion.id}. Periodo: {periodo.nombre}.'
            )
        )
