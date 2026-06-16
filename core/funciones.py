from django.http import JsonResponse


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
