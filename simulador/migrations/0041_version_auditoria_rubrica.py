from django.db import migrations, models


def actualizar_versiones(apps, schema_editor):
    Simulacion = apps.get_model('simulador', 'Simulacion')
    Simulacion.objects.filter(prompt_version='simuta-rubrica-v1').update(
        prompt_version='simuta-rubrica-v2',
    )
    Simulacion.objects.filter(esquema_ia_version='rubrica-docente-v1').update(
        esquema_ia_version='rubrica-docente-v2',
    )


class Migration(migrations.Migration):

    dependencies = [
        ('simulador', '0040_paso_prompt_ia_enviado'),
    ]

    operations = [
        migrations.AlterField(
            model_name='simulacion',
            name='prompt_version',
            field=models.CharField(blank=True, default='simuta-rubrica-v2', max_length=40),
        ),
        migrations.AlterField(
            model_name='simulacion',
            name='esquema_ia_version',
            field=models.CharField(blank=True, default='rubrica-docente-v2', max_length=40),
        ),
        migrations.RunPython(actualizar_versiones, migrations.RunPython.noop),
    ]
