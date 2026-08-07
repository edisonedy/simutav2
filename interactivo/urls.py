from django.urls import path

from . import views

app_name = 'interactivo'

urlpatterns = [
    path('motores/', views.catalogo_motores, name='catalogo'),
    path('materia/<int:materia_malla_id>/', views.lista_actividades, name='lista'),
    path('materia/<int:materia_malla_id>/crear/', views.crear_actividad, name='crear'),
    path('actividad/<int:actividad_id>/editar/', views.editar_actividad, name='editar'),
    path('actividad/<int:actividad_id>/jugar/', views.jugar_actividad, name='jugar'),
    path('actividad/<int:actividad_id>/estadisticas/', views.estadisticas_actividad, name='estadisticas'),
    path('intento/<int:intento_id>/finalizar/', views.finalizar_intento, name='finalizar'),
    path('intento/<int:intento_id>/evento/', views.registrar_evento, name='evento'),
    path('intento/<int:intento_id>/resultado/', views.resultado_intento, name='resultado'),
    path('api/motores/<str:codigo>/schema/', views.schema_motor, name='schema_motor'),
]
