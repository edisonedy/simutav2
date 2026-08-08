import re
import unicodedata
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from statistics import mean
from types import SimpleNamespace

from django.utils import timezone


TIPO_ERROR_VACIA = 'VACIA'
TIPO_ERROR_CORTA = 'CORTA'
TIPO_ERROR_BASURA = 'BASURA'
TIPO_ERROR_GENERICA = 'GENERICA'
TIPO_ERROR_SIN_JUSTIFICACION = 'SIN_JUSTIFICACION'
TIPO_ERROR_JUST_BREVE = 'JUST_BREVE'
TIPO_ERROR_OFFTOPIC = 'OFFTOPIC'
TIPO_ERROR_CONTRADICCION = 'CONTRADICCION'
TIPO_ERROR_ACCION_NO_DISPONIBLE = 'ACCION_NO_DISPONIBLE'
TIPO_ERROR_PRONOSTICO_REQUERIDO = 'PRONOSTICO_REQUERIDO'
TIPO_ERROR_TRADEOFF_REQUERIDO = 'TRADEOFF_REQUERIDO'
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


PALABRAS_FUNCIONALES_CONCEPTO = {
    'a', 'al', 'con', 'de', 'del', 'e', 'el', 'en', 'la', 'las', 'los',
    'o', 'para', 'por', 'un', 'una', 'y',
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


def _raiz_flexible(token):
    """Normalizacion morfologica minima para singular/plural en frases."""
    token = str(token or '')
    if len(token) > 5 and token.endswith('es'):
        return token[:-2]
    if len(token) > 4 and token.endswith('s'):
        return token[:-1]
    return token


def _contiene_frase_flexible(texto, patron):
    tokens_patron = _normalizar_texto(patron).split()
    if len(tokens_patron) < 2:
        return False
    tokens_texto = _normalizar_texto(texto).split()
    raices_patron = [_raiz_flexible(token) for token in tokens_patron]
    ancho = len(raices_patron)
    for inicio in range(0, len(tokens_texto) - ancho + 1):
        ventana = [_raiz_flexible(token) for token in tokens_texto[inicio:inicio + ancho]]
        if ventana == raices_patron:
            return True
    return False


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
            if _contiene_frase_flexible(texto, variante_norm):
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


def _es_regla_estructurada(valor):
    """Distingue una regla explicita {any/all/none} de la lista historica.

    En una regla explicita, ``any`` significa alternativas equivalentes: basta
    una para demostrar el concepto. Las listas antiguas separadas por comas
    conservan su puntuacion proporcional para no cambiar rubricas existentes.
    """
    if isinstance(valor, dict):
        return True
    try:
        return isinstance(json.loads(str(valor or '').strip()), dict)
    except (json.JSONDecodeError, TypeError):
        return False


def _factor_nombre_concepto(texto, nombre):
    """Da evidencia parcial cuando explica el concepto con su nombre natural.

    No concede cumplimiento completo: evita que repetir un titulo regale la
    rubrica, pero reconoce expresiones validas no incluidas literalmente en la
    lista de palabras del docente (p. ej. "hipotesis y objetivos").
    """
    tokens = [
        token for token in _normalizar_texto(nombre).split()
        if len(token) >= 4 and token not in PALABRAS_FUNCIONALES_CONCEPTO
    ]
    if not tokens:
        return 0.0
    detectados = sum(1 for token in tokens if _contiene_patron(texto, token))
    proporcion = detectados / len(tokens)
    return 0.5 if proporcion >= 0.75 else 0.0


def _lista_regla(regla, clave):
    valor = regla.get(clave, [])
    if isinstance(valor, str):
        return [valor]
    if isinstance(valor, list):
        return [str(item).strip() for item in valor if str(item).strip()]
    return []


def evaluar_regla_concepto(texto, palabras_clave):
    regla = parsear_regla_concepto(palabras_clave)
    estructurada = _es_regla_estructurada(palabras_clave)
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
    alternativas_equivalentes = alternativas_detectadas + sinonimos_detectados
    cumple_alternativas = bool(alternativas_equivalentes) if alternativas else True
    cumple_prohibidas = not prohibidas_detectadas
    cumple = cumple_obligatorias and cumple_alternativas and cumple_prohibidas

    if estructurada:
        # ``all`` aporta un requisito por elemento; ``any`` es un unico grupo
        # de alternativas equivalentes, no una lista que haya que recitar.
        total_requeridas = len(obligatorias) + (1 if alternativas else 0)
        detectadas_requeridas = len(obligatorias_detectadas) + (
            1 if alternativas and alternativas_equivalentes else 0
        )
    else:
        total_requeridas = len(obligatorias) + len(alternativas)
        detectadas_requeridas = (
            len(obligatorias_detectadas)
            + len(alternativas_detectadas)
            + len(sinonimos_detectados)
        )
    if prohibidas_detectadas:
        factor = 0.0
    elif total_requeridas > 0:
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
    if len(justificacion.strip()) >= 25 and any(
        palabra in texto
        for palabra in ['porque', 'para', 'permite', 'evita', 'garantiza', 'asegura', 'debido', 'ya que']
    ):
        return 10
    return 5


def validar_respuesta_estudiante(
    decision, justificacion, simulacion=None, situacion_actual=None,
    requerir_justificacion=False, minimo_justificacion=12,
    opcion_predefinida=False,
):
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

    # Una alternativa creada por el docente pertenece al caso por definicion.
    # Su texto no siempre comparte vocabulario con la consigna (p. ej. una
    # estrategia concreta frente a un briefing general), por lo que aqui solo
    # se evalua la calidad de la explicacion. Las respuestas completamente
    # libres si conservan el filtro de fuera de tema.
    if (
        not opcion_predefinida
        and simulacion is not None
        and _es_fuera_de_tema(combinado, simulacion, situacion_actual)
    ):
        return _resultado_validacion(
            False,
            'La respuesta no se relaciona con la situación planteada. Responde al caso de la materia.',
            0,
            TIPO_ERROR_OFFTOPIC,
        )

    if requerir_justificacion and len(justificacion_limpia) < minimo_justificacion:
        return _resultado_validacion(
            False,
            'Justifica en una frase breve con un dato, indicador o razón del caso.',
            0,
            TIPO_ERROR_SIN_JUSTIFICACION if not justificacion_limpia else TIPO_ERROR_JUST_BREVE,
        )

    # === VALIDA pero con tope de nota (baja calidad, igual avanza) ===
    if len(combinado) < 24 or len(decision_limpia) < 5:
        return _resultado_validacion(
            True, 'Respuesta válida pero muy breve: agrega un dato o una consecuencia.',
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

    if len(justificacion_limpia) < 30 and not re.search(r'\d', justificacion_limpia):
        return _resultado_validacion(
            True, 'La frase es válida; agrega un dato o indicador concreto para sustentarla.',
            70, TIPO_ERROR_JUST_BREVE,
        )

    if len(justificacion_limpia) < 12:
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


def justificacion_obligatoria(simulacion, numero_ronda, configuracion_snapshot=None):
    """La justificacion es obligatoria salvo en una ronda configurada solo para elegir."""
    caso = (configuracion_snapshot or {}).get('caso') or {}
    parametros = caso.get('parametros') if caso else None
    parametros = parametros if isinstance(parametros, dict) else (simulacion.parametros or {})
    rondas = parametros.get('rondas') or []
    ronda = next(
        (item for item in rondas if isinstance(item, dict) and item.get('numero') == numero_ronda),
        {},
    )
    if not ronda:
        indice = numero_ronda - 1
        ronda = rondas[indice] if 0 <= indice < len(rondas) and isinstance(rondas[indice], dict) else {}
    if 'justificacion_obligatoria' in ronda:
        return bool(ronda['justificacion_obligatoria'])
    return str(ronda.get('modo') or 'hibrido').lower() != 'elegir'


def configuracion_respuesta_ronda(simulacion, numero_ronda, configuracion_snapshot=None):
    """Reglas de entrada congeladas para una ronda.

    Los valores por defecto mantienen compatibles los casos antiguos y permiten
    que una respuesta breve, pero útil, siga siendo válida.
    """
    caso = (configuracion_snapshot or {}).get('caso') or {}
    parametros = caso.get('parametros') if isinstance(caso, dict) else None
    parametros = parametros if isinstance(parametros, dict) else (simulacion.parametros or {})
    rondas = parametros.get('rondas') or []
    ronda = next(
        (item for item in rondas if isinstance(item, dict) and item.get('numero') == numero_ronda),
        None,
    )
    if ronda is None:
        indice = numero_ronda - 1
        ronda = rondas[indice] if 0 <= indice < len(rondas) and isinstance(rondas[indice], dict) else {}
    try:
        minimo = int(ronda.get('minimo_justificacion', 12))
    except (TypeError, ValueError):
        minimo = 12
    modo = str(ronda.get('modo') or 'hibrido').lower()
    fuentes = ronda.get('fuentes_evaluacion')
    if not isinstance(fuentes, list):
        fuentes = ['decision', 'justificacion', 'pronostico', 'tradeoff']
    fuentes_validas = {'decision', 'justificacion', 'pronostico', 'tradeoff'}
    return {
        'minimo_justificacion': max(0, min(500, minimo)),
        'bloquear_contradiccion': bool(
            ronda.get('bloquear_contradiccion', modo == 'hibrido')
        ),
        'pronostico_obligatorio': bool(ronda.get('pronostico_obligatorio', False)),
        'tradeoff_obligatorio': bool(ronda.get('tradeoff_obligatorio', False)),
        'fuentes_evaluacion': [f for f in fuentes if f in fuentes_validas],
    }


def detectar_contradiccion_explicita(texto_opcion, justificacion):
    """Detecta negaciones directas de la opción sin intentar sustituir a la IA.

    Es deliberadamente conservadora: solo bloquea frases como "no aceptar" o
    "descarto contratar" cuando el verbo negado pertenece a la opción elegida.
    Las contradicciones semánticas menos literales las revisa el evaluador IA.
    """
    opcion = _normalizar_texto(texto_opcion)
    explicacion = _normalizar_texto(justificacion)
    if not opcion or not explicacion:
        return ''
    verbos = {
        'aceptar', 'aplicar', 'aumentar', 'calcular', 'contratar', 'ejecutar',
        'elegir', 'financiar', 'ignorar', 'implementar', 'ofertar', 'pagar',
        'pausar', 'presentar', 'proponer', 'reducir', 'revisar', 'usar',
    }
    raices = {
        token[:-2] for token in opcion.split()
        if token in verbos and len(token) > 5
    }
    if not raices:
        return ''
    tokens = explicacion.split()
    negaciones = {'no', 'nunca', 'evito', 'evitaria', 'descarto', 'descartaria', 'rechazo', 'rechazaria'}
    for indice, token in enumerate(tokens):
        if token not in negaciones:
            continue
        ventana = tokens[indice + 1:indice + 7]
        if any(any(palabra.startswith(raiz) for raiz in raices) for palabra in ventana):
            return 'La explicación niega explícitamente la opción seleccionada.'
    return ''


def indicadores_modificables_ronda(simulacion, numero_ronda, configuracion_snapshot=None):
    """Códigos que una fase puede modificar.

    La clave ausente conserva compatibilidad con casos antiguos (todos). Una
    lista vacía es válida y representa una fase informativa sin efecto directo.
    """
    caso = (configuracion_snapshot or {}).get('caso') or {}
    parametros = caso.get('parametros') if isinstance(caso, dict) else None
    parametros = parametros if isinstance(parametros, dict) else (simulacion.parametros or {})
    rondas = parametros.get('rondas') or []
    ronda = next(
        (item for item in rondas if isinstance(item, dict) and item.get('numero') == numero_ronda),
        None,
    )
    if ronda is None:
        indice = numero_ronda - 1
        ronda = rondas[indice] if 0 <= indice < len(rondas) and isinstance(rondas[indice], dict) else {}
    if 'indicadores_modificables' not in ronda:
        congelados = (configuracion_snapshot or {}).get('indicadores') or []
        if congelados:
            return {item.get('codigo') for item in congelados if item.get('codigo')}
        return set(simulacion.indicadores.filter(activo=True).values_list('codigo', flat=True))
    validos = {
        item.get('codigo') for item in ((configuracion_snapshot or {}).get('indicadores') or [])
        if item.get('codigo')
    } or set(simulacion.indicadores.filter(activo=True).values_list('codigo', flat=True))
    return {codigo for codigo in (ronda.get('indicadores_modificables') or []) if codigo in validos}


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
            # JSON no serializa Decimal, pero la operacion se hace con Decimal
            # para evitar residuos como 4.999999999999998.
            total = (Decimal(str(actual)) + Decimal(str(valor))).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP,
            )
            estado[clave] = float(total)
        else:
            estado[clave] = valor
    return estado


def desempeno_indicador(indicador, valor):
    """Normaliza un indicador a 0-100 respetando su semantica.

    Ademas de maximizar o minimizar, admite indicadores cuyo mejor resultado
    es acercarse a un valor objetivo (por ejemplo, tasa CIF o desviacion neta).
    """
    minimo = float(indicador.valor_minimo)
    maximo = float(indicador.valor_maximo)
    valor = max(minimo, min(maximo, float(valor)))
    if maximo <= minimo:
        return 50.0
    direccion = getattr(indicador, 'direccion_optima', 'ALTO')
    if direccion == 'OBJETIVO':
        objetivo_raw = getattr(indicador, 'valor_objetivo', None)
        objetivo = float(objetivo_raw) if objetivo_raw is not None else (minimo + maximo) / 2
        objetivo = max(minimo, min(maximo, objetivo))
        if valor <= objetivo:
            tramo = objetivo - minimo
            return 100.0 if tramo <= 0 else (valor - minimo) / tramo * 100
        tramo = maximo - objetivo
        return 100.0 if tramo <= 0 else (maximo - valor) / tramo * 100
    if direccion == 'RANGO':
        inferior_raw = getattr(indicador, 'valor_objetivo_min', None)
        superior_raw = getattr(indicador, 'valor_objetivo_max', None)
        if inferior_raw is None or superior_raw is None:
            return 50.0
        inferior = max(minimo, min(maximo, float(inferior_raw)))
        superior = max(minimo, min(maximo, float(superior_raw)))
        if inferior >= superior:
            return 50.0
        if inferior <= valor <= superior:
            return 100.0
        if valor < inferior:
            return (valor - minimo) / (inferior - minimo or 1) * 100
        return (maximo - valor) / (maximo - superior or 1) * 100
    posicion = (valor - minimo) / (maximo - minimo)
    return (1 - posicion) * 100 if direccion == 'BAJO' else posicion * 100


def indicador_mejora(indicador, antes, despues):
    if not isinstance(antes, (int, float)) or not isinstance(despues, (int, float)):
        return None
    diferencia = desempeno_indicador(indicador, despues) - desempeno_indicador(indicador, antes)
    if abs(diferencia) < 0.01:
        return None
    return diferencia > 0


def cumple_operador(operador, valor, limite):
    valor = float(valor)
    limite = float(limite)
    if operador == '<':
        return valor < limite
    if operador == '<=':
        return valor <= limite
    if operador == '>':
        return valor > limite
    if operador == '>=':
        return valor >= limite
    if operador in ('=', '=='):
        return valor == limite
    if operador == 'ABS<=':
        return abs(valor) <= abs(limite)
    return False


def _recursos_configurados(simulacion, configuracion_snapshot=None):
    congelados = (configuracion_snapshot or {}).get('recursos')
    if congelados is not None:
        return [SimpleNamespace(**item) for item in congelados]
    return list(simulacion.recursos.filter(activo=True))


def limitar_recursos_por_min_max(simulacion, recursos, configuracion_snapshot=None):
    recursos_limitados = dict(recursos or {})
    recursos_cfg = {
        recurso.codigo: recurso
        for recurso in _recursos_configurados(simulacion, configuracion_snapshot)
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


TIPOS_CAMPO_DECISION = ('numero', 'opcion', 'texto')


def campos_decision_ronda(simulacion, numero_ronda, configuracion_snapshot=None):
    """Los campos que el docente pidio en esta ronda.

    Una ronda aceptaba UNA decision, de tipo elegir o escribir. Con campos
    configurables el docente arma la ronda que necesita: pedir una cantidad
    ("cuanto producir"), varias decisiones a la vez (precio, publicidad,
    produccion) o una sola como antes. Sin campos configurados no cambia nada:
    la ronda se comporta como siempre.
    """
    rondas = None
    if configuracion_snapshot:
        rondas = (configuracion_snapshot.get('caso') or {}).get('rondas')
    if rondas is None:
        rondas = (simulacion.parametros or {}).get('rondas') or []
    indice = numero_ronda - 1
    if not (0 <= indice < len(rondas)) or not isinstance(rondas[indice], dict):
        return []

    campos = []
    for bruto in rondas[indice].get('campos') or []:
        if not isinstance(bruto, dict):
            continue
        clave = str(bruto.get('clave') or '').strip()
        tipo = str(bruto.get('tipo') or 'texto').strip().lower()
        if not clave or tipo not in TIPOS_CAMPO_DECISION:
            continue
        campo = {
            'clave': clave,
            'etiqueta': str(bruto.get('etiqueta') or clave).strip(),
            'tipo': tipo,
            'ayuda': str(bruto.get('ayuda') or '').strip(),
            'obligatorio': bool(bruto.get('obligatorio', True)),
            'unidad': str(bruto.get('unidad') or '').strip(),
        }
        if tipo == 'numero':
            for limite in ('minimo', 'maximo', 'objetivo', 'tolerancia'):
                valor = bruto.get(limite)
                campo[limite] = float(valor) if isinstance(valor, (int, float)) else None
        campos.append(campo)
    return campos


def evaluar_campos_numericos(campos, valores):
    """Puntua los campos numericos SIN IA: es aritmetica, no interpretacion.

    Dentro de la tolerancia del objetivo vale completo; mas lejos baja de forma
    proporcional hasta cero. Un campo sin objetivo no puntua: el docente solo
    queria el dato.
    """
    evaluables = [c for c in campos if c['tipo'] == 'numero' and c.get('objetivo') is not None]
    if not evaluables:
        return None

    detalle = []
    total = 0.0
    for campo in evaluables:
        crudo = (valores or {}).get(campo['clave'])
        try:
            valor = float(str(crudo).replace(',', '.'))
        except (TypeError, ValueError):
            detalle.append({'clave': campo['clave'], 'etiqueta': campo['etiqueta'],
                            'valor': None, 'objetivo': campo['objetivo'], 'puntaje': 0.0,
                            'comentario': 'No respondio con un numero.'})
            continue

        objetivo = campo['objetivo']
        tolerancia = campo.get('tolerancia')
        if not tolerancia or tolerancia <= 0:
            # Sin tolerancia explicita, el 10% del objetivo es el margen razonable.
            tolerancia = abs(objetivo) * 0.1 or 1
        distancia = abs(valor - objetivo)
        if distancia <= tolerancia:
            puntaje = 100.0
            comentario = 'Dentro del margen esperado.'
        elif distancia <= tolerancia * 3:
            puntaje = round(100 * (1 - (distancia - tolerancia) / (tolerancia * 2)), 2)
            comentario = f'Se aleja del valor esperado ({objetivo:g}).'
        else:
            puntaje = 0.0
            comentario = f'Muy lejos del valor esperado ({objetivo:g}).'
        total += puntaje
        detalle.append({'clave': campo['clave'], 'etiqueta': campo['etiqueta'],
                        'valor': valor, 'objetivo': objetivo, 'puntaje': puntaje,
                        'comentario': comentario})

    return {'puntaje': round(total / len(evaluables), 2), 'detalle': detalle}


def validar_campos_decision(campos, valores):
    """Devuelve los faltantes o fuera de rango, para no dejar avanzar a medias."""
    problemas = []
    for campo in campos:
        crudo = (valores or {}).get(campo['clave'])
        vacio = crudo is None or str(crudo).strip() == ''
        if vacio:
            if campo['obligatorio']:
                problemas.append(f'Falta "{campo["etiqueta"]}".')
            continue
        if campo['tipo'] != 'numero':
            continue
        try:
            valor = float(str(crudo).replace(',', '.'))
        except (TypeError, ValueError):
            problemas.append(f'"{campo["etiqueta"]}" debe ser un numero.')
            continue
        minimo, maximo = campo.get('minimo'), campo.get('maximo')
        if minimo is not None and valor < minimo:
            problemas.append(f'"{campo["etiqueta"]}" no puede ser menor que {minimo:g}.')
        if maximo is not None and valor > maximo:
            problemas.append(f'"{campo["etiqueta"]}" no puede ser mayor que {maximo:g}.')
    return problemas


def investigaciones_disponibles(intento):
    """Las averiguaciones que el estudiante puede pagar en la ronda actual, con
    su costo y, si ya las pago, el hallazgo revelado."""
    compradas = set(intento.investigaciones_compradas or [])
    recursos = intento.recursos_actuales or {}
    congeladas = (intento.configuracion_snapshot or {}).get('investigaciones')
    if congeladas is not None:
        catalogo = [
            SimpleNamespace(**item) for item in congeladas
            if int(item.get('disponible_desde_ronda') or 1) <= intento.numero_ronda_actual
        ]
    else:
        from simulador.models import InvestigacionSimulacion
        catalogo = InvestigacionSimulacion.objects.filter(
            simulacion=intento.simulacion, activo=True,
            disponible_desde_ronda__lte=intento.numero_ronda_actual,
        )
    items = []
    for inv in catalogo:
        pagada = inv.id in compradas
        alcanza = puede_pagar(recursos, inv.costo_recursos)
        items.append({
            'id': inv.id,
            'sujeto': inv.sujeto,
            'nombre': inv.nombre,
            'descripcion': inv.descripcion,
            'costo': inv.costo_recursos or {},
            'pagada': pagada,
            'alcanza': alcanza,
            'hallazgo': inv.hallazgo if pagada else '',
        })
    return items


def puede_pagar(recursos_actuales, costo):
    """True si el saldo alcanza para ese costo, sin quedar en negativo."""
    recursos = recursos_actuales or {}
    for clave, valor in (costo or {}).items():
        if not isinstance(valor, (int, float)):
            continue
        disponible = recursos.get(clave)
        if not isinstance(disponible, (int, float)) or float(disponible) < float(valor):
            return False
    return True


def comprar_investigacion(intento, investigacion):
    """Cobra la averiguacion y devuelve el hallazgo. No cobra dos veces."""
    compradas = list(intento.investigaciones_compradas or [])
    if investigacion.id in compradas:
        return {'ok': False, 'mensaje': 'Ya pagaste esa averiguacion.',
                'hallazgo': investigacion.hallazgo}
    if not puede_pagar(intento.recursos_actuales, investigacion.costo_recursos):
        return {'ok': False, 'mensaje': 'No te alcanza el presupuesto para esa averiguacion.',
                'hallazgo': ''}

    intento.recursos_actuales = aplicar_costo_recursos(
        intento.recursos_actuales, investigacion.costo_recursos,
    )
    compradas.append(investigacion.id)
    intento.investigaciones_compradas = compradas
    intento.save(update_fields=['recursos_actuales', 'investigaciones_compradas'])
    return {'ok': True, 'mensaje': 'Averiguacion realizada.',
            'hallazgo': investigacion.hallazgo,
            'recursos': intento.recursos_actuales}


def hallazgos_conocidos(intento):
    """Lo que el estudiante ya averiguo. Se le pasa a la IA para que pueda
    juzgar si uso la evidencia que pago o decidio a ciegas."""
    compradas = intento.investigaciones_compradas or []
    if not compradas:
        return []
    congeladas = (intento.configuracion_snapshot or {}).get('investigaciones')
    if congeladas is not None:
        return [
            {
                'sujeto': item.get('sujeto', ''),
                'averiguacion': item.get('nombre', ''),
                'hallazgo': item.get('hallazgo', ''),
            }
            for item in congeladas if item.get('id') in compradas
        ]
    from simulador.models import InvestigacionSimulacion
    return [
        {'sujeto': i.sujeto, 'averiguacion': i.nombre, 'hallazgo': i.hallazgo}
        for i in InvestigacionSimulacion.objects.filter(id__in=compradas, activo=True)
    ]


def validar_recursos(simulacion, recursos, configuracion_snapshot=None):
    alertas = []
    for recurso in _recursos_configurados(simulacion, configuracion_snapshot):
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


def detectar_accion_sugerida(simulacion, decision, configuracion_snapshot=None):
    texto = _normalizar_texto(decision)
    if not texto:
        return None
    congeladas = (configuracion_snapshot or {}).get('acciones_sugeridas') or []
    acciones = (
        [SimpleNamespace(**item) for item in congeladas]
        if congeladas else
        simulacion.acciones_sugeridas.filter(activo=True).order_by('numero_ronda', 'texto')
    )
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


def maximo_ejecuciones_efectivo(accion, total_rondas):
    """Limite seguro para configuraciones heredadas.

    Antes de existir el limite por ejecuciones, las acciones globales quedaron
    guardadas con cero (ilimitadas). En un caso de varias rondas eso permite
    repetir exactamente la misma jugada. Se interpreta como una sola ejecucion
    sin alterar las acciones especificas de ronda ni los casos de una ronda.
    """
    if isinstance(accion, dict):
        maximo = int(accion.get('maximo_ejecuciones') or 0)
        numero_ronda = accion.get('numero_ronda')
    else:
        maximo = int(getattr(accion, 'maximo_ejecuciones', 0) or 0)
        numero_ronda = getattr(accion, 'numero_ronda', None)
    if maximo == 0 and numero_ronda is None and int(total_rondas or 1) > 1:
        return 1
    return maximo


def accion_habilitada_por_historial(intento, accion):
    requerida = getattr(accion, 'requiere_accion_previa_id', None)
    bloqueante = getattr(accion, 'bloqueada_por_accion_previa_id', None)
    maximo = maximo_ejecuciones_efectivo(accion, maximo_decisiones_intento(intento))
    conteos = {}
    for detalle in intento.pasos.filter(es_valido=True).values_list('evaluacion_detalle', flat=True):
        seleccion = (detalle or {}).get('seleccion_registrada') or {}
        accion_id = seleccion.get('accion_id')
        try:
            accion_id = int(accion_id)
            conteos[accion_id] = conteos.get(accion_id, 0) + 1
        except (TypeError, ValueError):
            continue
    seleccionadas = set(conteos)
    try:
        if requerida is not None and int(requerida) not in seleccionadas:
            return False
        if bloqueante is not None and int(bloqueante) in seleccionadas:
            return False
        accion_id = int(getattr(accion, 'pk', 0) or 0)
        if maximo and conteos.get(accion_id, 0) >= maximo:
            return False
    except (TypeError, ValueError):
        return False
    return True


def limitar_estado_por_min_max(simulacion, estado, configuracion_snapshot=None):
    estado_limitado = dict(estado or {})
    congelados = (configuracion_snapshot or {}).get('indicadores') or []
    indicadores = (
        {item.get('codigo'): SimpleNamespace(**item) for item in congelados}
        if congelados else
        {indicador.codigo: indicador for indicador in simulacion.indicadores.filter(activo=True)}
    )
    for codigo, indicador in indicadores.items():
        valor = estado_limitado.get(codigo)
        if not isinstance(valor, (int, float)):
            continue
        minimo = float(indicador.valor_minimo)
        maximo = float(indicador.valor_maximo)
        estado_limitado[codigo] = max(minimo, min(maximo, float(valor)))
    return estado_limitado


def validar_impacto(simulacion, impacto, configuracion_snapshot=None):
    indicadores_snapshot = (configuracion_snapshot or {}).get('indicadores') or []
    codigos = (
        {i.get('codigo') for i in indicadores_snapshot}
        if indicadores_snapshot else
        {i.codigo for i in simulacion.indicadores.filter(activo=True)}
    )
    errores = []
    for clave, valor in (impacto or {}).items():
        if clave not in codigos:
            errores.append(f'Indicador "{clave}" no existe en la simulacion')
        elif not isinstance(valor, (int, float)):
            errores.append(f'Valor para "{clave}" debe ser numerico')
    return errores


def obtener_conceptos_esperados_ronda(
    simulacion, numero_ronda, escenario=None, configuracion_snapshot=None,
):
    from simulador.models import ConceptoEsperadoRonda

    datos = (configuracion_snapshot or {}).get('conceptos') or []
    if datos and not escenario and all(item.get('id') is not None for item in datos):
        seleccion = [item for item in datos if item.get('numero_ronda') == numero_ronda]
        if not seleccion:
            seleccion = [item for item in datos if item.get('numero_ronda') is None]
        return [
            SimpleNamespace(pk=item.get('id'), **item)
            for item in seleccion
        ]

    qs = ConceptoEsperadoRonda.objects.filter(activo=True)
    if escenario:
        qs = qs.filter(escenario=escenario)
    else:
        qs = qs.filter(simulacion=simulacion, escenario__isnull=True)

    conceptos = list(qs.filter(numero_ronda=numero_ronda))
    if not conceptos:
        conceptos = list(qs.filter(numero_ronda__isnull=True))
    return conceptos


# Rubrica transversal del metodo del caso: no evalua si el estudiante recito un
# concepto del temario, sino COMO decide. Es la misma para todos los casos, asi
# que el docente no tiene que escribirla, y agrega escalones a la nota: con solo
# los conceptos del dominio (4 criterios de 25%) la nota saltaba de 25 en 25 y
# caer a cero era facil.
CRITERIOS_DECISION = [
    {
        'clave': 'postura',
        'nombre': 'Toma una postura clara',
        'descripcion': 'Decide algo concreto y accionable en vez de describir el problema '
                       'o enumerar alternativas sin elegir.',
        'peso': 25,
    },
    {
        'clave': 'evidencia',
        'nombre': 'Sustenta con evidencia del caso',
        'descripcion': 'Apoya la decision en datos concretos del caso: cifras, indicadores '
                       'o hechos de la situacion, no en generalidades.',
        'peso': 25,
    },
    {
        'clave': 'tradeoff',
        'nombre': 'Reconoce el costo o el riesgo',
        'descripcion': 'Nombra que sacrifica, que riesgo asume o a quien afecta su decision. '
                       'No presenta la opcion como gratis y sin contras.',
        'peso': 25,
    },
    {
        'clave': 'consecuencia',
        'nombre': 'Anticipa una consecuencia medible',
        'descripcion': 'Dice que espera que pase con algun indicador del caso y como sabria '
                       'si funciono.',
        'peso': 25,
    },
]


def _normalizar_evaluaciones_decision(evaluaciones):
    """Deja las evaluaciones de la rubrica de decision indexadas por clave."""
    validas = {c['clave'] for c in CRITERIOS_DECISION}
    normalizadas = {}
    for item in evaluaciones or []:
        clave = str(item.get('clave') or '').strip().lower()
        if clave not in validas:
            continue
        normalizadas[clave] = {
            'cumple': bool(item.get('cumple')),
            'evidencia': str(item.get('evidencia') or '').strip(),
            'retroalimentacion': str(item.get('retroalimentacion') or '').strip(),
        }
    return normalizadas


def evaluar_rubrica_decision(evaluaciones_decision):
    """Puntaje 0-100 de la calidad de la decision. Cada criterio es binario a
    proposito: la evidencia dice que los modelos juzgan bien en binario y se
    pierden con los matices; la gradualidad sale de sumar varios criterios."""
    juicios = _normalizar_evaluaciones_decision(evaluaciones_decision)
    if not juicios:
        return None
    puntaje = 0
    detalle = []
    for criterio in CRITERIOS_DECISION:
        juicio = juicios.get(criterio['clave'], {})
        cumple = bool(juicio.get('cumple'))
        obtenidos = criterio['peso'] if cumple else 0
        puntaje += obtenidos
        detalle.append({
            'clave': criterio['clave'],
            'nombre': criterio['nombre'],
            'cumple': cumple,
            'puntos_obtenidos': obtenidos,
            'puntos_maximos': criterio['peso'],
            'evidencia': juicio.get('evidencia', ''),
            'retroalimentacion': juicio.get('retroalimentacion', ''),
        })
    return {'puntaje': puntaje, 'detalle': detalle}


def _normalizar_evaluaciones_ia(evaluaciones_ia):
    normalizadas = {}
    factores_por_nivel = {'completa': 1.0, 'parcial': 0.5, 'ausente': 0.0}
    for item in evaluaciones_ia or []:
        try:
            concepto_id = int(item.get('concepto_id'))
        except (TypeError, ValueError):
            continue
        nivel = str(item.get('nivel_evidencia') or '').strip().lower()
        if nivel in factores_por_nivel:
            factor = factores_por_nivel[nivel]
        else:
            # Compatibilidad con respuestas ya almacenadas y proveedores que
            # aun contesten con el esquema anterior.
            factor = item.get('factor', 1 if item.get('cumple') else 0)
            try:
                factor = float(factor)
            except (TypeError, ValueError):
                factor = 0.0
        normalizadas[concepto_id] = {
            'cumple': nivel == 'completa' if nivel else bool(item.get('cumple')),
            'factor': max(0.0, min(1.0, factor)),
            'evidencia': str(item.get('evidencia') or '').strip(),
            'retroalimentacion': str(item.get('retroalimentacion') or '').strip(),
            'fuente_evidencia': str(item.get('fuente_evidencia') or 'respuesta_completa').strip().lower(),
        }
    return normalizadas


def evaluar_conceptos_esperados(
    simulacion, numero_ronda, decision, justificacion, situacion_actual,
    escenario=None, evaluaciones_ia=None, evaluaciones_decision=None,
    configuracion_snapshot=None, opcion_predefinida=False,
):
    texto = _normalizar_texto(f'{decision} {justificacion}')
    conceptos = obtener_conceptos_esperados_ronda(
        simulacion, numero_ronda, escenario=escenario,
        configuracion_snapshot=configuracion_snapshot,
    )
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
            fuente_evidencia = evaluacion_ia.get('fuente_evidencia', 'respuesta_completa')
            # Elegir una opción correcta demuestra postura, pero el texto que
            # escribió el docente dentro de esa opción no sustituye el
            # razonamiento técnico del estudiante.
            if opcion_predefinida and fuente_evidencia == 'opcion':
                cumple, factor = False, 0.0
            elif opcion_predefinida and fuente_evidencia == 'ambas':
                factor = min(factor, 0.5)
        else:
            cumple = regla['cumple']
            factor = regla['factor']
            fuente_evidencia = 'rubrica_local'
            factor_nombre = _factor_nombre_concepto(texto, concepto.nombre)
            if factor_nombre > factor:
                factor = factor_nombre
                palabras_detectadas = palabras_detectadas + [f'concepto: {concepto.nombre}']
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
            'fuente_evidencia': fuente_evidencia,
            'retroalimentacion': _retroalimentacion_concepto(
                concepto,
                cumple,
                evaluacion_ia.get('retroalimentacion', '') if evaluacion_ia else '',
            ),
            'impacto': impacto_concepto,
        })

    errores_impacto = validar_impacto(simulacion, impacto_total, configuracion_snapshot)
    if errores_impacto:
        indicadores_snapshot = (configuracion_snapshot or {}).get('indicadores') or []
        codigos = (
            {item.get('codigo') for item in indicadores_snapshot}
            if indicadores_snapshot else
            set(simulacion.indicadores.filter(activo=True).values_list('codigo', flat=True))
        )
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

    # Mezcla con la rubrica de decision (metodo del caso). Solo aplica cuando la
    # IA pudo juzgarla: la rubrica local por palabras clave no sabe si el
    # estudiante tomo postura o reconocio un trade-off.
    rubrica_decision = evaluar_rubrica_decision(evaluaciones_decision)
    peso_decision = 0
    if rubrica_decision and conceptos:
        caso_snapshot = (configuracion_snapshot or {}).get('caso') or {}
        peso_configurado = caso_snapshot.get(
            'peso_rubrica_decision', getattr(simulacion, 'peso_rubrica_decision', 0),
        )
        peso_decision = max(0, min(100, int(peso_configurado or 0)))
        if peso_decision:
            proporcion = peso_decision / 100.0
            puntaje = round(puntaje * (1 - proporcion) + rubrica_decision['puntaje'] * proporcion, 2)

    partes = []
    if rubrica_decision and peso_decision:
        cumplidos_decision = [d['nombre'] for d in rubrica_decision['detalle'] if d['cumple']]
        faltantes_decision = [d['nombre'] for d in rubrica_decision['detalle'] if not d['cumple']]
        if cumplidos_decision:
            partes.append('Como decision: ' + ', '.join(cumplidos_decision).lower() + '.')
        if faltantes_decision:
            partes.append('Te falto: ' + ', '.join(faltantes_decision).lower() + '.')
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
        'rubrica_decision': rubrica_decision['detalle'] if rubrica_decision else [],
        'puntaje_decision': rubrica_decision['puntaje'] if rubrica_decision else None,
        'peso_decision': peso_decision,
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


