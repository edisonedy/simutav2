import csv
import json
from copy import copy

from django import forms
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db import models
from decimal import Decimal
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from core.funciones import ok_json, bad_json, conservar_seleccion_actual
from core.permisos import es_administrativo, es_docente
from academico.models import MateriaMalla, ProfesorMateria
from simulador import cursos_service
from simulador.models import (
    Simulacion, IndicadorSimulacion, RestriccionSimulacion,
    ConceptoEsperadoRonda, CriterioEvaluacion, AccionSugeridaSimulacion, CondicionExitoSimulacion,
    DecisionConfigurada, EscenarioSimulacion, EventoSimulacion, IntentoSimulacion,
    InvestigacionSimulacion, RecursoSimulacion,
    MatrizEvaluacionCaso, OpcionCasoSimulacion, PasoSimulacion, RetoRefuerzo,
    ResultadoAprendizaje,
)
from simulador.forms import (
    SimulacionForm, IndicadorSimulacionForm, RestriccionSimulacionForm,
    ConceptoEsperadoRondaForm, CriterioEvaluacionForm, AccionSugeridaForm, CondicionExitoForm,
    DecisionConfiguradaForm, EscenarioSimulacionForm, EventoSimulacionForm, RecursoSimulacionForm,
    MatrizEvaluacionCasoForm, OpcionCasoSimulacionForm, InvestigacionSimulacionForm,
)
from simulador.generator_service import generar_simulacion_desde_plantilla, serializar_configuracion_simulacion


def _request_id(request):
    return request.POST.get('id') or request.POST.get('pk') or request.GET.get('id') or request.GET.get('pk')


def _materias_qs(profesor):
    if _tiene_acceso_global(profesor):
        return MateriaMalla.objects.filter(activo=True)
    return MateriaMalla.objects.filter(
        pk__in=ProfesorMateria.objects.filter(
            profesor=profesor, activo=True
        ).values_list('materia_malla_id', flat=True)
    )


def _limit_form_materia(form, profesor):
    form.fields['materia_malla'].queryset = _materias_qs(profesor).select_related(
        'malla', 'materia', 'nivel',
    )
    # Al editar, la materia que ya tiene la simulacion puede quedar fuera del
    # alcance del profesor (o estar inactiva). Sin esto el select sale vacio y
    # guardar falla, porque materia_malla es obligatoria.
    return conservar_seleccion_actual(form)


def _simplificar_form_creacion(form):
    ocultos = [
        'plantilla_origen',
        'perfil_materia_ia',
        'resultado_aprendizaje',
        'instrucciones_ia',
        'nivel_ayuda_ia',
        'tono_retroalimentacion',
        'guia_debriefing',
        'retroalimentacion_base',
        'modelo_ia',
        'prompt_version',
        'esquema_ia_version',
        'ia_habilitada',
        'activo',
    ]
    for nombre in ocultos:
        form.fields[nombre].required = False
        form.fields[nombre].widget = forms.HiddenInput()
    return form


def _hide_simulacion_field(form, simulacion):
    form.fields['simulacion'].initial = simulacion
    form.fields['simulacion'].widget = forms.HiddenInput()
    form.fields['simulacion'].required = False
    return form


def _impacto_desde_post(post, simulacion, prefijo='impacto'):
    """Arma un dict {codigo: valor} a partir de una casilla numerica por indicador
    (name="<prefijo>_<codigo>"). El profesor no escribe JSON: solo pone numeros."""
    impacto = {}
    for ind in simulacion.indicadores.filter(activo=True):
        raw = (post.get(f'{prefijo}_{ind.codigo}') or '').strip().replace(',', '.')
        if not raw:
            continue
        try:
            valor = float(raw)
        except ValueError:
            continue
        if valor == 0:
            continue
        impacto[ind.codigo] = int(valor) if valor == int(valor) else round(valor, 2)
    return impacto


MODOS_RONDA = [
    ('elegir', 'Elegir una opción', 'El estudiante escoge una alternativa. Si activas la justificación, '
                                    'solo deberá escribir una frase breve con el dato principal.'),
    ('escribir', 'Solo escribir', 'No ve opciones: redacta su decision y la justifica. '
                                  'Util cuando debe construir una respuesta sin opciones sugeridas.'),
    ('hibrido', 'Elegir o escribir la suya', 'Ve las opciones y puede tomar una, o escribir su propia '
                                             'decision. Siempre justifica. Es el modo por defecto.'),
]
CLAVES_MODO_RONDA = {clave for clave, _, _ in MODOS_RONDA}
CONTROLES_VISIBILIDAD_RONDA = [
    ('mostrar_objetivos', 'Metas del caso'),
    ('mostrar_rubrica', 'Rúbrica visible'),
    ('mostrar_datos_caso', 'Alternativas y criterios'),
    ('mostrar_resultados_alternativas', 'Resultados comparativos de las alternativas'),
    ('mostrar_indicadores', 'Indicadores de la situación'),
    ('mostrar_recursos', 'Recursos disponibles'),
    ('mostrar_investigaciones', 'Averiguaciones opcionales'),
    ('pedir_pronostico', 'Pronóstico del indicador'),
    ('pedir_tradeoff', 'Campo separado de sacrificio o trade-off'),
    ('pedir_reflexion', 'Reflexión después de la ronda'),
]
FUENTES_EVALUACION_RONDA = [
    ('decision', 'Decisión escrita por el estudiante'),
    ('justificacion', 'Justificación o sustento'),
    ('pronostico', 'Pronóstico previo'),
    ('tradeoff', 'Costo o riesgo aceptado'),
]


def _entero_acotado(valor, predeterminado, minimo=0, maximo=500):
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        numero = predeterminado
    return max(minimo, min(maximo, numero))


def _rondas_configurables(simulacion):
    """Lo que el profesor puede ajustar en cada ronda. Los defaults son los
    mismos que usa la consola del alumno, para que vea lo que va a salir."""
    from simulador.alu_simulaciones import (
        _configuracion_ronda, _etiquetas_ronda, _modo_ronda, _visibilidad_ronda,
    )

    filas = []
    indicadores = list(simulacion.indicadores.filter(activo=True).order_by('nombre'))
    for numero in range(1, (simulacion.maximo_decisiones or 0) + 1):
        acciones_especificas = simulacion.acciones_sugeridas.filter(
            activo=True, numero_ronda=numero,
        ).count()
        acciones_globales = simulacion.acciones_sugeridas.filter(
            activo=True, numero_ronda__isnull=True,
        ).count()
        hay_opciones = bool(acciones_especificas or acciones_globales)
        etiqueta_decision, etiqueta_justificacion = _etiquetas_ronda(simulacion, numero)
        modo_efectivo = _modo_ronda(simulacion, numero, hay_opciones)
        ronda = _configuracion_ronda(simulacion, numero)
        codigos_modificables = ronda.get('indicadores_modificables')
        if codigos_modificables is None:
            codigos_modificables = [item.codigo for item in indicadores]
        configurado = (ronda.get('modo') or 'hibrido').lower()
        fuentes_configuradas = ronda.get('fuentes_evaluacion')
        if not isinstance(fuentes_configuradas, list):
            fuentes_configuradas = [clave for clave, _ in FUENTES_EVALUACION_RONDA]
        filas.append({
            'numero': numero,
            'titulo': ronda.get('titulo') or f'Ronda {numero}',
            'proposito': ronda.get('proposito') or '',
            'situacion': ronda.get('situacion') or '',
            'modo': configurado if configurado in CLAVES_MODO_RONDA else 'hibrido',
            'modo_efectivo': modo_efectivo,
            'degradado': modo_efectivo != configurado,
            'etiqueta_decision': etiqueta_decision,
            'etiqueta_justificacion': etiqueta_justificacion,
            'justificacion_obligatoria': bool(
                ronda.get('justificacion_obligatoria', configurado != 'elegir')
            ),
            'minimo_justificacion': _entero_acotado(
                ronda.get('minimo_justificacion', 12), 12,
            ),
            'bloquear_contradiccion': bool(
                ronda.get('bloquear_contradiccion', configurado == 'hibrido')
            ),
            'pronostico_obligatorio': bool(ronda.get('pronostico_obligatorio', False)),
            'tradeoff_obligatorio': bool(ronda.get('tradeoff_obligatorio', False)),
            'fuentes_evaluacion': [
                {'clave': clave, 'etiqueta': etiqueta, 'activo': clave in fuentes_configuradas}
                for clave, etiqueta in FUENTES_EVALUACION_RONDA
            ],
            'alternativas_desde_datos_caso': bool(
                ronda.get('alternativas_desde_datos_caso', False)
            ),
            'visibilidad': _visibilidad_ronda(simulacion, numero),
            'controles_visibilidad': [
                {'clave': clave, 'etiqueta': etiqueta,
                 'activo': _visibilidad_ronda(simulacion, numero)[clave]}
                for clave, etiqueta in CONTROLES_VISIBILIDAD_RONDA
            ],
            'acciones_especificas': acciones_especificas,
            'acciones_globales': acciones_globales,
            'indicadores_modificables': [
                {
                    'codigo': item.codigo,
                    'nombre': item.nombre,
                    'activo': item.codigo in codigos_modificables,
                }
                for item in indicadores
            ],
        })
    return filas


def _recursos_desde_post(post, simulacion, prefijo='costo'):
    costos = {}
    for recurso in simulacion.recursos.filter(activo=True):
        raw = (post.get(f'{prefijo}_{recurso.codigo}') or '').strip().replace(',', '.')
        if not raw:
            continue
        try:
            valor = float(raw)
        except ValueError:
            continue
        if valor == 0:
            continue
        costos[recurso.codigo] = int(valor) if valor == int(valor) else round(valor, 2)
    return costos


def _palabras_clave_desde_post(post):
    """El profesor escribe palabras/frases separadas por comas y elige el modo
    (cualquiera / todas). Se guarda como regla simple, sin que el escriba JSON."""
    texto = (post.get('palabras') or '').strip()
    palabras = [p.strip() for p in texto.split(',') if p.strip()]
    if not palabras:
        return ''
    modo = 'all' if post.get('modo_palabras') == 'all' else 'any'
    return json.dumps({modo: palabras}, ensure_ascii=False)


def _palabras_y_modo(palabras_clave):
    """Lee el valor guardado y lo devuelve como (texto separado por comas, modo)
    para precargar el formulario amigable al editar."""
    from simulador.services import parsear_regla_concepto
    regla = parsear_regla_concepto(palabras_clave)
    if regla.get('all'):
        return ', '.join(regla['all']), 'all'
    valores = regla.get('any') or []
    return ', '.join(valores), 'any'


def _impacto_indicadores_form(simulacion, impacto_cumple=None, impacto_falta=None):
    """Lista de indicadores con sus valores actuales de impacto, para pintar las
    casillas (cumple/falta) en el formulario de concepto."""
    impacto_cumple = impacto_cumple or {}
    impacto_falta = impacto_falta or {}
    items = []
    for ind in simulacion.indicadores.filter(activo=True):
        items.append({
            'codigo': ind.codigo,
            'nombre': ind.nombre,
            'direccion': ind.direccion_optima,
            'cumple': impacto_cumple.get(ind.codigo, ''),
            'falta': impacto_falta.get(ind.codigo, ''),
        })
    return items


def _impacto_legible(simulacion, impacto):
    """Convierte {codigo: valor} en [(nombre, valor), ...] para mostrarlo claro."""
    nombres = {i.codigo: i.nombre for i in simulacion.indicadores.filter(activo=True)}
    return [(nombres.get(k, k), v) for k, v in (impacto or {}).items()]


