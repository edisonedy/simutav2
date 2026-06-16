from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from academico.models import Carrera, Malla, Materia, MateriaMalla, NivelMalla
from core.models import Institucion
from simulador.models import (
    DecisionConfigurada,
    EscenarioSimulacion,
    IndicadorSimulacion,
    Simulacion,
)


class Command(BaseCommand):
    help = 'Carga una simulacion sin IA basada en arbol de decisiones para inscripcion a eventos.'

    def handle(self, *args, **options):
        usuario = User.objects.filter(is_superuser=True).first()
        institucion, _ = Institucion.objects.get_or_create(
            nombre='Universidad Tecnica de Ambato',
            defaults={'siglas': 'UTA', 'usuario_creacion': usuario},
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

        simulacion, _ = Simulacion.objects.update_or_create(
            materia_malla=materia_malla,
            titulo='Arbol: inscripcion a eventos academicos',
            defaults={
                'profesor': usuario,
                'tipo_simulacion': Simulacion.TIPO_SIN_IA_ARBOL,
                'tema': 'Inscripciones, cupos y concurrencia',
                'rol_estudiante': 'Desarrollador backend Django',
                'contexto': 'Debes decidir como implementar un modulo de inscripcion a eventos con cupo limitado.',
                'objetivo': 'Elegir decisiones tecnicas que reduzcan errores y mantengan integridad.',
                'resultado_aprendizaje': 'Evalua consecuencias tecnicas de decisiones de backend Django.',
                'maximo_decisiones': 3,
                'estado': Simulacion.PUBLICADA,
                'usuario_creacion': usuario,
            },
        )

        for codigo, nombre in [
            ('calidad_codigo', 'Calidad de codigo'),
            ('seguridad', 'Seguridad'),
            ('mantenibilidad', 'Mantenibilidad'),
            ('riesgo_errores', 'Riesgo de errores'),
        ]:
            IndicadorSimulacion.objects.update_or_create(
                simulacion=simulacion,
                codigo=codigo,
                defaults={
                    'nombre': nombre,
                    'valor_inicial': 50,
                    'valor_minimo': 0,
                    'valor_maximo': 100,
                    'es_critico': codigo in {'seguridad', 'riesgo_errores'},
                    'usuario_creacion': usuario,
                },
            )

        inicio, _ = EscenarioSimulacion.objects.update_or_create(
            simulacion=simulacion,
            titulo='Modelo de datos',
            defaults={
                'situacion': 'Debes elegir como modelar eventos e inscripciones para evitar duplicados y conservar historial.',
                'orden': 1,
                'es_inicial': True,
                'es_final': False,
                'usuario_creacion': usuario,
            },
        )
        cupos, _ = EscenarioSimulacion.objects.update_or_create(
            simulacion=simulacion,
            titulo='Control de cupos',
            defaults={
                'situacion': 'Dos estudiantes intentan inscribirse al ultimo cupo del evento al mismo tiempo.',
                'orden': 2,
                'es_inicial': False,
                'es_final': False,
                'usuario_creacion': usuario,
            },
        )
        final, _ = EscenarioSimulacion.objects.update_or_create(
            simulacion=simulacion,
            titulo='Resultado',
            defaults={
                'situacion': 'El modulo queda listo para revision del administrador.',
                'orden': 3,
                'es_inicial': False,
                'es_final': True,
                'retroalimentacion_final': 'Revisa como tus decisiones afectaron integridad, seguridad y mantenibilidad.',
                'usuario_creacion': usuario,
            },
        )

        DecisionConfigurada.objects.update_or_create(
            escenario=inicio,
            texto='Crear Evento e InscripcionEvento con restriccion unica estudiante-evento',
            defaults={
                'descripcion': 'Separa entidades, conserva historial y evita duplicados desde base de datos.',
                'impacto': {'calidad_codigo': 10, 'mantenibilidad': 8, 'riesgo_errores': -12},
                'puntaje_base': 85,
                'retroalimentacion': 'Buena decision: combina modelo claro e integridad de datos.',
                'siguiente_escenario': cupos,
                'usuario_creacion': usuario,
            },
        )
        DecisionConfigurada.objects.update_or_create(
            escenario=inicio,
            texto='Guardar solo una lista de nombres dentro del evento',
            defaults={
                'descripcion': 'Es rapido, pero dificulta historial, reportes, permisos y validaciones.',
                'impacto': {'calidad_codigo': -10, 'mantenibilidad': -12, 'riesgo_errores': 18},
                'puntaje_base': 30,
                'retroalimentacion': 'Decision debil: mezclar datos reduce control y aumenta errores.',
                'siguiente_escenario': cupos,
                'usuario_creacion': usuario,
            },
        )
        DecisionConfigurada.objects.update_or_create(
            escenario=cupos,
            texto='Usar transaction.atomic y select_for_update antes de descontar cupo',
            defaults={
                'descripcion': 'Bloquea el evento durante la validacion del cupo y evita sobreinscripcion.',
                'impacto': {'seguridad': 12, 'calidad_codigo': 8, 'riesgo_errores': -18},
                'puntaje_base': 92,
                'retroalimentacion': 'Excelente: controla concurrencia e integridad del cupo.',
                'siguiente_escenario': final,
                'usuario_creacion': usuario,
            },
        )
        DecisionConfigurada.objects.update_or_create(
            escenario=cupos,
            texto='Validar el cupo solo en el formulario',
            defaults={
                'descripcion': 'Mejora la experiencia, pero no evita carreras de concurrencia.',
                'impacto': {'seguridad': -6, 'riesgo_errores': 14},
                'puntaje_base': 45,
                'retroalimentacion': 'Incompleto: la validacion de formulario no basta ante concurrencia.',
                'siguiente_escenario': final,
                'usuario_creacion': usuario,
            },
        )

        self.stdout.write(self.style.SUCCESS(f'Simulacion arbol cargada correctamente. ID: {simulacion.id}.'))
