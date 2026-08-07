"""Panel de cursos del profesor: secciones, asignaciones (tareas con fecha
limite), libro de notas, exportacion CSV, analitica de cohorte, logro de
resultados de aprendizaje y tabla de posiciones (competencia)."""

import csv
from collections import OrderedDict

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from core.funciones import bad_json, errores_formulario, ok_json, periodo_de_sesion
from simulador import cursos_service
from simulador.forms import (
    AsignacionForm,
    EquipoForm,
    ResultadoAprendizajeForm,
    SeccionForm,
)
from simulador.models import (
    ActividadMateria,
    Asignacion,
    ConceptoEsperadoRonda,
    Equipo,
    ResultadoAprendizaje,
    Seccion,
)
from simulador.pro_simulaciones import _es_profesor, _simulaciones_permitidas, _tiene_acceso_global


def _secciones_permitidas(user):
    qs = Seccion.objects.select_related('materia_malla__materia', 'periodo', 'profesor')
    if _tiene_acceso_global(user):
        return qs
    return qs.filter(profesor=user)


def _get_seccion(user, pk):
    return get_object_or_404(_secciones_permitidas(user), pk=pk)


def _get_asignacion(user, pk):
    asignacion = get_object_or_404(
        Asignacion.objects.select_related('seccion', 'simulacion'), pk=pk,
    )
    if not _secciones_permitidas(user).filter(pk=asignacion.seccion_id).exists():
        raise PermissionDenied('No tienes acceso a esta asignacion.')
    return asignacion


@login_required
@transaction.atomic
def view(request):
    if not _es_profesor(request.user):
        return redirect('dashboard')

    if request.method == 'POST':
        return _post(request)

    action = request.GET.get('action')
    if action == 'seccion':
        return _detalle_seccion(request)
    if action == 'notas':
        return _libro_notas(request)
    if action == 'diagnostico':
        return _diagnostico_errores(request)
    if action == 'diagnostico_export':
        return _exportar_diagnostico_csv(request)
    if action == 'export':
        return _exportar_csv(request)
    if action == 'add_seccion':
        return render(request, 'simulador/pro_cursos/add_seccion.html', {
            'form': SeccionForm(periodo=periodo_de_sesion(request)),
        })
    if action == 'add_asignacion':
        seccion = _get_seccion(request.user, request.GET.get('seccion'))
        form = AsignacionForm(
            simulaciones=_simulaciones_permitidas(request.user), seccion=seccion,
        )
        return render(request, 'simulador/pro_cursos/add_asignacion.html', {'form': form, 'seccion': seccion})
    if action == 'add_resultado':
        return render(request, 'simulador/pro_cursos/add_resultado.html', {'form': ResultadoAprendizajeForm()})
    if action == 'reporte_pdf':
        return _reporte_pdf(request)
    if action == 'mapeo':
        return _mapeo_ra(request)
    if action == 'equipos':
        return _equipos(request)
    if action == 'add_equipo':
        asignacion = _get_asignacion(request.user, request.GET.get('asignacion'))
        form = EquipoForm(estudiantes=asignacion.seccion.estudiantes.filter(is_active=True))
        return render(request, 'simulador/pro_cursos/add_equipo.html', {'form': form, 'asignacion': asignacion})

    # El listado se limita al periodo elegido arriba (el mismo criterio del SGA).
    # El scope de permisos NO se toca: entrar a un curso de otro periodo por su
    # enlace sigue funcionando.
    periodo = periodo_de_sesion(request)
    secciones = _secciones_permitidas(request.user).select_related(
        'materia_malla__malla__carrera', 'materia_malla__nivel',
    )
    secciones = secciones.filter(periodo=periodo) if periodo else secciones.none()
    # Agrupados por malla: el profesor necesita saber de que plan de estudios es
    # cada curso, sobre todo cuando dicta la misma materia en dos mallas.
    grupos = OrderedDict()
    total = 0
    for seccion in secciones.order_by(
        'materia_malla__malla__nombre',
        'materia_malla__nivel__numero',
        'materia_malla__materia__nombre',
    ):
        malla = seccion.materia_malla.malla
        grupo = grupos.setdefault(malla.pk, {'malla': malla, 'cursos': []})
        grupo['cursos'].append({
            'seccion': seccion,
            'estudiantes': seccion.estudiantes.count(),
            'asignaciones': seccion.asignaciones.filter(activo=True).count(),
        })
        total += 1
    return render(request, 'simulador/pro_cursos/cursos.html', {
        'title': 'Mis cursos',
        'grupos': list(grupos.values()),
        'total_cursos': total,
        'periodo': periodo,
    })


