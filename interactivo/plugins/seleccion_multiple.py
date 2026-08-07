from copy import deepcopy
from uuid import uuid4

from .base import PluginActividadBase
from .registry import register_plugin


@register_plugin
class SeleccionMultiplePlugin(PluginActividadBase):
    codigo = 'seleccion_multiple'
    nombre = 'Selección múltiple'
    descripcion = 'Una o varias respuestas correctas por pregunta.'
    schema = {
        'fields': [
            {
                'name': 'preguntas',
                'type': 'list',
                'label': 'Preguntas',
                'min_items': 1,
                'item_fields': [
                    {'name': 'enunciado', 'type': 'text', 'label': 'Enunciado', 'required': True},
                    {'name': 'opciones', 'type': 'textarea', 'label': 'Opciones (una por línea)', 'required': True},
                    {
                        'name': 'correctas',
                        'type': 'text',
                        'label': 'Números correctos separados por coma, por ejemplo: 1,3',
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
            opciones = [{'id': uuid4().hex, 'texto': texto} for texto in textos]
            numeros = []
            for token in str(raw.get('correctas', '')).split(','):
                token = token.strip()
                if token.isdigit():
                    numeros.append(int(token))
            correctas_ids = [opciones[n - 1]['id'] for n in numeros if 1 <= n <= len(opciones)]
            preguntas.append({
                'id': raw.get('id') or uuid4().hex,
                'enunciado': str(raw.get('enunciado', '')).strip(),
                'opciones': opciones,
                'correctas_ids': sorted(set(correctas_ids)),
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
            if not pregunta.get('correctas_ids'):
                errors.append(f'Pregunta {index}: debe marcar al menos una opción correcta.')
        return errors

    def editor_config(self, config):
        preguntas = []
        for pregunta in config.get('preguntas', []):
            opciones = pregunta.get('opciones', [])
            correctas_ids = set(pregunta.get('correctas_ids', []))
            numeros = [str(i) for i, op in enumerate(opciones, start=1) if op.get('id') in correctas_ids]
            preguntas.append({
                'id': pregunta.get('id'),
                'enunciado': pregunta.get('enunciado', ''),
                'opciones': '\n'.join(op.get('texto', '') for op in opciones),
                'correctas': ','.join(numeros),
                'explicacion': pregunta.get('explicacion', ''),
            })
        return {'preguntas': preguntas}

    def public_config(self, config):
        data = deepcopy(config)
        for pregunta in data.get('preguntas', []):
            pregunta.pop('correctas_ids', None)
            pregunta.pop('explicacion', None)
        return data

    def grade(self, config, response):
        recibidas = response.get('respuestas', {})
        aciertos = 0
        detalle = []
        for pregunta in config.get('preguntas', []):
            seleccionadas = sorted(set(str(x) for x in recibidas.get(pregunta['id'], [])))
            correctas_ids = sorted(set(str(x) for x in pregunta.get('correctas_ids', [])))
            correcta = seleccionadas == correctas_ids
            aciertos += int(correcta)
            detalle.append({
                'pregunta_id': pregunta['id'],
                'correcta': correcta,
                'explicacion': pregunta.get('explicacion', ''),
            })
        return self.result(aciertos, len(config.get('preguntas', [])), {'preguntas': detalle})
