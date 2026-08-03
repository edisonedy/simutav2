from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.db import transaction
from django.urls import reverse
from core.funciones import errores_formulario, respuesta_error, respuesta_ok
from academico.forms import MateriaForm
from academico.models import Materia


@login_required
@transaction.atomic
def view(request):
    data = {}
    data['title'] = 'Materias'
    if request.method == 'POST':
        action = request.POST.get('action')
        url_retorno = reverse('adm_materias')
        if action == 'add':
            form = MateriaForm(request.POST)
            if form.is_valid():
                obj = form.save(commit=False)
                obj.usuario_creacion = request.user
                obj.save()
                return respuesta_ok(request, url_retorno)
            return respuesta_error(request, url_retorno, errores_formulario(form), {'errors': form.errors})
        elif action == 'edit':
            pk = request.POST.get('pk')
            obj = get_object_or_404(Materia, pk=pk)
            form = MateriaForm(request.POST, instance=obj)
            if form.is_valid():
                form.save()
                return respuesta_ok(request, url_retorno)
            return respuesta_error(request, url_retorno, errores_formulario(form), {'errors': form.errors})
        elif action == 'delete':
            pk = request.POST.get('pk')
            obj = get_object_or_404(Materia, pk=pk)
            obj.activo = False
            obj.save()
            return respuesta_ok(request, url_retorno, 'Eliminado correctamente')
        else:
            return respuesta_error(request, url_retorno, 'Accion no valida')
    else:
        action = request.GET.get('action')
        if action == 'add':
            form = MateriaForm()
            return render(request, 'academico/adm_materias/add.html', {'form': form})
        elif action == 'edit':
            pk = request.GET.get('pk')
            obj = get_object_or_404(Materia, pk=pk)
            form = MateriaForm(instance=obj)
            return render(request, 'academico/adm_materias/edit.html', {'form': form, 'object': obj})
        elif action == 'delete':
            pk = request.GET.get('pk')
            obj = get_object_or_404(Materia, pk=pk)
            return render(request, 'academico/adm_materias/delete.html', {'object': obj})
        else:
            data['list'] = Materia.objects.filter(activo=True).select_related('institucion')
            return render(request, 'academico/adm_materias/view.html', data)