def _resumen_impacto_form(indicadores_impacto):
    cumple = []
    falta = []
    for item in indicadores_impacto or []:
        valor_cumple = item.get('cumple')
        valor_falta = item.get('falta')
        try:
            valor_cumple = float(valor_cumple)
        except (TypeError, ValueError):
            valor_cumple = 0
        try:
            valor_falta = float(valor_falta)
        except (TypeError, ValueError):
            valor_falta = 0
        if valor_cumple:
            cumple.append((item['nombre'], valor_cumple))
        if valor_falta:
            falta.append((item['nombre'], valor_falta))
    return {'cumple': cumple, 'falta': falta}


def _recomendaciones_conceptos(simulacion, conceptos, resumen_rubrica):
    recomendaciones = []
    if simulacion.indicadores.filter(activo=True).count() < 3:
        recomendaciones.append('Agrega al menos 3 indicadores para que la evaluacion tenga mejor contexto.')
    incompletas = [item for item in resumen_rubrica if not item['completa']]
    if incompletas:
        rondas = ', '.join(str(item['ronda']) for item in incompletas)
        recomendaciones.append(f'Ajusta los pesos en las rondas {rondas} para que cada una sume 100.')
    sin_criticos = []
    for item in resumen_rubrica:
        if item['conceptos'] > 0 and item['criticos'] == 0:
            sin_criticos.append(str(item['ronda']))
    if sin_criticos:
        recomendaciones.append('Marca al menos un concepto critico en las rondas ' + ', '.join(sin_criticos) + '.')
    if conceptos:
        conceptos_sin_palabras = [c.nombre for c in conceptos if not str(c.palabras_clave or '').strip()]
        if conceptos_sin_palabras:
            recomendaciones.append('Completa palabras clave en: ' + ', '.join(conceptos_sin_palabras[:3]) + '.')
        conceptos_sin_impacto = []
        for c in conceptos:
            if not (c.impacto_si_cumple or c.impacto_si_falta):
                conceptos_sin_impacto.append(c.nombre)
        if conceptos_sin_impacto:
            recomendaciones.append('Revisa si estos conceptos deberian mover indicadores: ' + ', '.join(conceptos_sin_impacto[:3]) + '.')
        conceptos_faciles = []
        for c in conceptos:
            texto, modo = _palabras_y_modo(c.palabras_clave)
            palabras = [p.strip() for p in texto.split(',') if p.strip()]
            if modo == 'any' and palabras and len(palabras) <= 3 and all(' ' not in p for p in palabras):
                conceptos_faciles.append(c.nombre)
        if len(conceptos_faciles) >= 3:
            recomendaciones.append(
                'La rubrica puede estar demasiado facil: varios conceptos se cumplen con una sola palabra o palabra suelta. '
                'Revisa: ' + ', '.join(conceptos_faciles[:3]) + '.'
            )
    else:
        recomendaciones.append('Agrega conceptos por ronda para que la IA tenga una rubrica que evaluar.')
    if not recomendaciones:
        recomendaciones.append('La rubrica actual no muestra observaciones automaticas importantes.')
    return recomendaciones


def _costo_recursos_legible(simulacion, costo):
    nombres = {r.codigo: f'{r.nombre} ({r.unidad})' if r.unidad else r.nombre for r in simulacion.recursos.filter(activo=True)}
    return [(nombres.get(k, k), v) for k, v in (costo or {}).items()]


def _condicion_evento_legible(simulacion, evento):
    if not evento.codigo_indicador_condicion or evento.valor_condicion is None:
        return 'Sin condicion de indicador'
    nombres = {i.codigo: i.nombre for i in simulacion.indicadores.filter(activo=True)}
    nombre = nombres.get(evento.codigo_indicador_condicion, evento.codigo_indicador_condicion)
    return f'{nombre} {evento.operador_condicion or ">="} {evento.valor_condicion}'


def _pasos_configuracion(simulacion, rubrica_completa):
    """Arma los pasos de configuracion en orden, explicando que hace cada uno y
    como se conecta con el resto. Pensado para que el profesor entienda el flujo."""
    pid = simulacion.pk
    n_ind = simulacion.indicadores.filter(activo=True).count()
    n_rec = simulacion.recursos.filter(activo=True).count()
    n_res = simulacion.restricciones.filter(activo=True).count()
    n_con = simulacion.conceptos_esperados.filter(activo=True).count()
    n_con_ra = simulacion.conceptos_esperados.filter(
        activo=True, resultado_aprendizaje__isnull=False,
    ).count()
    n_acc = simulacion.acciones_sugeridas.filter(activo=True).count()
    n_acc_global = simulacion.acciones_sugeridas.filter(
        activo=True, numero_ronda__isnull=True,
    ).count()
    n_evt = simulacion.eventos.filter(activo=True).count()
    n_inv = simulacion.investigaciones.filter(activo=True).count()
    n_opc_caso = simulacion.opciones_caso.filter(activo=True).count()
    n_mat_caso = simulacion.matriz_caso.filter(activo=True).count()
    caso_ok = all([simulacion.contexto, simulacion.objetivo, simulacion.situacion_inicial])
    rondas_config = _rondas_configurables(simulacion)
    rondas_ok = bool(rondas_config) and all(
        ronda['titulo'] and ronda['situacion']
        and not (ronda['modo'] in ('elegir', 'hibrido') and ronda['degradado'])
        for ronda in rondas_config
    )

    def url(accion):
        return f'?action={accion}&id={pid}'

    return [
        {
            'numero': 1, 'titulo': 'Caso y aprendizaje',
            'fase': 'caso',
            'que_es': 'El contexto, el objetivo y la situacion inicial que leera el estudiante.',
            'como_conecta': 'Es el punto de partida: define el problema real que el estudiante debe resolver.',
            'ok': caso_ok, 'opcional': False, 'aviso': False,
            'detalle': 'Contexto, objetivo y situacion inicial', 'url': url('edit'), 'es_modal': True,
        },
        {
            'numero': 2, 'titulo': 'Indicadores',
            'fase': 'evaluacion',
            'que_es': 'Las variables que se miden (ej. riesgo, viabilidad, calidad). Cada decision las sube o baja.',
            'como_conecta': 'Son la base de todo: las restricciones, los conceptos y las decisiones actuan sobre estos indicadores.',
            'ok': n_ind > 0, 'opcional': False, 'aviso': 0 < n_ind < 3,
            'detalle': f'{n_ind} indicador(es)' + (' (se recomiendan 3 o mas)' if 0 < n_ind < 3 else ''),
            'url': url('indicadores'),
        },
        {
            'numero': 3, 'titulo': 'Opciones que cambian indicadores',
            'fase': 'consecuencias',
            'que_es': 'Alternativas predefinidas que modifican indicadores automaticamente.',
            'como_conecta': 'Usalas solo si quieres que una eleccion concreta cambie numeros sin depender de la redaccion del estudiante.',
            'ok': len((simulacion.parametros or {}).get('opciones_dinamicas', [])) > 0, 'opcional': True, 'aviso': False,
            'detalle': f'{len((simulacion.parametros or {}).get("opciones_dinamicas", []))} opcion(es)', 'url': url('opciones_dinamicas'),
        },
        {
            'numero': 4, 'titulo': 'Datos visibles del caso',
            'fase': 'caso',
            'que_es': 'Alternativas y matriz que el estudiante ve para comparar (proveedores, candidatos, cotizaciones, criterios).',
            'como_conecta': 'No da nota por si solo: entrega evidencia para que la respuesta pueda justificar bien los conceptos esperados.',
            'ok': n_opc_caso > 0 or n_mat_caso > 0, 'opcional': True, 'aviso': False,
            'detalle': f'{n_opc_caso} alternativa(s), {n_mat_caso} criterio(s)', 'url': url('datos_caso'),
        },
        {
            'numero': 5, 'titulo': 'Presupuesto y recursos',
            'fase': 'consecuencias',
            'que_es': 'Dinero, tiempo o capacidad limitada que se consume con las decisiones.',
            'como_conecta': 'Hace que una buena decision tenga costo: no se puede arreglar todo sin sacrificar recursos.',
            'ok': n_rec > 0, 'opcional': True, 'aviso': False,
            'detalle': f'{n_rec} recurso(s)', 'url': url('recursos'),
        },
        {
            'numero': 4.5, 'titulo': 'Como responde el estudiante en cada ronda',
            'fase': 'caso',
            'que_es': 'La situacion, el aprendizaje, la forma de responder y la informacion visible de cada ronda.',
            'como_conecta': 'Cada caso define su propio recorrido; el sistema no obliga a usar diagnostico, decision o plan.',
            'ok': rondas_ok, 'opcional': False, 'aviso': not rondas_ok,
            'detalle': f'{simulacion.maximo_decisiones} ronda(s) configurables', 'url': url('rondas'),
        },
        {
            'numero': 5.5, 'titulo': 'Informacion que se puede comprar',
            'fase': 'caso',
            'que_es': 'Pruebas, entrevistas, auditorias o encuestas que revelan datos ocultos y cuestan presupuesto.',
            'como_conecta': 'Convierte "elegir entre alternativas parecidas" en una decision real: como no alcanza para '
                            'todas, el estudiante debe apostar a cuales le dan mas informacion por lo que cuestan.',
            'ok': n_inv > 0, 'opcional': True, 'aviso': n_inv > 0 and n_rec == 0,
            'detalle': (f'{n_inv} averiguacion(es)' + (' - falta configurar un recurso para cobrarlas' if n_inv and not n_rec else '')),
            'url': url('investigaciones'),
        },
        {
            'numero': 6, 'titulo': 'Restricciones',
            'fase': 'evaluacion',
            'que_es': 'Limites que, si el estudiante los incumple, le restan puntos (ej. riesgo <= 75).',
            'como_conecta': 'Usan los indicadores del paso 2: penalizan cuando una decision deja un indicador en zona mala.',
            'ok': n_res > 0, 'opcional': True, 'aviso': False,
            'detalle': f'{n_res} restriccion(es)', 'url': url('restricciones'),
        },
        {
            'numero': 7, 'titulo': 'Conceptos esperados por ronda (rubrica)',
            'fase': 'evaluacion',
            'que_es': 'Lo que el estudiante debe mencionar o aplicar en cada ronda. Esto define la NOTA.',
            'como_conecta': 'Cada concepto puede vincularse con un resultado de aprendizaje definido por el docente; asi la evidencia del caso demuestra lo aprendido.',
            'ok': rubrica_completa, 'opcional': False,
            'aviso': (n_con > 0 and not rubrica_completa) or (n_con > n_con_ra),
            'detalle': (
                f'{n_con} concepto(s); {n_con_ra} vinculado(s) a resultados de aprendizaje'
                + ('' if rubrica_completa else ' - revisar que cada ronda sume 100')
                + (f'; {n_con - n_con_ra} sin vincular' if n_con > n_con_ra else '')
            ),
            'url': url('conceptos'),
        },
        {
            'numero': 8, 'titulo': 'Decisiones sugeridas',
            'fase': 'consecuencias',
            'que_es': 'Opciones reales que el estudiante puede elegir, cada una con su efecto en los indicadores.',
            'como_conecta': 'Al elegir una, sus numeros cambian. El estudiante igual puede escribir su propia decision.',
            'ok': n_acc > 0, 'opcional': True, 'aviso': n_acc_global > 0,
            'detalle': (
                f'{n_acc} alternativa(s)'
                + (f'; {n_acc_global} se repiten en todas las rondas' if n_acc_global else '')
            ), 'url': url('acciones'),
        },
        {
            'numero': 9, 'titulo': 'Eventos dinamicos',
            'fase': 'consecuencias',
            'que_es': 'Sorpresas que se disparan por ronda o por estado de indicadores.',
            'como_conecta': 'Despues de una decision, la empresa puede reaccionar y mover indicadores con un mensaje visible.',
            'ok': n_evt > 0, 'opcional': True, 'aviso': False,
            'detalle': f'{n_evt} evento(s)', 'url': url('eventos'),
        },
    ]


