from django.db import migrations


CONTEXTO = (
    'Industrias del Norte S.A. fabrica piezas bajo pedido. Para el trimestre '
    'presupuestó $120.000 de CIF sobre 8.000 horas máquina; los CIF reales fueron '
    '$133.333. Cada orden se vende en promedio por $5.000, tiene $3.000 de costo '
    'variable y la empresa soporta $50.000 de costos fijos. Debes decidir cómo '
    'corregir la asignación sin perder margen ni control operativo.'
)


def limpiar_contexto(apps, schema_editor):
    Simulacion = apps.get_model('simulador', 'Simulacion')
    Intento = apps.get_model('simulador', 'IntentoSimulacion')
    simulacion = Simulacion.objects.filter(titulo__icontains='Industrias del Norte').first()
    if not simulacion:
        return
    simulacion.contexto = CONTEXTO
    simulacion.objetivo = (
        'Diagnosticar la desviación de CIF, elegir una acción defendible y cerrar '
        'con un plan breve de implementación y control.'
    )
    simulacion.resultado_aprendizaje = (
        'Toma decisiones de costeo por órdenes usando tasa CIF, desviaciones, '
        'margen de contribución, punto de equilibrio y trade-offs.'
    )
    simulacion.configuracion_snapshot = {}
    simulacion.save(update_fields=[
        'contexto', 'objetivo', 'resultado_aprendizaje', 'configuracion_snapshot',
    ])

    for intento in Intento.objects.filter(simulacion_id=simulacion.pk):
        snapshot = dict(intento.configuracion_snapshot or {})
        caso = dict(snapshot.get('caso') or {})
        caso['contexto'] = CONTEXTO
        caso['objetivo'] = simulacion.objetivo
        caso['resultado_aprendizaje'] = simulacion.resultado_aprendizaje
        snapshot['caso'] = caso
        snapshot['aviso_version'] = (
            'Este intento se realizó con la configuración anterior. Las metas y '
            'escalas ya fueron corregidas; reintenta la misión para probar las nuevas consecuencias.'
        )
        intento.configuracion_snapshot = snapshot
        intento.save(update_fields=['configuracion_snapshot'])


class Migration(migrations.Migration):

    dependencies = [
        ('simulador', '0032_indicador_objetivo_y_caso_cif_coherente'),
    ]

    operations = [
        migrations.RunPython(limpiar_contexto, migrations.RunPython.noop),
    ]
