from django.shortcuts import get_object_or_404, render
from django.db import transaction
from django.db.models import Prefetch
from django.urls import reverse
from core.funciones import (
    errores_formulario,
    respuesta_error,
    respuesta_ok,
)
from core.permisos import solo_administrativos
from academico.forms import (
    MallaForm,
    MateriaMallaForm,
    MateriaMallaPredecesoraForm,
    NivelMallaForm,
)
from academico.models import (
    Malla,
    MateriaMalla,
    MateriaMallaPredecesora,
    NivelMalla,
)
from simulador.models import ActividadMateria


def _url_estructura(malla_id):
    return f"{reverse('adm_mallas')}?action=estructura&pk={malla_id}"


def _listado():
    """Catalogo de mallas, sin mezclar periodos ni materias operativas."""
    return Malla.objects.filter(activo=True).select_related(
        'carrera',
    )


def _estructura(malla, materia_ids=None):
    """Solo las materias realmente agregadas a la malla, ordenadas por nivel."""
    requisitos = MateriaMallaPredecesora.objects.filter(activo=True).select_related(
        'predecesora__materia', 'predecesora__nivel',
    )
    materias = MateriaMalla.objects.filter(malla=malla, activo=True).select_related(
        'nivel', 'materia',
    ).prefetch_related(
        Prefetch('predecesoras', queryset=requisitos),
        Prefetch(
            'actividades',
            queryset=ActividadMateria.objects.filter(
                activo=True, tipo=ActividadMateria.GUIA_APE,
            ).order_by('orden', 'titulo'),
            to_attr='guias_ape',
        ),
    )
    if materia_ids is not None:
        materias = materias.filter(pk__in=materia_ids)
    por_nivel = {}
    for materia_malla in materias:
        por_nivel.setdefault(materia_malla.nivel_id, []).append(materia_malla)
    niveles = NivelMalla.objects.filter(malla=malla, activo=True)
    filas = []
    for nivel in niveles:
        filas.append({
            'nivel': nivel,
            'materias': por_nivel.pop(nivel.id, []),
        })
    # Materias colgadas de un nivel dado de baja: se muestran igual para que no
    # queden invisibles en la malla.
    for materias_huerfanas in por_nivel.values():
        filas.append({'nivel': materias_huerfanas[0].nivel, 'materias': materias_huerfanas})
    return filas


@solo_administrativos
@transaction.atomic
def view(request):
    data = {}
    data['title'] = 'Mallas'
    if request.method == 'POST':
        action = request.POST.get('action')
        url_retorno = reverse('adm_mallas')
        if action == 'add':
            form = MallaForm(request.POST)
            if form.is_valid():
                obj = form.save(commit=False)
                obj.usuario_creacion = request.user
                obj.save()
                return respuesta_ok(request, url_retorno)
            return respuesta_error(request, url_retorno, errores_formulario(form), {'errors': form.errors})
        elif action == 'edit':
            pk = request.POST.get('pk')
            obj = get_object_or_404(Malla, pk=pk)
            form = MallaForm(request.POST, instance=obj)
            if form.is_valid():
                form.save()
                return respuesta_ok(request, url_retorno)
            return respuesta_error(request, url_retorno, errores_formulario(form), {'errors': form.errors})
        elif action == 'delete':
            pk = request.POST.get('pk')
            obj = get_object_or_404(Malla, pk=pk)
            obj.activo = False
            obj.save()
            return respuesta_ok(request, url_retorno, 'Eliminado correctamente')
        elif action == 'add_nivel':
            malla = get_object_or_404(Malla, pk=request.POST.get('malla_id'), activo=True)
            url_retorno = (
                f"{reverse('adm_materias')}?action=malla&pk={malla.pk}"
                if request.POST.get('retorno_materias')
                else _url_estructura(malla.pk)
            )
            form = NivelMallaForm(request.POST)
            if form.is_valid():
                obj = form.save(commit=False)
                obj.malla = malla
                obj.usuario_creacion = request.user
                obj.save()
                return respuesta_ok(request, url_retorno)
            return respuesta_error(request, url_retorno, errores_formulario(form), {'errors': form.errors})
        elif action == 'add_materia':
            malla = get_object_or_404(Malla, pk=request.POST.get('malla_id'), activo=True)
            url_retorno = _url_estructura(malla.pk)
            form = MateriaMallaForm(request.POST, malla=malla)
            if form.is_valid():
                obj = form.save(commit=False)
                obj.malla = malla
                obj.usuario_creacion = request.user
                obj.save()
                return respuesta_ok(request, url_retorno)
            return respuesta_error(request, url_retorno, errores_formulario(form), {'errors': form.errors})
        elif action == 'del_materia':
            materia_malla = get_object_or_404(MateriaMalla, pk=request.POST.get('pk'))
            url_retorno = _url_estructura(materia_malla.malla_id)
            materia_malla.activo = False
            materia_malla.save()
            return respuesta_ok(request, url_retorno, 'Materia retirada de la malla')
        elif action == 'add_predecesora':
            materia_malla = get_object_or_404(
                MateriaMalla, pk=request.POST.get('materia_malla_id'), activo=True,
            )
            url_retorno = _url_estructura(materia_malla.malla_id)
            form = MateriaMallaPredecesoraForm(request.POST, materia_malla=materia_malla)
            if form.is_valid():
                obj = form.save(commit=False)
                obj.materia_malla = materia_malla
                obj.usuario_creacion = request.user
                obj.save()
                return respuesta_ok(request, url_retorno, 'Requisito agregado')
            return respuesta_error(request, url_retorno, errores_formulario(form), {'errors': form.errors})
        elif action == 'del_predecesora':
            requisito = get_object_or_404(MateriaMallaPredecesora, pk=request.POST.get('pk'))
            url_retorno = _url_estructura(requisito.materia_malla.malla_id)
            requisito.activo = False
            requisito.save()
            return respuesta_ok(request, url_retorno, 'Requisito eliminado')
        else:
            return respuesta_error(request, url_retorno, 'Accion no valida')
    else:
        action = request.GET.get('action')
        if action == 'add':
            form = MallaForm()
            return render(request, 'academico/adm_mallas/add.html', {'form': form})
        elif action == 'edit':
            pk = request.GET.get('pk')
            obj = get_object_or_404(Malla, pk=pk)
            form = MallaForm(instance=obj)
            return render(request, 'academico/adm_mallas/edit.html', {
                'form': form,
                'object': obj,
                'malla': obj,
            })
        elif action == 'estructura':
            malla = get_object_or_404(
                Malla.objects.select_related('carrera'),
                pk=request.GET.get('pk'), activo=True,
            )
            return render(request, 'academico/adm_mallas/estructura.html', {
                'title': f'Asignaturas de {malla.nombre}',
                'malla': malla,
                'pestana': 'estructura',
                'estructura': _estructura(malla),
                'nivel_form': NivelMallaForm(),
                'materia_form': MateriaMallaForm(malla=malla),
            })
        elif action == 'add_predecesora':
            materia_malla = get_object_or_404(
                MateriaMalla, pk=request.GET.get('materia_malla_id'), activo=True,
            )
            return render(request, 'academico/adm_mallas/add_predecesora.html', {
                'materia_malla': materia_malla,
                'form': MateriaMallaPredecesoraForm(materia_malla=materia_malla),
            })
        elif action == 'delete':
            pk = request.GET.get('pk')
            obj = get_object_or_404(Malla, pk=pk)
            return render(request, 'academico/adm_mallas/delete.html', {'object': obj})
        else:
            data['list'] = _listado()
            return render(request, 'academico/adm_mallas/view.html', data)
