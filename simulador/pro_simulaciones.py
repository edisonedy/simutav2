import json

from django import forms
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db import models
from decimal import Decimal
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from core.funciones import ok_json, bad_json
from academico.models import MateriaMalla, ProfesorMateria
from simulador.models import (
    Simulacion, IndicadorSimulacion, RestriccionSimulacion,
    ConceptoEsperadoRonda, CriterioEvaluacion, AccionSugeridaSimulacion, CondicionExitoSimulacion,
    DecisionConfigurada, EscenarioSimulacion, EventoSimulacion, IntentoSimulacion, RecursoSimulacion,
    MatrizEvaluacionCaso, OpcionCasoSimulacion,
)
from simulador.forms import (
    SimulacionForm, IndicadorSimulacionForm, RestriccionSimulacionForm,
    ConceptoEsperadoRondaForm, CriterioEvaluacionForm, AccionSugeridaForm, CondicionExitoForm,
    DecisionConfiguradaForm, EscenarioSimulacionForm, EventoSimulacionForm, RecursoSimulacionForm,
    MatrizEvaluacionCasoForm, OpcionCasoSimulacionForm,
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
    form.fields['materia_malla'].queryset = _materias_qs(profesor)
    return form


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
    n_acc = simulacion.acciones_sugeridas.filter(activo=True).count()
    n_evt = simulacion.eventos.filter(activo=True).count()
    n_opc_caso = simulacion.opciones_caso.filter(activo=True).count()
    n_mat_caso = simulacion.matriz_caso.filter(activo=True).count()
    caso_ok = all([simulacion.contexto, simulacion.objetivo, simulacion.situacion_inicial])

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
            'como_conecta': 'Es el corazon de la evaluacion: cada concepto tiene un peso y los pesos de cada ronda deben sumar 100.',
            'ok': rubrica_completa, 'opcional': False, 'aviso': n_con > 0 and not rubrica_completa,
            'detalle': f'{n_con} concepto(s)' + ('' if rubrica_completa else ' - revisar que cada ronda sume 100'),
            'url': url('conceptos'),
        },
        {
            'numero': 8, 'titulo': 'Decisiones sugeridas',
            'fase': 'consecuencias',
            'que_es': 'Opciones reales que el estudiante puede elegir, cada una con su efecto en los indicadores.',
            'como_conecta': 'Al elegir una, sus numeros cambian. El estudiante igual puede escribir su propia decision.',
            'ok': n_acc > 0, 'opcional': True, 'aviso': False,
            'detalle': f'{n_acc} decision(es) de ejemplo', 'url': url('acciones'),
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
        if paso['numero'] in [1, 2, 7]:
            esenciales.append(paso)
        else:
            avanzados.append(paso)
    return {
        'caso': [paso for paso in esenciales if paso['numero'] == 1],
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
    return form


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
    return {
        'total_intentos': intentos.count(),
        'finalizados': finalizados.count(),
        'promedio': round(float(promedio), 2) if promedio is not None else None,
        'promedio_rondas': list(pasos),
        'conceptos_fallados': conceptos_fallados,
        'alertas_recursos': alertas_recursos,
        'alertas_restricciones': alertas_restricciones,
        'alertas_total': alertas_recursos + alertas_restricciones,
    }


def _es_profesor(user):
    """Solo profesores/staff pueden usar el panel del profesor. Evita que un
    estudiante edite o borre simulaciones por ID (IDOR / acceso indebido)."""
    if user.is_superuser or user.is_staff:
        return True
    perfil = getattr(user, 'perfil', None)
    if perfil and perfil.rol in ('PROFESOR', 'ADMIN', 'COORDINADOR'):
        return True
    return ProfesorMateria.objects.filter(profesor=user, activo=True).exists()


def _tiene_acceso_global(user):
    if user.is_superuser:
        return True
    perfil = getattr(user, 'perfil', None)
    return bool(perfil and perfil.rol in ('ADMIN', 'COORDINADOR'))


def _simulaciones_permitidas(user):
    qs = Simulacion.objects.all()
    if _tiene_acceso_global(user):
        return qs
    return qs.filter(
        models.Q(profesor=user)
        | models.Q(usuario_creacion=user)
        | models.Q(materia_malla__profesores__profesor=user, materia_malla__profesores__activo=True)
    ).distinct()


def _get_simulacion_profesor(user, pk):
    return get_object_or_404(_simulaciones_permitidas(user), pk=pk)


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

        if action == 'add':
            form = _limit_form_materia(SimulacionForm(request.POST), request.user)
            _simplificar_form_creacion(form)
            if form.is_valid():
                simulacion = form.save(commit=False)
                simulacion.profesor = request.user
                simulacion.estado = Simulacion.BORRADOR
                simulacion.save()
                return ok_json(data={'id': simulacion.pk}, mensaje='Simulacion creada correctamente.')
            return bad_json(mensaje=str(form.errors))

        elif action == 'edit':
            simulacion = _get_simulacion_profesor(request.user, _request_id(request))
            form = _limit_form_materia(SimulacionForm(request.POST, instance=simulacion), request.user)
            _simplificar_form_creacion(form)
            if form.is_valid():
                form.save()
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
            form = AccionSugeridaForm(request.POST)
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
            form = AccionSugeridaForm(request.POST, instance=accion)
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
        return render(request, 'simulador/pro_simulaciones/datos_caso.html', data)

    elif action == 'acciones':
        simulacion = _get_simulacion_profesor(request.user, request.GET.get('id'))
        form = AccionSugeridaForm()
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

    if _tiene_acceso_global(request.user):
        data['list'] = _simulaciones_permitidas(request.user).select_related(
            'materia_malla__materia', 'materia_malla__nivel'
        ).all()
        data['asignaciones'] = []
    else:
        data['list'] = _simulaciones_permitidas(request.user).select_related(
            'materia_malla__materia', 'materia_malla__nivel'
        ).distinct()
        data['asignaciones'] = ProfesorMateria.objects.filter(
            profesor=request.user,
            activo=True,
        ).select_related('materia_malla__materia', 'materia_malla__nivel', 'periodo')
    return render(request, 'simulador/pro_simulaciones/view.html', data)
