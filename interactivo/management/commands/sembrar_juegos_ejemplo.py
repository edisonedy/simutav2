"""Crea un juego de ejemplo por cada motor instalado.

Sirve para ver y probar los siete tipos sin tener que escribirlos a mano. El
contenido es de Administracion (costos, contabilidad, talento humano), que es
la facultad para la que se esta armando el sistema.

    python manage.py sembrar_juegos_ejemplo
    python manage.py sembrar_juegos_ejemplo --materia 12 --reemplazar
"""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from academico.models import MateriaMalla
from interactivo.models import ActividadInteractiva
from interactivo.plugins.registry import get_plugin
from simulador.models import TemaMateria

# Contenido tal como lo escribiria un docente en el editor: el plugin lo
# normaliza despues (genera ids, separa opciones, ubica los espacios).
EJEMPLOS = [
    {
        'motor': 'seleccion_unica',
        'titulo': 'Costos fijos y variables',
        'instrucciones': 'Elige la unica respuesta correcta en cada pregunta.',
        'config': {'preguntas': [
            {
                'enunciado': 'El arriendo mensual de la planta es un costo...',
                'opciones': 'Variable\nFijo\nMarginal\nDe oportunidad',
                'correcta': 2,
                'explicacion': 'No cambia con el volumen producido: se paga igual produzcas 10 o 1000.',
            },
            {
                'enunciado': 'La materia prima que entra en cada unidad producida es un costo...',
                'opciones': 'Fijo\nHundido\nVariable\nContable',
                'correcta': 3,
                'explicacion': 'Sube y baja en proporcion directa a las unidades producidas.',
            },
            {
                'enunciado': 'El punto de equilibrio es el nivel de ventas en el que...',
                'opciones': 'La utilidad es maxima\nLa utilidad es cero\nEl costo fijo es cero\nEl margen es 100%',
                'correcta': 2,
                'explicacion': 'Los ingresos cubren exactamente los costos totales: no se gana ni se pierde.',
            },
        ]},
    },
    {
        'motor': 'seleccion_multiple',
        'titulo': 'Que entra en el costo de produccion',
        'instrucciones': 'Puede haber mas de una respuesta correcta.',
        'config': {'preguntas': [
            {
                'enunciado': 'Cuales de estos son costos indirectos de fabricacion (CIF)?',
                'opciones': 'Energia electrica de la planta\nSueldo del obrero de linea\nDepreciacion de la maquinaria\nMateria prima directa\nSupervision de planta',
                'correctas': '1,3,5',
                'explicacion': 'Los CIF son los que no se pueden rastrear directamente a una unidad.',
            },
            {
                'enunciado': 'Que documentos respaldan una compra a credito?',
                'opciones': 'Factura del proveedor\nOrden de compra\nRol de pagos\nNota de ingreso a bodega',
                'correctas': '1,2,4',
                'explicacion': 'El rol de pagos respalda la nomina, no una compra.',
            },
        ]},
    },
    {
        'motor': 'verdadero_falso',
        'titulo': 'Principios contables',
        'instrucciones': 'Decide si cada afirmacion es verdadera o falsa.',
        'config': {'preguntas': [
            {
                'enunciado': 'En la partida doble, todo debe tiene un haber por el mismo valor.',
                'correcta': True,
                'explicacion': 'Es la regla base: la ecuacion contable siempre queda cuadrada.',
            },
            {
                'enunciado': 'Un aumento del activo siempre se registra en el haber.',
                'correcta': False,
                'explicacion': 'El aumento del activo va al debe.',
            },
            {
                'enunciado': 'La depreciacion es una salida de efectivo del periodo.',
                'correcta': False,
                'explicacion': 'Es un gasto contable sin movimiento de caja.',
            },
            {
                'enunciado': 'El pasivo corriente vence dentro del ano.',
                'correcta': True,
                'explicacion': 'Por eso se separa del pasivo de largo plazo.',
            },
        ]},
    },
    {
        'motor': 'ordenar',
        'titulo': 'El ciclo contable, paso a paso',
        'instrucciones': 'Ordena los pasos del ciclo contable, del primero al ultimo.',
        'config': {'elementos': [
            {'texto': 'Registrar la transaccion en el libro diario'},
            {'texto': 'Pasar los asientos al libro mayor'},
            {'texto': 'Elaborar el balance de comprobacion'},
            {'texto': 'Hacer los asientos de ajuste'},
            {'texto': 'Preparar los estados financieros'},
            {'texto': 'Cerrar las cuentas de resultado'},
        ]},
    },
    {
        'motor': 'relacionar',
        'titulo': 'Indicador financiero y que mide',
        'instrucciones': 'Une cada indicador con lo que realmente mide.',
        'config': {'pares': [
            {'izquierda': 'Liquidez corriente', 'derecha': 'Capacidad de pagar deudas de corto plazo'},
            {'izquierda': 'Margen neto', 'derecha': 'Cuanto queda de utilidad por cada dolar vendido'},
            {'izquierda': 'Rotacion de inventario', 'derecha': 'Cuantas veces se vende y repone el stock al ano'},
            {'izquierda': 'Endeudamiento', 'derecha': 'Que parte del activo esta financiada por terceros'},
            {'izquierda': 'ROE', 'derecha': 'Rendimiento que obtienen los accionistas'},
        ]},
    },
    {
        'motor': 'memoria',
        'titulo': 'Terminos de talento humano',
        'instrucciones': 'Encuentra las parejas: cada termino con su definicion.',
        'config': {'pares': [
            {'lado_a': 'Reclutamiento', 'lado_b': 'Atraer candidatos a una vacante'},
            {'lado_a': 'Seleccion', 'lado_b': 'Elegir al candidato adecuado'},
            {'lado_a': 'Induccion', 'lado_b': 'Integrar al nuevo empleado'},
            {'lado_a': 'Rotacion', 'lado_b': 'Porcentaje de personal que sale'},
            {'lado_a': 'Clima laboral', 'lado_b': 'Percepcion del ambiente de trabajo'},
        ]},
    },
    {
        'motor': 'completar_espacios',
        'titulo': 'La ecuacion contable',
        'instrucciones': 'Completa los espacios en blanco.',
        'config': {'texto': (
            'La ecuacion contable basica dice que el [[activo]] es igual al '
            '[[pasivo]] mas el [[patrimonio]]. Cuando la empresa compra un bien '
            'a credito, aumenta su activo y tambien su [[pasivo]], asi que la '
            'ecuacion sigue [[cuadrada|balanceada|equilibrada]].'
        )},
    },
]


