import json
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


def _limitar_prompt(prompt):
    prompt = str(prompt or '')
    max_chars = int(getattr(settings, 'SIMUTA_IA_MAX_PROMPT_CHARS', 18000))
    if max_chars > 0 and len(prompt) > max_chars:
        return prompt[:max_chars] + '\n\n[Prompt truncado por limite de seguridad.]'
    return prompt


def _ia_permitida_para_intento(intento):
    max_llamadas = int(getattr(settings, 'SIMUTA_IA_MAX_EVAL_CALLS_PER_INTENTO', 8))
    if max_llamadas <= 0:
        return False
    usadas = intento.pasos.exclude(api_ia='').count()
    return usadas < max_llamadas


class IAServiceMock:
    def evaluar_ronda_dinamica(self, intento, decision, justificacion):
        from simulador.services import validar_respuesta_estudiante
        respuesta = self.evaluar_paso(intento, decision, justificacion)
        return {
            'evaluacion': respuesta.get('evaluacion', ''),
            'impacto_sugerido': self._filtrar_impacto(intento.simulacion, respuesta.get('impacto', {})),
            'puntaje_sugerido': min(100, max(0, float(respuesta.get('puntaje_sugerido', 0)))),
            'siguiente_situacion': respuesta.get('siguiente_situacion', ''),
            'finalizar': False,
        }

    def evaluar_paso(self, intento, decision, justificacion):
        from simulador.services import validar_respuesta_estudiante
        situacion = intento.situacion_actual or intento.simulacion.situacion_inicial or intento.simulacion.contexto
        validacion = validar_respuesta_estudiante(
            decision, justificacion, simulacion=intento.simulacion, situacion_actual=situacion,
        )
        if not validacion['valida']:
            return {
                'evaluacion': validacion['motivo'], 'impacto': {},
                'puntaje_sugerido': validacion['puntaje_maximo'],
                'siguiente_situacion': situacion, 'validacion': validacion,
            }

        match = self._find_action_match(intento.simulacion, decision, justificacion)
        if match:
            return {
                'evaluacion': (
                    f'Tu decision se relaciona con la accion sugerida "{match.texto}". '
                    f'Revisa indicadores y restricciones para completar el analisis.'
                ),
                'impacto': dict(match.impacto_base or {}),
                'puntaje_sugerido': 70,
                'siguiente_situacion': self._next_situation(intento),
                'validacion': validacion,
            }

        puntaje = 45
        if len(decision.strip()) >= 40:
            puntaje += 10
        if len(justificacion.strip()) >= 80:
            puntaje += 10

        return {
            'evaluacion': (
                'La respuesta es valida, pero esta simulacion no tiene conceptos esperados '
                'configurados para evaluar con precision. El profesor debe definir conceptos, '
                'pesos, impactos y retroalimentacion por ronda.'
            ),
            'impacto': {},
            'puntaje_sugerido': min(puntaje, 65),
            'siguiente_situacion': self._next_situation(intento),
            'validacion': validacion,
        }

    def _find_action_match(self, simulacion, decision, justificacion):
        texto = f'{decision} {justificacion}'.lower()
        for accion in simulacion.acciones_sugeridas.filter(activo=True):
            palabras = [p for p in accion.texto.lower().split() if len(p) > 4]
            if any(p in texto for p in palabras):
                return accion
        return None

    def _filtrar_impacto(self, simulacion, impacto):
        codigos = {i.codigo for i in simulacion.indicadores.filter(activo=True)}
        return {
            clave: valor
            for clave, valor in (impacto or {}).items()
            if clave in codigos and isinstance(valor, (int, float))
        }

    def _next_situation(self, intento):
        siguiente_numero = intento.numero_ronda_actual + 1
        if siguiente_numero > intento.simulacion.maximo_decisiones:
            return 'Esta es tu ultima ronda. Consolida tus resultados y prepara tu reflexion final.'
        return (
            f'Ronda {siguiente_numero}: Revisa el nuevo estado de los indicadores y toma '
            'otra decision con una justificacion clara.'
        )


