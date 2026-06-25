"""Prepara una base de prueba completa para SimutaV2.

Deja tres estudiantes inscritos en todas las mallas activas, asegura casos
publicados para las materias y agrega eventos dinamicos editables por profesor.

Uso:
  python manage.py preparar_demo_completo
"""
from datetime import date

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from academico.models import InscripcionMalla, MateriaMalla, Malla, PeriodoAcademico, ProfesorMateria
from core.models import Institucion, PerfilUsuario
from simulador.models import (
    AccionSugeridaSimulacion,
    EventoSimulacion,
    IndicadorSimulacion,
    RecursoSimulacion,
    Simulacion,
)

User = get_user_model()


ESTUDIANTES_DEMO = [
    ('jnunez18', 'Jenrry', 'Nunez'),
    ('estudiante1', 'Ana', 'Gomez'),
    ('estudiante2', 'Luis', 'Martinez'),
]


def _usuario_base():
    return (
        User.objects.filter(is_superuser=True, is_active=True).first()
        or User.objects.filter(is_staff=True, is_active=True).first()
        or User.objects.filter(is_active=True).first()
    )


def _institucion(usuario):
    institucion = Institucion.objects.first()
    if institucion:
        return institucion
    return Institucion.objects.create(
        nombre='Universidad Tecnica de Ambato',
        siglas='UTA',
        direccion='Ambato, Ecuador',
        usuario_creacion=usuario,
    )


def _crear_usuario_demo(username, first_name, last_name, rol, institucion, creador, staff=False):
    user, _ = User.objects.get_or_create(username=username)
    user.first_name = first_name
    user.last_name = last_name
    user.email = user.email or f'{username}@uta.edu.ec'
    user.is_active = True
    user.is_staff = staff
    if not staff:
        user.is_superuser = False
    user.set_password('12345')
    user.save()
    PerfilUsuario.objects.update_or_create(
        usuario=user,
        defaults={
            'rol': rol,
            'institucion': institucion,
            'usuario_creacion': creador,
        },
    )
    return user


def _primer_indicador_evento(simulacion):
    return (
        IndicadorSimulacion.objects.filter(simulacion=simulacion, activo=True, es_critico=True).order_by('nombre').first()
        or IndicadorSimulacion.objects.filter(simulacion=simulacion, activo=True).order_by('nombre').first()
    )


def _efecto_presion(indicador):
    if indicador.direccion_optima == IndicadorSimulacion.DIRECCION_BAJO:
        return 6
    return -6


def _crear_evento_para_simulacion(simulacion, usuario):
    if EventoSimulacion.objects.filter(simulacion=simulacion, activo=True).exists():
        return False

    titulo = simulacion.titulo.lower()
    codigos = set(simulacion.indicadores.filter(activo=True).values_list('codigo', flat=True))

    if 'datanet' in titulo and 'saturacion_wan' in codigos:
        EventoSimulacion.objects.create(
            simulacion=simulacion,
            nombre='Campana masiva aumenta trafico WAN',
            mensaje='Una campana comercial inesperada dispara el trafico entre sucursales y presiona el enlace WAN.',
            ronda=2,
            codigo_indicador_condicion='saturacion_wan',
            operador_condicion='>=',
            valor_condicion=60,
            efecto={'saturacion_wan': 10},
            prioridad=1,
            usuario_creacion=usuario,
        )
        return True

    if 'techandes' in titulo and 'riesgo_rotacion' in codigos:
        efecto = {'riesgo_rotacion': 12}
        if 'costo_contratacion' in codigos:
            efecto['costo_contratacion'] = 120
        EventoSimulacion.objects.create(
            simulacion=simulacion,
            nombre='Contraoferta del mercado',
            mensaje='Uno de los candidatos recibe una contraoferta externa; ahora la decision debe considerar retencion y costo real.',
            ronda=2,
            codigo_indicador_condicion='riesgo_rotacion',
            operador_condicion='>=',
            valor_condicion=35,
            efecto=efecto,
            prioridad=1,
            usuario_creacion=usuario,
        )
        return True

    indicador = _primer_indicador_evento(simulacion)
    if not indicador:
        return False

    EventoSimulacion.objects.create(
        simulacion=simulacion,
        nombre='Presion operativa inesperada',
        mensaje='Aparece una restriccion externa de la empresa y los indicadores cambian antes de la siguiente ronda.',
        ronda=2 if simulacion.maximo_decisiones >= 2 else 1,
        efecto={indicador.codigo: _efecto_presion(indicador)},
        prioridad=5,
        usuario_creacion=usuario,
    )
    return True


