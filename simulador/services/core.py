import re
import unicodedata
import json
from statistics import mean

from django.utils import timezone


TIPO_ERROR_VACIA = 'VACIA'
TIPO_ERROR_CORTA = 'CORTA'
TIPO_ERROR_BASURA = 'BASURA'
TIPO_ERROR_GENERICA = 'GENERICA'
TIPO_ERROR_SIN_JUSTIFICACION = 'SIN_JUSTIFICACION'
TIPO_ERROR_JUST_BREVE = 'JUST_BREVE'
TIPO_ERROR_OFFTOPIC = 'OFFTOPIC'
TIPO_ERROR_OK = 'OK'

# Solo estos tipos de error invalidan la ronda (no cuenta como intento valido).
# El resto son respuestas validas con un tope de nota (baja calidad, pero avanzan).
TIPOS_ERROR_INVALIDANTES = {TIPO_ERROR_VACIA, TIPO_ERROR_BASURA, TIPO_ERROR_OFFTOPIC}


RESPUESTAS_BASURA = {
    'ddd',
    'dddd',
    'asdf',
    'qwerty',
    'sin',
    'no',
    'nada',
    'no se',
    'nose',
    'ninguna',
}


JUSTIFICACIONES_GENERICAS = {
    'porque si',
    'por experiencia',
    'me parece',
    'esta bien',
    'no tengo mucha idea',
    'creo que si',
}


SINONIMOS = {
    'control': ['control', 'controles', 'controlar', 'controlado', 'controladora', 'controlador'],
    'corregir': ['corregir', 'corregira', 'correccion', 'correctiva', 'correctivas', 'corrige', 'corrigio'],
    'mejora': ['mejora', 'mejorar', 'mejoramiento', 'mejoras', 'mejorado'],
    'indicador': ['indicador', 'indicadores', 'kpi', 'kpis', 'indice', 'indices'],
    'decision': ['decision', 'decisiones', 'decido', 'decidir', 'decida'],
    'gestion': ['gestion', 'gestionar', 'gestionado', 'gestiona'],
    'seguimiento': ['seguimiento', 'monitoreo', 'monitorear', 'dar seguimiento'],
    'auditoria': ['auditoria', 'auditar', 'auditor', 'auditado'],
    'analisis': ['analisis', 'analizar', 'analitico', 'analizado', 'analiza'],
    'viabilidad': ['viabilidad', 'viable', 'factible'],
    'alternativa': ['alternativa', 'alternativas', 'opcion', 'opciones'],
    'riesgo': ['riesgo', 'riesgos', 'riesgoso'],
    'justificacion': ['justificacion', 'justifica', 'justificar', 'justificado'],
}


def _normalizar_texto(texto):
    texto = unicodedata.normalize('NFKD', texto or '')
    texto = texto.encode('ascii', 'ignore').decode('ascii')
    texto = texto.lower().strip()
    texto = re.sub(r'[^a-z0-9\s]', ' ', texto)
    return re.sub(r'\s+', ' ', texto).strip()


def _tokenizar(texto):
    return set(_normalizar_texto(texto).split())


def _expandir_sinonimos(palabra):
    normalizada = _normalizar_texto(palabra)
    yield normalizada
    for variantes in SINONIMOS.values():
        if normalizada in variantes or normalizada == variantes[0]:
            yield from variantes
            return


def _contiene_patron(texto, palabra):
    palabra = _normalizar_texto(palabra)
    if not palabra:
        return False
    tokens = _tokenizar(texto)
    for variante in _expandir_sinonimos(palabra):
        variante_norm = _normalizar_texto(variante)
        if not variante_norm:
            continue
        if any(c in variante_norm for c in [' ', '_', '.']):
            if variante_norm in texto:
                return True
        if variante_norm in tokens:
            return True
        if re.search(rf'\b{re.escape(variante_norm)}\b', texto):
            return True
        # Allow substring match within a token (e.g. "unique" in "uniqueconstraint")
        for token in tokens:
            if variante_norm in token:
                return True
    return False


def parsear_palabras_clave(valor):
    if not valor:
        return []
    if isinstance(valor, list):
        return [str(item).strip() for item in valor if str(item).strip()]
    texto = str(valor).strip()
    try:
        data = json.loads(texto)
        if isinstance(data, list):
            return [str(item).strip() for item in data if str(item).strip()]
    except json.JSONDecodeError:
        pass
    return [item.strip() for item in texto.split(',') if item.strip()]


def parsear_regla_concepto(valor):
    if isinstance(valor, dict):
        return valor
    texto = str(valor or '').strip()
    try:
        data = json.loads(texto)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    return {'any': parsear_palabras_clave(valor)}


def _lista_regla(regla, clave):
    valor = regla.get(clave, [])
    if isinstance(valor, str):
        return [valor]
    if isinstance(valor, list):
        return [str(item).strip() for item in valor if str(item).strip()]
    return []


def evaluar_regla_concepto(texto, palabras_clave):
    regla = parsear_regla_concepto(palabras_clave)
    obligatorias = _lista_regla(regla, 'all')
    alternativas = _lista_regla(regla, 'any')
    prohibidas = _lista_regla(regla, 'none')
    sinonimos = _lista_regla(regla, 'sinonimos')

    obligatorias_detectadas = [p for p in obligatorias if _contiene_patron(texto, p)]
    obligatorias_faltantes = [p for p in obligatorias if p not in obligatorias_detectadas]
    alternativas_detectadas = [p for p in alternativas if _contiene_patron(texto, p)]
    prohibidas_detectadas = [p for p in prohibidas if _contiene_patron(texto, p)]
    sinonimos_detectados = [p for p in sinonimos if _contiene_patron(texto, p)]

    cumple_obligatorias = not obligatorias_faltantes
    cumple_alternativas = bool(alternativas_detectadas) if alternativas else True
    cumple_prohibidas = not prohibidas_detectadas
    cumple = cumple_obligatorias and cumple_alternativas and cumple_prohibidas

    total_requeridas = len(obligatorias) + len(alternativas)
    detectadas_requeridas = len(obligatorias_detectadas) + len(alternativas_detectadas) + len(sinonimos_detectados)
    if total_requeridas > 0:
        factor = detectadas_requeridas / total_requeridas
    elif sinonimos_detectados:
        factor = 0.5
    elif cumple:
        factor = 1.0
    else:
        factor = 0.0

    return {
        'cumple': cumple,
        'factor': round(min(1.0, factor), 2),
        'palabras_detectadas': obligatorias_detectadas + alternativas_detectadas + sinonimos_detectados,
        'obligatorias_faltantes': obligatorias_faltantes,
        'alternativas_faltantes': [] if cumple_alternativas else alternativas,
        'prohibidas_detectadas': prohibidas_detectadas,
        'sinonimos_detectados': sinonimos_detectados,
    }


def calcular_puntaje_justificacion(justificacion):
    validacion = validar_respuesta_estudiante('decision valida', justificacion)
    if validacion['tipo_error'] == TIPO_ERROR_SIN_JUSTIFICACION:
        if not (justificacion or '').strip():
            return 0
        return 2
    if validacion['tipo_error'] == TIPO_ERROR_GENERICA:
        return 2
    texto = _normalizar_texto(justificacion)
    if len(justificacion.strip()) >= 80 and any(
        palabra in texto
        for palabra in ['porque', 'para', 'permite', 'evita', 'garantiza', 'asegura', 'debido', 'ya que']
    ):
        return 10
    return 5


