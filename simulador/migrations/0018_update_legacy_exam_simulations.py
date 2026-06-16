from django.db import migrations


ACCIONES_AUTO_ANTIGUAS = {
    'Diagnosticar el problema con datos antes de decidir',
    'Definir un plan con responsables, tiempos y controles',
    'Actuar de inmediato sin analizar ni planificar',
}


def _lista_texto(valor):
    if isinstance(valor, list):
        return ', '.join(str(item) for item in valor if str(item).strip())
    return str(valor or '')


def _render(texto, simulacion):
    materia = simulacion.materia_malla.materia.nombre
    perfil = simulacion.perfil_materia_ia
    rol = simulacion.rol_estudiante or (perfil.rol_profesional if perfil else '') or f'Analista en {materia}'
    contexto = {
        'materia': materia,
        'nivel': simulacion.materia_malla.nivel.numero,
        'rol': rol,
        'temas': _lista_texto(perfil.temas_clave if perfil else []),
        'conceptos': _lista_texto(perfil.conceptos_clave if perfil else []),
        'competencias': _lista_texto(perfil.competencias if perfil else []),
    }
    try:
        return (texto or '').format(**contexto)
    except (KeyError, ValueError):
        return texto or ''


def _render_json(valor, simulacion):
    if isinstance(valor, dict):
        return {clave: _render_json(item, simulacion) for clave, item in valor.items()}
    if isinstance(valor, list):
        return [_render_json(item, simulacion) for item in valor]
    if isinstance(valor, str):
        return _render(valor, simulacion)
    return valor


def forwards(apps, schema_editor):
    PlantillaSimulacion = apps.get_model('simulador', 'PlantillaSimulacion')
    Simulacion = apps.get_model('simulador', 'Simulacion')
    AccionSugeridaSimulacion = apps.get_model('simulador', 'AccionSugeridaSimulacion')

    plantilla = PlantillaSimulacion.objects.filter(codigo='global-decision-3rondas-v1').first()
    if not plantilla:
        return

    simulaciones = (
        Simulacion.objects
        .filter(tipo_simulacion='CON_IA_DINAMICA', titulo__startswith='Examen SimutaV2 - ')
        .select_related('materia_malla__materia', 'materia_malla__nivel', 'perfil_materia_ia')
    )
    for simulacion in simulaciones:
        rondas_parametros = []
        for ronda in plantilla.rondas.filter(activo=True).order_by('numero'):
            opciones = _render_json(ronda.opciones_decision or [], simulacion)
            rondas_parametros.append({
                'numero': ronda.numero,
                'titulo': _render(ronda.titulo, simulacion),
                'proposito': _render(ronda.proposito, simulacion),
                'situacion': _render(ronda.consigna_base, simulacion),
                'opciones_decision': opciones,
            })
            for opcion in opciones:
                if isinstance(opcion, dict):
                    texto = str(opcion.get('texto') or '').strip()
                    descripcion = str(opcion.get('descripcion') or '').strip()
                    impacto = opcion.get('impacto') if isinstance(opcion.get('impacto'), dict) else {}
                else:
                    texto = str(opcion or '').strip()
                    descripcion = ''
                    impacto = {}
                if not texto:
                    continue
                AccionSugeridaSimulacion.objects.get_or_create(
                    simulacion=simulacion,
                    numero_ronda=ronda.numero,
                    texto=texto,
                    defaults={
                        'descripcion': descripcion,
                        'impacto_base': impacto,
                        'usuario_creacion': simulacion.usuario_creacion,
                    },
                )

        simulacion.acciones_sugeridas.filter(
            numero_ronda__isnull=True,
            texto__in=ACCIONES_AUTO_ANTIGUAS,
        ).update(activo=False)

        parametros = dict(simulacion.parametros or {})
        parametros['modo'] = 'toma_decisiones'
        parametros['rondas'] = rondas_parametros
        simulacion.parametros = parametros
        if not simulacion.plantilla_origen_id:
            simulacion.plantilla_origen = plantilla
        simulacion.titulo = simulacion.titulo.replace('Examen SimutaV2 - ', 'Simulacion SimutaV2 - ', 1)
        if rondas_parametros and rondas_parametros[0].get('situacion'):
            simulacion.situacion_inicial = rondas_parametros[0]['situacion']
        simulacion.version_configuracion = (simulacion.version_configuracion or 1) + 1
        simulacion.save(update_fields=[
            'plantilla_origen', 'titulo', 'situacion_inicial',
            'parametros', 'version_configuracion',
        ])


def backwards(apps, schema_editor):
    Simulacion = apps.get_model('simulador', 'Simulacion')
    for simulacion in Simulacion.objects.filter(titulo__startswith='Simulacion SimutaV2 - '):
        simulacion.titulo = simulacion.titulo.replace('Simulacion SimutaV2 - ', 'Examen SimutaV2 - ', 1)
        simulacion.save(update_fields=['titulo'])


class Migration(migrations.Migration):

    dependencies = [
        ('simulador', '0017_update_generated_simulations_to_decision_mode'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
