import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'simutav2.settings')
django.setup()

from academico.models import MateriaMalla
from simulador.models import Simulacion

print(f'Simulaciones activas: {Simulacion.objects.filter(activo=True).count()}')
print(f'Simulaciones totales: {Simulacion.objects.count()}')
print(f'MateriaMalla activas: {MateriaMalla.objects.filter(activo=True).count()}')

for mm in MateriaMalla.objects.filter(activo=True).select_related('materia','nivel','malla__carrera').order_by('malla__carrera__nombre','nivel__numero','materia__nombre'):
    sim = Simulacion.objects.filter(materia_malla=mm, activo=True).first()
    estado = 'TIENE SIM' if sim else 'SIN SIM'
    print(f'  ID={mm.pk}: {mm.materia.nombre} / {mm.malla.carrera.nombre} N{mm.nivel.numero} - {estado}')
