import json

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from academico.models import (
    Carrera,
    InscripcionMalla,
    Malla,
    Materia,
    MateriaMalla,
    NivelMalla,
    PeriodoAcademico,
    ProfesorMateria,
)
from core.models import Institucion, PerfilUsuario
from simulador.models import (
    ConceptoEsperadoRonda,
    CondicionExitoSimulacion,
    CriterioEvaluacion,
    IndicadorSimulacion,
    RestriccionSimulacion,
    Simulacion,
)


class Command(BaseCommand):
    help = 'Carga la simulacion financiera de Distribuidora Andina S.A.S.'

    def handle(self, *args, **options):
        usuario = User.objects.filter(username='emoyolema').first()
        if usuario is None:
            usuario = User.objects.filter(is_superuser=True).first()
        if usuario is None:
            usuario = User.objects.create_user(
                username='emoyolema',
                password='demo12345',
                first_name='Edison',
            )

        institucion, _ = Institucion.objects.get_or_create(
            nombre='Universidad Tecnica de Ambato',
            defaults={'siglas': 'UTA', 'direccion': 'Ambato, Ecuador', 'usuario_creacion': usuario},
        )
        PerfilUsuario.objects.update_or_create(
            usuario=usuario,
            defaults={
                'rol': PerfilUsuario.ADMIN,
                'institucion': institucion,
                'usuario_creacion': usuario,
            },
        )
        carrera, _ = Carrera.objects.get_or_create(
            institucion=institucion,
            codigo='ADM-DEMO',
            defaults={
                'nombre': 'Administracion de Empresas',
                'titulo_otorga': 'Licenciado/a en Administracion',
                'modalidad': 'Presencial',
                'duracion_periodos': 8,
                'usuario_creacion': usuario,
            },
        )
        malla, _ = Malla.objects.get_or_create(
            carrera=carrera,
            codigo='ADM-UTA-2026',
            defaults={'nombre': 'Malla Administracion UTA 2026', 'vigente': True, 'usuario_creacion': usuario},
        )
        nivel, _ = NivelMalla.objects.get_or_create(
            malla=malla,
            numero=3,
            defaults={'nombre': '3 Periodo', 'usuario_creacion': usuario},
        )
        materia, _ = Materia.objects.get_or_create(
            institucion=institucion,
            codigo='N3M1_ADMINISTRACION_FINANCI',
            defaults={
                'nombre': 'Administracion Financiera',
                'descripcion': 'Liquidez, financiamiento, costos, rentabilidad y riesgo.',
                'creditos': 4,
                'horas': 64,
                'usuario_creacion': usuario,
            },
        )
        materia_malla, _ = MateriaMalla.objects.get_or_create(
            malla=malla,
            materia=materia,
            defaults={'nivel': nivel, 'orden': 1, 'obligatoria': True, 'usuario_creacion': usuario},
        )
        periodo, _ = PeriodoAcademico.objects.get_or_create(
            institucion=institucion,
            nombre='Demo 2026',
            defaults={
                'fecha_inicio': timezone.datetime(2026, 1, 1).date(),
                'fecha_fin': timezone.datetime(2026, 12, 31).date(),
                'activo_matricula': True,
                'usuario_creacion': usuario,
            },
        )
        ProfesorMateria.objects.get_or_create(
            profesor=usuario,
            materia_malla=materia_malla,
            periodo=periodo,
            defaults={'usuario_creacion': usuario},
        )
        InscripcionMalla.objects.get_or_create(
            estudiante=usuario,
            malla=malla,
            periodo=periodo,
            defaults={'usuario_creacion': usuario},
        )

        rondas = [
            {
                'situacion': (
                    'La empresa Distribuidora Andina S.A.S. enfrenta presion simultanea sobre liquidez '
                    'y rentabilidad. Estado actual: caja $8.000, costos operativos 72%, riesgo financiero '
                    '65/100, liquidez corriente 1.1, rentabilidad 12%. Las ventas a credito aumentaron '
                    'pero los cobros se retrasan y los costos logisticos subieron por rutas urgentes. '
                    'Que harias primero como analista financiero junior? Diagnostica el problema principal, '
                    'propone medidas concretas para mejorar liquidez y costos, y justifica con indicadores.'
                )
            },
            {
                'situacion': (
                    'Tus medidas iniciales redujeron el riesgo pero la caja bajo a $100, casi en cero. '
                    'Estado actual: caja $100, costos 72%, riesgo 55/100, liquidez 1.1, rentabilidad 12%. '
                    'La empresa tiene facturas por cobrar por $15.000, dos proveedores esperan pago esta semana '
                    'y el banco ofrece una linea de credito rotativa al 14% anual. Como consigues liquidez urgente? '
                    'Compara alternativas de financiamiento, propone negociacion con proveedores y justifica prioridades.'
                )
            },
            {
                'situacion': (
                    'La caja llego a $0. La empresa no puede pagar nomina ni proveedores esta semana. '
                    'Estado actual: caja $0, costos 72%, riesgo 45/100, liquidez 1.1, rentabilidad 12%. '
                    'El banco puede aprobar $5.000 en 48 horas con garantia de facturas; puedes cobrar $3.000 '
                    'a un cliente con 5% de descuento; puedes suspender gastos no esenciales por $1.200; '
                    'puedes pedir 30 dias adicionales a proveedores. Cual es tu plan? Prioriza, justifica '
                    'impacto en caja y explica como evitas repetir la crisis.'
                )
            },
        ]

        instrucciones = (
            'Eres evaluador academico de finanzas para la Universidad Tecnica de Ambato. '
            'Evalua respuestas contra la rubrica configurada por ronda. No premies respuestas vagas. '
            'La nota la calcula SimutaV2 con conceptos, pesos, impactos, restricciones y topes criticos. '
            'Direcciones: caja, liquidez y rentabilidad mayor es mejor; costos y riesgo menor es mejor.'
        )

        simulacion, _ = Simulacion.objects.update_or_create(
            materia_malla=materia_malla,
            titulo='Decisiones financieras para estabilizar y expandir una empresa de distribucion',
            defaults={
                'profesor': usuario,
                'tipo_simulacion': Simulacion.TIPO_CON_IA_DINAMICA,
                'tema': 'Analisis financiero, liquidez, costos, riesgo y rentabilidad',
                'nivel_dificultad': Simulacion.DIFICULTAD_MEDIA,
                'maximo_decisiones': 3,
                'tiempo_estimado': 30,
                'rol_estudiante': 'Analista financiero junior',
                'contexto': (
                    'La empresa Distribuidora Andina S.A.S., dedicada a la comercializacion de insumos '
                    'de oficina y limpieza para clientes empresariales, enfrenta presion simultanea sobre '
                    'liquidez y rentabilidad. Aumentaron las ventas a credito, retrasos de cobro, costos '
                    'logisticos por rutas urgentes y dependencia de financiamiento de corto plazo.'
                ),
                'objetivo': (
                    'Interpretar indicadores financieros, comparar alternativas de financiamiento y control '
                    'de costos, y justificar decisiones que mejoren la liquidez, reduzcan riesgo y sostengan rentabilidad.'
                ),
                'resultado_aprendizaje': (
                    'El estudiante interpreta estados financieros basicos, identifica problemas de liquidez y rentabilidad, '
                    'propone financiamiento y control de costos, y justifica el impacto en indicadores.'
                ),
                'situacion_inicial': rondas[0]['situacion'],
                'instrucciones_ia': instrucciones,
                'parametros': {'rondas': rondas},
                'estado': Simulacion.PUBLICADA,
                'fecha_publicacion': timezone.now(),
                'activo': True,
                'usuario_creacion': usuario,
            },
        )

        simulacion.indicadores.update(activo=False)
        simulacion.restricciones.update(activo=False)
        simulacion.condiciones_exito.update(activo=False)
        simulacion.criterios.update(activo=False)
        simulacion.conceptos_esperados.update(activo=False)

        indicadores = [
            ('Caja disponible', 'caja', 8000.0, 0.0, 20000.0, 'ALTO', True, 'USD'),
            ('Nivel de costos operativos', 'costos', 72.0, 0.0, 100.0, 'BAJO', False, '%'),
            ('Riesgo financiero', 'riesgo', 65.0, 0.0, 100.0, 'BAJO', True, 'pts'),
            ('Liquidez corriente', 'liquidez', 1.1, 0.0, 5.0, 'ALTO', True, 'ratio'),
            ('Rentabilidad operativa', 'rentabilidad', 12.0, 0.0, 100.0, 'ALTO', False, '%'),
        ]
        for nombre, codigo, inicial, minimo, maximo, direccion, critico, unidad in indicadores:
            IndicadorSimulacion.objects.update_or_create(
                simulacion=simulacion,
                codigo=codigo,
                defaults={
                    'nombre': nombre,
                    'valor_inicial': inicial,
                    'valor_minimo': minimo,
                    'valor_maximo': maximo,
                    'direccion_optima': direccion,
                    'es_critico': critico,
                    'unidad': unidad,
                    'activo': True,
                    'usuario_creacion': usuario,
                },
            )

        restricciones = [
            ('La caja no debe llegar a cero - riesgo de insolvencia inmediata', 'caja', '>', 500.0, 20.0),
            ('La liquidez no debe bajar de 1.0 - minimo para cubrir obligaciones', 'liquidez', '>=', 1.0, 15.0),
            ('El riesgo no debe superar 80 - zona de crisis financiera', 'riesgo', '<=', 80.0, 15.0),
            ('Los costos no deben superar el 85% - perdida operativa', 'costos', '<=', 85.0, 10.0),
        ]
        for descripcion, codigo, operador, limite, penalizacion in restricciones:
            RestriccionSimulacion.objects.update_or_create(
                simulacion=simulacion,
                descripcion=descripcion,
                defaults={
                    'codigo_indicador': codigo,
                    'operador': operador,
                    'valor_limite': limite,
                    'penalizacion': penalizacion,
                    'activo': True,
                    'usuario_creacion': usuario,
                },
            )

        condiciones = [
            ('Recuperar caja por encima de $3.000', 'caja', '>=', 3000.0, 10.0),
            ('Reducir costos por debajo del 65%', 'costos', '<=', 65.0, 5.0),
            ('Bajar el riesgo por debajo de 40', 'riesgo', '<=', 40.0, 5.0),
        ]
        for descripcion, codigo, operador, objetivo, bonificacion in condiciones:
            CondicionExitoSimulacion.objects.update_or_create(
                simulacion=simulacion,
                descripcion=descripcion,
                defaults={
                    'codigo_indicador': codigo,
                    'operador': operador,
                    'valor_objetivo': objetivo,
                    'bonificacion': bonificacion,
                    'activo': True,
                    'usuario_creacion': usuario,
                },
            )

        conceptos = [
            (1, 'Diagnostico de liquidez', 'Identifica el problema de liquidez y su causa',
             ['liquidez', 'caja', 'flujo', 'cobro', 'cartera', 'corriente', 'ratio', 'iliquidez', 'efectivo'],
             30.0, True, {'liquidez': 0.3, 'riesgo': -8}, {'riesgo': 10},
             'Correcto: identificar la liquidez critica es el primer paso.',
             'Falto identificar que liquidez 1.1 es critica.'),
            (1, 'Control de costos', 'Propone reduccion concreta de costos operativos',
             ['costo', 'costos', 'reducir', 'logistico', 'ruta', 'proveedor', 'gasto', 'optimizar', 'eliminar', 'eficiencia'],
             25.0, False, {'costos': -8, 'rentabilidad': 4}, {},
             'Bien: reducir costos logisticos mejora el margen.',
             'Falto proponer reduccion de costos.'),
            (1, 'Gestion de cuentas por cobrar', 'Propone politica concreta de cobro',
             ['cobro', 'cobrar', 'plazo', 'cliente', 'cartera', 'vencido', 'credito', 'politica', '30 dias', 'factura'],
             25.0, False, {'caja': 1500, 'liquidez': 0.2}, {},
             'Excelente: mejorar el ciclo de cobro recupera caja.',
             'Falto proponer politica de cobro.'),
            (1, 'Justificacion con indicadores', 'Menciona indicadores concretos en la justificacion',
             ['indicador', 'caja', 'liquidez', 'riesgo', 'rentabilidad', 'costos', 'margen', 'ratio', 'prioridad', 'impacto'],
             20.0, False, {'riesgo': -5}, {},
             'Bien: justificar con indicadores demuestra analisis financiero.',
             'Falto mencionar indicadores concretos.'),
            (2, 'Alternativa de financiamiento', 'Propone fuente concreta de financiamiento',
             ['factoring', 'credito', 'linea', 'banco', 'financiamiento', 'prestamo', 'capital', 'deuda', 'rotativa', 'leasing'],
             35.0, True, {'caja': 3000, 'riesgo': -10}, {'riesgo': 15, 'caja': -500},
             'Correcto: una fuente de financiamiento recupera caja.',
             'Critico: sin financiamiento la caja seguira cayendo.'),
            (2, 'Negociacion con proveedores', 'Propone extender plazos con proveedores',
             ['proveedor', 'proveedores', 'plazo', 'pago', 'renegociar', 'extender', '45 dias', '60 dias', 'credito proveedor', 'diferir'],
             30.0, False, {'caja': 2000, 'costos': -5}, {},
             'Excelente: extender plazos libera caja sin costo financiero.',
             'Falto negociar con proveedores.'),
            (2, 'Comparacion de alternativas', 'Compara al menos dos opciones y justifica la elegida',
             ['comparar', 'alternativa', 'versus', 'vs', 'mejor que', 'ventaja', 'desventaja', 'opcion', 'elegir', 'diferencia'],
             20.0, False, {'riesgo': -5}, {},
             'Bien: comparar alternativas demuestra criterio analitico.',
             'Falto comparar alternativas.'),
            (2, 'Impacto en rentabilidad', 'Menciona como la decision afecta la rentabilidad',
             ['rentabilidad', 'margen', 'ganancia', 'utilidad', 'beneficio', 'retorno', 'rendimiento', 'roi'],
             15.0, False, {'rentabilidad': 5}, {},
             'Bien: considerar rentabilidad muestra vision integral.',
             'Falto mencionar el impacto en rentabilidad.'),
            (3, 'Plan de recuperacion de caja', 'Propone acciones concretas para recuperar caja desde 0',
             ['recuperar', 'caja', 'emergencia', 'credito', 'linea', 'banco', 'ingreso', 'cobrar', 'urgente', 'inmediato'],
             40.0, True, {'caja': 5000, 'riesgo': -10}, {'riesgo': 20},
             'Correcto: con caja en 0 la prioridad es recuperar liquidez.',
             'Critico: la caja esta en 0; falta accion inmediata.'),
            (3, 'Control de gastos de emergencia', 'Suspende o reduce gastos no esenciales',
             ['suspender', 'eliminar', 'recortar', 'gastos', 'no esencial', 'austeridad', 'reducir', 'congelar', 'priorizar'],
             25.0, False, {'costos': -10, 'caja': 1000}, {},
             'Bien: suspender gastos no esenciales es inmediato.',
             'Falto proponer suspension de gastos.'),
            (3, 'Comunicacion con proveedores', 'Menciona como manejar la relacion con proveedores',
             ['proveedor', 'proveedores', 'comunicar', 'negociar', 'incumplimiento', 'pago', 'plazo', 'acuerdo', 'mora', 'relacion'],
             20.0, False, {'riesgo': -8}, {'riesgo': 5},
             'Bien: comunicar evita dano comercial.',
             'Falto manejar la relacion con proveedores.'),
            (3, 'Plan de mediano plazo', 'Propone como evitar que la crisis se repita',
             ['mediano plazo', 'plan', 'prevenir', 'futuro', 'politica', 'control', 'proceso', 'sistema', 'repetir', 'evitar'],
             15.0, False, {'rentabilidad': 5, 'riesgo': -5}, {},
             'Excelente: pensar a mediano plazo muestra madurez.',
             'Falto proponer como evitar repetir la crisis.'),
        ]
        for ronda, nombre, descripcion, claves, peso, critico, impacto_cumple, impacto_falta, retro_ok, retro_fail in conceptos:
            ConceptoEsperadoRonda.objects.update_or_create(
                simulacion=simulacion,
                escenario=None,
                numero_ronda=ronda,
                nombre=nombre,
                defaults={
                    'descripcion': descripcion,
                    'palabras_clave': json.dumps({'any': claves}),
                    'peso': peso,
                    'impacto_si_cumple': impacto_cumple,
                    'impacto_si_falta': impacto_falta,
                    'retroalimentacion_si_cumple': retro_ok,
                    'retroalimentacion_si_falta': retro_fail,
                    'es_critico': critico,
                    'activo': True,
                    'usuario_creacion': usuario,
                },
            )

        criterios = [
            ('Diagnostico financiero', 30),
            ('Alternativas de financiamiento', 25),
            ('Control de costos', 20),
            ('Gestion de riesgo', 15),
            ('Justificacion con indicadores', 10),
        ]
        for nombre, peso in criterios:
            CriterioEvaluacion.objects.update_or_create(
                simulacion=simulacion,
                nombre=nombre,
                defaults={
                    'descripcion': f'Criterio orientativo: {nombre}.',
                    'peso': peso,
                    'activo': True,
                    'usuario_creacion': usuario,
                },
            )

        self.stdout.write(self.style.SUCCESS('Simulacion financiera cargada y publicada.'))
        self.stdout.write(f'Usuario inscrito: {usuario.username}')
        self.stdout.write(f'Simulacion: {simulacion.titulo} (ID {simulacion.id})')