def _crear_recursos_y_costos(simulacion, usuario):
    # Los recursos deben ser propios de cada caso/materia. No se agregan recursos
    # genericos aqui para no contaminar simulaciones de Contabilidad, Sistemas, etc.
    return 0, 0


def _score_malla(malla):
    return (
        Simulacion.objects.filter(materia_malla__malla=malla, activo=True, estado=Simulacion.PUBLICADA).count(),
        InscripcionMalla.objects.filter(malla=malla, activo=True, estado=InscripcionMalla.ACTIVA).count(),
        MateriaMalla.objects.filter(malla=malla, activo=True).count(),
        -malla.pk,
    )


def _consolidar_mallas_duplicadas():
    desactivadas = 0
    codigos = sorted(set(Malla.objects.filter(activo=True).values_list('codigo', flat=True)))
    for codigo in codigos:
        mallas = list(Malla.objects.filter(codigo=codigo, activo=True).order_by('id'))
        if len(mallas) <= 1:
            continue
        mantener = sorted(mallas, key=_score_malla, reverse=True)[0]
        for malla in mallas:
            if malla.pk == mantener.pk:
                continue
            EventoSimulacion.objects.filter(simulacion__materia_malla__malla=malla).update(activo=False)
            Simulacion.objects.filter(materia_malla__malla=malla).update(
                activo=False,
                estado=Simulacion.ARCHIVADA,
            )
            MateriaMalla.objects.filter(malla=malla).update(activo=False)
            InscripcionMalla.objects.filter(malla=malla).update(
                activo=False,
                estado=InscripcionMalla.RETIRADA,
            )
            malla.activo = False
            malla.save(update_fields=['activo'])
            desactivadas += 1
    return desactivadas


def _consolidar_inscripciones_duplicadas(periodo_preferido):
    desactivadas = 0
    pares = (
        InscripcionMalla.objects
        .filter(activo=True, estado=InscripcionMalla.ACTIVA, malla__activo=True)
        .values_list('estudiante_id', 'malla_id')
        .distinct()
    )
    for estudiante_id, malla_id in pares:
        inscripciones = list(
            InscripcionMalla.objects
            .filter(
                estudiante_id=estudiante_id,
                malla_id=malla_id,
                activo=True,
                estado=InscripcionMalla.ACTIVA,
            )
            .order_by('-periodo_id', '-id')
        )
        if len(inscripciones) <= 1:
            continue
        preferidas = [i for i in inscripciones if i.periodo_id == periodo_preferido.pk]
        mantener = preferidas[0] if preferidas else inscripciones[0]
        for inscripcion in inscripciones:
            if inscripcion.pk == mantener.pk:
                continue
            inscripcion.activo = False
            inscripcion.estado = InscripcionMalla.RETIRADA
            inscripcion.save(update_fields=['activo', 'estado'])
            desactivadas += 1
    return desactivadas


