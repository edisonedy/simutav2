from django.urls import path

from seguridad import views

app_name = 'seguridad'

urlpatterns = [
    path('usuarios/', views.usuarios, name='usuarios'),
]
