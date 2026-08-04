import json

from django.db import migrations


def configurar_caso_estrategia(apps, schema_editor):
    Simulacion = apps.get_model('simulador', 'Simulacion')
    Indicador = apps.get_model('simulador', 'IndicadorSimulacion')
    Recurso = apps.get_model('simulador', 'RecursoSimulacion')
    Restriccion = apps.get_model('simulador', 'RestriccionSimulacion')
    Condicion = apps.get_model('simulador', 'CondicionExitoSimulacion')
    Concepto = apps.get_model('simulador', 'ConceptoEsperadoRonda')
    Accion = apps.get_model('simulador', 'AccionSugeridaSimulacion')
    Intento = apps.get_model('simulador', 'IntentoSimulacion')

    simulacion = Simulacion.objects.filter(
        titulo__icontains='Estrategia de diversificación y entrada a nuevos mercados',
    ).first()
    if not simulacion:
        return

    for intento in Intento.objects.filter(simulacion=simulacion):
        snapshot = dict(intento.configuracion_snapshot or {})
        snapshot['aviso_version'] = (
            'Este intento conserva la configuración histórica, donde se repetían '
            'las mismas alternativas y no existían consecuencias numéricas. Las '
            'partidas nuevas usan decisiones e impactos específicos por fase.'
        )
        intento.configuracion_snapshot = snapshot
        intento.save(update_fields=['configuracion_snapshot'])

    simulacion.objetivo = (
        'Evaluar la entrada a IA en salud, escoger un modo de entrada y ejecutar '
        'un plan coherente con esa estrategia, equilibrando crecimiento y riesgo.'
    )
    simulacion.resultado_aprendizaje = (
        'Aplica VRIO, Cinco Fuerzas y análisis financiero para tomar y ejecutar '
        'una decisión estratégica con beneficios, riesgos y controles medibles.'
    )
    simulacion.instrucciones_ia = (
        'Evalúa significados, no palabras exactas. Reconoce evidencia parcial: por '
        'ejemplo, mencionar rivalidad sin analizar las demás fuerzas es parcial, no '
        'ausente. La alternativa elegida no sustituye la explicación del estudiante.'
    )
    simulacion.guia_debriefing = (
        'Describe únicamente cambios respaldados por estado antes/después e impacto '
        'neto. No atribuyas deuda, sinergias o riesgos que el motor no haya ejecutado.'
    )
    parametros = dict(simulacion.parametros or {})
    parametros['rondas'] = [
        {
            'numero': 1,
            'titulo': 'Diagnóstico estratégico',
            'proposito': 'Interpretar atractivo externo y preparación interna antes de elegir una entrada.',
            'situacion': (
                'Diagnostica la oportunidad de IA en salud con los datos del caso. '
                'Selecciona la conclusión que mejor represente el balance entre '
                'atractivo del mercado, recursos VRIO, competencia y capacidad financiera.'
            ),
            'modo': 'hibrido',
            'etiqueta_decision': 'Conclusión del diagnóstico',
            'etiqueta_justificacion': 'Dato del caso y aspecto todavía incierto',
            'justificacion_obligatoria': True,
            'minimo_justificacion': 25,
            'bloquear_contradiccion': True,
            'indicadores_modificables': [
                'calidad_informacion', 'preparacion_organizacional', 'riesgo_error_decision',
            ],
            'mostrar_datos_caso': False,
            'mostrar_resultados_alternativas': False,
            'mostrar_indicadores': True,
            'mostrar_recursos': True,
            'pedir_pronostico': False,
            'pedir_tradeoff': False,
            'pedir_reflexion': False,
        },
        {
            'numero': 2,
            'titulo': 'Estrategia de entrada',
            'proposito': 'Elegir un modo de entrada defendible y aceptar su principal sacrificio.',
            'situacion': (
                'Con el diagnóstico disponible, decide cómo entrar al mercado de IA '
                'en salud o si conviene esperar. Compara inversión, velocidad, control, '
                'sinergias y riesgo financiero. Justifica con un dato y una consecuencia.'
            ),
            'modo': 'hibrido',
            'etiqueta_decision': 'Modo de entrada',
            'etiqueta_justificacion': 'Evidencia, consecuencia y riesgo aceptado',
            'justificacion_obligatoria': True,
            'minimo_justificacion': 30,
            'bloquear_contradiccion': True,
            'indicadores_modificables': [
                'apalancamiento_financiero', 'capacidad_innovacion',
                'posicion_competitiva', 'riesgo_mercado', 'sinergia_operativa',
            ],
            'mostrar_datos_caso': False,
            'mostrar_resultados_alternativas': False,
            'mostrar_indicadores': True,
            'mostrar_recursos': True,
            'pedir_pronostico': False,
            'pedir_tradeoff': False,
            'pedir_reflexion': False,
        },
        {
            'numero': 3,
            'titulo': 'Implementación condicionada',
            'proposito': 'Ejecutar un plan compatible con la estrategia elegida y controlar sus riesgos.',
            'situacion': (
                'Elige un plan de implementación compatible con la estrategia tomada '
                'en la ronda anterior. Define responsable, horizonte, indicador de '
                'seguimiento y contingencia en una explicación breve.'
            ),
            'modo': 'hibrido',
            'etiqueta_decision': 'Plan compatible con la estrategia',
            'etiqueta_justificacion': 'Responsable, indicador y contingencia',
            'justificacion_obligatoria': True,
            'minimo_justificacion': 30,
            'bloquear_contradiccion': True,
            'indicadores_modificables': [
                'apalancamiento_financiero', 'capacidad_innovacion',
                'posicion_competitiva', 'riesgo_mercado', 'sinergia_operativa',
            ],
            'mostrar_datos_caso': False,
            'mostrar_resultados_alternativas': False,
            'mostrar_indicadores': True,
            'mostrar_recursos': True,
            'pedir_pronostico': False,
            'pedir_tradeoff': False,
            'pedir_reflexion': False,
        },
    ]
    simulacion.parametros = parametros
    simulacion.version_configuracion = (simulacion.version_configuracion or 1) + 1
    simulacion.peso_rubrica_decision = 40
    simulacion.save(update_fields=[
        'objetivo', 'resultado_aprendizaje', 'instrucciones_ia', 'guia_debriefing',
        'parametros', 'version_configuracion', 'peso_rubrica_decision',
    ])

    indicadores = [
        ('apalancamiento_financiero', 'Apalancamiento financiero', 40, 'BAJO', 20, True),
        ('capacidad_innovacion', 'Capacidad de innovación', 60, 'ALTO', 20, True),
        ('posicion_competitiva', 'Posición competitiva en salud', 10, 'ALTO', 25, True),
        ('riesgo_mercado', 'Riesgo de mercado', 70, 'BAJO', 20, True),
        ('sinergia_operativa', 'Sinergia operativa', 30, 'ALTO', 15, True),
        ('calidad_informacion', 'Calidad de la información estratégica', 40, 'ALTO', 0, False),
        ('preparacion_organizacional', 'Preparación organizacional diagnosticada', 40, 'ALTO', 0, False),
        ('riesgo_error_decision', 'Riesgo de decidir con información insuficiente', 60, 'BAJO', 0, False),
    ]
    codigos = []
    for codigo, nombre, inicial, direccion, peso, critico in indicadores:
        codigos.append(codigo)
        Indicador.objects.update_or_create(
            simulacion=simulacion, codigo=codigo,
            defaults={
                'nombre': nombre, 'valor_inicial': inicial, 'valor_minimo': 0,
                'valor_maximo': 100, 'direccion_optima': direccion,
                'valor_objetivo': None, 'peso_salud': peso,
                'es_critico': critico, 'unidad': 'puntos', 'activo': True,
            },
        )
    Indicador.objects.filter(simulacion=simulacion).exclude(codigo__in=codigos).update(activo=False)

    Recurso.objects.update_or_create(
        simulacion=simulacion, codigo='presupuesto_estrategico',
        defaults={
            'nombre': 'Presupuesto estratégico disponible', 'valor_inicial': 35,
            'valor_minimo': 0, 'valor_maximo': 35, 'unidad': 'millones USD',
            'es_critico': True, 'activo': True,
        },
    )

    Restriccion.objects.filter(simulacion=simulacion).delete()
    for descripcion, codigo, operador, limite in [
        ('El apalancamiento no debe superar 70 puntos.', 'apalancamiento_financiero', '<=', 70),
        ('La capacidad de innovación no debe caer por debajo de 40 puntos.', 'capacidad_innovacion', '>=', 40),
        ('El riesgo de mercado no debe superar 80 puntos.', 'riesgo_mercado', '<=', 80),
    ]:
        Restriccion.objects.create(
            simulacion=simulacion, descripcion=descripcion, codigo_indicador=codigo,
            operador=operador, valor_limite=limite, penalizacion=5, activo=True,
        )

    Condicion.objects.filter(simulacion=simulacion).delete()
    for descripcion, codigo, operador, objetivo in [
        ('Alcanzar una posición competitiva en salud de al menos 40.', 'posicion_competitiva', '>=', 40),
        ('Construir sinergia operativa de al menos 55.', 'sinergia_operativa', '>=', 55),
        ('Reducir el riesgo de mercado a 65 o menos.', 'riesgo_mercado', '<=', 65),
        ('Mantener el apalancamiento en 70 o menos.', 'apalancamiento_financiero', '<=', 70),
        ('Conservar capacidad de innovación de al menos 50.', 'capacidad_innovacion', '>=', 50),
    ]:
        Condicion.objects.create(
            simulacion=simulacion, descripcion=descripcion, codigo_indicador=codigo,
            operador=operador, valor_objetivo=objetivo, bonificacion=0, activo=True,
        )

    Concepto.objects.filter(simulacion=simulacion).delete()
    conceptos = {
        1: [
            ('Análisis VRIO de recursos', 30, True,
             ['valor', 'rareza', 'imitabilidad', 'organizacion', 'i+d', 'ingenieros']),
            ('Análisis de las Cinco Fuerzas', 30, True,
             ['rivalidad', 'clientes', 'proveedores', 'entrantes', 'sustitutos', 'barreras']),
            ('Competencias distintivas', 20, False,
             ['erp', 'i+d', 'capacidad', 'experiencia', 'diferenciacion']),
            ('Capacidad financiera', 20, False,
             ['deuda neta', 'ebitda', 'flujo', 'inversion', 'endeudamiento']),
        ],
        2: [
            ('Comparación de modos de entrada', 35, True,
             ['organico', 'alianza', 'adquisicion', 'control', 'velocidad']),
            ('Sinergias potenciales', 25, False,
             ['sinergia', 'complementariedad', 'integracion', 'cultura']),
            ('Riesgo financiero', 25, True,
             ['apalancamiento', 'deuda', 'retorno', 'presupuesto', 'costo']),
            ('Alineación estratégica', 15, False,
             ['mision', 'vision', 'objetivo', 'stakeholder', 'largo plazo']),
        ],
        3: [
            ('Plan, responsables y cronograma', 30, True,
             ['hito', 'mes', 'responsable', 'entregable', 'kpi']),
            ('Gestión del cambio', 25, False,
             ['comunicacion', 'capacitacion', 'liderazgo', 'cultura', 'equipo']),
            ('Control financiero y presupuesto', 25, True,
             ['presupuesto', 'flujo', 'costo', 'roi', 'financiamiento']),
            ('Riesgos y contingencias', 20, False,
             ['riesgo', 'contingencia', 'escenario', 'mitigacion', 'alerta']),
        ],
    }
    for ronda, items in conceptos.items():
        for nombre, peso, critico, palabras in items:
            regla = {'any': palabras}
            Concepto.objects.create(
                simulacion=simulacion, numero_ronda=ronda, nombre=nombre,
                descripcion=(
                    'Reconoce nivel completo, parcial o ausente según los componentes '
                    'realmente analizados; no exige escribir el nombre formal del modelo.'
                ),
                palabras_clave=json.dumps(palabras, ensure_ascii=False),
                regla_evaluacion=regla, peso=peso, impacto_si_cumple={},
                impacto_si_falta={}, es_critico=critico, activo=True,
            )

    Accion.objects.filter(simulacion=simulacion).delete()

    def crear(ronda, texto, descripcion, impacto, costo=0, requiere=None):
        return Accion.objects.create(
            simulacion=simulacion, numero_ronda=ronda, texto=texto,
            descripcion=descripcion, impacto_base=impacto,
            costo_recursos={'presupuesto_estrategico': costo} if costo else {},
            requiere_accion_previa=requiere, activo=True,
        )

    # Ronda 1: conclusiones del diagnóstico; solo cambia la calidad de la decisión.
    crear(1, 'Mercado atractivo, pero la empresa todavía no está preparada',
          'Reconoce la oportunidad y las brechas sectoriales antes de invertir.',
          {'calidad_informacion': 30, 'preparacion_organizacional': 10, 'riesgo_error_decision': -25})
    crear(1, 'Mercado atractivo y capacidades internas suficientes',
          'Prioriza velocidad, pero puede sobreestimar la transferibilidad del ERP a salud.',
          {'calidad_informacion': 15, 'preparacion_organizacional': 25, 'riesgo_error_decision': -5})
    crear(1, 'Mercado demasiado riesgoso para TecnoSoluciones',
          'Reduce exposición, pero puede descartar una oportunidad sin explorar socios.',
          {'calidad_informacion': 15, 'preparacion_organizacional': 5, 'riesgo_error_decision': -10})
    crear(1, 'Investigar regulación, clientes y socios antes de decidir',
          'Reduce incertidumbre, a costa de demorar la entrada.',
          {'calidad_informacion': 35, 'riesgo_error_decision': -30})

    # Ronda 2: modos de entrada con consecuencias de negocio reproducibles.
    organico = crear(2, 'Desarrollo orgánico con inversión de $10M y contratación especializada',
                     'Conserva control y construye capacidad propia, pero tarda más.',
                     {'apalancamiento_financiero': 5, 'capacidad_innovacion': -15,
                      'posicion_competitiva': 12, 'riesgo_mercado': 8, 'sinergia_operativa': 10}, 10)
    alianza = crear(2, 'Alianza estratégica con startup de salud digital por $5M',
                    'Comparte control e ingresos, pero reduce riesgo y acelera aprendizaje.',
                    {'apalancamiento_financiero': 8, 'capacidad_innovacion': -5,
                     'posicion_competitiva': 22, 'riesgo_mercado': -10, 'sinergia_operativa': 25}, 5)
    adquisicion = crear(2, 'Adquisición de empresa de IA en salud por $25M financiada con deuda',
                        'Acelera la entrada y el control, con alto riesgo financiero e integración.',
                        {'apalancamiento_financiero': 25, 'capacidad_innovacion': -10,
                         'posicion_competitiva': 38, 'riesgo_mercado': 15, 'sinergia_operativa': 18}, 25)
    esperar = crear(2, 'No ingresar todavía y mantener el foco en ERP',
                    'Protege recursos actuales, pero posterga posición y aprendizaje en salud.',
                    {'capacidad_innovacion': 5, 'posicion_competitiva': -5,
                     'riesgo_mercado': -12})

    # Ronda 3: solo se muestran planes compatibles con la elección anterior.
    crear(3, 'Desarrollo por etapas con dos pilotos y contratación gradual',
          'Valida demanda antes de escalar el producto propio.',
          {'apalancamiento_financiero': 5, 'capacidad_innovacion': 15,
           'posicion_competitiva': 18, 'riesgo_mercado': -15, 'sinergia_operativa': 15}, 8, organico)
    crear(3, 'Lanzamiento nacional inmediato con equipo interno',
          'Gana velocidad, pero eleva exposición y presión sobre I+D.',
          {'apalancamiento_financiero': 10, 'capacidad_innovacion': 5,
           'posicion_competitiva': 28, 'riesgo_mercado': 15, 'sinergia_operativa': 8}, 12, organico)
    crear(3, 'Piloto de seis meses con una clínica asociada',
          'Aprende con riesgo limitado y reglas de salida claras.',
          {'apalancamiento_financiero': 3, 'capacidad_innovacion': 5,
           'posicion_competitiva': 12, 'riesgo_mercado': -6, 'sinergia_operativa': 10}, 5, alianza)
    crear(3, 'Lanzamiento regional conjunto con la startup',
          'Acelera cobertura, con mayor dependencia del socio.',
          {'apalancamiento_financiero': 5, 'posicion_competitiva': 20,
           'riesgo_mercado': 8, 'sinergia_operativa': 15}, 8, alianza)
    crear(3, 'Integración gradual con equipo separado y hitos de 100 días',
          'Protege talento adquirido y controla sinergias y deuda por etapas.',
          {'apalancamiento_financiero': 5, 'capacidad_innovacion': 2,
           'posicion_competitiva': 8, 'riesgo_mercado': -20, 'sinergia_operativa': 15}, 7, adquisicion)
    crear(3, 'Integración total y lanzamiento nacional inmediato',
          'Busca capturar mercado rápidamente, con alta presión financiera y cultural.',
          {'apalancamiento_financiero': 15, 'capacidad_innovacion': -10,
           'posicion_competitiva': 20, 'riesgo_mercado': 15, 'sinergia_operativa': 5}, 10, adquisicion)
    crear(3, 'Realizar estudio regulatorio y mantener una puerta de entrada futura',
          'Reduce incertidumbre sin comprometer una inversión grande.',
          {'capacidad_innovacion': 10, 'posicion_competitiva': 5,
           'riesgo_mercado': -10, 'sinergia_operativa': 5}, 2, esperar)
    crear(3, 'Reforzar ERP y abandonar temporalmente la diversificación',
          'Fortalece el negocio principal, pero no crea posición en salud.',
          {'apalancamiento_financiero': -5, 'capacidad_innovacion': 15,
           'riesgo_mercado': -5}, 3, esperar)


class Migration(migrations.Migration):

    dependencies = [
        ('simulador', '0042_accion_requiere_accion_previa'),
    ]

    operations = [
        migrations.RunPython(configurar_caso_estrategia, migrations.RunPython.noop),
    ]
