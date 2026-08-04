"""Siembra el caso piloto de seleccion de personal con informacion que se compra.

Es el ejemplo de referencia del mecanismo: cuatro candidatos que en el papel son
casi identicos, un presupuesto que NO alcanza para investigarlos a todos, y
hallazgos que solo aparecen si el estudiante paga por averiguarlos.

    python manage.py sembrar_investigaciones_talento
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from simulador.models import InvestigacionSimulacion, RecursoSimulacion, Simulacion

PRESUPUESTO = {
    'codigo': 'presupuesto_seleccion',
    'nombre': 'Presupuesto de seleccion',
    'valor_inicial': 250,
    'valor_minimo': 0,
    'valor_maximo': 250,
    'unidad': 'USD',
}

# El total de averiguaciones cuesta 620 y el presupuesto es 250: a proposito no
# alcanza. Ahi esta la decision.
INVESTIGACIONES = [
    ('Andrea', 'Entrevista por competencias', 40,
     'Responde con solvencia tecnica, pero al hablar de su salida anterior culpa a sus companeros '
     'y al jefe. No reconoce ninguna responsabilidad propia.'),
    ('Andrea', 'Verificacion de referencias', 50,
     'La referencia confirma buen nivel tecnico y menciona roces frecuentes con el equipo.'),
    ('Carlos', 'Prueba practica de Excel', 60,
     'Obtiene 60 sobre 100. En la hoja de vida declaraba nivel avanzado: exagero su dominio.'),
    ('Carlos', 'Entrevista por competencias', 40,
     'Buena actitud y disposicion a aprender. Pidio menos sueldo porque necesita el empleo pronto.'),
    ('Daniela', 'Prueba practica de Excel', 60,
     'Obtiene 92 sobre 100, el mejor resultado. Documenta su procedimiento paso a paso.'),
    ('Daniela', 'Entrevista por competencias', 40,
     'Habla con poca seguridad y le cuesta venderse, pero sus ejemplos son concretos y verificables.'),
    ('Mateo', 'Prueba psicometrica', 80,
     'Perfil de liderazgo alto y baja tolerancia a la rutina. Riesgo de rotacion elevado en un '
     'puesto sin linea de ascenso clara.'),
    ('Mateo', 'Verificacion de referencias', 50,
     'Excelente desempeno en sus dos ultimos trabajos, pero permanecio menos de un ano en cada uno.'),
    ('Todos', 'Assessment center grupal', 200,
     'En dinamica grupal: Daniela ordena el trabajo del equipo, Andrea impone su criterio, '
     'Carlos aporta poco bajo presion y Mateo lidera pero se aburre en la parte operativa.'),
]


class Command(BaseCommand):
    help = 'Siembra las averiguaciones del caso de seleccion de personal (Talento Humano).'

    def add_arguments(self, parser):
        parser.add_argument('--simulacion', type=int, help='id de la simulacion; por defecto busca la de Talento Humano')

    @transaction.atomic
    def handle(self, *args, **opciones):
        if opciones.get('simulacion'):
            simulacion = Simulacion.objects.filter(pk=opciones['simulacion']).first()
        else:
            simulacion = Simulacion.objects.filter(
                materia_malla__materia__nombre__icontains='Talento',
                estado=Simulacion.PUBLICADA, activo=True,
            ).first()
        if not simulacion:
            raise CommandError('No encontre la simulacion de Talento Humano. Pasa --simulacion <id>.')

        recurso, creado = RecursoSimulacion.objects.get_or_create(
            simulacion=simulacion, codigo=PRESUPUESTO['codigo'],
            defaults={k: v for k, v in PRESUPUESTO.items() if k != 'codigo'},
        )
        self.stdout.write(f'Presupuesto {"creado" if creado else "ya existia"}: '
                          f'{recurso.valor_inicial} {recurso.unidad}')

        nuevas = 0
        for orden, (sujeto, nombre, costo, hallazgo) in enumerate(INVESTIGACIONES, start=1):
            _, creada = InvestigacionSimulacion.objects.update_or_create(
                simulacion=simulacion, sujeto=sujeto, nombre=nombre,
                defaults={
                    'hallazgo': hallazgo,
                    'costo_recursos': {PRESUPUESTO['codigo']: costo},
                    'descripcion': f'Cuesta {costo} {recurso.unidad}.',
                    'disponible_desde_ronda': 1,
                    'orden': orden,
                    'activo': True,
                },
            )
            nuevas += 1 if creada else 0

        total = sum(c for _, _, c, _ in INVESTIGACIONES)
        self.stdout.write(self.style.SUCCESS(
            f'{len(INVESTIGACIONES)} averiguaciones listas ({nuevas} nuevas) en "{simulacion.titulo[:50]}".'))
        self.stdout.write(
            f'Cuestan {total} {recurso.unidad} en total y el presupuesto es {recurso.valor_inicial}: '
            f'el estudiante solo puede pagar una parte.')