def validar_respuesta_estudiante(decision, justificacion, simulacion=None, situacion_actual=None):
    """Distingue VALIDEZ (cuenta como ronda) de CALIDAD (tope de nota).

    Solo se invalida la ronda cuando la respuesta es inutilizable:
      - decision vacia
      - texto basura / sin sentido / repetitivo
      - respuesta sin ninguna relacion con la situacion (fuera de tema)

    Una respuesta basica pero relacionada SIEMPRE es valida: avanza como ronda
    con una nota baja (tope segun el nivel detectado), nunca se bloquea.
    """
    decision_limpia = (decision or '').strip()
    justificacion_limpia = (justificacion or '').strip()
    decision_normalizada = _normalizar_texto(decision_limpia)
    justificacion_normalizada = _normalizar_texto(justificacion_limpia)
    combinado = f'{decision_limpia} {justificacion_limpia}'.strip()

    # === INVALIDA la ronda (no cuenta) ===
    if not decision_limpia:
        return _resultado_validacion(
            False, 'Debe ingresar una decisión concreta.', 0, TIPO_ERROR_VACIA,
        )

    if (
        decision_normalizada in RESPUESTAS_BASURA
        or justificacion_normalizada in RESPUESTAS_BASURA
        or _es_texto_repetitivo(decision_normalizada)
        or _es_texto_repetitivo(justificacion_normalizada)
    ):
        return _resultado_validacion(
            False, 'La respuesta no contiene una decisión con sentido.', 0, TIPO_ERROR_BASURA,
        )

    if simulacion is not None and _es_fuera_de_tema(combinado, simulacion, situacion_actual):
        return _resultado_validacion(
            False,
            'La respuesta no se relaciona con la situación planteada. Responde al caso de la materia.',
            0,
            TIPO_ERROR_OFFTOPIC,
        )

    # === VALIDA pero con tope de nota (baja calidad, igual avanza) ===
    if len(combinado) < 40 or len(decision_limpia) < 8:
        return _resultado_validacion(
            True, 'Respuesta válida pero muy breve: amplía tu decisión y justificación.',
            40, TIPO_ERROR_CORTA,
        )

    if not justificacion_limpia:
        return _resultado_validacion(
            True, 'Falta justificar la decisión; la nota queda limitada.',
            50, TIPO_ERROR_SIN_JUSTIFICACION,
        )

    if _es_justificacion_generica(justificacion_normalizada):
        return _resultado_validacion(
            True, 'La justificación es genérica; profundiza el razonamiento técnico.',
            60, TIPO_ERROR_GENERICA,
        )

    if len(justificacion_limpia) < 20:
        return _resultado_validacion(
            True, 'La justificación es breve; añade más detalle técnico.',
            70, TIPO_ERROR_JUST_BREVE,
        )

    return _resultado_validacion(
        True, 'Respuesta válida.', 100, TIPO_ERROR_OK,
    )


def _es_fuera_de_tema(texto, simulacion, situacion_actual=None):
    """Heuristica conservadora: solo marca fuera de tema cuando hay un vocabulario
    de referencia razonable y la respuesta no comparte NINGUNA palabra significativa
    con el caso. Pensada para no bloquear respuestas basicas legitimas."""
    vocabulario = _vocabulario_simulacion(simulacion, situacion_actual)
    if len(vocabulario) < 5:
        return False
    tokens_resp = {t for t in _tokenizar(texto) if len(t) > 4}
    if len(tokens_resp) < 3:
        return False
    return tokens_resp.isdisjoint(vocabulario)


def _vocabulario_simulacion(simulacion, situacion_actual=None):
    fuentes = [
        getattr(simulacion, 'titulo', ''),
        getattr(simulacion, 'tema', ''),
        getattr(simulacion, 'contexto', ''),
        getattr(simulacion, 'objetivo', ''),
        getattr(simulacion, 'situacion_inicial', ''),
        situacion_actual or '',
    ]
    try:
        for concepto in simulacion.conceptos_esperados.filter(activo=True):
            fuentes.append(concepto.nombre)
            fuentes.append(concepto.descripcion)
            fuentes.extend(parsear_palabras_clave(concepto.palabras_clave))
    except Exception:
        pass
    vocab = set()
    for fuente in fuentes:
        vocab |= {t for t in _tokenizar(str(fuente)) if len(t) > 4}
    return vocab


def _es_justificacion_generica(texto):
    if texto in JUSTIFICACIONES_GENERICAS:
        return True
    if len(texto) > 60:
        return False
    return any(
        frase in texto
        for frase in JUSTIFICACIONES_GENERICAS
        if frase != 'porque si'
    )


def _resultado_validacion(valida, motivo, puntaje_maximo, tipo_error):
    return {
        'valida': valida,
        'motivo': motivo,
        'puntaje_maximo': puntaje_maximo,
        'tipo_error': tipo_error,
    }


def _es_texto_repetitivo(texto):
    compacto = re.sub(r'[^a-z0-9]', '', texto)
    if len(compacto) >= 3 and len(set(compacto)) == 1:
        return True
    palabras = [p for p in texto.split() if p]
    return len(palabras) >= 3 and len(set(palabras)) == 1


def construir_estado_inicial(simulacion):
    estado = {}
    for indicador in simulacion.indicadores.filter(activo=True):
        estado[indicador.codigo] = float(indicador.valor_inicial)
    return estado


def construir_recursos_iniciales(simulacion):
    recursos = {}
    for recurso in simulacion.recursos.filter(activo=True):
        recursos[recurso.codigo] = float(recurso.valor_inicial)
    return recursos


def aplicar_impacto(estado_actual, impacto):
    estado = dict(estado_actual or {})
    for clave, valor in (impacto or {}).items():
        actual = estado.get(clave, 0)
        if isinstance(actual, (int, float)) and isinstance(valor, (int, float)):
            estado[clave] = actual + valor
        else:
            estado[clave] = valor
    return estado


def limitar_recursos_por_min_max(simulacion, recursos):
    recursos_limitados = dict(recursos or {})
    recursos_cfg = {
        recurso.codigo: recurso
        for recurso in simulacion.recursos.filter(activo=True)
    }
    for codigo, recurso in recursos_cfg.items():
        valor = recursos_limitados.get(codigo)
        if not isinstance(valor, (int, float)):
            continue
        minimo = float(recurso.valor_minimo)
        maximo = float(recurso.valor_maximo)
        recursos_limitados[codigo] = max(minimo, min(maximo, float(valor)))
    return recursos_limitados


def aplicar_costo_recursos(recursos_actuales, costo):
    recursos = dict(recursos_actuales or {})
    for clave, valor in (costo or {}).items():
        if not isinstance(valor, (int, float)):
            continue
        actual = recursos.get(clave, 0)
        if isinstance(actual, (int, float)):
            recursos[clave] = float(actual) - float(valor)
    return recursos


def validar_recursos(simulacion, recursos):
    alertas = []
    for recurso in simulacion.recursos.filter(activo=True):
        valor = recursos.get(recurso.codigo)
        if not isinstance(valor, (int, float)):
            continue
        minimo = float(recurso.valor_minimo)
        if float(valor) <= minimo:
            alertas.append({
                'recurso': recurso.codigo,
                'nombre': recurso.nombre,
                'valor_actual': round(float(valor), 2),
                'minimo': minimo,
                'descripcion': f'{recurso.nombre} se agoto o llego a su minimo.',
            })
    return alertas


def _costos_numericos(costo):
    return {
        clave: float(valor)
        for clave, valor in (costo or {}).items()
        if isinstance(valor, (int, float)) and float(valor) != 0
    }


