from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('simulador', '0041_version_auditoria_rubrica'),
    ]

    operations = [
        migrations.AddField(
            model_name='accionsugeridasimulacion',
            name='requiere_accion_previa',
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    'Si se configura, esta decisión solo aparece cuando el estudiante '
                    'eligió previamente la decisión indicada.'
                ),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='acciones_dependientes',
                to='simulador.accionsugeridasimulacion',
            ),
        ),
    ]
