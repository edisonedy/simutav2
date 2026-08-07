from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from academico.forms import ModalidadForm
from academico.models import Modalidad
from core.funciones import errores_formulario, respuesta_error, respuesta_ok
from core.permisos import solo_administrativos


@solo_administrativos
@transaction.atomic
def view(request):
    data = {'title': 'Modalidades'}
    url_retorno = reverse('adm_modalidades')

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add':
            form = ModalidadForm(request.POST)
            if form.is_valid():
                obj = form.save(commit=False)
                obj.usuario_creacion = request.user
                obj.save()
                return respuesta_ok(request, url_retorno)
            return respuesta_error(request, url_retorno, errores_formulario(form), {'errors': form.errors})

        if action == 'edit':
            obj = get_object_or_404(Modalidad, pk=request.POST.get('pk'))
            form = ModalidadForm(request.POST, instance=obj)
            if form.is_valid():
                form.save()
                return respuesta_ok(request, url_retorno)
            return respuesta_error(request, url_retorno, errores_formulario(form), {'errors': form.errors})

        if action == 'delete':
            obj = get_object_or_404(Modalidad, pk=request.POST.get('pk'))
            # Con carreras colgando, borrarla dejaria carreras sin modalidad.
            en_uso = obj.carreras.filter(activo=True).count()
            if en_uso:
                return respuesta_error(
                    request, url_retorno,
                    f'No se puede eliminar: {en_uso} carrera(s) la estan usando.',
                )
            obj.activo = False
            obj.save(update_fields=['activo', 'fecha_modificacion'])
            return respuesta_ok(request, url_retorno, 'Eliminado correctamente')

        return respuesta_error(request, url_retorno, 'Accion no valida')

    action = request.GET.get('action')
    if action == 'add':
        return render(request, 'academico/adm_modalidades/add.html', {'form': ModalidadForm()})

    if action in ('edit', 'delete'):
        obj = get_object_or_404(Modalidad, pk=request.GET.get('pk'))
        if action == 'edit':
            return render(request, 'academico/adm_modalidades/edit.html', {
                'form': ModalidadForm(instance=obj), 'object': obj,
            })
        return render(request, 'academico/adm_modalidades/delete.html', {'object': obj})

    data['list'] = Modalidad.objects.filter(activo=True).annotate(
        total_carreras=Count('carreras', filter=Q(carreras__activo=True)),
    )
    return render(request, 'academico/adm_modalidades/view.html', data)