class IAServiceLLM:
    """Logica compartida de evaluacion por rubrica. Las subclases definen el
    proveedor concreto (OpenAI / DeepSeek) implementando _llamar_modelo()."""
    nombre = 'llm'
    api_ia = 'llm'
    model = ''

    def _llamar_modelo(self, prompt):
        """Devuelve (resultado_dict, usage). Lanza excepcion si el proveedor
        falla (sin cuota, timeout, etc.) para que el despachador pruebe el otro."""
        raise NotImplementedError

    def evaluar_ronda_dinamica(self, intento, decision, justificacion):
        from simulador.services import (
            evaluar_conceptos_esperados,
            hallazgos_conocidos,
            situacion_de_ronda,
            validar_respuesta_estudiante,
        )

        simulacion = intento.simulacion
        situacion = intento.situacion_actual or simulacion.situacion_inicial or simulacion.contexto

        validacion = validar_respuesta_estudiante(
            decision, justificacion, simulacion=simulacion, situacion_actual=situacion,
        )
        if not validacion['valida']:
            return {
                'evaluacion': validacion['motivo'], 'impacto_sugerido': {},
                'puntaje_sugerido': validacion['puntaje_maximo'],
                'siguiente_situacion': situacion, 'finalizar': False,
                'evaluacion_detalle': {
                    'tipo': 'validacion',
                    'valida': False,
                    'motivo': validacion['motivo'],
                    'tipo_error': validacion['tipo_error'],
                    'puntaje_maximo': validacion['puntaje_maximo'],
                },
                'respuesta_ia_estructurada': {},
                'modelo_ia': self.model,
                'api_ia': self.api_ia,
                'prompt_version': getattr(simulacion, 'prompt_version', ''),
                'esquema_ia_version': getattr(simulacion, 'esquema_ia_version', ''),
            }

        conceptos_info = self._conceptos_para_prompt(simulacion, intento.numero_ronda_actual)
        if not conceptos_info:
            return IAServiceMock().evaluar_ronda_dinamica(intento, decision, justificacion)

        indicadores_info = self._indicadores_para_prompt(simulacion)
        prompt = self._construir_prompt_semantico(
            simulacion, situacion, decision, justificacion,
            intento.numero_ronda_actual, conceptos_info, indicadores_info,
            hallazgos_conocidos(intento),
        )

        # Si el proveedor falla (sin cuota, timeout, etc.) se lanza la excepcion
        # para que el despachador pruebe el siguiente proveedor (DeepSeek/OpenAI)
        # y, si todos fallan, el motor use la rubrica local.
        resultado, usage = self._llamar_modelo(_limitar_prompt(prompt))

        evaluaciones_conceptos = resultado.get('conceptos') or []
        evaluacion_rubrica = evaluar_conceptos_esperados(
            simulacion,
            intento.numero_ronda_actual,
            decision,
            justificacion,
            situacion,
            evaluaciones_ia=evaluaciones_conceptos,
            evaluaciones_decision=resultado.get('decision') or [],
        )
        retro_ai = str(resultado.get('retroalimentacion_general') or '').strip()
        evaluacion = retro_ai or evaluacion_rubrica['evaluacion']
        siguiente = str(resultado.get('siguiente_situacion') or '').strip()
        finalizar = bool(resultado.get('finalizar', False))
        if intento.numero_ronda_actual >= simulacion.maximo_decisiones:
            finalizar = True

        return {
            'evaluacion': evaluacion,
            'impacto_sugerido': evaluacion_rubrica['impacto_sugerido'],
            'puntaje_sugerido': evaluacion_rubrica['puntaje_sugerido'],
            'siguiente_situacion': siguiente or self._next_situation(intento, finalizar),
            'finalizar': finalizar,
            'evaluacion_detalle': {
                'tipo': 'ia_rubrica_docente',
                'proveedor': self.nombre,
                'modelo': self.model,
                'conceptos': evaluacion_rubrica['detalle_conceptos'],
                'conceptos_cumplidos': evaluacion_rubrica['conceptos_cumplidos'],
                'conceptos_parciales': evaluacion_rubrica['conceptos_parciales'],
                'conceptos_faltantes': evaluacion_rubrica['conceptos_faltantes'],
                'conceptos_criticos_faltantes': evaluacion_rubrica['conceptos_criticos_faltantes'],
                'puntaje_conceptos': evaluacion_rubrica['puntaje_conceptos'],
                'puntaje_sin_tope': evaluacion_rubrica['puntaje_sin_tope'],
                'tope_critico': evaluacion_rubrica['tope_critico'],
                'metodo_evaluacion': evaluacion_rubrica['metodo_evaluacion'],
                'rubrica_decision': evaluacion_rubrica['rubrica_decision'],
                'puntaje_decision': evaluacion_rubrica['puntaje_decision'],
                'peso_decision': evaluacion_rubrica['peso_decision'],
                'calculo': 'La nota e impactos se calculan con pesos, conceptos e indicadores configurados por el docente.',
            },
            'respuesta_ia_estructurada': resultado,
            'modelo_ia': self.model,
            'api_ia': self.api_ia,
            'prompt_version': simulacion.prompt_version,
            'esquema_ia_version': simulacion.esquema_ia_version,
            'tokens_entrada': self._usage_tokens(usage, 'input_tokens', 'prompt_tokens'),
            'tokens_salida': self._usage_tokens(usage, 'output_tokens', 'completion_tokens'),
        }

    def _usage_tokens(self, usage, *nombres):
        if not usage:
            return 0
        for nombre in nombres:
            valor = getattr(usage, nombre, None)
            if valor is not None:
                return int(valor or 0)
        return 0

    def _schema_evaluacion_semantica(self):
        from simulador.services import CRITERIOS_DECISION
        return {
            'type': 'object',
            'additionalProperties': False,
            'required': ['conceptos', 'retroalimentacion_general', 'siguiente_situacion', 'finalizar', 'opcion_detectada', 'confianza_opcion'],
            'properties': {
                'opcion_detectada': {'type': 'string'},
                'confianza_opcion': {'type': 'number', 'minimum': 0, 'maximum': 1},
                'conceptos': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'additionalProperties': False,
                        'required': [
                            'concepto_id', 'cumple', 'factor',
                            'evidencia', 'retroalimentacion',
                        ],
                        'properties': {
                            'concepto_id': {'type': 'integer'},
                            'cumple': {'type': 'boolean'},
                            'factor': {'type': 'number', 'minimum': 0, 'maximum': 1},
                            'evidencia': {'type': 'string'},
                            'retroalimentacion': {'type': 'string'},
                        },
                    },
                },
                'decision': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'additionalProperties': False,
                        'required': ['clave', 'cumple', 'evidencia', 'retroalimentacion'],
                        'properties': {
                            'clave': {
                                'type': 'string',
                                'enum': [c['clave'] for c in CRITERIOS_DECISION],
                            },
                            'cumple': {'type': 'boolean'},
                            'evidencia': {'type': 'string'},
                            'retroalimentacion': {'type': 'string'},
                        },
                    },
                },
                'retroalimentacion_general': {'type': 'string'},
                'siguiente_situacion': {'type': 'string'},
                'finalizar': {'type': 'boolean'},
            },
        }

    def _construir_prompt_semantico(self, simulacion, situacion, decision, justificacion, ronda, conceptos, indicadores, hallazgos=None):
        from simulador.services import CRITERIOS_DECISION
        criterios_decision = [
            {'clave': c['clave'], 'nombre': c['nombre'], 'descripcion': c['descripcion']}
            for c in CRITERIOS_DECISION
        ]
        bloque_hallazgos = ''
        if hallazgos:
            bloque_hallazgos = (
                '\n## Evidencia que el estudiante pago por averiguar\n'
                + json.dumps(hallazgos, ensure_ascii=False, indent=2)
                + '\nSi decidio ignorando esta evidencia que ya tenia, no le des por cumplido '
                  'el criterio de evidencia.\n'
            )
        rondas = (simulacion.parametros or {}).get('rondas') or []
        opciones_docente = []
        indice = ronda - 1
        if 0 <= indice < len(rondas) and isinstance(rondas[indice], dict):
            opciones_docente = rondas[indice].get('opciones_decision') or []

        from simulador.services.motor_dinamico import obtener_opciones_dinamicas, obtener_tipo_dinamica, obtener_nombre_opciones
        opciones_dinamicas = obtener_opciones_dinamicas(simulacion)
        tipo_dinamica = obtener_tipo_dinamica(simulacion)
        nombre_opciones = obtener_nombre_opciones(simulacion)
        opciones_dinamicas_prompt = ''
        if opciones_dinamicas:
            opciones_dinamicas_prompt = f"""
## Opciones dinamicas del caso ({nombre_opciones})
Tipo: {tipo_dinamica}
{json.dumps(opciones_dinamicas, ensure_ascii=False, indent=2)}

Antes de evaluar, revisa las opciones dinamicas del caso. Detecta si el estudiante eligio una opcion, alternativa, candidato, proveedor, estrategia, solucion tecnica o plan configurado. No inventes opciones. Solo usa las opciones configuradas. Evalua si la eleccion esta justificada con indicadores del caso.
"""
        return f"""Eres un evaluador academico. Tu tarea NO es asignar nota: SimutaV2 calcula la nota exacta con los pesos del docente.

Evalua semanticamente si la decision del estudiante cumple cada concepto configurado. Usa solo el escenario, opciones del docente, rubrica, indicadores e instrucciones del docente.
No tomes decisiones por el estudiante, no recomiendes una opcion como respuesta correcta y no reemplaces su decision. Solo evalua evidencia y consecuencias.

## Instrucciones del docente
{simulacion.instrucciones_ia or 'Evaluar contra la rubrica configurada.'}

## Simulacion
Titulo: {simulacion.titulo}
Tema: {simulacion.tema}
Rol: {simulacion.rol_estudiante}
Ronda: {ronda} de {simulacion.maximo_decisiones}

## Situacion actual
{situacion}

## Opciones de decision configuradas por el docente
{json.dumps(opciones_docente, ensure_ascii=False, indent=2)}
{opciones_dinamicas_prompt}
## Respuesta del estudiante
Decision:
{decision}

Justificacion:
{justificacion}

## Indicadores configurados
{json.dumps(indicadores, ensure_ascii=False, indent=2)}
{bloque_hallazgos}

## Conceptos configurados por el docente
{json.dumps(conceptos, ensure_ascii=False, indent=2)}

## Criterios de decision (metodo del caso)
Ademas de los conceptos, juzga COMO decidio el estudiante. Estos criterios son
los mismos para todos los casos y no dependen del temario:
{json.dumps(criterios_decision, ensure_ascii=False, indent=2)}

Devuelve SOLO JSON valido con esta estructura:
{{
  "conceptos": [
    {{
      "concepto_id": 0,
      "cumple": true,
      "factor": 1.0,
      "evidencia": "frase breve del estudiante que sustenta la decision",
      "retroalimentacion": "comentario breve para este concepto"
    }}
  ],
  "decision": [
    {{
      "clave": "postura",
      "cumple": true,
      "evidencia": "frase del estudiante que lo demuestra",
      "retroalimentacion": "que le falto, en una linea"
    }}
  ],
  "retroalimentacion_general": "retroalimentacion breve y concreta en espanol",
  "siguiente_situacion": "continuacion del caso si no finaliza",
  "finalizar": false
}}

Reglas:
- Incluye todos los concepto_id recibidos.
- Incluye las cuatro claves de decision: postura, evidencia, tradeoff, consecuencia.
- Los criterios de decision son SI o NO, sin medias tintas: cumple true o false.
- Un criterio de decision se cumple aunque el estudiante no use el vocabulario tecnico
  del temario: se juzga el razonamiento, no las palabras.
- factor debe estar entre 0 y 1: 1 cumple completo, 0.5 evidencia parcial, 0 no hay evidencia.
- No inventes conceptos, indicadores, puntajes ni impactos.
- No menciones nota numerica; SimutaV2 la calcula.
- No evalúes "redacción" o "justificación pobre" como criterio genérico.
- Cada retroalimentación debe referirse a un concepto configurado o a un indicador configurado por código/nombre.
- Si falta evidencia, explica qué indicador propio del caso quedó sin sustento; no uses comentarios vagos.
- La siguiente_situacion debe ser una consecuencia breve y realista de la decision tomada, no una nueva pregunta de examen.
- Si la decision es vaga o no ejecutable, marca factor parcial o cero en los conceptos correspondientes.
- Si es la ultima ronda, finalizar debe ser true.
"""

    def _conceptos_para_prompt(self, simulacion, ronda):
        conceptos = simulacion.conceptos_esperados.filter(
            activo=True, numero_ronda=ronda
        ).values('id', 'nombre', 'descripcion', 'palabras_clave', 'regla_evaluacion', 'peso', 'es_critico')
        if not conceptos:
            conceptos = simulacion.conceptos_esperados.filter(
                activo=True, numero_ronda__isnull=True
            ).values('id', 'nombre', 'descripcion', 'palabras_clave', 'regla_evaluacion', 'peso', 'es_critico')
        data = []
        for concepto in conceptos:
            item = self._serializar(concepto)
            item['concepto_id'] = item.pop('id')
            data.append(item)
        return data

    def _indicadores_para_prompt(self, simulacion):
        inds = simulacion.indicadores.filter(activo=True).values(
            'codigo', 'nombre', 'valor_inicial', 'valor_minimo', 'valor_maximo', 'direccion_optima', 'unidad'
        )
        return [
            {
                'codigo': i['codigo'],
                'nombre': i['nombre'],
                'rango': f"{float(i['valor_minimo'])}-{float(i['valor_maximo'])}",
                'direccion_optima': i['direccion_optima'],
                'unidad': i['unidad'],
            }
            for i in inds
        ]

    def _restricciones_para_prompt(self, simulacion):
        ress = simulacion.restricciones.filter(activo=True).values(
            'codigo_indicador', 'operador', 'valor_limite', 'penalizacion', 'descripcion'
        )
        return [self._serializar(r) for r in ress]

    def _serializar(self, data):
        return json.loads(json.dumps(data, default=str))

    def _next_situation(self, intento, finalizar=False):
        if finalizar:
            return ''
        siguiente = intento.numero_ronda_actual + 1
        if siguiente > intento.simulacion.maximo_decisiones:
            return ''
        return f'Ronda {siguiente}: Continua el caso con los indicadores actualizados.'

    def _filtrar_impacto(self, simulacion, impacto):
        codigos = {i.codigo for i in simulacion.indicadores.filter(activo=True)}
        return {
            clave: int(valor)
            for clave, valor in (impacto or {}).items()
            if clave in codigos and isinstance(valor, (int, float))
        }


