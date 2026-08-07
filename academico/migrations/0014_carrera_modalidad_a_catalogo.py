"""Carrera.modalidad deja de ser texto libre y pasa a apuntar al catalogo.

Se hace en tres tiempos dentro de la misma migracion para no perder lo que ya
estaba escrito: se aparta el texto, se crea la relacion, se traduce cada texto
a su modalidad (normalizando 'PRESENCIAL' y 'Presencial' a la misma fila) y
recien entonces se bota la columna vieja.
"""

import django.db.models.deletion
from django.db import migrations, models


def texto_a_catalogo(apps, schema_editor):
    Carrera = apps.get_model('academico', 'Carrera')
    Modalidad = apps.get_model('academico', 'Modalidad')

    cache = {}
    for carrera in Carrera.objects.exclude(modalidad_texto='').exclude(modalidad_texto=None):
        crudo = carrera.modalidad_texto.strip()
        if not crudo:
            continue
        clave = crudo.lower()
        modalidad = cache.get(clave)
        if modalidad is None:
            # Se guarda con la primera letra en mayuscula: 'PRESENCIAL' y
            # 'presencial' terminan siendo la misma 'Presencial'.
            modalidad, _ = Modalidad.objects.get_or_create(nombre=crudo.capitalize())
            cache[clave] = modalidad
        carrera.modalidad = modalidad
        carrera.save(update_fields=['modalidad'])


def catalogo_a_texto(apps, schema_editor):
    Carrera = apps.get_model('academico', 'Carrera')
    for carrera in Carrera.objects.exclude(modalidad=None).select_related('modalidad'):
        carrera.modalidad_texto = carrera.modalidad.nombre
        carrera.save(update_fields=['modalidad_texto'])


class Migration(migrations.Migration):

    dependencies = [
        ('academico', '0013_catalogo_modalidad'),
    ]

    operations = [
        migrations.RenameField(
            model_name='carrera',
            old_name='modalidad',
            new_name='modalidad_texto',
        ),
        migrations.AddField(
            model_name='carrera',
            name='modalidad',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='carreras',
                to='academico.modalidad',
            ),
        ),
        migrations.RunPython(texto_a_catalogo, catalogo_a_texto),
        migrations.RemoveField(
            model_name='carrera',
            name='modalidad_texto',
        ),
    ]
