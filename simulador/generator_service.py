import json
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from simulador.models import (
    AccionSugeridaSimulacion,
    ConceptoEsperadoRonda,
    CriterioEvaluacion,
    IndicadorSimulacion,
    PerfilMateriaIA,
    PlantillaSimulacion,
    RestriccionSimulacion,
    Simulacion,
)


def obtener_plantilla_predeterminada():
    return (
        PlantillaSimulacion.objects.filter(activo=True, es_predeterminada=True).order_by('-version').first()
        or PlantillaSimulacion.objects.filter(activo=True).order_by('-version', 'nombre').first()
    )


def obtener_o_crear_perfil_materia(materia_malla, usuario=None):
    perfil, _ = PerfilMateriaIA.objects.get_or_create(
        materia_malla=materia_malla,
        defaults={
            'rol_profesional': f'Analista en {materia_malla.materia.nombre}',
            'enfoque': materia_malla.materia.descripcion or materia_malla.materia.nombre,
            'temas_clave': [materia_malla.materia.nombre],
            'conceptos_clave': [materia_malla.materia.nombre],
            'usuario_creacion': usuario,
        },
    )
    return perfil


def _lista_texto(valor):
    if isinstance(valor, list):
        return ', '.join(str(item) for item in valor if str(item).strip())
    return str(valor or '')


def _render(texto, materia_malla, perfil):
    materia = materia_malla.materia.nombre
    rol = perfil.rol_profesional or f'Analista en {materia}'
    contexto = {
        'materia': materia,
        'nivel': materia_malla.nivel.numero,
        'rol': rol,
        'temas': _lista_texto(perfil.temas_clave),
        'conceptos': _lista_texto(perfil.conceptos_clave),
        'competencias': _lista_texto(perfil.competencias),
    }
    try:
        return (texto or '').format(**contexto)
    except (KeyError, ValueError):
        return texto or ''


def _render_json(valor, materia_malla, perfil):
    if isinstance(valor, dict):
        return {clave: _render_json(item, materia_malla, perfil) for clave, item in valor.items()}
    if isinstance(valor, list):
        return [_render_json(item, materia_malla, perfil) for item in valor]
    if isinstance(valor, str):
        return _render(valor, materia_malla, perfil)
    return valor


def _json_safe(valor):
    return json.loads(json.dumps(valor, default=str))


def serializar_configuracion_simulacion(simulacion):
    snapshot = {
        'simulacion_id': simulacion.id,
        'caso': {
            'titulo': simulacion.titulo,
            'tema': simulacion.tema,
            'tipo_simulacion': simulacion.tipo_simulacion,
            'nivel_dificultad': simulacion.nivel_dificultad,
            'maximo_decisiones': simulacion.maximo_decisiones,
            'tiempo_estimado': simulacion.tiempo_estimado,
            'rol_estudiante': simulacion.rol_estudiante,
            'contexto': simulacion.contexto,
            'objetivo': simulacion.objetivo,
            'resultado_aprendizaje': simulacion.resultado_aprendizaje,
            'situacion_inicial': simulacion.situacion_inicial,
            'instrucciones_ia': simulacion.instrucciones_ia,
            'parametros': simulacion.parametros or {},
            'peso_rubrica_decision': simulacion.peso_rubrica_decision,
        },
        'plantilla_origen_id': simulacion.plantilla_origen_id,
        'perfil_materia_ia_id': simulacion.perfil_materia_ia_id,
        'version_configuracion': simulacion.version_configuracion,
        'modelo_ia': simulacion.modelo_ia,
        'prompt_version': simulacion.prompt_version,
        'esquema_ia_version': simulacion.esquema_ia_version,
        'indicadores': list(
            simulacion.indicadores.filter(activo=True).values(
                'id', 'codigo', 'nombre', 'valor_inicial', 'valor_minimo',
                'valor_maximo', 'direccion_optima', 'valor_objetivo',
                'valor_objetivo_min', 'valor_objetivo_max',
                'peso_salud', 'es_critico', 'unidad',
            )
        ),
        'restricciones': list(
            simulacion.restricciones.filter(activo=True).values(
                'id', 'descripcion', 'codigo_indicador', 'operador', 'valor_limite', 'penalizacion',
            )
        ),
        'condiciones_exito': list(
            simulacion.condiciones_exito.filter(activo=True).values(
                'id', 'descripcion', 'codigo_indicador', 'operador',
                'valor_objetivo', 'bonificacion',
            )
        ),
        'conceptos': list(
            simulacion.conceptos_esperados.filter(activo=True).values(
                'id', 'numero_ronda', 'nombre', 'descripcion', 'regla_evaluacion',
                'palabras_clave', 'peso', 'impacto_si_cumple', 'impacto_si_falta',
                'retroalimentacion_si_cumple', 'retroalimentacion_si_falta', 'es_critico',
            )
        ),
        'acciones_sugeridas': list(
            simulacion.acciones_sugeridas.filter(activo=True).values(
                'id', 'numero_ronda', 'opcion_caso_id', 'requiere_accion_previa_id',
                'bloqueada_por_accion_previa_id', 'maximo_ejecuciones',
                'texto', 'descripcion', 'puntaje', 'retroalimentacion',
                'impacto_base', 'costo_recursos',
            )
        ),
        'matriz_caso': list(
            simulacion.matriz_caso.filter(activo=True).values(
                'criterio', 'peso', 'evalua', 'orden',
            )
        ),
        'opciones_caso': list(
            simulacion.opciones_caso.filter(activo=True).values(
                'id', 'nombre', 'subtitulo', 'valor_referencia',
                'fortaleza', 'riesgo', 'resultados', 'orden',
            )
        ),
        'recursos': list(
            simulacion.recursos.filter(activo=True).values(
                'id', 'codigo', 'nombre', 'valor_inicial', 'valor_minimo',
                'valor_maximo', 'unidad', 'es_critico',
            )
        ),
        'investigaciones': list(
            simulacion.investigaciones.filter(activo=True).values(
                'id', 'sujeto', 'nombre', 'descripcion', 'hallazgo',
                'costo_recursos', 'disponible_desde_ronda', 'orden',
            )
        ),
        'eventos': list(
            simulacion.eventos.filter(activo=True).values(
                'id', 'nombre', 'mensaje', 'ronda',
                'codigo_indicador_condicion', 'operador_condicion',
                'valor_condicion', 'efecto', 'prioridad',
            )
        ),
    }
    return _json_safe(snapshot)


