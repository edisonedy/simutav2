import random
from uuid import uuid4

from .base import PluginActividadBase
from .registry import register_plugin


@register_plugin
class MemoriaPlugin(PluginActividadBase):
    codigo = 'memoria'
    nombre = 'Juego de memoria'
    descripcion = 'Encuentra las parejas de tarjetas.'
    schema = {
        'fields': [
            {
                'name': 'pares',
                'type': 'list',
                'label': 'Parejas',
                'min_items': 2,
                'item_fields': [
                    {'name': 'lado_a', 'type': 'text', 'label': 'Tarjeta A', 'required': True},
                    {'name': 'lado_b', 'type': 'text', 'label': 'Tarjeta B', 'required': True},
                ],
            },
        ],
    }

    def normalize_config(self, config):
        pares = []
        for raw in config.get('pares', []):
            pares.append({
                'id': raw.get('id') or uuid4().hex,
                'lado_a': str(raw.get('lado_a', '')).strip(),
                'lado_b': str(raw.get('lado_b', '')).strip(),
            })
        return {'pares': pares}

    def validate_config(self, config):
        pares = config.get('pares', [])
        errors = []
        if len(pares) < 2:
            errors.append('Debe agregar al menos dos parejas.')
        for index, par in enumerate(pares, start=1):
            if not par.get('lado_a') or not par.get('lado_b'):
                errors.append(f'Pareja {index}: complete las dos tarjetas.')
        return errors

    def public_config(self, config):
        tarjetas = []
        for par in config.get('pares', []):
            # El token de pareja es necesario para la respuesta visual inmediata.
            # El servidor vuelve a calificar el resultado al finalizar.
            tarjetas.extend([
                {'id': uuid4().hex, 'pareja': par['id'], 'texto': par['lado_a']},
                {'id': uuid4().hex, 'pareja': par['id'], 'texto': par['lado_b']},
            ])
        random.shuffle(tarjetas)
        return {'tarjetas': tarjetas, 'total_pares': len(config.get('pares', []))}

    def grade(self, config, response):
        encontradas = set(str(x) for x in response.get('parejas_encontradas', []))
        correctas = set(str(par['id']) for par in config.get('pares', []))
        aciertos = len(encontradas & correctas)
        return self.result(aciertos, len(correctas), {'parejas_encontradas': list(encontradas)})
