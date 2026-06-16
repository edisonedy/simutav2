from django.urls import path

import simulador.adm_simulaciones as adm_simulaciones
import simulador.pro_simulaciones as pro_simulaciones
import simulador.alu_simulaciones as alu_simulaciones

urlpatterns = [
    path('adm_simulaciones', adm_simulaciones.view, name='adm_simulaciones'),
    path('pro_simulaciones', pro_simulaciones.view, name='pro_simulaciones'),
    path('alu_simulaciones', alu_simulaciones.view, name='alu_simulaciones'),
]
