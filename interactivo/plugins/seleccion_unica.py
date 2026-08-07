from copy import deepcopy
from uuid import uuid4

from .base import PluginActividadBase
from .registry import register_plugin


@register_plugin
class SeleccionUnicaPlugin(PluginActividadBase):
    codigo = 'seleccion_unica'
    nombre = 'Selección única'
    descripcion = 'Una sola respuesta correcta por pregunta.'
    schema = {
        'fields': [
            {
                'name': 'preguntas',
                'type': 'list',
                'label': 'Preguntas',
                'min_items': 1,
                'item_fields': [
                    {'name': 'enunciado', 'type': 'text', 'label': 'Enunciado', 'required': True},
                    {
                        'name': 'opciones',
                        'type': 'textarea',
                        'label': 'Opciones (una por línea)',
                        'required': True,
                    },
                    {
                        'name': 'correcta',
                        'type': 'number',
                        'label': 'Número de respuesta correcta (empieza en 1)',
                        'min': 1,
                        'required': True,
                    },
                    {'name': 'explicacion', 'type': 'textarea', 'label': 'Explicación', 'required': False},
                ],
            },
        ],
    }

    def normalize_config(self, config):
        preguntas = []
        for raw in config.get('preguntas', []):
            opciones_texto = raw.get('opciones', '')
            if isinstance(opciones_texto, list):
                textos = [str(x).strip() for x in opciones_texto if str(x).strip()]
            else:
                textos = [line.strip() for line in str(opciones_texto).splitlines() if line.strip()]
            opciones = [
                {'id': uuid4().hex, 'texto': texto}
                for texto in textos
            ]
            correcta_num = int(raw.get('correcta') or 0)
            correcta_id = opciones[correcta_num - 1]['id'] if 1 <= correcta_num <= len(opciones) else ''
            preguntas.append({
                'id': raw.get('id') or uuid4().hex,
                'enunciado': str(raw.get('enunciado', '')).strip(),
                'opciones': opciones,
                'correcta_id': correcta_id,
                'explicacion': str(raw.get('explicacion', '')).strip(),
            })
        return {'preguntas': preguntas}

    def validate_config(self, config):
        errors = []
        preguntas = config.get('preguntas', [])
        if not preguntas:
            return ['Debe agregar al menos una pregunta.']
        for index, pregunta in enumerate(preguntas, start=1):
            if not pregunta.get('enunciado'):
                errors.append(f'Pregunta {index}: falta el enunciado.')
            if len(pregunta.get('opciones', [])) < 2:
                errors.append(f'Pregunta {index}: debe tener al menos dos opciones.')
            if not pregunta.get('correcta_id'):
                errors.append(f'Pregunta {index}: seleccione una respuesta correcta válida.')
        return errors

    def editor_config(self, config):
        preguntas = []
        for pregunta in config.get('preguntas', []):
            opciones = pregunta.get('opciones', [])
            correcta_id = pregunta.get('correcta_id', '')
            correcta = next((i for i, op in enumerate(opciones, start=1) if op.get('id') == correcta_id), 1)
            preguntas.append({
                'id': pregunta.get('id'),
                'enunciado': pregunta.get('enunciado', ''),
                'opciones': '\n'.join(op.get('texto', '') for op in opciones),
                'correcta': correcta,
                'explicacion': pregunta.get('explicacion', ''),
            })
        return {'preguntas': preguntas}

    def public_config(self, config):
        data = deepcopy(config)
        for pregunta in data.get('preguntas', []):
            pregunta.pop('correcta_id', None)
            pregunta.pop('explicacion', None)
        return data

    def grade(self, config, response):
        recibidas = response.get('respuestas', {})
        aciertos = 0
        detalle = []
        for pregunta in config.get('preguntas', []):
            seleccionada = str(recibidas.get(pregunta['id'], ''))
            correcta = seleccionada == str(pregunta.get('correcta_id', ''))
            aciertos += int(correcta)
            detalle.append({
                'pregunta_id': pregunta['id'],
                'correcta': correcta,
                'explicacion': pregunta.get('explicacion', ''),
            })
        return self.result(aciertos, len(config.get('preguntas', [])), {'preguntas': detalle})