def _resumen_impacto_indicadores(simulacion, impacto, estado_antes=None):
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
        signo = '+' if delta > 0 else ''
        previo = (estado_antes or {}).get(codigo)
        mejora = indicador_mejora(
            ind, previo, float(previo) + float(delta),
        ) if isinstance(previo, (int, float)) else None
        estado = 'mejora' if mejora is True else 'empeora' if mejora is False else 'cambio'
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


def validar_restricciones(simulacion, estado, configuracion_snapshot=None):
    alertas = []
    congeladas = (configuracion_snapshot or {}).get('restricciones') or []
    restricciones = (
        [SimpleNamespace(**item) for item in congeladas]
        if congeladas else simulacion.restricciones.filter(activo=True)
    )
    for r in restricciones:
        valor = estado.get(r.codigo_indicador)
        if valor is None:
            continue
        incumple = not cumple_operador(r.operador, valor, r.valor_limite)
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


def _magnitud_violacion(operador, limite, valor):
    """Cuanto le falta a un indicador para cumplir su restriccion (0 = la cumple)."""
    if valor is None or limite is None:
        return 0.0
    valor = float(valor)
    limite = float(limite)
    if operador in ('>=', '>'):
        return max(0.0, limite - valor)
    if operador in ('<=', '<'):
        return max(0.0, valor - limite)
    if operador in ('==', '='):
        return abs(valor - limite)
    if operador == 'ABS<=':
        return max(0.0, abs(valor) - abs(limite))
    return 0.0


