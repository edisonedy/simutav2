import json

from django.db import migrations


def configurar_caso_dcf(apps, schema_editor):
    Simulacion = apps.get_model('simulador', 'Simulacion')
    Indicador = apps.get_model('simulador', 'IndicadorSimulacion')
    Restriccion = apps.get_model('simulador', 'RestriccionSimulacion')
    Condicion = apps.get_model('simulador', 'CondicionExitoSimulacion')
    Concepto = apps.get_model('simulador', 'ConceptoEsperadoRonda')
    Accion = apps.get_model('simulador', 'AccionSugeridaSimulacion')
    Opcion = apps.get_model('simulador', 'OpcionCasoSimulacion')
    Matriz = apps.get_model('simulador', 'MatrizEvaluacionCaso')
    Intento = apps.get_model('simulador', 'IntentoSimulacion')

    simulacion = Simulacion.objects.filter(
        titulo__icontains='Valoración de Empresas mediante Flujo de Caja Descontado',
    ).first()
    if not simulacion:
        return

    # Los intentos anteriores conservan exactamente lo que vio el estudiante.
    for intento in Intento.objects.filter(simulacion=simulacion):
        snapshot = dict(intento.configuracion_snapshot or {})
        snapshot['aviso_version'] = (
            'Este intento conserva la configuración histórica, donde las mismas '
            'opciones aparecían en todas las rondas y no producían consecuencias. '
            'Las partidas nuevas usan cálculos coherentes y decisiones por fase.'
        )
        intento.configuracion_snapshot = snapshot
        intento.save(update_fields=['configuracion_snapshot'])

    simulacion.contexto = (
        'TechValley S.A. reporta ingresos de $120 millones, margen EBITDA de 25%, '
        'depreciación de $6 millones, Capex de $8 millones, aumento de capital de '
        'trabajo de $2 millones y tasa de impuesto de 30%. Su deuda neta es $50 '
        'millones y tiene 10 millones de acciones. Para estimar el WACC se usa 60% '
        'de patrimonio y 40% de deuda: tasa libre de riesgo 3%, beta 1,70, prima de '
        'mercado 6% y costo de deuda antes de impuestos 7%. Los flujos crecerían 5% '
        'anual durante cinco años y 3% a perpetuidad. El mercado paga $15 por acción '
        'y el vendedor solicita $18.'
    )
    simulacion.situacion_inicial = (
        'La dirección necesita una valoración independiente antes de negociar. '
        'Calcula brevemente el FCFF base y el WACC con los datos del caso, y explica '
        'qué supuesto tiene mayor efecto sobre el valor. Puedes responder con las '
        'fórmulas y una o dos frases.'
    )
    simulacion.objetivo = (
        'Sustentar una valoración DCF y tomar una decisión de inversión, '
        'financiamiento e integración sin pagar por encima del valor defendible.'
    )
    simulacion.resultado_aprendizaje = (
        'Valora una empresa con FCFF y WACC, interpreta sensibilidad y defiende '
        'una negociación con consecuencias y riesgos explícitos.'
    )
    simulacion.maximo_decisiones = 3
    simulacion.nivel_dificultad = 'MEDIA'
    simulacion.peso_rubrica_decision = 40
    simulacion.parametros = {
        **(simulacion.parametros or {}),
        'caso_labels': {
            'alternativas_titulo': 'Estrategias disponibles',
            'alternativa_col': 'Estrategia',
            'valor_titulo': 'Referencia',
            'valor_col': 'Referencia',
            'fortaleza_titulo': 'Beneficio',
            'fortaleza_col': 'Beneficio',
            'riesgo_titulo': 'Costo o riesgo',
            'riesgo_col': 'Costo o riesgo',
            'matriz_titulo': 'Criterios para comparar',
            'datos_titulo': 'Información para decidir',
        },
        'rondas': [
            {
                'numero': 1,
                'titulo': 'Construir la valoración base',
                'proposito': 'Obtener una base numérica defendible antes de negociar.',
                'situacion': simulacion.situacion_inicial,
                'modo': 'escribir',
                'etiqueta_decision': 'Conclusión del diagnóstico',
                'etiqueta_justificacion': 'Cálculo breve y supuesto clave',
                'justificacion_obligatoria': True,
                'indicadores_modificables': [],
                'mostrar_datos_caso': False,
                'mostrar_resultados_alternativas': False,
                'mostrar_indicadores': True,
                'pedir_pronostico': False,
                'pedir_tradeoff': False,
                'pedir_reflexion': False,
            },
            {
                'numero': 2,
                'titulo': 'Definir la oferta',
                'proposito': 'Elegir una postura de negociación usando valoración y sensibilidad.',
                'situacion': (
                    'Con FCFF base de $12,80 millones y WACC aproximado de 9,88%, '
                    'la proyección de cinco años entrega un valor independiente cercano '
                    'a $15,87 por acción. Con sinergias razonables, el techo estratégico '
                    'es $16,50. El vendedor pide $18. Elige una postura y justifícala '
                    'con un dato y un riesgo en dos o tres frases.'
                ),
                'modo': 'hibrido',
                'etiqueta_decision': 'Postura de negociación',
                'etiqueta_justificacion': 'Dato usado, consecuencia y riesgo aceptado',
                'justificacion_obligatoria': True,
                'indicadores_modificables': [
                    'margen_seguridad', 'riesgo_sobrepago', 'probabilidad_aceptacion',
                ],
                'mostrar_datos_caso': False,
                'mostrar_resultados_alternativas': False,
                'mostrar_indicadores': True,
                'pedir_pronostico': False,
                'pedir_tradeoff': False,
                'pedir_reflexion': False,
            },
            {
                'numero': 3,
                'titulo': 'Financiar e integrar',
                'proposito': 'Convertir la oferta en un plan viable de financiamiento e integración.',
                'situacion': (
                    'La contraparte está dispuesta a negociar dentro del rango defendible. '
                    'Elige una estructura de financiamiento y una estrategia de los primeros '
                    '100 días. Justifica brevemente cómo controlarías el riesgo de ejecución.'
                ),
                'modo': 'hibrido',
                'etiqueta_decision': 'Plan de financiamiento e integración',
                'etiqueta_justificacion': 'Responsable, indicador y riesgo principal',
                'justificacion_obligatoria': True,
                'indicadores_modificables': [
                    'viabilidad_financiamiento', 'preparacion_integracion', 'riesgo_ejecucion',
                ],
                'mostrar_datos_caso': False,
                'mostrar_resultados_alternativas': False,
                'mostrar_indicadores': True,
                'pedir_pronostico': False,
                'pedir_tradeoff': False,
                'pedir_reflexion': False,
            },
        ],
    }
    simulacion.version_configuracion = (simulacion.version_configuracion or 1) + 1
    simulacion.save(update_fields=[
        'contexto', 'situacion_inicial', 'objetivo', 'resultado_aprendizaje',
        'maximo_decisiones', 'nivel_dificultad', 'peso_rubrica_decision',
        'parametros', 'version_configuracion',
    ])

    indicadores = [
        # Resultados y supuestos técnicos: se muestran, pero no forman la salud.
        ('wacc', 'Costo Promedio Ponderado de Capital (WACC)', 9.88, 5, 15, 'OBJETIVO', 9.88, 0, False, '%'),
        ('flujo_libre_empresa', 'Flujo Libre de Empresa (FCFF) base', 12.80, 0, 30, 'ALTO', None, 0, False, 'millones USD'),
        ('margen_ebitda', 'Margen EBITDA', 25, 10, 40, 'ALTO', None, 0, False, '%'),
        ('tasa_crecimiento', 'Tasa de Crecimiento a Perpetuidad', 3, 0, 6, 'OBJETIVO', 3, 0, False, '%'),
        ('valor_empresa', 'Valor de Empresa (EV) estimado', 208.65, 100, 350, 'ALTO', None, 0, False, 'millones USD'),
        ('valor_accion', 'Valor intrínseco por Acción', 15.87, 5, 30, 'ALTO', None, 0, False, 'USD'),
        # Consecuencias de las decisiones: estos sí construyen la salud del caso.
        ('margen_seguridad', 'Margen de seguridad de la oferta', 0, -30, 30, 'ALTO', None, 20, True, '%'),
        ('riesgo_sobrepago', 'Riesgo de sobrepago', 50, 0, 100, 'BAJO', None, 20, True, '%'),
        ('probabilidad_aceptacion', 'Probabilidad de aceptación', 50, 0, 100, 'ALTO', None, 15, False, '%'),
        ('viabilidad_financiamiento', 'Viabilidad del financiamiento', 50, 0, 100, 'ALTO', None, 15, True, '%'),
        ('preparacion_integracion', 'Preparación para la integración', 50, 0, 100, 'ALTO', None, 15, True, '%'),
        ('riesgo_ejecucion', 'Riesgo de ejecución', 50, 0, 100, 'BAJO', None, 15, True, '%'),
    ]
    codigos = []
    for codigo, nombre, inicial, minimo, maximo, direccion, objetivo, peso, critico, unidad in indicadores:
        codigos.append(codigo)
        Indicador.objects.update_or_create(
            simulacion=simulacion,
            codigo=codigo,
            defaults={
                'nombre': nombre,
                'valor_inicial': inicial,
                'valor_minimo': minimo,
                'valor_maximo': maximo,
                'direccion_optima': direccion,
                'valor_objetivo': objetivo,
                'peso_salud': peso,
                'es_critico': critico,
                'unidad': unidad,
                'activo': True,
            },
        )
    Indicador.objects.filter(simulacion=simulacion).exclude(codigo__in=codigos).update(activo=False)

    Restriccion.objects.filter(simulacion=simulacion).delete()
    for descripcion, codigo, operador, limite in [
        ('El crecimiento perpetuo no debe superar 4%.', 'tasa_crecimiento', '<=', 4),
        ('El WACC usado debe permanecer en un rango defendible de hasta 12%.', 'wacc', '<=', 12),
        ('La valoración independiente debe superar $14 por acción.', 'valor_accion', '>=', 14),
    ]:
        Restriccion.objects.create(
            simulacion=simulacion, descripcion=descripcion, codigo_indicador=codigo,
            operador=operador, valor_limite=limite, penalizacion=5, activo=True,
        )

    Condicion.objects.filter(simulacion=simulacion).delete()
    for descripcion, codigo, operador, objetivo in [
        ('Mantener el riesgo de sobrepago en 35% o menos.', 'riesgo_sobrepago', '<=', 35),
        ('Conservar una probabilidad de aceptación de al menos 60%.', 'probabilidad_aceptacion', '>=', 60),
        ('Cerrar con financiamiento viable de al menos 65%.', 'viabilidad_financiamiento', '>=', 65),
        ('Llegar a la integración con preparación de al menos 65%.', 'preparacion_integracion', '>=', 65),
    ]:
        Condicion.objects.create(
            simulacion=simulacion, descripcion=descripcion, codigo_indicador=codigo,
            operador=operador, valor_objetivo=objetivo, bonificacion=0, activo=True,
        )

    Concepto.objects.filter(simulacion=simulacion).delete()
    conceptos = {
        1: [
            ('Cálculo del FCFF base', 40, True, ['ebit', 'impuesto', 'depreciacion', 'capex', 'capital de trabajo', '12,8']),
            ('Estimación del WACC', 40, True, ['costo de deuda', 'costo de patrimonio', 'beta', 'estructura de capital', '9,88']),
            ('Interpretación de supuestos', 20, False, ['wacc', 'crecimiento perpetuo', 'sensibilidad', 'valor terminal']),
        ],
        2: [
            ('Valoración y valor terminal', 35, True, ['flujo', 'valor terminal', 'valor empresa', 'deuda neta', 'valor por accion']),
            ('Análisis de sensibilidad', 30, True, ['sensibilidad', 'wacc', 'crecimiento', 'escenario', 'rango']),
            ('Recomendación de inversión', 35, True, ['oferta', 'precio maximo', 'margen de seguridad', 'sobrepago', 'negociacion']),
        ],
        3: [
            ('Estrategia de negociación', 35, True, ['precio', 'techo', 'condicion', 'oferta', 'negociacion']),
            ('Estructura de financiamiento', 35, True, ['deuda', 'patrimonio', 'equity', 'apalancamiento', 'wacc']),
            ('Plan de integración y control', 30, True, ['100 dias', 'responsable', 'sinergia', 'indicador', 'seguimiento']),
        ],
    }
    for ronda, items in conceptos.items():
        for nombre, peso, critico, palabras in items:
            regla = {'any': palabras}
            Concepto.objects.create(
                simulacion=simulacion, numero_ronda=ronda, nombre=nombre,
                descripcion=(
                    'Evalúa si la respuesta demuestra la idea con datos del caso; '
                    'no exige palabras exactas ni una redacción extensa.'
                ),
                palabras_clave=json.dumps(palabras, ensure_ascii=False),
                regla_evaluacion=regla, peso=peso, impacto_si_cumple={},
                impacto_si_falta={}, es_critico=critico, activo=True,
            )

    Accion.objects.filter(simulacion=simulacion).delete()
    Opcion.objects.filter(simulacion=simulacion).delete()
    Matriz.objects.filter(simulacion=simulacion).delete()

    alternativas = [
        (2, 'Ofertar $15,50 con techo de $16,50', 'Equilibra margen de seguridad y posibilidad de cierre.', '$15,50–$16,50',
         'Usa el DCF y reserva parte de las sinergias para el comprador.',
         'Puede perderse la operación si el vendedor mantiene $18.',
         {'margen_seguridad': 15, 'riesgo_sobrepago': -20, 'probabilidad_aceptacion': 15}),
        (2, 'Presentar una oferta conservadora de $14,50', 'Prioriza no pagar de más.', '$14,50',
         'Aumenta el margen de seguridad y reduce el riesgo de sobrepago.',
         'Reduce fuertemente la probabilidad de aceptación.',
         {'margen_seguridad': 25, 'riesgo_sobrepago': -30, 'probabilidad_aceptacion': -30}),
        (2, 'Aceptar los $18 solicitados', 'Prioriza cerrar la adquisición.', '$18,00',
         'Eleva mucho la posibilidad de aceptación inmediata.',
         'Supera el valor estratégico defendible y consume las sinergias.',
         {'margen_seguridad': -25, 'riesgo_sobrepago': 35, 'probabilidad_aceptacion': 40}),
        (2, 'Pausar y pedir una revisión independiente', 'Reduce incertidumbre antes de ofertar.', '2 semanas',
         'Reduce el riesgo de valorar con supuestos incompletos.',
         'Retrasa la negociación y puede perder exclusividad.',
         {'margen_seguridad': 10, 'riesgo_sobrepago': -15, 'probabilidad_aceptacion': -10}),
        (3, 'Usar 60% patrimonio, 40% deuda y plan de 100 días', 'Estructura equilibrada con responsables y métricas.', '60/40',
         'Protege la capacidad de pago y acelera la captura de sinergias.',
         'Diluye a accionistas y exige disciplina de ejecución.',
         {'viabilidad_financiamiento': 20, 'preparacion_integracion': 25, 'riesgo_ejecucion': -20}),
        (3, 'Financiar 75% con deuda y aplicar recortes rápidos', 'Preserva caja del comprador.', '75% deuda',
         'Reduce el aporte inicial de patrimonio.',
         'Aumenta apalancamiento, presión de caja y riesgo cultural.',
         {'viabilidad_financiamiento': -15, 'preparacion_integracion': 10, 'riesgo_ejecucion': 20}),
        (3, 'Pagar 100% con patrimonio e integrar gradualmente', 'Minimiza presión de deuda.', '100% patrimonio',
         'Mantiene flexibilidad financiera y reduce riesgo de liquidez.',
         'Produce dilución y captura más lenta de sinergias.',
         {'viabilidad_financiamiento': 15, 'preparacion_integracion': 10, 'riesgo_ejecucion': -5}),
    ]
    for orden, (ronda, nombre, subtitulo, referencia, fortaleza, riesgo, impacto) in enumerate(alternativas, 1):
        opcion = Opcion.objects.create(
            simulacion=simulacion, nombre=nombre, subtitulo=subtitulo,
            valor_referencia=referencia, fortaleza=fortaleza, riesgo=riesgo,
            resultados=[], orden=orden, activo=True,
        )
        Accion.objects.create(
            simulacion=simulacion, opcion_caso=opcion, numero_ronda=ronda,
            texto=nombre, descripcion=subtitulo, impacto_base=impacto,
            costo_recursos={}, activo=True,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('simulador', '0038_visibilidad_datos_talento_por_ronda'),
    ]

    operations = [
        migrations.RunPython(configurar_caso_dcf, migrations.RunPython.noop),
    ]