class IAServiceOpenAI(IAServiceLLM):
    nombre = 'openai'
    api_ia = 'responses'

    def __init__(self):
        api_key = getattr(settings, 'OPENAI_API_KEY', '') or ''
        if not api_key:
            raise ValueError('OPENAI_API_KEY no configurada')
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key)
        self.model = getattr(settings, 'OPENAI_MODEL', 'gpt-5.5')

    def _llamar_modelo(self, prompt):
        respuesta = self.client.responses.create(
            model=self.model,
            input=prompt,
            text={
                'format': {
                    'type': 'json_schema',
                    'name': 'evaluacion_rubrica_docente',
                    'schema': self._schema_evaluacion_semantica(),
                    'strict': True,
                }
            },
            reasoning={'effort': 'low'},
            store=False,
            timeout=getattr(settings, 'OPENAI_TIMEOUT', 45),
        )
        return json.loads(respuesta.output_text), getattr(respuesta, 'usage', None)

    def completar_texto(self, prompt):
        respuesta = self.client.responses.create(
            model=self.model, input=prompt, reasoning={'effort': 'low'},
            store=False, timeout=getattr(settings, 'OPENAI_TIMEOUT', 45),
        )
        return (respuesta.output_text or '').strip()

    def completar_json(self, prompt):
        respuesta = self.client.responses.create(
            model=self.model, input=prompt,
            text={'format': {'type': 'json_object'}},
            reasoning={'effort': 'low'}, store=False,
            timeout=getattr(settings, 'OPENAI_TIMEOUT', 90),
        )
        return json.loads(respuesta.output_text)