def _restriccion_mejoro(alerta, estado_antes, estado_despues):
    """True si el estudiante ACERCO el indicador a cumplir su restriccion este
    turno (aunque todavia la incumpla). Sirve para premiar el avance: si baja los
    defectos de 15% a 7% va por buen camino y no debe penalizarse como si nada."""
    codigo = alerta.get('indicador')
    operador = alerta.get('operador')
    limite = alerta.get('limite')
    if not codigo or operador is None or limite is None:
        return False
    falta_antes = _magnitud_violacion(operador, limite, (estado_antes or {}).get(codigo))
    falta_despues = _magnitud_violacion(operador, limite, (estado_despues or {}).get(codigo))
    return falta_despues < falta_antes


def validar_condiciones_exito(simulacion, estado):
    cumplidas = []
    bonificacion_total = 0
    for c in simulacion.condiciones_exito.filter(activo=True):
        valor = estado.get(c.codigo_indicador)
        if valor is None:
            continue
        cumple = cumple_operador(c.operador, valor, c.valor_objetivo)
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


def _delta_estados(antes, despues):
    cambios = {}
    for codigo in set((antes or {}).keys()) | set((despues or {}).keys()):
        previo = (antes or {}).get(codigo)
        actual = (despues or {}).get(codigo)
        if not isinstance(previo, (int, float)) or not isinstance(actual, (int, float)):
            continue
        delta = round(float(actual) - float(previo), 2)
        if delta:
            cambios[codigo] = delta
    return cambios