def _fases_configuracion(pasos):
    orden = [
        {
            'clave': 'caso',
            'numero': 1,
            'titulo': 'Caso',
            'subtitulo': 'Define el problema que el estudiante va a resolver.',
            'pregunta': 'Que problema va a leer y con que datos debe decidir?',
        },
        {
            'clave': 'evaluacion',
            'numero': 2,
            'titulo': 'Evaluacion',
            'subtitulo': 'Define que revisa la IA y como se calcula la nota.',
            'pregunta': 'Que debe justificar el estudiante para obtener buena nota?',
        },
        {
            'clave': 'consecuencias',
            'numero': 3,
            'titulo': 'Consecuencias',
            'subtitulo': 'Define que cambia despues de cada decision.',
            'pregunta': 'Que indicadores, recursos o eventos cambian en la siguiente ronda?',
        },
    ]
    por_fase = {fase['clave']: [] for fase in orden}
    for paso in pasos:
        por_fase.setdefault(paso.get('fase'), []).append(paso)
    fases = []
    for fase in orden:
        items = por_fase.get(fase['clave'], [])
        fase = dict(fase)
        fase['items'] = items
        fase['ok'] = all(item['ok'] or item.get('opcional') for item in items)
        fases.append(fase)
    return fases


def _paneles_configuracion(pasos):
    esenciales = []
    avanzados = []
    for paso in pasos:
        if paso['numero'] in [1, 2, 4.5, 7]:
            esenciales.append(paso)
        else:
            avanzados.append(paso)
    return {
        'caso': [paso for paso in esenciales if paso['numero'] in [1, 4.5]],
        'evaluacion': [paso for paso in esenciales if paso['numero'] in [2, 7]],
        'avanzados': avanzados,
    }


def _limit_decision_form(form, simulacion, escenario=None):
    escenarios = EscenarioSimulacion.objects.filter(simulacion=simulacion, activo=True)
    form.fields['escenario'].queryset = escenarios
    form.fields['siguiente_escenario'].queryset = escenarios
    if escenario:
        form.fields['escenario'].initial = escenario
        form.fields['escenario'].widget = forms.HiddenInput()
        form.fields['escenario'].required = False
    return form


def _limit_concepto_form(form, simulacion=None):
    if simulacion:
        form.fields['simulacion'].initial = simulacion
        form.fields['simulacion'].widget = forms.HiddenInput()
        form.fields['simulacion'].required = False
        form.fields['escenario'].queryset = EscenarioSimulacion.objects.filter(simulacion=simulacion, activo=True)
        form.fields['resultado_aprendizaje'].queryset = ResultadoAprendizaje.objects.filter(
            materia_malla=simulacion.materia_malla,
            activo=True,
        )
        form.fields['resultado_aprendizaje'].empty_label = 'Sin vínculo formal'
    return form


def _sincronizar_cantidad_rondas(simulacion, cantidad_anterior=None):
    """Mantiene una sola fuente de verdad cuando cambia la cantidad de rondas.

    Los intentos iniciados conservan su snapshot. En la configuración editable se
    crean rondas neutrales al aumentar y se desactivan elementos fuera del nuevo
    recorrido al reducir, evitando opciones o rúbricas fantasma.
    """
    cantidad = max(1, int(simulacion.maximo_decisiones or 1))
    parametros = dict(simulacion.parametros or {})
    existentes = [
        dict(item) if isinstance(item, dict) else {}
        for item in (parametros.get('rondas') or [])
    ]
    por_numero = {
        int(item.get('numero')): item
        for item in existentes
        if str(item.get('numero') or '').isdigit()
    }
    rondas = []
    for numero in range(1, cantidad + 1):
        actual = por_numero.get(numero) or (
            existentes[numero - 1] if numero <= len(existentes) else {}
        )
        actual = dict(actual)
        actual['numero'] = numero
        actual.setdefault('titulo', f'Ronda {numero}')
        actual.setdefault('modo', 'escribir')
        rondas.append(actual)
    parametros['rondas'] = rondas
    simulacion.parametros = parametros
    simulacion.save(update_fields=['parametros'])

    if cantidad_anterior is not None and cantidad < cantidad_anterior:
        simulacion.acciones_sugeridas.filter(
            activo=True, numero_ronda__gt=cantidad,
        ).update(activo=False)
        simulacion.conceptos_esperados.filter(
            activo=True, numero_ronda__gt=cantidad,
        ).update(activo=False)
        simulacion.eventos.filter(
            activo=True, ronda__gt=cantidad,
        ).update(activo=False)


def _errores_rubrica_dinamica(simulacion):
    errors = []
    conceptos = ConceptoEsperadoRonda.objects.filter(
        activo=True,
        escenario__isnull=True,
        simulacion=simulacion,
    )
    conceptos_globales = conceptos.filter(numero_ronda__isnull=True)
    suma_global = sum((c.peso for c in conceptos_globales), Decimal('0'))

    if suma_global == Decimal('100'):
        return errors

    for numero in range(1, simulacion.maximo_decisiones + 1):
        suma_ronda = sum(
            (c.peso for c in conceptos.filter(numero_ronda=numero)),
            Decimal('0'),
        )
        if suma_ronda != Decimal('100'):
            errors.append(
                f'La rubrica de la ronda {numero} debe sumar 100 puntos '
                f'(actual: {suma_ronda}).'
            )
    return errors


def _errores_publicacion_pedagogica(simulacion):
    """Evita publicar un examen disfrazado o un caso que no puede reaccionar."""
    errors = []
    rondas = _rondas_configurables(simulacion)
    for ronda in rondas:
        numero = ronda['numero']
        fuentes_activas = [
            fuente['clave'] for fuente in ronda.get('fuentes_evaluacion', [])
            if fuente.get('activo')
        ]
        if not fuentes_activas:
            errors.append(
                f'La ronda {numero} debe permitir al menos una fuente de evidencia para la evaluación.'
            )
        visibilidad = {
            control['clave']: control['activo']
            for control in ronda.get('controles_visibilidad', [])
        }
        if ronda.get('pronostico_obligatorio') and not visibilidad.get('pedir_pronostico'):
            errors.append(
                f'La ronda {numero} exige pronóstico, pero el campo de pronóstico está oculto.'
            )
        if ronda.get('tradeoff_obligatorio') and not visibilidad.get('pedir_tradeoff'):
            errors.append(
                f'La ronda {numero} exige trade-off, pero el campo de trade-off está oculto.'
            )
        if not ronda['proposito'].strip():
            errors.append(f'La ronda {numero} debe indicar que aprendizaje practica.')
        if not ronda['situacion'].strip():
            errors.append(f'La ronda {numero} debe tener una situacion o dilema concreto.')
        if ronda['modo'] in ('elegir', 'hibrido'):
            acciones = simulacion.acciones_sugeridas.filter(
                activo=True,
            ).filter(models.Q(numero_ronda=numero) | models.Q(numero_ronda__isnull=True))
            if acciones.count() < 2:
                errors.append(f'La ronda {numero} necesita al menos dos alternativas comparables.')
            if acciones.filter(impacto_base={}, costo_recursos={}).exists():
                errors.append(f'Todas las alternativas de la ronda {numero} deben tener impacto o costo configurado.')
            if ronda.get('alternativas_desde_datos_caso'):
                ids_visibles = set(
                    simulacion.opciones_caso.filter(activo=True).values_list('id', flat=True)
                )
                ids_vinculados = set(
                    acciones.exclude(opcion_caso__isnull=True).values_list('opcion_caso_id', flat=True)
                )
                if len(ids_visibles) < 2:
                    errors.append(
                        f'La ronda {numero} usa la tabla de alternativas, pero necesita al menos dos registros visibles.'
                    )
                if acciones.filter(opcion_caso__isnull=True).exists():
                    errors.append(
                        f'Todas las decisiones de la ronda {numero} deben vincularse con una alternativa visible.'
                    )
                if ids_visibles != ids_vinculados:
                    errors.append(
                        f'La ronda {numero} debe permitir elegir exactamente las mismas alternativas que muestra la tabla.'
                    )
    if not simulacion.condiciones_exito.filter(activo=True).exists():
        errors.append('Debe configurar al menos una meta final medible.')
    if not (
        (simulacion.resultado_aprendizaje or '').strip()
        or simulacion.conceptos_esperados.filter(
            activo=True, resultado_aprendizaje__isnull=False,
        ).exists()
    ):
        errors.append('Debe definir o vincular un resultado de aprendizaje.')
    rangos = {
        ind.codigo: float(ind.valor_maximo) - float(ind.valor_minimo)
        for ind in simulacion.indicadores.filter(activo=True)
    }
    fuentes_impacto = [
        (f'alternativa "{a.texto}"', a.impacto_base or {})
        for a in simulacion.acciones_sugeridas.filter(activo=True)
    ] + [
        (f'evento "{e.nombre}"', e.efecto or {})
        for e in simulacion.eventos.filter(activo=True)
    ]
    for origen, impacto in fuentes_impacto:
        for codigo, delta in impacto.items():
            if codigo not in rangos:
                errors.append(f'El {origen} usa un indicador inexistente: {codigo}.')
            elif isinstance(delta, (int, float)) and abs(float(delta)) > rangos[codigo]:
                errors.append(
                    f'El impacto {delta} de {origen} supera todo el rango de {codigo}; revisa la escala.',
                )
    permitidos_por_ronda = {
        ronda['numero']: {
            item['codigo'] for item in ronda['indicadores_modificables'] if item['activo']
        }
        for ronda in rondas
    }

    def revisar_fase(origen, numero_ronda, impacto):
        if numero_ronda not in permitidos_por_ronda:
            return
        fuera = sorted(set((impacto or {}).keys()) - permitidos_por_ronda[numero_ronda])
        if fuera:
            errors.append(
                f'El {origen} intenta cambiar indicadores congelados en la ronda '
                f'{numero_ronda}: {", ".join(fuera)}.'
            )

    for accion in simulacion.acciones_sugeridas.filter(activo=True):
        previa = accion.requiere_accion_previa
        if previa:
            if previa.simulacion_id != simulacion.id:
                errors.append(
                    f'La alternativa "{accion.texto}" depende de una decisión de otro caso.'
                )
            if (
                not accion.numero_ronda or not previa.numero_ronda
                or previa.numero_ronda >= accion.numero_ronda
            ):
                errors.append(
                    f'La alternativa "{accion.texto}" debe depender de una decisión de una ronda anterior.'
                )
        bloqueante = accion.bloqueada_por_accion_previa
        if bloqueante:
            if bloqueante.simulacion_id != simulacion.id:
                errors.append(
                    f'La alternativa "{accion.texto}" se bloquea con una decisión de otro caso.'
                )
            if (
                not accion.numero_ronda or not bloqueante.numero_ronda
                or bloqueante.numero_ronda >= accion.numero_ronda
            ):
                errors.append(
                    f'La alternativa "{accion.texto}" solo puede bloquearse con una decisión de una ronda anterior.'
                )
        if previa and bloqueante and previa.pk == bloqueante.pk:
            errors.append(
                f'La alternativa "{accion.texto}" no puede ser habilitada y bloqueada por la misma decisión.'
            )
        numeros = [accion.numero_ronda] if accion.numero_ronda else list(permitidos_por_ronda)
        for numero in numeros:
            revisar_fase(f'alternativa "{accion.texto}"', numero, accion.impacto_base)
    for evento in simulacion.eventos.filter(activo=True):
        revisar_fase(f'evento "{evento.nombre}"', evento.ronda, evento.efecto)
    for concepto in simulacion.conceptos_esperados.filter(activo=True, numero_ronda__isnull=False):
        revisar_fase(f'concepto "{concepto.nombre}"', concepto.numero_ronda, {
            **(concepto.impacto_si_cumple or {}), **(concepto.impacto_si_falta or {}),
        })
    return errors


