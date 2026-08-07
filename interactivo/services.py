def actividades_pendientes(simulacion, estudiante):
    """Juegos obligatorios amarrados a este caso que el estudiante aun no aprueba."""
    pendientes = []
    actividades = simulacion.actividades_interactivas.filter(
        publicada=True,
        obligatoria=True,
    ).order_by('orden', 'pk')
    for actividad in actividades:
        if not actividad.aprobada_por(estudiante):
            pendientes.append(actividad)
    return pendientes


def puede_iniciar_simulacion(simulacion, estudiante):
    return not actividades_pendientes(simulacion, estudiante)
