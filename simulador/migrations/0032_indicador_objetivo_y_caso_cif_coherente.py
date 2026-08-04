from decimal import Decimal

from django.db import migrations, models


def corregir_caso_cif(apps, schema_editor):
    Simulacion = apps.get_model('simulador', 'Simulacion')
    simulacion = Simulacion.objects.filter(
        titulo__icontains='Industrias del Norte',
    ).first()
    if not simulacion:
        return

    indicadores = {i.codigo: i for i in simulacion.indicadores.all()}
    eficiencia = indicadores.get('eficiencia_cif')
    if eficiencia:
        eficiencia.valor_minimo = Decimal('0')
        eficiencia.valor_maximo = Decimal('1')
        eficiencia.direccion_optima = 'ALTO'
        eficiencia.valor_objetivo = None
        eficiencia.save(update_fields=[
            'valor_minimo', 'valor_maximo', 'direccion_optima', 'valor_objetivo',
        ])
    tasa = indicadores.get('tasa_cif')
    if tasa:
        tasa.direccion_optima = 'OBJETIVO'
        tasa.valor_objetivo = Decimal('15')
        tasa.save(update_fields=['direccion_optima', 'valor_objetivo'])
    desviacion = indicadores.get('sub_sobre_aplicacion')
    if desviacion:
        desviacion.direccion_optima = 'OBJETIVO'
        desviacion.valor_objetivo = Decimal('0')
        desviacion.save(update_fields=['direccion_optima', 'valor_objetivo'])

    meta_margen = simulacion.condiciones_exito.filter(
        codigo_indicador='margen_contribucion',
    ).first()
    if meta_margen:
        meta_margen.descripcion = 'Mantener el margen de contribución por orden sobre $2.000'
        meta_margen.operador = '>='
        meta_margen.valor_objetivo = Decimal('2000')
        meta_margen.save(update_fields=['descripcion', 'operador', 'valor_objetivo'])
    meta_desviacion = simulacion.condiciones_exito.filter(
        codigo_indicador='sub_sobre_aplicacion',
    ).first()
    if meta_desviacion:
        meta_desviacion.descripcion = 'Cerrar con la sub o sobreaplicación dentro de ±$5.000'
        meta_desviacion.operador = 'ABS<='
        meta_desviacion.valor_objetivo = Decimal('5000')
        meta_desviacion.save(update_fields=['descripcion', 'operador', 'valor_objetivo'])

    evento_reclamo = simulacion.eventos.filter(nombre__icontains='Reclamo').first()
    if evento_reclamo:
        evento_reclamo.efecto = {'sub_sobre_aplicacion': 500}
        evento_reclamo.save(update_fields=['efecto'])
    evento_tarifa = simulacion.eventos.filter(nombre__icontains='tarifa electrica').first()
    if evento_tarifa:
        evento_tarifa.efecto = {'tasa_cif': 1.8, 'eficiencia_cif': -0.08}
        evento_tarifa.save(update_fields=['efecto'])

    simulacion.acciones_sugeridas.filter(activo=True).update(numero_ronda=2)
    parametros = dict(simulacion.parametros or {})
    rondas = [dict(r) for r in (parametros.get('rondas') or []) if isinstance(r, dict)]
    por_numero = {int(r.get('numero', 0)): r for r in rondas}
    datos_fijos = (
        'Datos del trimestre: CIF presupuestados $120.000, 8.000 horas máquina, '
        'CIF reales $133.333, costos fijos $50.000, precio promedio $5.000 y '
        'costo variable promedio $3.000 por orden.'
    )
    r1 = por_numero.get(1, {'numero': 1})
    r1.update({
        'titulo': 'Diagnóstico',
        'proposito': 'Identificar el problema principal y sustentarlo con un cálculo del caso.',
        'situacion': datos_fijos + ' Indica el problema principal y el dato que lo demuestra.',
        'modo': 'escribir',
        'etiqueta_decision': 'Problema principal',
        'etiqueta_justificacion': 'Dato que lo demuestra',
        'justificacion_obligatoria': True,
        'pedir_pronostico': False,
        'pedir_tradeoff': False,
        'pedir_reflexion': False,
    })
    r2 = por_numero.get(2, {'numero': 2})
    r2.update({
        'titulo': 'Decisión',
        'proposito': 'Elegir una acción viable y reconocer su consecuencia y su costo.',
        'situacion': 'Elige la acción prioritaria para corregir el costeo. Justifícala con un dato en una sola frase.',
        'modo': 'hibrido',
        'etiqueta_decision': 'Acción prioritaria',
        'etiqueta_justificacion': 'Dato o razón principal',
        'justificacion_obligatoria': True,
        'pedir_pronostico': False,
        'pedir_tradeoff': True,
        'pedir_reflexion': False,
    })
    r3 = por_numero.get(3, {'numero': 3})
    r3.update({
        'titulo': 'Plan breve',
        'proposito': 'Convertir la decisión en acciones controlables.',
        'situacion': 'Cierra con un plan breve: primera acción, responsable, plazo e indicador de control.',
        'modo': 'escribir',
        'etiqueta_decision': 'Acción, responsable y plazo',
        'etiqueta_justificacion': 'Indicador con el que controlarás el resultado',
        'justificacion_obligatoria': True,
        'pedir_pronostico': False,
        'pedir_tradeoff': False,
        'pedir_reflexion': True,
    })
    parametros['rondas'] = [r1, r2, r3]
    simulacion.parametros = parametros
    if datos_fijos not in (simulacion.contexto or ''):
        simulacion.contexto = f'{simulacion.contexto or ""} {datos_fijos}'.strip()
    simulacion.situacion_inicial = r1['situacion']
    simulacion.configuracion_snapshot = {}
    simulacion.save(update_fields=[
        'parametros', 'contexto', 'situacion_inicial', 'configuracion_snapshot',
    ])

    Intento = apps.get_model('simulador', 'IntentoSimulacion')
    for intento in Intento.objects.filter(simulacion_id=simulacion.pk):
        snapshot = dict(intento.configuracion_snapshot or {})
        for item in snapshot.get('indicadores') or []:
            if item.get('codigo') == 'eficiencia_cif':
                item.update({'valor_minimo': '0.00', 'valor_maximo': '1.00', 'direccion_optima': 'ALTO', 'valor_objetivo': None})
            elif item.get('codigo') == 'tasa_cif':
                item.update({'direccion_optima': 'OBJETIVO', 'valor_objetivo': '15.00'})
            elif item.get('codigo') == 'sub_sobre_aplicacion':
                item.update({'direccion_optima': 'OBJETIVO', 'valor_objetivo': '0.00'})
        for meta in snapshot.get('condiciones_exito') or []:
            if meta.get('codigo_indicador') == 'margen_contribucion':
                meta.update({
                    'descripcion': 'Mantener el margen de contribución por orden sobre $2.000',
                    'operador': '>=', 'valor_objetivo': '2000.00',
                })
            elif meta.get('codigo_indicador') == 'sub_sobre_aplicacion':
                meta.update({
                    'descripcion': 'Cerrar con la sub o sobreaplicación dentro de ±$5.000',
                    'operador': 'ABS<=', 'valor_objetivo': '5000.00',
                })
        caso = dict(snapshot.get('caso') or {})
        caso['parametros'] = parametros
        caso['situacion_inicial'] = r1['situacion']
        snapshot['caso'] = caso
        intento.configuracion_snapshot = snapshot
        intento.save(update_fields=['configuracion_snapshot'])

    conceptos_r2 = list(simulacion.conceptos_esperados.filter(numero_ronda=2, activo=True))
    especificaciones = [
        (
            'Decisión técnica sustentada', Decimal('40'), True,
            {'any': ['tasa', 'base de asignación', 'precio', 'margen', 'costos fijos', 'horas máquina']},
        ),
        (
            'Evidencia cuantitativa del caso', Decimal('35'), True,
            {'any': ['13333', '13,33', '13.33', '15', '2000', '2.000', '25', 'horas máquina']},
        ),
        (
            'Consecuencia o riesgo aceptado', Decimal('25'), False,
            {'any': ['subaplicación', 'sobreaplicación', 'demanda', 'margen', 'riesgo', 'costo', 'retraso']},
        ),
    ]
    for concepto, spec in zip(conceptos_r2, especificaciones):
        concepto.nombre, concepto.peso, concepto.es_critico, concepto.regla_evaluacion = spec
        concepto.palabras_clave = spec[3]
        concepto.impacto_si_cumple = {}
        concepto.impacto_si_falta = {}
        concepto.save(update_fields=[
            'nombre', 'peso', 'es_critico', 'regla_evaluacion', 'palabras_clave',
            'impacto_si_cumple', 'impacto_si_falta',
        ])