def _detalle_seccion(request):
    seccion = _get_seccion(request.user, request.GET.get('pk'))
    asignaciones = seccion.asignaciones.filter(activo=True).select_related('simulacion')
    contexto = {
        'seccion': seccion,
        'analitica': cursos_service.analitica_seccion(seccion),
        'resultados': cursos_service.logro_resultados_aprendizaje(seccion),
        'asignaciones': asignaciones,
        # Las guias APE son de la asignatura de la malla, no del paralelo: se
        # escriben una vez en Materias y sirven en todos los periodos. Aqui solo
        # se muestran, con enlace a donde se editan.
        'guias': ActividadMateria.objects.filter(
            materia_malla=seccion.materia_malla,
            tipo=ActividadMateria.GUIA_APE,
            activo=True,
        ).select_related('tema').order_by('tema__orden', 'orden', 'titulo'),
    }
    return render(request, 'simulador/pro_cursos/seccion.html', contexto)


def _reporte_pdf(request):
    from simulador import reportes
    seccion = _get_seccion(request.user, request.GET.get('pk'))
    pdf = reportes.reporte_acreditacion_pdf(seccion)
    materia = seccion.materia_malla.materia
    nombre = f'reporte_acreditacion_{materia.codigo}_{seccion.paralelo}.pdf'
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{nombre}"'
    return response


def _mapeo_ra(request):
    """Enlazar los conceptos de la rubrica (de las simulaciones asignadas) con
    los resultados de aprendizaje de la materia."""
    seccion = _get_seccion(request.user, request.GET.get('pk'))
    sim_ids = list(seccion.asignaciones.filter(activo=True).values_list('simulacion_id', flat=True))
    conceptos = ConceptoEsperadoRonda.objects.filter(
        simulacion_id__in=sim_ids, activo=True,
    ).select_related('simulacion', 'resultado_aprendizaje').order_by('simulacion__titulo', 'numero_ronda', 'nombre')
    contexto = {
        'seccion': seccion,
        'conceptos': conceptos,
        'resultados': ResultadoAprendizaje.objects.filter(materia_malla=seccion.materia_malla, activo=True),
    }
    return render(request, 'simulador/pro_cursos/mapeo.html', contexto)


def _equipos(request):
    asignacion = _get_asignacion(request.user, request.GET.get('pk'))
    contexto = {
        'asignacion': asignacion,
        'equipos': asignacion.equipos.filter(activo=True).prefetch_related('integrantes'),
        'posiciones': cursos_service.tabla_posiciones(asignacion),
    }
    return render(request, 'simulador/pro_cursos/equipos.html', contexto)


def _libro_notas(request):
    asignacion = _get_asignacion(request.user, request.GET.get('pk'))
    filas = cursos_service.libro_notas(asignacion)
    contexto = {
        'asignacion': asignacion,
        'filas': filas,
        'resumen': cursos_service.resumen_asignacion(asignacion, filas),
        'posiciones': cursos_service.tabla_posiciones(asignacion, top=10),
    }
    return render(request, 'simulador/pro_cursos/notas.html', contexto)


def _diagnostico_errores(request):
    asignacion = _get_asignacion(request.user, request.GET.get('pk'))
    contexto = {
        'asignacion': asignacion,
        'diagnostico': cursos_service.diagnostico_errores_asignacion(asignacion),
    }
    return render(request, 'simulador/pro_cursos/diagnostico.html', contexto)


def _exportar_diagnostico_csv(request):
    asignacion = _get_asignacion(request.user, request.GET.get('pk'))
    diagnostico = cursos_service.diagnostico_errores_asignacion(asignacion)
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    nombre = f'diagnostico_{asignacion.seccion.materia_malla.materia.codigo}_{asignacion.pk}.csv'
    response['Content-Disposition'] = f'attachment; filename="{nombre}"'
    response.write('﻿')
    writer = csv.writer(response)
    writer.writerow(['Categoria', 'Elemento', 'Conteo'])
    categorias = [
        ('Concepto faltante', 'conceptos_faltantes'),
        ('Pronostico fallido', 'pronosticos_fallidos'),
        ('Sacrificio frecuente', 'tradeoffs_sacrificados'),
        ('Indicador deteriorado', 'indicadores_danados'),
        ('Respuesta invalida', 'respuestas_invalidas'),
        ('Reflexion pendiente', 'sin_reflexion'),
    ]
    for etiqueta, clave in categorias:
        for item in diagnostico.get(clave) or []:
            writer.writerow([etiqueta, item['nombre'], item['conteo']])
    writer.writerow([])
    writer.writerow(['Estudiante en riesgo', 'Motivo', 'Nota'])
    for item in diagnostico['estudiantes_riesgo']:
        estudiante = item['estudiante'].get_full_name() or item['estudiante'].username
        writer.writerow([estudiante, item['motivo'], item['nota'] if item['nota'] is not None else ''])
    writer.writerow([])
    writer.writerow(['Recomendacion', '', ''])
    for rec in diagnostico['recomendaciones']:
        writer.writerow([rec, '', ''])
    auditoria = diagnostico.get('auditoria_caso') or {}
    if auditoria:
        writer.writerow([])
        writer.writerow(['Auditoria del caso', auditoria.get('nivel', ''), auditoria.get('puntaje', '')])
        for hallazgo in auditoria.get('hallazgos') or []:
            writer.writerow(['Hallazgo', hallazgo, ''])
    return response


