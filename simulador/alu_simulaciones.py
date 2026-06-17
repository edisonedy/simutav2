from collections import OrderedDict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.db import transaction
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render, redirect
from core.funciones import ok_json, bad_json
from academico.models import InscripcionMalla, MateriaMalla, PeriodoAcademico
from simulador.models import Simulacion, IntentoSimulacion
from simulador.forms import PasoSimulacionForm
from simulador.services import (
    construir_estado_inicial,
    ejecutar_decision_arbol,
    ejecutar_ronda_ia_dinamica,
    obtener_escenario_inicial,
)
from simulador.generator_service import serializar_configuracion_simulacion


def _situacion_actual(intento, numero):
    if numero == 1:
        s = intento.simulacion
        return s.situacion_inicial or f'{s.contexto} Actuas como {s.rol_estudiante}. Objetivo: {s.objetivo}.'
    ultimo = intento.pasos.order_by('-numero').first()
    if ultimo and ultimo.siguiente_situacion:
        return ultimo.siguiente_situacion
    return f'Ronda {numero}: Continua con la simulacion de decisiones.'


def _estado_indicadores(intento):
    """Arma el estado de indicadores para la UI: nombre, valor, % de avance,
    color segun desempeno y el CAMBIO (delta) tras la ultima decision, para que
    el estudiante vea como reacciona la empresa a lo que decide."""
    estado = intento.estado_actual or {}
    pasos_validos = list(intento.pasos.filter(es_valido=True).order_by('numero'))
    ultimo = pasos_validos[-1] if pasos_validos else None
    antes = (ultimo.estado_antes if ultimo else {}) or {}
    inicial = construir_estado_inicial(intento.simulacion)
    indicadores = []
    for ind in intento.simulacion.indicadores.filter(activo=True):
        valor = estado.get(ind.codigo)
        if not isinstance(valor, (int, float)):
            continue
        minimo = float(ind.valor_minimo)
        maximo = float(ind.valor_maximo)
        rango = maximo - minimo or 1
        pct = max(0.0, min(100.0, (float(valor) - minimo) / rango * 100))
        es_bajo = ind.direccion_optima == ind.DIRECCION_BAJO
        desempeno = (100 - pct) if es_bajo else pct
        if desempeno >= 66:
            color = 'success'
        elif desempeno >= 40:
            color = 'warning'
        else:
            color = 'danger'
        valor_antes = antes.get(ind.codigo)
        delta = round(float(valor) - float(valor_antes), 1) if isinstance(valor_antes, (int, float)) else 0
        if delta > 0:
            flecha, delta_bueno = '▲', not es_bajo
        elif delta < 0:
            flecha, delta_bueno = '▼', es_bajo
        else:
            flecha, delta_bueno = '', None

        # Serie historica (inicial + cada ronda) para el mini-grafico de evolucion.
        valores_serie = [inicial.get(ind.codigo)]
        for p in pasos_validos:
            v = (p.estado_despues or {}).get(ind.codigo)
            valores_serie.append(v if isinstance(v, (int, float)) else valores_serie[-1])
        serie_pct = [
            max(0.0, min(100.0, (float(v) - minimo) / rango * 100)) if isinstance(v, (int, float)) else 50.0
            for v in valores_serie
        ]
        spark_points = _sparkline_points(serie_pct)

        indicadores.append({
            'codigo': ind.codigo,
            'nombre': ind.nombre,
            'valor': round(float(valor), 1),
            'pct': round(pct, 1),
            'color': color,
            'direccion': ind.direccion_optima,
            'critico': ind.es_critico,
            'delta': delta,
            'delta_abs': abs(delta),
            'flecha': flecha,
            'delta_bueno': delta_bueno,
            'spark_points': spark_points,
        })
    return indicadores


