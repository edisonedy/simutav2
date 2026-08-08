from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from academico.models import Carrera, InscripcionMalla, Malla, Materia, PeriodoAcademico, ProfesorMateria
from core.funciones import CLAVE_PERIODO_SESION
from core.permisos import solo_administrativos, usuarios_con_rol
from core.models import PerfilUsuario
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
        ).select_related('malla_periodo__malla', 'malla_periodo__periodo')
        contexto['intentos'] = IntentoSimulacion.objects.filter(estudiante=request.user)[:5]
    elif rol == PerfilUsuario.PROFESOR:
        contexto['asignaciones'] = ProfesorMateria.objects.filter(
            profesor=request.user,
            activo=True,
        ).select_related('materia_malla__materia', 'materia_malla__nivel', 'materia_malla__malla')
    else:
        contexto['total_carreras'] = Carrera.objects.count()
        contexto['total_mallas'] = Malla.objects.count()
        contexto['total_materias'] = Materia.objects.count()
        contexto['total_periodos'] = PeriodoAcademico.objects.count()
        contexto['total_profesores'] = usuarios_con_rol(PerfilUsuario.PROFESOR).count()
        contexto['total_estudiantes'] = usuarios_con_rol(PerfilUsuario.ESTUDIANTE).count()
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
def cambiar_periodo(request):
    """Guarda en sesion el periodo elegido en la barra superior y devuelve al
    usuario a la pantalla donde estaba."""
    if request.method != 'POST':
        return redirect('dashboard')
    elegido = request.POST.get('periodo') or ''
    if elegido.isdigit() and PeriodoAcademico.objects.filter(pk=elegido, activo=True).exists():
        request.session[CLAVE_PERIODO_SESION] = int(elegido)
    else:
        request.session.pop(CLAVE_PERIODO_SESION, None)

    destino = request.POST.get('next') or ''
    if not url_has_allowed_host_and_scheme(
        destino, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
    ):
        destino = reverse('dashboard')
    return redirect(destino)


@solo_administrativos
def estado_ia(request):
    """Estado real de los proveedores, visible solo para administradores."""
    clave_cache = 'estado_proveedores_ia_v1'
    refrescar = request.GET.get('refresh') == '1'
    resultado = None if refrescar else cache.get(clave_cache)
    desde_cache = resultado is not None
    if resultado is None:
        from simulador.ia_status import comprobar_estado_ia
        resultado = comprobar_estado_ia()
        cache.set(clave_cache, resultado, 60)
    return JsonResponse({**resultado, 'desde_cache': desde_cache})
