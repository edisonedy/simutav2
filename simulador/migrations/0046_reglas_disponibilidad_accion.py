from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('simulador', '0045_indicador_rango_objetivo'),
    ]

    operations = [
        migrations.AddField(
            model_name='accionsugeridasimulacion',
            name='bloqueada_por_accion_previa',
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    'Si el estudiante eligió previamente esta decisión, la alternativa '
                    'actual deja de estar disponible.'
                ),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='acciones_bloqueadas',
                to='simulador.accionsugeridasimulacion',
            ),
        ),
        migrations.AddField(
            model_name='accionsugeridasimulacion',
            name='maximo_ejecuciones',
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text='Número máximo de veces que puede ejecutarse en un intento. 0 significa sin límite.',
            ),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='accionsugeridasimulacion',
            name='maximo_ejecuciones',
            field=models.PositiveSmallIntegerField(
                default=1,
                help_text='Número máximo de veces que puede ejecutarse en un intento. 0 significa sin límite.',
            ),
        ),
    ]
