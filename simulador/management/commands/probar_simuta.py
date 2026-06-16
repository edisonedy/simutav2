import json
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from simulador.models import Simulacion, ConceptoEsperadoRonda
from simulador.services import evaluar_conceptos_esperados


RESPUESTAS_MALAS = [
    {
        'nombre': 'Respuesta muy corta',
        'decision': 'Si',
        'justificacion': 'Porque si',
    },
    {
        'nombre': 'Respuesta sin justificacion tecnica',
        'decision': 'Cambiar el sistema',
        'justificacion': 'Por experiencia me parece bien',
    },
    {
        'nombre': 'Respuesta generica sin conceptos',
        'decision': 'Hay que revisar los datos',
        'justificacion': 'Porque es necesario mejorar los procesos de la empresa',
    },
]

RESPUESTAS_MEDIAS = [
    {
        'nombre': 'Respuesta basica con algunos conceptos',
        'decision': 'Diagnosticar el problema principal de la empresa usando indicadores',
        'justificacion': (
            'Porque permite identificar las causas raiz del problema '
            'y priorizar las acciones correctivas necesarias para mejorar los resultados'
        ),
    },
    {
        'nombre': 'Respuesta con alternativas pero sin detalle',
        'decision': 'Comparar dos alternativas y seleccionar la mas viable con mejor impacto',
        'justificacion': (
            'Porque analizando las ventajas y desventajas de cada opcion '
            'se puede tomar una decision informada que reduzca los riesgos'
        ),
    },
    {
        'nombre': 'Respuesta con plan basico',
        'decision': 'Implementar un plan con actividades, responsables y un cronograma basico',
        'justificacion': (
            'Porque permite organizar el trabajo y dar seguimiento a los resultados '
            'con indicadores de control para medir el avance'
        ),
    },
]

RESPUESTAS_BUENAS = [
    {
        'nombre': 'Respuesta completa con analisis detallado',
        'decision': (
            'Diagnosticar el problema principal analizando datos, causas y tendencias '
            'para identificar los indicadores criticos que requieren atencion inmediata'
        ),
        'justificacion': (
            'Porque un analisis sistematico del problema permite identificar las causas raiz '
            'usando indicadores cuantitativos y datos de la situacion actual, lo que garantiza '
            'una decision fundamentada en evidencia concreta. Ademas aplicar los conceptos tecnicos '
            'de la materia asegura un analisis profesional y evita soluciones basadas en suposiciones.'
        ),
    },
    {
        'nombre': 'Respuesta completa con alternativas y riesgos',
        'decision': (
            'Comparar tres alternativas viables evaluando ventajas, desventajas, riesgos '
            'e impacto de cada una, y recomendar la opcion con mejor relacion costo-beneficio'
        ),
        'justificacion': (
            'Porque seleccionar la mejor alternativa requiere analizar opciones, '
            'comparar resultados esperados y mitigar los riesgos identificados mediante controles '
            'y seguimiento. La decision final se justifica por el impacto positivo en los indicadores '
            'y la viabilidad de implementacion con los recursos disponibles.'
        ),
    },
    {
        'nombre': 'Respuesta completa con plan y control',
        'decision': (
            'Implementar un plan detallado con actividades, responsables, cronograma semanal, '
            'indicadores KPI, controles de seguimiento y acciones correctivas para garantizar resultados'
        ),
        'justificacion': (
            'Porque un plan estructurado con responsables, tiempos y metas medibles permite '
            'controlar el avance mediante indicadores de gestion. Ademas incorporar mecanismos '
            'de correccion y mejora continua asegura que los resultados se mantengan en el tiempo '
            'y se puedan ajustar las acciones segun el desempeno observado en cada fase.'
        ),
    },
]


