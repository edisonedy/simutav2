"""Agrega o quita perfiles a usuarios desde la consola.

Util para el servidor, donde no siempre hay una sesion de administrador a mano
(y para el superusuario creado por consola, que arranca sin perfil).

    python manage.py asignar_rol emoyolema bpalate --agregar ADMIN
    python manage.py asignar_rol jnunez18 --quitar ADMIN
    python manage.py asignar_rol --listar
"""
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import PerfilUsuario

VALIDOS = [clave for clave, _ in PerfilUsuario.ROLES]


class Command(BaseCommand):
    help = 'Agrega o quita perfiles (roles) a uno o varios usuarios.'

    def add_arguments(self, parser):
        parser.add_argument('usuarios', nargs='*', help='username de cada persona')
        parser.add_argument('--agregar', nargs='+', default=[], metavar='ROL')
        parser.add_argument('--quitar', nargs='+', default=[], metavar='ROL')
        parser.add_argument('--listar', action='store_true', help='solo muestra quien tiene que')

    @transaction.atomic
    def handle(self, *args, **opciones):
        if opciones['listar']:
            return self._listar()

        agregar = {r.upper() for r in opciones['agregar']}
        quitar = {r.upper() for r in opciones['quitar']}
        desconocidos = (agregar | quitar) - set(VALIDOS)
        if desconocidos:
            raise CommandError(f'Rol desconocido: {", ".join(sorted(desconocidos))}. Validos: {", ".join(VALIDOS)}')
        if not opciones['usuarios'] or not (agregar or quitar):
            raise CommandError('Indica al menos un usuario y --agregar o --quitar.')

        for username in opciones['usuarios']:
            try:
                usuario = User.objects.get(username=username)
            except User.DoesNotExist:
                self.stderr.write(self.style.ERROR(f'{username}: no existe'))
                continue

            perfil = getattr(usuario, 'perfil', None)
            if perfil is None:
                # Perfil recien creado: arranca vacio, no con el rol por defecto,
                # para que se quede exactamente con lo que se le esta agregando.
                perfil = PerfilUsuario.objects.create(usuario=usuario)
                antes = set()
                self.stdout.write(f'{username}: no tenia perfil, se le creo uno')
            else:
                antes = perfil.roles
            despues = (antes | agregar) - quitar
            if not despues:
                self.stderr.write(self.style.ERROR(
                    f'{username}: se quedaria sin ningun perfil, no se toca'))
                continue

            perfil.fijar_roles(despues)
            perfil.save()
            self.stdout.write(self.style.SUCCESS(
                f'{username}: {" + ".join(sorted(antes))} -> {" + ".join(sorted(perfil.roles))} '
                f'(principal {perfil.rol})'))

    def _listar(self):
        for usuario in User.objects.select_related('perfil').order_by('username'):
            perfil = getattr(usuario, 'perfil', None)
            roles = ' + '.join(sorted(perfil.roles)) if perfil else 'SIN PERFIL'
            self.stdout.write(f'{usuario.username:22} {roles}')
