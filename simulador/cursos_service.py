"""Logica de la capa de curso: libro de notas, analitica de cohorte,
logro de resultados de aprendizaje y tabla de posiciones.

Funciones puras sobre el ORM (sin tocar plantillas): las vistas las consumen.
La nota de un estudiante en una asignacion = su MEJOR intento finalizado de la
simulacion asignada (premia la mejora; encaja con el reintento existente)."""

from collections import Counter, defaultdict

from django.db.models import Count, Max

from simulador.models import (
    Asignacion,
    ConceptoEsperadoRonda,
    IntentoSimulacion,
    ResultadoAprendizaje,
)


def asignacion_para(estudiante, simulacion):
    """Asignacion vigente de esta simulacion para una seccion del estudiante.
    Devuelve None si la simulacion es de juego libre (no asignada a su curso)."""
    return (
        Asignacion.objects.filter(
            simulacion=simulacion,
            publicada=True,
            activo=True,
            seccion__estudiantes=estudiante,
            seccion__activo=True,
        )
        .select_related('seccion')
        .order_by('-fecha_apertura')
        .first()
    )


def equipo_de(estudiante, asignacion):
    """Equipo del estudiante dentro de una asignacion de trabajo en equipo."""
    if not asignacion or not asignacion.trabajo_en_equipo:
        return None
    return asignacion.equipos.filter(integrantes=estudiante, activo=True).first()


def _intentos_de(asignacion, estudiante):
    return IntentoSimulacion.objects.filter(
        estudiante=estudiante,
        simulacion=asignacion.simulacion,
        finalizado=True,
        activo=True,
    )


def nota_estudiante(asignacion, estudiante):
    """(mejor_nota, numero_de_intentos) del estudiante en la asignacion."""
    agg = _intentos_de(asignacion, estudiante).aggregate(
        mejor=Max('puntuacion_final'), n=Count('id'),
    )
    return agg['mejor'], agg['n']


def libro_notas(asignacion):
    """Una fila por estudiante de la seccion con su nota y estado de entrega."""
    minimo = asignacion.nota_minima_aprobacion
    estudiantes = asignacion.seccion.estudiantes.filter(is_active=True).order_by(
        'last_name', 'first_name', 'username',
    )
    filas = []
    for estudiante in estudiantes:
        mejor, n = nota_estudiante(asignacion, estudiante)
        if n == 0:
            estado = 'SIN_ENTREGAR'
        elif mejor is not None and mejor >= minimo:
            estado = 'APROBADO'
        else:
            estado = 'REPROBADO'
        filas.append({
            'estudiante': estudiante,
            'nombre': estudiante.get_full_name() or estudiante.username,
            'nota': mejor,
            'intentos': n,
            'estado': estado,
        })
    return filas


def resumen_asignacion(asignacion, filas=None):
    """Metricas agregadas de una asignacion (para analitica de cohorte)."""
    if filas is None:
        filas = libro_notas(asignacion)
    total = len(filas)
    notas = [f['nota'] for f in filas if f['nota'] is not None]
    entregados = len(notas)
    aprobados = sum(1 for f in filas if f['estado'] == 'APROBADO')
    promedio = round(sum(notas) / entregados, 2) if entregados else None
    return {
        'asignacion': asignacion,
        'total': total,
        'entregados': entregados,
        'sin_entregar': total - entregados,
        'aprobados': aprobados,
        'reprobados': entregados - aprobados,
        'promedio': promedio,
        'pct_entrega': round(entregados / total * 100) if total else 0,
        'pct_aprobacion': round(aprobados / entregados * 100) if entregados else 0,
    }


def analitica_seccion(seccion):
    """Resumen por cada asignacion de la seccion + totales del curso."""
    resumenes = [
        resumen_asignacion(a)
        for a in seccion.asignaciones.filter(activo=True).select_related('simulacion')
    ]
    promedios = [r['promedio'] for r in resumenes if r['promedio'] is not None]
    return {
        'asignaciones': resumenes,
        'promedio_curso': round(sum(promedios) / len(promedios), 2) if promedios else None,
        'total_asignaciones': len(resumenes),
        'total_estudiantes': seccion.estudiantes.filter(is_active=True).count(),
    }


