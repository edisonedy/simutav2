"""Puente entre las rondas configuradas y el motor que ya juega el estudiante.

El docente configura el caso en `RondaSimulacion` / `OpcionRondaSimulacion`.
El motor de juego, en cambio, lee las rondas desde `Simulacion.parametros`
y las alternativas desde `AccionSugeridaSimulacion`. Este modulo traduce lo
primero en lo segundo.

Se hace asi a proposito: la configuracion pasa a ser datos editables -que es
lo que permite cargar un caso nuevo sin escribir Python- sin tener que
reescribir el motor, el snapshot de los intentos ni las pantallas del alumno.
"""

from django.db import transaction

from simulador.models import (
    AccionSugeridaSimulacion,
    OpcionRondaSimulacion,
    RondaSimulacion,
    Simulacion,
)

# Estas banderas deciden que ve el estudiante en cada ronda. Con rondas
# configuradas se derivan del tipo de respuesta en vez de pedirselas al
# docente una por una.
def _visibilidad(ronda):
    tiene_datos = bool(ronda.datos)
    return {
        'mostrar_objetivos': True,
        'mostrar_rubrica': True,
        'mostrar_datos_caso': tiene_datos or ronda.pide_elegir,
        'mostrar_indicadores': (
            ronda.simulacion.modo_ejecucion == Simulacion.MODO_SIMULACION_ENCADENADA
        ),
        'mostrar_recursos': (
            ronda.simulacion.modo_ejecucion == Simulacion.MODO_SIMULACION_ENCADENADA
        ),
    }


def _etiqueta_decision(ronda):
    return {
        RondaSimulacion.OPCION_UNICA: 'Tu decision',
        RondaSimulacion.OPCION_MULTIPLE: 'Tus decisiones',
        RondaSimulacion.NUMERICA: 'Tu calculo',
        RondaSimulacion.ARCHIVO: 'Tu entrega',
        RondaSimulacion.TEXTO: 'Tu respuesta',
    }.get(ronda.tipo_respuesta, 'Tu respuesta')


def ronda_a_parametros(ronda):
    """La ronda en el formato que espera el motor de juego."""
    item = {
        'numero': ronda.numero,
        'titulo': ronda.titulo,
        'situacion': ronda.situacion,
        'proposito': ronda.instrucciones,
        'modo': ronda.modo_interaccion,
        'tipo_respuesta': ronda.tipo_respuesta,
        'etiqueta_decision': _etiqueta_decision(ronda),
        'etiqueta_justificacion': (
            'Justifica tu decision' if ronda.requiere_justificacion
            else 'Comentario (opcional)'
        ),
        # Sin esto la etiqueta decia "opcional" pero el campo seguia siendo
        # obligatorio y el navegador no dejaba enviar la ronda.
        'justificacion_obligatoria': ronda.requiere_justificacion,
        'campos': list(ronda.campos or []),
        'datos': ronda.datos or {},
        'respuesta_modelo': ronda.respuesta_modelo,
        'retroalimentacion': ronda.retroalimentacion,
    }
    item.update(_visibilidad(ronda))
    return item


@transaction.atomic
def materializar(simulacion):
    """Vuelca las rondas configuradas al motor. Idempotente.

    Devuelve cuantas rondas y cuantas alternativas quedaron activas.
    """
    rondas = list(
        RondaSimulacion.objects
        .filter(simulacion=simulacion, activo=True)
        .select_related('simulacion')
        .prefetch_related('opciones')
        .order_by('numero')
    )
    if not rondas:
        return 0, 0

    parametros = dict(simulacion.parametros or {})
    parametros['rondas'] = [ronda_a_parametros(ronda) for ronda in rondas]
    simulacion.parametros = parametros
    simulacion.maximo_decisiones = len(rondas)
    simulacion.save(update_fields=['parametros', 'maximo_decisiones'])

    numeros = {ronda.numero for ronda in rondas}
    alternativas = 0
    vistas = []
    for ronda in rondas:
        for opcion in ronda.opciones.filter(activo=True).order_by('orden', 'texto'):
            accion, _ = AccionSugeridaSimulacion.objects.update_or_create(
                simulacion=simulacion,
                numero_ronda=ronda.numero,
                texto=opcion.texto,
                defaults={
                    'descripcion': opcion.descripcion,
                    # Lo que hace que el caso se pueda calificar sin IA: elegir
                    # la alternativa correcta vale distinto que elegir mal.
                    'puntaje': opcion.puntaje,
                    'retroalimentacion': opcion.retroalimentacion,
                    # El impacto solo tiene sentido cuando la decision mueve la
                    # empresa. En decisiones independientes se deja limpio para
                    # que la ronda 2 no arranque contaminada por la ronda 1.
                    'impacto_base': (
                        dict(opcion.impacto or {})
                        if simulacion.modo_ejecucion == Simulacion.MODO_SIMULACION_ENCADENADA
                        else {}
                    ),
                    'maximo_ejecuciones': 1,
                    'activo': True,
                    'usuario_creacion': simulacion.usuario_creacion,
                },
            )
            vistas.append(accion.pk)
            alternativas += 1

    # Lo que sobro de una configuracion anterior deja de ofrecerse, para que no
    # queden alternativas fantasma de una version vieja del caso.
    AccionSugeridaSimulacion.objects.filter(
        simulacion=simulacion, activo=True, numero_ronda__in=numeros,
    ).exclude(pk__in=vistas).update(activo=False)
    AccionSugeridaSimulacion.objects.filter(
        simulacion=simulacion, activo=True, numero_ronda__gt=len(rondas),
    ).update(activo=False)

    return len(rondas), alternativas


def opciones_de(simulacion, numero_ronda):
    """Las alternativas configuradas de una ronda, para pantallas y reportes."""
    return OpcionRondaSimulacion.objects.filter(
        ronda__simulacion=simulacion,
        ronda__numero=numero_ronda,
        ronda__activo=True,
        activo=True,
    ).order_by('orden', 'texto')