def detectar_accion_sugerida(simulacion, decision):
    texto = _normalizar_texto(decision)
    if not texto:
        return None
    acciones = simulacion.acciones_sugeridas.filter(activo=True).order_by('numero_ronda', 'texto')
    mejor = None
    mejor_score = 0
    tokens_texto = set(texto.split())
    for accion in acciones:
        accion_norm = _normalizar_texto(accion.texto)
        if not accion_norm:
            continue
        if accion_norm in texto:
            return accion
        tokens_accion = set(accion_norm.split())
        if not tokens_accion:
            continue
        score = len(tokens_texto & tokens_accion) / len(tokens_accion)
        if score > mejor_score:
            mejor = accion
            mejor_score = score
    return mejor if mejor_score >= 0.45 else None


def limitar_estado_por_min_max(simulacion, estado):
    estado_limitado = dict(estado or {})
    indicadores = {
        indicador.codigo: indicador
        for indicador in simulacion.indicadores.filter(activo=True)
    }
    for codigo, indicador in indicadores.items():
        valor = estado_limitado.get(codigo)
        if not isinstance(valor, (int, float)):
            continue
        minimo = float(indicador.valor_minimo)
        maximo = float(indicador.valor_maximo)
        estado_limitado[codigo] = max(minimo, min(maximo, float(valor)))
    return estado_limitado


def validar_impacto(simulacion, impacto):
    codigos = {i.codigo for i in simulacion.indicadores.filter(activo=True)}
    errores = []
    for clave, valor in (impacto or {}).items():
        if clave not in codigos:
            errores.append(f'Indicador "{clave}" no existe en la simulacion')
        elif not isinstance(valor, (int, float)):
            errores.append(f'Valor para "{clave}" debe ser numerico')
    return errores


def obtener_conceptos_esperados_ronda(simulacion, numero_ronda, escenario=None):
    from simulador.models import ConceptoEsperadoRonda

    qs = ConceptoEsperadoRonda.objects.filter(activo=True)
    if escenario:
        qs = qs.filter(escenario=escenario)
    else:
        qs = qs.filter(simulacion=simulacion, escenario__isnull=True)

    conceptos = list(qs.filter(numero_ronda=numero_ronda))
    if not conceptos:
        conceptos = list(qs.filter(numero_ronda__isnull=True))
    return conceptos


def _normalizar_evaluaciones_ia(evaluaciones_ia):
    normalizadas = {}
    for item in evaluaciones_ia or []:
        try:
            concepto_id = int(item.get('concepto_id'))
        except (TypeError, ValueError):
            continue
        factor = item.get('factor', 1 if item.get('cumple') else 0)
        try:
            factor = float(factor)
        except (TypeError, ValueError):
            factor = 0.0
        normalizadas[concepto_id] = {
            'cumple': bool(item.get('cumple')),
            'factor': max(0.0, min(1.0, factor)),
            'evidencia': str(item.get('evidencia') or '').strip(),
            'retroalimentacion': str(item.get('retroalimentacion') or '').strip(),
        }
    return normalizadas


def evaluar_conceptos_esperados(simulacion, numero_ronda, decision, justificacion, situacion_actual, escenario=None, evaluaciones_ia=None):
    texto = _normalizar_texto(f'{decision} {justificacion}')
    conceptos = obtener_conceptos_esperados_ronda(simulacion, numero_ronda, escenario=escenario)
    evaluaciones_ia = _normalizar_evaluaciones_ia(evaluaciones_ia)
    cumplidos = []
    parciales = []
    faltantes = []
    criticos_faltantes = []
    detalles = []
    impacto_total = {}
    puntaje_conceptos = 0
    retro_cumple = []
    retro_falta = []

    for concepto in conceptos:
        regla_fuente = concepto.regla_evaluacion or concepto.palabras_clave
        regla = evaluar_regla_concepto(texto, regla_fuente)
        palabras_detectadas = regla['palabras_detectadas']
        evaluacion_ia = evaluaciones_ia.get(concepto.id)
        if evaluacion_ia:
            cumple = evaluacion_ia['cumple']
            factor = evaluacion_ia['factor']
        else:
            cumple = regla['cumple']
            factor = regla['factor']
        cumple_completo = bool(cumple and factor >= 0.75)
        tiene_evidencia = factor > 0
        puntos = round(float(concepto.peso) * factor, 2)
        impacto_concepto = {}
        if tiene_evidencia:
            if cumple_completo:
                cumplidos.append(concepto)
            else:
                parciales.append(concepto)
            puntaje_conceptos += puntos
            for clave, valor in (concepto.impacto_si_cumple or {}).items():
                if isinstance(valor, (int, float)):
                    impacto_escalado = round(float(valor) * factor, 2)
                    impacto_concepto[clave] = impacto_escalado
                    impacto_total[clave] = impacto_total.get(clave, 0) + impacto_escalado
            if cumple_completo and concepto.retroalimentacion_si_cumple:
                retro_cumple.append(concepto.retroalimentacion_si_cumple)
            elif not cumple_completo:
                retro_falta.append('Evidencia parcial: ' + (concepto.retroalimentacion_si_cumple or ''))
        else:
            faltantes.append(concepto)
            if concepto.es_critico:
                criticos_faltantes.append(concepto)
            for clave, valor in (concepto.impacto_si_falta or {}).items():
                if isinstance(valor, (int, float)):
                    impacto_concepto[clave] = valor
                    impacto_total[clave] = impacto_total.get(clave, 0) + valor
            if concepto.retroalimentacion_si_falta:
                retro_falta.append(concepto.retroalimentacion_si_falta)
        detalles.append({
            'concepto_id': concepto.id,
            'nombre': concepto.nombre,
            'descripcion': concepto.descripcion,
            'cumple': cumple_completo,
            'cumple_ia': cumple,
            'parcial': tiene_evidencia and not cumple_completo,
            'factor_coincidencia': factor,
            'es_critico': concepto.es_critico,
            'puntos_maximos': float(concepto.peso),
            'puntos_obtenidos': puntos,
            'palabras_detectadas': palabras_detectadas,
            'obligatorias_faltantes': regla['obligatorias_faltantes'],
            'alternativas_faltantes': regla['alternativas_faltantes'],
            'prohibidas_detectadas': regla['prohibidas_detectadas'],
            'sinonimos_detectados': regla['sinonimos_detectados'],
            'evidencia_ia': evaluacion_ia.get('evidencia', '') if evaluacion_ia else '',
            'retroalimentacion': _retroalimentacion_concepto(
                concepto,
                cumple,
                evaluacion_ia.get('retroalimentacion', '') if evaluacion_ia else '',
            ),
            'impacto': impacto_concepto,
        })

    errores_impacto = validar_impacto(simulacion, impacto_total)
    if errores_impacto:
        codigos = set(simulacion.indicadores.filter(activo=True).values_list('codigo', flat=True))
        impacto_total = {k: v for k, v in impacto_total.items() if k in codigos}

    puntaje_sin_tope = max(0, min(100, puntaje_conceptos))
    # Critical concepts apply a proportional reduction, not a hard cap to 40
    if criticos_faltantes:
        # If critical concepts are missing but there is evidence, apply a softer penalty
        total_peso_criticos = sum(float(c.peso) for c in conceptos if c.es_critico)
        peso_criticos_faltantes = sum(float(c.peso) for c in criticos_faltantes)
        if total_peso_criticos > 0:
            penalizacion_critica = (peso_criticos_faltantes / total_peso_criticos) * 30
            tope_critico = 100 - penalizacion_critica
        else:
            tope_critico = 70
        puntaje = min(puntaje_sin_tope, tope_critico)
    else:
        tope_critico = None
        puntaje = puntaje_sin_tope

    partes = []
    if cumplidos:
        partes.append('Conceptos cumplidos: ' + ', '.join(c.nombre for c in cumplidos) + '.')
    if parciales:
        partes.append('Evidencia parcial en: ' + ', '.join(c.nombre for c in parciales) + '.')
    if faltantes:
        partes.append('Conceptos faltantes: ' + ', '.join(c.nombre for c in faltantes) + '.')
    if criticos_faltantes:
        partes.append('Advertencia crítica: falta ' + ', '.join(c.nombre for c in criticos_faltantes) + '.')
    resumen_indicadores = _resumen_impacto_indicadores(simulacion, impacto_total)
    if resumen_indicadores:
        partes.append(resumen_indicadores)
    partes.extend(retro_cumple)
    partes.extend(retro_falta)
    if criticos_faltantes:
        partes.append(_recomendacion_por_indicadores(simulacion, criticos_faltantes))
    elif faltantes:
        partes.append(_recomendacion_por_indicadores(simulacion, faltantes))
    else:
        partes.append('Recomendación: la decisión cubre la evidencia esperada y mueve indicadores configurados del caso.')

    return {
        'tiene_conceptos': bool(conceptos),
        'conceptos_cumplidos': [c.nombre for c in cumplidos],
        'conceptos_parciales': [c.nombre for c in parciales],
        'conceptos_faltantes': [c.nombre for c in faltantes],
        'conceptos_criticos_faltantes': [c.nombre for c in criticos_faltantes],
        'detalle_conceptos': detalles,
        'puntaje_conceptos': puntaje_conceptos,
        'puntaje_sin_tope': puntaje_sin_tope,
        'tope_critico': tope_critico,
        'puntaje_sugerido': puntaje,
        'impacto_sugerido': impacto_total,
        'evaluacion': ' '.join(partes),
        'metodo_evaluacion': 'ia_semantica_rubrica' if evaluaciones_ia else 'rubrica_palabras_clave',
    }


