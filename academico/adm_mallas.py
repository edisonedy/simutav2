from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.db import transaction
from core.funciones import ok_json, bad_json
from academico.forms import MallaForm, MateriaMallaForm, NivelMallaForm
from academico.models import Malla, NivelMalla, MateriaMalla


@login_required
@transaction.atomic
def view(request):
    data = {}
    data['title'] = 'Mallas'
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add':
            form = MallaForm(request.POST)
            if form.is_valid():
                obj = form.save(commit=False)
                obj.usuario_creacion = request.user
                obj.save()
                return ok_json()
            return bad_json(mensaje='Error en el formulario', data={'errors': form.errors})
        elif action == 'edit':
            pk = request.POST.get('pk')
            obj = get_object_or_404(Malla, pk=pk)
            form = MallaForm(request.POST, instance=obj)
            if form.is_valid():
                form.save()
                return ok_json()
            return bad_json(mensaje='Error en el formulario', data={'errors': form.errors})
        elif action == 'delete':
            pk = request.POST.get('pk')
            obj = get_object_or_404(Malla, pk=pk)
            obj.activo = False
            obj.save()
            return ok_json(mensaje='Eliminado correctamente')
        elif action == 'add_nivel':
            malla = get_object_or_404(Malla, pk=request.POST.get('malla_id'), activo=True)
            form = NivelMallaForm(request.POST)
            if form.is_valid():
                obj = form.save(commit=False)
                obj.malla = malla
                obj.usuario_creacion = request.user
                obj.save()
                return ok_json()
            return bad_json(mensaje='Error en el formulario', data={'errors': form.errors})
        elif action == 'add_materia':
            malla = get_object_or_404(Malla, pk=request.POST.get('malla_id'), activo=True)
            form = MateriaMallaForm(request.POST, malla=malla)
            if form.is_valid():
                obj = form.save(commit=False)
                obj.malla = malla
                obj.usuario_creacion = request.user
                obj.save()
                return ok_json()
            return bad_json(mensaje='Error en el formulario', data={'errors': form.errors})
        else:
            return bad_json(mensaje='Accion no valida')
    else:
        action = request.GET.get('action')
        if action == 'add':
            form = MallaForm()
            return render(request, 'academico/adm_mallas/add.html', {'form': form})
        elif action == 'edit':
            pk = request.GET.get('pk')
            obj = get_object_or_404(Malla, pk=pk)
            form = MallaForm(instance=obj)
            niveles = NivelMalla.objects.filter(malla=obj, activo=True)
            materias_malla = MateriaMalla.objects.filter(malla=obj, activo=True).select_related('nivel', 'materia')
            nivel_form = NivelMallaForm()
            materia_form = MateriaMallaForm(malla=obj)
            return render(request, 'academico/adm_mallas/edit.html', {
                'form': form,
                'object': obj,
                'malla': obj,
                'niveles': niveles,
                'materias_malla': materias_malla,
                'nivel_form': nivel_form,
                'materia_form': materia_form,
            })
        elif action == 'delete':
            pk = request.GET.get('pk')
            obj = get_object_or_404(Malla, pk=pk)
            return render(request, 'academico/adm_mallas/delete.html', {'object': obj})
        else:
            data['list'] = Malla.objects.filter(activo=True).select_related('carrera', 'carrera__institucion').prefetch_related('niveles')
            return render(request, 'academico/adm_mallas/view.html', data)
