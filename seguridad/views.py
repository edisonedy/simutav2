from django.contrib.auth.models import User
from django.db import transaction
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from core.funciones import errores_formulario, respuesta_error, respuesta_ok
from core.models import PerfilUsuario
from core.permisos import solo_administrativos
from seguridad.forms import AsignarPerfilForm, PerfilUsuarioForm, UsuarioPerfilCreationForm

MENSAJE_AUTOBLOQUEO = 'No puedes quitarte a ti mismo el acceso de administrador.'


def _se_esta_bloqueando(request, perfil, rol_nuevo, activo):
    """Evita que el ultimo administrador se deje fuera del sistema sin querer."""
    if perfil.usuario_id != request.user.pk or request.user.is_superuser:
        return False
    sigue_mandando = activo and rol_nuevo in (PerfilUsuario.ADMIN, PerfilUsuario.COORDINADOR)
    return not sigue_mandando


@solo_administrativos
@transaction.atomic
def usuarios(request):
    url_retorno = reverse('seguridad:usuarios')

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add':
            form = UsuarioPerfilCreationForm(request.POST)
            if form.is_valid():
                form.save(creado_por=request.user)
                return respuesta_ok(request, url_retorno, 'Usuario creado correctamente')
            return respuesta_error(request, url_retorno, errores_formulario(form), {'errors': form.errors})

        elif action == 'edit':
            perfil = get_object_or_404(PerfilUsuario, pk=request.POST.get('pk'))
            form = PerfilUsuarioForm(request.POST, instance=perfil)
            if form.is_valid():
                if _se_esta_bloqueando(request, perfil, form.cleaned_data['rol'], form.cleaned_data['activo']):
                    return respuesta_error(request, url_retorno, MENSAJE_AUTOBLOQUEO)
                form.save()
                return respuesta_ok(request, url_retorno)
            return respuesta_error(request, url_retorno, errores_formulario(form), {'errors': form.errors})

        elif action == 'asignar':
            form = AsignarPerfilForm(request.POST)
            if form.is_valid():
                form.save(creado_por=request.user)
                return respuesta_ok(request, url_retorno, 'Perfil asignado correctamente')
            return respuesta_error(request, url_retorno, errores_formulario(form), {'errors': form.errors})

        elif action == 'delete':
            perfil = get_object_or_404(PerfilUsuario, pk=request.POST.get('pk'))
            if _se_esta_bloqueando(request, perfil, perfil.rol, False):
                return respuesta_error(request, url_retorno, MENSAJE_AUTOBLOQUEO)
            perfil.activo = False
            perfil.save(update_fields=['activo'])
            perfil.usuario.is_active = False
            perfil.usuario.save(update_fields=['is_active'])
            return respuesta_ok(request, url_retorno, 'Usuario desactivado correctamente')

        return respuesta_error(request, url_retorno, 'Accion no valida')

    action = request.GET.get('action')

    if action == 'add':
        return render(request, 'seguridad/usuarios/add.html', {'form': UsuarioPerfilCreationForm()})

    elif action == 'edit':
        perfil = get_object_or_404(PerfilUsuario, pk=request.GET.get('pk'))
        return render(request, 'seguridad/usuarios/edit.html', {
            'form': PerfilUsuarioForm(instance=perfil), 'object': perfil,
        })

    elif action == 'asignar':
        usuario_fijo = None
        if request.GET.get('pk'):
            usuario_fijo = get_object_or_404(User, pk=request.GET.get('pk'), perfil__isnull=True)
        return render(request, 'seguridad/usuarios/asignar.html', {
            'form': AsignarPerfilForm(usuario_fijo=usuario_fijo), 'usuario_fijo': usuario_fijo,
        })

    elif action == 'delete':
        perfil = get_object_or_404(PerfilUsuario, pk=request.GET.get('pk'))
        return render(request, 'seguridad/usuarios/delete.html', {'object': perfil})

    # El listado recorre USUARIOS, no perfiles: asi tambien salen los que no
    # tienen ninguno (el superusuario creado por consola, por ejemplo).
    lista = User.objects.select_related('perfil', 'perfil__institucion').order_by(
        'last_name', 'first_name', 'username',
    )
    return render(request, 'seguridad/usuarios/view.html', {
        'title': 'Usuarios',
        'total': len(lista),
        'grupos': _agrupar_por_perfil(lista),
    })


GRUPOS_PERFIL = [
    (PerfilUsuario.ADMIN, 'Administradores', 'Administran todo el sistema.'),
    (PerfilUsuario.COORDINADOR, 'Coordinadores', 'Administran el catalogo academico.'),
    (PerfilUsuario.PROFESOR, 'Profesores', 'Crean simulaciones y llevan sus cursos.'),
    (PerfilUsuario.ESTUDIANTE, 'Estudiantes', 'Solo entran a sus simulaciones.'),
    (None, 'Sin perfil', 'El sistema no sabe que rol darles: asignaselo para que puedan entrar.'),
]


def _agrupar_por_perfil(usuarios):
    """Una sola pantalla, ordenada por perfil. Los grupos vacios no se muestran."""
    por_rol = {clave: [] for clave, _, _ in GRUPOS_PERFIL}
    for usuario in usuarios:
        perfil = getattr(usuario, 'perfil', None)
        clave = perfil.rol if perfil else None
        por_rol.setdefault(clave, []).append(usuario)
    return [
        {'clave': clave or 'SIN_PERFIL', 'titulo': titulo, 'ayuda': ayuda, 'usuarios': por_rol[clave]}
        for clave, titulo, ayuda in GRUPOS_PERFIL
        if por_rol[clave]
    ]
