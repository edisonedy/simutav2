from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from academico.forms import MateriaForm, MateriaPeriodoForm
from academico.models import (
    Malla,
    MallaPeriodo,
    Materia,
    MateriaMalla,
    MateriaPeriodo,
    NivelMalla,
)
from core.funciones import errores_formulario, periodo_de_sesion, respuesta_error, respuesta_ok
from core.permisos import es_administrativo, es_docente
from simulador.forms import ActividadMateriaForm, TemaMateriaForm
from simulador.models import ActividadMateria, Simulacion, TemaMateria


def _url_malla(malla_id):
    """Las aperturas de la malla en el periodo."""
    return f"{reverse('adm_materias')}?action=malla&pk={malla_id}"


def _url_apertura(malla_periodo_id):
    """Las materias creadas dentro de una apertura concreta."""
    return f"{reverse('adm_materias')}?action=apertura&pk={malla_periodo_id}"


def _url_materia(materia_malla_id, malla_periodo_id=None):
    url = f"{reverse('adm_materias')}?action=detalle&pk={materia_malla_id}"
    if malla_periodo_id:
        url += f"&malla_periodo={malla_periodo_id}"
    return url


def _exigir_administrativo(user):
    if not es_administrativo(user):
        raise PermissionDenied('Solo administracion puede modificar el catalogo academico.')


def _materias_permitidas(user):
    qs = MateriaMalla.objects.filter(
        activo=True, malla__activo=True, materia__activo=True,
    ).select_related('malla__carrera', 'nivel', 'materia')
    if es_administrativo(user):
        return qs
    return qs.filter(
        Q(profesores__profesor=user, profesores__activo=True)
        | Q(secciones__profesor=user, secciones__activo=True),
    ).distinct()


def _get_materia_malla(user, pk):
    return get_object_or_404(_materias_permitidas(user), pk=pk)


def _mallas_del_periodo(user, periodo):
    """El hub de materias: todas las mallas del catalogo, con el estado de su
    apertura en el periodo elegido.

    Antes solo salian las mallas abiertas en el periodo, y una malla recien
    creada quedaba invisible sin manera obvia de llegar a ella.
    """
    qs = Malla.objects.filter(activo=True).select_related('carrera')

    if not es_administrativo(user):
        permitidas = _materias_permitidas(user)
        qs = qs.filter(materias_malla__in=permitidas).distinct()
        filtro_niveles = Q(niveles__activo=True, niveles__materias_malla__in=permitidas)
        filtro_asignaturas = Q(
            materias_malla__activo=True, materias_malla__in=permitidas,
        )
    else:
        filtro_niveles = Q(niveles__activo=True)
        filtro_asignaturas = Q(materias_malla__activo=True)

    qs = qs.annotate(
        total_niveles=Count('niveles', filter=filtro_niveles, distinct=True),
        total_asignaturas=Count(
            'materias_malla', filter=filtro_asignaturas, distinct=True,
        ),
    ).order_by('carrera__nombre', 'nombre')

    # Una malla puede tener VARIAS aperturas en el mismo periodo, asi que se
    # agrupan en lista y no en un solo enlace.
    aperturas = {}
    if periodo is not None:
        for enlace in MallaPeriodo.objects.filter(
            periodo=periodo, activo=True,
        ).annotate(
            total_materias=Count('materias', filter=Q(materias__activo=True), distinct=True),
        ).order_by('nombre', 'pk'):
            aperturas.setdefault(enlace.malla_id, []).append(enlace)

    filas = []
    for malla in qs:
        de_esta = aperturas.get(malla.pk, [])
        filas.append({
            'malla': malla,
            'aperturas': de_esta,
            'total_aperturas': len(de_esta),
            'total_niveles': malla.total_niveles,
            'total_asignaturas': malla.total_asignaturas,
            'total_materias': sum(a.total_materias for a in de_esta),
        })
    return filas


