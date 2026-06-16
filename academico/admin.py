from django.contrib import admin

from .models import (
    Carrera,
    InscripcionMalla,
    Malla,
    Materia,
    MateriaMalla,
    NivelMalla,
    PeriodoAcademico,
    ProfesorMateria,
)


admin.site.register(Carrera)
admin.site.register(Malla)
admin.site.register(NivelMalla)
admin.site.register(Materia)
admin.site.register(MateriaMalla)
admin.site.register(PeriodoAcademico)
admin.site.register(InscripcionMalla)
admin.site.register(ProfesorMateria)
