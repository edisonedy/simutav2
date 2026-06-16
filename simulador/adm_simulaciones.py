from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.shortcuts import get_object_or_404, render

from core.funciones import ok_json, bad_json
from simulador.models import Simulacion, IndicadorSimulacion, RestriccionSimulacion
from simulador.models import CriterioEvaluacion, ConceptoEsperadoRonda
from simulador.models import EscenarioSimulacion, DecisionConfigurada
from simulador.forms import SimulacionForm


@login_required
@transaction.atomic
def view(request):
    data = {'title': 'Simulaciones'}
    if request.method == 'POST':
        action = request.POST.get('action') or request.GET.get('action')
        if action == 'add':
            form = SimulacionForm(request.POST)
            if form.is_valid():
                obj = form.save(commit=False)
                obj.profesor = request.user
                obj.usuario_creacion = request.user
                obj.estado = Simulacion.BORRADOR
                obj.save()
                return ok_json()
            return bad_json(mensaje='Error en el formulario', data={'errors': form.errors})
        elif action == 'edit':
            pk = request.POST.get('pk') or request.GET.get('pk')
            obj = get_object_or_404(Simulacion, pk=pk)
            form = SimulacionForm(request.POST, instance=obj)
            if form.is_valid():
                form.save()
                return ok_json()
            return bad_json(mensaje='Error en el formulario', data={'errors': form.errors})
        elif action == 'delete':
            pk = request.POST.get('pk') or request.GET.get('pk')
            obj = get_object_or_404(Simulacion, pk=pk)
            obj.activo = False
            obj.save()
            return ok_json(mensaje='Eliminado correctamente')
        return bad_json(mensaje='Accion no valida')
    else:
        action = request.GET.get('action')
        if action == 'add':
            form = SimulacionForm()
            return render(request, 'simulador/adm_simulaciones/add.html', {'form': form})
        elif action == 'edit':
            pk = request.GET.get('pk')
            obj = get_object_or_404(Simulacion, pk=pk)
            form = SimulacionForm(instance=obj)
            return render(request, 'simulador/adm_simulaciones/edit.html', {'form': form, 'object': obj})
        elif action == 'delete':
            pk = request.GET.get('pk')
            obj = get_object_or_404(Simulacion, pk=pk)
            return render(request, 'simulador/adm_simulaciones/delete.html', {'object': obj})
        elif action == 'config':
            pk = request.GET.get('pk')
            sim = get_object_or_404(
                Simulacion.objects.select_related(
                    'materia_malla__materia', 'materia_malla__nivel', 'materia_malla__malla',
                    'profesor', 'usuario_creacion',
                ),
                pk=pk,
            )
            indicadores = sim.indicadores.filter(activo=True).order_by('codigo')
            restricciones = sim.restricciones.filter(activo=True).order_by('codigo_indicador')
            criterios = sim.criterios.filter(activo=True).order_by('-peso')
            conceptos = ConceptoEsperadoRonda.objects.filter(
                simulacion=sim, activo=True
            ).order_by('numero_ronda', 'nombre')
            escenarios = EscenarioSimulacion.objects.filter(
                simulacion=sim, activo=True
            ).order_by('orden').prefetch_related(
                'decisiones'
            )
            return render(request, 'simulador/adm_simulaciones/config.html', {
                'simulacion': sim,
                'indicadores': indicadores,
                'restricciones': restricciones,
                'criterios': criterios,
                'conceptos': conceptos,
                'escenarios': escenarios,
            })
        else:
            data['list'] = Simulacion.objects.select_related(
                'materia_malla__materia', 'profesor',
            ).all()
            return render(request, 'simulador/adm_simulaciones/view.html', data)