def _resumen_rubrica(simulacion):
    resumen = []
    for numero in range(1, simulacion.maximo_decisiones + 1):
        conceptos = ConceptoEsperadoRonda.objects.filter(
            simulacion=simulacion,
            escenario__isnull=True,
            numero_ronda=numero,
            activo=True,
        )
        total = sum((c.peso for c in conceptos), Decimal('0'))
        criticos = conceptos.filter(es_critico=True).count()
        resumen.append({
            'ronda': numero,
            'total': total,
            'conceptos': conceptos.count(),
            'criticos': criticos,
            'completa': total == Decimal('100') and conceptos.exists(),
        })
    return resumen


def _analitica_simulacion(simulacion):
    intentos = IntentoSimulacion.objects.filter(simulacion=simulacion)
    finalizados = intentos.filter(finalizado=True)
    promedio = finalizados.aggregate(prom=models.Avg('puntuacion_final')).get('prom')
    pasos_qs = PasoSimulacion.objects.filter(intento__simulacion=simulacion)
    pasos_validos_qs = pasos_qs.filter(es_valido=True)
    pasos = simulacion.intentos.filter(pasos__es_valido=True).values(
        'pasos__numero'
    ).annotate(
        promedio=models.Avg('pasos__puntaje_paso'),
        total=models.Count('pasos__id'),
    ).order_by('pasos__numero')

    fallos = {}
    alertas_recursos = 0
    alertas_restricciones = 0
    for paso in (
        simulacion.intentos
        .filter(pasos__isnull=False)
        .values_list('pasos__evaluacion_detalle', 'pasos__alertas_restricciones')
    ):
        detalle, restricciones = paso
        for concepto in (detalle or {}).get('conceptos', []):
            if not concepto.get('cumple'):
                nombre = concepto.get('nombre') or 'Concepto sin nombre'
                item = fallos.setdefault(nombre, {'nombre': nombre, 'fallos': 0, 'parciales': 0})
                item['fallos'] += 1
                if concepto.get('parcial'):
                    item['parciales'] += 1
        alertas_recursos += len((detalle or {}).get('alertas_recursos') or [])
        alertas_restricciones += len(restricciones or [])

    conceptos_fallados = sorted(fallos.values(), key=lambda x: x['fallos'], reverse=True)[:10]
    pasos_validos = list(pasos_validos_qs.select_related('intento__estudiante'))
    total_pasos_validos = len(pasos_validos)
    reflexiones = [p for p in pasos_validos if (p.reflexion or '').strip()]
    pronosticos = [p for p in pasos_validos if (p.pronostico_indicador or '').strip()]
    pronosticos_acertados = [
        p for p in pronosticos if (p.pronostico_resultado or {}).get('estado') == 'acierto'
    ]
    tradeoffs = [p for p in pasos_validos if (p.tradeoff_aceptado or '').strip()]
    tradeoffs_reales = [
        p for p in tradeoffs if (p.tradeoff_resultado or {}).get('estado') == 'tradeoff_real'
    ]
    retos = RetoRefuerzo.objects.filter(simulacion=simulacion)
    retos_total = retos.count()
    retos_completados = retos.filter(completado=True).count()

    def pct(parte, total):
        return round((parte / total) * 100, 1) if total else 0

    estudiantes = {}
    for intento in finalizados.select_related('estudiante').prefetch_related('pasos'):
        pasos_estudiante = list(intento.pasos.filter(es_valido=True))
        if not pasos_estudiante:
            continue
        sin_reflexion = sum(1 for p in pasos_estudiante if not (p.reflexion or '').strip())
        pronosticos_estudiante = [
            p for p in pasos_estudiante if (p.pronostico_indicador or '').strip()
        ]
        pronosticos_fallidos = sum(
            1 for p in pronosticos_estudiante
            if (p.pronostico_resultado or {}).get('estado') == 'diferencia'
        )
        estudiantes[intento.estudiante_id] = {
            'nombre': intento.estudiante.get_full_name() or intento.estudiante.username,
            'nota': intento.puntuacion_final,
            'sin_reflexion': sin_reflexion,
            'pronosticos_fallidos': pronosticos_fallidos,
            'requiere_refuerzo': float(intento.puntuacion_final or 0) < 70
                or sin_reflexion
                or pronosticos_fallidos,
        }

    estudiantes_riesgo = [
        item for item in estudiantes.values() if item['requiere_refuerzo']
    ][:10]
    recomendaciones = []
    if pct(len(reflexiones), total_pasos_validos) < 70:
        recomendaciones.append('Abrir una discusion breve sobre evidencias: muchos estudiantes deciden sin explicar la causa.')
    if pronosticos and pct(len(pronosticos_acertados), len(pronosticos)) < 60:
        recomendaciones.append('Practicar lectura de indicadores antes de decidir; el pronostico esta fallando.')
    if tradeoffs and pct(len(tradeoffs_reales), len(tradeoffs)) < 60:
        recomendaciones.append('Reforzar pensamiento sistemico: no estan identificando costos o sacrificios reales.')
    if retos_total and pct(retos_completados, retos_total) < 60:
        recomendaciones.append('Dar seguimiento a los retos de refuerzo pendientes antes del siguiente caso.')

    return {
        'total_intentos': intentos.count(),
        'finalizados': finalizados.count(),
        'promedio': round(float(promedio), 2) if promedio is not None else None,
        'promedio_rondas': list(pasos),
        'conceptos_fallados': conceptos_fallados,
        'alertas_recursos': alertas_recursos,
        'alertas_restricciones': alertas_restricciones,
        'alertas_total': alertas_recursos + alertas_restricciones,
        'metacognicion': {
            'pasos_validos': total_pasos_validos,
            'reflexiones': len(reflexiones),
            'reflexion_pct': pct(len(reflexiones), total_pasos_validos),
            'pronosticos': len(pronosticos),
            'pronosticos_acertados': len(pronosticos_acertados),
            'pronostico_pct': pct(len(pronosticos_acertados), len(pronosticos)),
            'tradeoffs': len(tradeoffs),
            'tradeoffs_reales': len(tradeoffs_reales),
            'tradeoff_pct': pct(len(tradeoffs_reales), len(tradeoffs)),
            'retos_total': retos_total,
            'retos_completados': retos_completados,
            'retos_pct': pct(retos_completados, retos_total),
        },
        'estudiantes_riesgo': estudiantes_riesgo,
        'recomendaciones': recomendaciones,
    }


def _es_profesor(user):
    """Solo profesores/staff pueden usar el panel del profesor. Evita que un
    estudiante edite o borre simulaciones por ID (IDOR / acceso indebido)."""
    return es_docente(user)


def _tiene_acceso_global(user):
    return es_administrativo(user)


def _simulaciones_permitidas(user):
    qs = Simulacion.objects.all()
    if _tiene_acceso_global(user):
        return qs
    return qs.filter(
        models.Q(profesor=user)
        | models.Q(usuario_creacion=user)
        | models.Q(materia_malla__profesores__profesor=user, materia_malla__profesores__activo=True)
    ).distinct()


def _auditar_lista_simulaciones(simulaciones):
    for simulacion in simulaciones:
        simulacion.auditoria_caso = cursos_service.auditar_calidad_simulacion(simulacion)
    return simulaciones


def _exportar_auditoria_casos(request):
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = 'attachment; filename="auditoria_calidad_simulaciones.csv"'
    writer = csv.writer(response)
    writer.writerow([
        'simulacion', 'materia', 'estado', 'tipo', 'nivel_calidad', 'puntaje',
        'indicadores', 'conceptos', 'acciones', 'acciones_con_tradeoff',
        'restricciones', 'recursos', 'eventos', 'hallazgos',
    ])
    simulaciones = _simulaciones_permitidas(request.user).select_related(
        'materia_malla__materia',
    ).distinct()
    for simulacion in simulaciones:
        auditoria = cursos_service.auditar_calidad_simulacion(simulacion)
        writer.writerow([
            simulacion.titulo,
            simulacion.materia_malla.materia.nombre if simulacion.materia_malla_id else '',
            simulacion.get_estado_display(),
            simulacion.get_tipo_simulacion_display(),
            auditoria['nivel'],
            auditoria['puntaje'],
            auditoria['indicadores'],
            auditoria['conceptos'],
            auditoria['acciones'],
            auditoria['acciones_tradeoff'],
            auditoria['restricciones'],
            auditoria['recursos'],
            auditoria['eventos'],
            ' | '.join(auditoria['hallazgos']),
        ])
    return response


def _exportar_analitica_simulacion(simulacion):
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = (
        f'attachment; filename="analitica_simulacion_{simulacion.pk}.csv"'
    )
    writer = csv.writer(response)
    writer.writerow([
        'estudiante', 'intento_id', 'finalizado', 'nota', 'pasos_validos',
        'reflexiones', 'pronosticos', 'pronosticos_acertados', 'pronosticos_fallidos',
        'tradeoffs', 'tradeoffs_reales', 'retos_total', 'retos_completados',
        'requiere_refuerzo',
    ])
    intentos = (
        IntentoSimulacion.objects
        .filter(simulacion=simulacion, activo=True)
        .select_related('estudiante')
        .prefetch_related('pasos')
        .order_by('estudiante_id', '-puntuacion_final', '-fecha_fin')
    )
    mejor_por_estudiante = {}
    for intento in intentos:
        if intento.estudiante_id not in mejor_por_estudiante:
            mejor_por_estudiante[intento.estudiante_id] = intento

    for intento in mejor_por_estudiante.values():
        pasos = list(intento.pasos.filter(es_valido=True))
        pronosticos = [p for p in pasos if (p.pronostico_indicador or '').strip()]
        pronosticos_acertados = [
            p for p in pronosticos if (p.pronostico_resultado or {}).get('estado') == 'acierto'
        ]
        pronosticos_fallidos = [
            p for p in pronosticos if (p.pronostico_resultado or {}).get('estado') == 'diferencia'
        ]
        tradeoffs = [p for p in pasos if (p.tradeoff_aceptado or '').strip()]
        tradeoffs_reales = [
            p for p in tradeoffs if (p.tradeoff_resultado or {}).get('estado') == 'tradeoff_real'
        ]
        retos = RetoRefuerzo.objects.filter(simulacion=simulacion, estudiante=intento.estudiante)
        retos_total = retos.count()
        retos_completados = retos.filter(completado=True).count()
        reflexiones = [p for p in pasos if (p.reflexion or '').strip()]
        requiere_refuerzo = (
            float(intento.puntuacion_final or 0) < 70
            or len(reflexiones) < len(pasos)
            or bool(pronosticos_fallidos)
            or (retos_total > retos_completados)
        )
        writer.writerow([
            intento.estudiante.get_full_name() or intento.estudiante.username,
            intento.pk,
            'si' if intento.finalizado else 'no',
            intento.puntuacion_final,
            len(pasos),
            len(reflexiones),
            len(pronosticos),
            len(pronosticos_acertados),
            len(pronosticos_fallidos),
            len(tradeoffs),
            len(tradeoffs_reales),
            retos_total,
            retos_completados,
            'si' if requiere_refuerzo else 'no',
        ])
    return response


