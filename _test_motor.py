import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
sys.path.insert(0, os.path.dirname(__file__))
django.setup()

from simulador.models import Simulacion
from simulador.services.motor_dinamico import *

s = Simulacion.objects.filter(activo=True).first()
print(f'Sim: {s.titulo}')

params = dict(s.parametros or {})
params['tipo_dinamica'] = 'comparacion_opciones'
params['nombre_opciones'] = 'candidatos'
params['opciones_dinamicas'] = [
    {'codigo': 'A', 'nombre': 'Candidato A', 'descripcion': 'Perfil equilibrado', 'aliases': ['candidato a', 'opcion a'], 'indicadores': {'experiencia': 3, 'prueba': 78}},
    {'codigo': 'B', 'nombre': 'Candidato B', 'descripcion': 'Perfil tecnico', 'aliases': ['candidato b', 'opcion b'], 'indicadores': {'experiencia': 5, 'prueba': 88}},
]
params['reglas_actualizacion'] = {'modo': 'copiar_indicadores_opcion', 'rondas_aplica': [2], 'confianza_minima': 0.6}
s.parametros = params
s.save(update_fields=['parametros'])
print('Opciones guardadas')

opciones = obtener_opciones_dinamicas(s)
print(f'Opciones: {len(opciones)}')

opcion, conf = detectar_opcion_por_texto(s, 'Elijo al candidato a porque tiene experiencia', 'es la mejor opcion')
print(f'Test 1 - Detectada: {opcion["codigo"] if opcion else None}, confianza: {conf}')

estado = {'experiencia': 0, 'prueba': 0}
estado_despues, impacto, opc, conf2 = aplicar_opcion_dinamica(s, estado, 'Selecciono candidato b', 'tiene mejor prueba', 2)
print(f'Test 2 - Estado despues: {estado_despues}')
print(f'Test 2 - Impacto: {impacto}')
print(f'Test 2 - Opcion: {opc["codigo"] if opc else None}')

estado3, impacto3, opc3, conf3 = aplicar_opcion_dinamica(s, estado, 'Respuesta generica sin opcion', 'sin decision clara', 2)
print(f'Test 3 (sin opcion) - Estado: {estado3}, Opcion: {opc3}')

print('\nTODO OK')
