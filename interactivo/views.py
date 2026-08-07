import json
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Avg, Count, Max, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from academico.models import MateriaMalla

from .forms import ActividadInteractivaForm
from .models import (
    ActividadInteractiva,
    EventoActividadInteractiva,
    IntentoActividadInteractiva,
)
from .plugins.base import PluginError
from .plugins.registry import all_plugins, get_plugin


def _can_manage(user, actividad=None, materia_malla=None):
    """Administra quien dicta la materia; el autor siempre puede con lo suyo."""
    if user.is_superuser or user.is_staff:
        return True
    if actividad is not None:
        if actividad.creador_id == user.id:
            return True
        materia_malla = actividad.materia_malla
    if materia_malla is not None:
        return materia_malla.profesores.filter(
            profesor=user, activo=True,
        ).exists()
    return False


def _save_with_user(instance, request):
    # Compatible tanto con un ModeloBase normal como con variantes que
    # exigen guardar pasando request.
    if hasattr(instance, 'usuario_creacion_id') and not instance.pk:
        instance.usuario_creacion = request.user
    if hasattr(instance, 'usuario_modificacion_id') and instance.pk:
        instance.usuario_modificacion = request.user
    instance.save()


def _posted_config(request, default=None):
    if request.method != 'POST':
        return default or {}
    try:
        value = json.loads(request.POST.get('configuracion_json') or '{}')
        return value if isinstance(value, dict) else (default or {})
    except json.JSONDecodeError:
        return default or {}


@login_required
@require_GET
def catalogo_motores(request):
    return render(request, 'interactivo/catalogo.html', {
        'title': 'Tipos de actividades interactivas',
        'motores': all_plugins(),
    })


def _materia(materia_malla_id):
    return get_object_or_404(
        MateriaMalla.objects.select_related('materia', 'nivel', 'malla'),
        pk=materia_malla_id,
        activo=True,
    )


@login_required
@require_GET
def lista_actividades(request, materia_malla_id):
    materia_malla = _materia(materia_malla_id)
    puede_gestionar = _can_manage(request.user, materia_malla=materia_malla)
    actividades = materia_malla.actividades_interactivas.select_related(
        'creador', 'tema', 'simulacion',
    ).all()
    if not puede_gestionar:
        actividades = actividades.filter(publicada=True)

    # Agrupadas por tema, con los sueltos de la materia al final.
    por_tema = {}
    for actividad in actividades:
        por_tema.setdefault(actividad.tema, []).append(actividad)
    grupos = [
        {'tema': tema, 'actividades': lista}
        for tema, lista in sorted(
            por_tema.items(),
            key=lambda par: (par[0] is None, par[0].orden if par[0] else 0),
        )
    ]

    return render(request, 'interactivo/lista.html', {
        'title': 'Juegos de la materia',
        'materia_malla': materia_malla,
        'grupos': grupos,
        'total': len(actividades),
        'puede_gestionar': puede_gestionar,
    })


@login_required
def crear_actividad(request, materia_malla_id):
    materia_malla = _materia(materia_malla_id)
    if not _can_manage(request.user, materia_malla=materia_malla):
        raise PermissionDenied

    if request.method == 'POST':
        form = ActividadInteractivaForm(request.POST, materia_malla=materia_malla)
        if form.is_valid():
            try:
                plugin = get_plugin(form.cleaned_data['motor'])
                config = plugin.normalize_config(form.cleaned_data['configuracion_json'])
                errors = plugin.validate_config(config)
                if errors:
                    for error in errors:
                        form.add_error('configuracion_json', error)
                else:
                    with transaction.atomic():
                        actividad = form.save(commit=False)
                        actividad.materia_malla = materia_malla
                        actividad.creador = request.user
                        actividad.motor_version = plugin.version
                        actividad.configuracion = config
                        _save_with_user(actividad, request)
                    messages.success(request, 'Juego creado correctamente.')
                    return redirect('interactivo:lista', materia_malla_id=materia_malla.pk)
            except PluginError as exc:
                form.add_error('motor', str(exc))
    else:
        form = ActividadInteractivaForm(
            materia_malla=materia_malla,
            initial={
                'orden': materia_malla.actividades_interactivas.count() + 1,
                'puntaje_minimo': 70,
                'obligatoria': True,
                'tema': request.GET.get('tema') or None,
            },
        )

    return render(request, 'interactivo/editor.html', {
        'title': 'Nuevo juego',
        'form': form,
        'materia_malla': materia_malla,
        'configuracion_inicial': _posted_config(request, {}),
    })