class IAServiceDeepSeek(IAServiceLLM):
    """DeepSeek es compatible con el SDK de OpenAI (otro base_url) y usa la API
    clasica chat.completions con modo JSON."""
    nombre = 'deepseek'
    api_ia = 'chat.completions'

    def __init__(self):
        api_key = getattr(settings, 'DEEPSEEK_API_KEY', '') or ''
        if not api_key:
            raise ValueError('DEEPSEEK_API_KEY no configurada')
        from openai import OpenAI
        self.client = OpenAI(
            api_key=api_key,
            base_url=getattr(settings, 'DEEPSEEK_BASE_URL', 'https://api.deepseek.com'),
        )
        self.model = getattr(settings, 'DEEPSEEK_MODEL', 'deepseek-chat')

    def _llamar_modelo(self, prompt):
        respuesta = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {'role': 'system', 'content': 'Eres un evaluador academico. Responde SOLO con JSON valido segun la estructura pedida.'},
                {'role': 'user', 'content': prompt},
            ],
            response_format={'type': 'json_object'},
            temperature=0.2,
            timeout=getattr(settings, 'DEEPSEEK_TIMEOUT', 45),
        )
        return json.loads(respuesta.choices[0].message.content), getattr(respuesta, 'usage', None)

    def completar_texto(self, prompt):
        respuesta = self.client.chat.completions.create(
            model=self.model,
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.5,
            timeout=getattr(settings, 'DEEPSEEK_TIMEOUT', 45),
        )
        return (respuesta.choices[0].message.content or '').strip()

    def completar_json(self, prompt):
        respuesta = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {'role': 'system', 'content': 'Eres un disenador de simulaciones academicas. Responde SOLO con JSON valido.'},
                {'role': 'user', 'content': prompt},
            ],
            response_format={'type': 'json_object'},
            temperature=0.4,
            max_tokens=8000,
            timeout=getattr(settings, 'DEEPSEEK_TIMEOUT', 120),
        )
        return json.loads(respuesta.choices[0].message.content)


