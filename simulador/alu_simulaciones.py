from collections import OrderedDict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.db import transaction
from django.http import HttpResponseRedirect
from django.utils import timezone
from django.shortcuts import get_object_or_404, render, redirect
from core.funciones import ok_json, bad_json
from academico.models import InscripcionMalla, MateriaMalla, PeriodoAcademico
from simulador.models import Simulacion, IntentoSimulacion
from simulador import cursos_service
from simulador.forms import PasoSimulacionForm
from simulador.services import (
    CRITERIOS_DECISION,
    calcular_bonificaciones,
    construir_estado_inicial,
    construir_recursos_iniciales,
    ejecutar_decision_arbol,
    ejecutar_ronda_ia_dinamica,
    obtener_escenario_inicial,
    obtener_conceptos_esperados_ronda,
)
from simulador.generator_service import serializar_configuracion_simulacion


def _pronostico_desde_post(request):
    return {
        'indicador': request.POST.get('pronostico_indicador', ''),
        'direccion': request.POST.get('pronostico_direccion', ''),
        'justificacion': request.POST.get('pronostico_justificacion', ''),
    }


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
    return 100 if valor == objetivo else 0


def _reaccion_narrada(paso, simulacion):
    """Narra la reaccion de la empresa como una breve historia, a partir de los
    cambios REALES de indicadores. Sin IA: instantaneo, robusto y emotivo. Le da
    'alma' a las consecuencias (lo que la ciencia de serious games llama feedback
    emocional) sin pedirle nada extra al estudiante."""
    if not paso or not paso.es_valido:
        return ''
    antes = paso.estado_antes or {}
    despues = paso.estado_despues or {}
    inds = {i.codigo: i for i in simulacion.indicadores.filter(activo=True)}
    mejoras, deterioros = [], []
    for cod, ind in inds.items():
        va, vd = antes.get(cod), despues.get(cod)
        if not isinstance(va, (int, float)) or not isinstance(vd, (int, float)):
            continue
        delta = float(vd) - float(va)
        if abs(delta) < 0.05:
            continue
        es_bajo = ind.direccion_optima == ind.DIRECCION_BAJO
        bueno = (delta < 0) if es_bajo else (delta > 0)
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
            'descripcion': getattr(f, 'descripcion', '') or f'Lleva {ind.nombre} a {f.operador} {objetivo:g}',
            'indicador': ind.nombre,
            'meta': f'{f.operador} {objetivo:g} {ind.unidad}'.strip(),
            'valor_actual': round(float(valor), 1),
            'cumplido': pct >= 100,
            'progreso_pct': pct,
        })
    return objetivos


def _objetivos_mision(intento):
    return _objetivos_desde_estado(intento.simulacion, intento.estado_actual)


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


def _recursos_estado(intento):
    recursos_actuales = intento.recursos_actuales or {}
    items = []
    for recurso in intento.simulacion.recursos.filter(activo=True):
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


def _datos_visibles_caso(simulacion):
    """Datos de apoyo que ve el estudiante para decidir.

    Primero lee las tablas nuevas. Si un caso antiguo aun usa parametros JSON,
    mantiene compatibilidad.
    """
    opciones = list(simulacion.opciones_caso.filter(activo=True).order_by('orden', 'nombre'))
    matriz = list(simulacion.matriz_caso.filter(activo=True).order_by('orden', 'criterio'))
    parametros = simulacion.parametros or {}

    if opciones:
        candidatos = [
            {
                'nombre': item.nombre,
                'experiencia': item.subtitulo,
                'salario_pretendido': item.valor_referencia,
                'valor_display': item.valor_referencia,
                'fortalezas': item.fortaleza,
                'debilidades': item.riesgo,
                'resultados': item.resultados or [],
            }
            for item in opciones
        ]
    else:
        candidatos = []
        for item in parametros.get('candidatos', []) or []:
            normalizado = dict(item or {})
            normalizado['valor_display'] = normalizado.get('valor_display') or normalizado.get('salario_pretendido', '')
            candidatos.append(normalizado)

    if matriz:
        prueba_tecnica = [
            {'criterio': item.criterio, 'peso': item.peso, 'evalua': item.evalua}
            for item in matriz
        ]
    else:
        prueba_tecnica = parametros.get('prueba_tecnica', []) or []

    columnas = parametros.get('columnas_resultados', []) or []
    if not columnas and candidatos:
        for item in candidatos:
            resultados = item.get('resultados') or []
            if resultados:
                columnas = [str(r.get('criterio') or '') for r in resultados]
                break

    return {
        'candidatos': candidatos,
        'prueba_tecnica': prueba_tecnica,
        'caso_labels': parametros.get('caso_labels', {}),
        'columnas_resultados': columnas,
    }


