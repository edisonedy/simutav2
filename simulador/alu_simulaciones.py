from collections import OrderedDict
from types import SimpleNamespace

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Prefetch, Q
from django.db import transaction
from django.http import HttpResponseRedirect
from django.utils import timezone
from django.shortcuts import get_object_or_404, render
from core.funciones import ok_json, bad_json
from academico.models import InscripcionMalla, MateriaMalla, PeriodoAcademico
from interactivo.models import ActividadInteractiva, IntentoActividadInteractiva
from interactivo.services import actividades_pendientes
from simulador.models import (
    ActividadMateria, InvestigacionSimulacion, PerfilJuego, Simulacion, IntentoSimulacion,
)
from simulador import cursos_service
from simulador.forms import PasoSimulacionForm
from simulador.services import (
    CRITERIOS_DECISION,
    calcular_bonificaciones,
    campos_decision_ronda,
    evaluar_campos_numericos,
    validar_campos_decision,
    comprar_investigacion,
    configuracion_respuesta_ronda,
    construir_estado_inicial,
    cumple_operador,
    desempeno_indicador,
    indicador_mejora,
    investigaciones_disponibles,
    justificacion_obligatoria,
    maximo_decisiones_intento,
    maximo_ejecuciones_efectivo,
    construir_recursos_iniciales,
    ejecutar_decision_arbol,
    ejecutar_ronda_ia_dinamica,
    obtener_escenario_inicial,
    obtener_conceptos_esperados_ronda,
    resultado_del_caso,
)
from simulador.generator_service import serializar_configuracion_simulacion


CODIGOS_EVALUACION_ACADEMICA = {
    'calidad', 'calidad_analisis', 'claridad', 'claridad_justificacion',
    'impacto', 'impacto_esperado', 'riesgo', 'riesgo_decision',
    'viabilidad', 'viabilidad_propuesta',
}


def _es_indicador_academico(codigo):
    return str(codigo or '').lower() in CODIGOS_EVALUACION_ACADEMICA


def _periodo_del_estudiante(usuario):
    """El periodo con el que se sella un intento.

    Sale de la malla en la que el estudiante esta inscrito. Si esta en varias,
    manda la mas reciente; si no esta en ninguna, el intento se guarda sin
    periodo, que es un dato de reporteria y no un requisito para jugar.
    """
    inscripcion = InscripcionMalla.objects.filter(
        estudiante=usuario,
        estado=InscripcionMalla.ACTIVA,
        activo=True,
    ).select_related(
        'malla_periodo__periodo',
    ).order_by(
        '-malla_periodo__periodo__fecha_inicio',
    ).first()

    if inscripcion:
        return inscripcion.malla_periodo.periodo

    return PeriodoAcademico.objects.filter(activo=True).order_by('-fecha_inicio').first()


def _pronostico_desde_post(request):
    return {
        'indicador': request.POST.get('pronostico_indicador', ''),
        'direccion': request.POST.get('pronostico_direccion', ''),
        'justificacion': request.POST.get('pronostico_justificacion', ''),
    }


def _aplicar_campos_al_paso(paso, campos, valores):
    """Guarda lo que el estudiante entrego en los campos de la ronda y, si el
    docente puso un valor esperado, promedia esa correccion -que es aritmetica,
    no interpretacion- con el puntaje de la rubrica.
    """
    detalle = dict(paso.evaluacion_detalle or {})
    detalle['campos_respuesta'] = valores
    numerico = evaluar_campos_numericos(campos, valores)
    campos_actualizados = ['evaluacion_detalle']

    if numerico and paso.es_valido:
        detalle['campos_numericos'] = numerico['detalle']
        detalle['puntaje_campos'] = numerico['puntaje']
        detalle['puntaje_rubrica'] = float(paso.puntaje_paso)
        paso.puntaje_paso = round((float(paso.puntaje_paso) + numerico['puntaje']) / 2, 2)
        campos_actualizados.append('puntaje_paso')

    paso.evaluacion_detalle = detalle
    paso.save(update_fields=campos_actualizados)
    return paso


def _tradeoff_desde_post(request):
    return (request.POST.get('tradeoff_aceptado') or '').strip()


def _andamiaje_adaptativo(intento):
    """Ajusta la ayuda segun desempeno reciente y autorregulacion.

    ALTO: el estudiante necesita estructura explicita.
    MEDIO: mantiene el ciclo pronostico/trade-off/reflexion.
    BAJO: desvanece campos obligatorios y usa preguntas abiertas.
    """
    pasos = list(intento.pasos.order_by('-numero')[:3])
    if not pasos:
        return {
            'nivel': 'MEDIO',
            'etiqueta': 'Guia normal',
            'requiere_campos': True,
            'mensaje': 'Formula una hipotesis y reconoce el costo de tu decision antes de actuar.',
        }
    invalidos = sum(1 for p in pasos if not p.es_valido)
    validos = [p for p in pasos if p.es_valido]
    promedio = sum(float(p.puntaje_paso) for p in validos) / len(validos) if validos else 0
    ultimo = pasos[0]
    fallo_pronostico = (ultimo.pronostico_resultado or {}).get('estado') == 'diferencia'
    sin_reflexion = bool(ultimo.es_valido and not ultimo.reflexion)
    sin_tradeoff = bool(ultimo.es_valido and not ultimo.tradeoff_aceptado)

    if invalidos or promedio < 60 or fallo_pronostico:
        return {
            'nivel': 'ALTO',
            'etiqueta': 'Paso guiado',
            'requiere_campos': True,
            'mensaje': 'Antes de decidir, identifica indicador, efecto esperado y sacrificio aceptado.',
        }
    if promedio >= 80 and not sin_reflexion and not sin_tradeoff:
        return {
            'nivel': 'BAJO',
            'etiqueta': 'Autonomia',
            'requiere_campos': False,
            'mensaje': 'Ya puedes decidir con menos guia: usa pronostico y trade-off solo si te ayudan a pensar mejor.',
        }
    return {
        'nivel': 'MEDIO',
        'etiqueta': 'Guia normal',
        'requiere_campos': True,
        'mensaje': 'Mantén el habito: anticipa el efecto y explicita el trade-off antes de actuar.',
    }


def _progreso_objetivo(operador, valor, objetivo, minimo, maximo):
    """% de avance hacia una meta (0-100). Da sensacion de progreso para la mision."""
    valor = float(valor)
    objetivo = float(objetivo)
    minimo = float(minimo)
    maximo = float(maximo)
    if operador in ('>=', '>'):
        if valor >= objetivo:
            return 100
        base = objetivo - minimo or 1
        return max(0, min(100, round((valor - minimo) / base * 100)))
    if operador in ('<=', '<'):
        if valor <= objetivo:
            return 100
        base = maximo - objetivo or 1
        return max(0, min(100, round((maximo - valor) / base * 100)))
    if operador == 'ABS<=':
        if abs(valor) <= abs(objetivo):
            return 100
        extremo = max(abs(minimo), abs(maximo))
        base = extremo - abs(objetivo) or 1
        return max(0, min(100, round((extremo - abs(valor)) / base * 100)))
    return 100 if valor == objetivo else 0


def _meta_legible(operador, objetivo, unidad):
    unidad = unidad or ''
    objetivo_txt = _valor_legible(objetivo, unidad)
    if operador == 'ABS<=':
        return f'entre -{objetivo_txt} y +{objetivo_txt}'
    return f'{operador} {objetivo_txt}'.strip()


def _valor_legible(valor, unidad=''):
    valor = float(valor)
    if unidad.strip() == '$':
        texto = f'{valor:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
        return f'${texto}'
    decimales = 0 if valor.is_integer() else (2 if abs(valor) < 100 else 1)
    texto = f'{valor:.{decimales}f}'.replace('.', ',')
    return f'{texto} {unidad}'.strip()


def _reaccion_narrada(paso, intento_o_simulacion):
    """Narra la reaccion de la empresa como una breve historia, a partir de los
    cambios REALES de indicadores. Sin IA: instantaneo, robusto y emotivo. Le da
    'alma' a las consecuencias (lo que la ciencia de serious games llama feedback
    emocional) sin pedirle nada extra al estudiante."""
    if not paso or not paso.es_valido:
        return ''
    antes = paso.estado_antes or {}
    despues = paso.estado_despues or {}
    # Compatibilidad: el flujo actual entrega el intento (para respetar su
    # snapshot), pero esta utilidad tambien se usa directamente con una
    # Simulacion en pruebas y llamadas antiguas.
    if hasattr(intento_o_simulacion, 'simulacion'):
        indicadores = _indicadores_del_intento(intento_o_simulacion)
    else:
        indicadores = intento_o_simulacion.indicadores.filter(activo=True)
    inds = {i.codigo: i for i in indicadores}
    mejoras, deterioros = [], []
    for cod, ind in inds.items():
        va, vd = antes.get(cod), despues.get(cod)
        if not isinstance(va, (int, float)) or not isinstance(vd, (int, float)):
            continue
        delta = float(vd) - float(va)
        if abs(delta) < 0.05:
            continue
        bueno = indicador_mejora(ind, va, vd)
        if bueno is None:
            continue
        (mejoras if bueno else deterioros).append((abs(delta), ind.nombre))
    mejoras.sort(reverse=True)
    deterioros.sort(reverse=True)
    partes = []
    if mejoras:
        txt = f'{mejoras[0][1]} mejoró'
        if len(mejoras) > 1:
            txt += f' y {mejoras[1][1]} también'
        partes.append(txt)
    if deterioros:
        partes.append(f'pero {deterioros[0][1]} se resintió')
    cuerpo = '; '.join(partes) if partes else 'los indicadores apenas se movieron'
    puntaje = float(paso.puntaje_paso)
    if puntaje >= 70:
        return f'📈 La empresa responde bien: {cuerpo}. El equipo retoma confianza.'
    if puntaje >= 40:
        return f'📊 Reacción mixta: {cuerpo}. Hay avances, pero la gerencia sigue atenta.'
    return f'📉 Momento tenso: {cuerpo}. La presión sube y piden mejores decisiones.'


def _objetivos_desde_estado(simulacion, estado):
    """Metas de la mision con progreso, calculadas desde un estado dado. Usa
    condiciones de exito; si no hay, cae a las restricciones. Sirve tanto para la
    portada (estado inicial) como para la partida en curso."""
    estado = estado or {}
    inds = {i.codigo: i for i in simulacion.indicadores.filter(activo=True)}
    objetivos = []
    fuentes = list(simulacion.condiciones_exito.filter(activo=True))
    usa_condiciones = bool(fuentes)
    if not usa_condiciones:
        fuentes = list(simulacion.restricciones.filter(activo=True))
    for f in fuentes:
        codigo = f.codigo_indicador
        ind = inds.get(codigo)
        valor = estado.get(codigo)
        if ind is None or not isinstance(valor, (int, float)):
            continue
        objetivo = float(f.valor_objetivo if usa_condiciones else f.valor_limite)
        pct = _progreso_objetivo(f.operador, valor, objetivo, ind.valor_minimo, ind.valor_maximo)
        objetivos.append({
            'codigo': codigo,
            'descripcion': getattr(f, 'descripcion', '') or f'Lleva {ind.nombre} a {f.operador} {objetivo:g}',
            'indicador': ind.nombre,
            'meta': _meta_legible(f.operador, objetivo, ind.unidad),
            'valor_actual': round(float(valor), 1),
            'valor_actual_legible': _valor_legible(valor, ind.unidad),
            'cumplido': cumple_operador(f.operador, valor, objetivo),
            'progreso_pct': pct,
            'tipo': 'meta' if usa_condiciones else 'restriccion',
        })
    return objetivos