def _get_simulacion_profesor(user, pk):
    return get_object_or_404(_simulaciones_permitidas(user), pk=pk)


def _crear_nueva_version(simulacion, usuario):
    """Copia la configuracion editable sin tocar intentos de la version publicada."""
    original = simulacion
    nueva = copy(original)
    nueva.pk = None
    nueva.id = None
    sufijo = f' · v{original.version_configuracion + 1}'
    nueva.titulo = f'{original.titulo[:200 - len(sufijo)]}{sufijo}'
    nueva.estado = Simulacion.BORRADOR
    nueva.version_configuracion = original.version_configuracion + 1
    nueva.configuracion_bloqueada = False
    nueva.fecha_bloqueo = None
    nueva.fecha_publicacion = None
    nueva.configuracion_snapshot = {}
    nueva.profesor = usuario
    nueva.usuario_creacion = usuario
    nueva.save()

    relaciones = [
        'indicadores', 'restricciones', 'condiciones_exito', 'conceptos_esperados',
        'matriz_caso', 'opciones_caso', 'acciones_sugeridas', 'recursos',
        'investigaciones', 'eventos', 'criterios',
    ]
    opciones_clonadas = {}
    for relacion in relaciones:
        for objeto in getattr(original, relacion).all():
            id_original = objeto.pk
            opcion_original_id = getattr(objeto, 'opcion_caso_id', None)
            copia = copy(objeto)
            copia.pk = None
            copia.id = None
            copia.simulacion = nueva
            if relacion == 'acciones_sugeridas' and opcion_original_id:
                copia.opcion_caso_id = opciones_clonadas.get(opcion_original_id)
            copia.save()
            if relacion == 'opciones_caso':
                opciones_clonadas[id_original] = copia.pk
    return nueva


def _validar_acceso_simulacion(user, simulacion):
    if not _simulaciones_permitidas(user).filter(pk=simulacion.pk).exists():
        raise PermissionDenied('No tienes permiso para modificar esta simulacion.')


def _get_objeto_de_simulacion(user, modelo, pk, related='simulacion'):
    obj = get_object_or_404(modelo.objects.select_related(related), pk=pk)
    _validar_acceso_simulacion(user, getattr(obj, related))
    return obj


def _get_concepto_profesor(user, pk):
    concepto = get_object_or_404(
        ConceptoEsperadoRonda.objects.select_related('simulacion', 'escenario__simulacion'),
        pk=pk,
    )
    simulacion = concepto.simulacion or concepto.escenario.simulacion
    _validar_acceso_simulacion(user, simulacion)
    return concepto


def _get_escenario_profesor(user, pk):
    escenario = get_object_or_404(EscenarioSimulacion.objects.select_related('simulacion'), pk=pk)
    _validar_acceso_simulacion(user, escenario.simulacion)
    return escenario


