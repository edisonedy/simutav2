from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('simulador', '0044_investigacion_diagnostico_estrategico'),
    ]

    operations = [
        migrations.AddField(
            model_name='indicadorsimulacion',
            name='valor_objetivo_min',
            field=models.DecimalField(
                blank=True, decimal_places=2,
                help_text='Límite inferior deseable cuando la dirección óptima es un rango.',
                max_digits=12, null=True,
            ),
        ),
        migrations.AddField(
            model_name='indicadorsimulacion',
            name='valor_objetivo_max',
            field=models.DecimalField(
                blank=True, decimal_places=2,
                help_text='Límite superior deseable cuando la dirección óptima es un rango.',
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
                    ('RANGO', 'Mejor dentro de un rango objetivo'),
                ],
                default='ALTO',
                help_text='Define si conviene subir, bajar, acercarse a un valor o permanecer en un rango.',
                max_length=10,
            ),
        ),
    ]