def _sparkline_points(serie_pct, ancho=120, alto=28, pad=2):
    """Convierte una serie de porcentajes (0-100) en puntos 'x,y x,y ...' para
    una polyline SVG. El eje Y se invierte (mas alto = arriba)."""
    n = len(serie_pct)
    if n == 0:
        return ''
    if n == 1:
        serie_pct = serie_pct * 2
        n = 2
    usable_w = ancho - 2 * pad
    usable_h = alto - 2 * pad
    paso = usable_w / (n - 1)
    puntos = []
    for i, pct in enumerate(serie_pct):
        x = pad + i * paso
        y = pad + (1 - pct / 100.0) * usable_h
        puntos.append(f'{round(x, 1)},{round(y, 1)}')
    return ' '.join(puntos)


def _pasos_stepper(simulacion, numero_actual):
    """Recorrido por etapas de la simulacion (Diagnostico -> Decision -> Plan ...)
    para que el estudiante vea en que punto del caso esta."""
    nombres = {1: 'Diagnóstico', 2: 'Decisión', 3: 'Plan'}
    total = simulacion.maximo_decisiones or 3
    pasos = []
    for n in range(1, total + 1):
        if n < numero_actual:
            estado = 'hecho'
        elif n == numero_actual:
            estado = 'actual'
        else:
            estado = 'pendiente'
        pasos.append({'numero': n, 'nombre': nombres.get(n, f'Ronda {n}'), 'estado': estado})
    return pasos


INSIGNIAS_CATALOGO = {
    'primera_mision': ('Primera misión', '🚀'),
    'mision_aprobada': ('Misión aprobada', '✅'),
    'maestria': ('Maestría (90+)', '🏆'),
    'racha_imparable': ('Racha imparable (x3)', '🔥'),
    'veterano': ('Veterano (5 misiones)', '🎖'),
    'explorador': ('Explorador (3 materias)', '🧭'),
}


def _carrera_contexto(user):
    """Datos de la pantalla 'Mi carrera': perfil de juego, insignias, ranking e historial."""
    from simulador.models import PerfilJuego

    perfil, _ = PerfilJuego.objects.get_or_create(usuario=user)
    ganadas = set(perfil.insignias or [])
    insignias_catalogo = [
        {'codigo': c, 'nombre': n, 'icono': ic, 'ganada': c in ganadas}
        for c, (n, ic) in INSIGNIAS_CATALOGO.items()
    ]
    ranking = PerfilJuego.objects.select_related('usuario').order_by('-xp_total')[:10]
    historial = (
        user.intentos_simulacion.filter(finalizado=True)
        .select_related('simulacion__materia_malla__materia')
        .order_by('-fecha_fin')[:8]
    )
    mi_posicion = PerfilJuego.objects.filter(xp_total__gt=perfil.xp_total).count() + 1
    return {
        'perfil': perfil,
        'insignias_catalogo': insignias_catalogo,
        'ranking': ranking,
        'historial': historial,
        'mi_posicion': mi_posicion,
    }


