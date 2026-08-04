from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('simulador', '0033_contexto_cif_unico_y_aviso_historico'),
    ]

    operations = [
        migrations.AddField(
            model_name='indicadorsimulacion',
            name='peso_salud',
            field=models.DecimalField(
                decimal_places=2,
                default=1,
                help_text=(
                    'Peso relativo de este indicador en la salud del caso. '
                    'No necesita sumar 100; el sistema normaliza todos los pesos.'
                ),
                max_digits=6,
            ),
        ),
    ]
