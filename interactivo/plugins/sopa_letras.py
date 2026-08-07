"""Sopa de letras.

El tablero se arma en el SERVIDOR y las posiciones no viajan al navegador: el
estudiante manda las celdas que marco y el servidor comprueba si coinciden con
donde quedo cada palabra. Asi encontrar la palabra es el juego, y decir "ya la
encontre" sin marcarla no cuenta.
"""

import random
import unicodedata
from uuid import uuid4

from .base import PluginActividadBase
from .registry import register_plugin

ALFABETO = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'

# (fila, columna): horizontal, vertical y las dos diagonales, en ambos sentidos.
DIRECCIONES = [
    (0, 1), (1, 0), (1, 1), (1, -1),
    (0, -1), (-1, 0), (-1, -1), (-1, 1),
]


def _limpiar(texto):
    """Sin tildes, sin espacios y en mayusculas: lo que de verdad va al tablero."""
    plano = unicodedata.normalize('NFKD', str(texto or ''))
    plano = ''.join(c for c in plano if not unicodedata.combining(c))
    return ''.join(c for c in plano.upper() if c.isalpha())


def _cabe(tablero, palabra, fila, columna, dfila, dcolumna, lado):
    for indice, letra in enumerate(palabra):
        f = fila + dfila * indice
        c = columna + dcolumna * indice
        if not (0 <= f < lado and 0 <= c < lado):
            return False
        ocupada = tablero[f][c]
        if ocupada and ocupada != letra:
            return False
    return True


def _colocar(tablero, palabra, fila, columna, dfila, dcolumna):
    celdas = []
    for indice, letra in enumerate(palabra):
        f = fila + dfila * indice
        c = columna + dcolumna * indice
        tablero[f][c] = letra
        celdas.append([f, c])
    return celdas


def _armar_tablero(palabras, semilla=None):
    """Devuelve (tablero, colocadas). Las que no entren quedan fuera."""
    azar = random.Random(semilla)
    mas_larga = max((len(p['limpia']) for p in palabras), default=0)
    lado = max(mas_larga, 10, int(len(palabras) * 1.6))
    lado = min(lado, 18)

    tablero = [[''] * lado for _ in range(lado)]
    colocadas = []

    # De la mas larga a la mas corta: las dificiles primero entran mejor.
    for palabra in sorted(palabras, key=lambda p: -len(p['limpia'])):
        letras = palabra['limpia']
        if not letras or len(letras) > lado:
            continue
        posiciones = [
            (f, c, df, dc)
            for f in range(lado) for c in range(lado)
            for df, dc in DIRECCIONES
        ]
        azar.shuffle(posiciones)
        for fila, columna, dfila, dcolumna in posiciones:
            if _cabe(tablero, letras, fila, columna, dfila, dcolumna, lado):
                celdas = _colocar(tablero, letras, fila, columna, dfila, dcolumna)
                colocadas.append({
                    'id': palabra['id'],
                    'texto': palabra['texto'],
                    'pista': palabra.get('pista', ''),
                    'celdas': celdas,
                })
                break

    # Relleno: las casillas vacias se completan con letras al azar.
    for f in range(lado):
        for c in range(lado):
            if not tablero[f][c]:
                tablero[f][c] = azar.choice(ALFABETO)

    return tablero, colocadas


@register_plugin
class SopaLetrasPlugin(PluginActividadBase):
    codigo = 'sopa_letras'
    nombre = 'Sopa de letras'
    descripcion = 'Encuentra los terminos escondidos en el tablero.'
    schema = {
        'fields': [
            {
                'name': 'palabras',
                'type': 'list',
                'label': 'Palabras a esconder',
                'min_items': 3,
                'item_fields': [
                    {'name': 'texto', 'type': 'text', 'label': 'Palabra', 'required': True},
                    {'name': 'pista', 'type': 'text', 'label': 'Pista (opcional)', 'required': False},
                ],
            },
        ],
    }

    def normalize_config(self, config):
        palabras = []
        for raw in config.get('palabras', []):
            texto = str(raw.get('texto', '')).strip()
            limpia = _limpiar(texto)
            if not limpia:
                continue
            palabras.append({
                'id': raw.get('id') or uuid4().hex,
                'texto': texto,
                'limpia': limpia,
                'pista': str(raw.get('pista', '')).strip(),
            })

        tablero, colocadas = _armar_tablero(palabras)
        return {'tablero': tablero, 'palabras': colocadas}

    def validate_config(self, config):
        palabras = config.get('palabras', [])
        if len(palabras) < 3:
            return [
                'Debe agregar al menos tres palabras que quepan en el tablero '
                '(máximo 18 letras cada una).'
            ]
        return []

    def editor_config(self, config):
        return {
            'palabras': [
                {'id': p['id'], 'texto': p['texto'], 'pista': p.get('pista', '')}
                for p in config.get('palabras', [])
            ],
        }

    def public_config(self, config):
        # El tablero si viaja (es el juego); las posiciones NO.
        return {
            'tablero': config.get('tablero', []),
            'palabras': [
                {'id': p['id'], 'texto': p['texto'], 'pista': p.get('pista', '')}
                for p in config.get('palabras', [])
            ],
        }

    def grade(self, config, response):
        marcadas = response.get('hallazgos', {})
        aciertos = 0
        detalle = []
        for palabra in config.get('palabras', []):
            esperadas = [tuple(celda) for celda in palabra.get('celdas', [])]
            recibidas = [
                tuple(celda) for celda in marcadas.get(palabra['id'], [])
                if isinstance(celda, (list, tuple)) and len(celda) == 2
            ]
            # Vale marcarla al derecho o al reves.
            correcta = bool(esperadas) and (
                recibidas == esperadas or recibidas == list(reversed(esperadas))
            )
            aciertos += int(correcta)
            detalle.append({'palabra_id': palabra['id'], 'correcta': correcta})
        return self.result(
            aciertos, len(config.get('palabras', [])), {'palabras': detalle},
        )