class Command(BaseCommand):
    help = 'Crea un juego de ejemplo por cada motor interactivo instalado.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--materia', type=int, default=None,
            help='Id de la MateriaMalla. Por defecto, la primera de Administracion.',
        )
        parser.add_argument(
            '--reemplazar', action='store_true',
            help='Borra los juegos de ejemplo anteriores de esa materia.',
        )

    def _materia(self, materia_id):
        if materia_id:
            try:
                return MateriaMalla.objects.select_related('materia', 'malla').get(
                    pk=materia_id, activo=True,
                )
            except MateriaMalla.DoesNotExist:
                raise CommandError(f'No existe la materia de malla {materia_id}.')

        materia = MateriaMalla.objects.filter(
            activo=True, malla__carrera__nombre__icontains='administra',
        ).select_related('materia', 'malla').order_by(
            'nivel__numero', 'orden',
        ).first()
        if materia is None:
            materia = MateriaMalla.objects.filter(activo=True).select_related(
                'materia', 'malla',
            ).order_by('nivel__numero', 'orden').first()
        if materia is None:
            raise CommandError('No hay ninguna materia de malla activa donde sembrar.')
        return materia

    def _creador(self, materia):
        asignado = materia.profesores.filter(activo=True).select_related('profesor').first()
        if asignado:
            return asignado.profesor
        usuario = (
            User.objects.filter(is_superuser=True, is_active=True).first()
            or User.objects.filter(is_staff=True, is_active=True).first()
            or User.objects.filter(is_active=True).first()
        )
        if usuario is None:
            raise CommandError('No hay usuarios activos para figurar como creador.')
        return usuario

    @transaction.atomic
    def handle(self, *args, **options):
        materia = self._materia(options['materia'])
        creador = self._creador(materia)
        titulos = [ejemplo['titulo'] for ejemplo in EJEMPLOS]

        if options['reemplazar']:
            borrados, _ = ActividadInteractiva.objects.filter(
                materia_malla=materia, titulo__in=titulos,
            ).delete()
            if borrados:
                self.stdout.write(f'Se borraron {borrados} juegos de ejemplo anteriores.')

        # Los ejemplos van a un tema propio para no ensuciar los del docente.
        tema, _ = TemaMateria.objects.get_or_create(
            materia_malla=materia,
            nombre='Ejemplos de juegos',
            defaults={
                'descripcion': 'Juegos de muestra, uno por cada tipo disponible.',
                'orden': 99,
                'usuario_creacion': creador,
            },
        )

        self.stdout.write(
            f'Materia: {materia.materia.nombre} ({materia.malla.nombre}) '
            f'- creador: {creador.get_username()}'
        )

        creados = 0
        saltados = 0
        for orden, ejemplo in enumerate(EJEMPLOS, start=1):
            if ActividadInteractiva.objects.filter(
                materia_malla=materia, titulo=ejemplo['titulo'],
            ).exists():
                self.stdout.write(f'  = ya existe: {ejemplo["titulo"]}')
                saltados += 1
                continue

            plugin = get_plugin(ejemplo['motor'])
            configuracion = plugin.normalize_config(ejemplo['config'])
            errores = plugin.validate_config(configuracion)
            if errores:
                raise CommandError(
                    f'El ejemplo "{ejemplo["titulo"]}" no es valido: {"; ".join(errores)}'
                )

            ActividadInteractiva.objects.create(
                materia_malla=materia,
                tema=tema,
                creador=creador,
                motor=plugin.codigo,
                motor_version=plugin.version,
                titulo=ejemplo['titulo'],
                instrucciones=ejemplo['instrucciones'],
                configuracion=configuracion,
                orden=orden,
                puntaje_minimo=70,
                obligatoria=False,
                publicada=True,
                usuario_creacion=creador,
            )
            self.stdout.write(f'  + {plugin.nombre}: {ejemplo["titulo"]}')
            creados += 1

        self.stdout.write(self.style.SUCCESS(
            f'Listo: {creados} juegos creados, {saltados} ya existian. '
            f'Se ven en /interactivo/materia/{materia.pk}/'
        ))
