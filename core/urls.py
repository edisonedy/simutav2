from django.urls import path

from core import views

app_name = 'core'

urlpatterns = [
    path('', views.instituciones, name='home'),
    path('instituciones/', views.instituciones, name='instituciones'),
    path('instituciones/add/', views.institucion_add, name='institucion_add'),
    path('instituciones/<int:pk>/edit/', views.institucion_edit, name='institucion_edit'),
]
