from django.urls import path

import academico.adm_carreras as adm_carreras
import academico.adm_mallas as adm_mallas
import academico.adm_materias as adm_materias
import academico.adm_periodos as adm_periodos
import academico.adm_inscripciones as adm_inscripciones

urlpatterns = [
    path('adm_carreras', adm_carreras.view, name='adm_carreras'),
    path('adm_mallas', adm_mallas.view, name='adm_mallas'),
    path('adm_materias', adm_materias.view, name='adm_materias'),
    path('adm_periodos', adm_periodos.view, name='adm_periodos'),
    path('adm_inscripciones', adm_inscripciones.view, name='adm_inscripciones'),
]
