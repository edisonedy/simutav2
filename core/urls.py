from django.urls import path

from . import views

app_name = 'core'

urlpatterns = [
    path('cambiar-periodo/', views.cambiar_periodo, name='cambiar_periodo'),
    path('estado-ia/', views.estado_ia, name='estado_ia'),
]