PROVEEDORES_IA = {
    'openai': IAServiceOpenAI,
    'deepseek': IAServiceDeepSeek,
}


def _api_key_disponible(nombre):
    if nombre == 'openai':
        return bool(getattr(settings, 'OPENAI_API_KEY', ''))
    if nombre == 'deepseek':
        return bool(getattr(settings, 'DEEPSEEK_API_KEY', ''))
    return False


def orden_proveedores():
    """Orden de proveedores a intentar: principal y luego respaldo, solo los que
    tienen API key configurada. Permite 'cuando openai no responda, usa deepseek'."""
    principal = getattr(settings, 'IA_PROVIDER', 'openai')
    respaldo = getattr(settings, 'IA_FALLBACK_PROVIDER', '')
    orden = []
    for nombre in (principal, respaldo):
        if (nombre and nombre != 'mock' and nombre in PROVEEDORES_IA
                and nombre not in orden and _api_key_disponible(nombre)):
            orden.append(nombre)
    return orden


def evaluar_ronda_con_proveedores(intento, decision, justificacion):
    """Intenta los proveedores en orden; si uno falla (sin cuota/timeout) prueba
    el siguiente. Lanza excepcion solo si todos fallan (el motor usa rubrica)."""
    if not _ia_permitida_para_intento(intento):
        raise RuntimeError('Limite de llamadas IA alcanzado para este intento')
    ultimo_error = None
    for nombre in orden_proveedores():
        try:
            servicio = PROVEEDORES_IA[nombre]()
            return servicio.evaluar_ronda_dinamica(intento, decision, justificacion)
        except Exception as e:
            ultimo_error = e
            logger.warning(f"Proveedor IA '{nombre}' fallo: {e}")
            continue
    if ultimo_error:
        raise ultimo_error
    raise RuntimeError('No hay proveedores de IA con API key configurada')