def _retroalimentacion_concepto(concepto, cumple, retro_ia=''):
    """Evita retroalimentacion generica: cada comentario debe apuntar al
    concepto configurado por el docente, no a "calidad" abstracta del texto."""
    retro = (retro_ia or '').strip()
    if retro:
        return retro
    if cumple and concepto.retroalimentacion_si_cumple:
        return concepto.retroalimentacion_si_cumple
    if not cumple and concepto.retroalimentacion_si_falta:
        return concepto.retroalimentacion_si_falta
    accion = 'Evidencia suficiente' if cumple else 'Falta evidencia'
    return f'{accion} sobre: {concepto.nombre}.'


def _resumen_impacto_indicadores(simulacion, impacto):
    if not impacto:
        return ''
    indicadores = {
        ind.codigo: ind
        for ind in simulacion.indicadores.filter(activo=True)
    }
    partes = []
    for codigo, delta in (impacto or {}).items():
        ind = indicadores.get(codigo)
        if not ind or not isinstance(delta, (int, float)):
            continue
        es_bajo = ind.direccion_optima == ind.DIRECCION_BAJO
        mejora = (delta < 0) if es_bajo else (delta > 0)
        signo = '+' if delta > 0 else ''
        estado = 'mejora' if mejora else 'empeora'
        partes.append(f'{ind.nombre} {signo}{round(float(delta), 2)} ({estado})')
    if not partes:
        return ''
    return 'Indicadores propios afectados: ' + '; '.join(partes) + '.'


def _recomendacion_por_indicadores(simulacion, conceptos_faltantes):
    criticos = list(simulacion.indicadores.filter(activo=True, es_critico=True).values_list('nombre', flat=True)[:3])
    conceptos = ', '.join(c.nombre for c in conceptos_faltantes[:2])
    if criticos:
        return (
            f'Recomendación: refuerza "{conceptos}" conectándolo con indicadores del caso: '
            f'{", ".join(criticos)}.'
        )
    return f'Recomendación: refuerza "{conceptos}" usando evidencia del caso configurado.'


def validar_restricciones(simulacion, estado):
    alertas = []
    for r in simulacion.restricciones.filter(activo=True):
        valor = estado.get(r.codigo_indicador)
        if valor is None:
            continue
        incumple = False
        if r.operador == '<':
            incumple = not (float(valor) < float(r.valor_limite))
        elif r.operador == '<=':
            incumple = not (float(valor) <= float(r.valor_limite))
        elif r.operador == '>':
            incumple = not (float(valor) > float(r.valor_limite))
        elif r.operador == '>=':
            incumple = not (float(valor) >= float(r.valor_limite))
        elif r.operador == '=':
            incumple = not (float(valor) == float(r.valor_limite))
        if incumple:
            alertas.append({
                'descripcion': r.descripcion,
                'indicador': r.codigo_indicador,
                'operador': r.operador,
                'limite': float(r.valor_limite),
                'valor_actual': float(valor),
                'penalizacion': float(r.penalizacion),
            })
    return alertas


def calcular_penalizaciones(alertas):
    return sum(a.get('penalizacion', 0) for a in alertas)


def validar_condiciones_exito(simulacion, estado):
    cumplidas = []
    bonificacion_total = 0
    for c in simulacion.condiciones_exito.filter(activo=True):
        valor = estado.get(c.codigo_indicador)
        if valor is None:
            continue
        cumple = False
        if c.operador == '<':
            cumple = float(valor) < float(c.valor_objetivo)
        elif c.operador == '<=':
            cumple = float(valor) <= float(c.valor_objetivo)
        elif c.operador == '>':
            cumple = float(valor) > float(c.valor_objetivo)
        elif c.operador == '>=':
            cumple = float(valor) >= float(c.valor_objetivo)
        elif c.operador == '=':
            cumple = float(valor) == float(c.valor_objetivo)
        if cumple:
            cumplidas.append({
                'descripcion': c.descripcion,
                'indicador': c.codigo_indicador,
                'bonificacion': float(c.bonificacion),
            })
            bonificacion_total += float(c.bonificacion)
    return cumplidas, bonificacion_total


# Tope de penalizacion por restricciones en una ronda: nunca debe aplastar la
# nota de calidad. Las restricciones nudgean, no destruyen el puntaje del paso.
PENALIZACION_MAX_PASO = 15


def calcular_puntaje_paso(puntaje_ia_sugerido, penalizacion):
    puntaje = float(puntaje_ia_sugerido) - float(penalizacion)
    return max(0, min(100, puntaje))


def impacto_automatico(simulacion, puntaje, estado_antes=None):
    """La empresa reacciona a la calidad de la decision cuando el docente no
    configuro impactos: una buena decision (puntaje alto) mueve cada indicador
    hacia su direccion optima; una mala lo aleja. Neutral en 50.
    Mueve hasta ~12% del rango por ronda para que se sienta vivo pero gradual."""
    factor = (float(puntaje) - 50.0) / 50.0  # -1 .. +1
    if abs(factor) < 0.05:
        return {}
    estado_antes = estado_antes or {}
    impacto = {}
    for ind in simulacion.indicadores.filter(activo=True):
        rango = float(ind.valor_maximo) - float(ind.valor_minimo)
        if rango <= 0:
            continue
        magnitud = rango * 0.12 * factor
        if ind.direccion_optima == ind.DIRECCION_BAJO:
            magnitud = -magnitud
        magnitud = round(magnitud, 2)
        if magnitud:
            impacto[ind.codigo] = magnitud
    return impacto


