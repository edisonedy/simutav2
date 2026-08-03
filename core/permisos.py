"""Quien puede hacer que. Definicion unica para todo el sistema."""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db.models import Q

from core.funciones import bad_json, es_ajax
from core.models import PerfilUsuario

ROLES_ADMINISTRATIVOS = (PerfilUsuario.ADMIN, PerfilUsuario.COORDINADOR)
ROLES_DOCENTES = (PerfilUsuario.PROFESOR, PerfilUsuario.ADMIN, PerfilUsuario.COORDINADOR)

MENSAJE_SIN_PERMISO = 'No tienes permiso para administrar esta seccion.'


def _perfil_activo(user):
    if user is None or not user.is_authenticated:
        return None
    perfil = getattr(user, 'perfil', None)
    return perfil if perfil and perfil.activo else None


def es_administrativo(user):
    """Puede administrar el catalogo academico, los usuarios y las instituciones.

    A proposito NO basta con is_staff: los profesores lo tienen y no deben crear
    carreras, inscribir estudiantes ni dar de alta usuarios.
    """
    if user is None or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    perfil = _perfil_activo(user)
    return bool(perfil and perfil.tiene_rol(*ROLES_ADMINISTRATIVOS))


def es_docente(user):
    """Puede usar el panel del profesor. Aqui is_staff SI cuenta."""
    if user is None or not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    perfil = _perfil_activo(user)
    if perfil and perfil.tiene_rol(*ROLES_DOCENTES):
        return True
    from academico.models import ProfesorMateria
    return ProfesorMateria.objects.filter(profesor=user, activo=True).exists()


def usuarios_con_rol(*roles):
    """Usuarios activos que tienen alguno de esos perfiles, sea como principal o
    como adicional. Una persona puede aparecer como estudiante aunque ademas sea
    administradora."""
    return User.objects.filter(
        Q(perfil__rol__in=roles)
        | Q(perfil__roles_adicionales__rol__in=roles, perfil__roles_adicionales__activo=True),
        perfil__activo=True,
        is_active=True,
    ).distinct()


def solo_administrativos(vista):
    """Cierra una vista a administradores. Responde JSON a los modales y 403 al
    resto, para que el usuario vea la pagina de error y no un volcado."""
    @wraps(vista)
    @login_required
    def _envoltura(request, *args, **kwargs):
        if not es_administrativo(request.user):
            if es_ajax(request):
                respuesta = bad_json(mensaje=MENSAJE_SIN_PERMISO)
                respuesta.status_code = 403
                return respuesta
            raise PermissionDenied(MENSAJE_SIN_PERMISO)
        return vista(request, *args, **kwargs)
    return _envoltura
