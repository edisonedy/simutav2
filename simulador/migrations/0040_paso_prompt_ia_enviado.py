from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('simulador', '0039_coherencia_caso_dcf'),
    ]

    operations = [
        migrations.AddField(
            model_name='pasosimulacion',
            name='prompt_ia_enviado',
            field=models.TextField(
                blank=True,
                default='',
                help_text='Prompt efectivo enviado al proveedor para auditoría de la evaluación.',
            ),
        ),
    ]