class Command(BaseCommand):
    help = 'Prueba la evaluacion de una simulacion con respuestas mala, media y buena.'

    def add_arguments(self, parser):
        parser.add_argument('--simulacion', type=int, required=True,
                            help='ID de la simulacion a probar')
        parser.add_argument('--ronda', type=int, default=1,
                            help='Numero de ronda a probar (default: 1)')

    def handle(self, *args, **options):
        simulacion_id = options['simulacion']
        ronda = options['ronda']

        try:
            simulacion = Simulacion.objects.get(pk=simulacion_id, activo=True)
        except Simulacion.DoesNotExist:
            raise CommandError(f'Simulacion con ID {simulacion_id} no encontrada o inactiva.')

        conceptos = ConceptoEsperadoRonda.objects.filter(
            simulacion=simulacion, numero_ronda=ronda, activo=True,
        )
        if not conceptos.exists():
            raise CommandError(
                f'La simulacion "{simulacion.titulo}" no tiene conceptos configurados '
                f'para la ronda {ronda}.'
            )

        self.stdout.write(f'Simulacion: {simulacion.titulo}')
        self.stdout.write(f'Materia: {simulacion.materia_malla.materia.nombre}')
        self.stdout.write(f'Ronda: {ronda}')
        self.stdout.write(f'Conceptos disponibles: {conceptos.count()}')
        peso_total = sum(c.peso for c in conceptos)
        self.stdout.write(f'Peso total de conceptos: {peso_total}')
        self.stdout.write('')
        self.stdout.write('=' * 60)
        self.stdout.write('')

        resultados = {}

        for categoria, respuestas, rango_min, rango_max in [
            ('MALA', RESPUESTAS_MALAS, 0, 40),
            ('MEDIA', RESPUESTAS_MEDIAS, 45, 75),
            ('BUENA', RESPUESTAS_BUENAS, 80, 100),
        ]:
            self.stdout.write(f'--- RESPUESTAS {categoria} (esperado: {rango_min}-{rango_max}) ---')
            for respuesta in respuestas:
                resultado = evaluar_conceptos_esperados(
                    simulacion,
                    ronda,
                    respuesta['decision'],
                    respuesta['justificacion'],
                    situacion_actual=simulacion.situacion_inicial or '',
                )
                puntaje = resultado['puntaje_sugerido']
                cumple_rango = rango_min <= puntaje <= rango_max
                estado = 'OK' if cumple_rango else 'FUERA DE RANGO'

                resultados.setdefault(categoria, []).append({
                    'nombre': respuesta['nombre'],
                    'puntaje': puntaje,
                    'cumplidos': resultado['conceptos_cumplidos'],
                    'faltantes': resultado['conceptos_faltantes'],
                    'criticos_faltantes': resultado['conceptos_criticos_faltantes'],
                    'detalle': [
                        {
                            'nombre': d['nombre'],
                            'cumple': d['cumple'],
                            'factor': d['factor_coincidencia'],
                            'puntos': d['puntos_obtenidos'],
                            'max': d['puntos_maximos'],
                            'detectadas': d['palabras_detectadas'],
                        }
                        for d in resultado['detalle_conceptos']
                    ],
                    'en_rango': cumple_rango,
                })

                self.stdout.write(f'  [{estado}] {respuesta["nombre"]}: {puntaje}')
                if cumple_rango:
                    self.stdout.write(self.style.SUCCESS(f'    Puntaje: {puntaje} (rango {rango_min}-{rango_max})'))
                else:
                    self.stdout.write(self.style.ERROR(f'    Puntaje: {puntaje} (rango esperado: {rango_min}-{rango_max})'))
                self.stdout.write(f'    Cumplidos: {resultado["conceptos_cumplidos"]}')
                self.stdout.write(f'    Faltantes: {resultado["conceptos_faltantes"]}')
                if resultado['conceptos_criticos_faltantes']:
                    self.stdout.write(self.style.WARNING(
                        f'    Criticos faltantes: {resultado["conceptos_criticos_faltantes"]}'
                    ))
                # Show detail per concept
                for d in resultado['detalle_conceptos']:
                    estado_concepto = 'Cumple' if d['cumple'] else (
                        f'Parcial({d["factor_coincidencia"]})' if d['factor_coincidencia'] > 0 else 'Falta'
                    )
                    self.stdout.write(
                        f'    - {d["nombre"]}: {estado_concepto} '
                        f'({d["puntos_obtenidos"]}/{d["puntos_maximos"]}) '
                        f'[{", ".join(d["palabras_detectadas"]) or "-"}]'
                    )
                self.stdout.write('')

        self.stdout.write('=' * 60)
        self.stdout.write('RESUMEN FINAL')
        self.stdout.write('=' * 60)

        todos_ok = True
        for categoria, rango_min, rango_max in [('MALA', 0, 40), ('MEDIA', 45, 75), ('BUENA', 80, 100)]:
            items = resultados.get(categoria, [])
            puntajes = [r['puntaje'] for r in items]
            en_rango = all(r['en_rango'] for r in items)
            if not en_rango:
                todos_ok = False
            self.stdout.write(
                f'{categoria}: min={min(puntajes):.2f} max={max(puntajes):.2f} '
                f'promedio={sum(puntajes)/len(puntajes):.2f} '
                f'rango_esperado={rango_min}-{rango_max} '
                f'{"OK" if en_rango else "REVISAR"}'
            )

        # Check for overly generous rubric
        for r in resultados.get('MEDIA', []):
            if r['puntaje'] == 100:
                self.stdout.write(self.style.WARNING(
                    f'ADVERTENCIA: Respuesta media "{r["nombre"]}" obtuvo 100. '
                    f'La rubrica puede ser muy generosa.'
                ))
        for r in resultados.get('BUENA', []):
            if r['puntaje'] == 0:
                self.stdout.write(self.style.ERROR(
                    f'ADVERTENCIA: Respuesta buena "{r["nombre"]}" obtuvo 0. '
                    f'La deteccion de conceptos puede estar fallando.'
                ))

        if todos_ok:
            self.stdout.write(self.style.SUCCESS(
                '\nTodas las respuestas estan en los rangos esperados. La rubrica esta calibrada correctamente.'
            ))
        else:
            self.stdout.write(self.style.WARNING(
                '\nAlgunas respuestas no estan en los rangos esperados. Revise la rubrica.'
            ))