def _objetivos_mision(intento):
    snapshot = intento.configuracion_snapshot or {}
    indicadores = snapshot.get('indicadores') or []
    if not indicadores:
        return _objetivos_desde_estado(intento.simulacion, intento.estado_actual)
    por_codigo = {i.get('codigo'): i for i in indicadores}
    fuentes = snapshot.get('condiciones_exito') or snapshot.get('restricciones') or []
    usa_condiciones = bool(snapshot.get('condiciones_exito'))
    objetivos = []
    for fuente in fuentes:
        codigo = fuente.get('codigo_indicador')
        ind = por_codigo.get(codigo)
        valor = (intento.estado_actual or {}).get(codigo)
        if not ind or not isinstance(valor, (int, float)):
            continue
        meta = float(fuente.get('valor_objetivo') if usa_condiciones else fuente.get('valor_limite'))
        inicial = float(ind.get('valor_inicial', 0))
        operador = fuente.get('operador', '=')
        pct = _progreso_objetivo(
            operador, valor, meta, ind.get('valor_minimo', 0), ind.get('valor_maximo', 100),
        )
        delta = round(float(valor) - inicial, 2)
        if operador == 'ABS<=':
            mejora = abs(float(valor)) < abs(inicial)
        else:
            mejora = delta > 0 if operador in ('>=', '>') else delta < 0 if operador in ('<=', '<') else delta == 0
        objetivos.append({
            'codigo': codigo,
            'descripcion': fuente.get('descripcion') or f'Lleva {ind.get("nombre")} a {operador} {meta:g}',
            'indicador': ind.get('nombre', codigo),
            'meta': _meta_legible(operador, meta, ind.get('unidad', '')),
            'valor_actual': round(float(valor), 2),
            'valor_actual_legible': _valor_legible(valor, ind.get('unidad', '')),
            'valor_inicial': round(inicial, 2),
            'valor_inicial_legible': _valor_legible(inicial, ind.get('unidad', '')),
            'delta': delta,
            'evolucion': 'sin_cambio' if delta == 0 else ('mejora' if mejora else 'empeora'),
            'cumplido': cumple_operador(operador, valor, meta),
            'progreso_pct': pct,
            'tipo': 'meta' if usa_condiciones else 'restriccion',
        })
    return objetivos


def _caso_del_intento(intento):
    """Datos inmutables que vio el estudiante al comenzar el intento."""
    caso = (intento.configuracion_snapshot or {}).get('caso') or {}
    if caso:
        return caso
    simulacion = intento.simulacion
    return {
        'titulo': simulacion.titulo,
        'tema': simulacion.tema,
        'tipo_simulacion': simulacion.tipo_simulacion,
        'maximo_decisiones': simulacion.maximo_decisiones,
        'rol_estudiante': simulacion.rol_estudiante,
        'objetivo': simulacion.objetivo,
        'situacion_inicial': simulacion.situacion_inicial,
        'parametros': simulacion.parametros or {},
    }


def _indicadores_del_intento(intento):
    datos = (intento.configuracion_snapshot or {}).get('indicadores') or []
    if datos:
        return [SimpleNamespace(**item) for item in datos]
    return list(intento.simulacion.indicadores.filter(activo=True))


def _metas_por_indicador(intento):
    snapshot = intento.configuracion_snapshot or {}
    condiciones = snapshot.get('condiciones_exito')
    if condiciones is None:
        condiciones = list(
            intento.simulacion.condiciones_exito.filter(activo=True).values(
                'codigo_indicador', 'operador', 'valor_objetivo',
            )
        )
    return {
        item.get('codigo_indicador'): item
        for item in (condiciones or [])
        if item.get('codigo_indicador')
    }


def _desempeno_con_meta(indicador, valor, meta=None):
    """Usa la meta docente como umbral aceptable de 70/100."""
    if not meta:
        return desempeno_indicador(indicador, valor)
    try:
        valor = float(valor)
        objetivo = float(meta.get('valor_objetivo'))
        minimo = float(indicador.valor_minimo)
        maximo = float(indicador.valor_maximo)
    except (TypeError, ValueError):
        return desempeno_indicador(indicador, valor)
    operador = meta.get('operador')
    if operador in ('>=', '>'):
        if valor >= objetivo:
            return min(100, 70 + (valor - objetivo) / (maximo - objetivo or 1) * 30)
        return max(0, (valor - minimo) / (objetivo - minimo or 1) * 70)
    if operador in ('<=', '<'):
        if valor <= objetivo:
            return min(100, 70 + (objetivo - valor) / (objetivo - minimo or 1) * 30)
        return max(0, (maximo - valor) / (maximo - objetivo or 1) * 70)
    return desempeno_indicador(indicador, valor)


def _recursos_del_intento(intento):
    datos = (intento.configuracion_snapshot or {}).get('recursos')
    if datos is not None:
        return [SimpleNamespace(**item) for item in datos]
    return list(intento.simulacion.recursos.filter(activo=True))


def _historial_acciones_seleccionadas(intento):
    conteos = {}
    for detalle in intento.pasos.filter(es_valido=True).values_list('evaluacion_detalle', flat=True):
        seleccion = (detalle or {}).get('seleccion_registrada') or {}
        accion_id = seleccion.get('accion_id')
        if accion_id is not None:
            try:
                accion_id = int(accion_id)
                conteos[accion_id] = conteos.get(accion_id, 0) + 1
            except (TypeError, ValueError):
                continue
    return set(conteos), conteos


def _accion_habilitada_por_historial(accion, seleccionadas, conteos, total_rondas=1):
    requerida = getattr(accion, 'requiere_accion_previa_id', None)
    bloqueante = getattr(accion, 'bloqueada_por_accion_previa_id', None)
    maximo = maximo_ejecuciones_efectivo(accion, total_rondas)
    accion_id = int(getattr(accion, 'pk', 0) or 0)
    if requerida is not None and int(requerida) not in seleccionadas:
        return False
    if bloqueante is not None and int(bloqueante) in seleccionadas:
        return False
    if maximo and conteos.get(accion_id, 0) >= maximo:
        return False
    return True


def _acciones_del_intento(intento, numero):
    datos = (intento.configuracion_snapshot or {}).get('acciones_sugeridas') or []
    seleccionadas, conteos = _historial_acciones_seleccionadas(intento)
    total_rondas = maximo_decisiones_intento(intento)
    if not datos or any(item.get('id') is None for item in datos):
        acciones = list(intento.simulacion.acciones_sugeridas.select_related(
            'opcion_caso', 'requiere_accion_previa', 'bloqueada_por_accion_previa',
        ).filter(
            Q(numero_ronda=numero) | Q(numero_ronda__isnull=True), activo=True,
        ))
        return [
            a for a in acciones
            if _accion_habilitada_por_historial(a, seleccionadas, conteos, total_rondas)
        ]
    opciones = {
        item.get('id'): item for item in (intento.configuracion_snapshot or {}).get('opciones_caso', [])
    }
    acciones = []
    for item in datos:
        if item.get('numero_ronda') not in (None, numero):
            continue
        requerida = item.get('requiere_accion_previa_id')
        if requerida is not None and int(requerida) not in seleccionadas:
            continue
        bloqueante = item.get('bloqueada_por_accion_previa_id')
        if bloqueante is not None and int(bloqueante) in seleccionadas:
            continue
        maximo = maximo_ejecuciones_efectivo(item, total_rondas)
        if maximo and conteos.get(int(item.get('id')), 0) >= maximo:
            continue
        opcion = opciones.get(item.get('opcion_caso_id')) or {}
        valores = {k: v for k, v in item.items() if k != 'id'}
        valores['texto_visible'] = opcion.get('nombre') or item.get('texto', '')
        valores['descripcion_visible'] = opcion.get('subtitulo') or item.get('descripcion', '')
        acciones.append(SimpleNamespace(pk=item.get('id'), **valores))
    return acciones


def _investigacion_del_intento(intento, investigacion_id):
    """Obtiene la averiguacion congelada al iniciar; las ediciones posteriores
    del docente no cambian el caso que el estudiante ya esta resolviendo."""
    try:
        investigacion_id = int(investigacion_id)
    except (TypeError, ValueError):
        return None
    congeladas = (intento.configuracion_snapshot or {}).get('investigaciones')
    if congeladas is not None:
        item = next((i for i in congeladas if i.get('id') == investigacion_id), None)
        if not item or int(item.get('disponible_desde_ronda') or 1) > intento.numero_ronda_actual:
            return None
        return SimpleNamespace(**item)
    return InvestigacionSimulacion.objects.filter(
        pk=investigacion_id,
        simulacion=intento.simulacion,
        activo=True,
        disponible_desde_ronda__lte=intento.numero_ronda_actual,
    ).first()


def _situacion_actual(intento, numero):
    """Que se le plantea al estudiante en esta ronda.

    En un caso de decisiones independientes manda SIEMPRE lo que el docente
    escribio en la ronda: la ronda 2 es una situacion ya preparada, no la
    consecuencia de la ronda 1. En una simulacion encadenada es al reves: pesa
    mas como quedo la empresa despues de la decision anterior.
    """
    caso = _caso_del_intento(intento)
    configurada = (_configuracion_ronda(
        intento.simulacion, numero, caso.get('parametros') or {},
    ).get('situacion') or '').strip()
    encadenada = (
        intento.simulacion.modo_ejecucion == Simulacion.MODO_SIMULACION_ENCADENADA
    )

    if configurada and not encadenada:
        return configurada

    if numero == 1:
        return caso.get('situacion_inicial') or configurada or (
            f'{caso.get("contexto", "")} Actuas como {caso.get("rol_estudiante", "")}. '
            f'Objetivo: {caso.get("objetivo", "")}.'
        )

    ultimo = intento.pasos.order_by('-numero').first()
    if ultimo and ultimo.siguiente_situacion:
        return ultimo.siguiente_situacion
    if configurada:
        return configurada
    return f'Ronda {numero}: Continua con la simulacion de decisiones.'


