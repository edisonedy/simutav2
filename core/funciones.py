from django.contrib import messages
from django.core.exceptions import FieldDoesNotExist
from django.db.models import Q
from django.http import HttpResponseRedirect, JsonResponse


def ok_json(data=None, mensaje='Guardado correctamente'):
    if data is None:
        data = {}
    response = {'result': True, 'mensaje': mensaje}
    response.update(data)
    return JsonResponse(response)


def bad_json(mensaje='Error al procesar la solicitud', data=None):
    if data is None:
        data = {}
    response = {'result': False, 'mensaje': mensaje}
    response.update(data)
    return JsonResponse(response)


def errores_formulario(form):
    """Devuelve los errores de un formulario como un texto legible para el usuario."""
    mensajes = []
    for campo, errores in form.errors.items():
        etiqueta = form.fields[campo].label if campo in form.fields else 'General'
        prefijo = f'{etiqueta}: ' if campo != '__all__' else ''
        for error in errores:
            mensajes.append(f'{prefijo}{error}')
    return ' | '.join(mensajes) or 'Error en el formulario'


def es_ajax(request):
    """True si el formulario se envio desde un modal con fetch y espera JSON."""
    return request.headers.get('x-requested-with') == 'XMLHttpRequest'


def respuesta_ok(request, url_retorno, mensaje='Guardado correctamente'):
    """Responde JSON al modal; si el navegador envio el formulario sin JavaScript
    redirige al listado con el mensaje visible."""
    if es_ajax(request):
        return ok_json(mensaje=mensaje)
    messages.success(request, mensaje)
    return HttpResponseRedirect(url_retorno)


def respuesta_error(request, url_retorno, mensaje='Error al procesar la solicitud', data=None):
    """Contraparte de respuesta_ok para los errores."""
    if es_ajax(request):
        return bad_json(mensaje=mensaje, data=data)
    messages.error(request, mensaje)
    return HttpResponseRedirect(url_retorno)


def conservar_seleccion_actual(form):
    """Vuelve a meter en los desplegables el valor que el registro YA tiene.

    Los formularios recortan sus querysets (por rol, por activo, por materias
    asignadas). Al editar, si el valor guardado quedo fuera de ese recorte el
    select aparece vacio y guardar revienta con "Escoja una opcion valida".
    Solo afecta a la edicion: en un alta no hay instancia y no se toca nada.
    """
    instancia = getattr(form, 'instance', None)
    if instancia is None or not instancia.pk:
        return form
    for nombre, campo in form.fields.items():
        queryset = getattr(campo, 'queryset', None)
        if queryset is None:
            continue
        try:
            campo_modelo = instancia._meta.get_field(nombre)
        except FieldDoesNotExist:
            continue
        if campo_modelo.many_to_many:
            actuales = list(getattr(instancia, nombre).values_list('pk', flat=True))
        elif campo_modelo.is_relation:
            actuales = [getattr(instancia, f'{nombre}_id', None)]
        else:
            continue
        faltantes = [pk for pk in actuales if pk and not queryset.filter(pk=pk).exists()]
        if faltantes:
            campo.queryset = queryset.model.objects.filter(
                Q(pk__in=queryset.values('pk')) | Q(pk__in=faltantes)
            )
    return form
