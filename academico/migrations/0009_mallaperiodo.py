"""El enlace con el periodo pasa de ser por nivel a ser por malla.

Conectar la malla con el periodo es lo que hace falta; los niveles y sus
asignaturas se ven todos dentro, sin filtrar.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def pasar_de_nivel_a_malla(apps, schema_editor):
    """Cada malla que tuviera algun nivel enlazado a un periodo conserva ese
    enlace, ahora a nivel de malla. Se guarda el primer nombre propio que se
    haya escrito, si habia alguno."""
    NivelPeriodo = apps.get_model('academico', 'NivelPeriodo')
    MallaPeriodo = apps.get_model('academico', 'MallaPeriodo')
    vistos = {}
    for enlace in NivelPeriodo.objects.select_related('nivel').order_by('id'):
        clave = (enlace.periodo_id, enlace.nivel.malla_id)
        if clave in vistos:
            continue
        vistos[clave] = MallaPeriodo.objects.create(
            periodo_id=enlace.periodo_id,
            malla_id=enlace.nivel.malla_id,
            nombre=enlace.nombre,
            activo=enlace.activo,
            usuario_creacion_id=enlace.usuario_creacion_id,
        )


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('academico', '0008_alter_nivelperiodo_options_nivelperiodo_nombre'),
    ]

    operations = [
        migrations.CreateModel(
            name='MallaPeriodo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('activo', models.BooleanField(default=True)),
                ('fecha_creacion', models.DateTimeField(auto_now_add=True)),
                ('fecha_modificacion', models.DateTimeField(auto_now=True)),
                ('nombre', models.CharField(blank=True, help_text='Como se llama esta malla en el periodo. Si lo dejas vacio se usa el de la malla.', max_length=150)),
                ('malla', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='periodos', to='academico.malla')),
                ('periodo', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='mallas_periodo', to='academico.periodoacademico')),
                ('usuario_creacion', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_creados', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'malla en el periodo',
                'verbose_name_plural': 'mallas en el periodo',
                'ordering': ['-periodo__fecha_inicio', 'malla__nombre'],
                'unique_together': {('periodo', 'malla')},
            },
        ),
        migrations.RunPython(pasar_de_nivel_a_malla, migrations.RunPython.noop),
    ]
