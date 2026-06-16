import re
import logging
from copy import deepcopy

logger = logging.getLogger(__name__)


def normalizar_texto(texto):
    """Normaliza texto para comparacion: minusculas, sin tildes, sin puntuacion extrana."""
    if not texto:
        return ''
    t = texto.lower().strip()
    reemplazos = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'ü': 'u', 'ñ': 'n',
    }
    for orig, dest in reemplazos.items():
        t = t.replace(orig, dest)
    t = re.sub(r'[^a-z0-9\s]', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def obtener_opciones_dinamicas(simulacion):
    return deepcopy(simulacion.parametros or {}).get('opciones_dinamicas', [])


def obtener_reglas_actualizacion(simulacion):
    return deepcopy(simulacion.parametros or {}).get('reglas_actualizacion', {})


def obtener_tipo_dinamica(simulacion):
    return (simulacion.parametros or {}).get('tipo_dinamica', '')


def obtener_nombre_opciones(simulacion):
    return (simulacion.parametros or {}).get('nombre_opciones', 'opciones')


def detectar_opcion_por_texto(simulacion, decision, justificacion):
    """Busca coincidencia del texto del estudiante contra los aliases de cada opcion."""
    opciones = obtener_opciones_dinamicas(simulacion)
    if not opciones:
        return None, 0.0

    texto_completo = f'{decision} {justificacion}'
    texto_norm = normalizar_texto(texto_completo)
    palabras_texto = set(texto_norm.split())

    mejor_opcion = None
    mejor_confianza = 0.0

    for opcion in opciones:
        aliases = opcion.get('aliases', [])
        codigo = opcion.get('codigo', '')
        nombre = opcion.get('nombre', '')

        max_conf = 0.0
        for alias in aliases:
            alias_norm = normalizar_texto(alias)
            palabras_alias = set(alias_norm.split())

            if not palabras_alias:
                continue

            # Si el alias aparece como substring en el texto normalizado
            if alias_norm in texto_norm:
                conf = len(palabras_alias) / max(len(palabras_alias), 1)
                if conf > max_conf:
                    max_conf = conf

        # Tambien buscar codigo (min 2 chars) y nombre directamente
        codigo_norm = normalizar_texto(codigo)
        nombre_norm = normalizar_texto(nombre)

        if codigo_norm and len(codigo_norm) >= 2 and codigo_norm in texto_norm:
            max_conf = max(max_conf, 0.8)
        if nombre_norm and len(nombre_norm) >= 3 and nombre_norm in texto_norm:
            max_conf = max(max_conf, 0.7)

        if max_conf > mejor_confianza:
            mejor_confianza = max_conf
            mejor_opcion = opcion

    return mejor_opcion, round(mejor_confianza, 2)


def aplicar_opcion_dinamica(simulacion, estado_antes, decision, justificacion, numero_ronda):
    """Aplica los indicadores de la opcion detectada al estado_antes y devuelve estado_despues e impacto."""
    opcion, confianza = detectar_opcion_por_texto(simulacion, decision, justificacion)

    reglas = obtener_reglas_actualizacion(simulacion)
    rondas_aplica = reglas.get('rondas_aplica', [])
    confianza_minima = reglas.get('confianza_minima', 0.6)

    if not opcion:
        return deepcopy(estado_antes or {}), {}, None, 0.0

    if rondas_aplica and numero_ronda not in rondas_aplica:
        return deepcopy(estado_antes or {}), {}, opcion, confianza

    if confianza < confianza_minima:
        return deepcopy(estado_antes or {}), {}, opcion, confianza

    modo = reglas.get('modo', 'copiar_indicadores_opcion')
    estado_actual = deepcopy(estado_antes or {})
    indicadores_opcion = opcion.get('indicadores', {})

    impacto = {}
    estado_despues = dict(estado_actual)

    if modo == 'copiar_indicadores_opcion':
        for codigo, valor in indicadores_opcion.items():
            if codigo not in estado_actual:
                estado_despues[codigo] = float(valor)
                impacto[codigo] = float(valor)
            else:
                estado_despues[codigo] = float(valor)
                impacto[codigo] = round(float(valor) - float(estado_actual.get(codigo, 0)), 2)

    return estado_despues, impacto, opcion, confianza


def calcular_impacto(estado_antes, estado_despues):
    """Calcula impacto como diferencia entre estado_despues y estado_antes."""
    if not estado_antes or not estado_despues:
        return {}
    impacto = {}
    for k in estado_despues:
        antes = float(estado_antes.get(k, 0))
        despues = float(estado_despues[k])
        if despues != antes:
            impacto[k] = round(despues - antes, 2)
    return impacto
