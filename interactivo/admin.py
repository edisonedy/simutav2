from django.contrib import admin

from .models import (
    ActividadInteractiva,
    EventoActividadInteractiva,
    IntentoActividadInteractiva,
    RecursoActividadInteractiva,
)


@admin.register(ActividadInteractiva)
class ActividadInteractivaAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'motor', 'simulacion', 'creador', 'publicada', 'orden')
    list_filter = ('motor', 'publicada', 'obligatoria')
    search_fields = ('titulo', 'simulacion__titulo', 'creador__username')


@admin.register(IntentoActividadInteractiva)
class IntentoActividadInteractivaAdmin(admin.ModelAdmin):
    list_display = ('actividad', 'estudiante', 'numero_intento', 'porcentaje', 'estado', 'fecha_inicio')
    list_filter = ('estado', 'aprobado', 'completado')
    search_fields = ('actividad__titulo', 'estudiante__username')


admin.site.register(RecursoActividadInteractiva)
admin.site.register(EventoActividadInteractiva)
