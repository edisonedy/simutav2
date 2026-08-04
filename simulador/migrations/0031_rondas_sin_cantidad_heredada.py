from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('simulador', '0030_intentosimulacion_investigaciones_compradas_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='plantillasimulacion',
            name='maximo_decisiones',
        ),
        migrations.AlterField(
            model_name='simulacion',
            name='maximo_decisiones',
            field=models.PositiveIntegerField(
                default=1,
                help_text='Cantidad exacta de rondas que necesita el caso.',
                validators=[MinValueValidator(1)],
            ),
        ),
    ]