def _hubo_movimiento(antes, despues):
    """True si algun indicador cambio entre el estado anterior y el nuevo."""
    antes = antes or {}
    for clave, valor in (despues or {}).items():
        prev = antes.get(clave)
        if isinstance(valor, (int, float)) and isinstance(prev, (int, float)):
            if round(float(valor), 3) != round(float(prev), 3):
                return True
    return False


def _cumple_condicion(estado, cond):
    valor = estado.get(cond.get('indicador'))
    if not isinstance(valor, (int, float)):
        return False
    v, limite = float(valor), float(cond.get('valor', 0))
    op = cond.get('operador', '<')
    return {
        '<': v < limite, '<=': v <= limite, '>': v > limite,
        '>=': v >= limite, '=': v == limite,
    }.get(op, False)


def aplicar_eventos(simulacion, estado_despues, ronda_actual):
    """Fase B - eventos dinamicos.

    Lee eventos desde la tabla EventoSimulacion. Si la simulacion aun no tiene
    eventos en tabla, conserva compatibilidad con simulacion.parametros['eventos']:
    cada evento = {id, ronda?, condicion?{indicador,operador,valor}, mensaje, efecto{codigo:delta}}.
    Se dispara si coincide la ronda (o no se especifica) y se cumple la condicion sobre
    el estado (o no hay), UNA sola vez por intento (se rastrea en estado['__eventos__'])."""
    eventos = []
    try:
        for evento in simulacion.eventos.filter(activo=True).order_by('prioridad', 'ronda', 'nombre'):
            condicion = None
            if evento.codigo_indicador_condicion and evento.valor_condicion is not None:
                condicion = {
                    'indicador': evento.codigo_indicador_condicion,
                    'operador': evento.operador_condicion or '>=',
                    'valor': float(evento.valor_condicion),
                }
            eventos.append({
                'id': f'db:{evento.pk}',
                'ronda': evento.ronda,
                'condicion': condicion,
                'mensaje': evento.mensaje,
                'efecto': evento.efecto or {},
            })
    except Exception:
        eventos = []
    if not eventos:
        for idx, evento_json in enumerate((simulacion.parametros or {}).get('eventos') or []):
            item = dict(evento_json or {})
            item['id'] = f'json:{item.get("id", idx)}'
            eventos.append(item)
    estado = dict(estado_despues or {})
    if not eventos:
        return estado, []
    disparados = list(estado.get('__eventos__', []))
    mensajes = []
    for idx, ev in enumerate(eventos):
        ev_id = str(ev.get('id', idx))
        if ev_id in disparados:
            continue
        ronda_ev = ev.get('ronda')
        if ronda_ev is not None and int(ronda_ev) != int(ronda_actual):
            continue
        cond = ev.get('condicion')
        if cond and not _cumple_condicion(estado, cond):
            continue
        efecto = {k: v for k, v in (ev.get('efecto') or {}).items() if isinstance(v, (int, float))}
        if efecto:
            estado = limitar_estado_por_min_max(simulacion, aplicar_impacto(estado, efecto))
        mensaje = str(ev.get('mensaje', '')).strip()
        if mensaje:
            mensajes.append(mensaje)
        disparados.append(ev_id)
    estado['__eventos__'] = disparados
    return estado, mensajes


def calcular_promedio_pasos(intento):
    puntajes = [
        float(p.puntaje_paso)
        for p in intento.pasos.filter(es_valido=True)
    ]
    return round(mean(puntajes), 2) if puntajes else 0


def _calcular_score_indicadores(simulacion, estado):
    from simulador.models import IndicadorSimulacion

    indicadores = list(simulacion.indicadores.filter(activo=True))
    if not indicadores or not estado:
        return 50.0

    total = 0.0
    count = 0
    for ind in indicadores:
        valor = estado.get(ind.codigo)
        if valor is None:
            continue
        minimo = float(ind.valor_minimo)
        maximo = float(ind.valor_maximo)
        rango = maximo - minimo
        if rango <= 0:
            continue
        posicion = (float(valor) - minimo) / rango
        if ind.direccion_optima == IndicadorSimulacion.DIRECCION_BAJO:
            score = (1 - posicion) * 100
        else:
            score = posicion * 100
        total += score
        count += 1

    return round(total / count, 2) if count > 0 else 50.0


def _calcular_desempeno_indicador(indicador, valor):
    minimo = float(indicador.valor_minimo)
    maximo = float(indicador.valor_maximo)
    rango = maximo - minimo
    if rango <= 0:
        return 50.0
    posicion = (float(valor) - minimo) / rango
    if indicador.direccion_optima == indicador.DIRECCION_BAJO:
        return (1 - posicion) * 100
    return posicion * 100


def calcular_puntaje_final(intento):
    """La nota final depende principalmente de los puntajes por paso.

    promedio_pasos = mean(puntaje_paso de pasos validos)
    final = clamp(0, 100, promedio_pasos)

    Nota: la penalizacion por restricciones ya esta incluida en cada
    puntaje_paso (ver calcular_puntaje_paso), por lo que NO se vuelve a restar
    aqui para evitar doble conteo. Los indicadores se usan para estado,
    retroalimentacion y restricciones, pero NO inflan la nota final.
    """
    pasos_validos = list(intento.pasos.filter(es_valido=True))
    if not pasos_validos:
        return 0.0
    promedio_pasos = mean(float(p.puntaje_paso) for p in pasos_validos)
    return round(max(0, min(100, promedio_pasos)), 2)


def obtener_nivel_resultado(puntaje):
    if puntaje is None:
        return 'Sin evaluar'
    if puntaje >= 90:
        return 'Excelente'
    if puntaje >= 75:
        return 'Bueno'
    if puntaje >= 60:
        return 'Aceptable'
    if puntaje >= 40:
        return 'Básico'
    return 'Insuficiente'


def generar_retroalimentacion_final(simulacion, estado, promedio):
    from simulador.models import IndicadorSimulacion

    indicadores = {
        indicador.codigo: indicador
        for indicador in simulacion.indicadores.filter(activo=True)
    }
    alertas = []
    fortalezas = []
    for clave, valor in (estado or {}).items():
        if not isinstance(valor, (int, float)):
            continue
        indicador = indicadores.get(clave)
        if indicador is None:
            continue
        nombre = indicador.nombre or clave
        minimo = float(indicador.valor_minimo)
        maximo = float(indicador.valor_maximo)
        rango = maximo - minimo
        if rango <= 0:
            continue
        posicion = (float(valor) - minimo) / rango
        if indicador.direccion_optima == IndicadorSimulacion.DIRECCION_BAJO:
            desempeno = 1 - posicion
        else:
            desempeno = posicion
        if desempeno >= 0.7:
            fortalezas.append(f'{nombre} en buen nivel ({valor})')
        elif desempeno <= 0.3:
            alertas.append(f'{nombre} requiere atencion ({valor})')
    texto = [f'Puntuacion final: {promedio}.']
    if fortalezas:
        texto.append('Fortalezas: ' + '; '.join(fortalezas) + '.')
    if alertas:
        texto.append('Aspectos a mejorar: ' + '; '.join(alertas) + '.')
    texto.append('Reflexiona sobre tus decisiones, los indicadores que priorizaste y que cambiarias en un segundo intento.')
    return ' '.join(texto)


