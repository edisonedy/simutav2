"""Se retira el enlace por nivel, ya reemplazado por MallaPeriodo.

Va aparte de la 0009 porque esa mueve datos leyendo esta tabla.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('academico', '0009_mallaperiodo'),
        # Seccion tenia una FK a NivelPeriodo; hay que esperar a que se quite o
        # el modelo historico no se puede resolver.
        ('simulador', '0051_remove_asignacion_guia_api_remove_seccion_cupo_and_more'),
    ]

    operations = [
        migrations.DeleteModel(name='NivelPeriodo'),
    ]