@login_required
def editar_actividad(request, actividad_id):
    actividad = get_object_or_404(ActividadInteractiva, pk=actividad_id)
    if not _can_manage(request.user, actividad=actividad):
        raise PermissionDenied

    try:
        plugin_actual = get_plugin(actividad.motor)
    except PluginError as exc:
        raise Http404(str(exc))

    if request.method == 'POST':
        form = ActividadInteractivaForm(
            request.POST, instance=actividad, materia_malla=actividad.materia_malla,
        )
        if form.is_valid():
            try:
                plugin = get_plugin(form.cleaned_data['motor'])
                config = plugin.normalize_config(form.cleaned_data['configuracion_json'])
                errors = plugin.validate_config(config)
                if errors:
                    for error in errors:
                        form.add_error('configuracion_json', error)
                else:
                    with transaction.atomic():
                        actividad = form.save(commit=False)
                        actividad.motor_version = plugin.version
                        actividad.configuracion = config
                        _save_with_user(actividad, request)
                    messages.success(request, 'Juego actualizado correctamente.')
                    return redirect(
                        'interactivo:lista', materia_malla_id=actividad.materia_malla_id,
                    )
            except PluginError as exc:
                form.add_error('motor', str(exc))
    else:
        form = ActividadInteractivaForm(
            instance=actividad, materia_malla=actividad.materia_malla,
        )

    return render(request, 'interactivo/editor.html', {
        'title': 'Editar juego',
        'form': form,
        'actividad': actividad,
        'materia_malla': actividad.materia_malla,
        'configuracion_inicial': _posted_config(
            request, plugin_actual.editor_config(actividad.configuracion)
        ),
    })


@login_required
@require_GET
def schema_motor(request, codigo):
    try:
        plugin = get_plugin(codigo)
    except PluginError as exc:
        return JsonResponse({'ok': False, 'error': str(exc)}, status=404)
    return JsonResponse({
        'ok': True,
        'codigo': plugin.codigo,
        'nombre': plugin.nombre,
        'descripcion': plugin.descripcion,
        'version': plugin.version,
        'schema': plugin.schema,
    })


@login_required
def jugar_actividad(request, actividad_id):
    actividad = get_object_or_404(ActividadInteractiva, pk=actividad_id)
    puede_gestionar = _can_manage(request.user, actividad=actividad)
    if not actividad.publicada and not puede_gestionar:
        raise PermissionDenied('La actividad todavía no está publicada.')

    if request.method != 'GET':
        return JsonResponse({'ok': False, 'error': 'Método no permitido.'}, status=405)

    try:
        plugin = get_plugin(actividad.motor)
    except PluginError as exc:
        raise Http404(str(exc))

    intento = actividad.intentos.filter(
        estudiante=request.user,
        estado=IntentoActividadInteractiva.EN_PROCESO,
    ).order_by('-fecha_inicio').first()

    if intento is None:
        realizados = actividad.intentos.filter(estudiante=request.user).count()
        if actividad.intentos_permitidos and realizados >= actividad.intentos_permitidos:
            messages.error(request, 'Ya utilizaste todos los intentos permitidos.')
            return redirect(
                'interactivo:lista', materia_malla_id=actividad.materia_malla_id,
            )

        numero = (
            actividad.intentos.filter(estudiante=request.user)
            .aggregate(maximo=Max('numero_intento'))['maximo'] or 0
        ) + 1
        intento = IntentoActividadInteractiva(
            actividad=actividad,
            estudiante=request.user,
            numero_intento=numero,
        )
        _save_with_user(intento, request)

    plugin_js = static(plugin.player_js) if plugin.player_js else ''
    plugin_css = static(plugin.player_css) if plugin.player_css else ''

    return render(request, 'interactivo/jugar.html', {
        'title': actividad.titulo,
        'actividad': actividad,
        'intento': intento,
        'configuracion_publica': plugin.public_config(actividad.configuracion),
        'plugin_js': plugin_js,
        'plugin_css': plugin_css,
        'renderer_codigo': plugin.renderer or plugin.codigo,
    })


