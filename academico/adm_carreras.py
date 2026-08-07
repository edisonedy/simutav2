from django.shortcuts import get_object_or_404, render
from django.db import transaction
from django.urls import reverse
from core.funciones import errores_formulario, respuesta_error, respuesta_ok
from core.permisos import solo_administrativos
from academico.forms import CarreraForm
from academico.models import Carrera


@solo_administrativos
@transaction.atomic
def view(request):
    data = {}
    data['title'] = 'Carreras'
    if request.method == 'POST':
        action = request.POST.get('action')
        url_retorno = reverse('adm_carreras')
        if action == 'add':
            form = CarreraForm(request.POST)
            if form.is_valid():
                obj = form.save(commit=False)
                obj.usuario_creacion = request.user
                obj.save()
                return respuesta_ok(request, url_retorno)
            return respuesta_error(request, url_retorno, errores_formulario(form), {'errors': form.errors})
        elif action == 'edit':
            pk = request.POST.get('pk')
            obj = get_object_or_404(Carrera, pk=pk)
            form = CarreraForm(request.POST, instance=obj)
            if form.is_valid():
                form.save()
                return respuesta_ok(request, url_retorno)
            return respuesta_error(request, url_retorno, errores_formulario(form), {'errors': form.errors})
        elif action == 'delete':
            pk = request.POST.get('pk')
            obj = get_object_or_404(Carrera, pk=pk)
            obj.activo = False
            obj.save()
            return respuesta_ok(request, url_retorno, 'Eliminado correctamente')
        else:
            return respuesta_error(request, url_retorno, 'Accion no valida')
    else:
        action = request.GET.get('action')
        if action == 'add':
            form = CarreraForm()
            return render(request, 'academico/adm_carreras/add.html', {'form': form})
        elif action == 'edit':
            pk = request.GET.get('pk')
            obj = get_object_or_404(Carrera, pk=pk)
            form = CarreraForm(instance=obj)
            return render(request, 'academico/adm_carreras/edit.html', {'form': form, 'object': obj})
        elif action == 'delete':
            pk = request.GET.get('pk')
            obj = get_object_or_404(Carrera, pk=pk)
            return render(request, 'academico/adm_carreras/delete.html', {'object': obj})
        else:
            data['list'] = Carrera.objects.filter(activo=True)
            return render(request, 'academico/adm_carreras/view.html', data)