def generar_debriefing_final(intento):
    estado_inicial = construir_estado_inicial(intento.simulacion)
    estado_final = intento.estado_actual or {}
    cambios = []
    for clave in estado_inicial:
        inicial = estado_inicial.get(clave, 0)
        final = estado_final.get(clave, 0)
        diff = float(final) - float(inicial)
        if diff > 0:
            cambios.append(f'{clave}: {inicial} -> {final} (+{diff})')
        elif diff < 0:
            cambios.append(f'{clave}: {inicial} -> {final} ({diff})')
        else:
            cambios.append(f'{clave}: {inicial} (sin cambios)')
    restricciones = sum(1 for p in intento.pasos.all() if p.alertas_restricciones)
    rondas_validas = intento.pasos.filter(es_valido=True).count()
    intentos_invalidos = intento.pasos.filter(es_valido=False).count()
    partes = [
        f'=== DEBRIEFING ===',
        f'Simulacion: {intento.simulacion.titulo}',
        f'Estudiante: {intento.estudiante.get_full_name() or intento.estudiante.username}',
        f'Puntaje final: {intento.puntuacion_final} - {obtener_nivel_resultado(float(intento.puntuacion_final))}',
        f'Rondas validas completadas: {rondas_validas}',
        f'Intentos invalidos: {intentos_invalidos}',
        f'Restricciones incumplidas en {restricciones} paso(s).',
        f'',
        f'Evolucion de indicadores:',
    ] + [f'  {c}' for c in cambios] + [
        f'',
        f'Retroalimentacion: {intento.retroalimentacion_final}',
    ]
    if intentos_invalidos > 0:
        partes.append(
            'Recomendacion: revisa las respuestas invalidas y vuelve a plantear decisiones concretas con justificacion tecnica.'
        )
    return '\n'.join(partes)


def finalizar_intento(intento):
    intento.puntuacion_final = calcular_puntaje_final(intento)
    intento.nivel_resultado = obtener_nivel_resultado(float(intento.puntuacion_final))
    intento.retroalimentacion_final = generar_retroalimentacion_final(
        intento.simulacion, intento.estado_actual, float(intento.puntuacion_final),
    )
    intento.debriefing_final = generar_debriefing_final(intento)
    intento.finalizado = True
    intento.fecha_fin = timezone.now()
    intento.save(update_fields=[
        'puntuacion_final', 'nivel_resultado', 'retroalimentacion_final',
        'debriefing_final', 'finalizado', 'fecha_fin',
    ])
    registrar_resultado_juego(intento)
    return intento


def registrar_resultado_juego(intento):
    """Suma XP, sube de nivel, actualiza racha y otorga insignias persistentes
    al perfil del estudiante. Se cuenta una sola vez por intento."""
    from simulador.models import PerfilJuego

    if intento.juego_contabilizado:
        return None
    perfil, _ = PerfilJuego.objects.get_or_create(usuario=intento.estudiante)
    nota = float(intento.puntuacion_final or 0)
    xp = int(round(sum(float(p.puntaje_paso) for p in intento.pasos.filter(es_valido=True))))

    perfil.xp_total += xp
    perfil.simulaciones_completadas += 1
    if nota >= 70:
        perfil.racha_actual += 1
        perfil.mejor_racha = max(perfil.mejor_racha, perfil.racha_actual)
    else:
        perfil.racha_actual = 0
    perfil.mejor_nota = max(float(perfil.mejor_nota), nota)
    perfil.nivel = 1 + perfil.xp_total // PerfilJuego.XP_POR_NIVEL

    insignias = set(perfil.insignias or [])
    insignias.add('primera_mision')
    if nota >= 70:
        insignias.add('mision_aprobada')
    if nota >= 90:
        insignias.add('maestria')
    if perfil.racha_actual >= 3:
        insignias.add('racha_imparable')
    if perfil.simulaciones_completadas >= 5:
        insignias.add('veterano')
    materias = (intento.estudiante.intentos_simulacion
                .filter(finalizado=True)
                .values_list('simulacion__materia_malla__materia_id', flat=True).distinct().count())
    if materias >= 3:
        insignias.add('explorador')
    perfil.insignias = sorted(insignias)
    perfil.save()

    intento.juego_contabilizado = True
    intento.save(update_fields=['juego_contabilizado'])
    return perfil


def situacion_de_ronda(simulacion, numero_ronda):
    rondas = (simulacion.parametros or {}).get('rondas') or []
    indice = numero_ronda - 1
    if 0 <= indice < len(rondas):
        valor = rondas[indice]
        if isinstance(valor, dict):
            situacion = valor.get('situacion') or valor.get('enunciado') or ''
            titulo = valor.get('titulo') or ''
            proposito = valor.get('proposito') or ''
            partes = [texto for texto in [titulo, situacion, proposito] if texto]
            return '\n\n'.join(partes)
        return str(valor)
    return ''


def obtener_escenario_inicial(simulacion):
    inicial = simulacion.escenarios_arbol.filter(activo=True, es_inicial=True).order_by('orden').first()
    if inicial:
        return inicial
    return simulacion.escenarios_arbol.filter(activo=True).order_by('orden').first()


def ejecutar_decision_arbol(intento, decision):
    estado_antes = dict(intento.estado_actual or {})
    recursos_antes = dict(intento.recursos_actuales or {})
    impacto = dict(decision.impacto or {})
    estado_despues = aplicar_impacto(estado_antes, impacto)
    estado_despues = limitar_estado_por_min_max(intento.simulacion, estado_despues)
    recursos_despues = limitar_recursos_por_min_max(intento.simulacion, recursos_antes)
    alertas = validar_restricciones(intento.simulacion, estado_despues)
    penalizacion = calcular_penalizaciones(alertas)
    puntaje_paso = calcular_puntaje_paso(float(decision.puntaje_base), penalizacion)
    numero = intento.pasos.count() + 1
    siguiente = decision.siguiente_escenario
    situacion = intento.escenario_actual.situacion if intento.escenario_actual else decision.escenario.situacion

    paso = intento.pasos.create(
        numero=numero,
        es_valido=True,
        tipo_paso='VALIDO',
        situacion_presentada=situacion,
        decision_estudiante=decision.texto,
        justificacion_estudiante=decision.descripcion,
        evaluacion_ia=decision.retroalimentacion,
        evaluacion_detalle={
            'tipo': 'arbol_decisiones',
            'decision_id': decision.id,
            'puntaje_base': float(decision.puntaje_base),
            'penalizacion': float(penalizacion),
            'puntaje_paso': float(puntaje_paso),
        },
        impacto_calculado=impacto,
        estado_antes=estado_antes,
        estado_despues=estado_despues,
        costo_recursos={},
        recursos_antes=recursos_antes,
        recursos_despues=recursos_despues,
        puntaje_ia_sugerido=float(decision.puntaje_base),
        puntaje_paso=puntaje_paso,
        alertas_restricciones=alertas,
        penalizacion_aplicada=penalizacion,
        siguiente_situacion=siguiente.situacion if siguiente else '',
    )

    intento.estado_actual = estado_despues
    intento.recursos_actuales = recursos_despues
    intento.numero_ronda_actual = numero + 1
    if siguiente:
        intento.escenario_actual = siguiente
        intento.situacion_actual = siguiente.situacion
    else:
        intento.escenario_actual = None
        intento.situacion_actual = ''
    intento.save(update_fields=[
        'estado_actual', 'recursos_actuales', 'numero_ronda_actual',
        'escenario_actual', 'situacion_actual',
    ])

    if not siguiente or siguiente.es_final:
        if siguiente and siguiente.retroalimentacion_final:
            intento.retroalimentacion_final = siguiente.retroalimentacion_final
            intento.save(update_fields=['retroalimentacion_final'])
        finalizar_intento(intento)

    return paso