def _prompt_pista(simulacion, situacion, conceptos_nombres, ronda, nivel_andamiaje='MEDIO'):
    conceptos = ', '.join(conceptos_nombres) if conceptos_nombres else 'los conceptos de la ronda'
    nivel_andamiaje = (nivel_andamiaje or 'MEDIO').upper()
    if nivel_andamiaje == 'ALTO':
        estilo = 'Da una pista mas guiada: propone 2 pasos de pensamiento, sin resolver la decision.'
    elif nivel_andamiaje == 'BAJO':
        estilo = 'Da una pregunta abierta y exigente; no des estructura paso a paso.'
    else:
        estilo = 'Da una pista equilibrada: orienta sin resolver.'
    return (
        "Eres un tutor socratico. El estudiante esta atascado en una simulacion de decisiones.\n"
        "Da UNA pista breve (maximo 2 frases) en forma de PREGUNTA orientadora.\n"
        "REGLAS: NO des la respuesta ni la decision; NO menciones nota; guia a que el estudiante "
        "considere los conceptos esperados y conecte su decision con un indicador del caso.\n"
        f"Nivel de andamiaje: {nivel_andamiaje}. {estilo}\n\n"
        f"Materia/tema: {simulacion.titulo} - {simulacion.tema}\n"
        f"Ronda {ronda}. Situacion actual: {situacion}\n"
        f"Conceptos que deberia abordar: {conceptos}\n\n"
        "Pista (solo el texto, en espanol):"
    )


def generar_pista_ia(intento, conceptos_nombres, situacion, nivel_andamiaje='MEDIO'):
    """Genera una pista socratica con el primer proveedor disponible. Devuelve ''
    si no hay proveedor o todos fallan (el llamador usa la pista de plantilla)."""
    prompt = _limitar_prompt(_prompt_pista(
        intento.simulacion, situacion, conceptos_nombres, intento.numero_ronda_actual,
        nivel_andamiaje=nivel_andamiaje,
    ))
    for nombre in orden_proveedores():
        try:
            servicio = PROVEEDORES_IA[nombre]()
            texto = servicio.completar_texto(prompt)
            if texto:
                return texto[:400]
        except Exception as e:
            logger.warning(f"Pista IA con '{nombre}' fallo: {e}")
            continue
    return ''


def _completar_con_proveedores(prompt, tope=900):
    """Devuelve texto del primer proveedor que responda, o '' si todos fallan."""
    prompt = _limitar_prompt(prompt)
    for nombre in orden_proveedores():
        try:
            texto = PROVEEDORES_IA[nombre]().completar_texto(prompt)
            if texto:
                return texto[:tope]
        except Exception as e:
            logger.warning(f"Texto IA con '{nombre}' fallo: {e}")
            continue
    return ''


