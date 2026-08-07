import random
from uuid import uuid4

from .base import PluginActividadBase
from .registry import register_plugin


@register_plugin
class RelacionarPlugin(PluginActividadBase):
    codigo = 'relacionar'
    nombre = 'Relacionar columnas'
    descripcion = 'Relaciona conceptos, textos o imágenes entre dos columnas.'
    schema = {
        'fields': [
            {
                'name': 'pares',
                'type': 'list',
                'label': 'Pares correctos',
                'min_items': 2,
                'item_fields': [
                    {'name': 'izquierda', 'type': 'text', 'label': 'Columna izquierda', 'required': True},
                    {'name': 'derecha', 'type': 'text', 'label': 'Columna derecha', 'required': True},
                ],
            },
        ],
    }

    def normalize_config(self, config):
        pares = []
        for raw in config.get('pares', []):
            pares.append({
                'id': raw.get('id') or uuid4().hex,
                'izquierda_id': raw.get('izquierda_id') or uuid4().hex,
                'derecha_id': raw.get('derecha_id') or uuid4().hex,
                'izquierda': str(raw.get('izquierda', '')).strip(),
                'derecha': str(raw.get('derecha', '')).strip(),
            })
        return {'pares': pares}

    def validate_config(self, config):
        pares = config.get('pares', [])
        errors = []
        if len(pares) < 2:
            errors.append('Debe agregar al menos dos pares.')
        for index, par in enumerate(pares, start=1):
            if not par.get('izquierda') or not par.get('derecha'):
                errors.append(f'Par {index}: complete ambos lados.')
        return errors

    def public_config(self, config):
        izquierdas = [
            {'id': par['izquierda_id'], 'texto': par['izquierda']}
            for par in config.get('pares', [])
        ]
        derechas = [
            {'id': par['derecha_id'], 'texto': par['derecha']}
            for par in config.get('pares', [])
        ]
        random.shuffle(izquierdas)
        random.shuffle(derechas)
        return {'izquierdas': izquierdas, 'derechas': derechas}

    def grade(self, config, response):
        recibidas = response.get('relaciones', {})
        aciertos = 0
        detalle = []
        for par in config.get('pares', []):
            seleccion = str(recibidas.get(par['izquierda_id'], ''))
            correcta = seleccion == str(par['derecha_id'])
            aciertos += int(correcta)
            detalle.append({'izquierda_id': par['izquierda_id'], 'correcta': correcta})
        return self.result(aciertos, len(config.get('pares', [])), {'pares': detalle})