@login_required
@require_POST
def finalizar_intento(request, intento_id):
    intento = get_object_or_404(
        IntentoActividadInteractiva.objects.select_related('actividad'),
        pk=intento_id,
        estudiante=request.user,
    )
    if intento.estado != IntentoActividadInteractiva.EN_PROCESO:
        return JsonResponse({'ok': False, 'error': 'El intento ya fue finalizado.'}, status=409)

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'JSON inválido.'}, status=400)

    respuesta = payload.get('respuesta', {})
    if not isinstance(respuesta, dict):
        return JsonResponse({'ok': False, 'error': 'La respuesta debe ser un objeto.'}, status=400)

    try:
        plugin = get_plugin(intento.actividad.motor)
        resultado = plugin.grade(intento.actividad.configuracion, respuesta)
    except (PluginError, ValueError, TypeError, KeyError) as exc:
        return JsonResponse({'ok': False, 'error': f'No se pudo calificar: {exc}'}, status=400)

    ahora = timezone.now()
    tiempo_real = max(int((ahora - intento.fecha_inicio).total_seconds()), 0)
    tiempo_cliente = int(payload.get('tiempo_segundos') or tiempo_real)
    tiempo = max(0, min(tiempo_cliente, tiempo_real + 30))
    porcentaje = Decimal(str(resultado.get('porcentaje', 0))).quantize(Decimal('0.01'))
    aprobado = porcentaje >= intento.actividad.puntaje_minimo

    intento.fecha_fin = ahora
    intento.tiempo_segundos = tiempo
    intento.puntaje = Decimal(str(resultado.get('puntaje', porcentaje)))
    intento.puntaje_maximo = Decimal(str(resultado.get('puntaje_maximo', 100)))
    intento.porcentaje = porcentaje
    intento.aciertos = int(resultado.get('aciertos', 0))
    intento.errores = int(resultado.get('errores', 0))
    intento.total_elementos = int(resultado.get('total', 0))
    intento.completado = True
    intento.aprobado = aprobado
    intento.estado = (
        IntentoActividadInteractiva.APROBADO
        if aprobado else IntentoActividadInteractiva.NO_APROBADO
    )
    intento.respuesta = respuesta
    intento.detalle_resultado = resultado.get('detalle', {})
    _save_with_user(intento, request)

    return JsonResponse({
        'ok': True,
        'intento_id': intento.pk,
        'porcentaje': float(intento.porcentaje),
        'aprobado': intento.aprobado,
        'redirect_url': reverse('interactivo:resultado', args=[intento.pk]),
    })


@login_required
@require_POST
def registrar_evento(request, intento_id):
    intento = get_object_or_404(
        IntentoActividadInteractiva,
        pk=intento_id,
        estudiante=request.user,
    )
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'JSON inválido.'}, status=400)

    verbo = str(payload.get('verbo', '')).strip()[:50]
    if not verbo:
        return JsonResponse({'ok': False, 'error': 'Falta el verbo del evento.'}, status=400)

    evento = EventoActividadInteractiva(
        intento=intento,
        verbo=verbo,
        elemento_id=str(payload.get('elemento_id', ''))[:120],
        tiempo_segundos=max(int(payload.get('tiempo_segundos') or 0), 0),
        datos=payload.get('datos', {}) if isinstance(payload.get('datos', {}), dict) else {},
    )
    _save_with_user(evento, request)
    return JsonResponse({'ok': True})


@login_required
@require_GET
def resultado_intento(request, intento_id):
    intento = get_object_or_404(
        IntentoActividadInteractiva.objects.select_related('actividad', 'estudiante'),
        pk=intento_id,
    )
    if intento.estudiante_id != request.user.id and not _can_manage(request.user, actividad=intento.actividad):
        raise PermissionDenied
    return render(request, 'interactivo/resultado.html', {
        'title': 'Resultado de la actividad',
        'intento': intento,
    })


@login_required
@require_GET
def estadisticas_actividad(request, actividad_id):
    actividad = get_object_or_404(ActividadInteractiva, pk=actividad_id)
    if not _can_manage(request.user, actividad=actividad):
        raise PermissionDenied

    intentos = actividad.intentos.filter(completado=True)
    resumen = intentos.aggregate(
        intentos=Count('id'),
        estudiantes=Count('estudiante', distinct=True),
        promedio=Avg('porcentaje'),
        tiempo_promedio=Avg('tiempo_segundos'),
        aprobados=Count('id', filter=Q(aprobado=True)),
        no_aprobados=Count('id', filter=Q(aprobado=False)),
    )
    mejores = (
        intentos.values('estudiante__username', 'estudiante__first_name', 'estudiante__last_name')
        .annotate(mejor=Max('porcentaje'), intentos=Count('id'))
        .order_by('-mejor', 'estudiante__username')
    )
    return render(request, 'interactivo/estadisticas.html', {
        'title': 'Estadísticas de la actividad',
        'actividad': actividad,
        'resumen': resumen,
        'mejores': mejores,
    })