@login_required
@transaction.atomic
def view(request):
    if not _es_profesor(request.user):
        messages.error(request, 'No tienes permiso para acceder al panel del profesor.')
        return redirect('dashboard')
    data = {}
    if request.method == 'POST':
        action = request.POST.get('action') or request.GET.get('action')

        simulacion_post = request.POST.get('simulacion') or request.POST.get('simulacion_id')
        if not simulacion_post and action in {'edit', 'save_rondas'}:
            simulacion_post = _request_id(request)
        if simulacion_post and action not in {'publicar', 'nueva_version'}:
            bloqueada = _simulaciones_permitidas(request.user).filter(
                pk=simulacion_post, configuracion_bloqueada=True,
            ).first()
            if bloqueada:
                return bad_json(
                    mensaje='Esta version ya esta publicada y no se puede modificar. Crea una nueva version.',
                )

        if action == 'add':
            form = _limit_form_materia(SimulacionForm(request.POST), request.user)
            _simplificar_form_creacion(form)
            if form.is_valid():
                simulacion = form.save(commit=False)
                simulacion.profesor = request.user
                simulacion.estado = Simulacion.BORRADOR
                simulacion.save()
                _sincronizar_cantidad_rondas(simulacion)
                return ok_json(data={'id': simulacion.pk}, mensaje='Simulacion creada correctamente.')
            return bad_json(mensaje=str(form.errors))

        elif action == 'nueva_version':
            simulacion = _get_simulacion_profesor(request.user, _request_id(request))
            nueva = _crear_nueva_version(simulacion, request.user)
            return ok_json(
                data={
                    'id': nueva.pk,
                    'redirect_url': f'?action=configuracion&id={nueva.pk}',
                },
                mensaje='Nueva version creada. La version publicada permanece intacta.',
            )

        elif action == 'edit':
            simulacion = _get_simulacion_profesor(request.user, _request_id(request))
            cantidad_anterior = simulacion.maximo_decisiones
            form = _limit_form_materia(SimulacionForm(request.POST, instance=simulacion), request.user)
            _simplificar_form_creacion(form)
            if form.is_valid():
                simulacion = form.save()
                _sincronizar_cantidad_rondas(simulacion, cantidad_anterior)
                return ok_json(mensaje='Simulacion actualizada correctamente.')
            return bad_json(mensaje=str(form.errors))

        elif action == 'delete':
            simulacion = _get_simulacion_profesor(request.user, _request_id(request))
            simulacion.activo = False
            simulacion.save(update_fields=['activo'])
            return ok_json(mensaje='Simulacion desactivada correctamente.')

        elif action == 'publicar':
            simulacion = _get_simulacion_profesor(request.user, _request_id(request))
            errors = []
            if simulacion.tipo_simulacion == Simulacion.TIPO_SIN_IA_ARBOL:
                if simulacion.indicadores.filter(activo=True).count() < 1:
                    errors.append('Debe tener al menos 1 indicador activo.')
                inicial = simulacion.escenarios_arbol.filter(activo=True, es_inicial=True).first()
                if not inicial:
                    errors.append('Debe configurar un escenario inicial.')
                if simulacion.escenarios_arbol.filter(activo=True, decisiones__activo=True).distinct().count() < 1:
                    errors.append('Debe configurar al menos una decision en el arbol.')
            else:
                if not simulacion.titulo:
                    errors.append('Debe ingresar un titulo.')
                if not simulacion.contexto:
                    errors.append('Debe ingresar un contexto.')
                if not simulacion.objetivo:
                    errors.append('Debe ingresar un objetivo.')
                if not simulacion.situacion_inicial:
                    errors.append('Debe ingresar una situacion inicial.')
                if simulacion.maximo_decisiones <= 0:
                    errors.append('El maximo de decisiones debe ser mayor a 0.')
                if simulacion.indicadores.filter(activo=True).count() < 3:
                    errors.append('Debe tener al menos 3 indicadores activos.')
                if simulacion.conceptos_esperados.filter(activo=True).count() < 1:
                    errors.append('Debe configurar conceptos esperados para evaluar la simulacion.')
                errors.extend(_errores_rubrica_dinamica(simulacion))
                errors.extend(_errores_publicacion_pedagogica(simulacion))
            if errors:
                return bad_json(mensaje=' '.join(errors))
            simulacion.estado = Simulacion.PUBLICADA
            simulacion.fecha_publicacion = timezone.now()
            simulacion.configuracion_bloqueada = True
            simulacion.fecha_bloqueo = simulacion.fecha_publicacion
            simulacion.configuracion_snapshot = serializar_configuracion_simulacion(simulacion)
            simulacion.save(update_fields=[
                'estado', 'fecha_publicacion', 'configuracion_bloqueada',
                'fecha_bloqueo', 'configuracion_snapshot',
            ])
            return ok_json(mensaje='Simulacion publicada correctamente.')

        elif action == 'generar_desde_plantilla':
            materia_malla = get_object_or_404(_materias_qs(request.user), pk=request.POST.get('materia_malla_id'))
            simulacion = generar_simulacion_desde_plantilla(
                materia_malla=materia_malla,
                profesor=request.user,
                publicar=False,
            )
            return ok_json(
                data={'redirect_url': f'?action=configuracion&id={simulacion.pk}'},
                mensaje='Simulacion generada desde plantilla global.',
            )

        elif action == 'add_indicador':
            simulacion = _get_simulacion_profesor(request.user, _request_id(request))
            form = IndicadorSimulacionForm(request.POST)
            if form.is_valid():
                indicador = form.save(commit=False)
                indicador.simulacion = simulacion
                indicador.save()
                return ok_json(mensaje='Indicador agregado correctamente.')
            return bad_json(mensaje=str(form.errors))

        elif action == 'edit_indicador':
            indicador = _get_objeto_de_simulacion(request.user, IndicadorSimulacion, _request_id(request))
            form = IndicadorSimulacionForm(request.POST, instance=indicador)
            if form.is_valid():
                form.save()
                return ok_json(mensaje='Indicador actualizado correctamente.')
            return bad_json(mensaje=str(form.errors))

        elif action == 'delete_indicador':
            indicador = _get_objeto_de_simulacion(request.user, IndicadorSimulacion, _request_id(request))
            indicador.activo = False
            indicador.save(update_fields=['activo'])
            return ok_json(mensaje='Indicador eliminado correctamente.')

        elif action == 'add_recurso':
            simulacion = _get_simulacion_profesor(request.user, _request_id(request))
            form = RecursoSimulacionForm(request.POST)
            if form.is_valid():
                recurso = form.save(commit=False)
                recurso.simulacion = simulacion
                recurso.usuario_creacion = request.user
                recurso.save()
                return ok_json(mensaje='Recurso agregado correctamente.')
            return bad_json(mensaje=str(form.errors))

        elif action == 'guardar_rondas':
            simulacion = _get_simulacion_profesor(request.user, _request_id(request))
            parametros = dict(simulacion.parametros or {})
            rondas = list(parametros.get('rondas') or [])
            while len(rondas) < simulacion.maximo_decisiones:
                rondas.append({})
            for numero in range(1, simulacion.maximo_decisiones + 1):
                indice = numero - 1
                actual = rondas[indice] if isinstance(rondas[indice], dict) else {}
                formulario_completo = f'titulo_{numero}' in request.POST
                modo = (request.POST.get(f'modo_{numero}') or 'hibrido').lower()
                if modo not in CLAVES_MODO_RONDA:
                    modo = 'hibrido'
                actual['modo'] = modo
                actual['numero'] = numero
                # En un envío completo el profesor puede cambiar estos textos.
                # En integraciones antiguas/parciales se conservan los del generador.
                if formulario_completo:
                    actual['titulo'] = (
                        request.POST.get(f'titulo_{numero}') or f'Ronda {numero}'
                    ).strip()
                    actual['proposito'] = (
                        request.POST.get(f'proposito_{numero}') or ''
                    ).strip()
                    actual['situacion'] = (
                        request.POST.get(f'situacion_{numero}') or ''
                    ).strip()
                actual['etiqueta_decision'] = (request.POST.get(f'etiqueta_decision_{numero}') or '').strip()
                actual['etiqueta_justificacion'] = (request.POST.get(f'etiqueta_justificacion_{numero}') or '').strip()
                if formulario_completo:
                    actual['justificacion_obligatoria'] = (
                        request.POST.get(f'justificacion_obligatoria_{numero}') == 'on'
                    )
                    try:
                        minimo_justificacion = int(
                            request.POST.get(f'minimo_justificacion_{numero}', '12')
                        )
                    except (TypeError, ValueError):
                        minimo_justificacion = 12
                    actual['minimo_justificacion'] = max(0, min(500, minimo_justificacion))
                    actual['bloquear_contradiccion'] = (
                        request.POST.get(f'bloquear_contradiccion_{numero}') == 'on'
                    )
                    actual['pronostico_obligatorio'] = (
                        request.POST.get(f'pronostico_obligatorio_{numero}') == 'on'
                    )
                    actual['tradeoff_obligatorio'] = (
                        request.POST.get(f'tradeoff_obligatorio_{numero}') == 'on'
                    )
                    fuentes_validas = {clave for clave, _ in FUENTES_EVALUACION_RONDA}
                    actual['fuentes_evaluacion'] = [
                        fuente for fuente in request.POST.getlist(f'fuentes_evaluacion_{numero}')
                        if fuente in fuentes_validas
                    ]
                    actual['alternativas_desde_datos_caso'] = (
                        request.POST.get(f'alternativas_desde_datos_caso_{numero}') == 'on'
                    )
                    from simulador.alu_simulaciones import VISIBILIDAD_RONDA_DEFAULTS
                    for clave in VISIBILIDAD_RONDA_DEFAULTS:
                        actual[clave] = request.POST.get(f'{clave}_{numero}') == 'on'
                    codigos_validos = set(
                        simulacion.indicadores.filter(activo=True).values_list('codigo', flat=True)
                    )
                    actual['indicadores_modificables'] = [
                        codigo for codigo in request.POST.getlist(f'indicadores_modificables_{numero}')
                        if codigo in codigos_validos
                    ]
                rondas[indice] = actual
            parametros['rondas'] = rondas[:simulacion.maximo_decisiones]
            simulacion.parametros = parametros
            simulacion.save(update_fields=['parametros'])
            return ok_json(mensaje='Rondas actualizadas correctamente.')

        elif action == 'cambiar_cantidad_rondas':
            simulacion = _get_simulacion_profesor(request.user, _request_id(request))
            try:
                cantidad = int(request.POST.get('cantidad_rondas', ''))
            except (TypeError, ValueError):
                return bad_json(mensaje='Ingresa una cantidad válida de rondas.')
            if cantidad < 1:
                return bad_json(mensaje='El caso debe tener al menos una ronda.')
            cantidad_anterior = simulacion.maximo_decisiones
            simulacion.maximo_decisiones = cantidad
            simulacion.full_clean(exclude=['profesor'])
            simulacion.save(update_fields=['maximo_decisiones'])
            _sincronizar_cantidad_rondas(simulacion, cantidad_anterior)
            return ok_json(
                data={
                    'redirect_url': (
                        f'?action=rondas&id={simulacion.pk}'
                    ),
                },
                mensaje=f'El caso ahora tiene {cantidad} ronda(s).',
            )

        elif action == 'add_investigacion':
            simulacion = _get_simulacion_profesor(request.user, _request_id(request))
            form = InvestigacionSimulacionForm(request.POST)
            if form.is_valid():
                investigacion = form.save(commit=False)
                investigacion.simulacion = simulacion
                investigacion.costo_recursos = _recursos_desde_post(request.POST, simulacion)
                investigacion.usuario_creacion = request.user
                investigacion.save()
                return ok_json(mensaje='Averiguacion agregada correctamente.')
            return bad_json(mensaje=str(form.errors))

        elif action == 'delete_investigacion':
            investigacion = _get_objeto_de_simulacion(request.user, InvestigacionSimulacion, _request_id(request))
            investigacion.activo = False
            investigacion.save(update_fields=['activo'])
            return ok_json(mensaje='Averiguacion eliminada correctamente.')

        elif action == 'delete_recurso':
            recurso = _get_objeto_de_simulacion(request.user, RecursoSimulacion, _request_id(request))
            recurso.activo = False
            recurso.save(update_fields=['activo'])
            return ok_json(mensaje='Recurso desactivado correctamente.')

        elif action == 'add_restriccion':
            simulacion = _get_simulacion_profesor(request.user, _request_id(request))
            form = RestriccionSimulacionForm(request.POST)
            if form.is_valid():
                restriccion = form.save(commit=False)
                restriccion.simulacion = simulacion
                restriccion.save()
                return ok_json(mensaje='Restriccion agregada correctamente.')
            return bad_json(mensaje=str(form.errors))

        elif action == 'edit_restriccion':
            restriccion = _get_objeto_de_simulacion(request.user, RestriccionSimulacion, _request_id(request))
            form = RestriccionSimulacionForm(request.POST, instance=restriccion)
            if form.is_valid():
                form.save()
                return ok_json(mensaje='Restriccion actualizada correctamente.')
            return bad_json(mensaje=str(form.errors))

        elif action == 'delete_restriccion':
            restriccion = _get_objeto_de_simulacion(request.user, RestriccionSimulacion, _request_id(request))
            restriccion.activo = False
            restriccion.save(update_fields=['activo'])
            return ok_json(mensaje='Restriccion eliminada correctamente.')

        elif action == 'add_criterio':
            simulacion = _get_simulacion_profesor(request.user, _request_id(request))
            form = CriterioEvaluacionForm(request.POST)
            if form.is_valid():
                criterio = form.save(commit=False)
                criterio.simulacion = simulacion
                criterio.save()
                return ok_json(mensaje='Criterio agregado correctamente.')
            return bad_json(mensaje=str(form.errors))

        elif action == 'edit_criterio':
            criterio = _get_objeto_de_simulacion(request.user, CriterioEvaluacion, _request_id(request))
            form = CriterioEvaluacionForm(request.POST, instance=criterio)
            if form.is_valid():
                form.save()
                return ok_json(mensaje='Criterio actualizado correctamente.')
            return bad_json(mensaje=str(form.errors))

        elif action == 'delete_criterio':
            criterio = _get_objeto_de_simulacion(request.user, CriterioEvaluacion, _request_id(request))
            criterio.activo = False
            criterio.save(update_fields=['activo'])
            return ok_json(mensaje='Criterio eliminado correctamente.')

        elif action == 'guardar_etiquetas_caso':
            simulacion = _get_simulacion_profesor(request.user, _request_id(request))
            from simulador.alu_simulaciones import ETIQUETAS_DATOS_CASO
            parametros = dict(simulacion.parametros or {})
            etiquetas = dict(parametros.get('caso_labels') or {})
            for clave, por_defecto in ETIQUETAS_DATOS_CASO.items():
                etiquetas[clave] = (
                    request.POST.get(clave) or por_defecto
                ).strip()[:100]
            parametros['caso_labels'] = etiquetas
            simulacion.parametros = parametros
            simulacion.save(update_fields=['parametros'])
            return ok_json(mensaje='Etiquetas del caso actualizadas correctamente.')

        elif action == 'add_matriz_caso':
            simulacion = _get_simulacion_profesor(request.user, _request_id(request))
            form = MatrizEvaluacionCasoForm(request.POST)
            if form.is_valid():
                item = form.save(commit=False)
                item.simulacion = simulacion
                item.save()
                return ok_json(mensaje='Criterio visible agregado correctamente.')
            return bad_json(mensaje=str(form.errors))

        elif action == 'delete_matriz_caso':
            item = _get_objeto_de_simulacion(request.user, MatrizEvaluacionCaso, _request_id(request))
            item.activo = False
            item.save(update_fields=['activo'])
            return ok_json(mensaje='Criterio visible eliminado correctamente.')

        elif action == 'add_opcion_caso':
            simulacion = _get_simulacion_profesor(request.user, _request_id(request))
            form = OpcionCasoSimulacionForm(request.POST)
            if form.is_valid():
                item = form.save(commit=False)
                item.simulacion = simulacion
                item.save()
                return ok_json(mensaje='Alternativa visible agregada correctamente.')
            return bad_json(mensaje=str(form.errors))

        elif action == 'delete_opcion_caso':
            item = _get_objeto_de_simulacion(request.user, OpcionCasoSimulacion, _request_id(request))
            item.activo = False
            item.save(update_fields=['activo'])
            return ok_json(mensaje='Alternativa visible eliminada correctamente.')

        elif action == 'save_opciones_dinamicas':
            simulacion = _get_simulacion_profesor(request.user, _request_id(request))
            try:
                opciones_json = request.POST.get('opciones_dinamicas_json', '[]')
                opciones = json.loads(opciones_json)
                if not isinstance(opciones, list):
                    return bad_json(mensaje='El formato de opciones debe ser una lista.')
                codigos_opcion = set()
                for opcion in opciones:
                    cod = opcion.get('codigo', '').strip()
                    if not cod:
                        return bad_json(mensaje='Cada opcion debe tener un codigo.')
                    if cod in codigos_opcion:
                        return bad_json(mensaje=f'Codigo duplicado: {cod}')
                    codigos_opcion.add(cod)
                    if not opcion.get('nombre', '').strip():
                        return bad_json(mensaje=f'Opcion "{cod}" debe tener nombre.')
                    inds = opcion.get('indicadores', {})
                    if not isinstance(inds, dict):
                        return bad_json(mensaje=f'indicadores de "{cod}" debe ser un diccionario.')
                    codigos_sim = set(
                        IndicadorSimulacion.objects.filter(
                            simulacion=simulacion, activo=True
                        ).values_list('codigo', flat=True)
                    )
                    claves_invalidas = [k for k in inds if k not in codigos_sim]
                    if claves_invalidas:
                        return bad_json(mensaje=f'Opcion "{cod}" usa indicadores no existentes: {", ".join(claves_invalidas)}.')
                    aliases = opcion.get('aliases', [])
                    if isinstance(aliases, str):
                        opcion['aliases'] = [a.strip() for a in aliases.split(',') if a.strip()]
                    elif not isinstance(aliases, list):
                        opcion['aliases'] = []

                reglas_raw = request.POST.get('reglas_actualizacion_json', '{}')
                reglas = json.loads(reglas_raw)
                confianza = reglas.get('confianza_minima', 0.6)
                if not (0 <= confianza <= 1):
                    return bad_json(mensaje='confianza_minima debe estar entre 0 y 1.')

                params = dict(simulacion.parametros or {})
                params['tipo_dinamica'] = request.POST.get('tipo_dinamica', 'comparacion_opciones')
                params['nombre_opciones'] = request.POST.get('nombre_opciones', 'opciones')
                params['opciones_dinamicas'] = opciones
                params['reglas_actualizacion'] = reglas
                simulacion.parametros = params
                simulacion.save(update_fields=['parametros'])
                return ok_json(mensaje='Opciones dinamicas guardadas correctamente.')
            except json.JSONDecodeError as e:
                return bad_json(mensaje=f'Error en JSON: {e}')
            except Exception as e:
                return bad_json(mensaje=str(e))

        elif action == 'add_accion':
            simulacion = _get_simulacion_profesor(request.user, _request_id(request))
            form = AccionSugeridaForm(request.POST, simulacion_obj=simulacion)
            if form.is_valid():
                accion = form.save(commit=False)
                accion.simulacion = simulacion
                accion.impacto_base = _impacto_desde_post(request.POST, simulacion)
                accion.costo_recursos = _recursos_desde_post(request.POST, simulacion)
                accion.save()
                return ok_json(mensaje='Accion agregada correctamente.')
            return bad_json(mensaje=str(form.errors))

        elif action == 'edit_accion':
            accion = _get_objeto_de_simulacion(request.user, AccionSugeridaSimulacion, _request_id(request))
            form = AccionSugeridaForm(
                request.POST, instance=accion, simulacion_obj=accion.simulacion,
            )
            if form.is_valid():
                accion = form.save(commit=False)
                accion.impacto_base = _impacto_desde_post(request.POST, accion.simulacion)
                accion.costo_recursos = _recursos_desde_post(request.POST, accion.simulacion)
                accion.save()
                return ok_json(mensaje='Accion actualizada correctamente.')
            return bad_json(mensaje=str(form.errors))

        elif action == 'delete_accion':
            accion = _get_objeto_de_simulacion(request.user, AccionSugeridaSimulacion, _request_id(request))
            accion.activo = False
            accion.save(update_fields=['activo'])
            return ok_json(mensaje='Accion eliminada correctamente.')

        elif action == 'add_condicion':
            simulacion = _get_simulacion_profesor(request.user, _request_id(request))
            form = CondicionExitoForm(request.POST)
            if form.is_valid():
                condicion = form.save(commit=False)
                condicion.simulacion = simulacion
                condicion.save()
                return ok_json(mensaje='Condicion agregada correctamente.')
            return bad_json(mensaje=str(form.errors))

        elif action == 'add_evento':
            simulacion = _get_simulacion_profesor(request.user, _request_id(request))
            form = EventoSimulacionForm(request.POST, simulacion_obj=simulacion)
            if form.is_valid():
                efecto = _impacto_desde_post(request.POST, simulacion, 'efecto')
                if not efecto:
                    return bad_json(mensaje='Configura al menos un efecto sobre un indicador.')
                evento = form.save(commit=False)
                evento.simulacion = simulacion
                evento.efecto = efecto
                evento.usuario_creacion = request.user
                evento.save()
                return ok_json(mensaje='Evento dinamico agregado correctamente.')
            return bad_json(mensaje=str(form.errors))

        elif action == 'edit_evento':
            evento = _get_objeto_de_simulacion(request.user, EventoSimulacion, _request_id(request))
            form = EventoSimulacionForm(request.POST, instance=evento, simulacion_obj=evento.simulacion)
            if form.is_valid():
                efecto = _impacto_desde_post(request.POST, evento.simulacion, 'efecto')
                if not efecto:
                    return bad_json(mensaje='Configura al menos un efecto sobre un indicador.')
                evento = form.save(commit=False)
                evento.efecto = efecto
                evento.save()
                return ok_json(mensaje='Evento dinamico actualizado correctamente.')
            return bad_json(mensaje=str(form.errors))

        elif action == 'delete_evento':
            evento = _get_objeto_de_simulacion(request.user, EventoSimulacion, _request_id(request))
            evento.activo = False
            evento.save(update_fields=['activo'])
            return ok_json(mensaje='Evento dinamico desactivado correctamente.')

        elif action == 'add_escenario':
            simulacion = _get_simulacion_profesor(request.user, _request_id(request))
            form = EscenarioSimulacionForm(request.POST)
            if form.is_valid():
                escenario = form.save(commit=False)
                escenario.simulacion = simulacion
                if escenario.es_inicial:
                    EscenarioSimulacion.objects.filter(simulacion=simulacion, es_inicial=True).update(es_inicial=False)
                escenario.save()
                return ok_json(mensaje='Escenario agregado correctamente.')
            return bad_json(mensaje=str(form.errors))

        elif action == 'add_decision':
            escenario = _get_escenario_profesor(request.user, request.POST.get('escenario_id'))
            form = _limit_decision_form(DecisionConfiguradaForm(request.POST), escenario.simulacion, escenario)
            if form.is_valid():
                decision = form.save(commit=False)
                decision.escenario = escenario
                decision.save()
                return ok_json(mensaje='Decision agregada correctamente.')
            return bad_json(mensaje=str(form.errors))

        elif action == 'edit_condicion':
            condicion = _get_objeto_de_simulacion(request.user, CondicionExitoSimulacion, _request_id(request))
            form = CondicionExitoForm(request.POST, instance=condicion)
            if form.is_valid():
                form.save()
                return ok_json(mensaje='Condicion actualizada correctamente.')
            return bad_json(mensaje=str(form.errors))

        elif action == 'delete_condicion':
            condicion = _get_objeto_de_simulacion(request.user, CondicionExitoSimulacion, _request_id(request))
            condicion.activo = False
            condicion.save(update_fields=['activo'])
            return ok_json(mensaje='Condicion eliminada correctamente.')

        elif action == 'add_concepto':
            simulacion = _get_simulacion_profesor(request.user, request.POST.get('simulacion_id') or _request_id(request))
            form = _limit_concepto_form(ConceptoEsperadoRondaForm(request.POST), simulacion)
            if form.is_valid():
                concepto = form.save(commit=False)
                concepto.simulacion = simulacion if not concepto.escenario else None
                concepto.palabras_clave = _palabras_clave_desde_post(request.POST)
                concepto.impacto_si_cumple = _impacto_desde_post(request.POST, simulacion, 'cumple')
                concepto.impacto_si_falta = _impacto_desde_post(request.POST, simulacion, 'falta')
                concepto.usuario_creacion = request.user
                concepto.save()
                return ok_json(mensaje='Concepto agregado correctamente.')
            return bad_json(mensaje=str(form.errors))

        elif action == 'edit_concepto':
            concepto = _get_concepto_profesor(request.user, _request_id(request))
            simulacion = concepto.simulacion or concepto.escenario.simulacion
            form = _limit_concepto_form(ConceptoEsperadoRondaForm(request.POST, instance=concepto), simulacion)
            if form.is_valid():
                obj = form.save(commit=False)
                obj.simulacion = simulacion if not obj.escenario else None
                obj.palabras_clave = _palabras_clave_desde_post(request.POST)
                obj.impacto_si_cumple = _impacto_desde_post(request.POST, simulacion, 'cumple')
                obj.impacto_si_falta = _impacto_desde_post(request.POST, simulacion, 'falta')
                obj.save()
                return ok_json(mensaje='Concepto actualizado correctamente.')
            return bad_json(mensaje=str(form.errors))

        elif action == 'delete_concepto':
            concepto = _get_concepto_profesor(request.user, _request_id(request))
            concepto.activo = False
            concepto.save(update_fields=['activo'])
            return ok_json(mensaje='Concepto eliminado correctamente.')

    action = request.GET.get('action')

    if action == 'add':
        if request.headers.get('X-Requested-With') != 'XMLHttpRequest':
            return redirect('pro_simulaciones')
        form = SimulacionForm()
        _limit_form_materia(form, request.user)
        _simplificar_form_creacion(form)
        data['form'] = form
        return render(request, 'simulador/pro_simulaciones/add.html', data)

    elif action == 'edit':
        if request.headers.get('X-Requested-With') != 'XMLHttpRequest':
            return redirect('pro_simulaciones')
        simulacion = _get_simulacion_profesor(request.user, request.GET.get('id'))
        form = SimulacionForm(instance=simulacion)
        _limit_form_materia(form, request.user)
        _simplificar_form_creacion(form)
        data['form'] = form
        data['simulacion'] = simulacion
        return render(request, 'simulador/pro_simulaciones/edit.html', data)

    elif action == 'configuracion':
        simulacion = get_object_or_404(
            _simulaciones_permitidas(request.user).select_related('materia_malla__materia', 'materia_malla__nivel', 'profesor'),
            pk=request.GET.get('id'),
        )
        data['simulacion'] = simulacion
        data['indicadores'] = IndicadorSimulacion.objects.filter(simulacion=simulacion, activo=True)
        data['restricciones'] = RestriccionSimulacion.objects.filter(simulacion=simulacion, activo=True)
        data['criterios'] = CriterioEvaluacion.objects.filter(simulacion=simulacion, activo=True)
        data['conceptos'] = ConceptoEsperadoRonda.objects.filter(simulacion=simulacion, activo=True)
        data['acciones'] = AccionSugeridaSimulacion.objects.filter(simulacion=simulacion, activo=True)
        data['escenarios'] = EscenarioSimulacion.objects.filter(simulacion=simulacion, activo=True).prefetch_related('decisiones')
        resumen_rubrica = _resumen_rubrica(simulacion)
        data['resumen_rubrica'] = resumen_rubrica
        data['rubrica_completa'] = bool(resumen_rubrica) and all(item['completa'] for item in resumen_rubrica)
        from simulador.ia_service import orden_proveedores
        orden = orden_proveedores()
        data['ia_provider'] = getattr(settings, 'IA_PROVIDER', 'mock')
        data['ia_modelo'] = getattr(settings, 'OPENAI_MODEL', '')
        data['ia_api_ok'] = bool(orden)
        data['ia_orden'] = orden
        data['ia_proveedores'] = [
            {
                'nombre': 'OpenAI',
                'clave': 'openai',
                'conectado': bool(getattr(settings, 'OPENAI_API_KEY', '')),
                'modelo': getattr(settings, 'OPENAI_MODEL', ''),
            },
            {
                'nombre': 'DeepSeek',
                'clave': 'deepseek',
                'conectado': bool(getattr(settings, 'DEEPSEEK_API_KEY', '')),
                'modelo': getattr(settings, 'DEEPSEEK_MODEL', ''),
            },
        ]
        pasos_config = _pasos_configuracion(simulacion, data['rubrica_completa'])
        data['pasos_config'] = pasos_config
        data['fases_config'] = _fases_configuracion(pasos_config)
        data['paneles_config'] = _paneles_configuracion(pasos_config)
        return render(request, 'simulador/pro_simulaciones/configuracion.html', data)

    elif action == 'indicadores':
        simulacion = _get_simulacion_profesor(request.user, request.GET.get('id'))
        form = IndicadorSimulacionForm()
        _hide_simulacion_field(form, simulacion)
        data['simulacion'] = simulacion
        data['form'] = form
        data['indicadores'] = IndicadorSimulacion.objects.filter(simulacion=simulacion)
        return render(request, 'simulador/pro_simulaciones/indicadores.html', data)

    elif action == 'rondas':
        simulacion = _get_simulacion_profesor(request.user, request.GET.get('id'))
        data['simulacion'] = simulacion
        data['rondas'] = _rondas_configurables(simulacion)
        data['modos'] = MODOS_RONDA
        data['hay_opciones'] = simulacion.acciones_sugeridas.filter(activo=True).exists()
        return render(request, 'simulador/pro_simulaciones/rondas.html', data)

    elif action == 'investigaciones':
        simulacion = _get_simulacion_profesor(request.user, request.GET.get('id'))
        form = InvestigacionSimulacionForm()
        _hide_simulacion_field(form, simulacion)
        data['simulacion'] = simulacion
        data['form'] = form
        data['recursos'] = RecursoSimulacion.objects.filter(simulacion=simulacion, activo=True)
        data['investigaciones'] = InvestigacionSimulacion.objects.filter(simulacion=simulacion, activo=True)
        return render(request, 'simulador/pro_simulaciones/investigaciones.html', data)

    elif action == 'recursos':
        simulacion = _get_simulacion_profesor(request.user, request.GET.get('id'))
        form = RecursoSimulacionForm()
        _hide_simulacion_field(form, simulacion)
        data['simulacion'] = simulacion
        data['form'] = form
        data['recursos'] = RecursoSimulacion.objects.filter(simulacion=simulacion)
        return render(request, 'simulador/pro_simulaciones/recursos.html', data)

    elif action == 'edit_indicador':
        indicador = _get_objeto_de_simulacion(request.user, IndicadorSimulacion, request.GET.get('id'))
        simulacion = indicador.simulacion
        form = IndicadorSimulacionForm(instance=indicador)
        _hide_simulacion_field(form, simulacion)
        data['simulacion'] = simulacion
        data['indicador'] = indicador
        data['form'] = form
        return render(request, 'simulador/pro_simulaciones/edit_indicador.html', data)

    elif action == 'opciones_dinamicas':
        simulacion = _get_simulacion_profesor(request.user, request.GET.get('id'))
        data['simulacion'] = simulacion
        data['tipo_dinamica'] = (simulacion.parametros or {}).get('tipo_dinamica', 'comparacion_opciones')
        data['nombre_opciones'] = (simulacion.parametros or {}).get('nombre_opciones', 'opciones')
        data['opciones_dinamicas'] = (simulacion.parametros or {}).get('opciones_dinamicas', [])
        data['reglas_actualizacion'] = (simulacion.parametros or {}).get('reglas_actualizacion', {})
        data['indicadores'] = IndicadorSimulacion.objects.filter(simulacion=simulacion, activo=True)
        return render(request, 'simulador/pro_simulaciones/opciones_dinamicas.html', data)

    elif action == 'conceptos':
        simulacion = _get_simulacion_profesor(request.user, request.GET.get('id') or request.GET.get('id_simulacion'))
        conceptos = ConceptoEsperadoRonda.objects.filter(activo=True).filter(
            models.Q(simulacion=simulacion) | models.Q(escenario__simulacion=simulacion)
        ).select_related('simulacion', 'escenario')
        ronda = request.GET.get('ronda')
        escenario_id = request.GET.get('escenario')
        if ronda:
            conceptos = conceptos.filter(numero_ronda=ronda)
        if escenario_id:
            conceptos = conceptos.filter(escenario_id=escenario_id)
        conceptos = list(conceptos)
        for concepto in conceptos:
            texto, modo = _palabras_y_modo(concepto.palabras_clave)
            concepto.palabras_legibles = [p.strip() for p in texto.split(',') if p.strip()]
            concepto.modo_legible = 'todas' if modo == 'all' else 'al menos una'
            concepto.impacto_cumple_legible = _impacto_legible(simulacion, concepto.impacto_si_cumple)
            concepto.impacto_falta_legible = _impacto_legible(simulacion, concepto.impacto_si_falta)
        data['simulacion'] = simulacion
        data['conceptos'] = conceptos
        data['ronda'] = ronda or ''
        data['escenario_id'] = escenario_id or ''
        data['escenarios'] = EscenarioSimulacion.objects.filter(simulacion=simulacion, activo=True)
        data['resumen_rubrica'] = _resumen_rubrica(simulacion)
        data['recomendaciones'] = _recomendaciones_conceptos(simulacion, conceptos, data['resumen_rubrica'])
        return render(request, 'simulador/pro_simulaciones/conceptos.html', data)

    elif action == 'add_concepto':
        simulacion = _get_simulacion_profesor(request.user, request.GET.get('id') or request.GET.get('id_simulacion'))
        form = ConceptoEsperadoRondaForm(initial={'numero_ronda': request.GET.get('ronda') or 1})
        _limit_concepto_form(form, simulacion)
        data['simulacion'] = simulacion
        data['form'] = form
        data['indicadores_impacto'] = _impacto_indicadores_form(simulacion)
        data['impacto_preview'] = _resumen_impacto_form(data['indicadores_impacto'])
        data['palabras_texto'] = ''
        data['modo_palabras'] = 'any'
        return render(request, 'simulador/pro_simulaciones/add_concepto.html', data)

    elif action == 'edit_concepto':
        concepto = _get_concepto_profesor(request.user, request.GET.get('id') or request.GET.get('id_concepto'))
        simulacion = concepto.simulacion or concepto.escenario.simulacion
        form = ConceptoEsperadoRondaForm(instance=concepto)
        _limit_concepto_form(form, simulacion)
        palabras_texto, modo_palabras = _palabras_y_modo(concepto.palabras_clave)
        data['simulacion'] = simulacion
        data['concepto'] = concepto
        data['form'] = form
        data['indicadores_impacto'] = _impacto_indicadores_form(
            simulacion, concepto.impacto_si_cumple, concepto.impacto_si_falta,
        )
        data['impacto_preview'] = _resumen_impacto_form(data['indicadores_impacto'])
        data['palabras_texto'] = palabras_texto
        data['modo_palabras'] = modo_palabras
        return render(request, 'simulador/pro_simulaciones/edit_concepto.html', data)

    elif action == 'restricciones':
        simulacion = _get_simulacion_profesor(request.user, request.GET.get('id'))
        form = RestriccionSimulacionForm()
        _hide_simulacion_field(form, simulacion)
        data['simulacion'] = simulacion
        data['form'] = form
        data['restricciones'] = RestriccionSimulacion.objects.filter(simulacion=simulacion)
        return render(request, 'simulador/pro_simulaciones/restricciones.html', data)

    elif action == 'criterios':
        simulacion = _get_simulacion_profesor(request.user, request.GET.get('id'))
        form = CriterioEvaluacionForm()
        _hide_simulacion_field(form, simulacion)
        criterios = CriterioEvaluacion.objects.filter(simulacion=simulacion)
        data['simulacion'] = simulacion
        data['form'] = form
        data['criterios'] = criterios
        data['suma_pesos'] = sum(item.peso for item in criterios if item.activo)
        return render(request, 'simulador/pro_simulaciones/criterios.html', data)

    elif action == 'datos_caso':
        simulacion = _get_simulacion_profesor(request.user, request.GET.get('id'))
        form_matriz = MatrizEvaluacionCasoForm()
        form_opcion = OpcionCasoSimulacionForm()
        _hide_simulacion_field(form_matriz, simulacion)
        _hide_simulacion_field(form_opcion, simulacion)
        matriz = MatrizEvaluacionCaso.objects.filter(simulacion=simulacion)
        opciones = OpcionCasoSimulacion.objects.filter(simulacion=simulacion)
        data['simulacion'] = simulacion
        data['form_matriz'] = form_matriz
        data['form_opcion'] = form_opcion
        data['matriz'] = matriz
        data['opciones_caso'] = opciones
        data['suma_matriz'] = sum(item.peso for item in matriz if item.activo)
        from simulador.alu_simulaciones import _etiquetas_datos_caso
        data['caso_labels'] = _etiquetas_datos_caso(simulacion.parametros or {})
        return render(request, 'simulador/pro_simulaciones/datos_caso.html', data)

    elif action == 'acciones':
        simulacion = _get_simulacion_profesor(request.user, request.GET.get('id'))
        form = AccionSugeridaForm(simulacion_obj=simulacion)
        _hide_simulacion_field(form, simulacion)
        indicadores = list(simulacion.indicadores.filter(activo=True))
        recursos = list(simulacion.recursos.filter(activo=True))
        acciones = list(AccionSugeridaSimulacion.objects.filter(simulacion=simulacion, activo=True))
        for accion in acciones:
            accion.impacto_legible = _impacto_legible(simulacion, accion.impacto_base)
            accion.costo_legible = _costo_recursos_legible(simulacion, accion.costo_recursos)
        data['simulacion'] = simulacion
        data['form'] = form
        data['indicadores'] = indicadores
        data['recursos'] = recursos
        data['acciones'] = acciones
        return render(request, 'simulador/pro_simulaciones/acciones.html', data)

    elif action == 'eventos':
        simulacion = _get_simulacion_profesor(request.user, request.GET.get('id'))
        form = EventoSimulacionForm(simulacion_obj=simulacion)
        _hide_simulacion_field(form, simulacion)
        indicadores = list(simulacion.indicadores.filter(activo=True))
        eventos = list(EventoSimulacion.objects.filter(simulacion=simulacion, activo=True))
        for evento in eventos:
            evento.efecto_legible = _impacto_legible(simulacion, evento.efecto)
            evento.condicion_legible = _condicion_evento_legible(simulacion, evento)
        data['simulacion'] = simulacion
        data['form'] = form
        data['indicadores'] = indicadores
        data['eventos'] = eventos
        return render(request, 'simulador/pro_simulaciones/eventos.html', data)

    elif action == 'edit_evento':
        evento = _get_objeto_de_simulacion(request.user, EventoSimulacion, request.GET.get('id'))
        simulacion = evento.simulacion
        form = EventoSimulacionForm(instance=evento, simulacion_obj=simulacion)
        _hide_simulacion_field(form, simulacion)
        data['simulacion'] = simulacion
        data['evento'] = evento
        data['form'] = form
        data['indicadores'] = _impacto_indicadores_form(simulacion, evento.efecto, {})
        return render(request, 'simulador/pro_simulaciones/edit_evento.html', data)

    elif action == 'condiciones':
        simulacion = _get_simulacion_profesor(request.user, request.GET.get('id'))
        form = CondicionExitoForm()
        _hide_simulacion_field(form, simulacion)
        data['simulacion'] = simulacion
        data['form'] = form
        data['condiciones'] = CondicionExitoSimulacion.objects.filter(simulacion=simulacion)
        return render(request, 'simulador/pro_simulaciones/condiciones.html', data)

    elif action == 'escenarios':
        simulacion = _get_simulacion_profesor(request.user, request.GET.get('id'))
        form = EscenarioSimulacionForm()
        _hide_simulacion_field(form, simulacion)
        data['simulacion'] = simulacion
        data['form'] = form
        data['escenarios'] = EscenarioSimulacion.objects.filter(simulacion=simulacion, activo=True).prefetch_related('decisiones')
        return render(request, 'simulador/pro_simulaciones/escenarios.html', data)

    elif action == 'decisiones':
        escenario = _get_escenario_profesor(request.user, request.GET.get('id'))
        form = DecisionConfiguradaForm()
        _limit_decision_form(form, escenario.simulacion, escenario)
        data['escenario'] = escenario
        data['simulacion'] = escenario.simulacion
        data['form'] = form
        data['decisiones'] = DecisionConfigurada.objects.filter(escenario=escenario, activo=True).select_related('siguiente_escenario')
        return render(request, 'simulador/pro_simulaciones/decisiones.html', data)

    elif action == 'revisar':
        simulacion = _get_simulacion_profesor(request.user, request.GET.get('id'))
        data['simulacion'] = simulacion
        data['intentos'] = IntentoSimulacion.objects.filter(
            simulacion=simulacion
        ).select_related('estudiante')
        return render(request, 'simulador/pro_simulaciones/revisar.html', data)

    elif action == 'analitica':
        simulacion = _get_simulacion_profesor(request.user, request.GET.get('id'))
        data['simulacion'] = simulacion
        data['analitica'] = _analitica_simulacion(simulacion)
        return render(request, 'simulador/pro_simulaciones/analitica.html', data)

    elif action == 'analitica_export':
        simulacion = _get_simulacion_profesor(request.user, request.GET.get('id'))
        return _exportar_analitica_simulacion(simulacion)

    elif action == 'auditoria_export':
        return _exportar_auditoria_casos(request)

    if _tiene_acceso_global(request.user):
        data['list'] = _auditar_lista_simulaciones(list(_simulaciones_permitidas(request.user).select_related(
            'materia_malla__materia', 'materia_malla__nivel'
        ).all()))
        data['asignaciones'] = []
    else:
        data['list'] = _auditar_lista_simulaciones(list(_simulaciones_permitidas(request.user).select_related(
            'materia_malla__materia', 'materia_malla__nivel'
        ).distinct()))
        data['asignaciones'] = ProfesorMateria.objects.filter(
            profesor=request.user,
            activo=True,
        ).select_related('materia_malla__materia', 'materia_malla__nivel', 'periodo')
    return render(request, 'simulador/pro_simulaciones/view.html', data)