def _estado_indicadores(intento):
    """Arma el estado de indicadores para la UI: nombre, valor, % de avance,
    color segun desempeno y el CAMBIO (delta) tras la ultima decision, para que
    el estudiante vea como reacciona la empresa a lo que decide."""
    estado = intento.estado_actual or {}
    pasos_validos = list(intento.pasos.filter(es_valido=True).order_by('numero'))
    ultimo = pasos_validos[-1] if pasos_validos else None
    antes = (ultimo.estado_antes if ultimo else {}) or {}
    inicial = {i.codigo: float(i.valor_inicial) for i in _indicadores_del_intento(intento)}
    indicadores = []
    metas = _metas_por_indicador(intento)
    for ind in _indicadores_del_intento(intento):
        valor = estado.get(ind.codigo)
        if not isinstance(valor, (int, float)):
            continue
        minimo = float(ind.valor_minimo)
        maximo = float(ind.valor_maximo)
        rango = maximo - minimo or 1
        desempeno = _desempeno_con_meta(ind, valor, metas.get(ind.codigo))
        pct = desempeno
        if desempeno >= 66:
            color = 'success'
        elif desempeno >= 40:
            color = 'warning'
        else:
            color = 'danger'
        valor_antes = antes.get(ind.codigo)
        delta = round(float(valor) - float(valor_antes), 1) if isinstance(valor_antes, (int, float)) else 0
        if delta > 0:
            flecha, delta_bueno = '▲', indicador_mejora(ind, valor_antes, valor)
        elif delta < 0:
            flecha, delta_bueno = '▼', indicador_mejora(ind, valor_antes, valor)
        else:
            flecha, delta_bueno = '', None

        # Serie historica (inicial + cada ronda) para el mini-grafico de evolucion.
        valores_serie = [inicial.get(ind.codigo)]
        for p in pasos_validos:
            v = (p.estado_despues or {}).get(ind.codigo)
            valores_serie.append(v if isinstance(v, (int, float)) else valores_serie[-1])
        serie_pct = [
            _desempeno_con_meta(ind, v, metas.get(ind.codigo))
            if isinstance(v, (int, float)) else 50.0
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
            'es_academico': _es_indicador_academico(ind.codigo),
        })
    return indicadores


def _recursos_estado(intento):
    recursos_actuales = intento.recursos_actuales or {}
    items = []
    for recurso in _recursos_del_intento(intento):
        valor = recursos_actuales.get(recurso.codigo)
        if not isinstance(valor, (int, float)):
            valor = float(recurso.valor_inicial)
        minimo = float(recurso.valor_minimo)
        maximo = float(recurso.valor_maximo)
        rango = maximo - minimo or 1
        pct = max(0.0, min(100.0, (float(valor) - minimo) / rango * 100))
        if pct >= 50:
            color = 'success'
        elif pct >= 25:
            color = 'warning'
        else:
            color = 'danger'
        items.append({
            'codigo': recurso.codigo,
            'nombre': recurso.nombre,
            'valor': round(float(valor), 1),
            'unidad': recurso.unidad,
            'pct': round(pct, 1),
            'color': color,
            'critico': recurso.es_critico,
        })
    return items


ETIQUETAS_DATOS_CASO = {
    'alternativas_titulo': 'Alternativas del caso',
    'alternativa_col': 'Alternativa',
    'valor_titulo': 'Valor de referencia',
    'valor_col': 'Valor',
    'fortaleza_titulo': 'Fortaleza',
    'fortaleza_col': 'Fortaleza',
    'riesgo_titulo': 'Riesgo o limitación',
    'riesgo_col': 'Riesgo o limitación',
    'matriz_titulo': 'Criterios de comparación',
    'datos_titulo': 'Información para decidir',
}


def _etiquetas_datos_caso(parametros):
    """Etiquetas neutrales con compatibilidad para configuraciones antiguas.

    Los nombres históricos (candidato, salario, prueba técnica) solo se usan si
    el caso los configuró expresamente; nunca vuelven a ser el valor por defecto.
    """
    configuradas = dict((parametros or {}).get('caso_labels') or {})
    equivalencias = {
        'participantes_titulo': 'alternativas_titulo',
        'participante_col': 'alternativa_col',
        'fortalezas_titulo': 'fortaleza_titulo',
        'fortalezas_col': 'fortaleza_col',
    }
    for antigua, nueva in equivalencias.items():
        if configuradas.get(antigua) and not configuradas.get(nueva):
            configuradas[nueva] = configuradas[antigua]
    return {**ETIQUETAS_DATOS_CASO, **configuradas}


def _datos_visibles_caso(simulacion, configuracion_snapshot=None):
    """Datos de apoyo que ve el estudiante para decidir.

    Primero lee las tablas nuevas. Si un caso antiguo aun usa parametros JSON,
    mantiene compatibilidad.
    """
    snapshot = configuracion_snapshot or {}
    caso_snapshot = snapshot.get('caso') or {}
    parametros = caso_snapshot.get('parametros') or simulacion.parametros or {}
    if configuracion_snapshot is not None and 'opciones_caso' in snapshot:
        opciones = snapshot.get('opciones_caso') or []
    else:
        opciones = list(simulacion.opciones_caso.filter(activo=True).order_by('orden', 'nombre'))
    if configuracion_snapshot is not None and 'matriz_caso' in snapshot:
        matriz = snapshot.get('matriz_caso') or []
    else:
        matriz = list(simulacion.matriz_caso.filter(activo=True).order_by('orden', 'criterio'))

    if opciones:
        alternativas = [
            {
                'nombre': item.get('nombre') if isinstance(item, dict) else item.nombre,
                'subtitulo': item.get('subtitulo', '') if isinstance(item, dict) else item.subtitulo,
                'valor': item.get('valor_referencia', '') if isinstance(item, dict) else item.valor_referencia,
                'fortaleza': item.get('fortaleza', '') if isinstance(item, dict) else item.fortaleza,
                'riesgo': item.get('riesgo', '') if isinstance(item, dict) else item.riesgo,
                'resultados': (item.get('resultados') or []) if isinstance(item, dict) else (item.resultados or []),
            }
            for item in opciones
        ]
    else:
        alternativas = []
        for item in parametros.get('candidatos', []) or []:
            legado = dict(item or {})
            alternativas.append({
                'nombre': legado.get('nombre', ''),
                'subtitulo': legado.get('subtitulo') or legado.get('experiencia', ''),
                'valor': legado.get('valor_display') or legado.get('salario_pretendido', ''),
                'fortaleza': legado.get('fortaleza') or legado.get('fortalezas', ''),
                'riesgo': legado.get('riesgo') or legado.get('debilidades', ''),
                'resultados': legado.get('resultados') or [],
            })

    if matriz:
        prueba_tecnica = [
            {
                'criterio': item.get('criterio') if isinstance(item, dict) else item.criterio,
                'peso': item.get('peso') if isinstance(item, dict) else item.peso,
                'evalua': item.get('evalua', '') if isinstance(item, dict) else item.evalua,
            }
            for item in matriz
        ]
    else:
        prueba_tecnica = parametros.get('prueba_tecnica', []) or []

    columnas = parametros.get('columnas_resultados', []) or []
    if not columnas and alternativas:
        for item in alternativas:
            resultados = item.get('resultados') or []
            if resultados:
                columnas = [str(r.get('criterio') or '') for r in resultados]
                break

    return {
        'alternativas_caso': alternativas,
        # Alias temporal para integraciones externas que aun consuman la clave.
        'candidatos': alternativas,
        'prueba_tecnica': prueba_tecnica,
        'caso_labels': _etiquetas_datos_caso(parametros),
        'columnas_resultados': columnas,
    }


def _rubrica_visible(intento, numero):
    conceptos = obtener_conceptos_esperados_ronda(
        intento.simulacion, numero, configuracion_snapshot=intento.configuracion_snapshot,
    )
    indicadores = _indicadores_del_intento(intento)[:5]
    restricciones_datos = (intento.configuracion_snapshot or {}).get('restricciones') or []
    restricciones = (
        [SimpleNamespace(**item) for item in restricciones_datos[:5]]
        if restricciones_datos else
        list(intento.simulacion.restricciones.filter(activo=True).order_by('codigo_indicador')[:5])
    )
    # Los criterios del caso con su peso: es la "rubrica rapida" que traen los
    # simuladores del docente (Planificacion 20, Analisis 25...). El estudiante
    # tiene que saber contra que se lo mide ANTES de responder.
    criterios_caso = list(
        intento.simulacion.criterios.filter(activo=True).order_by('-peso', 'nombre')
    )
    if not conceptos and not indicadores and not restricciones and not criterios_caso:
        return None
    return {
        'conceptos': conceptos[:5],
        'indicadores': indicadores,
        'restricciones': restricciones,
        'criterios_caso': criterios_caso,
        # Los criterios del metodo del caso valen nota de verdad, asi que el
        # estudiante debe verlos antes de responder, no descubrirlos despues.
        'criterios_decision': CRITERIOS_DECISION,
        'peso_decision': (_caso_del_intento(intento).get('peso_rubrica_decision')
                          or intento.simulacion.peso_rubrica_decision),
        'formato': [
            'Decisión concreta',
            'Evidencia del caso',
            'Indicador afectado',
            'Consecuencia medible',
            'Trade-off aceptado',
        ],
    }


def _calidad_metacognitiva(intento):
    pasos = list(intento.pasos.filter(es_valido=True).order_by('numero'))
    if not pasos:
        return None
    parametros = (_caso_del_intento(intento).get('parametros') or {})
    esperadas = {
        clave: {
            p.numero for p in pasos
            if _visibilidad_ronda(intento.simulacion, p.numero, parametros).get(clave)
        }
        for clave in ('pedir_reflexion', 'pedir_pronostico', 'pedir_tradeoff')
    }
    rondas_cfg = parametros.get('rondas') or []
    for clave, tiene_evidencia in (
        ('pedir_reflexion', any((p.reflexion or '').strip() for p in pasos)),
        ('pedir_pronostico', any(p.pronostico_indicador for p in pasos)),
        ('pedir_tradeoff', any(p.tradeoff_aceptado for p in pasos)),
    ):
        explicita = any(isinstance(r, dict) and clave in r for r in rondas_cfg)
        if not explicita and tiene_evidencia:
            esperadas[clave] = {p.numero for p in pasos}
    total = len(pasos)
    reflexiones = sum(1 for p in pasos if p.reflexion)
    pronosticos = sum(1 for p in pasos if p.pronostico_indicador)
    pronosticos_acertados = sum(1 for p in pasos if (p.pronostico_resultado or {}).get('estado') == 'acierto')
    tradeoffs = sum(1 for p in pasos if p.tradeoff_aceptado)
    tradeoffs_reales = sum(1 for p in pasos if (p.tradeoff_resultado or {}).get('estado') == 'tradeoff_real')
    componentes = []
    if esperadas['pedir_reflexion']:
        componentes.append(sum(1 for p in pasos if p.numero in esperadas['pedir_reflexion'] and p.reflexion) / len(esperadas['pedir_reflexion']) * 100)
    if esperadas['pedir_pronostico']:
        componentes.append(sum(1 for p in pasos if p.numero in esperadas['pedir_pronostico'] and (p.pronostico_resultado or {}).get('estado') == 'acierto') / len(esperadas['pedir_pronostico']) * 100)
    if esperadas['pedir_tradeoff']:
        componentes.append(sum(1 for p in pasos if p.numero in esperadas['pedir_tradeoff'] and p.tradeoff_aceptado) / len(esperadas['pedir_tradeoff']) * 100)
    puntaje = round(sum(componentes) / len(componentes), 1) if componentes else None
    if puntaje is None:
        nivel = 'No solicitado'
    elif puntaje >= 80:
        nivel = 'Fuerte'
    elif puntaje >= 55:
        nivel = 'En desarrollo'
    else:
        nivel = 'Inicial'
    recomendaciones = []
    if esperadas['pedir_reflexion'] and reflexiones < len(esperadas['pedir_reflexion']):
        recomendaciones.append('Completa la reflexion en la ronda que la solicita.')
    if esperadas['pedir_pronostico'] and pronosticos_acertados < len(esperadas['pedir_pronostico']):
        recomendaciones.append('Antes de decidir, revisa mejor la direccion optima de cada indicador.')
    if esperadas['pedir_tradeoff'] and tradeoffs < len(esperadas['pedir_tradeoff']):
        recomendaciones.append('Explicita el costo o riesgo solo en la ronda que lo solicita.')
    if componentes and not recomendaciones:
        recomendaciones.append('Sigue usando evidencia, pronostico y trade-off para justificar tus decisiones.')
    return {
        'puntaje': puntaje,
        'nivel': nivel,
        'reflexiones': reflexiones,
        'total': total,
        'pronosticos': pronosticos,
        'pronosticos_acertados': pronosticos_acertados,
        'tradeoffs': tradeoffs,
        'tradeoffs_reales': tradeoffs_reales,
        'reflexiones_esperadas': len(esperadas['pedir_reflexion']),
        'pronosticos_esperados': len(esperadas['pedir_pronostico']),
        'tradeoffs_esperados': len(esperadas['pedir_tradeoff']),
        'solicitada': bool(componentes),
        'recomendaciones': recomendaciones,
    }