def normalizar_pronostico(pronostico=None):
    pronostico = pronostico or {}
    direccion = (pronostico.get('direccion') or '').strip().lower()
    if direccion not in {'sube', 'baja', 'igual'}:
        direccion = ''
    return {
        'indicador': (pronostico.get('indicador') or '').strip()[:80],
        'direccion': direccion,
        'justificacion': (pronostico.get('justificacion') or '').strip()[:1000],
    }


def evaluar_pronostico(pronostico, estado_antes, estado_despues):
    pronostico = normalizar_pronostico(pronostico)
    indicador = pronostico.get('indicador')
    direccion = pronostico.get('direccion')
    if not indicador or not direccion:
        return {}
    if indicador not in (estado_antes or {}) and indicador not in (estado_despues or {}):
        return {
            'estado': 'sin_datos',
            'mensaje': 'No se pudo comparar el pronostico porque el indicador no tiene datos en este paso.',
        }
    antes = float((estado_antes or {}).get(indicador, 0) or 0)
    despues = float((estado_despues or {}).get(indicador, antes) or antes)
    delta = despues - antes
    if delta > 0:
        real = 'sube'
    elif delta < 0:
        real = 'baja'
    else:
        real = 'igual'
    acerto = direccion == real
    return {
        'estado': 'acierto' if acerto else 'diferencia',
        'indicador': indicador,
        'direccion_predicha': direccion,
        'direccion_real': real,
        'valor_antes': antes,
        'valor_despues': despues,
        'delta': delta,
        'mensaje': (
            'Tu pronostico coincidio con el cambio real.'
            if acerto else
            f'Tu pronostico fue "{direccion}", pero el indicador realmente quedo "{real}".'
        ),
    }


def evaluar_tradeoff(simulacion, tradeoff_aceptado, estado_antes, estado_despues, recursos_antes=None, recursos_despues=None):
    tradeoff_aceptado = (tradeoff_aceptado or '').strip()[:1000]
    indicadores = {
        ind.codigo: ind
        for ind in simulacion.indicadores.filter(activo=True)
    }
    recursos = {
        rec.codigo: rec
        for rec in simulacion.recursos.filter(activo=True)
    }
    ganancias = []
    sacrificios = []

    for codigo, ind in indicadores.items():
        antes = (estado_antes or {}).get(codigo)
        despues = (estado_despues or {}).get(codigo)
        if not isinstance(antes, (int, float)) or not isinstance(despues, (int, float)):
            continue
        delta = round(float(despues) - float(antes), 2)
        if delta == 0:
            continue
        mejora = indicador_mejora(ind, antes, despues)
        item = {
            'tipo': 'indicador',
            'codigo': codigo,
            'nombre': ind.nombre or codigo,
            'antes': float(antes),
            'despues': float(despues),
            'delta': delta,
        }
        if mejora is True:
            ganancias.append(item)
        elif mejora is False:
            sacrificios.append(item)

    for codigo, rec in recursos.items():
        antes = (recursos_antes or {}).get(codigo)
        despues = (recursos_despues or {}).get(codigo)
        if not isinstance(antes, (int, float)) or not isinstance(despues, (int, float)):
            continue
        delta = round(float(despues) - float(antes), 2)
        if delta == 0:
            continue
        item = {
            'tipo': 'recurso',
            'codigo': codigo,
            'nombre': rec.nombre or codigo,
            'antes': float(antes),
            'despues': float(despues),
            'delta': delta,
            'unidad': rec.unidad,
        }
        if delta < 0:
            sacrificios.append(item)
        else:
            ganancias.append(item)

    if not ganancias and not sacrificios and not tradeoff_aceptado:
        return {}
    if ganancias and sacrificios:
        estado = 'tradeoff_real'
        mensaje = 'La jugada tuvo un intercambio real: mejoro algo, pero sacrifico otra variable.'
    elif ganancias:
        estado = 'solo_ganancia'
        mensaje = 'La jugada genero ganancias visibles sin sacrificios medibles en este paso.'
    elif sacrificios:
        estado = 'solo_sacrificio'
        mensaje = 'La jugada tuvo costo o deterioro, pero no genero una ganancia medible inmediata.'
    else:
        estado = 'sin_cambio'
        mensaje = 'No hubo cambios medibles para contrastar el trade-off declarado.'
    return {
        'estado': estado,
        'mensaje': mensaje,
        'aceptado': tradeoff_aceptado,
        'ganancias': ganancias,
        'sacrificios': sacrificios,
    }


