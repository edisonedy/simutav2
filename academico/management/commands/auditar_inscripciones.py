# -*- coding: utf-8 -*-
from django.core.management.base import BaseCommand
from django.db import transaction

from academico.models import InscripcionMalla
from core.models import PerfilUsuario


class Command(BaseCommand):
    help = (
        'Detecta inscripciones cuyo estudiante no tiene rol ESTUDIANTE '
        '(datos quedados del comportamiento anterior). '
        'Sin argumentos solo reporta; con --fix las desactiva (activo=False).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Desactiva (activo=False) las inscripciones con estudiante invalido.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        ids_estudiantes = set(
            PerfilUsuario.objects.filter(rol=PerfilUsuario.ESTUDIANTE, activo=True)
            .values_list('usuario_id', flat=True)
        )

        invalidas = (
            InscripcionMalla.objects.filter(activo=True)
            .exclude(estudiante_id__in=ids_estudiantes)
            .select_related('estudiante', 'malla')
        )

        total = invalidas.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS('No hay inscripciones con estudiante invalido.'))
            return

        self.stdout.write(self.style.WARNING(f'Inscripciones con estudiante invalido: {total}'))
        for ins in invalidas:
            perfil = getattr(ins.estudiante, 'perfil', None)
            rol = perfil.get_rol_display() if perfil else 'sin perfil'
            self.stdout.write(f'  #{ins.pk}  {ins.estudiante}  ({rol})  ->  {ins.malla}')

        if options['fix']:
            actualizadas = invalidas.update(activo=False)
            self.stdout.write(self.style.SUCCESS(f'Desactivadas {actualizadas} inscripciones invalidas.'))
        else:
            self.stdout.write(self.style.NOTICE('Modo reporte. Ejecuta con --fix para desactivarlas.'))