def _casos_equivalentes(intento, usuario, limite=3):
    """Casos para transferir el mismo aprendizaje a otro contexto."""
    sim = intento.simulacion
    ra_ids = set(
        sim.conceptos_esperados.filter(
            activo=True, resultado_aprendizaje__isnull=False,
        ).values_list('resultado_aprendizaje_id', flat=True)
    )
    completadas = set(
        usuario.intentos_simulacion.filter(finalizado=True, activo=True)
        .values_list('simulacion_id', flat=True)
    )
    candidatos = list(
        Simulacion.objects.filter(
            estado=Simulacion.PUBLICADA,
            activo=True,
            materia_malla=sim.materia_malla,
        )
        .exclude(pk=sim.pk)
        .select_related('materia_malla__materia')
        .prefetch_related('conceptos_esperados')
    )
    sugerencias = []
    for candidato in candidatos:
        candidato_ra = set(
            c.resultado_aprendizaje_id
            for c in candidato.conceptos_esperados.all()
            if c.activo and c.resultado_aprendizaje_id
        )
        compartidos = len(ra_ids & candidato_ra)
        score = compartidos * 3
        if candidato.pk not in completadas:
            score += 2
        if (sim.tema or '') and (candidato.tema or '') and sim.tema.lower() == candidato.tema.lower():
            score += 1
        if score <= 0 and candidato.materia_malla_id == sim.materia_malla_id:
            score = 1
        sugerencias.append({
            'simulacion': candidato,
            'score': score,
            'compartidos': compartidos,
            'completada': candidato.pk in completadas,
        })
    sugerencias.sort(key=lambda s: (s['score'], not s['completada'], s['simulacion'].titulo), reverse=True)
    return [s for s in sugerencias if s['score'] > 0][:limite]


def _costo_accion_legible(simulacion, costo):
    recursos = {
        recurso.codigo: f'{recurso.nombre} ({recurso.unidad})' if recurso.unidad else recurso.nombre
        for recurso in simulacion.recursos.filter(activo=True)
    }
    return [
        (recursos.get(codigo, codigo), valor)
        for codigo, valor in (costo or {}).items()
        if isinstance(valor, (int, float)) and float(valor) != 0
    ]


def _comparacion_reintento(intento):
    origen = intento.intento_origen
    if not origen:
        return None
    delta = None
    if intento.finalizado and origen.finalizado:
        delta = round(float(intento.puntuacion_final) - float(origen.puntuacion_final), 2)
    indicadores_cfg = {
        ind.codigo: ind
        for ind in intento.simulacion.indicadores.filter(activo=True)
    }
    indicadores = []
    for codigo, ind in indicadores_cfg.items():
        anterior = (origen.estado_actual or {}).get(codigo)
        actual = (intento.estado_actual or {}).get(codigo)
        if not isinstance(anterior, (int, float)) or not isinstance(actual, (int, float)):
            continue
        cambio = round(float(actual) - float(anterior), 2)
        if cambio == 0:
            continue
        mejora = (
            cambio > 0 if ind.direccion_optima == ind.DIRECCION_ALTO
            else cambio < 0
        )
        indicadores.append({
            'codigo': codigo,
            'nombre': ind.nombre or codigo,
            'anterior': round(float(anterior), 2),
            'actual': round(float(actual), 2),
            'cambio': cambio,
            'mejora': mejora,
        })

    pasos_origen = list(origen.pasos.all())
    pasos_actual = list(intento.pasos.all())
    invalidos_origen = sum(1 for p in pasos_origen if not p.es_valido)
    invalidos_actual = sum(1 for p in pasos_actual if not p.es_valido)
    reflexiones_origen = sum(1 for p in pasos_origen if p.reflexion)
    reflexiones_actual = sum(1 for p in pasos_actual if p.reflexion)
    pronosticos_origen = sum(1 for p in pasos_origen if (p.pronostico_resultado or {}).get('estado') == 'acierto')
    pronosticos_actual = sum(1 for p in pasos_actual if (p.pronostico_resultado or {}).get('estado') == 'acierto')
    tradeoffs_origen = sum(1 for p in pasos_origen if p.tradeoff_aceptado)
    tradeoffs_actual = sum(1 for p in pasos_actual if p.tradeoff_aceptado)

    senales = []
    if delta is not None and delta > 0:
        senales.append(f'Subiste {delta} puntos frente al intento anterior.')
    elif delta is not None and delta < 0:
        senales.append(f'Bajaste {abs(delta)} puntos; revisa que cambio en tu estrategia.')
    if invalidos_actual < invalidos_origen:
        senales.append('Redujiste respuestas invalidas.')
    if reflexiones_actual > reflexiones_origen:
        senales.append('Aumentaste tus reflexiones despues de decidir.')
    if pronosticos_actual > pronosticos_origen:
        senales.append('Mejoraste la precision de tus pronosticos.')
    if tradeoffs_actual > tradeoffs_origen:
        senales.append('Reconociste mas trade-offs antes de actuar.')
    mejoras_ind = [i for i in indicadores if i['mejora']]
    deterioros_ind = [i for i in indicadores if not i['mejora']]
    if mejoras_ind:
        senales.append('Mejoraste indicadores clave: ' + ', '.join(i['nombre'] for i in mejoras_ind[:3]) + '.')
    if deterioros_ind:
        senales.append('Aun debes cuidar: ' + ', '.join(i['nombre'] for i in deterioros_ind[:3]) + '.')

    return {
        'origen': origen,
        'delta_puntaje': delta,
        'mejoro': delta is not None and delta > 0,
        'indicadores': indicadores,
        'mejoras_indicadores': mejoras_ind,
        'deterioros_indicadores': deterioros_ind,
        'invalidos_origen': invalidos_origen,
        'invalidos_actual': invalidos_actual,
        'reflexiones_origen': reflexiones_origen,
        'reflexiones_actual': reflexiones_actual,
        'pronosticos_origen': pronosticos_origen,
        'pronosticos_actual': pronosticos_actual,
        'tradeoffs_origen': tradeoffs_origen,
        'tradeoffs_actual': tradeoffs_actual,
        'senales': senales,
    }


def _crear_pista_tutor(intento):
    from simulador.models import PistaTutor

    numero = intento.numero_ronda_actual
    andamiaje = _andamiaje_adaptativo(intento)
    conceptos = obtener_conceptos_esperados_ronda(
        intento.simulacion, numero, configuracion_snapshot=intento.configuracion_snapshot,
    )
    usados = list(
        intento.pistas_tutor.filter(numero_ronda=numero).values_list('conceptos_referidos', flat=True)
    )
    usados_ids = {str(cid) for grupo in usados for cid in (grupo or [])}
    concepto = next((c for c in conceptos if str(c.pk) not in usados_ids), None)
    if not concepto and conceptos:
        concepto = conceptos[0]
    if concepto:
        if andamiaje['nivel'] == 'BAJO':
            pista = f'Piensa en el criterio "{concepto.nombre}": que evidencia del caso confirmaria que tu decision fue buena?'
        elif andamiaje['nivel'] == 'ALTO':
            pista = (
                f'Paso a paso: toma el criterio "{concepto.nombre}", elige un indicador relacionado y explica '
                f'que cambio esperas antes de decidir.'
            )
        else:
            pista = (
                f'Revisa el criterio "{concepto.nombre}". Antes de responder, conecta tu decision '
                f'con un indicador del caso y explica que riesgo reduces o que trade-off aceptas.'
            )
        conceptos_ref = [concepto.pk]
    else:
        if andamiaje['nivel'] == 'BAJO':
            pista = 'Que evidencia verificarias despues de decidir para saber si tu estrategia funciono?'
        else:
            pista = (
                'Antes de responder, identifica un indicador del caso, una restriccion y una consecuencia medible. '
                'Luego justifica por que tu decision mejora el estado sin ignorar sus costos.'
            )
        conceptos_ref = []

    # Tutor IA: intenta una pista socratica real (DeepSeek/OpenAI); si no hay
    # proveedor o falla, se queda con la pista de plantilla de arriba.
    try:
        from simulador.ia_service import generar_pista_ia
        situacion = intento.situacion_actual or intento.simulacion.situacion_inicial or intento.simulacion.contexto
        nombres = [c.nombre for c in conceptos] if conceptos else []
        pista_ia = generar_pista_ia(intento, nombres, situacion, nivel_andamiaje=andamiaje['nivel'])
        if pista_ia:
            pista = pista_ia
    except Exception:
        pass

    return PistaTutor.objects.create(
        intento=intento,
        numero_ronda=numero,
        pista=pista,
        conceptos_referidos=conceptos_ref,
        usuario_creacion=intento.estudiante,
    )


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


def _configuracion_ronda(simulacion, numero, parametros=None):
    """Configuracion de una ronda por su numero, sin imponer una secuencia.

    La posicion se conserva como respaldo para datos antiguos, pero una ronda
    puede llamarse y comportarse como el docente necesite.
    """
    fuente = parametros if isinstance(parametros, dict) else (simulacion.parametros or {})
    rondas = fuente.get('rondas') or []
    for ronda in rondas:
        if isinstance(ronda, dict) and ronda.get('numero') == numero:
            return ronda
    indice = numero - 1
    if 0 <= indice < len(rondas) and isinstance(rondas[indice], dict):
        return rondas[indice]
    return {}


def _pasos_stepper(simulacion, numero_actual, total=None, parametros=None):
    """Recorrido configurado por el docente; el motor no presupone fases."""
    total = total or simulacion.maximo_decisiones or 1
    pasos = []
    for n in range(1, total + 1):
        if n < numero_actual:
            estado = 'hecho'
        elif n == numero_actual:
            estado = 'actual'
        else:
            estado = 'pendiente'
        ronda = _configuracion_ronda(simulacion, n, parametros)
        pasos.append({
            'numero': n,
            'nombre': ronda.get('titulo') or f'Ronda {n}',
            'estado': estado,
        })
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
    retos = (
        user.retos_refuerzo.filter(activo=True, completado=False)
        .select_related('simulacion__materia_malla__materia')
        .order_by('fecha_disponible')[:5]
    )
    mi_posicion = PerfilJuego.objects.filter(xp_total__gt=perfil.xp_total).count() + 1
    return {
        'perfil': perfil,
        'insignias_catalogo': insignias_catalogo,
        'ranking': ranking,
        'historial': historial,
        'retos_refuerzo': retos,
        'ahora': timezone.now(),
        'mi_posicion': mi_posicion,
    }