def _estructura_malla(malla, malla_periodo, permitidas):
    """Las materias CREADAS en el periodo, agrupadas por nivel.

    Solo se lista lo que existe: la materia aparece cuando se crea, y es ahi
    donde viven sus temas, sus juegos y sus casos. Mostrar tambien las
    asignaturas sin crear confundia, porque salian con contadores de contenido
    que en realidad son del plan y no de la materia.

    Devuelve (grupos, creadas, pendientes); `pendientes` es solo el contador que
    necesita el boton de crear.
    """
    if malla_periodo is None:
        pendientes = permitidas.filter(malla=malla).count()
        return [], 0, pendientes

    materias = MateriaPeriodo.objects.filter(
        malla_periodo=malla_periodo,
        materia_malla__in=permitidas.filter(malla=malla),
        activo=True,
    ).select_related(
        'materia_malla__materia',
        'materia_malla__nivel',
    ).annotate(
        total_temas=Count(
            'materia_malla__temas',
            filter=Q(materia_malla__temas__activo=True),
            distinct=True,
        ),
        total_actividades=Count(
            'materia_malla__actividades',
            filter=Q(materia_malla__actividades__activo=True),
            distinct=True,
        ),
        total_simulaciones=Count(
            'materia_malla__simulaciones',
            filter=Q(materia_malla__simulaciones__activo=True),
            distinct=True,
        ),
        total_juegos=Count(
            'materia_malla__actividades_interactivas',
            filter=Q(materia_malla__actividades_interactivas__activo=True),
            distinct=True,
        ),
    ).order_by(
        'materia_malla__nivel__numero',
        'materia_malla__orden',
        'materia_malla__materia__nombre',
    )

    por_nivel = {}
    for materia in materias:
        por_nivel.setdefault(materia.materia_malla.nivel_id, []).append({
            'materia_malla': materia.materia_malla,
            'materia_periodo': materia,
            'total_temas': materia.total_temas,
            'total_actividades': materia.total_actividades,
            'total_simulaciones': materia.total_simulaciones,
            'total_juegos': materia.total_juegos,
        })

    grupos = []
    niveles = NivelMalla.objects.filter(malla=malla, activo=True).order_by('numero')
    for nivel in niveles:
        filas = por_nivel.get(nivel.pk, [])
        if not filas:
            continue
        grupos.append({'nivel': nivel, 'filas': filas, 'total': len(filas)})

    creadas = len(materias)
    pendientes = malla_periodo.asignaturas_disponibles().filter(
        pk__in=permitidas.filter(malla=malla).values('pk'),
    ).count()
    return grupos, creadas, pendientes


def _contenido_materia(materia_malla):
    actividades = list(
        ActividadMateria.objects.filter(
            materia_malla=materia_malla, activo=True,
        ).select_related('tema').order_by('tema__orden', 'categoria', 'orden', 'titulo')
    )
    simulaciones = list(
        Simulacion.objects.filter(
            materia_malla=materia_malla, activo=True,
        ).select_related('tema_materia').order_by('tema_materia__orden', 'titulo')
    )

    def separar(tema_id):
        return {
            'refuerzo': [
                a for a in actividades
                if a.tema_id == tema_id and a.categoria == ActividadMateria.REFUERZO
            ],
            'evaluacion': [
                a for a in actividades
                if a.tema_id == tema_id and a.categoria == ActividadMateria.EVALUACION
            ],
            'simulaciones': [s for s in simulaciones if s.tema_materia_id == tema_id],
        }

    temas = []
    for tema in TemaMateria.objects.filter(
        materia_malla=materia_malla, activo=True,
    ).order_by('orden', 'nombre'):
        contenido = separar(tema.pk)
        # Un tema sin actividades sigue apareciendo porque el docente lo creo
        # expresamente y necesita poder empezar a cargar su contenido.
        temas.append({'tema': tema, **contenido})
    return separar(None), temas