def _calcular_gamificacion(intento):
    """Capa de juego sobre el resultado: XP, rango con icono, progreso al
    siguiente rango e insignias ganadas, para una experiencia mas motivadora."""
    pasos_validos = list(intento.pasos.filter(es_valido=True).order_by('numero'))
    invalidos = intento.pasos.filter(es_valido=False).count()
    final = float(intento.puntuacion_final or 0)
    xp_total = int(round(sum(float(p.puntaje_paso) for p in pasos_validos)))

    # Rango segun la nota final (de menor a mayor).
    rangos = [
        (90, 'Maestro', '🏆'),
        (75, 'Experto', '🥇'),
        (60, 'Competente', '🥈'),
        (40, 'Aprendiz', '🥉'),
        (0, 'Novato', '🔰'),
    ]
    rango, icono, umbral_actual = 'Novato', '🔰', 0
    siguiente_umbral = 40
    for i, (umbral, nombre, ic) in enumerate(rangos):
        if final >= umbral:
            rango, icono, umbral_actual = nombre, ic, umbral
            siguiente_umbral = rangos[i - 1][0] if i > 0 else 100
            break
    tramo = max(1, siguiente_umbral - umbral_actual)
    progreso_pct = round(max(0, min(100, (final - umbral_actual) / tramo * 100)), 1)

    # Insignias.
    etiquetas = {1: 'Diagnóstico', 2: 'Decisión', 3: 'Plan'}
    insignias = []
    for p in pasos_validos:
        if float(p.puntaje_paso) >= 70:
            nombre_r = etiquetas.get(p.numero, f'Ronda {p.numero}')
            insignias.append({'nombre': f'{nombre_r} certero', 'icono': '🎯'})
    if pasos_validos and invalidos == 0:
        insignias.append({'nombre': 'Sin intentos fallidos', 'icono': '✅'})
    if pasos_validos and not any(float(p.penalizacion_aplicada) for p in pasos_validos):
        insignias.append({'nombre': 'Decisiones sin riesgo', 'icono': '🛡️'})
    if final >= 90:
        insignias.append({'nombre': 'Maestría', 'icono': '🏆'})
    elif final >= 75:
        insignias.append({'nombre': 'Gran desempeño', 'icono': '⭐'})

    # Empresa saneada: salud promedio de indicadores >= 60.
    salud = _salud_indicadores(intento)
    if salud is not None and salud >= 60:
        insignias.append({'nombre': 'Empresa saneada', 'icono': '🏢'})

    return {
        'xp_total': xp_total,
        'rango': rango,
        'icono': icono,
        'progreso_pct': progreso_pct,
        'siguiente_umbral': siguiente_umbral,
        'insignias': insignias,
        'rondas_validas': len(pasos_validos),
        'salud': round(salud, 0) if salud is not None else None,
    }


def _salud_indicadores(intento):
    """Promedio 0-100 de desempeno de los indicadores (considera direccion optima)."""
    estado = intento.estado_actual or {}
    valores = []
    for ind in intento.simulacion.indicadores.filter(activo=True):
        v = estado.get(ind.codigo)
        if not isinstance(v, (int, float)):
            continue
        minimo, maximo = float(ind.valor_minimo), float(ind.valor_maximo)
        rango = maximo - minimo or 1
        pct = max(0.0, min(100.0, (float(v) - minimo) / rango * 100))
        valores.append((100 - pct) if ind.direccion_optima == ind.DIRECCION_BAJO else pct)
    return sum(valores) / len(valores) if valores else None


def _hud_simulacion(intento):
    """HUD tipo videojuego para la consola del estudiante: XP acumulada, vidas
    (intentos validos restantes en la ronda) y salud de la empresa."""
    pasos_validos = intento.pasos.filter(es_valido=True)
    xp = int(round(sum(float(p.puntaje_paso) for p in pasos_validos)))
    vidas_max = intento.max_intentos_invalidos_por_ronda or 3
    vidas = max(0, vidas_max - intento.intentos_invalidos_actuales)
    salud = _salud_indicadores(intento)
    if salud is None:
        salud = 50.0
    if salud >= 66:
        salud_color = 'success'
    elif salud >= 40:
        salud_color = 'warning'
    else:
        salud_color = 'danger'
    return {
        'xp': xp,
        'vidas': vidas,
        'vidas_max': vidas_max,
        'salud': round(salud),
        'salud_color': salud_color,
    }


def _es_ajax(request):
    return request.headers.get('x-requested-with') == 'XMLHttpRequest'


def _ok_o_redirect(request, redirect_url, mensaje):
    if _es_ajax(request):
        return ok_json(data={'redirect_url': redirect_url}, mensaje=mensaje)
    messages.success(request, mensaje)
    return HttpResponseRedirect(redirect_url)