class Migration(migrations.Migration):

    dependencies = [
        ('simulador', '0031_rondas_sin_cantidad_heredada'),
    ]

    operations = [
        migrations.AddField(
            model_name='indicadorsimulacion',
            name='valor_objetivo',
            field=models.DecimalField(
                blank=True, decimal_places=2,
                help_text='Solo se usa cuando el indicador debe acercarse a un valor concreto.',
                max_digits=12, null=True,
            ),
        ),
        migrations.AlterField(
            model_name='indicadorsimulacion',
            name='direccion_optima',
            field=models.CharField(
                choices=[
                    ('ALTO', 'Mejor cuando es alto'),
                    ('BAJO', 'Mejor cuando es bajo'),
                    ('OBJETIVO', 'Mejor cerca de un valor objetivo'),
                ],
                default='ALTO',
                help_text='Define si conviene subir, bajar o acercarse a un valor objetivo.',
                max_length=10,
            ),
        ),
        migrations.AlterField(
            model_name='restriccionsimulacion',
            name='operador',
            field=models.CharField(
                choices=[('>', '>'), ('>=', '>='), ('<', '<'), ('<=', '<='), ('=', '='), ('ABS<=', 'Valor absoluto <=')],
                max_length=5,
            ),
        ),
        migrations.AlterField(
            model_name='condicionexitosimulacion',
            name='operador',
            field=models.CharField(
                choices=[('>', '>'), ('>=', '>='), ('<', '<'), ('<=', '<='), ('=', '='), ('ABS<=', 'Valor absoluto <=')],
                max_length=5,
            ),
        ),
        migrations.RunPython(corregir_caso_cif, migrations.RunPython.noop),
    ]