@transaction.atomic
def generar_simulacion_desde_plantilla(materia_malla, profesor, plantilla=None, perfil=None, publicar=False):
    plantilla = plantilla or obtener_plantilla_predeterminada()
    if not plantilla:
        raise ValueError('No existe una plantilla activa para generar simulaciones.')

    perfil = perfil or obtener_o_crear_perfil_materia(materia_malla, usuario=profesor)
    materia = materia_malla.materia.nombre
    rol = perfil.rol_profesional or plantilla.rol_base or f'Analista en {materia}'
    rondas_plantilla = list(plantilla.rondas.filter(activo=True).order_by('numero'))
    if not rondas_plantilla:
        raise ValueError('La plantilla no tiene rondas activas para generar el caso.')
    cantidad_rondas = len(rondas_plantilla)
    rondas_parametros = [
        {
            'numero': ronda.numero,
            'titulo': _render(ronda.titulo, materia_malla, perfil),
            'proposito': _render(ronda.proposito, materia_malla, perfil),
            'situacion': _render(ronda.consigna_base, materia_malla, perfil),
            'opciones_decision': _render_json(ronda.opciones_decision or [], materia_malla, perfil),
            'modo': 'hibrido' if ronda.opciones_decision else 'escribir',
            'etiqueta_decision': _render(ronda.etiqueta_decision, materia_malla, perfil) or 'Tu respuesta',
            'etiqueta_justificacion': (
                _render(ronda.etiqueta_justificacion, materia_malla, perfil)
                or 'Explica tu razonamiento'
            ),
            'justificacion_obligatoria': True,
            'mostrar_objetivos': True,
            'mostrar_rubrica': True,
            'mostrar_datos_caso': True,
            'mostrar_resultados_alternativas': False,
            'mostrar_indicadores': True,
            'mostrar_recursos': True,
            'mostrar_investigaciones': False,
            'pedir_pronostico': False,
            'pedir_tradeoff': False,
            'pedir_reflexion': False,
        }
        for ronda in rondas_plantilla
    ]
    situacion_inicial = (
        rondas_parametros[0]['situacion']
        if rondas_parametros and rondas_parametros[0].get('situacion')
        else _render(plantilla.contexto_base, materia_malla, perfil)
    )

    simulacion = Simulacion.objects.create(
        materia_malla=materia_malla,
        plantilla_origen=plantilla,
        perfil_materia_ia=perfil,
        profesor=profesor,
        tipo_simulacion=Simulacion.TIPO_CON_IA_DINAMICA,
        titulo=f'Simulacion SimutaV2 - {materia}',
        tema=_lista_texto(perfil.temas_clave) or materia,
        nivel_dificultad=plantilla.nivel_dificultad or Simulacion.DIFICULTAD_MEDIA,
        maximo_decisiones=cantidad_rondas,
        tiempo_estimado=plantilla.tiempo_estimado,
        rol_estudiante=rol,
        contexto=_render(plantilla.contexto_base, materia_malla, perfil),
        objetivo=_render(plantilla.objetivo_base, materia_malla, perfil),
        resultado_aprendizaje=_render(plantilla.resultado_base, materia_malla, perfil),
        situacion_inicial=situacion_inicial,
        instrucciones_ia=plantilla.instrucciones_ia,
        parametros={
            'modo': 'toma_decisiones',
            'rondas': rondas_parametros,
        },
        metadata_generacion={
            'origen': 'plantilla',
            'plantilla_codigo': plantilla.codigo,
            'plantilla_version': plantilla.version,
            'perfil_materia_ia_id': perfil.id,
        },
        version_configuracion=1,
        api_ia='responses',
        modelo_ia=getattr(settings, 'OPENAI_MODEL', ''),
        usuario_creacion=profesor,
    )

    for indicador in plantilla.indicadores.filter(activo=True):
        IndicadorSimulacion.objects.create(
            simulacion=simulacion,
            codigo=indicador.codigo,
            nombre=indicador.nombre,
            valor_inicial=indicador.valor_inicial,
            valor_minimo=indicador.valor_minimo,
            valor_maximo=indicador.valor_maximo,
            direccion_optima=indicador.direccion_optima,
            valor_objetivo=getattr(indicador, 'valor_objetivo', None),
            valor_objetivo_min=getattr(indicador, 'valor_objetivo_min', None),
            valor_objetivo_max=getattr(indicador, 'valor_objetivo_max', None),
            es_critico=indicador.es_critico,
            unidad=indicador.unidad,
            usuario_creacion=profesor,
        )

    for restriccion in plantilla.restricciones.filter(activo=True):
        RestriccionSimulacion.objects.create(
            simulacion=simulacion,
            descripcion=restriccion.descripcion,
            codigo_indicador=restriccion.codigo_indicador,
            operador=restriccion.operador,
            valor_limite=restriccion.valor_limite,
            penalizacion=restriccion.penalizacion,
            usuario_creacion=profesor,
        )

    peso_base = Decimal('100') // Decimal(cantidad_rondas)
    peso_acumulado = Decimal('0')
    for indice, ronda in enumerate(rondas_plantilla):
        peso_criterio = (
            Decimal('100') - peso_acumulado
            if indice == cantidad_rondas - 1 else peso_base
        )
        CriterioEvaluacion.objects.create(
            simulacion=simulacion,
            nombre=ronda.titulo,
            descripcion=ronda.proposito or f'Criterio orientativo de {materia}: {ronda.titulo}.',
            peso=peso_criterio,
            puntaje_maximo=100,
            usuario_creacion=profesor,
        )
        peso_acumulado += peso_criterio
        for concepto in ronda.conceptos.filter(activo=True):
            regla = _render_json(concepto.regla_evaluacion or {}, materia_malla, perfil)
            ConceptoEsperadoRonda.objects.create(
                simulacion=simulacion,
                numero_ronda=ronda.numero,
                nombre=concepto.nombre,
                descripcion=_render(concepto.descripcion, materia_malla, perfil),
                palabras_clave=json.dumps(regla, ensure_ascii=False),
                regla_evaluacion=regla,
                peso=concepto.peso,
                impacto_si_cumple=concepto.impacto_si_cumple,
                impacto_si_falta=concepto.impacto_si_falta,
                retroalimentacion_si_cumple=concepto.retroalimentacion_si_cumple,
                retroalimentacion_si_falta=concepto.retroalimentacion_si_falta,
                es_critico=concepto.es_critico,
                usuario_creacion=profesor,
            )
        for opcion in ronda.opciones_decision or []:
            if isinstance(opcion, dict):
                texto = _render(str(opcion.get('texto') or ''), materia_malla, perfil).strip()
                descripcion = _render(str(opcion.get('descripcion') or ''), materia_malla, perfil).strip()
                impacto = opcion.get('impacto') if isinstance(opcion.get('impacto'), dict) else {}
            else:
                texto = _render(str(opcion or ''), materia_malla, perfil).strip()
                descripcion = ''
                impacto = {}
            if not texto:
                continue
            AccionSugeridaSimulacion.objects.create(
                simulacion=simulacion,
                numero_ronda=ronda.numero,
                texto=texto,
                descripcion=descripcion,
                impacto_base=impacto,
                usuario_creacion=profesor,
            )

    simulacion.configuracion_snapshot = serializar_configuracion_simulacion(simulacion)
    if publicar:
        simulacion.estado = Simulacion.PUBLICADA
        simulacion.configuracion_bloqueada = True
        simulacion.fecha_publicacion = timezone.now()
        simulacion.fecha_bloqueo = simulacion.fecha_publicacion
    simulacion.save(update_fields=[
        'configuracion_snapshot', 'estado', 'configuracion_bloqueada',
        'fecha_publicacion', 'fecha_bloqueo',
    ])
    return simulacion