def _resumen_decisiones(intento):
    lineas = []
    for p in intento.pasos.order_by('numero'):
        if not p.decision_estudiante:
            continue
        lineas.append(f"Ronda {p.numero}: decidio '{p.decision_estudiante[:160]}' "
                      f"(puntaje {float(p.puntaje_paso):.0f}/100).")
    return '\n'.join(lineas) or 'Sin decisiones registradas.'


def generar_debriefing_ia(intento):
    """Debrief REFLEXIVO (ciclo de Kolb) a partir de las decisiones reales del
    estudiante. Devuelve '' si no hay proveedor de IA (el motor usa el de texto)."""
    sim = intento.simulacion
    prompt = (
        "Eres un tutor que cierra una simulacion de toma de decisiones. Escribe un "
        "DEBRIEFING para que el estudiante APRENDA de la experiencia (no memorice). "
        "Usa EXACTAMENTE estas 4 secciones cortas, en espanol, en segunda persona:\n"
        "1. Lo que lograste: que cambio en la empresa por tus decisiones.\n"
        "2. La decision clave: cual fue la decision mas determinante y por que.\n"
        "3. Que harias distinto: 1-2 mejoras concretas para la proxima.\n"
        "4. Concepto para reforzar: 1 idea de la materia que conviene estudiar mas.\n\n"
        f"Caso: {sim.titulo} - {sim.tema}\n"
        f"Nota final: {intento.puntuacion_final}/100.\n"
        f"Decisiones del estudiante:\n{_resumen_decisiones(intento)}\n\n"
        "Maximo 140 palabras. No repitas la nota como juicio; enfocate en el aprendizaje."
    )
    return _completar_con_proveedores(prompt, tope=1200)


def generar_feedback_reflexion(intento, paso, reflexion):
    """Repregunta socratica del tutor ante la reflexion del estudiante tras ver
    las consecuencias de su decision. NO da la respuesta; profundiza el pensamiento."""
    sim = intento.simulacion
    prompt = (
        "Eres un tutor socratico. El estudiante acaba de ver las consecuencias de su "
        "decision y escribio una reflexion. Responde en 2-3 frases que VALIDEN lo "
        "rescatable y hagan UNA repregunta que lo lleve mas profundo (causa-efecto, "
        "trade-offs, o que evidencia faltaba). REGLAS: no des la decision correcta; no "
        "menciones la nota; conecta con un indicador o concepto del caso.\n\n"
        f"Caso: {sim.titulo} - {sim.tema}\n"
        f"Ronda {paso.numero}. Decision que tomo: {paso.decision_estudiante[:200]}\n"
        f"Reflexion del estudiante: {reflexion[:400]}\n\n"
        "Respuesta del tutor (solo el texto, en espanol):"
    )
    return _completar_con_proveedores(prompt, tope=500)


def _prompt_generacion_caso(materia_nombre, nivel):
    return (
        "Disena una simulacion academica de TOMA DE DECISIONES para la materia indicada. "
        "Debe ser un caso REAL de una empresa con datos concretos, con INDICADORES PROPIOS de la "
        "materia (NO uses indicadores genericos como 'calidad_analisis', 'viabilidad', 'claridad'). "
        "3 rondas: 1 Diagnostico, 2 Decision, 3 Plan. Devuelve SOLO JSON con esta estructura exacta:\n"
        "{\n"
        '  "empresa": "nombre ficticio",\n'
        '  "tema": "...",\n'
        '  "rol_estudiante": "...",\n'
        '  "contexto": "caso real con datos concretos (numeros)",\n'
        '  "objetivo": "...",\n'
        '  "resultado_aprendizaje": "...",\n'
        '  "situacion_inicial": "lo que lee el estudiante en la ronda 1",\n'
        '  "indicadores": [ {"codigo":"snake_case","nombre":"...","valor_inicial":N,"valor_minimo":N,"valor_maximo":N,"direccion_optima":"ALTO|BAJO","unidad":"...","es_critico":true} ],\n'
        '  "restricciones": [ {"descripcion":"...","codigo_indicador":"...","operador":"<=|>=|<|>|=","valor_limite":N,"penalizacion":N} ],\n'
        '  "rondas": [ {"numero":1,"titulo":"Diagnostico","situacion":"...","conceptos":[ {"nombre":"...","peso":N,"es_critico":true,"palabras_clave":"palabra1, palabra2, frase clave","impacto_si_cumple":{"codigo_indicador":N},"impacto_si_falta":{"codigo_indicador":N}} ]} ],\n'
        '  "acciones": [ {"texto":"decision de ejemplo","descripcion":"consecuencia","impacto":{"codigo_indicador":N}} ]\n'
        "}\n\n"
        "Reglas: 5 a 6 indicadores propios de la materia; en cada ronda 3-4 conceptos cuyos pesos SUMEN 100; "
        "los impactos deben usar SOLO los codigos de los indicadores definidos; incluye 4 a 5 acciones (decisiones de "
        "ejemplo) variadas, con AL MENOS una mala/riesgosa; palabras_clave separadas por comas (tecnicas de la materia). "
        "Todo en espanol.\n\n"
        f"Materia: {materia_nombre}\nNivel: {nivel}\n"
    )