def _calcular_gamificacion(intento):
    """Capa de juego sobre el resultado: XP, rango con icono, progreso al
    siguiente rango e insignias ganadas, para una experiencia mas motivadora."""
    pasos_validos = list(intento.pasos.filter(es_valido=True).order_by('numero'))
    invalidos = intento.pasos.filter(es_valido=False).count()
    final = float(intento.puntuacion_final or 0)
    xp_total = int(round(sum(float(p.puntaje_paso) for p in pasos_validos)))
    reflexiones = sum(1 for p in pasos_validos if p.reflexion)
    pronosticos = sum(1 for p in pasos_validos if p.pronostico_indicador)
    pronosticos_acertados = sum(
        1 for p in pasos_validos if (p.pronostico_resultado or {}).get('estado') == 'acierto'
    )
    tradeoffs = sum(1 for p in pasos_validos if p.tradeoff_aceptado)

    salud = _salud_indicadores(intento)
    metas = _objetivos_mision(intento)
    todas_metas = bool(metas) and all(item['cumplido'] for item in metas)

    # El rango reconoce el aprendizaje, pero no llama "experto" a quien deja
    # el caso en riesgo o no cumple sus metas principales.
    rangos = [
        (90, 'Maestro', '🏆'),
        (85, 'Experto', '🥇'),
        (70, 'Competente', '🥈'),
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
    if salud is not None and (salud < 70 or not todas_metas) and rango in {'Maestro', 'Experto'}:
        rango, icono, umbral_actual, siguiente_umbral = 'Competente', '🥈', 70, 85
    tramo = max(1, siguiente_umbral - umbral_actual)
    progreso_pct = round(max(0, min(100, (final - umbral_actual) / tramo * 100)), 1)

    # Insignias.
    insignias = []
    parametros = (intento.configuracion_snapshot or {}).get('parametros') or {}
    for p in pasos_validos:
        if float(p.puntaje_paso) >= 80:
            nombre_r = (
                _configuracion_ronda(intento.simulacion, p.numero, parametros).get('titulo')
                or f'Ronda {p.numero}'
            )
            insignias.append({'nombre': f'{nombre_r} certero', 'icono': '🎯'})
    if pasos_validos and invalidos == 0:
        insignias.append({'nombre': 'Sin intentos fallidos', 'icono': '✅'})
    criticos_empeorados = any(
        indicador_mejora(
            ind,
            float(ind.valor_inicial),
            (intento.estado_actual or {}).get(ind.codigo),
        ) is False
        for ind in _indicadores_del_intento(intento)
        if ind.es_critico and isinstance((intento.estado_actual or {}).get(ind.codigo), (int, float))
    )
    if (
        pasos_validos
        and not any(float(p.penalizacion_aplicada) for p in pasos_validos)
        and not criticos_empeorados
        and (salud is None or salud >= 70)
    ):
        insignias.append({'nombre': 'Decisiones sin riesgo', 'icono': '🛡️'})
    if final >= 90 and (salud is None or salud >= 80) and todas_metas:
        insignias.append({'nombre': 'Maestría', 'icono': '🏆'})
    elif final >= 85 and (salud is None or salud >= 70) and todas_metas:
        insignias.append({'nombre': 'Gran desempeño', 'icono': '⭐'})

    # Empresa saneada exige salud suficiente y todas las metas, no solo una nota alta.
    if salud is not None and salud >= 70 and todas_metas:
        insignias.append({'nombre': 'Empresa saneada', 'icono': '🏢'})

    return {
        'xp_total': xp_total,
        'rango': rango,
        'icono': icono,
        'progreso_pct': progreso_pct,
        'siguiente_umbral': siguiente_umbral,
        'insignias': insignias,
        'rondas_validas': len(pasos_validos),
        'reflexiones': reflexiones,
        'pronosticos': pronosticos,
        'pronosticos_acertados': pronosticos_acertados,
        'tradeoffs': tradeoffs,
        'salud': round(salud, 0) if salud is not None else None,
    }


def _salud_indicadores(intento):
    """Salud ponderada 0-100 según dirección y peso configurados."""
    estado = intento.estado_actual or {}
    valores = []
    indicadores_empresa = [
        ind for ind in _indicadores_del_intento(intento)
        if not _es_indicador_academico(ind.codigo)
    ]
    metas = _metas_por_indicador(intento)
    for ind in indicadores_empresa:
        v = estado.get(ind.codigo)
        if not isinstance(v, (int, float)):
            continue
        peso = max(0.0, float(getattr(ind, 'peso_salud', 1) or 0))
        if peso:
            valores.append((_desempeno_con_meta(ind, v, metas.get(ind.codigo)), peso))
    total_peso = sum(peso for _, peso in valores)
    return sum(valor * peso for valor, peso in valores) / total_peso if total_peso else None


def _hud_simulacion(intento):
    """HUD tipo videojuego para la consola del estudiante: XP acumulada, vidas
    (intentos validos restantes en la ronda) y salud de la empresa."""
    pasos_validos = intento.pasos.filter(es_valido=True)
    xp = int(round(sum(float(p.puntaje_paso) for p in pasos_validos)))
    vidas_max = intento.max_intentos_invalidos_por_ronda or 3
    vidas = max(0, vidas_max - intento.intentos_invalidos_actuales)
    salud = _salud_indicadores(intento)
    salud_disponible = salud is not None
    if salud is not None and salud >= 66:
        salud_color = 'success'
    elif salud is not None and salud >= 40:
        salud_color = 'warning'
    else:
        salud_color = 'secondary' if salud is None else 'danger'
    return {
        'xp': xp,
        'vidas': vidas,
        'vidas_max': vidas_max,
        'salud': round(salud) if salud is not None else None,
        'salud_disponible': salud_disponible,
        'salud_color': salud_color,
    }


def _medallas_de_la_ronda(intento, paso):
    """Lo que el estudiante se gano en la ronda que acaba de cerrar.

    El ciclo de recompensa tiene que cerrarse EN EL MOMENTO. Las insignias del
    perfil solo se veian al final, en "Mi carrera": para cuando llegaban, el
    estudiante ya no recordaba que hizo bien. Cada medalla se ancla a algo que
    de verdad hizo, no a haber pulsado el boton.
    """
    if paso is None or not paso.es_valido:
        return []

    nota = float(paso.puntaje_paso)
    medallas = []

    if nota >= 90:
        medallas.append({'icono': '\U0001F3AF', 'nombre': 'Certero',
                         'detalle': f'Cerraste la ronda con {nota:g}.'})
    if not paso.intento.intentos_invalidos_actuales and nota >= 70:
        medallas.append({'icono': '\U0001F9E0', 'nombre': 'A la primera',
                         'detalle': 'Resolviste la ronda sin intentos fallidos.'})

    anterior = (
        intento.pasos.filter(es_valido=True, numero__lt=paso.numero)
        .order_by('-numero').first()
    )
    if anterior and nota - float(anterior.puntaje_paso) >= 20:
        medallas.append({'icono': '\U0001F4C8', 'nombre': 'Remontada',
                         'detalle': 'Subiste 20 puntos o mas frente a la ronda anterior.'})

    if (paso.pronostico_resultado or {}).get('estado') == 'acierto':
        medallas.append({'icono': '\U0001F52E', 'nombre': 'Vidente',
                         'detalle': 'Anticipaste bien como se moveria el indicador.'})
    if (paso.tradeoff_resultado or {}).get('estado') == 'tradeoff_real':
        medallas.append({'icono': '⚖', 'nombre': 'Honesto',
                         'detalle': 'Declaraste el costo de tu decision y se cumplio.'})

    if intento.finalizado:
        medallas.append({'icono': '\U0001F3C1', 'nombre': 'Caso cerrado',
                         'detalle': 'Completaste todas las rondas.'})

    return medallas


def _avance_mision(intento, numero, total):
    """Cuanto llevas de la mision, para la barra del HUD."""
    total = max(1, int(total or 1))
    hechas = intento.pasos.filter(es_valido=True).count()
    return {
        'hechas': hechas,
        'total': total,
        'pct': min(100, round(hechas / total * 100)),
        'ronda': numero,
    }


def _indicadores_finales(intento):
    estado = intento.estado_actual or {}
    indicadores = []
    fuentes = sorted(_indicadores_del_intento(intento), key=lambda item: item.nombre)
    pesos_empresa = {
        ind.codigo: max(0.0, float(getattr(ind, 'peso_salud', 1) or 0))
        for ind in fuentes if not _es_indicador_academico(ind.codigo)
    }
    total_peso = sum(pesos_empresa.values()) or 1
    metas = _metas_por_indicador(intento)
    for ind in fuentes:
        valor = estado.get(ind.codigo)
        if not isinstance(valor, (int, float)):
            continue
        desempeno = _salud_indicadores_item(ind, float(valor), metas.get(ind.codigo))
        peso = pesos_empresa.get(ind.codigo, 0)
        peso_pct = peso / total_peso * 100 if peso else 0
        indicadores.append({
            'codigo': ind.codigo,
            'nombre': ind.nombre,
            'valor': round(float(valor), 2),
            'unidad': ind.unidad,
            'critico': ind.es_critico,
            'desempeno': round(desempeno, 0),
            'peso_relativo': round(peso_pct, 1),
            'aporte_salud': round(desempeno * peso_pct / 100, 1),
            'participa_salud': bool(peso),
            'direccion': getattr(ind, 'direccion_optima', 'ALTO'),
            'direccion_legible': {
                'ALTO': 'más alto es mejor',
                'BAJO': 'más bajo es mejor',
                'OBJETIVO': 'mejor cerca del objetivo',
                'RANGO': 'mejor dentro del rango objetivo',
            }.get(getattr(ind, 'direccion_optima', 'ALTO'), ''),
            'es_academico': _es_indicador_academico(ind.codigo),
        })
    return indicadores


def _salud_indicadores_item(indicador, valor, meta=None):
    return _desempeno_con_meta(indicador, valor, meta)


def _explicacion_resultado(intento):
    puntaje = float(intento.puntuacion_final or 0)
    salud = _salud_indicadores(intento)
    indicadores = _indicadores_finales(intento)
    por_codigo = {item['codigo']: item for item in indicadores}
    objetivos = _objetivos_mision(intento)
    alertas = []
    usados = set()
    # Primero aparecen las metas incumplidas; las críticas tienen prioridad.
    metas_incumplidas = [meta for meta in objetivos if not meta['cumplido']]
    metas_incumplidas.sort(
        key=lambda meta: (
            not bool(por_codigo.get(meta.get('codigo'), {}).get('critico')),
            float(por_codigo.get(meta.get('codigo'), {}).get('desempeno', 100)),
        ),
    )
    for meta in metas_incumplidas:
        item = por_codigo.get(meta.get('codigo'))
        if not item or item['codigo'] in usados:
            continue
        item = dict(item)
        item['mensaje_alerta'] = (
            f"{item['nombre']} quedó en {_valor_legible(item['valor'], item['unidad'])}; "
            f"la meta es {meta['meta']}."
        )
        alertas.append(item)
        usados.add(item['codigo'])
    objetivos_cumplidos = {
        meta.get('codigo') for meta in objetivos if meta.get('cumplido')
    }
    for item_fuente in sorted(
        (
            item for item in indicadores
            if item['participa_salud'] and item['desempeno'] < 70
        ),
        key=lambda item: (not item['critico'], item['desempeno']),
    ):
        if item_fuente['codigo'] in usados or item_fuente['codigo'] in objetivos_cumplidos:
            continue
        item = dict(item_fuente)
        item['mensaje_alerta'] = (
            f"{item['nombre']} quedó en {_valor_legible(item['valor'], item['unidad'])} "
            f"({item['desempeno']:.0f} de 100; {item['direccion_legible']})."
        )
        alertas.append(item)
        usados.add(item['codigo'])
    if salud is None:
        salud = 0
    if puntaje >= 90 and salud < 80:
        texto = (
            'Sacaste buena nota academica porque tu respuesta cumplio la rubrica, '
            'pero la salud del caso no depende solo de la nota: tambien refleja como quedaron los indicadores.'
        )
    else:
        texto = (
            'El puntaje academico mide que tan bien cumpliste la rubrica. '
            'La salud del caso mide como terminaron los indicadores de la situacion.'
        )
    return {
        'texto': texto,
        'alertas': alertas[:4],
    }


def _selecciones_registradas(intento):
    selecciones = []
    for paso in intento.pasos.filter(es_valido=True).order_by('numero'):
        seleccion = (paso.evaluacion_detalle or {}).get('seleccion_registrada')
        if seleccion:
            selecciones.append(seleccion)
    return selecciones


def _modo_ronda(simulacion, numero, hay_acciones, parametros=None):
    """Modo de interaccion de la ronda, PARAMETRIZABLE por el profesor en
    parametros['rondas'][n]['modo']: 'hibrido' (elegir + justificar),
    'elegir' (solo elegir opcion) o 'escribir' (solo texto libre).
    Default 'hibrido'. Si no hay opciones configuradas, cae a 'escribir'."""
    modo = 'hibrido'
    ronda = _configuracion_ronda(simulacion, numero, parametros)
    modo = (ronda.get('modo') or 'hibrido').lower()
    if modo not in ('hibrido', 'elegir', 'escribir'):
        modo = 'hibrido'
    if modo in ('hibrido', 'elegir') and not hay_acciones:
        modo = 'escribir'
    return modo


def _etiquetas_ronda(simulacion, numero, parametros=None):
    """Etiquetas configurables por el profesor: usa etiqueta_decision /
    etiqueta_justificacion definidas en parametros['rondas'][n] si existen;
    si no, usa textos neutrales que no presuponen una fase."""
    ronda = _configuracion_ronda(simulacion, numero, parametros)
    return (
        ronda.get('etiqueta_decision') or 'Tu respuesta',
        ronda.get('etiqueta_justificacion') or 'Explica tu razonamiento',
    )


VISIBILIDAD_RONDA_DEFAULTS = {
    # Elementos centrales de una decision informada.
    'mostrar_objetivos': True,
    'mostrar_rubrica': True,
    'mostrar_datos_caso': True,
    'mostrar_resultados_alternativas': False,
    'mostrar_indicadores': True,
    'mostrar_recursos': True,
    # Herramientas avanzadas: el docente las activa solo cuando aportan.
    'mostrar_investigaciones': False,
    'pedir_pronostico': False,
    'pedir_tradeoff': False,
    'pedir_reflexion': False,
}


def _visibilidad_ronda(simulacion, numero, parametros=None):
    ronda = _configuracion_ronda(simulacion, numero, parametros)
    return {
        clave: bool(ronda.get(clave, por_defecto))
        for clave, por_defecto in VISIBILIDAD_RONDA_DEFAULTS.items()
    }


def _progreso_del_estudiante(usuario, materias):
    """El estado real de cada juego y cada caso de la malla, en 2 consultas.

    Sin esto la pantalla era una lista de titulos: el estudiante no sabia que
    ya habia aprobado, que dejo a medias ni cuanto le falta. El progreso es lo
    que convierte el listado en un tablero de juego.
    """
    ids_juegos, ids_casos = [], []
    for materia in materias:
        ids_juegos.extend(j.pk for j in materia.juegos_disponibles)
        ids_casos.extend(s.pk for s in materia.simulaciones_disponibles)

    mejor_juego = {}
    for intento in IntentoActividadInteractiva.objects.filter(
        estudiante=usuario, actividad_id__in=ids_juegos, completado=True,
    ).order_by('actividad_id', '-porcentaje'):
        actual = mejor_juego.get(intento.actividad_id)
        if actual is None or intento.porcentaje > actual['porcentaje']:
            mejor_juego[intento.actividad_id] = {
                'porcentaje': intento.porcentaje,
                'aprobado': intento.aprobado,
            }

    casos = {}
    for intento in IntentoSimulacion.objects.filter(
        estudiante=usuario, simulacion_id__in=ids_casos, activo=True,
    ).order_by('simulacion_id', '-fecha_inicio'):
        actual = casos.setdefault(intento.simulacion_id, {
            'nota': None, 'en_curso': None, 'ronda': 0,
        })
        if intento.finalizado:
            nota = float(intento.puntuacion_final)
            if actual['nota'] is None or nota > actual['nota']:
                actual['nota'] = nota
        elif actual['en_curso'] is None:
            actual['en_curso'] = intento.pk
            actual['ronda'] = intento.numero_ronda_actual

    return mejor_juego, casos


def _pintar_progreso(materias, mejor_juego, casos):
    """Cuelga el estado de cada pieza y el avance de la materia."""
    for materia in materias:
        hechos = 0
        for juego in materia.juegos_disponibles:
            estado = mejor_juego.get(juego.pk)
            juego.jugado = estado is not None
            juego.aprobado_por_mi = bool(estado and estado['aprobado'])
            juego.mi_porcentaje = estado['porcentaje'] if estado else None
            hechos += int(juego.aprobado_por_mi)
        for caso in materia.simulaciones_disponibles:
            estado = casos.get(caso.pk) or {}
            caso.mi_nota = estado.get('nota')
            caso.mi_intento_en_curso = estado.get('en_curso')
            caso.mi_ronda = estado.get('ronda') or 0
            hechos += int(caso.mi_nota is not None)
        total = len(materia.juegos_disponibles) + len(materia.simulaciones_disponibles)
        materia.piezas_hechas = hechos
        materia.piezas_totales = total
        materia.avance = round(hechos / total * 100) if total else 0
        materia.completa = bool(total) and hechos == total


def _datos_de_la_ronda(ronda_config):
    """Las tablas, la formula y la nota que el docente puso en esta ronda.

    Se normaliza aqui y no en la plantilla para que una ficha mal escrita
    (una tabla sin filas, por ejemplo) no reviente la pantalla del alumno.
    """
    datos = (ronda_config or {}).get('datos') or {}
    if not isinstance(datos, dict):
        return None

    tablas = []
    for bruto in datos.get('tablas') or []:
        if not isinstance(bruto, dict):
            continue
        filas = [f for f in (bruto.get('filas') or []) if isinstance(f, (list, tuple))]
        if not filas:
            continue
        tablas.append({
            'titulo': str(bruto.get('titulo') or ''),
            'columnas': [str(c) for c in (bruto.get('columnas') or [])],
            'filas': [[str(celda) for celda in fila] for fila in filas],
        })

    formula = str(datos.get('formula') or '').strip()
    nota = str(datos.get('nota') or '').strip()
    if not (tablas or formula or nota):
        return None
    return {'tablas': tablas, 'formula': formula, 'nota': nota}


def _modelo_docente_de_la_ronda(simulacion, numero, parametros=None):
    """El desarrollo del docente para una ronda, para comparar despues de
    responderla. Vacio si el docente no lo escribio."""
    if not numero:
        return None
    ronda = _configuracion_ronda(simulacion, numero, parametros)
    modelo = (ronda.get('respuesta_modelo') or '').strip()
    cierre = (ronda.get('retroalimentacion') or '').strip()
    if not (modelo or cierre):
        return None
    return {
        'numero': numero,
        'titulo': ronda.get('titulo') or f'Ronda {numero}',
        'modelo': modelo,
        'cierre': cierre,
    }


def _modelo_docente_completo(intento):
    """Todos los desarrollos del docente, ronda por ronda, para el cierre."""
    parametros = (_caso_del_intento(intento).get('parametros') or {})
    total = int(_caso_del_intento(intento).get('maximo_decisiones')
                or intento.simulacion.maximo_decisiones or 0)
    bloques = []
    for numero in range(1, total + 1):
        bloque = _modelo_docente_de_la_ronda(intento.simulacion, numero, parametros)
        if bloque:
            bloques.append(bloque)
    return bloques


def _archivos_de_la_ronda(simulacion, numero):
    """Los adjuntos del caso: los generales mas los propios de esta ronda."""
    from simulador.models import RecursoSimulacionArchivo

    return list(
        RecursoSimulacionArchivo.objects
        .filter(simulacion=simulacion, activo=True)
        .filter(Q(ronda__isnull=True) | Q(ronda__numero=numero))
        .order_by('ronda__numero', 'orden', 'nombre')
    )


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
            intento_origen = None
            origen_id = request.POST.get('intento_origen_id')
            if origen_id:
                intento_origen = get_object_or_404(
                    IntentoSimulacion,
                    pk=origen_id,
                    estudiante=request.user,
                    simulacion=simulacion,
                    finalizado=True,
                )
            # Si la simulacion esta asignada como tarea del curso del estudiante,
            # se enlaza el intento a la asignacion (para el libro de notas) y se
            # respeta la fecha limite: una tarea cerrada no admite nuevos intentos.
            asignacion = cursos_service.asignacion_para(request.user, simulacion)
            if asignacion and asignacion.cerrada:
                limite = asignacion.fecha_limite.strftime('%d/%m/%Y %H:%M')
                mensaje = f'Esta tarea esta cerrada: la fecha limite ({limite}) ya paso.'
                if _es_ajax(request):
                    return bad_json(mensaje=mensaje)
                messages.error(request, mensaje)
                return HttpResponseRedirect('?action=iniciar&simulacion_id=' + str(simulacion.pk))

            # Los juegos obligatorios del caso son un candado: sin aprobarlos, el
            # estudiante no entra. Es el punto de la preparacion previa.
            pendientes = actividades_pendientes(simulacion, request.user)
            if pendientes:
                nombres = ', '.join(juego.titulo for juego in pendientes)
                mensaje = (
                    f'Antes de entrar al caso tienes que aprobar: {nombres}.'
                )
                if _es_ajax(request):
                    return bad_json(mensaje=mensaje)
                messages.error(request, mensaje)
                return HttpResponseRedirect('?action=iniciar&simulacion_id=' + str(simulacion.pk))

            # Con que periodo se sella el intento: el que el estudiante tiene
            # abierto en su inscripcion. Antes se leia una bandera del periodo
            # (activo_matricula), que ya no existe porque SimutaV2 no lleva
            # matricula: el periodo sale de la malla en la que esta inscrito.
            periodo = _periodo_del_estudiante(request.user)
            escenario_inicial = None
            situacion_actual = simulacion.situacion_inicial or simulacion.contexto
            # Si el docente escribio la ronda 1, esa es la situacion: el
            # contexto general ya se leyo en la portada del caso.
            primera = simulacion.rondas.filter(activo=True, numero=1).first()
            if primera and primera.situacion.strip():
                situacion_actual = primera.situacion
            if simulacion.tipo_simulacion == Simulacion.TIPO_SIN_IA_ARBOL:
                escenario_inicial = obtener_escenario_inicial(simulacion)
                situacion_actual = escenario_inicial.situacion if escenario_inicial else ''
            intento = IntentoSimulacion.objects.create(
                estudiante=request.user,
                simulacion=simulacion,
                intento_origen=intento_origen,
                asignacion=asignacion,
                equipo=cursos_service.equipo_de(request.user, asignacion),
                periodo=periodo,
                estado_actual=construir_estado_inicial(simulacion),
                recursos_actuales=construir_recursos_iniciales(simulacion),
                # Siempre se serializa la version que el estudiante acaba de ver.
                # No se reutiliza un snapshot de publicacion que pudo quedar viejo.
                configuracion_snapshot=serializar_configuracion_simulacion(simulacion),
                escenario_actual=escenario_inicial,
                situacion_actual=situacion_actual,
                numero_ronda_actual=1,
            )
            return _ok_o_redirect(
                request,
                f'?action=simular&intento_id={intento.pk}',
                'Intento iniciado correctamente.',
            )

        elif action == 'reflexionar':
            intento = get_object_or_404(
                IntentoSimulacion.objects.select_related('simulacion'),
                pk=request.POST.get('intento_id'),
                estudiante=request.user,
            )
            paso = get_object_or_404(
                intento.pasos, numero=request.POST.get('numero'),
            )
            texto = (request.POST.get('reflexion') or '').strip()
            if not texto:
                return bad_json(mensaje='Escribe tu reflexion antes de enviarla.')
            paso.reflexion = texto[:2000]
            try:
                from simulador.ia_service import generar_feedback_reflexion
                paso.reflexion_feedback = generar_feedback_reflexion(intento, paso, texto)
            except Exception:
                paso.reflexion_feedback = ''
            paso.save(update_fields=['reflexion', 'reflexion_feedback'])
            mensaje = paso.reflexion_feedback or 'Reflexion guardada. Buen habito: pensar el porque de cada decision.'
            if _es_ajax(request):
                return ok_json(data={'feedback': paso.reflexion_feedback}, mensaje=mensaje)
            messages.info(request, mensaje)
            return HttpResponseRedirect(f'?action=simular&intento_id={intento.pk}')

        elif action == 'investigar':
            intento = get_object_or_404(
                IntentoSimulacion.objects.select_related('simulacion'),
                pk=request.POST.get('intento_id'),
                estudiante=request.user,
                finalizado=False,
            )
            investigacion = _investigacion_del_intento(
                intento, request.POST.get('investigacion_id'),
            )
            if investigacion is None:
                return bad_json(mensaje='La averiguacion no pertenece a este intento o no esta disponible.')
            resultado = comprar_investigacion(intento, investigacion)
            if not resultado['ok']:
                if _es_ajax(request):
                    return bad_json(mensaje=resultado['mensaje'])
                messages.error(request, resultado['mensaje'])
                return HttpResponseRedirect(f'?action=simular&intento_id={intento.pk}')
            if _es_ajax(request):
                return ok_json(
                    data={'hallazgo': resultado['hallazgo'], 'recursos': resultado['recursos']},
                    mensaje=resultado['mensaje'],
                )
            messages.info(request, resultado['hallazgo'])
            return HttpResponseRedirect(f'?action=simular&intento_id={intento.pk}')

        elif action == 'pedir_pista':
            intento = get_object_or_404(
                IntentoSimulacion.objects.select_related('simulacion'),
                pk=request.POST.get('intento_id'),
                estudiante=request.user,
                finalizado=False,
            )
            pista = _crear_pista_tutor(intento)
            if _es_ajax(request):
                return ok_json(data={'pista': pista.pista}, mensaje='Pista generada.')
            messages.info(request, pista.pista)
            return HttpResponseRedirect(f'?action=simular&intento_id={intento.pk}')

        elif action == 'completar_reto':
            from simulador.models import RetoRefuerzo
            reto = get_object_or_404(
                RetoRefuerzo,
                pk=request.POST.get('reto_id'),
                estudiante=request.user,
                completado=False,
                activo=True,
            )
            if reto.fecha_disponible > timezone.now():
                return bad_json(mensaje='Este reto aun no esta disponible.')
            respuesta = (request.POST.get('respuesta') or '').strip()
            if len(respuesta) < 40:
                return bad_json(mensaje='Responde con una decision, un indicador y un trade-off.')
            texto = respuesta.lower()
            senales = sum(
                1 for palabra in ['indicador', 'medir', 'trade-off', 'costo', 'riesgo', 'decision', 'decisión']
                if palabra in texto
            )
            reto.respuesta = respuesta[:2000]
            reto.feedback = (
                'Buen refuerzo: conectaste la decision con evidencia y consecuencias.'
                if senales >= 2 else
                'Reto completado. Para subir calidad, menciona explicitamente indicador, evidencia y trade-off.'
            )
            reto.completado = True
            reto.fecha_completado = timezone.now()
            reto.save(update_fields=['respuesta', 'feedback', 'completado', 'fecha_completado'])
            if _es_ajax(request):
                return ok_json(mensaje=reto.feedback)
            messages.info(request, reto.feedback)
            return HttpResponseRedirect('?action=carrera')

        elif action == 'ejecutar_paso':
            intento = get_object_or_404(
                IntentoSimulacion.objects.select_related('simulacion', 'escenario_actual'),
                pk=request.POST.get('intento_id'),
                estudiante=request.user,
                finalizado=False,
            )
            simulacion = intento.simulacion
            pronostico = _pronostico_desde_post(request)
            tradeoff_aceptado = _tradeoff_desde_post(request)

            # Campos que el docente pidio en esta ronda (una cantidad, varias
            # decisiones a la vez...). Sin campos configurados no cambia nada.
            campos_ronda = campos_decision_ronda(
                simulacion, intento.numero_ronda_actual, intento.configuracion_snapshot,
            )
            valores_campos = {}
            decision_enviada = (request.POST.get('decision') or '').strip()
            if campos_ronda:
                valores_campos = {c['clave']: (request.POST.get(c['clave']) or '').strip()
                                  for c in campos_ronda}
                # En una ronda de calculo, LO QUE CAPTURO ES SU DECISION. Sin
                # esto el estudiante ponia el numero, dejaba vacio el texto
                # libre y el motor le rechazaba la jugada pidiendole "una
                # decision concreta" que la ronda nunca le pidio.
                if not decision_enviada:
                    decision_enviada = '. '.join(
                        f"{campo['etiqueta']}: {valores_campos[campo['clave']]}"
                        f"{' ' + campo['unidad'] if campo.get('unidad') else ''}"
                        for campo in campos_ronda
                        if valores_campos.get(campo['clave'])
                    )
                problemas = validar_campos_decision(campos_ronda, valores_campos)
                if problemas:
                    mensaje = ' '.join(problemas)
                    if _es_ajax(request):
                        return bad_json(mensaje=mensaje)
                    messages.error(request, mensaje)
                    return HttpResponseRedirect(f'?action=simular&intento_id={intento.pk}')
            if simulacion.tipo_simulacion == Simulacion.TIPO_SIN_IA_ARBOL:
                reglas_respuesta = configuracion_respuesta_ronda(
                    simulacion, intento.numero_ronda_actual, intento.configuracion_snapshot,
                )
                if reglas_respuesta['pronostico_obligatorio'] and not (
                    pronostico.get('indicador') and pronostico.get('direccion')
                ):
                    return bad_json(
                        mensaje='Selecciona el indicador y la dirección de tu pronóstico.'
                    )
                if reglas_respuesta['tradeoff_obligatorio'] and len(tradeoff_aceptado) < 8:
                    return bad_json(
                        mensaje='Explica brevemente qué costo, riesgo o sacrificio aceptas.'
                    )
                if not intento.escenario_actual:
                    return bad_json(mensaje='La simulacion no tiene un escenario actual configurado.')
                decision = get_object_or_404(
                    intento.escenario_actual.decisiones,
                    pk=request.POST.get('decision_id'),
                    activo=True,
                )
                paso = ejecutar_decision_arbol(
                    intento, decision, pronostico=pronostico, tradeoff_aceptado=tradeoff_aceptado,
                )
            else:
                accion = None
                accion_id = request.POST.get('accion_id')
                if accion_id:
                    acciones_congeladas = {
                        str(item.pk): item for item in _acciones_del_intento(intento, intento.numero_ronda_actual)
                        if item.pk is not None
                    }
                    if acciones_congeladas:
                        accion = acciones_congeladas.get(str(accion_id))
                    else:
                        accion = intento.simulacion.acciones_sugeridas.filter(pk=accion_id, activo=True).first()
                    if accion is None:
                        return bad_json(mensaje='La decision elegida no pertenece a esta version del intento.')
                paso = ejecutar_ronda_ia_dinamica(
                    intento,
                    decision_enviada,
                    request.POST.get('justificacion', ''),
                    accion=accion,
                    pronostico=pronostico,
                    tradeoff_aceptado=tradeoff_aceptado,
                )
            if campos_ronda and paso is not None:
                _aplicar_campos_al_paso(paso, campos_ronda, valores_campos)

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
            data['indicadores_empresa'] = [
                item for item in indicadores if not _es_indicador_academico(item.codigo)
            ]
            data['indicadores_academicos'] = [
                item for item in indicadores if _es_indicador_academico(item.codigo)
            ]
            data['asignacion'] = cursos_service.asignacion_para(request.user, simulacion)
            # Si dejo el caso a medias, se retoma donde quedo. Antes cada
            # regreso a la portada creaba un intento nuevo y el anterior
            # quedaba huerfano "en curso".
            data['intento_en_curso'] = IntentoSimulacion.objects.filter(
                estudiante=request.user,
                simulacion=simulacion,
                finalizado=False,
                activo=True,
            ).order_by('-fecha_inicio').first()
            # La portada avisa que juegos faltan antes de dejar entrar.
            data['juegos_pendientes'] = actividades_pendientes(simulacion, request.user)
            data['juegos_del_caso'] = simulacion.actividades_interactivas.filter(
                publicada=True, activo=True,
            ).order_by('orden', 'pk')
            data['objetivos_mision'] = _objetivos_desde_estado(simulacion, construir_estado_inicial(simulacion))
            data.update(_datos_visibles_caso(simulacion))
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
            data['caso'] = _caso_del_intento(intento)
            # En decisiones independientes manda la ronda configurada; en arbol
            # y en encadenada manda el estado que dejo la decision anterior.
            if intento.simulacion.modo_ejecucion == Simulacion.MODO_CASO_INDEPENDIENTE:
                data['situacion'] = _situacion_actual(intento, numero) or intento.situacion_actual
            else:
                data['situacion'] = intento.situacion_actual or _situacion_actual(intento, numero)
            data['numero'] = numero
            data['form'] = PasoSimulacionForm(ronda=numero)
            parametros_caso = data['caso'].get('parametros') or {}
            data.update(_datos_visibles_caso(intento.simulacion, intento.configuracion_snapshot))
            data['ronda_config'] = _configuracion_ronda(intento.simulacion, numero, parametros_caso)
            data.update(_visibilidad_ronda(intento.simulacion, numero, parametros_caso))
            # Las tablas del caso y sus adjuntos: el Estado de Resultados o el
            # Excel del ejercicio no son decoracion, son con lo que se decide.
            data['datos_ronda'] = _datos_de_la_ronda(data['ronda_config'])
            data['archivos_ronda'] = _archivos_de_la_ronda(intento.simulacion, numero)
            data['rubrica_visible'] = (
                _rubrica_visible(intento, numero) if data['mostrar_rubrica'] else None
            )
            etq_dec, etq_jus = _etiquetas_ronda(intento.simulacion, numero, parametros_caso)
            data['etiqueta_decision'] = etq_dec
            data['etiqueta_justificacion'] = etq_jus
            data['ultimo_paso'] = intento.pasos.order_by('-numero').first()
            # El cierre de los simuladores del docente: despues de responder, el
            # estudiante compara su desarrollo con el modelo. No tiene que ser
            # identico, pero si coherente. Es de la ronda YA respondida.
            data['modelo_docente'] = _modelo_docente_de_la_ronda(
                intento.simulacion,
                data['ultimo_paso'].numero if data['ultimo_paso'] else None,
                parametros_caso,
            )
            data['pedir_reflexion_ultimo'] = bool(
                data['ultimo_paso']
                and _visibilidad_ronda(
                    intento.simulacion, data['ultimo_paso'].numero, parametros_caso,
                )['pedir_reflexion']
            )
            data['reaccion_narrada'] = _reaccion_narrada(data['ultimo_paso'], intento)
            data['objetivos_mision'] = _objetivos_mision(intento) if data['mostrar_objetivos'] else []
            data['andamiaje'] = _andamiaje_adaptativo(intento)
            indicadores_estado = _estado_indicadores(intento)
            data['indicadores_estado'] = indicadores_estado
            data['indicadores_empresa'] = [i for i in indicadores_estado if not i['es_academico']]
            data['indicadores_academicos'] = [i for i in indicadores_estado if i['es_academico']]
            data['cambios_indicadores'] = [i for i in indicadores_estado if i['flecha']]
            data['pronostico_indicadores'] = indicadores_estado if data['pedir_pronostico'] else []
            reglas_respuesta = configuracion_respuesta_ronda(
                intento.simulacion, numero, intento.configuracion_snapshot,
            )
            data['pronostico_obligatorio'] = reglas_respuesta['pronostico_obligatorio']
            data['tradeoff_obligatorio'] = reglas_respuesta['tradeoff_obligatorio']
            data['minimo_justificacion'] = reglas_respuesta['minimo_justificacion']
            data['pedir_tradeoff'] = data['pedir_tradeoff'] and bool(
                indicadores_estado or _recursos_del_intento(intento)
            )
            data['investigaciones'] = (
                investigaciones_disponibles(intento) if data['mostrar_investigaciones'] else []
            )
            if intento.simulacion.tipo_simulacion == Simulacion.TIPO_SIN_IA_ARBOL:
                data['escenario'] = intento.escenario_actual
                data['decisiones'] = intento.escenario_actual.decisiones.filter(activo=True) if intento.escenario_actual else []
            else:
                acciones_sugeridas = _acciones_del_intento(intento, numero)
                for accion in acciones_sugeridas:
                    accion.costo_legible = _costo_accion_legible(intento.simulacion, accion.costo_recursos)
                data['acciones_sugeridas'] = acciones_sugeridas
                data['campos_ronda'] = campos_decision_ronda(
                    intento.simulacion, numero, intento.configuracion_snapshot,
                )
                data['modo_ronda'] = _modo_ronda(
                    intento.simulacion, numero, bool(acciones_sugeridas), parametros_caso,
                )
                if justificacion_obligatoria(intento.simulacion, numero, intento.configuracion_snapshot):
                    data['form'].fields['justificacion'].widget.attrs.update({
                        'required': True,
                        'minlength': reglas_respuesta['minimo_justificacion'],
                    })
                    data['justificacion_obligatoria'] = True
                data['recursos_estado'] = _recursos_estado(intento)
                data['pistas_tutor'] = intento.pistas_tutor.filter(numero_ronda=numero)
                data['pasos_stepper'] = _pasos_stepper(
                    intento.simulacion, numero, data['caso'].get('maximo_decisiones'), parametros_caso,
                )
                data['hud'] = _hud_simulacion(intento)
            # El premio se entrega al cerrar la ronda, no al final del caso.
            data['medallas_ronda'] = _medallas_de_la_ronda(intento, data['ultimo_paso'])
            data['avance_mision'] = _avance_mision(
                intento, numero, data['caso'].get('maximo_decisiones'),
            )
            return render(request, 'simulador/alu_simulaciones/simular.html', data)

        elif action == 'resultado':
            intento = get_object_or_404(
                IntentoSimulacion.objects.select_related('simulacion').prefetch_related('pasos'),
                pk=request.GET.get('intento_id'),
                estudiante=request.user,
            )
            data['intento'] = intento
            data['caso'] = _caso_del_intento(intento)
            data['aviso_version'] = (intento.configuracion_snapshot or {}).get('aviso_version', '')
            data['gamificacion'] = _calcular_gamificacion(intento)
            data['objetivos_mision'] = _objetivos_mision(intento)
            data['comparacion_reintento'] = _comparacion_reintento(intento)
            data['indicadores_finales'] = _indicadores_finales(intento)
            data['indicadores_empresa'] = [i for i in data['indicadores_finales'] if not i['es_academico']]
            data['indicadores_academicos'] = [i for i in data['indicadores_finales'] if i['es_academico']]
            data['explicacion_resultado'] = _explicacion_resultado(intento)
            data['selecciones_registradas'] = _selecciones_registradas(intento)
            data['calidad_metacognitiva'] = _calidad_metacognitiva(intento)
            data['bonificaciones'] = calcular_bonificaciones(intento)
            data['peso_resultado'] = intento.simulacion.peso_resultado
            data['resultado_caso'] = (
                resultado_del_caso(intento) if intento.simulacion.peso_resultado else None
            )
            data['casos_equivalentes'] = _casos_equivalentes(intento, request.user)
            # El cierre del caso: el desarrollo completo del docente, ronda por
            # ronda, para comparar. No tiene que coincidir palabra por palabra;
            # tiene que ser coherente.
            data['modelo_docente_completo'] = _modelo_docente_completo(intento)
            data['criterios_caso'] = list(
                intento.simulacion.criterios.filter(activo=True).order_by('-peso', 'nombre')
            )
            return render(request, 'simulador/alu_simulaciones/resultado.html', data)

        elif action == 'carrera':
            data.update(_carrera_contexto(request.user))
            # Para volver a la malla desde la que se abrio, no al selector.
            malla_volver = request.GET.get('malla') or ''
            data['malla_volver'] = malla_volver if malla_volver.isdigit() else ''
            return render(request, 'simulador/alu_simulaciones/carrera.html', data)

        from academico.models import Malla
        inscripciones = InscripcionMalla.objects.filter(
            estudiante=request.user,
            estado=InscripcionMalla.ACTIVA,
        ).select_related('malla_periodo__malla')
        mallas_ids = list(inscripciones.values_list('malla_periodo__malla_id', flat=True))
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
        #
        # Cada materia trae sus dos bloques por separado:
        #   JUEGOS           -> ActividadInteractiva (aprender y reforzar)
        #   PRACTICAS REALES -> Simulacion + ActividadMateria (aplicar y decidir)
        #
        # Estaban mezclados y el estudiante no distinguia "jugar un memoria" de
        # "resolver un caso de tres rondas", que son dos cosas distintas.
        materias = (
            MateriaMalla.objects
            .filter(malla_id=malla_sel, malla_id__in=mallas_ids, activo=True)
            .select_related('materia', 'nivel', 'malla__carrera')
            .prefetch_related(
                Prefetch(
                    'simulaciones',
                    queryset=Simulacion.objects.filter(
                        activo=True, estado=Simulacion.PUBLICADA,
                    ).select_related('tema_materia').order_by('tema_materia__orden', 'titulo'),
                    to_attr='simulaciones_disponibles',
                ),
                Prefetch(
                    'actividades_interactivas',
                    queryset=ActividadInteractiva.objects.filter(
                        activo=True, publicada=True,
                    ).select_related('tema').order_by('tema__orden', 'orden', 'titulo'),
                    to_attr='juegos_disponibles',
                ),
                Prefetch(
                    'actividades',
                    queryset=ActividadMateria.objects.filter(
                        activo=True,
                    ).select_related('tema').order_by('tema__orden', 'orden', 'titulo'),
                    to_attr='trabajos_disponibles',
                ),
            )
            .order_by('nivel__numero', 'orden', 'materia__nombre')
        )
        materias = list(materias)
        data['malla_sel'] = materias[0].malla if materias else None
        # El estado real de cada pieza: que aprobo, que dejo a medias y cuanto
        # le falta. Es lo que hace que la pantalla sea un tablero y no un indice.
        mejor_juego, casos_jugados = _progreso_del_estudiante(request.user, materias)
        _pintar_progreso(materias, mejor_juego, casos_jugados)
        # Agrupar por nivel en orden (primero -> ultimo) para el dashboard.
        niveles = OrderedDict()
        total_simulaciones = 0
        total_juegos = 0
        for m in materias:
            total_simulaciones += len(m.simulaciones_disponibles)
            total_juegos += len(m.juegos_disponibles)
            m.total_juegos = len(m.juegos_disponibles)
            m.total_practicas = len(m.simulaciones_disponibles) + len(m.trabajos_disponibles)
            numero = m.nivel.numero if m.nivel else 0
            if numero not in niveles:
                niveles[numero] = {
                    'numero': numero,
                    'nombre': m.nivel.nombre if m.nivel else 'Sin nivel',
                    'materias': [],
                    'total_simulaciones': 0,
                }
            niveles[numero]['materias'].append(m)
            niveles[numero]['total_simulaciones'] += len(m.simulaciones_disponibles)
        data['niveles'] = list(niveles.values())
        data['total_simulaciones'] = total_simulaciones
        data['total_juegos'] = total_juegos
        data['total_materias'] = len(materias)
        # Marcador de la malla: cuanto lleva hecho de todo lo que hay.
        hechas = sum(m.piezas_hechas for m in materias)
        totales = sum(m.piezas_totales for m in materias)
        data['avance_malla'] = round(hechas / totales * 100) if totales else 0
        data['piezas_hechas'] = hechas
        data['piezas_totales'] = totales
        data['perfil_juego'] = PerfilJuego.objects.filter(usuario=request.user).first()
        return render(request, 'simulador/alu_simulaciones/view.html', data)