def _rubrica_visible(intento, numero):
    conceptos = obtener_conceptos_esperados_ronda(intento.simulacion, numero)
    indicadores = list(intento.simulacion.indicadores.filter(activo=True).order_by('nombre')[:5])
    restricciones = list(intento.simulacion.restricciones.filter(activo=True).order_by('codigo_indicador')[:5])
    if not conceptos and not indicadores and not restricciones:
        return None
    return {
        'conceptos': conceptos[:5],
        'indicadores': indicadores,
        'restricciones': restricciones,
        # Los criterios del metodo del caso valen nota de verdad, asi que el
        # estudiante debe verlos antes de responder, no descubrirlos despues.
        'criterios_decision': CRITERIOS_DECISION,
        'peso_decision': intento.simulacion.peso_rubrica_decision,
        'formato': [
            'Decisión concreta',
            'Evidencia del caso',
            'Indicador afectado',
            'Consecuencia medible',
            'Trade-off aceptado',
        ],
    }


def _calidad_metacognitiva(intento):
    pasos = list(intento.pasos.order_by('numero'))
    if not pasos:
        return None
    total = len(pasos)
    reflexiones = sum(1 for p in pasos if p.reflexion)
    pronosticos = sum(1 for p in pasos if p.pronostico_indicador)
    pronosticos_acertados = sum(1 for p in pasos if (p.pronostico_resultado or {}).get('estado') == 'acierto')
    tradeoffs = sum(1 for p in pasos if p.tradeoff_aceptado)
    tradeoffs_reales = sum(1 for p in pasos if (p.tradeoff_resultado or {}).get('estado') == 'tradeoff_real')
    puntaje = 0
    if total:
        puntaje += reflexiones / total * 35
        puntaje += (pronosticos_acertados / max(1, pronosticos)) * 30 if pronosticos else 0
        puntaje += tradeoffs / total * 20
        puntaje += tradeoffs_reales / max(1, tradeoffs) * 15 if tradeoffs else 0
    puntaje = round(min(100, puntaje), 1)
    if puntaje >= 80:
        nivel = 'Fuerte'
    elif puntaje >= 55:
        nivel = 'En desarrollo'
    else:
        nivel = 'Inicial'
    recomendaciones = []
    if reflexiones < total:
        recomendaciones.append('Completa la reflexion despues de cada decision.')
    if pronosticos and pronosticos_acertados < pronosticos:
        recomendaciones.append('Antes de decidir, revisa mejor la direccion optima de cada indicador.')
    if tradeoffs < total:
        recomendaciones.append('Explicita que costo o riesgo aceptas en cada jugada.')
    if not recomendaciones:
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
    conceptos = obtener_conceptos_esperados_ronda(intento.simulacion, numero)
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


def _indicadores_finales(intento):
    estado = intento.estado_actual or {}
    indicadores = []
    for ind in intento.simulacion.indicadores.filter(activo=True).order_by('nombre'):
        valor = estado.get(ind.codigo)
        if not isinstance(valor, (int, float)):
            continue
        desempeno = _salud_indicadores_item(ind, float(valor))
        indicadores.append({
            'codigo': ind.codigo,
            'nombre': ind.nombre,
            'valor': round(float(valor), 2),
            'unidad': ind.unidad,
            'critico': ind.es_critico,
            'desempeno': round(desempeno, 0),
        })
    return indicadores


def _salud_indicadores_item(indicador, valor):
    minimo, maximo = float(indicador.valor_minimo), float(indicador.valor_maximo)
    rango = maximo - minimo or 1
    pct = max(0.0, min(100.0, (float(valor) - minimo) / rango * 100))
    return (100 - pct) if indicador.direccion_optima == indicador.DIRECCION_BAJO else pct


def _explicacion_resultado(intento):
    puntaje = float(intento.puntuacion_final or 0)
    salud = _salud_indicadores(intento)
    indicadores = _indicadores_finales(intento)
    alertas = [i for i in indicadores if i['desempeno'] < 70]
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
        'alertas': alertas[:3],
    }


def _modo_ronda(simulacion, numero, hay_acciones):
    """Modo de interaccion de la ronda, PARAMETRIZABLE por el profesor en
    parametros['rondas'][n]['modo']: 'hibrido' (elegir + justificar),
    'elegir' (solo elegir opcion) o 'escribir' (solo texto libre).
    Default 'hibrido'. Si no hay opciones configuradas, cae a 'escribir'."""
    modo = 'hibrido'
    rondas = (simulacion.parametros or {}).get('rondas') or []
    idx = numero - 1
    if 0 <= idx < len(rondas) and isinstance(rondas[idx], dict):
        modo = (rondas[idx].get('modo') or 'hibrido').lower()
    if modo not in ('hibrido', 'elegir', 'escribir'):
        modo = 'hibrido'
    if modo in ('hibrido', 'elegir') and not hay_acciones:
        modo = 'escribir'
    return modo