def _cumple_condicion(estado, cond):
    valor = estado.get(cond.get('indicador'))
    if not isinstance(valor, (int, float)):
        return False
    v, limite = float(valor), float(cond.get('valor', 0))
    op = cond.get('operador', '<')
    return cumple_operador(op, v, limite)


def aplicar_eventos(simulacion, estado_despues, ronda_actual, configuracion_snapshot=None):
    """Fase B - eventos dinamicos.

    Lee eventos desde la tabla EventoSimulacion. Si la simulacion aun no tiene
    eventos en tabla, conserva compatibilidad con simulacion.parametros['eventos']:
    cada evento = {id, ronda?, condicion?{indicador,operador,valor}, mensaje, efecto{codigo:delta}}.
    Se dispara si coincide la ronda (o no se especifica) y se cumple la condicion sobre
    el estado (o no hay), UNA sola vez por intento (se rastrea en estado['__eventos__'])."""
    eventos = []
    congelados = (configuracion_snapshot or {}).get('eventos')
    if congelados is not None:
        for evento in congelados:
            condicion = None
            if evento.get('codigo_indicador_condicion') and evento.get('valor_condicion') is not None:
                condicion = {
                    'indicador': evento.get('codigo_indicador_condicion'),
                    'operador': evento.get('operador_condicion') or '>=',
                    'valor': float(evento.get('valor_condicion')),
                }
            eventos.append({
                'id': f"db:{evento.get('id')}",
                'ronda': evento.get('ronda'),
                'condicion': condicion,
                'mensaje': evento.get('mensaje', ''),
                'efecto': evento.get('efecto') or {},
            })
    else:
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
        caso = (configuracion_snapshot or {}).get('caso') or {}
        parametros = caso.get('parametros') if caso else simulacion.parametros
        for idx, evento_json in enumerate((parametros or {}).get('eventos') or []):
            item = dict(evento_json or {})
            item['id'] = f'json:{item.get("id", idx)}'
            eventos.append(item)
    estado = dict(estado_despues or {})
    modificables = indicadores_modificables_ronda(
        simulacion, ronda_actual, configuracion_snapshot,
    )
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
        efecto = {
            k: v for k, v in (ev.get('efecto') or {}).items()
            if isinstance(v, (int, float)) and k in modificables
        }
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
    indicadores = list(simulacion.indicadores.filter(activo=True))
    if not indicadores or not estado:
        return 50.0

    total = 0.0
    count = 0
    for ind in indicadores:
        valor = estado.get(ind.codigo)
        if valor is None:
            continue
        score = desempeno_indicador(ind, valor)
        total += score
        count += 1

    return round(total / count, 2) if count > 0 else 50.0


def calcular_puntaje_final(intento):
    """La nota final combina COMO decidio y COMO quedo la empresa.

    proceso   = mean(puntaje_paso de pasos validos)   -> razonamiento y rubrica
    resultado = condiciones de exito cumplidas, o salud de los indicadores
    final     = proceso * (1 - p) + resultado * p + bonificaciones

    donde p = simulacion.peso_resultado. Con p = 0 la nota vuelve a depender
    solo del proceso, que era el comportamiento anterior: se podia hundir la
    empresa y aprobar igual si se usaba el vocabulario correcto. Eso era un
    examen; el resultado es lo que lo convierte en una decision.

    La penalizacion por restricciones ya esta incluida en cada puntaje_paso
    (ver calcular_puntaje_paso), asi que NO se vuelve a restar aqui.
    """
    pasos_validos = list(intento.pasos.filter(es_valido=True))
    if not pasos_validos:
        return 0.0
    promedio_pasos = mean(float(p.puntaje_paso) for p in pasos_validos)
    base = max(0, min(100, promedio_pasos))

    peso = max(0, min(100, int(getattr(intento.simulacion, 'peso_resultado', 0) or 0)))
    resultado = resultado_del_caso(intento) if peso else None
    if resultado:
        proporcion = peso / 100.0
        base = base * (1 - proporcion) + resultado['puntaje'] * proporcion

    bonos = calcular_bonificaciones(intento, pasos_validos)
    return round(max(0, min(100, base + bonos['total'])), 2)


def resultado_del_caso(intento):
    """Como quedo la empresa al final, de 0 a 100.

    Esto es lo que separa una simulacion de decisiones de un examen: no basta
    con razonar bien y nombrar los conceptos, hay que dejar el caso en mejor
    estado. Se mide primero con las condiciones de exito del docente, que son su
    definicion explicita de "lo lograste"; si no configuro ninguna, se usa la
    salud ponderada de los indicadores.
    """
    simulacion = intento.simulacion
    estado = intento.estado_actual or {}
    condiciones = list(simulacion.condiciones_exito.filter(activo=True))

    if condiciones:
        cumplidas = []
        for condicion in condiciones:
            valor = estado.get(condicion.codigo_indicador)
            if not isinstance(valor, (int, float)):
                continue
            cumplidas.append(cumple_operador(
                condicion.operador, float(valor), float(condicion.valor_objetivo)))
        if cumplidas:
            logradas = sum(1 for c in cumplidas if c)
            return {
                'puntaje': round(logradas / len(cumplidas) * 100, 2),
                'fuente': 'condiciones_exito',
                'logradas': logradas,
                'de': len(cumplidas),
            }

    indicadores = list(simulacion.indicadores.filter(activo=True))
    total_peso = 0.0
    acumulado = 0.0
    for indicador in indicadores:
        valor = estado.get(indicador.codigo)
        if not isinstance(valor, (int, float)):
            continue
        peso = max(0.0, float(getattr(indicador, 'peso_salud', 1) or 0))
        if peso <= 0:
            continue
        acumulado += desempeno_indicador(indicador, valor) * peso
        total_peso += peso
    if total_peso <= 0:
        return None
    return {
        'puntaje': round(acumulado / total_peso, 2),
        'fuente': 'salud_indicadores',
        'logradas': None,
        'de': None,
    }