def ejecutar_ronda_ia_dinamica(intento, decision, justificacion, accion=None):
    # Modo hibrido: si el estudiante ELIGIO una decision (accion), su texto se
    # suma a la decision (la IA evalua la justificacion) y su impacto_base es la
    # CONSECUENCIA real sobre los indicadores. Si no elige, es texto libre.
    accion_impacto = {}
    accion_costo = {}
    if accion is not None:
        decision = (f'{accion.texto}. {decision}').strip() if decision else accion.texto
        accion_impacto = {k: v for k, v in (accion.impacto_base or {}).items() if isinstance(v, (int, float))}
        accion_costo = dict(getattr(accion, 'costo_recursos', {}) or {})
    estado_antes = dict(intento.estado_actual or {})
    recursos_antes = dict(intento.recursos_actuales or construir_recursos_iniciales(intento.simulacion))
    numero = intento.pasos.count() + 1
    ronda_actual = intento.numero_ronda_actual
    situacion_actual = intento.situacion_actual or intento.simulacion.situacion_inicial or intento.simulacion.contexto
    validacion = validar_respuesta_estudiante(
        decision,
        justificacion,
        simulacion=intento.simulacion,
        situacion_actual=situacion_actual,
    )

    if not validacion['valida']:
        puntaje_sugerido = max(0, min(100, float(validacion['puntaje_maximo'])))
        paso = intento.pasos.create(
            numero=numero,
            es_valido=False,
            tipo_paso='INVALIDO',
            situacion_presentada=situacion_actual,
            decision_estudiante=decision,
            justificacion_estudiante=justificacion,
            evaluacion_ia=validacion['motivo'],
            evaluacion_detalle={
                'tipo': 'validacion',
                'valida': False,
                'motivo': validacion['motivo'],
                'tipo_error': validacion['tipo_error'],
                'puntaje_maximo': validacion['puntaje_maximo'],
            },
            impacto_calculado={},
            estado_antes=estado_antes,
            estado_despues=dict(estado_antes),
            costo_recursos={},
            recursos_antes=recursos_antes,
            recursos_despues=dict(recursos_antes),
            puntaje_ia_sugerido=puntaje_sugerido,
            puntaje_paso=puntaje_sugerido,
            alertas_restricciones=[],
            penalizacion_aplicada=0,
            siguiente_situacion=situacion_actual,
        )
        intento.intentos_invalidos_actuales += 1
        update_fields = ['intentos_invalidos_actuales']

        if intento.intentos_invalidos_actuales >= intento.max_intentos_invalidos_por_ronda:
            intento.numero_ronda_actual = ronda_actual + 1
            intento.intentos_invalidos_actuales = 0
            siguiente_configurada = situacion_de_ronda(intento.simulacion, intento.numero_ronda_actual)
            intento.situacion_actual = siguiente_configurada or (
                f'Ronda {intento.numero_ronda_actual}: Se agotaron los intentos de la ronda anterior. '
                f'Replantea la solucion con una decision concreta, conceptos tecnicos y justificacion.'
            )
            update_fields.extend(['numero_ronda_actual', 'situacion_actual'])
            if ronda_actual >= intento.simulacion.maximo_decisiones:
                intento.save(update_fields=update_fields)
                finalizar_intento(intento)
                return paso

        intento.save(update_fields=update_fields)
        return paso
    else:
        from simulador.ia_service import orden_proveedores, evaluar_ronda_con_proveedores

        if orden_proveedores():
            # Intenta OpenAI y/o DeepSeek (segun configuracion); si todos fallan
            # (sin cuota/timeout) cae a la rubrica local.
            try:
                respuesta = evaluar_ronda_con_proveedores(intento, decision, justificacion)
                detalle = respuesta.get('evaluacion_detalle') or {}
                detalle.setdefault('tipo', 'ia_rubrica_docente')
                respuesta['evaluacion_detalle'] = detalle
            except Exception as e:
                respuesta = _fallback_conceptos_o_mock(intento, ronda_actual, decision, justificacion, situacion_actual)
                detalle = respuesta.get('evaluacion_detalle') or {}
                detalle['error_ia'] = str(e)
                respuesta['evaluacion_detalle'] = detalle
        else:
            respuesta = _fallback_conceptos_o_mock(intento, ronda_actual, decision, justificacion, situacion_actual)

        from simulador.services.motor_dinamico import aplicar_opcion_dinamica
        estado_motor, impacto_motor, opcion_detectada, confianza_opcion = aplicar_opcion_dinamica(
            intento.simulacion, estado_antes, decision, justificacion, ronda_actual,
        )
        accion_detectada = accion or detectar_accion_sugerida(intento.simulacion, decision)
        impacto_accion = {}
        costo_recursos = {}
        if accion_detectada:
            impacto_accion = {
                k: v for k, v in (accion_detectada.impacto_base or {}).items()
                if isinstance(v, (int, float))
            }
            costo_recursos = _costos_numericos(accion_detectada.costo_recursos)
        # Modo hibrido: la decision ELEGIDA por el estudiante manda sobre lo detectado por texto.
        if accion_impacto:
            impacto_accion = accion_impacto
        if accion_costo:
            costo_recursos = _costos_numericos(accion_costo)

        impacto = respuesta.get('impacto_sugerido', {})
        errores_impacto = validar_impacto(intento.simulacion, impacto)
        if errores_impacto:
            impacto = {}

        if impacto_motor:
            impacto = {**impacto, **impacto_motor}
        if impacto_accion:
            impacto = {**impacto, **impacto_accion}
        puntaje_sugerido = max(0, min(100, float(respuesta.get('puntaje_sugerido', 0))))
        estado_despues = estado_motor if impacto_motor else aplicar_impacto(estado_antes, impacto)
        estado_despues = limitar_estado_por_min_max(intento.simulacion, estado_despues)
        recursos_despues = limitar_recursos_por_min_max(
            intento.simulacion,
            aplicar_costo_recursos(recursos_antes, costo_recursos),
        )
        # Si la decision no movio ningun indicador (sin impactos configurados y el
        # motor no detecto una opcion), la empresa reacciona a la CALIDAD de la
        # decision, para que la simulacion se sienta viva ronda a ronda.
        if not _hubo_movimiento(estado_antes, estado_despues):
            impacto = impacto_automatico(intento.simulacion, puntaje_sugerido, estado_antes)
            if impacto:
                estado_despues = limitar_estado_por_min_max(
                    intento.simulacion, aplicar_impacto(estado_antes, impacto))
        # Fase B: eventos dinamicos -- la empresa reacciona con sucesos segun el
        # estado/ronda (un cliente cancela, aparece una crisis, etc.).
        estado_despues, eventos_msgs = aplicar_eventos(intento.simulacion, estado_despues, ronda_actual)
        # Solo se penaliza por indicadores que la decision del estudiante movio
        # este turno: no se castiga un estado inicial malo que el no causo. Ademas
        # se aplica un tope para que las restricciones nunca aplasten la nota.
        alertas = validar_restricciones(intento.simulacion, estado_despues)
        alertas_recursos = validar_recursos(intento.simulacion, recursos_despues)
        indicadores_movidos = set(impacto.keys())
        alertas = [a for a in alertas if a.get('indicador') in indicadores_movidos]
        penalizacion_recursos = min(15, len(alertas_recursos) * 5)
        penalizacion = min(PENALIZACION_MAX_PASO, calcular_penalizaciones(alertas) + penalizacion_recursos)
        puntaje_paso = calcular_puntaje_paso(puntaje_sugerido, penalizacion)
        # Tope de calidad: una respuesta valida pero debil (corta/generica/sin
        # justificacion) avanza, pero su nota se limita segun el nivel detectado.
        tope_calidad = float(validacion.get('puntaje_maximo', 100))
        if tope_calidad < 100:
            puntaje_paso = min(puntaje_paso, tope_calidad)
        evaluacion = respuesta.get('evaluacion', '')
        resumen_impacto_real = _resumen_impacto_indicadores(intento.simulacion, impacto)
        if resumen_impacto_real and resumen_impacto_real not in evaluacion:
            evaluacion = f'{evaluacion} Impacto real de la jugada: {resumen_impacto_real}'.strip()
        evaluacion_detalle = respuesta.get('evaluacion_detalle') or {
            'tipo': 'mock',
            'puntaje_sugerido': puntaje_sugerido,
            'evaluacion': evaluacion,
        }
        if accion_detectada or costo_recursos or alertas_recursos:
            evaluacion_detalle = {
                **evaluacion_detalle,
                'accion_sugerida_detectada': accion_detectada.texto if accion_detectada else '',
                'costo_recursos': costo_recursos,
                'alertas_recursos': alertas_recursos,
                'penalizacion_recursos': penalizacion_recursos,
            }
        respuesta_ia_estructurada = respuesta.get('respuesta_ia_estructurada') or {}
        modelo_ia = respuesta.get('modelo_ia', '')
        api_ia = respuesta.get('api_ia', '')
        prompt_version = respuesta.get('prompt_version', '')
        esquema_ia_version = respuesta.get('esquema_ia_version', '')
        tokens_entrada = int(respuesta.get('tokens_entrada') or 0)
        tokens_salida = int(respuesta.get('tokens_salida') or 0)
        siguiente_situacion = respuesta.get('siguiente_situacion') or situacion_actual
        finalizar = bool(respuesta.get('finalizar', False))
        if eventos_msgs:
            texto_eventos = ' '.join(eventos_msgs)
            evaluacion_detalle = {**evaluacion_detalle, 'evento_mensaje': texto_eventos}
            siguiente_situacion = (siguiente_situacion + ' ⚡ ' + texto_eventos).strip()

    paso = intento.pasos.create(
        numero=numero,
        es_valido=True,
        tipo_paso='VALIDO',
        situacion_presentada=situacion_actual,
        decision_estudiante=decision,
        justificacion_estudiante=justificacion,
        evaluacion_ia=evaluacion,
        evaluacion_detalle=evaluacion_detalle,
        respuesta_ia_estructurada=respuesta_ia_estructurada,
        modelo_ia=modelo_ia,
        api_ia=api_ia,
        prompt_version=prompt_version,
        esquema_ia_version=esquema_ia_version,
        tokens_entrada=tokens_entrada,
        tokens_salida=tokens_salida,
        impacto_calculado=impacto,
        estado_antes=estado_antes,
        estado_despues=estado_despues,
        costo_recursos=costo_recursos,
        recursos_antes=recursos_antes,
        recursos_despues=recursos_despues,
        puntaje_ia_sugerido=puntaje_sugerido,
        puntaje_paso=max(0, min(100, float(puntaje_paso))),
        alertas_restricciones=alertas,
        penalizacion_aplicada=penalizacion,
        siguiente_situacion=siguiente_situacion,
    )

    intento.estado_actual = estado_despues
    intento.recursos_actuales = recursos_despues
    intento.situacion_actual = siguiente_situacion
    intento.numero_ronda_actual = ronda_actual + 1
    intento.intentos_invalidos_actuales = 0
    intento.save(update_fields=[
        'estado_actual', 'recursos_actuales', 'situacion_actual', 'numero_ronda_actual',
        'intentos_invalidos_actuales',
    ])

    if ronda_actual >= intento.simulacion.maximo_decisiones or finalizar:
        finalizar_intento(intento)

    return paso