@login_required
@transaction.atomic
def view(request):
    if not (es_administrativo(request.user) or es_docente(request.user)):
        raise PermissionDenied('No tienes permiso para administrar materias.')

    if request.method == 'POST':
        return _post(request)
    return _get(request)


def _post(request):
    action = request.POST.get('action')
    listado = reverse('adm_materias')

    if action == 'add':
        _exigir_administrativo(request.user)
        malla_id = request.POST.get('malla')
        nivel_id = request.POST.get('nivel')
        malla = get_object_or_404(Malla, pk=malla_id, activo=True) if malla_id else None
        # Si se crea desde un nivel, se vuelve a la malla y no al listado.
        retorno = _url_malla(malla.pk) if malla else listado
        form = MateriaForm(request.POST)
        if form.is_valid():
            materia = form.save(commit=False)
            materia.usuario_creacion = request.user
            materia.save()
            if malla and nivel_id:
                nivel = get_object_or_404(
                    NivelMalla, pk=nivel_id, malla=malla, activo=True,
                )
                MateriaMalla.objects.create(
                    malla=malla, nivel=nivel, materia=materia,
                    usuario_creacion=request.user,
                )
            return respuesta_ok(request, retorno)
        return respuesta_error(request, retorno, errores_formulario(form), {'errors': form.errors})

    if action == 'add_malla_periodo':
        _exigir_administrativo(request.user)
        malla = get_object_or_404(Malla, pk=request.POST.get('malla'), activo=True)
        periodo = periodo_de_sesion(request)

        if periodo is None:
            return respuesta_error(
                request,
                listado,
                'Primero debes crear y seleccionar un periodo academico.',
            )

        # Sin nombre propio la apertura se llama como la malla (nombre_visible).
        nombre = (request.POST.get('nombre') or '').strip()

        enlace = MallaPeriodo.objects.filter(
            periodo=periodo,
            malla=malla,
            nombre=nombre,
        ).first()

        if enlace and enlace.activo:
            return respuesta_error(
                request,
                listado,
                'Ya existe una apertura activa con esa malla y ese nombre.',
            )

        if enlace:
            enlace.activo = True
            enlace.save(update_fields=[
                'activo',
                'fecha_modificacion',
            ])
        else:
            enlace = MallaPeriodo.objects.create(
                periodo=periodo,
                malla=malla,
                nombre=nombre,
                usuario_creacion=request.user,
            )

        return respuesta_ok(
            request,
            _url_apertura(enlace.pk),
            'Malla abierta en el periodo',
        )

    if action in ('add_materia_periodo', 'add_materias_bloque'):
        _exigir_administrativo(request.user)
        malla_periodo = get_object_or_404(
            MallaPeriodo.objects.select_related('malla', 'periodo'),
            pk=request.POST.get('malla_periodo'),
            periodo=periodo_de_sesion(request), activo=True,
        )
        retorno = _url_apertura(malla_periodo.pk)

        if action == 'add_materia_periodo':
            nivel = None
            nivel_id = request.POST.get('nivel')
            if nivel_id:
                nivel = get_object_or_404(
                    NivelMalla,
                    pk=nivel_id,
                    malla=malla_periodo.malla,
                    activo=True,
                )

            form = MateriaPeriodoForm(
                request.POST,
                malla_periodo=malla_periodo,
                nivel=nivel,
            )
            if not form.is_valid():
                return respuesta_error(
                    request, retorno, errores_formulario(form), {'errors': form.errors},
                )
            materia_malla = form.cleaned_data['materia_malla']
            materia = MateriaPeriodo.objects.filter(
                malla_periodo=malla_periodo,
                materia_malla=materia_malla,
            ).first()

            if materia:
                materia.activo = True
                materia.save(update_fields=['activo', 'fecha_modificacion'])
            else:
                materia = form.save(commit=False)
                materia.malla_periodo = malla_periodo
                materia.usuario_creacion = request.user
                materia.full_clean()
                materia.save()

            return respuesta_ok(request, retorno, 'Materia creada')

        # En bloque: se crean de golpe las asignaturas marcadas. El queryset ya
        # descarta las de otra malla y las que ya tienen materia, asi que lo que
        # llegue de mas simplemente no entra.
        elegidas = request.POST.getlist('asignaturas')
        disponibles = malla_periodo.asignaturas_disponibles().filter(pk__in=elegidas)
        creadas = []
        for asignatura_malla in disponibles:
            materia = MateriaPeriodo.objects.filter(
                malla_periodo=malla_periodo,
                materia_malla=asignatura_malla,
            ).first()

            if materia:
                materia.activo = True
                materia.save(update_fields=['activo', 'fecha_modificacion'])
            else:
                materia = MateriaPeriodo.objects.create(
                    malla_periodo=malla_periodo,
                    materia_malla=asignatura_malla,
                    usuario_creacion=request.user,
                )

            creadas.append(materia)
        if not creadas:
            return respuesta_error(
                request, retorno,
                'No se creo ninguna materia: marca al menos una asignatura pendiente.',
            )
        return respuesta_ok(request, retorno, f'Se crearon {len(creadas)} materias')

    if action == 'delete_materia_periodo':
        _exigir_administrativo(request.user)
        materia = get_object_or_404(
            MateriaPeriodo.objects.select_related('malla_periodo'),
            pk=request.POST.get('pk'),
            malla_periodo__periodo=periodo_de_sesion(request), activo=True,
        )
        materia.activo = False
        materia.save(update_fields=['activo', 'fecha_modificacion'])
        return respuesta_ok(
            request, _url_apertura(materia.malla_periodo_id), 'Materia quitada del periodo',
        )

    if action == 'edit_malla_periodo':
        _exigir_administrativo(request.user)
        enlace = get_object_or_404(
            MallaPeriodo,
            pk=request.POST.get('pk'),
            periodo=periodo_de_sesion(request),
            activo=True,
        )
        nombre = (request.POST.get('nombre') or '').strip()

        if not nombre:
            return respuesta_error(
                request,
                _url_apertura(enlace.pk),
                'El nombre de la apertura es obligatorio.',
            )

        repetida = MallaPeriodo.objects.filter(
            periodo=enlace.periodo,
            malla=enlace.malla,
            nombre=nombre,
        ).exclude(pk=enlace.pk).exists()

        if repetida:
            return respuesta_error(
                request,
                _url_apertura(enlace.pk),
                'Ya existe otra apertura con esa malla y ese nombre.',
            )

        enlace.nombre = nombre
        enlace.save(update_fields=[
            'nombre',
            'fecha_modificacion',
        ])
        return respuesta_ok(
            request,
            _url_apertura(enlace.pk),
            'Nombre actualizado',
        )

    if action == 'delete_malla_periodo':
        _exigir_administrativo(request.user)
        enlace = get_object_or_404(
            MallaPeriodo, pk=request.POST.get('pk'),
            periodo=periodo_de_sesion(request), activo=True,
        )
        enlace.activo = False
        enlace.save(update_fields=['activo', 'fecha_modificacion'])
        return respuesta_ok(
            request, listado, 'Malla quitada del periodo',
        )

    if action == 'edit':
        _exigir_administrativo(request.user)
        materia = get_object_or_404(Materia, pk=request.POST.get('pk'))
        form = MateriaForm(request.POST, instance=materia)
        if form.is_valid():
            form.save()
            return respuesta_ok(request, listado)
        return respuesta_error(request, listado, errores_formulario(form), {'errors': form.errors})

    if action == 'delete':
        _exigir_administrativo(request.user)
        materia = get_object_or_404(Materia, pk=request.POST.get('pk'))
        materia.activo = False
        materia.save(update_fields=['activo', 'fecha_modificacion'])
        return respuesta_ok(request, listado, 'Materia eliminada')

    if action in ('add_tema', 'edit_tema'):
        if action == 'add_tema':
            materia_malla = _get_materia_malla(request.user, request.POST.get('materia_malla'))
            tema = TemaMateria(materia_malla=materia_malla)
        else:
            tema = get_object_or_404(
                TemaMateria.objects.select_related('materia_malla'),
                pk=request.POST.get('pk'), activo=True,
            )
            materia_malla = _get_materia_malla(request.user, tema.materia_malla_id)
        retorno = _url_materia(materia_malla.pk)
        form = TemaMateriaForm(request.POST, instance=tema)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.materia_malla = materia_malla
            if not obj.pk:
                obj.usuario_creacion = request.user
            obj.save()
            return respuesta_ok(request, retorno, 'Tema guardado')
        return respuesta_error(request, retorno, errores_formulario(form), {'errors': form.errors})

    if action == 'delete_tema':
        tema = get_object_or_404(
            TemaMateria.objects.select_related('materia_malla'),
            pk=request.POST.get('pk'), activo=True,
        )
        materia_malla = _get_materia_malla(request.user, tema.materia_malla_id)
        retorno = _url_materia(materia_malla.pk)
        if tema.actividades.filter(activo=True).exists() or tema.simulaciones.filter(activo=True).exists():
            return respuesta_error(
                request, retorno,
                'El tema tiene actividades. Muevelas o eliminalas antes de quitar el tema.',
            )
        tema.activo = False
        tema.save(update_fields=['activo', 'fecha_modificacion'])
        return respuesta_ok(request, retorno, 'Tema eliminado')

    if action in ('add_actividad', 'edit_actividad'):
        solo_guia_ape = bool(request.POST.get('solo_guia_ape'))
        if action == 'add_actividad':
            materia_malla = _get_materia_malla(request.user, request.POST.get('materia_malla'))
            actividad = ActividadMateria(materia_malla=materia_malla)
        else:
            actividad = get_object_or_404(
                ActividadMateria.objects.select_related('materia_malla'),
                pk=request.POST.get('pk'), activo=True,
            )
            materia_malla = _get_materia_malla(request.user, actividad.materia_malla_id)
        retorno = (
            f"{reverse('adm_mallas')}?action=estructura&pk={materia_malla.malla_id}"
            if request.POST.get('retorno_malla')
            else _url_materia(materia_malla.pk)
        )
        form = ActividadMateriaForm(
            request.POST, request.FILES, instance=actividad, materia_malla=materia_malla,
            solo_guia_ape=solo_guia_ape,
        )
        if form.is_valid():
            obj = form.save(commit=False)
            obj.materia_malla = materia_malla
            if not obj.pk:
                obj.usuario_creacion = request.user
            obj.save()
            return respuesta_ok(request, retorno, 'Actividad guardada')
        return respuesta_error(request, retorno, errores_formulario(form), {'errors': form.errors})

    if action == 'delete_actividad':
        actividad = get_object_or_404(
            ActividadMateria.objects.select_related('materia_malla'),
            pk=request.POST.get('pk'), activo=True,
        )
        materia_malla = _get_materia_malla(request.user, actividad.materia_malla_id)
        actividad.activo = False
        actividad.save(update_fields=['activo', 'fecha_modificacion'])
        return respuesta_ok(request, _url_materia(materia_malla.pk), 'Actividad eliminada')

    return respuesta_error(request, listado, 'Accion no valida')