def calcular_bonificaciones(intento, pasos_validos=None):
    """Premia el proceso, no solo el acierto: pronosticar bien antes de decidir,
    reflexionar despues de ver las consecuencias, y corregir el rumbo entre
    rondas. Son puntos que SUMAN sobre la nota base, nunca restan, porque el
    pronostico y la reflexion son opcionales para el estudiante.
    """
    simulacion = intento.simulacion
    if pasos_validos is None:
        pasos_validos = list(intento.pasos.filter(es_valido=True))
    pasos = sorted(pasos_validos, key=lambda p: p.numero)
    detalle = []
    caso = (intento.configuracion_snapshot or {}).get('caso') or {}
    parametros = caso.get('parametros') if isinstance(caso, dict) else None
    parametros = parametros if isinstance(parametros, dict) else (simulacion.parametros or {})
    rondas_cfg = parametros.get('rondas') or []
    claves_explicitas = {
        clave: any(isinstance(r, dict) and clave in r for r in rondas_cfg)
        for clave in ('pedir_pronostico', 'pedir_reflexion')
    }

    def solicita(paso, clave):
        ronda = next(
            (r for r in rondas_cfg if isinstance(r, dict) and r.get('numero') == paso.numero),
            None,
        )
        if ronda is None and 0 <= paso.numero - 1 < len(rondas_cfg):
            candidata = rondas_cfg[paso.numero - 1]
            ronda = candidata if isinstance(candidata, dict) else {}
        if claves_explicitas.get(clave):
            return bool((ronda or {}).get(clave, False))
        if clave == 'pedir_pronostico':
            return any((p.pronostico_resultado or {}).get('estado') for p in pasos)
        if clave == 'pedir_reflexion':
            return any((p.reflexion or '').strip() for p in pasos)
        return False

    def _bono(clave, etiqueta, tope, logrados, total, explicacion):
        tope = int(tope or 0)
        if not tope or not total:
            return 0.0
        puntos = round(tope * (logrados / total), 2)
        detalle.append({
            'clave': clave, 'etiqueta': etiqueta, 'puntos': puntos, 'tope': tope,
            'logrados': logrados, 'de': total, 'explicacion': explicacion,
        })
        return puntos

    pasos_pronostico = [p for p in pasos if solicita(p, 'pedir_pronostico')]
    aciertos = sum(
        1 for p in pasos
        if p in pasos_pronostico and (p.pronostico_resultado or {}).get('estado') == 'acierto'
    )
    total_pronostico = _bono(
        'pronostico', 'Pronostico acertado', getattr(simulacion, 'bonus_pronostico', 0),
        aciertos, len(pasos_pronostico),
        'Anticipaste hacia donde se moveria el indicador antes de decidir.',
    )

    pasos_reflexion = [p for p in pasos if solicita(p, 'pedir_reflexion')]
    reflexiones = sum(1 for p in pasos_reflexion if (p.reflexion or '').strip())
    total_reflexion = _bono(
        'reflexion', 'Reflexion despues de decidir', getattr(simulacion, 'bonus_reflexion', 0),
        reflexiones, len(pasos_reflexion),
        'Explicaste por que reacciono asi la empresa y que cambiarias.',
    )

    mejoras = sum(
        1 for anterior, actual in zip(pasos, pasos[1:])
        if float(actual.puntaje_paso) > float(anterior.puntaje_paso)
    )
    total_adaptacion = _bono(
        'adaptacion', 'Mejora entre rondas', getattr(simulacion, 'bonus_adaptacion', 0),
        mejoras, max(len(pasos) - 1, 0),
        'Corregiste el rumbo: cada ronda fue mejor que la anterior.',
    )

    return {
        'total': round(total_pronostico + total_reflexion + total_adaptacion, 2),
        'detalle': detalle,
    }


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
        desempeno = desempeno_indicador(indicador, valor) / 100
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
    snapshot = intento.configuracion_snapshot or {}
    caso_snapshot = snapshot.get('caso') or {}
    indicadores_cfg = snapshot.get('indicadores') or []
    if indicadores_cfg:
        estado_inicial = {
            item['codigo']: float(item.get('valor_inicial', 0))
            for item in indicadores_cfg
        }
        metadatos = {item['codigo']: item for item in indicadores_cfg}
    else:
        estado_inicial = construir_estado_inicial(intento.simulacion)
        metadatos = {
            item.codigo: {'nombre': item.nombre, 'unidad': item.unidad}
            for item in intento.simulacion.indicadores.filter(activo=True)
        }
    estado_final = intento.estado_actual or {}
    cambios = []
    for clave in estado_inicial:
        inicial = estado_inicial.get(clave, 0)
        final = estado_final.get(clave, 0)
        try:
            inicial_d = Decimal(str(inicial)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            final_d = Decimal(str(final)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        except (InvalidOperation, TypeError, ValueError):
            continue
        diff = (final_d - inicial_d).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        meta = metadatos.get(clave, {})
        nombre = meta.get('nombre') or clave.replace('_', ' ').title()
        unidad = meta.get('unidad') or ''
        def legible(numero):
            texto = f'{numero:.2f}'.replace('.', ',')
            return f'{texto} {unidad}'.strip()
        if diff > 0:
            cambios.append(f'{nombre}: {legible(inicial_d)} → {legible(final_d)} (+{legible(diff)})')
        elif diff < 0:
            cambios.append(f'{nombre}: {legible(inicial_d)} → {legible(final_d)} ({legible(diff)})')
        else:
            cambios.append(f'{nombre}: {legible(inicial_d)} (sin cambios)')
    restricciones = sum(1 for p in intento.pasos.all() if p.alertas_restricciones)
    condiciones = snapshot.get('condiciones_exito') or []
    restricciones_finales = snapshot.get('restricciones') or []
    metas_evaluadas = [
        c for c in condiciones
        if isinstance(estado_final.get(c.get('codigo_indicador')), (int, float))
    ]
    metas_logradas = sum(
        1 for c in metas_evaluadas
        if cumple_operador(
            c.get('operador', '='),
            estado_final.get(c.get('codigo_indicador')),
            c.get('valor_objetivo', 0),
        )
    )
    limites_evaluados = [
        r for r in restricciones_finales
        if isinstance(estado_final.get(r.get('codigo_indicador')), (int, float))
    ]
    limites_cumplidos = sum(
        1 for r in limites_evaluados
        if cumple_operador(
            r.get('operador', '='),
            estado_final.get(r.get('codigo_indicador')),
            r.get('valor_limite', 0),
        )
    )
    rondas_validas = intento.pasos.filter(es_valido=True).count()
    intentos_invalidos = intento.pasos.filter(es_valido=False).count()
    partes = []
    # Debrief REFLEXIVO con IA (ciclo de Kolb): lo mas importante para aprender.
    try:
        from simulador.ia_service import generar_debriefing_ia
        reflexivo = generar_debriefing_ia(intento)
    except Exception:
        reflexivo = ''
    if reflexivo:
        partes += ['=== QUE APRENDISTE ===', reflexivo, '']
    partes += [
        f'=== RESUMEN ===',
        f'Simulacion: {caso_snapshot.get("titulo", intento.simulacion.titulo)}',
        f'Estudiante: {intento.estudiante.get_full_name() or intento.estudiante.username}',
        f'Puntaje final: {intento.puntuacion_final} - {obtener_nivel_resultado(float(intento.puntuacion_final))}',
        f'Rondas validas completadas: {rondas_validas}',
        f'Intentos invalidos: {intentos_invalidos}',
        f'Restricciones operativas incumplidas en {restricciones} paso(s).',
        (
            f'Metas finales logradas: {metas_logradas} de {len(metas_evaluadas)}.'
            if metas_evaluadas else 'Metas finales configuradas: ninguna.'
        ),
        (
            f'Limites tecnicos finales cumplidos: {limites_cumplidos} de {len(limites_evaluados)}.'
            if limites_evaluados else 'Limites tecnicos finales configurados: ninguno.'
        ),
        f'',
        f'Evolucion de indicadores:',
    ] + [f'  {c}' for c in cambios]
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
    intento.debriefing_final = re.sub(
        r'\*\*(.*?)\*\*', r'\1', generar_debriefing_final(intento), flags=re.DOTALL,
    ).replace('### ', '').replace('## ', '')
    intento.finalizado = True
    intento.fecha_fin = timezone.now()
    intento.save(update_fields=[
        'puntuacion_final', 'nivel_resultado', 'retroalimentacion_final',
        'debriefing_final', 'finalizado', 'fecha_fin',
    ])
    registrar_resultado_juego(intento)
    programar_retos_refuerzo(intento)
    return intento


def programar_retos_refuerzo(intento):
    from datetime import timedelta
    from simulador.models import ConceptoEsperadoRonda, RetoRefuerzo

    if RetoRefuerzo.objects.filter(intento_origen=intento).exists():
        return []

    faltantes = []
    for paso in intento.pasos.order_by('numero'):
        for nombre in (paso.evaluacion_detalle or {}).get('conceptos_faltantes') or []:
            if nombre and nombre not in faltantes:
                faltantes.append(str(nombre))

    conceptos = faltantes[:2]
    if not conceptos:
        conceptos = list(
            ConceptoEsperadoRonda.objects.filter(
                simulacion=intento.simulacion, activo=True,
            ).order_by('numero_ronda', 'nombre').values_list('nombre', flat=True)[:2]
        )
    if not conceptos:
        conceptos = [intento.simulacion.tema or intento.simulacion.titulo]

    retos = []
    for idx, concepto in enumerate(conceptos[:2]):
        dias = 1 if idx == 0 else 3
        pregunta = (
            f'Aplica "{concepto}" en un caso distinto al que jugaste: '
            f'que decision tomarias, que indicador observarias y que trade-off aceptarias?'
        )
        retos.append(RetoRefuerzo.objects.create(
            estudiante=intento.estudiante,
            simulacion=intento.simulacion,
            intento_origen=intento,
            concepto=concepto[:200],
            pregunta=pregunta,
            fecha_disponible=timezone.now() + timedelta(days=dias),
            usuario_creacion=intento.estudiante,
        ))
    return retos


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
    salud = _calcular_score_indicadores(intento.simulacion, intento.estado_actual or {})
    condiciones = list(intento.simulacion.condiciones_exito.filter(activo=True))
    metas_cumplidas = bool(condiciones) and all(
        isinstance((intento.estado_actual or {}).get(c.codigo_indicador), (int, float))
        and cumple_operador(
            c.operador,
            (intento.estado_actual or {}).get(c.codigo_indicador),
            c.valor_objetivo,
        )
        for c in condiciones
    )
    if nota >= 90 and salud >= 80 and metas_cumplidas:
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


def situacion_de_ronda(simulacion, numero_ronda, configuracion_snapshot=None):
    caso = (configuracion_snapshot or {}).get('caso') or {}
    parametros = caso.get('parametros') if isinstance(caso, dict) else None
    parametros = parametros if isinstance(parametros, dict) else (simulacion.parametros or {})
    rondas = parametros.get('rondas') or []
    valor = next(
        (item for item in rondas if isinstance(item, dict) and item.get('numero') == numero_ronda),
        None,
    )
    if valor is None:
        indice = numero_ronda - 1
        valor = rondas[indice] if 0 <= indice < len(rondas) else None
    if valor is not None:
        if isinstance(valor, dict):
            situacion = valor.get('situacion') or valor.get('enunciado') or ''
            titulo = valor.get('titulo') or ''
            proposito = valor.get('proposito') or ''
            partes = [texto for texto in [titulo, situacion, proposito] if texto]
            return '\n\n'.join(partes)
        return str(valor)
    return ''


def maximo_decisiones_intento(intento):
    caso = (intento.configuracion_snapshot or {}).get('caso') or {}
    try:
        return int(caso.get('maximo_decisiones') or intento.simulacion.maximo_decisiones)
    except (TypeError, ValueError):
        return intento.simulacion.maximo_decisiones


def obtener_escenario_inicial(simulacion):
    inicial = simulacion.escenarios_arbol.filter(activo=True, es_inicial=True).order_by('orden').first()
    if inicial:
        return inicial
    return simulacion.escenarios_arbol.filter(activo=True).order_by('orden').first()


def ejecutar_decision_arbol(intento, decision, pronostico=None, tradeoff_aceptado=''):
    estado_antes = dict(intento.estado_actual or {})
    recursos_antes = dict(intento.recursos_actuales or {})
    impacto = dict(decision.impacto or {})
    estado_despues = aplicar_impacto(estado_antes, impacto)
    estado_despues = limitar_estado_por_min_max(
        intento.simulacion, estado_despues, intento.configuracion_snapshot,
    )
    recursos_despues = limitar_recursos_por_min_max(
        intento.simulacion, recursos_antes, intento.configuracion_snapshot,
    )
    alertas = validar_restricciones(
        intento.simulacion, estado_despues, intento.configuracion_snapshot,
    )
    penalizacion = calcular_penalizaciones(alertas)
    puntaje_paso = calcular_puntaje_paso(float(decision.puntaje_base), penalizacion)
    pronostico = normalizar_pronostico(pronostico)
    pronostico_resultado = evaluar_pronostico(pronostico, estado_antes, estado_despues)
    tradeoff_aceptado = (tradeoff_aceptado or '').strip()[:1000]
    tradeoff_resultado = evaluar_tradeoff(
        intento.simulacion, tradeoff_aceptado, estado_antes, estado_despues,
        recursos_antes, recursos_despues,
    )
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
        pronostico_indicador=pronostico['indicador'],
        pronostico_direccion=pronostico['direccion'],
        pronostico_justificacion=pronostico['justificacion'],
        pronostico_resultado=pronostico_resultado,
        tradeoff_aceptado=tradeoff_aceptado,
        tradeoff_resultado=tradeoff_resultado,
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


def _registrar_paso_invalido_dinamico(
    intento, decision, justificacion, situacion_actual, estado_antes, recursos_antes,
    validacion, pronostico, tradeoff_aceptado, auditoria=None,
):
    """Registra un rechazo sin aplicar impactos ni avanzar como ronda válida."""
    auditoria = auditoria or {}
    puntaje_sugerido = max(0, min(100, float(validacion.get('puntaje_maximo', 0))))
    detalle = dict(auditoria.get('evaluacion_detalle') or {})
    detalle.update({
        'tipo': 'validacion',
        'valida': False,
        'motivo': validacion['motivo'],
        'tipo_error': validacion['tipo_error'],
        'puntaje_maximo': validacion.get('puntaje_maximo', 0),
    })
    paso = intento.pasos.create(
        numero=intento.pasos.count() + 1,
        es_valido=False,
        tipo_paso='INVALIDO',
        situacion_presentada=situacion_actual,
        decision_estudiante=decision,
        justificacion_estudiante=justificacion,
        evaluacion_ia=validacion['motivo'],
        evaluacion_detalle=detalle,
        respuesta_ia_estructurada=auditoria.get('respuesta_ia_estructurada') or {},
        modelo_ia=auditoria.get('modelo_ia', ''),
        api_ia=auditoria.get('api_ia', ''),
        prompt_version=auditoria.get('prompt_version', ''),
        esquema_ia_version=auditoria.get('esquema_ia_version', ''),
        tokens_entrada=int(auditoria.get('tokens_entrada') or 0),
        tokens_salida=int(auditoria.get('tokens_salida') or 0),
        prompt_ia_enviado=auditoria.get('prompt_ia_enviado', ''),
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
        pronostico_indicador=pronostico['indicador'],
        pronostico_direccion=pronostico['direccion'],
        pronostico_justificacion=pronostico['justificacion'],
        pronostico_resultado=(
            {
                'estado': 'sin_aplicar',
                'mensaje': 'No se comparo el pronostico porque la jugada no fue valida.',
            }
            if pronostico.get('indicador') else {}
        ),
        tradeoff_aceptado=tradeoff_aceptado,
        tradeoff_resultado=(
            {
                'estado': 'sin_aplicar',
                'mensaje': 'No se analizo el trade-off porque la jugada no fue valida.',
                'aceptado': tradeoff_aceptado,
                'ganancias': [],
                'sacrificios': [],
            }
            if tradeoff_aceptado else {}
        ),
    )
    ronda_actual = intento.numero_ronda_actual
    intento.intentos_invalidos_actuales += 1
    update_fields = ['intentos_invalidos_actuales']
    if intento.intentos_invalidos_actuales >= intento.max_intentos_invalidos_por_ronda:
        intento.numero_ronda_actual = ronda_actual + 1
        intento.intentos_invalidos_actuales = 0
        siguiente_configurada = situacion_de_ronda(
            intento.simulacion, intento.numero_ronda_actual, intento.configuracion_snapshot,
        )
        intento.situacion_actual = siguiente_configurada or (
            f'Ronda {intento.numero_ronda_actual}: Se agotaron los intentos de la ronda anterior. '
            f'Replantea la solucion con una decision concreta, conceptos tecnicos y justificacion.'
        )
        update_fields.extend(['numero_ronda_actual', 'situacion_actual'])
        if ronda_actual >= maximo_decisiones_intento(intento):
            intento.save(update_fields=update_fields)
            finalizar_intento(intento)
            return paso
    intento.save(update_fields=update_fields)
    return paso


def ejecutar_ronda_ia_dinamica(intento, decision, justificacion, accion=None, pronostico=None, tradeoff_aceptado=''):
    # Modo hibrido: si el estudiante ELIGIO una decision (accion), su texto se
    # suma a la decision (la IA evalua la justificacion) y su impacto_base es la
    # CONSECUENCIA real sobre los indicadores. Si no elige, es texto libre.
    decision_escrita = (decision or '').strip()
    accion_impacto = {}
    accion_costo = {}
    if accion is not None:
        texto_accion = getattr(accion, 'texto_visible', accion.texto)
        descripcion_accion = getattr(accion, 'descripcion_visible', accion.descripcion)
        decision = (f'{texto_accion}. {decision}').strip() if decision else texto_accion
        accion_impacto = {k: v for k, v in (accion.impacto_base or {}).items() if isinstance(v, (int, float))}
        accion_costo = dict(getattr(accion, 'costo_recursos', {}) or {})
    estado_antes = dict(intento.estado_actual or {})
    recursos_antes = dict(intento.recursos_actuales or construir_recursos_iniciales(intento.simulacion))
    pronostico = normalizar_pronostico(pronostico)
    tradeoff_aceptado = (tradeoff_aceptado or '').strip()[:1000]
    numero = intento.pasos.count() + 1
    ronda_actual = intento.numero_ronda_actual
    reglas_respuesta = configuracion_respuesta_ronda(
        intento.simulacion, ronda_actual, intento.configuracion_snapshot,
    )
    caso_snapshot = (intento.configuracion_snapshot or {}).get('caso') or {}
    situacion_actual = (
        intento.situacion_actual
        or caso_snapshot.get('situacion_inicial')
        or caso_snapshot.get('contexto')
        or intento.simulacion.situacion_inicial
        or intento.simulacion.contexto
    )
    if reglas_respuesta['pronostico_obligatorio'] and not (
        pronostico.get('indicador') and pronostico.get('direccion')
    ):
        return _registrar_paso_invalido_dinamico(
            intento, decision, justificacion, situacion_actual, estado_antes,
            recursos_antes,
            _resultado_validacion(
                False, 'Selecciona el indicador y la dirección de tu pronóstico.', 0,
                TIPO_ERROR_PRONOSTICO_REQUERIDO,
            ),
            pronostico, tradeoff_aceptado,
        )
    if reglas_respuesta['tradeoff_obligatorio'] and len(tradeoff_aceptado) < 8:
        return _registrar_paso_invalido_dinamico(
            intento, decision, justificacion, situacion_actual, estado_antes,
            recursos_antes,
            _resultado_validacion(
                False, 'Explica brevemente qué costo, riesgo o sacrificio aceptas.', 0,
                TIPO_ERROR_TRADEOFF_REQUERIDO,
            ),
            pronostico, tradeoff_aceptado,
        )
    if accion is not None and not accion_habilitada_por_historial(intento, accion):
        return _registrar_paso_invalido_dinamico(
            intento, decision, justificacion, situacion_actual, estado_antes,
            recursos_antes,
            _resultado_validacion(
                False,
                'Esta opción no corresponde a la estrategia elegida anteriormente.',
                0,
                TIPO_ERROR_ACCION_NO_DISPONIBLE,
            ),
            pronostico,
            tradeoff_aceptado,
        )
    validacion = validar_respuesta_estudiante(
        decision,
        justificacion,
        simulacion=intento.simulacion,
        situacion_actual=situacion_actual,
        opcion_predefinida=accion is not None,
        requerir_justificacion=justificacion_obligatoria(
            intento.simulacion, ronda_actual, intento.configuracion_snapshot,
        ),
        minimo_justificacion=reglas_respuesta['minimo_justificacion'],
    )

    if not validacion['valida']:
        return _registrar_paso_invalido_dinamico(
            intento, decision, justificacion, situacion_actual, estado_antes,
            recursos_antes, validacion, pronostico, tradeoff_aceptado,
        )
    else:
        if accion is not None and reglas_respuesta['bloquear_contradiccion']:
            contradiccion_local = detectar_contradiccion_explicita(texto_accion, justificacion)
            if contradiccion_local:
                return _registrar_paso_invalido_dinamico(
                    intento, decision, justificacion, situacion_actual, estado_antes,
                    recursos_antes,
                    _resultado_validacion(
                        False,
                        f'{contradiccion_local} Revisa tu respuesta antes de continuar.',
                        0,
                        TIPO_ERROR_CONTRADICCION,
                    ),
                    pronostico,
                    tradeoff_aceptado,
                    auditoria={'evaluacion_detalle': {
                        'decision_justificacion_coherentes': False,
                        'coherencia_motivo': contradiccion_local,
                        'seleccion_registrada': {
                            'accion_id': getattr(accion, 'pk', None),
                            'nombre': texto_accion,
                            'descripcion': descripcion_accion,
                            'ronda': ronda_actual,
                            'respuesta_adicional': decision_escrita,
                        },
                    }},
                )
        from simulador.ia_service import orden_proveedores, evaluar_ronda_con_proveedores

        # `ia_habilitada=False` significa SIN IA de verdad: ni se llama al
        # proveedor. Los casos que vienen de un simulador del docente ya traen
        # su respuesta correcta, el puntaje de cada alternativa y su rubrica,
        # asi que la nota sale de aritmetica y palabras clave. Antes este campo
        # existia en el formulario pero el motor lo ignoraba.
        if intento.simulacion.ia_habilitada and orden_proveedores():
            # Intenta OpenAI y/o DeepSeek (segun configuracion); si todos fallan
            # (sin cuota/timeout) cae a la rubrica local.
            try:
                respuesta = evaluar_ronda_con_proveedores(
                    intento, decision, justificacion,
                    opcion_predefinida=getattr(accion, 'texto_visible', accion.texto) if accion is not None else '',
                    pronostico=pronostico,
                    tradeoff_aceptado=tradeoff_aceptado,
                )
                detalle = respuesta.get('evaluacion_detalle') or {}
                detalle.setdefault('tipo', 'ia_rubrica_docente')
                respuesta['evaluacion_detalle'] = detalle
            except Exception as e:
                respuesta = _fallback_conceptos_o_mock(
                    intento, ronda_actual, decision, justificacion, situacion_actual,
                    opcion_predefinida=bool(accion),
                    fuentes_evaluacion=reglas_respuesta['fuentes_evaluacion'],
                    pronostico=pronostico, tradeoff_aceptado=tradeoff_aceptado,
                )
                detalle = respuesta.get('evaluacion_detalle') or {}
                detalle['error_ia'] = str(e)
                respuesta['evaluacion_detalle'] = detalle
        else:
            respuesta = _fallback_conceptos_o_mock(
                intento, ronda_actual, decision, justificacion, situacion_actual,
                opcion_predefinida=bool(accion),
                fuentes_evaluacion=reglas_respuesta['fuentes_evaluacion'],
                pronostico=pronostico, tradeoff_aceptado=tradeoff_aceptado,
            )

        detalle_coherencia = respuesta.get('evaluacion_detalle') or {}
        if (
            accion is not None
            and reglas_respuesta['bloquear_contradiccion']
            and detalle_coherencia.get('decision_justificacion_coherentes') is False
        ):
            motivo = (
                detalle_coherencia.get('coherencia_motivo')
                or 'La explicación desarrolla una acción distinta de la opción seleccionada.'
            )
            detalle_coherencia['seleccion_registrada'] = {
                'accion_id': getattr(accion, 'pk', None),
                'nombre': texto_accion,
                'descripcion': descripcion_accion,
                'ronda': ronda_actual,
                'respuesta_adicional': decision_escrita,
            }
            respuesta['evaluacion_detalle'] = detalle_coherencia
            return _registrar_paso_invalido_dinamico(
                intento, decision, justificacion, situacion_actual, estado_antes,
                recursos_antes,
                _resultado_validacion(
                    False,
                    f'La decisión seleccionada contradice la explicación: {motivo} '
                    'Revisa tu respuesta antes de continuar.',
                    0,
                    TIPO_ERROR_CONTRADICCION,
                ),
                pronostico,
                tradeoff_aceptado,
                auditoria=respuesta,
            )

        from simulador.services.motor_dinamico import aplicar_opcion_dinamica
        caso_snapshot = (intento.configuracion_snapshot or {}).get('caso') or {}
        parametros_snapshot = caso_snapshot.get('parametros') if isinstance(caso_snapshot, dict) else None
        estado_motor, impacto_motor, opcion_detectada, confianza_opcion = aplicar_opcion_dinamica(
            intento.simulacion, estado_antes, decision, justificacion, ronda_actual,
            parametros_snapshot,
        )
        accion_detectada = accion or detectar_accion_sugerida(
            intento.simulacion, decision, intento.configuracion_snapshot,
        )
        if accion_detectada and not accion_habilitada_por_historial(intento, accion_detectada):
            accion_detectada = None
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
        errores_impacto = validar_impacto(intento.simulacion, impacto, intento.configuracion_snapshot)
        if errores_impacto:
            impacto = {}

        if impacto_motor:
            impacto = {**impacto, **impacto_motor}
        if impacto_accion:
            impacto = {**impacto, **impacto_accion}
        modificables = indicadores_modificables_ronda(
            intento.simulacion, ronda_actual, intento.configuracion_snapshot,
        )
        impacto = {codigo: delta for codigo, delta in impacto.items() if codigo in modificables}
        puntaje_sugerido = max(0, min(100, float(respuesta.get('puntaje_sugerido', 0))))
        # En un caso con respuesta correcta, la alternativa elegida puntua por
        # si sola. Sin esto, elegir el proveedor equivocado valia lo mismo que
        # elegir el correcto mientras la justificacion estuviera bien escrita.
        puntaje_opcion = _puntaje_de_la_opcion(accion)
        pide_justificacion_escrita = justificacion_obligatoria(
            intento.simulacion, ronda_actual, intento.configuracion_snapshot,
        )
        if puntaje_opcion is not None:
            respuesta.setdefault('evaluacion_detalle', {})
            detalle_opcion = respuesta['evaluacion_detalle']
            detalle_opcion['puntaje_opcion'] = puntaje_opcion
            detalle_opcion['puntaje_rubrica_previo'] = puntaje_sugerido
            if pide_justificacion_escrita:
                # Elegir bien y explicar bien pesan lo mismo.
                puntaje_sugerido = round((puntaje_opcion + puntaje_sugerido) / 2, 2)
            else:
                puntaje_sugerido = puntaje_opcion
            detalle_opcion['puntaje_combinado'] = puntaje_sugerido
            retro_opcion = (getattr(accion, 'retroalimentacion', '') or '').strip()
            if retro_opcion:
                detalle_opcion['retroalimentacion_opcion'] = retro_opcion
                respuesta['evaluacion'] = (
                    f"{retro_opcion} {respuesta.get('evaluacion', '')}".strip()
                )
        # El estado se deriva siempre del impacto ya filtrado por fase. Así una
        # opción dinámica tampoco puede saltarse los indicadores congelados.
        estado_despues = aplicar_impacto(estado_antes, impacto)
        estado_despues = limitar_estado_por_min_max(
            intento.simulacion, estado_despues, intento.configuracion_snapshot,
        )
        recursos_despues = limitar_recursos_por_min_max(
            intento.simulacion,
            aplicar_costo_recursos(recursos_antes, costo_recursos),
            intento.configuracion_snapshot,
        )
        estado_tras_decision = dict(estado_despues)
        impacto_decision_real = _delta_estados(estado_antes, estado_tras_decision)
        # Fase B: eventos dinamicos -- la empresa reacciona con sucesos segun el
        # estado/ronda (un cliente cancela, aparece una crisis, etc.).
        estado_despues, eventos_msgs = aplicar_eventos(
            intento.simulacion, estado_despues, ronda_actual, intento.configuracion_snapshot,
        )
        impacto_evento_real = _delta_estados(estado_tras_decision, estado_despues)
        impacto_neto = _delta_estados(estado_antes, estado_despues)
        pronostico_resultado = evaluar_pronostico(pronostico, estado_antes, estado_despues)
        tradeoff_resultado = evaluar_tradeoff(
            intento.simulacion, tradeoff_aceptado, estado_antes, estado_despues,
            recursos_antes, recursos_despues,
        )
        # Solo se penaliza por indicadores que la decision del estudiante movio
        # este turno: no se castiga un estado inicial malo que el no causo. Ademas
        # se aplica un tope para que las restricciones nunca aplasten la nota.
        alertas = validar_restricciones(
            intento.simulacion, estado_despues, intento.configuracion_snapshot,
        )
        alertas_recursos = validar_recursos(
            intento.simulacion, recursos_despues, intento.configuracion_snapshot,
        )
        indicadores_movidos = set(impacto_neto.keys())
        # Solo se penaliza un indicador que el estudiante movio este turno Y que
        # NO acerco a cumplir su restriccion. Si lo mejoro (aunque siga fuera de
        # rango) va por buen camino: premiar el avance, no castigar el progreso.
        alertas = [
            a for a in alertas
            if a.get('indicador') in indicadores_movidos
            and not _restriccion_mejoro(a, estado_antes, estado_despues)
        ]
        penalizacion_recursos = min(15, len(alertas_recursos) * 5)
        penalizacion = min(PENALIZACION_MAX_PASO, calcular_penalizaciones(alertas) + penalizacion_recursos)
        puntaje_paso = calcular_puntaje_paso(puntaje_sugerido, penalizacion)
        # Tope de calidad: una respuesta valida pero debil (corta/generica/sin
        # justificacion) avanza, pero su nota se limita segun el nivel detectado.
        tope_calidad = float(validacion.get('puntaje_maximo', 100))
        if tope_calidad < 100:
            puntaje_paso = min(puntaje_paso, tope_calidad)
        evaluacion = respuesta.get('evaluacion', '')
        resumen_impacto_real = _resumen_impacto_indicadores(
            intento.simulacion, impacto_neto, estado_antes,
        )
        if resumen_impacto_real and resumen_impacto_real not in evaluacion:
            evaluacion = f'{evaluacion} Impacto real de la jugada: {resumen_impacto_real}'.strip()
        evaluacion_detalle = respuesta.get('evaluacion_detalle') or {
            'tipo': 'mock',
            'puntaje_sugerido': puntaje_sugerido,
            'evaluacion': evaluacion,
        }
        evaluacion_detalle.update({
            'origen_impacto': (
                'reglas_configuradas_reproducibles'
                if impacto_neto else 'sin_consecuencia_configurada'
            ),
            'impacto_decision': impacto_decision_real,
            'impacto_evento': impacto_evento_real,
            'impacto_neto': impacto_neto,
            'indicadores_modificables': sorted(modificables),
        })
        if accion is not None:
            evaluacion_detalle['seleccion_registrada'] = {
                'accion_id': getattr(accion, 'pk', None),
                'nombre': texto_accion,
                'descripcion': descripcion_accion,
                'ronda': ronda_actual,
                'respuesta_adicional': decision_escrita,
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
        prompt_ia_enviado = respuesta.get('prompt_ia_enviado', '')
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
        prompt_ia_enviado=prompt_ia_enviado,
        impacto_calculado=impacto_neto,
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
        pronostico_indicador=pronostico['indicador'],
        pronostico_direccion=pronostico['direccion'],
        pronostico_justificacion=pronostico['justificacion'],
        pronostico_resultado=pronostico_resultado,
        tradeoff_aceptado=tradeoff_aceptado,
        tradeoff_resultado=tradeoff_resultado,
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

    if ronda_actual >= maximo_decisiones_intento(intento) or finalizar:
        finalizar_intento(intento)

    return paso


def _puntaje_fallback_justo(
    intento, decision, justificacion, situacion_actual, evaluacion_conceptos,
    opcion_predefinida=False,
):
    """Sin IA, el emparejador por palabras es muy literal y castiga respuestas
    buenas que no usan las palabras exactas. Para no tankear injustamente, una
    respuesta VALIDA y en tema recibe un piso honesto basado en su calidad de
    escritura y en la cobertura parcial de conceptos. No infla: las coincidencias
    de la rubrica pueden subir por encima del piso, pero el piso evita el 0/10
    en respuestas completas. El 80-100 real requiere la IA (OpenAI/DeepSeek)."""
    base = float(evaluacion_conceptos.get('puntaje_sugerido') or 0)
    validacion = validar_respuesta_estudiante(
        decision, justificacion, simulacion=intento.simulacion, situacion_actual=situacion_actual,
        opcion_predefinida=opcion_predefinida,
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


def _puntaje_de_la_opcion(accion):
    """Cuanto vale, por si sola, la alternativa que eligio el estudiante.

    Devuelve None cuando la alternativa no lleva puntaje propio: entonces la
    nota sale solo de la rubrica, como antes. Acepta tanto un objeto del ORM
    como el dict congelado en el snapshot del intento.
    """
    if accion is None:
        return None
    crudo = accion.get('puntaje') if isinstance(accion, dict) else getattr(accion, 'puntaje', None)
    if crudo is None or crudo == '':
        return None
    try:
        return max(0.0, min(100.0, float(crudo)))
    except (TypeError, ValueError):
        return None


def _fallback_conceptos_o_mock(
    intento, ronda_actual, decision, justificacion, situacion_actual,
    opcion_predefinida=False, fuentes_evaluacion=None,
    pronostico=None, tradeoff_aceptado='',
):
    fuentes = set(fuentes_evaluacion or ['decision', 'justificacion'])
    decision_conceptos = decision if 'decision' in fuentes and not opcion_predefinida else ''
    partes_justificacion = [justificacion] if 'justificacion' in fuentes else []
    if 'pronostico' in fuentes and pronostico:
        partes_justificacion.append(json.dumps(pronostico, ensure_ascii=False))
    if 'tradeoff' in fuentes and tradeoff_aceptado:
        partes_justificacion.append(tradeoff_aceptado)
    justificacion_conceptos = ' '.join(partes_justificacion)
    evaluacion_conceptos = evaluar_conceptos_esperados(
        intento.simulacion,
        ronda_actual,
        decision_conceptos,
        justificacion_conceptos,
        situacion_actual,
        configuracion_snapshot=intento.configuracion_snapshot,
        opcion_predefinida=opcion_predefinida,
    )
    if evaluacion_conceptos['tiene_conceptos']:
        puntaje_justo = _puntaje_fallback_justo(
            intento, decision, justificacion, situacion_actual, evaluacion_conceptos,
            opcion_predefinida=opcion_predefinida,
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
                'metodo_evaluacion': evaluacion_conceptos['metodo_evaluacion'],
                'opcion_predefinida': opcion_predefinida,
            },
            'impacto_sugerido': evaluacion_conceptos['impacto_sugerido'],
            'puntaje_sugerido': puntaje_justo,
            'siguiente_situacion': (
                situacion_de_ronda(
                    intento.simulacion, ronda_actual + 1, intento.configuracion_snapshot,
                )
                or f'Ronda {ronda_actual + 1}: Continua el caso considerando los indicadores actualizados y los conceptos faltantes.'
                if ronda_actual < maximo_decisiones_intento(intento) else ''
            ),
            'finalizar': False,
        }
    else:
        from simulador.ia_service import IAServiceMock
        return IAServiceMock().evaluar_ronda_dinamica(
            intento, decision, justificacion,
            opcion_predefinida='opcion configurada' if opcion_predefinida else '',
            pronostico=pronostico,
            tradeoff_aceptado=tradeoff_aceptado,
        )
