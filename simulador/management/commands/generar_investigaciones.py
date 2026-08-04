"""Genera, para cualquier caso, la informacion oculta que el estudiante compra.

Las averiguaciones salen del propio caso, asi que son especificas de la materia:
en Produccion seran auditorias a proveedores, en Talento Humano pruebas a
candidatos, en Productos encuestas a segmentos. El docente no escribe nada.

    python manage.py generar_investigaciones --todas
    python manage.py generar_investigaciones --materia "Administracion de la Produccion"
    python manage.py generar_investigaciones --simulacion 196 --rehacer
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from simulador.ia_service import generar_investigaciones_ia
from simulador.models import (
    InvestigacionSimulacion, OpcionCasoSimulacion, RecursoSimulacion, Simulacion,
)

CODIGO_PRESUPUESTO = 'presupuesto_investigacion'
PRESUPUESTO_POR_DEFECTO = 250


class Command(BaseCommand):
    help = 'Genera con IA las averiguaciones que el estudiante puede comprar en cada caso.'

    def add_arguments(self, parser):
        parser.add_argument('--simulacion', type=int)
        parser.add_argument('--materia', type=str)
        parser.add_argument('--malla', type=str, help='codigo de malla, ej. ADM-UTA-2026')
        parser.add_argument('--todas', action='store_true')
        parser.add_argument('--limite', type=int, default=5)
        parser.add_argument('--presupuesto', type=int, default=PRESUPUESTO_POR_DEFECTO)
        parser.add_argument('--rehacer', action='store_true',
                            help='reemplaza las averiguaciones que ya tenga el caso')
        parser.add_argument('--solo-visibilidad', action='store_true', dest='solo_visibilidad',
                            help='no genera nada: solo enciende las averiguaciones que el '
                                 'estudiante no puede ver en ninguna ronda')

    def handle(self, *args, **opciones):
        if opciones.get('solo_visibilidad'):
            return self._reparar_visibilidad(opciones)
        casos = self._seleccionar(opciones)
        if not casos:
            raise CommandError('Ningun caso coincide. Usa --simulacion, --materia, --malla o --todas.')

        hechos = fallidos = saltados = 0
        for simulacion in casos:
            ya_tiene = simulacion.investigaciones.filter(activo=True).exists()
            if ya_tiene and not opciones['rehacer']:
                # Aunque se salte, se revisa la visibilidad: una averiguacion que
                # el estudiante no ve es dato muerto.
                encendidas = self._mostrar_en_las_rondas(simulacion)
                aviso = f' (se encendieron {encendidas} ronda(s))' if encendidas else ''
                self.stdout.write(f'- {simulacion.titulo[:52]}: ya tiene, se salta{aviso}')
                saltados += 1
                continue
            resultado = self._generar_para(simulacion, opciones['presupuesto'], opciones['rehacer'])
            if resultado is None:
                self.stderr.write(self.style.ERROR(f'x {simulacion.titulo[:52]}: la IA no respondio'))
                fallidos += 1
            else:
                creadas, total = resultado
                self.stdout.write(self.style.SUCCESS(
                    f'+ {simulacion.titulo[:52]}: {creadas} averiguaciones, '
                    f'cuestan {total} de {opciones["presupuesto"]} disponibles'))
                hechos += 1

        self.stdout.write(f'\nGenerados {hechos}, saltados {saltados}, fallidos {fallidos}.')
        if fallidos:
            self.stdout.write('Los fallidos suelen ser JSON malformado de la IA: vuelve a correr el comando.')

    def _seleccionar(self, opciones):
        qs = Simulacion.objects.filter(estado=Simulacion.PUBLICADA, activo=True).select_related(
            'materia_malla__materia', 'materia_malla__malla')
        if opciones.get('simulacion'):
            return list(qs.filter(pk=opciones['simulacion']))
        if opciones.get('materia'):
            return list(qs.filter(materia_malla__materia__nombre__icontains=opciones['materia']))
        if opciones.get('malla'):
            qs = qs.filter(materia_malla__malla__codigo=opciones['malla'])
        elif not opciones.get('todas'):
            return []
        # En lote, saltamos los que ya tienen para poder correr el comando varias
        # veces e ir cubriendo el resto sin repetir trabajo ni gastar API de mas.
        if not opciones['rehacer']:
            qs = qs.exclude(investigaciones__activo=True)
        return list(qs.distinct()[:opciones['limite']])

    def _alternativas(self, simulacion):
        """Sobre que se puede averiguar: las alternativas del caso si las hay,
        si no las opciones de decision configuradas."""
        opciones = list(OpcionCasoSimulacion.objects.filter(
            simulacion=simulacion, activo=True).values_list('nombre', flat=True))
        if opciones:
            return opciones
        candidatos = (simulacion.parametros or {}).get('candidatos') or []
        nombres = [c.get('nombre') for c in candidatos if isinstance(c, dict) and c.get('nombre')]
        if nombres:
            return nombres
        return list(simulacion.acciones_sugeridas.filter(activo=True).values_list('texto', flat=True)[:5])

    @staticmethod
    def _sujeto(item):
        """Sobre quien o que se averigua. Si la IA copio ahi el texto de una
        decision -pasa- lo dejamos vacio en vez de mostrar una frase cortada."""
        valor = str(item.get('sujeto') or '').strip()
        if len(valor) > 40 or valor.count(' ') > 4:
            return ''
        return valor[:120]

    def _reparar_visibilidad(self, opciones):
        """Un caso puede tener averiguaciones y que ninguna ronda las muestre:
        entonces el estudiante nunca investiga y el mecanismo no existe."""
        qs = Simulacion.objects.filter(estado=Simulacion.PUBLICADA, activo=True,
                                       investigaciones__activo=True).distinct()
        if opciones.get('malla'):
            qs = qs.filter(materia_malla__malla__codigo=opciones['malla'])
        if opciones.get('materia'):
            qs = qs.filter(materia_malla__materia__nombre__icontains=opciones['materia'])
        if opciones.get('simulacion'):
            qs = qs.filter(pk=opciones['simulacion'])

        arreglados = ya_visibles = 0
        for simulacion in qs:
            encendidas = self._mostrar_en_las_rondas(simulacion)
            if encendidas:
                arreglados += 1
                self.stdout.write(self.style.SUCCESS(
                    f'+ {simulacion.titulo[:52]}: visibles desde {encendidas} ronda(s)'))
            else:
                ya_visibles += 1
        self.stdout.write(f'\nArreglados {arreglados}, ya estaban visibles {ya_visibles}.')

    @staticmethod
    def _mostrar_en_las_rondas(simulacion):
        """Enciende la visibilidad de las averiguaciones en las rondas donde ya
        estan disponibles. El interruptor arranca apagado para no saturar la
        pantalla, pero si el caso TIENE averiguaciones y ninguna ronda las
        muestra, el estudiante nunca puede investigar y el mecanismo no existe.
        """
        disponibles = simulacion.investigaciones.filter(activo=True).values_list(
            'disponible_desde_ronda', flat=True)
        if not disponibles:
            return 0
        desde = min(disponibles)
        parametros = dict(simulacion.parametros or {})
        rondas = list(parametros.get('rondas') or [])
        while len(rondas) < simulacion.maximo_decisiones:
            rondas.append({})
        encendidas = 0
        for numero in range(desde, simulacion.maximo_decisiones + 1):
            indice = numero - 1
            if indice >= len(rondas):
                break
            ronda = rondas[indice] if isinstance(rondas[indice], dict) else {}
            if not ronda.get('mostrar_investigaciones'):
                ronda['mostrar_investigaciones'] = True
                encendidas += 1
            rondas[indice] = ronda
        if encendidas:
            parametros['rondas'] = rondas
            simulacion.parametros = parametros
            simulacion.save(update_fields=['parametros'])
        return encendidas

    @transaction.atomic
    def _generar_para(self, simulacion, presupuesto, rehacer):
        recurso, _ = RecursoSimulacion.objects.get_or_create(
            simulacion=simulacion, codigo=CODIGO_PRESUPUESTO,
            defaults={
                'nombre': 'Presupuesto para investigar', 'valor_inicial': presupuesto,
                'valor_minimo': 0, 'valor_maximo': presupuesto, 'unidad': 'USD',
            },
        )
        items = generar_investigaciones_ia(
            simulacion, self._alternativas(simulacion), CODIGO_PRESUPUESTO, presupuesto)
        if not items:
            return None

        if rehacer:
            InvestigacionSimulacion.objects.filter(simulacion=simulacion).delete()

        validos = []
        for item in items:
            nombre = str(item.get('nombre') or '').strip()
            hallazgo = str(item.get('hallazgo') or '').strip()
            try:
                costo = max(1, int(float(item.get('costo') or 0)))
            except (TypeError, ValueError):
                continue
            if nombre and hallazgo:
                validos.append((item, nombre, hallazgo, costo))
        if not validos:
            return None

        # El mecanismo solo funciona si NO alcanza para todas. No lo dejamos a
        # criterio de la IA: reescalamos los costos para que el total sea ~2.5
        # veces el presupuesto, conservando la proporcion entre averiguaciones.
        suma = sum(c for _, _, _, c in validos)
        objetivo = presupuesto * 2.5
        factor = objetivo / suma if suma else 1
        validos = [(i, n, h, max(1, round(c * factor / 5) * 5)) for i, n, h, c in validos]

        creadas = total = 0
        for orden, (item, nombre, hallazgo, costo) in enumerate(validos, start=1):
            InvestigacionSimulacion.objects.update_or_create(
                simulacion=simulacion, sujeto=self._sujeto(item),
                nombre=nombre[:200],
                defaults={
                    'descripcion': str(item.get('descripcion') or '').strip(),
                    'hallazgo': hallazgo,
                    'costo_recursos': {CODIGO_PRESUPUESTO: costo},
                    'orden': orden, 'activo': True,
                },
            )
            creadas += 1
            total += costo
        if not creadas:
            return None
        self._mostrar_en_las_rondas(simulacion)
        return creadas, total