class Command(BaseCommand):
    help = 'Carga mallas, simulaciones reales, tres estudiantes inscritos y eventos dinamicos.'

    def handle(self, *args, **options):
        # Cargas idempotentes existentes del proyecto.
        for comando in [
            'cargar_malla_uta',
            'crear_malla_ti_redes',
            'crear_mallas_fisei',
            'poblar_simulaciones_todas',
            'crear_caso_seguridad_redes',
            'crear_caso_talento_django',
        ]:
            self.stdout.write(f'==> {comando}')
            call_command(comando)

        with transaction.atomic():
            creador = _usuario_base()
            institucion = _institucion(creador)
            profesor = _crear_usuario_demo(
                'bpalate', 'Byron', 'Palate', PerfilUsuario.PROFESOR, institucion, creador, staff=True,
            )
            periodo, _ = PeriodoAcademico.objects.get_or_create(
                institucion=institucion,
                nombre='Periodo Pruebas SimutaV2',
                defaults={
                    'fecha_inicio': date(2026, 1, 1),
                    'fecha_fin': date(2026, 12, 31),
                    'activo_matricula': True,
                    'usuario_creacion': creador,
                },
            )
            periodo.activo = True
            periodo.activo_matricula = True
            periodo.save()

            estudiantes = [
                _crear_usuario_demo(username, first, last, PerfilUsuario.ESTUDIANTE, institucion, creador)
                for username, first, last in ESTUDIANTES_DEMO
            ]

            mallas = list(Malla.objects.filter(activo=True).order_by('codigo'))
            materias = list(MateriaMalla.objects.filter(activo=True).select_related('malla'))
            inscripciones = 0
            asignaciones = 0
            for materia_malla in materias:
                _, created = ProfesorMateria.objects.get_or_create(
                    profesor=profesor,
                    materia_malla=materia_malla,
                    periodo=periodo,
                    defaults={'usuario_creacion': creador or profesor},
                )
                asignaciones += int(created)

            for estudiante in estudiantes:
                for malla in mallas:
                    _, created = InscripcionMalla.objects.update_or_create(
                        estudiante=estudiante,
                        malla=malla,
                        periodo=periodo,
                        defaults={
                            'estado': InscripcionMalla.ACTIVA,
                            'activo': True,
                            'usuario_creacion': creador or profesor,
                        },
                    )
                    inscripciones += int(created)

            eventos = 0
            recursos = 0
            costos = 0
            for simulacion in Simulacion.objects.filter(activo=True, estado=Simulacion.PUBLICADA).select_related('materia_malla__materia'):
                eventos += int(_crear_evento_para_simulacion(simulacion, creador or profesor))
                nuevos_recursos, nuevos_costos = _crear_recursos_y_costos(simulacion, creador or profesor)
                recursos += nuevos_recursos
                costos += nuevos_costos
            mallas_duplicadas = _consolidar_mallas_duplicadas()
            inscripciones_duplicadas = _consolidar_inscripciones_duplicadas(periodo)

            mallas = list(Malla.objects.filter(activo=True).order_by('codigo'))
            materias = list(MateriaMalla.objects.filter(activo=True, malla__activo=True).select_related('malla'))

        self.stdout.write('---')
        self.stdout.write(self.style.SUCCESS('Demo completo preparado.'))
        self.stdout.write(f'Mallas activas: {len(mallas)}')
        self.stdout.write(f'Materias activas: {len(materias)}')
        self.stdout.write(f'Estudiantes inscritos en todas las mallas: {", ".join(u.username for u in estudiantes)} / clave 12345')
        self.stdout.write(f'Inscripciones nuevas: {inscripciones}')
        self.stdout.write(f'Asignaciones nuevas a bpalate: {asignaciones}')
        self.stdout.write(f'Eventos dinamicos nuevos: {eventos}')
        self.stdout.write(f'Recursos nuevos: {recursos}')
        self.stdout.write(f'Decisiones con costo nuevo: {costos}')
        self.stdout.write(f'Mallas duplicadas desactivadas: {mallas_duplicadas}')
        self.stdout.write(f'Inscripciones duplicadas desactivadas: {inscripciones_duplicadas}')
