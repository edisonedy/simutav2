import random
from uuid import uuid4

from .base import PluginActividadBase
from .registry import register_plugin


@register_plugin
class OrdenarPlugin(PluginActividadBase):
    codigo = 'ordenar'
    nombre = 'Ordenar elementos'
    descripcion = 'Ordena pasos, palabras o imágenes en la secuencia correcta.'
    schema = {
        'fields': [
            {
                'name': 'elementos',
                'type': 'list',
                'label': 'Elementos en el orden correcto',
                'min_items': 2,
                'item_fields': [
                    {'name': 'texto', 'type': 'text', 'label': 'Texto', 'required': True},
                ],
            },
        ],
    }

    def normalize_config(self, config):
        elementos = []
        for pos, raw in enumerate(config.get('elementos', []), start=1):
            elementos.append({
                'id': raw.get('id') or uuid4().hex,
                'texto': str(raw.get('texto', '')).strip(),
                'orden': pos,
            })
        return {'elementos': elementos}

    def validate_config(self, config):
        elementos = config.get('elementos', [])
        errors = []
        if len(elementos) < 2:
            errors.append('Debe agregar al menos dos elementos.')
        for index, elemento in enumerate(elementos, start=1):
            if not elemento.get('texto'):
                errors.append(f'Elemento {index}: falta el texto.')
        return errors

    def public_config(self, config):
        elementos = [
            {'id': item['id'], 'texto': item['texto']}
            for item in config.get('elementos', [])
        ]
        random.shuffle(elementos)
        return {'elementos': elementos}

    def grade(self, config, response):
        correcto = [str(item['id']) for item in config.get('elementos', [])]
        recibido = [str(item) for item in response.get('orden', [])]
        aciertos = sum(
            1 for index, item_id in enumerate(correcto)
            if index < len(recibido) and recibido[index] == item_id
        )
        return self.result(aciertos, len(correcto), {'orden_recibido': recibido})
