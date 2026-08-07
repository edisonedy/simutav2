"""Clasificar elementos en categorias.

El juego mas util para Administracion: costo fijo o variable, activo/pasivo/
patrimonio, gasto o inversion. Obliga a decidir a que grupo pertenece cada
cosa, que es donde se equivoca el estudiante.
"""

from uuid import uuid4

from .base import PluginActividadBase
from .registry import register_plugin


@register_plugin
class ClasificarPlugin(PluginActividadBase):
    codigo = 'clasificar'
    nombre = 'Clasificar en categorias'
    descripcion = 'Arrastra cada elemento al grupo que le corresponde.'
    schema = {
        'fields': [
            {
                'name': 'categorias',
                'type': 'list',
                'label': 'Categorias',
                'min_items': 2,
                'item_fields': [
                    {'name': 'nombre', 'type': 'text', 'label': 'Nombre del grupo', 'required': True},
                ],
            },
            {
                'name': 'elementos',
                'type': 'list',
                'label': 'Elementos a clasificar',
                'min_items': 2,
                'item_fields': [
                    {'name': 'texto', 'type': 'text', 'label': 'Elemento', 'required': True},
                    {
                        'name': 'categoria',
                        'type': 'number',
                        'label': 'Numero de la categoria correcta (empieza en 1)',
                        'min': 1,
                        'required': True,
                    },
                ],
            },
        ],
    }

    def normalize_config(self, config):
        categorias = []
        for raw in config.get('categorias', []):
            nombre = str(raw.get('nombre', '')).strip()
            if not nombre:
                continue
            categorias.append({
                'id': raw.get('id') or uuid4().hex,
                'nombre': nombre,
            })

        elementos = []
        for raw in config.get('elementos', []):
            texto = str(raw.get('texto', '')).strip()
            if not texto:
                continue
            numero = int(raw.get('categoria') or 0)
            categoria_id = (
                categorias[numero - 1]['id']
                if 1 <= numero <= len(categorias) else ''
            )
            elementos.append({
                'id': raw.get('id') or uuid4().hex,
                'texto': texto,
                'categoria_id': categoria_id,
            })

        return {'categorias': categorias, 'elementos': elementos}

    def validate_config(self, config):
        errores = []
        categorias = config.get('categorias', [])
        elementos = config.get('elementos', [])
        if len(categorias) < 2:
            errores.append('Debe definir al menos dos categorias.')
        if len(elementos) < 2:
            errores.append('Debe agregar al menos dos elementos.')
        for indice, elemento in enumerate(elementos, start=1):
            if not elemento.get('categoria_id'):
                errores.append(
                    f'Elemento {indice} ("{elemento.get("texto", "")}"): '
                    'el numero de categoria no corresponde a ninguna.'
                )
        return errores

    def editor_config(self, config):
        categorias = config.get('categorias', [])
        posicion = {c['id']: i for i, c in enumerate(categorias, start=1)}
        return {
            'categorias': [{'id': c['id'], 'nombre': c['nombre']} for c in categorias],
            'elementos': [
                {
                    'id': e['id'],
                    'texto': e['texto'],
                    'categoria': posicion.get(e.get('categoria_id'), 1),
                }
                for e in config.get('elementos', [])
            ],
        }

    def public_config(self, config):
        import random

        elementos = [
            {'id': e['id'], 'texto': e['texto']}
            for e in config.get('elementos', [])
        ]
        random.shuffle(elementos)
        return {
            'categorias': [
                {'id': c['id'], 'nombre': c['nombre']}
                for c in config.get('categorias', [])
            ],
            'elementos': elementos,
        }

    def grade(self, config, response):
        recibidas = response.get('asignaciones', {})
        aciertos = 0
        detalle = []
        for elemento in config.get('elementos', []):
            elegida = str(recibidas.get(elemento['id'], ''))
            correcta = elegida == str(elemento.get('categoria_id', ''))
            aciertos += int(correcta)
            detalle.append({'elemento_id': elemento['id'], 'correcta': correcta})
        return self.result(
            aciertos, len(config.get('elementos', [])), {'elementos': detalle},
        )