def _puntaje_fallback_justo(intento, decision, justificacion, situacion_actual, evaluacion_conceptos):
    """Sin IA, el emparejador por palabras es muy literal y castiga respuestas
    buenas que no usan las palabras exactas. Para no tankear injustamente, una
    respuesta VALIDA y en tema recibe un piso honesto basado en su calidad de
    escritura y en la cobertura parcial de conceptos. No infla: las coincidencias
    de la rubrica pueden subir por encima del piso, pero el piso evita el 0/10
    en respuestas completas. El 80-100 real requiere la IA (OpenAI/DeepSeek)."""
    base = float(evaluacion_conceptos.get('puntaje_sugerido') or 0)
    validacion = validar_respuesta_estudiante(
        decision, justificacion, simulacion=intento.simulacion, situacion_actual=situacion_actual,
    )
    if not validacion['valida']:
        return base
    calidad = float(validacion.get('puntaje_maximo', 100))
    detalles = evaluacion_conceptos.get('detalle_conceptos') or []
    if detalles:
        cobertura = sum(min(1.0, float(d.get('factor_coincidencia') or 0)) for d in detalles) / len(detalles) * 100
    else:
        cobertura = 0.0
    piso = 0.45 * calidad + 0.25 * cobertura
    return round(min(100.0, max(base, piso)), 2)


def _fallback_conceptos_o_mock(intento, ronda_actual, decision, justificacion, situacion_actual):
    evaluacion_conceptos = evaluar_conceptos_esperados(
        intento.simulacion,
        ronda_actual,
        decision,
        justificacion,
        situacion_actual,
    )
    if evaluacion_conceptos['tiene_conceptos']:
        puntaje_justo = _puntaje_fallback_justo(
            intento, decision, justificacion, situacion_actual, evaluacion_conceptos,
        )
        return {
            'evaluacion': evaluacion_conceptos['evaluacion'],
            'evaluacion_detalle': {
                'tipo': 'rubrica_conceptos',
                'ronda': ronda_actual,
                'conceptos': evaluacion_conceptos['detalle_conceptos'],
                'conceptos_cumplidos': evaluacion_conceptos['conceptos_cumplidos'],
                'conceptos_parciales': evaluacion_conceptos['conceptos_parciales'],
                'conceptos_faltantes': evaluacion_conceptos['conceptos_faltantes'],
                'conceptos_criticos_faltantes': evaluacion_conceptos['conceptos_criticos_faltantes'],
                'puntaje_conceptos': evaluacion_conceptos['puntaje_conceptos'],
                'puntaje_sin_tope': evaluacion_conceptos['puntaje_sin_tope'],
                'tope_critico': evaluacion_conceptos['tope_critico'],
            },
            'impacto_sugerido': evaluacion_conceptos['impacto_sugerido'],
            'puntaje_sugerido': puntaje_justo,
            'siguiente_situacion': (
                situacion_de_ronda(intento.simulacion, ronda_actual + 1)
                or f'Ronda {ronda_actual + 1}: Continua el caso considerando los indicadores actualizados y los conceptos faltantes.'
                if ronda_actual < intento.simulacion.maximo_decisiones else ''
            ),
            'finalizar': False,
        }
    else:
        from simulador.ia_service import IAServiceMock
        return IAServiceMock().evaluar_ronda_dinamica(intento, decision, justificacion)
