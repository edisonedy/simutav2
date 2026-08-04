"""Completa con contenido real las tres materias que el docente pidio revisar.

Sin alternativas comparables no hay decision, solo redaccion: el estudiante
describe y la IA lo evalua, pero nunca ELIGE entre opciones con trade-offs. Este
comando agrega a cada caso las alternativas, la matriz de criterios, las
condiciones de exito y los eventos, con los contenidos que realmente se ensenan
en cada asignatura de Administracion de Empresas.

    python manage.py completar_casos_administracion
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from simulador.models import (
    CondicionExitoSimulacion, EventoSimulacion, MatrizEvaluacionCaso,
    OpcionCasoSimulacion, Simulacion,
)

# ---------------------------------------------------------------- CONTABILIDAD
# Decision canonica de Costeo por ordenes: sobre que base se aplican los costos
# indirectos de fabricacion. Cada base reparte el CIF distinto, asi que la misma
# orden puede salir rentable o no segun lo que elija el estudiante.
CONTABILIDAD = {
    'materia': 'Contabilidad de Costos',
    'opciones': [
        ('Horas maquina', 'Tasa predeterminada $15,00 por hora maquina', '$15,00 / HM',
         'Sigue de cerca al consumo real: el 70% del CIF es depreciacion y energia de maquinaria.',
         'Castiga a las ordenes automatizadas y subsidia a las manuales.',
         [('Correlacion con el CIF real', 88), ('Costo de implementar', 75),
          ('Precision por orden', 82), ('Facilidad de control', 80)]),
        ('Horas de mano de obra directa', 'Tasa predeterminada $9,50 por HMOD', '$9,50 / HMOD',
         'Es la base tradicional y el area de nomina ya registra las horas.',
         'La planta se automatizo: la MOD bajo al 12% del costo y distorsiona el reparto.',
         [('Correlacion con el CIF real', 45), ('Costo de implementar', 95),
          ('Precision por orden', 48), ('Facilidad de control', 90)]),
        ('Costo de materiales directos', 'Tasa del 120% sobre el material', '120% del MD',
         'Sencilla de calcular y de auditar con las facturas de compra.',
         'Una orden con material caro carga CIF que no consumio.',
         [('Correlacion con el CIF real', 38), ('Costo de implementar', 92),
          ('Precision por orden', 40), ('Facilidad de control', 85)]),
        ('Costeo ABC por actividades', 'Cuatro inductores: preparacion, inspeccion, montaje, despacho', '4 inductores',
         'Reparte segun lo que cada orden consume de verdad y revela las ordenes que dan perdida.',
         'Cuesta implementarlo y exige medir cada actividad todos los meses.',
         [('Correlacion con el CIF real', 95), ('Costo de implementar', 35),
          ('Precision por orden', 94), ('Facilidad de control', 55)]),
    ],
    'matriz': [
        ('Correlacion con el CIF real', 30, 'que tan bien la base explica el consumo real de costos indirectos'),
        ('Precision por orden', 25, 'si el costo unitario resultante sirve para fijar precio y margen'),
        ('Facilidad de control', 25, 'si el area contable puede sostener el calculo mes a mes'),
        ('Costo de implementar', 20, 'esfuerzo y sistemas que exige poner la base en marcha'),
    ],
    'exito': [
        ('Cerrar el ejercicio con la sub o sobreaplicacion controlada', 'sub_sobre_aplicacion', '<=', 5, 6),
        ('Sostener el margen de contribucion sobre el 35%', 'margen_contribucion', '>=', 35, 6),
    ],
    'eventos': [
        ('Reclamo de un cliente grande', 2,
         'Un cliente reclama: dice que sus ordenes pagan un CIF que no consumen. La gerencia '
         'pide revisar si la base de aplicacion esta subsidiando a las ordenes pequenas.',
         {'sub_sobre_aplicacion': 3.5}),
        ('Sube la tarifa electrica', 3,
         'La tarifa industrial sube 12%. El CIF real del periodo se eleva y la tasa '
         'predeterminada que fijaste queda corta.',
         {'tasa_cif': 1.8, 'eficiencia_cif': -4}),
    ],
}

# ------------------------------------------------------------------- FINANCIERA
# Conflicto clasico VAN vs TIR entre proyectos mutuamente excluyentes: el de
# mayor TIR NO es el de mayor VAN. Si el estudiante decide solo por TIR, se
# equivoca; si decide solo por VAN, ignora el riesgo y el payback.
FINANCIERA = {
    'materia': 'Administracion Financiera',
    'opciones': [
        ('Proyecto A: planta propia', 'Inversion $480.000 - VAN $92.000 - TIR 18,4% - Payback 4,2 anos', 'VAN $92.000',
         'El VAN mas alto de los tres con deuda a tasa fija y activo propio como garantia.',
         'Inmoviliza caja cuatro anos y sube el apalancamiento a 1,9 veces.',
         [('VAN', 92), ('TIR sobre el WACC', 72), ('Payback', 45), ('Riesgo y apalancamiento', 48)]),
        ('Proyecto B: tercerizar y ampliar canal', 'Inversion $180.000 - VAN $61.000 - TIR 24,7% - Payback 2,1 anos', 'TIR 24,7%',
         'La TIR mas alta y recupera la inversion en dos anos, sin comprometer la estructura.',
         'Depende de un tercero y su VAN es 34% menor: crea menos valor absoluto.',
         [('VAN', 61), ('TIR sobre el WACC', 95), ('Payback', 92), ('Riesgo y apalancamiento', 78)]),
        ('Proyecto C: adquirir un competidor', 'Inversion $650.000 - VAN $105.000 - TIR 15,2% - Payback 5,6 anos', 'VAN $105.000',
         'Crea el mayor valor absoluto y suma participacion de mercado de inmediato.',
         'Su TIR de 15,2% deja poco margen sobre el WACC y exige emitir capital.',
         [('VAN', 100), ('TIR sobre el WACC', 42), ('Payback', 28), ('Riesgo y apalancamiento', 35)]),
    ],
    'matriz': [
        ('VAN', 30, 'valor absoluto que crea el proyecto, descontado al WACC'),
        ('TIR sobre el WACC', 25, 'margen entre el rendimiento del proyecto y el costo del capital'),
        ('Riesgo y apalancamiento', 25, 'como queda la estructura de capital y la cobertura de intereses'),
        ('Payback', 20, 'en cuanto tiempo se recupera la inversion'),
    ],
    'exito': [
        ('Elegir el proyecto que mas valor crea', 'van', '>=', 90000, 6),
        ('No encarecer el costo del capital', 'wacc', '<=', 12, 6),
    ],
    'eventos': [
        ('El banco endurece las condiciones', 2,
         'El banco sube la tasa 150 puntos base y exige cobertura de intereses de 3 veces. '
         'El costo de la deuda se encarece y el WACC se mueve.',
         {'wacc': 1.5, 'apalancamiento': 0.2}),
        ('Oportunidad de capital semilla', 3,
         'Un fondo ofrece capital a cambio del 15% de la empresa. Baja el apalancamiento, '
         'pero diluye a los socios actuales.',
         {'apalancamiento': -0.4, 'wacc': -0.6}),
    ],
}

# ---------------------------------------------------------------------- TALENTO
# El caso venia de una siembra vieja y trataba de contratar desarrolladores
# Django: eso no es lo que se ensena en Administracion de Empresas. Se reemplaza
# por la vacante que si corresponde, con perfiles casi identicos en el papel.
TALENTO = {
    'materia': 'Talento Humano',
    'opciones': [
        ('Andrea Villacis', '3 anos de experiencia - Excel avanzado declarado - pretende $900', '$900',
         'La mejor preparacion tecnica del grupo y certificacion en gestion documental.',
         'En la entrevista culpa a sus companeros de su salida anterior.',
         [('Competencia tecnica', 88), ('Trabajo en equipo', 42), ('Riesgo de rotacion', 55),
          ('Ajuste al presupuesto', 70)]),
        ('Carlos Bermeo', '3 anos de experiencia - Excel avanzado declarado - pretende $850', '$850',
         'Es el mas barato y esta disponible de inmediato.',
         'En la prueba practica saca 60 sobre 100: exagero su nivel de Excel.',
         [('Competencia tecnica', 58), ('Trabajo en equipo', 75), ('Riesgo de rotacion', 60),
          ('Ajuste al presupuesto', 92)]),
        ('Daniela Freire', '3 anos de experiencia - Excel avanzado declarado - pretende $900', '$900',
         'Saca 92 sobre 100 en la prueba practica y trae referencias verificables.',
         'Se expresa con poca seguridad: en entrevista da peor impresion de la que merece.',
         [('Competencia tecnica', 92), ('Trabajo en equipo', 85), ('Riesgo de rotacion', 25),
          ('Ajuste al presupuesto', 70)]),
        ('Mateo Ludena', '3 anos de experiencia - Excel avanzado declarado - pretende $950', '$950',
         'Perfil de liderazgo y experiencia coordinando equipos pequenos.',
         'Busca crecer rapido: alto riesgo de irse de un puesto sin linea de ascenso.',
         [('Competencia tecnica', 80), ('Trabajo en equipo', 78), ('Riesgo de rotacion', 82),
          ('Ajuste al presupuesto', 45)]),
    ],
    'matriz': [
        ('Competencia tecnica', 30, 'resultado en la prueba practica, no lo declarado en la hoja de vida'),
        ('Trabajo en equipo', 25, 'como resuelve conflictos y si asume responsabilidad propia'),
        ('Riesgo de rotacion', 25, 'probabilidad de que abandone el puesto en el primer ano'),
        ('Ajuste al presupuesto', 20, 'pretension salarial frente a los $900 del cargo'),
    ],
    'exito': [
        ('Contratar con alto ajuste al perfil', 'ajuste_perfil', '>=', 85, 5),
        ('Mantener bajo el riesgo de rotacion', 'riesgo_rotacion', '<=', 25, 5),
    ],
    'eventos': [
        ('Llegadas tarde de la persona contratada', 3,
         'La persona que contrataste rinde bien, pero llega tarde tres veces por semana. '
         'El equipo lo comenta. Decidir entre conversacion informal, llamado de atencion, '
         'cambio de horario o plan de mejora.',
         {'clima_equipo': -6}),
    ],
}


class Command(BaseCommand):
    help = 'Completa Contabilidad de Costos, Talento Humano y Administracion Financiera con alternativas reales.'

    def add_arguments(self, parser):
        parser.add_argument('--solo', type=str, help='completa solo una materia (texto parcial)')

    def handle(self, *args, **opciones):
        for spec in (CONTABILIDAD, TALENTO, FINANCIERA):
            if opciones.get('solo') and opciones['solo'].lower() not in spec['materia'].lower():
                continue
            simulacion = Simulacion.objects.filter(
                materia_malla__materia__nombre__icontains=spec['materia'],
                estado=Simulacion.PUBLICADA, activo=True,
            ).first()
            if not simulacion:
                self.stderr.write(self.style.ERROR(f'No encontre el caso de {spec["materia"]}'))
                continue
            self._completar(simulacion, spec)

    @transaction.atomic
    def _completar(self, simulacion, spec):
        codigos = set(simulacion.indicadores.filter(activo=True).values_list('codigo', flat=True))

        OpcionCasoSimulacion.objects.filter(simulacion=simulacion).delete()
        for orden, (nombre, subtitulo, ref, fortaleza, riesgo, resultados) in enumerate(spec['opciones'], start=1):
            OpcionCasoSimulacion.objects.create(
                simulacion=simulacion, nombre=nombre, subtitulo=subtitulo,
                valor_referencia=ref, fortaleza=fortaleza, riesgo=riesgo,
                resultados=[{'criterio': c, 'valor': v} for c, v in resultados],
                orden=orden,
            )

        MatrizEvaluacionCaso.objects.filter(simulacion=simulacion).delete()
        for orden, (criterio, peso, evalua) in enumerate(spec['matriz'], start=1):
            MatrizEvaluacionCaso.objects.create(
                simulacion=simulacion, criterio=criterio, peso=peso, evalua=evalua, orden=orden)

        exito_ok = 0
        CondicionExitoSimulacion.objects.filter(simulacion=simulacion).delete()
        for descripcion, indicador, operador, objetivo, bonificacion in spec['exito']:
            if indicador not in codigos:
                self.stderr.write(f'   (aviso) el indicador "{indicador}" no existe en el caso, se omite')
                continue
            CondicionExitoSimulacion.objects.create(
                simulacion=simulacion, descripcion=descripcion, codigo_indicador=indicador,
                operador=operador, valor_objetivo=objetivo, bonificacion=bonificacion)
            exito_ok += 1

        eventos_ok = 0
        for nombre, ronda, mensaje, efecto in spec['eventos']:
            efecto_valido = {k: v for k, v in efecto.items() if k in codigos}
            if not efecto_valido:
                continue
            EventoSimulacion.objects.update_or_create(
                simulacion=simulacion, nombre=nombre,
                defaults={'mensaje': mensaje, 'ronda': ronda, 'efecto': efecto_valido,
                          'prioridad': 1, 'activo': True},
            )
            eventos_ok += 1

        self.stdout.write(self.style.SUCCESS(
            f'{spec["materia"]}: {len(spec["opciones"])} alternativas, {len(spec["matriz"])} criterios, '
            f'{exito_ok} condiciones de exito, {eventos_ok} eventos.'))