def logro_resultados_aprendizaje(seccion):
    """Promedio de logro por Resultado de Aprendizaje (RA) de la materia.

    El logro de un RA = promedio de las notas de los intentos finalizados de la
    seccion sobre simulaciones que tienen al menos un concepto mapeado a ese RA.
    """
    ras = ResultadoAprendizaje.objects.filter(
        materia_malla=seccion.materia_malla, activo=True,
    )
    sim_ids = list(
        seccion.asignaciones.filter(activo=True).values_list('simulacion_id', flat=True)
    )
    estudiantes = seccion.estudiantes.filter(is_active=True)
    filas = []
    for ra in ras:
        sims_ra = set(
            ConceptoEsperadoRonda.objects.filter(
                resultado_aprendizaje=ra, simulacion_id__in=sim_ids, activo=True,
            ).values_list('simulacion_id', flat=True)
        )
        sims_ra.discard(None)
        if not sims_ra:
            filas.append({'ra': ra, 'simulaciones': 0, 'promedio': None, 'logro_pct': None})
            continue
        # logro = promedio del MEJOR intento por estudiante (consistente con el
        # libro de notas), no promedio de todos los intentos.
        mejores = (
            IntentoSimulacion.objects.filter(
                simulacion_id__in=sims_ra, estudiante__in=estudiantes,
                finalizado=True, activo=True,
            )
            .values('estudiante')
            .annotate(mejor=Max('puntuacion_final'))
            .values_list('mejor', flat=True)
        )
        mejores = [float(m) for m in mejores]
        prom = sum(mejores) / len(mejores) if mejores else None
        filas.append({
            'ra': ra,
            'simulaciones': len(sims_ra),
            'promedio': round(prom, 2) if prom is not None else None,
            'logro_pct': round(prom) if prom is not None else None,
        })
    return filas


def tabla_posiciones(asignacion, top=None):
    """Ranking de la asignacion por mejor nota. Si la asignacion es de equipo,
    rankea por equipo (mejor nota de cualquier integrante); si no, por estudiante."""
    if asignacion.trabajo_en_equipo:
        filas = []
        for equipo in asignacion.equipos.filter(activo=True).prefetch_related('integrantes'):
            mejor = IntentoSimulacion.objects.filter(
                simulacion=asignacion.simulacion,
                estudiante__in=equipo.integrantes.all(),
                finalizado=True, activo=True,
            ).aggregate(m=Max('puntuacion_final'))['m']
            if mejor is not None:
                filas.append({'nombre': equipo.nombre, 'nota': mejor, 'es_equipo': True})
    else:
        filas = []
        for fila in libro_notas(asignacion):
            if fila['nota'] is not None:
                filas.append({'nombre': fila['nombre'], 'nota': fila['nota'], 'es_equipo': False})
    filas.sort(key=lambda f: f['nota'], reverse=True)
    for i, fila in enumerate(filas, start=1):
        fila['posicion'] = i
    return filas[:top] if top else filas


def diagnostico_errores_asignacion(asignacion):
    """Patrones accionables para el docente sobre una tarea.

    No califica de nuevo: resume evidencia ya guardada en intentos/pasos para
    decidir que reforzar en clase.
    """
    estudiantes = list(asignacion.seccion.estudiantes.filter(is_active=True))
    intentos = list(
        IntentoSimulacion.objects.filter(
            simulacion=asignacion.simulacion,
            estudiante__in=estudiantes,
            finalizado=True,
            activo=True,
        )
        .select_related('estudiante')
        .prefetch_related('pasos')
        .order_by('estudiante_id', '-puntuacion_final', '-fecha_fin')
    )
    mejor_por_estudiante = {}
    for intento in intentos:
        if intento.estudiante_id not in mejor_por_estudiante:
            mejor_por_estudiante[intento.estudiante_id] = intento

    conceptos = Counter()
    indicadores_danados = Counter()
    pronosticos_fallidos = Counter()
    tradeoffs = Counter()
    invalidos = Counter()
    sin_reflexion = Counter()
    estudiantes_riesgo = []

    for estudiante in estudiantes:
        intento = mejor_por_estudiante.get(estudiante.id)
        if not intento:
            estudiantes_riesgo.append({
                'estudiante': estudiante,
                'motivo': 'Sin entrega',
                'nota': None,
            })
            continue
        if float(intento.puntuacion_final or 0) < float(asignacion.nota_minima_aprobacion):
            estudiantes_riesgo.append({
                'estudiante': estudiante,
                'motivo': 'Bajo minimo',
                'nota': intento.puntuacion_final,
            })
        for paso in intento.pasos.all():
            detalle = paso.evaluacion_detalle or {}
            for nombre in detalle.get('conceptos_faltantes') or []:
                conceptos[str(nombre)] += 1
            if not paso.es_valido:
                tipo = detalle.get('tipo_error') or 'respuesta_invalida'
                invalidos[str(tipo)] += 1
            if paso.es_valido and not paso.reflexion:
                sin_reflexion[estudiante.get_full_name() or estudiante.username] += 1
            if (paso.pronostico_resultado or {}).get('estado') == 'diferencia':
                codigo = paso.pronostico_resultado.get('indicador') or paso.pronostico_indicador or 'indicador'
                pronosticos_fallidos[str(codigo)] += 1
            for item in (paso.tradeoff_resultado or {}).get('sacrificios') or []:
                tradeoffs[str(item.get('nombre') or item.get('codigo') or 'sacrificio')] += 1
            for codigo, delta in (paso.impacto_calculado or {}).items():
                if isinstance(delta, (int, float)) and float(delta) < 0:
                    indicadores_danados[str(codigo)] += 1

    recomendaciones = []
    if conceptos:
        recomendaciones.append(f'Reforzar el concepto "{conceptos.most_common(1)[0][0]}" con un ejemplo guiado.')
    if pronosticos_fallidos:
        recomendaciones.append('Practicar lectura de indicadores antes de decidir: hay pronosticos que no coinciden con el resultado real.')
    if tradeoffs:
        recomendaciones.append('Discutir trade-offs en plenaria: los estudiantes estan aceptando sacrificios sin siempre justificar su valor.')
    if invalidos:
        recomendaciones.append('Modelar una respuesta valida: decision concreta, evidencia, indicador y consecuencia medible.')

    def top(counter, n=5):
        return [{'nombre': k, 'conteo': v} for k, v in counter.most_common(n)]

    return {
        'asignacion': asignacion,
        'intentos_analizados': len(mejor_por_estudiante),
        'conceptos_faltantes': top(conceptos),
        'indicadores_danados': top(indicadores_danados),
        'pronosticos_fallidos': top(pronosticos_fallidos),
        'tradeoffs_sacrificados': top(tradeoffs),
        'respuestas_invalidas': top(invalidos),
        'sin_reflexion': top(sin_reflexion),
        'estudiantes_riesgo': estudiantes_riesgo[:10],
        'recomendaciones': recomendaciones,
        'auditoria_caso': auditar_calidad_simulacion(asignacion.simulacion),
    }


