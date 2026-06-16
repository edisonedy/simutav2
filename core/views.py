from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from academico.models import Carrera, InscripcionMalla, Malla, Materia, PeriodoAcademico, ProfesorMateria
from core.forms import InstitucionForm
from core.models import PerfilUsuario
from core.models import Institucion
from simulador.models import EscenarioSimulacion, IntentoSimulacion, PasoSimulacion, Simulacion


@login_required
def dashboard(request):
    perfil = getattr(request.user, 'perfil', None)
    rol = perfil.rol if perfil else None
    contexto = {'perfil': perfil, 'rol': rol}

    if rol == PerfilUsuario.ESTUDIANTE:
        contexto['inscripciones'] = InscripcionMalla.objects.filter(
            estudiante=request.user,
            estado=InscripcionMalla.ACTIVA,
        ).select_related('malla', 'periodo')
        contexto['intentos'] = IntentoSimulacion.objects.filter(estudiante=request.user)[:5]
    elif rol == PerfilUsuario.PROFESOR:
        contexto['asignaciones'] = ProfesorMateria.objects.filter(
            profesor=request.user,
            activo=True,
        ).select_related('materia_malla__materia', 'periodo')
    else:
        contexto['total_carreras'] = Carrera.objects.count()
        contexto['total_mallas'] = Malla.objects.count()
        contexto['total_materias'] = Materia.objects.count()
        contexto['total_periodos'] = PeriodoAcademico.objects.count()
        contexto['total_profesores'] = PerfilUsuario.objects.filter(rol=PerfilUsuario.PROFESOR).count()
        contexto['total_estudiantes'] = PerfilUsuario.objects.filter(rol=PerfilUsuario.ESTUDIANTE).count()
        contexto['total_simulaciones'] = Simulacion.objects.count()
        contexto['total_escenarios'] = EscenarioSimulacion.objects.filter(activo=True).count()
        contexto['total_intentos'] = IntentoSimulacion.objects.count()
        contexto['total_decisiones_tomadas'] = PasoSimulacion.objects.count()
        contexto['simulaciones_recientes'] = Simulacion.objects.select_related(
            'materia_malla__materia',
            'materia_malla__nivel',
        ).order_by('-fecha_creacion')[:8]
        contexto['intentos_recientes'] = IntentoSimulacion.objects.select_related(
            'estudiante',
            'simulacion',
        ).order_by('-fecha_inicio')[:8]

    return render(request, 'dashboard.html', contexto)


@login_required
def instituciones(request):
    instituciones_qs = Institucion.objects.all()
    return render(request, 'core/instituciones/view.html', {'instituciones': instituciones_qs})


@login_required
def institucion_add(request):
    form = InstitucionForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        institucion = form.save(commit=False)
        institucion.usuario_creacion = request.user
        institucion.save()
        return redirect('core:instituciones')
    return render(request, 'core/instituciones/add.html', {'form': form})


@login_required
def institucion_edit(request, pk):
    institucion = get_object_or_404(Institucion, pk=pk)
    form = InstitucionForm(request.POST or None, instance=institucion)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('core:instituciones')
    return render(request, 'core/instituciones/edit.html', {'form': form, 'institucion': institucion})
