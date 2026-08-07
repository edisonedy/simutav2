"""Crucigrama.

El tablero se arma en el servidor cruzando las palabras por letras compartidas.
Al navegador viajan las casillas y las pistas, nunca las respuestas: cada
palabra se compara aqui, sin tildes ni mayusculas.
"""

import unicodedata
from uuid import uuid4

from .base import PluginActividadBase
from .registry import register_plugin


def _limpiar(texto):
    plano = unicodedata.normalize('NFKD', str(texto or ''))
    plano = ''.join(c for c in plano if not unicodedata.combining(c))
    return ''.join(c for c in plano.upper() if c.isalpha())


def _cruce_valido(ocupadas, letras, fila, columna, horizontal):
    """Comprueba que la palabra encaje sin pisar ni pegarse a otra."""
    for indice, letra in enumerate(letras):
        f = fila + (0 if horizontal else indice)
        c = columna + (indice if horizontal else 0)
        existente = ocupadas.get((f, c))
        if existente and existente != letra:
            return False
        if not existente:
            # Los costados deben estar libres, si no se forman palabras falsas.
            vecinas = [(f - 1, c), (f + 1, c)] if horizontal else [(f, c - 1), (f, c + 1)]
            if any(v in ocupadas for v in vecinas):
                return False
    # Los extremos tambien tienen que respirar.
    antes = (fila, columna - 1) if horizontal else (fila - 1, columna)
    despues = (
        (fila, columna + len(letras)) if horizontal
        else (fila + len(letras), columna)
    )
    return antes not in ocupadas and despues not in ocupadas


def _armar_crucigrama(palabras):
    """Coloca la primera palabra y va cruzando las demas. Devuelve las colocadas."""
    ordenadas = sorted(palabras, key=lambda p: -len(p['limpia']))
    ocupadas = {}
    colocadas = []

    for palabra in ordenadas:
        letras = palabra['limpia']
        if not letras:
            continue

        if not colocadas:
            posicion = (0, 0, True)
        else:
            posicion = None
            for indice, letra in enumerate(letras):
                for puesta in colocadas:
                    for pos_puesta, letra_puesta in enumerate(puesta['limpia']):
                        if letra_puesta != letra:
                            continue
                        # Se cruza en perpendicular a la palabra ya puesta.
                        if puesta['horizontal']:
                            fila = puesta['fila'] - indice
                            columna = puesta['columna'] + pos_puesta
                            horizontal = False
                        else:
                            fila = puesta['fila'] + pos_puesta
                            columna = puesta['columna'] - indice
                            horizontal = True
                        if _cruce_valido(ocupadas, letras, fila, columna, horizontal):
                            posicion = (fila, columna, horizontal)
                            break
                    if posicion:
                        break
                if posicion:
                    break
            if posicion is None:
                continue  # No cruza con nada: se queda fuera.

        fila, columna, horizontal = posicion
        celdas = []
        for indice, letra in enumerate(letras):
            f = fila + (0 if horizontal else indice)
            c = columna + (indice if horizontal else 0)
            ocupadas[(f, c)] = letra
            celdas.append([f, c])
        colocadas.append({
            **palabra,
            'fila': fila,
            'columna': columna,
            'horizontal': horizontal,
            'celdas': celdas,
        })

    if not colocadas:
        return [], 0, 0

    # Se corre todo para que empiece en (0,0).
    min_fila = min(c[0] for p in colocadas for c in p['celdas'])
    min_col = min(c[1] for p in colocadas for c in p['celdas'])
    for palabra in colocadas:
        palabra['fila'] -= min_fila
        palabra['columna'] -= min_col
        palabra['celdas'] = [[f - min_fila, c - min_col] for f, c in palabra['celdas']]

    filas = max(c[0] for p in colocadas for c in p['celdas']) + 1
    columnas = max(c[1] for p in colocadas for c in p['celdas']) + 1
    return colocadas, filas, columnas


@register_plugin
class CrucigramaPlugin(PluginActividadBase):
    codigo = 'crucigrama'
    nombre = 'Crucigrama'
    descripcion = 'Completa las palabras cruzadas a partir de sus pistas.'
    schema = {
        'fields': [
            {
                'name': 'palabras',
                'type': 'list',
                'label': 'Palabras y pistas',
                'min_items': 3,
                'item_fields': [
                    {'name': 'texto', 'type': 'text', 'label': 'Palabra', 'required': True},
                    {'name': 'pista', 'type': 'text', 'label': 'Pista', 'required': True},
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

        colocadas, filas, columnas = _armar_crucigrama(palabras)
        for numero, palabra in enumerate(colocadas, start=1):
            palabra['numero'] = numero
        return {'palabras': colocadas, 'filas': filas, 'columnas': columnas}

    def validate_config(self, config):
        palabras = config.get('palabras', [])
        if len(palabras) < 3:
            return [
                'Necesita al menos tres palabras que compartan letras entre si: '
                'las que no cruzan con ninguna no entran al tablero.'
            ]
        sin_pista = [p['texto'] for p in palabras if not p.get('pista')]
        if sin_pista:
            return [f'Falta la pista de: {", ".join(sin_pista)}.']
        return []

    def editor_config(self, config):
        return {
            'palabras': [
                {'id': p['id'], 'texto': p['texto'], 'pista': p.get('pista', '')}
                for p in config.get('palabras', [])
            ],
        }

    def public_config(self, config):
        return {
            'filas': config.get('filas', 0),
            'columnas': config.get('columnas', 0),
            'palabras': [
                {
                    'id': p['id'],
                    'numero': p.get('numero'),
                    'pista': p.get('pista', ''),
                    'horizontal': p.get('horizontal', True),
                    'fila': p.get('fila', 0),
                    'columna': p.get('columna', 0),
                    'largo': len(p.get('limpia', '')),
                }
                for p in config.get('palabras', [])
            ],
        }

    def grade(self, config, response):
        recibidas = response.get('respuestas', {})
        aciertos = 0
        detalle = []
        for palabra in config.get('palabras', []):
            escrita = _limpiar(recibidas.get(palabra['id'], ''))
            correcta = bool(escrita) and escrita == palabra['limpia']
            aciertos += int(correcta)
            detalle.append({'palabra_id': palabra['id'], 'correcta': correcta})
        return self.result(
            aciertos, len(config.get('palabras', [])), {'palabras': detalle},
        )