def auditar_calidad_simulacion(simulacion):
    indicadores = simulacion.indicadores.filter(activo=True).count()
    conceptos = simulacion.conceptos_esperados.filter(activo=True).count()
    acciones = simulacion.acciones_sugeridas.filter(activo=True).count()
    restricciones = simulacion.restricciones.filter(activo=True).count()
    recursos = simulacion.recursos.filter(activo=True).count()
    eventos = simulacion.eventos.filter(activo=True).count()
    metas = simulacion.condiciones_exito.filter(activo=True).count()
    alternativas = simulacion.opciones_caso.filter(activo=True).count()
    conceptos_ra = simulacion.conceptos_esperados.filter(
        activo=True, resultado_aprendizaje__isnull=False,
    ).count()
    rondas = (simulacion.parametros or {}).get('rondas') or []
    rondas_sin_proposito = sum(
        1 for ronda in rondas if isinstance(ronda, dict) and not (ronda.get('proposito') or '').strip()
    )
    acciones_tradeoff = 0
    for accion in simulacion.acciones_sugeridas.filter(activo=True):
        impacto = accion.impacto_base or {}
        costo = accion.costo_recursos or {}
        positivos = sum(1 for v in impacto.values() if isinstance(v, (int, float)) and float(v) > 0)
        negativos = sum(1 for v in impacto.values() if isinstance(v, (int, float)) and float(v) < 0)
        costos = sum(1 for v in costo.values() if isinstance(v, (int, float)) and float(v) > 0)
        if positivos and (negativos or costos):
            acciones_tradeoff += 1

    hallazgos = []
    if indicadores < 3:
        hallazgos.append('Agregar al menos 3 indicadores propios de la materia.')
    if conceptos < max(1, simulacion.maximo_decisiones or 1):
        hallazgos.append('Configurar conceptos esperados por ronda.')
    if acciones < 3 and simulacion.tipo_simulacion == simulacion.TIPO_CON_IA_DINAMICA:
        hallazgos.append('Agregar al menos 3 decisiones sugeridas variadas.')
    if acciones and acciones_tradeoff == 0:
        hallazgos.append('Configurar decisiones con trade-offs reales: beneficio mas costo o riesgo.')
    if restricciones == 0:
        hallazgos.append('Agregar restricciones para que existan limites de negocio.')
    if recursos == 0:
        hallazgos.append('Agregar recursos limitados si el caso involucra presupuesto, tiempo o capacidad.')
    if eventos == 0:
        hallazgos.append('Agregar eventos dinamicos para que el caso reaccione al estado.')
    if metas == 0:
        hallazgos.append('Agregar al menos una meta final medible.')
    if rondas_sin_proposito:
        hallazgos.append('Indicar el aprendizaje que practica cada ronda.')
    if conceptos and conceptos_ra == 0 and not (simulacion.resultado_aprendizaje or '').strip():
        hallazgos.append('Vincular la rubrica con un resultado de aprendizaje.')

    puntaje = 100
    puntaje -= max(0, 3 - indicadores) * 12
    puntaje -= 20 if conceptos == 0 else 0
    puntaje -= 15 if acciones and acciones_tradeoff == 0 else 0
    puntaje -= 10 if restricciones == 0 else 0
    puntaje -= 10 if recursos == 0 else 0
    puntaje -= 8 if eventos == 0 else 0
    puntaje -= 10 if metas == 0 else 0
    puntaje -= min(12, rondas_sin_proposito * 4)
    puntaje = max(0, min(100, puntaje))
    if puntaje >= 80:
        nivel = 'Completo'
    elif puntaje >= 55:
        nivel = 'Mejorable'
    else:
        nivel = 'Debil'
    return {
        'puntaje': puntaje,
        'nivel': nivel,
        'indicadores': indicadores,
        'conceptos': conceptos,
        'acciones': acciones,
        'acciones_tradeoff': acciones_tradeoff,
        'restricciones': restricciones,
        'recursos': recursos,
        'eventos': eventos,
        'hallazgos': hallazgos,
    }