def _get(request):
    action = request.GET.get('action')

    if action in ('add', 'edit', 'delete'):
        _exigir_administrativo(request.user)
        if action == 'add':
            malla = None
            nivel = None
            if request.GET.get('malla'):
                malla = get_object_or_404(Malla, pk=request.GET.get('malla'), activo=True)
            if request.GET.get('nivel'):
                nivel = get_object_or_404(
                    NivelMalla, pk=request.GET.get('nivel'), malla=malla, activo=True,
                )
            return render(request, 'academico/adm_materias/add.html', {
                'form': MateriaForm(), 'malla': malla, 'nivel': nivel,
                'niveles': (
                    NivelMalla.objects.filter(malla=malla, activo=True)
                    if malla and nivel is None else None
                ),
            })
        materia = get_object_or_404(Materia, pk=request.GET.get('pk'))
        if action == 'edit':
            return render(request, 'academico/adm_materias/edit.html', {
                'form': MateriaForm(instance=materia), 'object': materia,
            })
        return render(request, 'academico/adm_materias/delete.html', {'object': materia})

    if action == 'add_materia_periodo':
        _exigir_administrativo(request.user)
        periodo = periodo_de_sesion(request)

        malla_periodo = get_object_or_404(
            MallaPeriodo.objects.select_related(
                'malla',
                'malla__carrera',
                'periodo',
            ),
            pk=request.GET.get('malla_periodo'),
            periodo=periodo,
            activo=True,
        )

        nivel = None
        nivel_id = request.GET.get('nivel')
        if nivel_id:
            nivel = get_object_or_404(
                NivelMalla,
                pk=nivel_id,
                malla=malla_periodo.malla,
                activo=True,
            )

        form = MateriaPeriodoForm(
            malla_periodo=malla_periodo,
            nivel=nivel,
        )

        return render(
            request,
            'academico/adm_materias/materia_periodo_form.html',
            {
                'form': form,
                'malla_periodo': malla_periodo,
                'nivel': nivel,
            },
        )

    if action == 'malla':
        # Escalon 2 del recorrido: las aperturas de esta malla en el periodo.
        # Una misma malla puede abrirse varias veces (matutina, vespertina...).
        periodo = periodo_de_sesion(request)
        malla = get_object_or_404(
            Malla.objects.select_related('carrera'),
            pk=request.GET.get('pk'),
            activo=True,
        )
        permitidas = _materias_permitidas(request.user).filter(malla=malla)
        if not es_administrativo(request.user) and not permitidas.exists():
            raise PermissionDenied('No tienes materias asignadas en esta malla.')

        aperturas = []
        if periodo is not None:
            aperturas = list(
                MallaPeriodo.objects.filter(
                    malla=malla, periodo=periodo, activo=True,
                ).annotate(
                    total_materias=Count(
                        'materias', filter=Q(materias__activo=True), distinct=True,
                    ),
                ).order_by('nombre', 'pk')
            )

        return render(request, 'academico/adm_materias/malla.html', {
            'title': malla.nombre,
            'malla': malla,
            'periodo': periodo,
            'aperturas': aperturas,
            'total_asignaturas': permitidas.count(),
            'puede_editar': es_administrativo(request.user),
        })

    if action == 'apertura':
        # Escalon 3: las materias creadas dentro de UNA apertura concreta.
        periodo = periodo_de_sesion(request)
        malla_periodo = get_object_or_404(
            MallaPeriodo.objects.select_related('malla', 'malla__carrera', 'periodo'),
            pk=request.GET.get('pk'),
            periodo=periodo,
            activo=True,
        )
        malla = malla_periodo.malla
        permitidas = _materias_permitidas(request.user).filter(malla=malla)

        if not es_administrativo(request.user) and not permitidas.exists():
            raise PermissionDenied('No tienes materias asignadas en esta malla.')

        niveles, total_materias, pendientes = _estructura_malla(
            malla,
            malla_periodo,
            permitidas,
        )

        return render(request, 'academico/adm_materias/apertura.html', {
            'title': malla_periodo.nombre_visible,
            'malla': malla,
            'periodo': periodo,
            'malla_periodo': malla_periodo,
            'niveles': niveles,
            'total_materias': total_materias,
            'pendientes': pendientes,
            'puede_editar': es_administrativo(request.user),
        })

    if action in ('add_malla_periodo', 'edit_malla_periodo'):
        _exigir_administrativo(request.user)
        periodo = periodo_de_sesion(request)
        if action == 'edit_malla_periodo':
            enlace = get_object_or_404(
                MallaPeriodo.objects.select_related('malla', 'periodo'),
                pk=request.GET.get('pk'), periodo=periodo, activo=True,
            )
            malla = enlace.malla
        else:
            enlace = None
            malla = get_object_or_404(Malla, pk=request.GET.get('malla'), activo=True)
        return render(request, 'academico/adm_materias/malla_periodo_form.html', {
            'malla_periodo': enlace, 'malla': malla, 'periodo': periodo,
        })

    if action == 'detalle':
        materia_malla = _get_materia_malla(request.user, request.GET.get('pk'))
        generales, temas = _contenido_materia(materia_malla)
        periodo = periodo_de_sesion(request)
        malla_periodo = None
        if request.GET.get('malla_periodo'):
            malla_periodo = get_object_or_404(
                MallaPeriodo,
                pk=request.GET.get('malla_periodo'),
                periodo=periodo,
                malla=materia_malla.malla,
                activo=True,
            )
        return render(request, 'academico/adm_materias/detalle.html', {
            'title': materia_malla.materia.nombre,
            'materia_malla': materia_malla,
            'malla': materia_malla.malla,
            'nivel': materia_malla.nivel,
            'malla_periodo': malla_periodo,
            'generales': generales,
            'temas': temas,
        })

    if action in ('add_tema', 'edit_tema'):
        if action == 'add_tema':
            materia_malla = _get_materia_malla(request.user, request.GET.get('materia_malla'))
            tema = None
            form = TemaMateriaForm()
        else:
            tema = get_object_or_404(
                TemaMateria.objects.select_related('materia_malla'),
                pk=request.GET.get('pk'), activo=True,
            )
            materia_malla = _get_materia_malla(request.user, tema.materia_malla_id)
            form = TemaMateriaForm(instance=tema)
        return render(request, 'academico/adm_materias/tema_form.html', {
            'form': form, 'materia_malla': materia_malla, 'tema': tema,
        })

    if action in ('add_actividad', 'edit_actividad'):
        solo_guia_ape = request.GET.get('solo_guia_ape') == '1'
        retorno_malla = request.GET.get('retorno_malla') == '1'
        if action == 'add_actividad':
            materia_malla = _get_materia_malla(request.user, request.GET.get('materia_malla'))
            tema = None
            if request.GET.get('tema'):
                tema = get_object_or_404(
                    TemaMateria, pk=request.GET.get('tema'),
                    materia_malla=materia_malla, activo=True,
                )
            actividad = None
            form = ActividadMateriaForm(
                materia_malla=materia_malla,
                tema_inicial=tema,
                categoria=request.GET.get('categoria'),
                tipo_inicial=request.GET.get('tipo'),
                solo_guia_ape=solo_guia_ape,
            )
        else:
            actividad = get_object_or_404(
                ActividadMateria.objects.select_related('materia_malla'),
                pk=request.GET.get('pk'), activo=True,
            )
            materia_malla = _get_materia_malla(request.user, actividad.materia_malla_id)
            form = ActividadMateriaForm(
                instance=actividad, materia_malla=materia_malla,
                solo_guia_ape=solo_guia_ape,
            )
        return render(request, 'academico/adm_materias/actividad_form.html', {
            'form': form, 'materia_malla': materia_malla, 'actividad': actividad,
            'solo_guia_ape': solo_guia_ape, 'retorno_malla': retorno_malla,
        })

    periodo = periodo_de_sesion(request)
    puede_editar = es_administrativo(request.user)

    return render(request, 'academico/adm_materias/view.html', {
        'title': 'Materias del periodo',
        'periodo': periodo,
        'list': _mallas_del_periodo(request.user, periodo),
        'puede_editar': puede_editar,
    })