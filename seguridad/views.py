from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from core.models import PerfilUsuario
from seguridad.forms import UsuarioPerfilCreationForm


@login_required
def usuarios(request):
    perfiles = PerfilUsuario.objects.select_related('usuario', 'institucion').all()
    return render(request, 'seguridad/usuarios.html', {'perfiles': perfiles})


@login_required
def crear_usuario(request):
    form = UsuarioPerfilCreationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        usuario = form.save(commit=False)
        usuario.first_name = form.cleaned_data['first_name']
        usuario.last_name = form.cleaned_data['last_name']
        usuario.email = form.cleaned_data['email']
        usuario.save()
        PerfilUsuario.objects.create(
            usuario=usuario,
            rol=form.cleaned_data['rol'],
            institucion=form.cleaned_data['institucion'],
            identificacion=form.cleaned_data['identificacion'],
            telefono=form.cleaned_data['telefono'],
            usuario_creacion=request.user,
        )
        return redirect('seguridad:usuarios')
    return render(request, 'seguridad/crear_usuario.html', {'form': form})
