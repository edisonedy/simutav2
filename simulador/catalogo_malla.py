"""Como se recorre el catalogo de simulaciones en todos los paneles.

El mismo camino que ve el estudiante, para que administrador, profesor y alumno
hablen del mismo sitio:

    malla -> materias por nivel -> simulaciones de cada materia

Sin esto cada panel listaba simulaciones sueltas y no habia forma de saber de
que plan de estudios era cada una.
"""

from collections import OrderedDict

from academico.models import Malla, MateriaMalla


def mallas_con_simulaciones(simulaciones):
    """Las mallas que aparecen en ese conjunto de simulaciones, con sus conteos.

    `simulaciones` es el queryset ya recortado por permisos, asi que cada rol ve
    solo lo suyo sin que esta funcion tenga que saber de roles."""
    conteos = {}
    for simulacion in simulaciones.select_related('materia_malla'):
        fila = conteos.setdefault(
            simulacion.materia_malla.malla_id, {'simulaciones': 0, 'publicadas': 0, 'materias': set()},
        )
        fila['simulaciones'] += 1
        fila['materias'].add(simulacion.materia_malla_id)
        if simulacion.estado == simulacion.PUBLICADA:
            fila['publicadas'] += 1

    mallas = Malla.objects.filter(pk__in=conteos).select_related('carrera')
    tarjetas = [
        {
            'malla': malla,
            'simulaciones': conteos[malla.pk]['simulaciones'],
            'publicadas': conteos[malla.pk]['publicadas'],
            'materias': len(conteos[malla.pk]['materias']),
        }
        for malla in mallas
    ]
    return sorted(tarjetas, key=lambda t: (t['malla'].carrera.nombre, t['malla'].nombre))


def niveles_de_la_malla(malla, simulaciones):
    """Las materias de la malla agrupadas por nivel, cada una con las
    simulaciones que le tocan. Se listan TODAS las materias de la malla, tambien
    las que aun no tienen ninguna: ver el hueco es justamente lo util."""
    por_materia = {}
    for simulacion in simulaciones.select_related('materia_malla'):
        por_materia.setdefault(simulacion.materia_malla_id, []).append(simulacion)

    materias = MateriaMalla.objects.filter(malla=malla, activo=True).select_related(
        'materia', 'nivel', 'malla',
    ).order_by('nivel__numero', 'orden', 'materia__nombre')

    niveles = OrderedDict()
    total = 0
    for materia_malla in materias:
        suyas = por_materia.get(materia_malla.pk, [])
        materia_malla.simulaciones_visibles = suyas
        total += len(suyas)
        numero = materia_malla.nivel.numero
        nivel = niveles.setdefault(numero, {
            'numero': numero,
            'nombre': materia_malla.nivel.nombre,
            'materias': [],
            'total_simulaciones': 0,
        })
        nivel['materias'].append(materia_malla)
        nivel['total_simulaciones'] += len(suyas)
    return list(niveles.values()), total