def _etiquetas_ronda(simulacion, numero):
    """Etiquetas configurables por el profesor: usa etiqueta_decision /
    etiqueta_justificacion definidas en parametros['rondas'][n] si existen;
    si no, cae a un valor por defecto segun la ronda."""
    defaults = {
        1: ('Diagnóstico', 'Justificación del diagnóstico'),
        2: ('Decisión', 'Justificación de la decisión'),
        3: ('Plan de implementación', 'Justificación, control y seguimiento'),
    }
    dec, jus = defaults.get(numero, ('Decisión', 'Justificación'))
    rondas = (simulacion.parametros or {}).get('rondas') or []
    idx = numero - 1
    if 0 <= idx < len(rondas) and isinstance(rondas[idx], dict):
        dec = rondas[idx].get('etiqueta_decision') or dec
        jus = rondas[idx].get('etiqueta_justificacion') or jus
    return dec, jus


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
            periodo = PeriodoAcademico.objects.filter(activo_matricula=True).first()
            escenario_inicial = None
            situacion_actual = simulacion.situacion_inicial or simulacion.contexto
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
            if simulacion.tipo_simulacion == Simulacion.TIPO_SIN_IA_ARBOL:
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
                    accion = intento.simulacion.acciones_sugeridas.filter(pk=accion_id, activo=True).first()
                paso = ejecutar_ronda_ia_dinamica(
                    intento,
                    request.POST.get('decision', ''),
                    request.POST.get('justificacion', ''),
                    accion=accion,
                    pronostico=pronostico,
                    tradeoff_aceptado=tradeoff_aceptado,
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
            data['asignacion'] = cursos_service.asignacion_para(request.user, simulacion)
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
            data['situacion'] = intento.situacion_actual or _situacion_actual(intento, numero)
            data['numero'] = numero
            data['form'] = PasoSimulacionForm(ronda=numero)
            data.update(_datos_visibles_caso(intento.simulacion))
            data['rubrica_visible'] = _rubrica_visible(intento, numero)
            etq_dec, etq_jus = _etiquetas_ronda(intento.simulacion, numero)
            data['etiqueta_decision'] = etq_dec
            data['etiqueta_justificacion'] = etq_jus
            data['ultimo_paso'] = intento.pasos.order_by('-numero').first()
            data['reaccion_narrada'] = _reaccion_narrada(data['ultimo_paso'], intento.simulacion)
            data['objetivos_mision'] = _objetivos_mision(intento)
            data['andamiaje'] = _andamiaje_adaptativo(intento)
            indicadores_estado = _estado_indicadores(intento)
            data['indicadores_estado'] = indicadores_estado
            data['cambios_indicadores'] = [i for i in indicadores_estado if i['flecha']]
            data['pronostico_indicadores'] = indicadores_estado
            data['pedir_tradeoff'] = bool(indicadores_estado or intento.simulacion.recursos.filter(activo=True).exists())
            if intento.simulacion.tipo_simulacion == Simulacion.TIPO_SIN_IA_ARBOL:
                data['escenario'] = intento.escenario_actual
                data['decisiones'] = intento.escenario_actual.decisiones.filter(activo=True) if intento.escenario_actual else []
            else:
                acciones_sugeridas = list(intento.simulacion.acciones_sugeridas.filter(
                    Q(numero_ronda=numero) | Q(numero_ronda__isnull=True),
                    activo=True,
                ))
                for accion in acciones_sugeridas:
                    accion.costo_legible = _costo_accion_legible(intento.simulacion, accion.costo_recursos)
                data['acciones_sugeridas'] = acciones_sugeridas
                data['modo_ronda'] = _modo_ronda(intento.simulacion, numero, bool(acciones_sugeridas))
                data['recursos_estado'] = _recursos_estado(intento)
                data['pistas_tutor'] = intento.pistas_tutor.filter(numero_ronda=numero)
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
            data['objetivos_mision'] = _objetivos_mision(intento)
            data['comparacion_reintento'] = _comparacion_reintento(intento)
            data['indicadores_finales'] = _indicadores_finales(intento)
            data['explicacion_resultado'] = _explicacion_resultado(intento)
            data['calidad_metacognitiva'] = _calidad_metacognitiva(intento)
            data['bonificaciones'] = calcular_bonificaciones(intento)
            data['casos_equivalentes'] = _casos_equivalentes(intento, request.user)
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
