"""Comprobacion ligera del estado de los proveedores de IA configurados."""
from time import perf_counter

from django.conf import settings
from django.utils import timezone
from openai import OpenAI


def _clasificar_error(exc):
    codigo = getattr(exc, 'status_code', None)
    codigo_proveedor = str(getattr(exc, 'code', '') or '').lower()
    texto = str(exc).lower()

    if codigo == 429 or codigo_proveedor in ('credit_balance_exhausted', 'insufficient_quota'):
        if any(p in texto for p in ('credit', 'quota', 'billing', 'insufficient')):
            return 'sin_creditos', 'Sin creditos o cuota disponible'
        return 'limitado', 'Limite temporal de solicitudes alcanzado'
    if codigo == 503:
        return 'saturado', 'Servicio saturado; intenta nuevamente en unos minutos'
    if codigo in (401, 403):
        return 'credenciales', 'Clave API invalida o sin permisos'
    if codigo and codigo >= 500:
        return 'no_disponible', 'El proveedor no esta disponible temporalmente'
    if 'timeout' in texto or 'timed out' in texto:
        return 'timeout', 'La comprobacion supero el tiempo de espera'
    if 'connect' in texto or 'network' in texto:
        return 'conexion', 'No se pudo conectar con el proveedor'
    return 'error', 'El proveedor devolvio un error inesperado'


def _base(nombre, clave, modelo):
    principal = getattr(settings, 'IA_PROVIDER', '') == clave
    respaldo = getattr(settings, 'IA_FALLBACK_PROVIDER', '') == clave
    return {
        'nombre': nombre,
        'clave': clave,
        'modelo': modelo,
        'rol': 'principal' if principal else ('respaldo' if respaldo else ''),
    }


def _comprobar_openai():
    dato = _base('OpenAI', 'openai', getattr(settings, 'OPENAI_MODEL', ''))
    api_key = getattr(settings, 'OPENAI_API_KEY', '') or ''
    if not api_key:
        return {**dato, 'estado': 'sin_configurar', 'detalle': 'API key no configurada'}

    inicio = perf_counter()
    try:
        respuesta = OpenAI(api_key=api_key).responses.create(
            model=dato['modelo'],
            input='Responde solamente OK.',
            reasoning={'effort': 'low'},
            max_output_tokens=16,
            store=False,
            timeout=8,
        )
        return {
            **dato, 'estado': 'disponible', 'detalle': 'Responde correctamente',
            'latencia_ms': round((perf_counter() - inicio) * 1000),
            'modelo_respuesta': getattr(respuesta, 'model', '') or '',
        }
    except Exception as exc:
        estado, detalle = _clasificar_error(exc)
        return {
            **dato, 'estado': estado, 'detalle': detalle,
            'latencia_ms': round((perf_counter() - inicio) * 1000),
        }


def _comprobar_deepseek():
    dato = _base('DeepSeek', 'deepseek', getattr(settings, 'DEEPSEEK_MODEL', ''))
    api_key = getattr(settings, 'DEEPSEEK_API_KEY', '') or ''
    if not api_key:
        return {**dato, 'estado': 'sin_configurar', 'detalle': 'API key no configurada'}

    inicio = perf_counter()
    try:
        respuesta = OpenAI(
            api_key=api_key,
            base_url=getattr(settings, 'DEEPSEEK_BASE_URL', 'https://api.deepseek.com'),
        ).chat.completions.create(
            model=dato['modelo'],
            messages=[{'role': 'user', 'content': 'Responde solamente OK.'}],
            max_tokens=2,
            temperature=0,
            timeout=8,
        )
        return {
            **dato, 'estado': 'disponible', 'detalle': 'Responde correctamente',
            'latencia_ms': round((perf_counter() - inicio) * 1000),
            'modelo_respuesta': getattr(respuesta, 'model', '') or '',
        }
    except Exception as exc:
        estado, detalle = _clasificar_error(exc)
        return {
            **dato, 'estado': estado, 'detalle': detalle,
            'latencia_ms': round((perf_counter() - inicio) * 1000),
        }


def comprobar_estado_ia():
    """Comprueba ambos proveedores de forma independiente.

    Las llamadas consecutivas evitan que un fallo de concurrencia del cliente HTTP
    convierta dos respuestas reales en falsos ``error inesperado``.
    """
    proveedores = [_comprobar_deepseek(), _comprobar_openai()]
    ahora = timezone.localtime()
    return {
        'proveedores': proveedores,
        'comprobado_en': ahora.isoformat(),
        'comprobado_texto': ahora.strftime('%d/%m/%Y %H:%M:%S'),
    }
