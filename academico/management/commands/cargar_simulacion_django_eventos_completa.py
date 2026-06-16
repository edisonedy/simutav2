import json

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from academico.models import (
    Carrera,
    InscripcionMalla,
    Malla,
    Materia,
    MateriaMalla,
    NivelMalla,
    PeriodoAcademico,
    ProfesorMateria,
)
from core.models import Institucion, PerfilUsuario
from simulador.models import (
    ConceptoEsperadoRonda,
    CriterioEvaluacion,
    IndicadorSimulacion,
    RestriccionSimulacion,
    Simulacion,
)


class Command(BaseCommand):
    help = 'Carga la simulacion completa de inscripcion a eventos academicos con Django.'

    def handle(self, *args, **options):
        usuario = User.objects.filter(username='emoyolema').first()
        if usuario is None:
            usuario = User.objects.filter(is_superuser=True).first()
        if usuario is None:
            usuario = User.objects.create_user(
                username='emoyolema',
                password='demo12345',
                first_name='Edison',
            )

        institucion, _ = Institucion.objects.get_or_create(
            nombre='Universidad Tecnica de Ambato',
            defaults={'siglas': 'UTA', 'direccion': 'Ambato, Ecuador', 'usuario_creacion': usuario},
        )
        PerfilUsuario.objects.update_or_create(
            usuario=usuario,
            defaults={
                'rol': PerfilUsuario.ADMIN,
                'institucion': institucion,
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
        InscripcionMalla.objects.get_or_create(
            estudiante=usuario,
            malla=malla,
            periodo=periodo,
            defaults={'usuario_creacion': usuario},
        )

        rondas = [
            {
                'situacion': (
                    'La universidad necesita un modulo de inscripcion a eventos academicos. '
                    'Eres el desarrollador backend Django asignado al proyecto. Define el modelo de datos: '
                    'que entidades crearias, que campos tendrian, como las relacionarias y que restricciones '
                    'de integridad aplicarias para evitar duplicados y mantener trazabilidad.'
                )
            },
            {
                'situacion': (
                    'Los modelos estan creados. Ahora el director pide que solo estudiantes autenticados '
                    'puedan inscribirse, y que el administrador pueda ver la lista completa de inscritos por evento. '
                    'Como disenas las vistas y como controlas los permisos de acceso?'
                )
            },
            {
                'situacion': (
                    'En la primera semana se reportaron dos problemas: un estudiante se inscribio dos veces '
                    'al mismo evento y un evento supero su cupo maximo. Como implementas las validaciones '
                    'para evitar ambos problemas? En que capa las pones y por que?'
                )
            },
            {
                'situacion': (
                    'Durante una prueba de carga con 50 usuarios simultaneos, tres estudiantes tomaron el ultimo '
                    'cupo del mismo evento al mismo tiempo. Como resuelves este problema? Explica el mecanismo '
                    'de Django que usarias y por que es necesario.'
                )
            },
            {
                'situacion': (
                    'Un estudiante cancela su inscripcion. El sistema debe liberar el cupo para que otro pueda '
                    'inscribirse, mantener el historial y no borrar el registro de la base de datos. Como implementas '
                    'la cancelacion? Que campos y que logica usas?'
                )
            },
        ]

        instrucciones = (
            'Eres evaluador tecnico de Django. Evalua contra la rubrica configurada por ronda. '
            'No premies respuestas vagas o genericas. Exige terminos tecnicos reales de Django. '
            'La nota final la calcula SimutaV2 con conceptos, pesos, impactos, restricciones y topes criticos.'
        )

        simulacion, _ = Simulacion.objects.update_or_create(
            materia_malla=materia_malla,
            titulo='Modulo de inscripcion a eventos academicos con Django',
            defaults={
                'profesor': usuario,
                'tipo_simulacion': Simulacion.TIPO_CON_IA_DINAMICA,
                'tema': 'Diseno de modelos, vistas, formularios, validaciones y transacciones',
                'nivel_dificultad': Simulacion.DIFICULTAD_MEDIA,
                'maximo_decisiones': 5,
                'tiempo_estimado': 35,
                'rol_estudiante': 'Desarrollador backend Django',
                'contexto': (
                    'La universidad necesita un modulo para que los estudiantes se inscriban a eventos academicos '
                    'con cupo limitado. El sistema debe evitar duplicados, permitir cancelaciones, mostrar inscritos '
                    'al administrador y controlar errores de concurrencia.'
                ),
                'objetivo': (
                    'Disenar una solucion funcional, segura y mantenible para el modulo de inscripcion a eventos academicos.'
                ),
                'resultado_aprendizaje': (
                    'El estudiante toma decisiones tecnicas sobre modelos, relaciones, validaciones, permisos, '
                    'transacciones y manejo de cupos, justificando por que su solucion es adecuada.'
                ),
                'situacion_inicial': rondas[0]['situacion'],
                'instrucciones_ia': instrucciones,
                'parametros': {'rondas': rondas},
                'estado': Simulacion.PUBLICADA,
                'fecha_publicacion': timezone.now(),
                'usuario_creacion': usuario,
            },
        )

        indicadores = [
            ('calidad_codigo', 'Calidad de codigo', 'ALTO'),
            ('experiencia_usuario', 'Experiencia de usuario', 'ALTO'),
            ('mantenibilidad', 'Mantenibilidad', 'ALTO'),
            ('rendimiento', 'Rendimiento', 'ALTO'),
            ('riesgo_errores', 'Riesgo de errores', 'BAJO'),
            ('seguridad', 'Seguridad', 'ALTO'),
        ]
        for codigo, nombre, direccion in indicadores:
            IndicadorSimulacion.objects.update_or_create(
                simulacion=simulacion,
                codigo=codigo,
                defaults={
                    'nombre': nombre,
                    'valor_inicial': 50,
                    'valor_minimo': 0,
                    'valor_maximo': 100,
                    'direccion_optima': direccion,
                    'es_critico': codigo in ['riesgo_errores', 'seguridad', 'calidad_codigo'],
                    'usuario_creacion': usuario,
                },
            )

        restricciones = [
            ('Usar transacciones cuando exista riesgo de concurrencia.', 'calidad_codigo', '>=', 40, 15),
            ('No borrar registros fisicos; usar estado activo/inactivo.', 'mantenibilidad', '>=', 40, 15),
            ('No permitir inscripciones duplicadas.', 'riesgo_errores', '<=', 80, 20),
            ('No permitir superar el cupo del evento.', 'riesgo_errores', '<=', 75, 20),
            ('Validar permisos de usuario en todas las vistas.', 'seguridad', '>=', 40, 15),
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
            ('Diseno de modelos', 25),
            ('Validaciones de negocio', 25),
            ('Seguridad y permisos', 20),
            ('Calidad de solucion', 20),
            ('Justificacion tecnica', 10),
        ]
        for nombre, peso in criterios:
            CriterioEvaluacion.objects.update_or_create(
                simulacion=simulacion,
                nombre=nombre,
                defaults={
                    'descripcion': f'Criterio orientativo: {nombre}.',
                    'peso': peso,
                    'usuario_creacion': usuario,
                },
            )

        conceptos = [
            # Ronda 1
            (1, 'Diseno de modelos', 30, True,
             ['model', 'modelo', 'foreignkey', 'event', 'inscription', 'entidad', 'relacion', 'campo', 'charfield', 'integerfield', 'datetimefield', 'cupo', 'max_attendees'],
             {'calidad_codigo': 15, 'mantenibilidad': 10}, {'riesgo_errores': 15}),
            (1, 'Restricciones de integridad', 25, True,
             ['unique_together', 'uniqueconstraint', 'constraint', 'duplicado', 'unique', 'integridad', 'no repetir'],
             {'riesgo_errores': -20, 'seguridad': 10}, {'riesgo_errores': 15}),
            (1, 'Soft delete', 20, False,
             ['activo', 'is_active', 'estado', 'soft delete', 'no borrar', 'inactivo', 'cancelado', 'booleanfield'],
             {'mantenibilidad': 15}, {}),
            (1, 'Justificacion tecnica', 25, False,
             ['porque', 'justificacion', 'ventaja', 'evita', 'garantiza', 'permite', 'asegura', 'razon', 'beneficio'],
             {}, {}),
            # Ronda 2
            (2, 'Control de acceso', 30, True,
             ['login_required', 'permission_required', '@login', 'permissiondenied', 'autenticacion', 'permiso', 'acceso', 'rol', 'restrict', 'decorator', 'decorador'],
             {'seguridad': 20, 'riesgo_errores': -15}, {'seguridad': -20}),
            (2, 'Vistas de inscripcion', 30, True,
             ['view', 'createview', 'def inscribir', 'request', 'post', 'get', 'redirect', 'httpresponse', 'vista', 'funcion'],
             {'calidad_codigo': 10, 'experiencia_usuario': 10}, {'riesgo_errores': 10}),
            (2, 'Vista administrador', 20, False,
             ['admin', 'list_display', 'filter', 'annotate', 'inscritos', 'panel', 'administrador', 'modeladmin'],
             {'experiencia_usuario': 15}, {}),
            (2, 'Justificacion tecnica', 20, False,
             ['porque', 'justificacion', 'ventaja', 'evita', 'garantiza', 'permite', 'asegura', 'razon'],
             {}, {}),
            # Ronda 3
            (3, 'Control de cupo', 35, True,
             ['cupo', 'capacidad', 'limite', 'inscritos', 'count()', 'available', 'lleno', 'agotado', 'full', 'disponible', 'verificar'],
             {'riesgo_errores': -20, 'experiencia_usuario': 10}, {'riesgo_errores': 25}),
            (3, 'Evitar duplicados', 30, True,
             ['unique_together', 'uniqueconstraint', 'ya inscrito', 'duplicado', 'exists()', 'filter()', 'unique', 'constraint'],
             {'riesgo_errores': -15, 'calidad_codigo': 10}, {'riesgo_errores': 25}),
            (3, 'Validacion en modelo', 20, False,
             ['clean()', 'save()', 'validationerror', 'raise', 'validar', 'override', 'metodo'],
             {'calidad_codigo': 10, 'mantenibilidad': 5}, {}),
            (3, 'Justificacion tecnica', 15, False,
             ['porque', 'justificacion', 'ventaja', 'evita', 'garantiza', 'permite', 'asegura'],
             {}, {}),
            # Ronda 4
            (4, 'Transaccion atomica', 40, True,
             ['transaction.atomic', 'atomic', 'with transaction', 'transaccion', 'rollback', 'commit', 'acid'],
             {'riesgo_errores': -25, 'seguridad': 15}, {'riesgo_errores': 30}),
            (4, 'Bloqueo de registros', 35, True,
             ['select_for_update', 'bloqueo', 'lock', 'concurrencia', 'simultaneo', 'race condition', 'condicion de carrera', 'for update'],
             {'riesgo_errores': -20, 'rendimiento': -5}, {'riesgo_errores': 30}),
            (4, 'Manejo de errores', 25, False,
             ['try', 'except', 'integrityerror', 'databaseerror', 'error', 'excepcion', 'manejar', 'capturar'],
             {'calidad_codigo': 10, 'riesgo_errores': -10}, {}),
            # Ronda 5
            (5, 'Cancelacion sin borrar', 30, True,
             ['is_active', 'estado', 'cancelado', 'inactivo', 'soft delete', 'no borrar', 'false', 'cambiar estado'],
             {'mantenibilidad': 20, 'riesgo_errores': -10}, {'mantenibilidad': -15}),
            (5, 'Historial y trazabilidad', 30, False,
             ['created_at', 'updated_at', 'datetimefield', 'auto_now', 'historial', 'registro', 'log', 'trazabilidad', 'auditoria', 'fecha'],
             {'mantenibilidad': 15, 'calidad_codigo': 10}, {}),
            (5, 'Liberacion de cupo', 25, True,
             ['cupo', 'liberar', 'disponible', 'cancelar', 'decrementar', 'volver', 'incrementar', 'sumar', 'f()'],
             {'experiencia_usuario': 15, 'riesgo_errores': -10}, {'mantenibilidad': -15}),
            (5, 'Justificacion tecnica', 15, False,
             ['porque', 'justificacion', 'ventaja', 'evita', 'garantiza', 'permite', 'asegura'],
             {}, {}),
        ]

        for ronda, nombre, peso, critico, claves, impacto_cumple, impacto_falta in conceptos:
            ConceptoEsperadoRonda.objects.update_or_create(
                simulacion=simulacion,
                escenario=None,
                numero_ronda=ronda,
                nombre=nombre,
                defaults={
                    'descripcion': f'Ronda {ronda}: {nombre}.',
                    'palabras_clave': json.dumps({'any': claves}),
                    'peso': peso,
                    'impacto_si_cumple': impacto_cumple,
                    'impacto_si_falta': impacto_falta,
                    'retroalimentacion_si_cumple': f'Cumple {nombre}.',
                    'retroalimentacion_si_falta': f'Falta {nombre}.',
                    'es_critico': critico,
                    'activo': True,
                    'usuario_creacion': usuario,
                },
            )

        self.stdout.write(self.style.SUCCESS('Simulacion Django completa cargada y publicada.'))
        self.stdout.write(f'Usuario inscrito: {usuario.username}')
        self.stdout.write(f'Simulacion: {simulacion.titulo} (ID {simulacion.id})')
