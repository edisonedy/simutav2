from core.funciones import periodo_de_sesion
from core.permisos import es_administrativo, es_docente


def permisos(request):
    """Expone los permisos al menu, para no mostrar enlaces que van a dar 403."""
    usuario = getattr(request, 'user', None)
    return {
        'puede_administrar': es_administrativo(usuario),
        'puede_ensenar': es_docente(usuario),
    }


def periodo_barra(request):
    """El selector de periodo de la barra superior. Solo lo ve quien trabaja por
    periodo (administracion y docencia); al estudiante no le sirve de nada."""
    from academico.models import PeriodoAcademico

    usuario = getattr(request, 'user', None)
    if not (es_administrativo(usuario) or es_docente(usuario)):
        return {}
    return {
        'periodos_barra': PeriodoAcademico.objects.filter(activo=True),
        'periodo_barra': periodo_de_sesion(request),
    }
