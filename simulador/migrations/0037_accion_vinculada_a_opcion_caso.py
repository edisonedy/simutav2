from django.db import migrations, models
import django.db.models.deletion


def vincular_caso_talento(apps, schema_editor):
    Simulacion = apps.get_model('simulador', 'Simulacion')
    Accion = apps.get_model('simulador', 'AccionSugeridaSimulacion')
    Opcion = apps.get_model('simulador', 'OpcionCasoSimulacion')

    simulacion = Simulacion.objects.filter(
        titulo__icontains='Contratar 1 de 3 desarrolladores Django',
    ).first()
    if not simulacion:
        return
    vinculos = {
        'Contratar a Ana Reyes': 'Ana Reyes',
        'Contratar a Luis Carrion': 'Luis Carrión',
        'Contratar a Marta Sanchez': 'Marta Sánchez',
    }
    for texto, nombre in vinculos.items():
        opcion = Opcion.objects.filter(simulacion=simulacion, nombre=nombre, activo=True).first()
        if opcion:
            Accion.objects.filter(
                simulacion=simulacion, numero_ronda=2, texto=texto, activo=True,
            ).update(opcion_caso_id=opcion.id)

    parametros = dict(simulacion.parametros or {})
    rondas = list(parametros.get('rondas') or [])
    for indice, item in enumerate(rondas):
        if not isinstance(item, dict):
            continue
        numero = int(item.get('numero') or indice + 1)
        if numero == 2:
            item = dict(item)
            item['alternativas_desde_datos_caso'] = True
            rondas[indice] = item
    parametros['rondas'] = rondas
    simulacion.parametros = parametros
    simulacion.save(update_fields=['parametros'])


class Migration(migrations.Migration):

    dependencies = [
        ('simulador', '0036_propositos_caso_talento'),
    ]

    operations = [
        migrations.AddField(
            model_name='accionsugeridasimulacion',
            name='opcion_caso',
            field=models.ForeignKey(
                blank=True,
                help_text='Alternativa visible a la que pertenece esta consecuencia, si aplica.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='acciones_vinculadas',
                to='simulador.opcioncasosimulacion',
            ),
        ),
        migrations.RunPython(vincular_caso_talento, migrations.RunPython.noop),
    ]
