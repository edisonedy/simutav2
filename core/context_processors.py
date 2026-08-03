from core.permisos import es_administrativo, es_docente


def permisos(request):
    """Expone los permisos al menu, para no mostrar enlaces que van a dar 403."""
    usuario = getattr(request, 'user', None)
    return {
        'puede_administrar': es_administrativo(usuario),
        'puede_ensenar': es_docente(usuario),
    }
