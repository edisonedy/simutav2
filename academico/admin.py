from django.contrib import admin

from .models import (
    Carrera,
    InscripcionMalla,
    Malla,
    MallaPeriodo,
    Materia,
    MateriaMalla,
    MateriaMallaPredecesora,
    Modalidad,
    NivelMalla,
    PeriodoAcademico,
    ProfesorMateria,
    RecordAcademico,
)


admin.site.register(Modalidad)
admin.site.register(Carrera)
admin.site.register(Malla)
admin.site.register(MallaPeriodo)
admin.site.register(NivelMalla)
admin.site.register(Materia)
admin.site.register(MateriaMalla)
admin.site.register(MateriaMallaPredecesora)
admin.site.register(PeriodoAcademico)
admin.site.register(InscripcionMalla)
admin.site.register(ProfesorMateria)
admin.site.register(RecordAcademico)