def _exportar_csv(request):
    asignacion = _get_asignacion(request.user, request.GET.get('pk'))
    filas = cursos_service.libro_notas(asignacion)
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    nombre = f'notas_{asignacion.seccion.materia_malla.materia.codigo}_{asignacion.pk}.csv'
    response['Content-Disposition'] = f'attachment; filename="{nombre}"'
    response.write('﻿')  # BOM para que Excel respete los acentos
    writer = csv.writer(response)
    writer.writerow(['Estudiante', 'Nota', 'Intentos', 'Estado'])
    for fila in filas:
        nota = '' if fila['nota'] is None else f"{fila['nota']:.2f}"
        writer.writerow([fila['nombre'], nota, fila['intentos'], fila['estado']])
    return response


def _post(request):
    action = request.POST.get('action')
    if action == 'add_seccion':
        form = SeccionForm(request.POST)
        if form.is_valid():
            seccion = form.save(commit=False)
            seccion.profesor = request.user
            seccion.usuario_creacion = request.user
            seccion.save()
            form.save_m2m()
            return ok_json(mensaje='Curso creado')
        return bad_json(mensaje=errores_formulario(form), data={'errors': form.errors})

    if action == 'add_asignacion':
        seccion = _get_seccion(request.user, request.POST.get('seccion'))
        form = AsignacionForm(
            request.POST, simulaciones=_simulaciones_permitidas(request.user), seccion=seccion,
        )
        if form.is_valid():
            asignacion = form.save(commit=False)
            asignacion.seccion = seccion
            asignacion.usuario_creacion = request.user
            asignacion.save()
            return ok_json(mensaje='Tarea asignada')
        return bad_json(mensaje=errores_formulario(form), data={'errors': form.errors})

    if action == 'add_resultado':
        form = ResultadoAprendizajeForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.usuario_creacion = request.user
            obj.save()
            return ok_json(mensaje='Resultado de aprendizaje creado')
        return bad_json(mensaje=errores_formulario(form), data={'errors': form.errors})

    if action == 'map_concepto':
        seccion = _get_seccion(request.user, request.POST.get('seccion'))
        sim_ids = list(seccion.asignaciones.filter(activo=True).values_list('simulacion_id', flat=True))
        concepto = get_object_or_404(
            ConceptoEsperadoRonda, pk=request.POST.get('concepto'), simulacion_id__in=sim_ids,
        )
        ra_id = request.POST.get('resultado') or None
        if ra_id:
            ra = get_object_or_404(
                ResultadoAprendizaje, pk=ra_id, materia_malla=seccion.materia_malla, activo=True,
            )
            concepto.resultado_aprendizaje = ra
        else:
            concepto.resultado_aprendizaje = None
        concepto.save(update_fields=['resultado_aprendizaje'])
        return ok_json(mensaje='Mapeo guardado')

    if action == 'add_equipo':
        asignacion = _get_asignacion(request.user, request.POST.get('asignacion'))
        form = EquipoForm(request.POST, estudiantes=asignacion.seccion.estudiantes.filter(is_active=True))
        if form.is_valid():
            equipo = form.save(commit=False)
            equipo.asignacion = asignacion
            equipo.usuario_creacion = request.user
            equipo.save()
            form.save_m2m()
            return ok_json(mensaje='Equipo creado')
        return bad_json(mensaje=errores_formulario(form), data={'errors': form.errors})

    if action == 'delete_equipo':
        equipo = get_object_or_404(Equipo, pk=request.POST.get('pk'))
        if not _secciones_permitidas(request.user).filter(pk=equipo.asignacion.seccion_id).exists():
            raise PermissionDenied('No tienes acceso a este equipo.')
        equipo.activo = False
        equipo.save()
        return ok_json(mensaje='Equipo eliminado')

    if action == 'delete_asignacion':
        asignacion = _get_asignacion(request.user, request.POST.get('pk'))
        asignacion.activo = False
        asignacion.save()
        return ok_json(mensaje='Tarea eliminada')

    return bad_json(mensaje='Accion no valida')
