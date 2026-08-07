import re
import unicodedata
from uuid import uuid4

from .base import PluginActividadBase
from .registry import register_plugin


_PATTERN = re.compile(r'\[\[(.+?)\]\]')


def _clean(value):
    text = unicodedata.normalize('NFKD', str(value or ''))
    text = ''.join(char for char in text if not unicodedata.combining(char))
    return ' '.join(text.lower().strip().split())


@register_plugin
class CompletarEspaciosPlugin(PluginActividadBase):
    codigo = 'completar_espacios'
    nombre = 'Completar espacios'
    descripcion = 'Completa palabras dentro de un texto.'
    schema = {
        'fields': [
            {
                'name': 'texto',
                'type': 'textarea',
                'label': 'Texto; escriba las respuestas entre [[doble corchete]]. Ejemplo: La capital es [[Quito]].',
                'required': True,
            },
        ],
    }

    def normalize_config(self, config):
        raw_text = str(config.get('texto', '')).strip()
        respuestas = []
        partes = []
        cursor = 0
        for match in _PATTERN.finditer(raw_text):
            partes.append({'tipo': 'texto', 'valor': raw_text[cursor:match.start()]})
            alternativas = [item.strip() for item in match.group(1).split('|') if item.strip()]
            blank_id = uuid4().hex
            respuestas.append({'id': blank_id, 'alternativas': alternativas})
            partes.append({'tipo': 'espacio', 'id': blank_id})
            cursor = match.end()
        partes.append({'tipo': 'texto', 'valor': raw_text[cursor:]})
        return {'texto_original': raw_text, 'partes': partes, 'respuestas': respuestas}

    def validate_config(self, config):
        if not config.get('texto_original'):
            return ['Debe escribir el texto.']
        if not config.get('respuestas'):
            return ['Debe incluir al menos una respuesta entre [[doble corchete]].']
        return []

    def editor_config(self, config):
        return {'texto': config.get('texto_original', '')}

    def public_config(self, config):
        return {'partes': config.get('partes', [])}

    def grade(self, config, response):
        recibidas = response.get('respuestas', {})
        aciertos = 0
        detalle = []
        for expected in config.get('respuestas', []):
            value = _clean(recibidas.get(expected['id'], ''))
            alternativas = [_clean(item) for item in expected.get('alternativas', [])]
            correcta = bool(value) and value in alternativas
            aciertos += int(correcta)
            detalle.append({'espacio_id': expected['id'], 'correcta': correcta})
        return self.result(aciertos, len(config.get('respuestas', [])), {'espacios': detalle})