@login_required
@transaction.atomic
def view(request):
    data = {}
    if request.method == 'POST':
        action = request.POST.get('action') or request.GET.get('action')

        if action == 'iniciar':
            simulacion = get_object_or_404(
                Simulacion,
                pk=request.POST.get('simulacion_id'),
                estado=Simulacion.PUBLICADA,
                activo=True,
            )
            periodo = PeriodoAcademico.objects.filter(activo_matricula=True).first()
            escenario_inicial = None
            situacion_actual = simulacion.situacion_inicial or simulacion.contexto
            if simulacion.tipo_simulacion == Simulacion.TIPO_SIN_IA_ARBOL:
                escenario_inicial = obtener_escenario_inicial(simulacion)
                situacion_actual = escenario_inicial.situacion if escenario_inicial else ''
            intento = IntentoSimulacion.objects.create(
                estudiante=request.user,
                simulacion=simulacion,
                periodo=periodo,
                estado_actual=construir_estado_inicial(simulacion),
                configuracion_snapshot=simulacion.configuracion_snapshot or serializar_configuracion_simulacion(simulacion),
                escenario_actual=escenario_inicial,
                situacion_actual=situacion_actual,
                numero_ronda_actual=1,
            )
            return _ok_o_redirect(
                request,
                f'?action=simular&intento_id={intento.pk}',
                'Intento iniciado correctamente.',
            )

        elif action == 'ejecutar_paso':
            intento = get_object_or_404(
                IntentoSimulacion.objects.select_related('simulacion', 'escenario_actual'),
                pk=request.POST.get('intento_id'),
                estudiante=request.user,
                finalizado=False,
            )
            simulacion = intento.simulacion
            if simulacion.tipo_simulacion == Simulacion.TIPO_SIN_IA_ARBOL:
                if not intento.escenario_actual:
                    return bad_json(mensaje='La simulacion no tiene un escenario actual configurado.')
                decision = get_object_or_404(
                    intento.escenario_actual.decisiones,
                    pk=request.POST.get('decision_id'),
                    activo=True,
                )
                paso = ejecutar_decision_arbol(intento, decision)
            else:
                paso = ejecutar_ronda_ia_dinamica(
                    intento,
                    request.POST.get('decision', ''),
                    request.POST.get('justificacion', ''),
                )
            intento.refresh_from_db()
            if intento.finalizado:
                return _ok_o_redirect(
                    request,
                    f'?action=resultado&intento_id={intento.pk}',
                    'Simulacion finalizada. Revisa tus resultados.',
                )

            mensaje = 'Paso registrado correctamente.'
            if not paso.es_valido:
                mensaje = 'La respuesta no es valida. Corrige la decision y vuelve a responder la misma situacion.'
                if intento.intentos_invalidos_actuales == 0:
                    mensaje = 'Se agotaron los intentos invalidos de la ronda. Avanzas a una situacion de ayuda con puntaje 0 en esos intentos.'
            return _ok_o_redirect(request, f'?action=simular&intento_id={intento.pk}', mensaje)

    else:
        action = request.GET.get('action')

        if action == 'iniciar':
            simulacion = get_object_or_404(
                Simulacion,
                pk=request.GET.get('simulacion_id'),
                estado=Simulacion.PUBLICADA,
                activo=True,
            )
            data['simulacion'] = simulacion
            indicadores = simulacion.indicadores.filter(activo=True)
            data['indicadores'] = indicadores
            candidatos = (simulacion.parametros or {}).get('candidatos', [])
            data['candidatos'] = candidatos
            return render(request, 'simulador/alu_simulaciones/iniciar.html', data)

        elif action == 'simular':
            intento = get_object_or_404(
                IntentoSimulacion.objects.select_related('simulacion'),
                pk=request.GET.get('intento_id'),
                estudiante=request.user,
            )
            if intento.finalizado:
                return HttpResponseRedirect(f'?action=resultado&intento_id={intento.pk}')
            numero = intento.numero_ronda_actual
            data['intento'] = intento
            data['simulacion'] = intento.simulacion
            data['situacion'] = intento.situacion_actual or _situacion_actual(intento, numero)
            data['numero'] = numero
            data['form'] = PasoSimulacionForm(ronda=numero)
            data['ultimo_paso'] = intento.pasos.order_by('-numero').first()
            if intento.simulacion.tipo_simulacion == Simulacion.TIPO_SIN_IA_ARBOL:
                data['escenario'] = intento.escenario_actual
                data['decisiones'] = intento.escenario_actual.decisiones.filter(activo=True) if intento.escenario_actual else []
            else:
                data['acciones_sugeridas'] = intento.simulacion.acciones_sugeridas.filter(
                    Q(numero_ronda=numero) | Q(numero_ronda__isnull=True),
                    activo=True,
                )
                indicadores_estado = _estado_indicadores(intento)
                data['indicadores_estado'] = indicadores_estado
                data['cambios_indicadores'] = [i for i in indicadores_estado if i['flecha']]
                data['pasos_stepper'] = _pasos_stepper(intento.simulacion, numero)
                data['hud'] = _hud_simulacion(intento)
            return render(request, 'simulador/alu_simulaciones/simular.html', data)

        elif action == 'resultado':
            intento = get_object_or_404(
                IntentoSimulacion.objects.select_related('simulacion').prefetch_related('pasos'),
                pk=request.GET.get('intento_id'),
                estudiante=request.user,
            )
            data['intento'] = intento
            data['gamificacion'] = _calcular_gamificacion(intento)
            return render(request, 'simulador/alu_simulaciones/resultado.html', data)

        elif action == 'carrera':
            data.update(_carrera_contexto(request.user))
            return render(request, 'simulador/alu_simulaciones/carrera.html', data)

        from academico.models import Malla
        inscripciones = InscripcionMalla.objects.filter(
            estudiante=request.user,
            estado=InscripcionMalla.ACTIVA,
        ).select_related('malla')
        mallas_ids = list(inscripciones.values_list('malla_id', flat=True))
        malla_sel = request.GET.get('malla')

        # Paso 1: el estudiante elige primero la malla (para no mezclar materias).
        if not malla_sel:
            mallas_cards = []
            for malla in Malla.objects.filter(id__in=mallas_ids, activo=True).select_related('carrera'):
                mm_list = list(
                    MateriaMalla.objects.filter(malla=malla, activo=True).prefetch_related('simulaciones')
                )
                n_sims = sum(
                    1 for mm in mm_list for s in mm.simulaciones.all()
                    if s.estado == Simulacion.PUBLICADA and s.activo
                )
                mallas_cards.append({'malla': malla, 'materias': len(mm_list), 'simulaciones': n_sims})
            data['mallas'] = mallas_cards
            return render(request, 'simulador/alu_simulaciones/mallas.html', data)

        # Paso 2: ya eligio una malla -> mostrar solo SUS materias por nivel.
        materias = (
            MateriaMalla.objects
            .filter(malla_id=malla_sel, malla_id__in=mallas_ids, activo=True)
            .select_related('materia', 'nivel', 'malla__carrera')
            .prefetch_related('simulaciones')
            .order_by('nivel__numero', 'orden', 'materia__nombre')
        )
        data['malla_sel'] = materias[0].malla if materias else None
        # Agrupar por nivel en orden (primero -> ultimo) para el dashboard.
        niveles = OrderedDict()
        total_simulaciones = 0
        for m in materias:
            sims = [s for s in m.simulaciones.all() if s.estado == Simulacion.PUBLICADA and s.activo]
            m.simulaciones_disponibles = sims
            total_simulaciones += len(sims)
            numero = m.nivel.numero if m.nivel else 0
            if numero not in niveles:
                niveles[numero] = {
                    'numero': numero,
                    'nombre': m.nivel.nombre if m.nivel else 'Sin nivel',
                    'materias': [],
                    'total_simulaciones': 0,
                }
            niveles[numero]['materias'].append(m)
            niveles[numero]['total_simulaciones'] += len(sims)
        data['niveles'] = list(niveles.values())
        data['total_simulaciones'] = total_simulaciones
        data['total_materias'] = len(materias)
        return render(request, 'simulador/alu_simulaciones/view.html', data)
