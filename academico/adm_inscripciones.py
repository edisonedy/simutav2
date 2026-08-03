from django.shortcuts import get_object_or_404, render
from django.db import transaction
from django.urls import reverse
from core.funciones import errores_formulario, respuesta_error, respuesta_ok
from core.permisos import solo_administrativos
from academico.forms import InscripcionMallaForm
from academico.models import InscripcionMalla


@solo_administrativos
@transaction.atomic
def view(request):
    data = {}
    data['title'] = 'Inscripciones'
    if request.method == 'POST':
        action = request.POST.get('action')
        url_retorno = reverse('adm_inscripciones')
        if action == 'add':
            form = InscripcionMallaForm(request.POST)
            if form.is_valid():
                obj = form.save(commit=False)
                obj.usuario_creacion = request.user
                obj.save()
                return respuesta_ok(request, url_retorno)
            return respuesta_error(request, url_retorno, errores_formulario(form), {'errors': form.errors})
        elif action == 'edit':
            pk = request.POST.get('pk')
            obj = get_object_or_404(InscripcionMalla, pk=pk)
            form = InscripcionMallaForm(request.POST, instance=obj)
            if form.is_valid():
                form.save()
                return respuesta_ok(request, url_retorno)
            return respuesta_error(request, url_retorno, errores_formulario(form), {'errors': form.errors})
        elif action == 'delete':
            pk = request.POST.get('pk')
            obj = get_object_or_404(InscripcionMalla, pk=pk)
            obj.activo = False
            obj.save()
            return respuesta_ok(request, url_retorno, 'Eliminado correctamente')
        else:
            return respuesta_error(request, url_retorno, 'Accion no valida')
    else:
        action = request.GET.get('action')
        if action == 'add':
            form = InscripcionMallaForm()
            return render(request, 'academico/adm_inscripciones/add.html', {'form': form})
        elif action == 'edit':
            pk = request.GET.get('pk')
            obj = get_object_or_404(InscripcionMalla, pk=pk)
            form = InscripcionMallaForm(instance=obj)
            return render(request, 'academico/adm_inscripciones/edit.html', {'form': form, 'object': obj})
        elif action == 'delete':
            pk = request.GET.get('pk')
            obj = get_object_or_404(InscripcionMalla, pk=pk)
            return render(request, 'academico/adm_inscripciones/delete.html', {'object': obj})
        else:
            data['list'] = InscripcionMalla.objects.filter(activo=True).select_related('estudiante', 'malla', 'periodo')
            return render(request, 'academico/adm_inscripciones/view.html', data)
