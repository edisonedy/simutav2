import os, sys, django
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.contrib.auth.models import User
from django.db import transaction
from core.models import Institucion, PerfilUsuario

try:
    institucion = Institucion.objects.first()
except:
    institucion = None

@transaction.atomic
def crear_usuarios():
    usuarios = [
        {
            "username": "emoyolema",
            "password": "edison",
            "email": "emoyolema@uta.edu.ec",
            "first_name": "Edison",
            "last_name": "Moyolema",
            "is_staff": True,
            "is_superuser": True,
            "rol": PerfilUsuario.ADMIN,
            "identificacion": "1800000001",
            "telefono": "0999999991",
        },
        {
            "username": "profesor1",
            "password": "edison",
            "email": "profesor1@uta.edu.ec",
            "first_name": "Carlos",
            "last_name": "Perez",
            "is_staff": True,
            "is_superuser": False,
            "rol": PerfilUsuario.PROFESOR,
            "identificacion": "1800000002",
            "telefono": "0999999992",
        },
        {
            "username": "profesor2",
            "password": "edison",
            "email": "profesor2@uta.edu.ec",
            "first_name": "Maria",
            "last_name": "Lopez",
            "is_staff": True,
            "is_superuser": False,
            "rol": PerfilUsuario.PROFESOR,
            "identificacion": "1800000003",
            "telefono": "0999999993",
        },
        {
            "username": "estudiante1",
            "password": "edison",
            "email": "estudiante1@uta.edu.ec",
            "first_name": "Ana",
            "last_name": "Gomez",
            "is_staff": False,
            "is_superuser": False,
            "rol": PerfilUsuario.ESTUDIANTE,
            "identificacion": "1800000004",
            "telefono": "0999999994",
        },
        {
            "username": "estudiante2",
            "password": "edison",
            "email": "estudiante2@uta.edu.ec",
            "first_name": "Luis",
            "last_name": "Martinez",
            "is_staff": False,
            "is_superuser": False,
            "rol": PerfilUsuario.ESTUDIANTE,
            "identificacion": "1800000005",
            "telefono": "0999999995",
        },
    ]

    for data in usuarios:
        user, created = User.objects.get_or_create(
            username=data["username"],
            defaults={
                "email": data["email"],
                "first_name": data["first_name"],
                "last_name": data["last_name"],
                "is_staff": data["is_staff"],
                "is_superuser": data["is_superuser"],
            },
        )
        user.set_password(data["password"])
        user.save()

        PerfilUsuario.objects.get_or_create(
            usuario=user,
            defaults={
                "institucion": institucion,
                "rol": data["rol"],
                "identificacion": data["identificacion"],
                "telefono": data["telefono"],
            },
        )

        status = "creado" if created else "actualizado"
        print(f"Usuario '{user.username}' ({data['rol']}) {status}")

crear_usuarios()
