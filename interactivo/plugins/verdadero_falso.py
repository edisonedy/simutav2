from copy import deepcopy
from uuid import uuid4

from .base import PluginActividadBase
from .registry import register_plugin


@register_plugin
class VerdaderoFalsoPlugin(PluginActividadBase):
    codigo = 'verdadero_falso'
    nombre = 'Verdadero o falso'
    descripcion = 'Clasifica afirmaciones como verdaderas o falsas.'
    schema = {
        'fields': [
            {
                'name': 'preguntas',
                'type': 'list',
                'label': 'Afirmaciones',
                'min_items': 1,
                'item_fields': [
                    {'name': 'enunciado', 'type': 'text', 'label': 'Afirmación', 'required': True},
                    {'name': 'correcta', 'type': 'boolean', 'label': 'La afirmación es verdadera'},
                    {'name': 'explicacion', 'type': 'textarea', 'label': 'Explicación', 'required': False},
                ],
            },
        ],
    }

    def normalize_config(self, config):
        preguntas = []
        for raw in config.get('preguntas', []):
            value = raw.get('correcta', False)
            if isinstance(value, str):
                value = value.lower() in {'1', 'true', 'on', 'si', 'sí'}
            preguntas.append({
                'id': raw.get('id') or uuid4().hex,
                'enunciado': str(raw.get('enunciado', '')).strip(),
                'correcta': bool(value),
                'explicacion': str(raw.get('explicacion', '')).strip(),
            })
        return {'preguntas': preguntas}

    def validate_config(self, config):
        preguntas = config.get('preguntas', [])
        if not preguntas:
            return ['Debe agregar al menos una afirmación.']
        return [
            f'Afirmación {index}: falta el texto.'
            for index, pregunta in enumerate(preguntas, start=1)
            if not pregunta.get('enunciado')
        ]

    def public_config(self, config):
        data = deepcopy(config)
        for pregunta in data.get('preguntas', []):
            pregunta.pop('correcta', None)
            pregunta.pop('explicacion', None)
        return data

    def grade(self, config, response):
        recibidas = response.get('respuestas', {})
        aciertos = 0
        detalle = []
        for pregunta in config.get('preguntas', []):
            value = recibidas.get(pregunta['id'])
            if isinstance(value, str):
                value = value.lower() == 'true'
            correcta = value is not None and bool(value) == bool(pregunta.get('correcta'))
            aciertos += int(correcta)
            detalle.append({
                'pregunta_id': pregunta['id'],
                'correcta': correcta,
                'explicacion': pregunta.get('explicacion', ''),
            })
        return self.result(aciertos, len(config.get('preguntas', [])), {'preguntas': detalle})