def generar_caso_ia(materia_nombre, nivel=1):
    """Genera el spec de una simulacion bespoke (indicadores propios) con el primer
    proveedor disponible (DeepSeek/OpenAI). Devuelve dict o None si falla."""
    prompt = _prompt_generacion_caso(materia_nombre, nivel)
    for nombre in orden_proveedores():
        try:
            data = PROVEEDORES_IA[nombre]().completar_json(prompt)
            if isinstance(data, dict) and data.get('indicadores') and data.get('rondas'):
                data['_proveedor'] = nombre
                return data
        except Exception as e:
            logger.warning(f"Generacion de caso con '{nombre}' fallo: {e}")
            continue
    return None


def _prompt_investigaciones(simulacion, alternativas, recurso, presupuesto):
    """Pide averiguaciones PROPIAS del dominio del caso, no genericas."""
    return (
        'Diseña las AVERIGUACIONES que un estudiante puede pagar antes de decidir en esta '
        'simulacion academica. Son pruebas, entrevistas, auditorias, encuestas o estudios que '
        'revelan informacion OCULTA sobre las alternativas.\n\n'
        f'Materia: {simulacion.materia_malla.materia.nombre}\n'
        f'Caso: {simulacion.titulo}\n'
        f'Contexto: {(simulacion.contexto or "")[:600]}\n'
        f'Rol del estudiante: {simulacion.rol_estudiante}\n'
        f'Alternativas entre las que debe elegir: {json.dumps(alternativas, ensure_ascii=False)}\n'
        f'Presupuesto disponible: {presupuesto} (codigo de recurso "{recurso}")\n\n'
        'Reglas:\n'
        '- Entre 6 y 9 averiguaciones, propias de ESTA materia. Nada generico tipo "investigar mas".\n'
        f'- El COSTO TOTAL debe ser entre 2 y 3 veces {presupuesto}, para que NO alcance para todas '
        'y el estudiante tenga que elegir en que gastar.\n'
        '- Cada hallazgo debe ser un dato CONCRETO y verificable (cifras, hechos, resultados), no una '
        'opinion vaga. Debe cambiar la decision de quien lo lee.\n'
        '- Reparte hallazgos buenos y malos: ninguna alternativa debe ser obviamente la mejor.\n'
        '- "sujeto" es sobre QUIEN o QUE se averigua, en 3 palabras como maximo: un candidato, un '
        'proveedor, un segmento, un area o una estacion de trabajo. Si aplica a todo el caso, pon '
        '"Todos". NUNCA copies ahi el texto de una decision.\n'
        '- "descripcion" dice que obtiene SIN revelar el hallazgo.\n\n'
        'Devuelve SOLO JSON:\n'
        '{"investigaciones": [{"sujeto": "...", "nombre": "...", "descripcion": "...", '
        '"hallazgo": "...", "costo": 60}]}'
    )


def generar_investigaciones_ia(simulacion, alternativas, recurso, presupuesto):
    """Devuelve la lista de averiguaciones para un caso, o None si la IA falla."""
    prompt = _prompt_investigaciones(simulacion, alternativas, recurso, presupuesto)
    for nombre in orden_proveedores():
        try:
            data = PROVEEDORES_IA[nombre]().completar_json(_limitar_prompt(prompt))
            items = (data or {}).get('investigaciones')
            if isinstance(items, list) and len(items) >= 4:
                return items
        except Exception as e:
            logger.warning(f"Generacion de averiguaciones con '{nombre}' fallo: {e}")
            continue
    return None


def evaluar_paso(intento, decision, justificacion):
    if orden_proveedores():
        try:
            return evaluar_ronda_con_proveedores(intento, decision, justificacion)
        except Exception as e:
            logger.warning(f"Fallaron todos los proveedores IA, usando mock: {e}")
    ia = IAServiceMock()
    return ia.evaluar_paso(intento, decision, justificacion)
