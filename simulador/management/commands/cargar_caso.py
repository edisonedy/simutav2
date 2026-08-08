"""Carga un caso desde una ficha declarativa. UN comando para todos los casos.

Antes cada caso nuevo era un comando de Python (`crear_caso_talento_django.py`,
`crear_caso_sistemas_informacion.py`, ...). Eso significa que meter el caso de
Finanzas que manda una facultad es una tarea de programacion, y que el docente
depende de alguien para publicar el suyo.

Aqui el caso es un archivo de datos: materia, contexto, archivos, rondas,
alternativas y rubrica. El comando lo lee y arma la simulacion completa.

    py manage.py cargar_caso casos/sag_benchmarking.json
    py manage.py cargar_caso casos/ --publicar
    py manage.py cargar_caso casos/finanzas_fcff.json --dry-run

La ficha se documenta en `simulador/casos/README.md`.
"""

import json
from decimal import Decimal
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from academico.models import Carrera, Malla, Materia, MateriaMalla, NivelMalla
from core.models import PerfilUsuario
from interactivo.models import ActividadInteractiva
from interactivo.plugins.base import PluginError
from interactivo.plugins.registry import get_plugin
from simulador.models import (
    ConceptoEsperadoRonda,
    CriterioEvaluacion,
    IndicadorSimulacion,
    MatrizEvaluacionCaso,
    OpcionCasoSimulacion,
    OpcionRondaSimulacion,
    RecursoSimulacionArchivo,
    RondaSimulacion,
    Simulacion,
    TemaMateria,
)
from simulador.services import rondas as servicio_rondas


class FichaInvalida(CommandError):
    pass


def _requerido(dato, clave, contexto):
    valor = dato.get(clave)
    if valor in (None, '', [], {}):
        raise FichaInvalida(f'{contexto}: falta "{clave}".')
    return valor


def _decimal(valor, por_defecto='0'):
    try:
        return Decimal(str(valor))
    except (TypeError, ValueError):
        return Decimal(por_defecto)


def _algun_admin():
    """A quien se le atribuye lo cargado cuando la ficha no dice nada."""
    perfil = PerfilUsuario.objects.filter(
        rol=PerfilUsuario.ADMIN, activo=True,
    ).select_related('usuario').first()
    return perfil.usuario if perfil else None


class Command(BaseCommand):
    help = 'Carga uno o varios casos desde fichas JSON, sin escribir codigo por caso.'

    def add_arguments(self, parser):
        parser.add_argument(
            'ruta',
            help='Archivo .json de la ficha, o carpeta con varias fichas.',
        )
        parser.add_argument(
            '--publicar',
            action='store_true',
            help='Deja el caso PUBLICADA en vez de BORRADOR.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Valida la ficha y muestra lo que haria, sin escribir nada.',
        )

    # ------------------------------------------------------------------
    # entrada
    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        ruta = Path(options['ruta'])
        if not ruta.exists():
            raise CommandError(f'No existe: {ruta}')

        fichas = sorted(ruta.glob('*.json')) if ruta.is_dir() else [ruta]
        if not fichas:
            raise CommandError(f'No hay fichas .json en {ruta}')

        cargados = 0
        for archivo in fichas:
            self.stdout.write(f'==> {archivo.name}')
            try:
                datos = json.loads(archivo.read_text(encoding='utf-8'))
            except json.JSONDecodeError as error:
                raise CommandError(f'{archivo.name}: JSON invalido ({error}).')
            simulacion = self._cargar(datos, archivo.parent, options)
            if simulacion:
                cargados += 1

        self.stdout.write(self.style.SUCCESS(f'Casos cargados: {cargados}/{len(fichas)}'))

    def _cargar(self, datos, base, options):
        if options['dry_run']:
            self._validar(datos)
            self.stdout.write('    ficha valida (dry-run, no se escribio nada)')
            return None
        with transaction.atomic():
            return self._construir(datos, base, options['publicar'])

    # ------------------------------------------------------------------
    # validacion
    # ------------------------------------------------------------------

    def _validar(self, datos):
        caso = _requerido(datos, 'caso', 'ficha')
        _requerido(caso, 'titulo', 'caso')
        _requerido(datos, 'materia', 'ficha')
        lista = _requerido(datos, 'rondas', 'ficha')
        numeros = []
        for indice, ronda in enumerate(lista, start=1):
            contexto = f'ronda {indice}'
            _requerido(ronda, 'titulo', contexto)
            _requerido(ronda, 'situacion', contexto)
            numero = int(ronda.get('numero') or indice)
            numeros.append(numero)
            tipo = ronda.get('tipo_respuesta', RondaSimulacion.OPCION_UNICA)
            validos = dict(RondaSimulacion.TIPOS_RESPUESTA)
            if tipo not in validos:
                raise FichaInvalida(
                    f'{contexto}: tipo_respuesta "{tipo}" no existe. '
                    f'Usa uno de: {", ".join(validos)}.'
                )
            if tipo in (RondaSimulacion.OPCION_UNICA, RondaSimulacion.OPCION_MULTIPLE):
                if not ronda.get('opciones'):
                    raise FichaInvalida(
                        f'{contexto}: es de eleccion pero no trae alternativas.'
                    )
            if tipo == RondaSimulacion.NUMERICA and not ronda.get('campos'):
                raise FichaInvalida(
                    f'{contexto}: es numerica pero no dice que valor se pide '
                    '(falta "campos").'
                )
        if len(set(numeros)) != len(numeros):
            raise FichaInvalida('Hay dos rondas con el mismo numero.')

    # ------------------------------------------------------------------
    # construccion
    # ------------------------------------------------------------------

    def _construir(self, datos, base, publicar):
        self._validar(datos)
        materia_malla = self._resolver_materia(datos['materia'])
        tema = self._resolver_tema(materia_malla, datos.get('tema'))
        simulacion = self._resolver_simulacion(datos['caso'], materia_malla, tema, publicar)

        self._cargar_indicadores(simulacion, datos.get('indicadores') or [])
        self._cargar_criterios(simulacion, datos.get('criterios') or [])
        self._cargar_matriz(simulacion, datos.get('matriz') or [])
        self._cargar_opciones_caso(simulacion, datos.get('opciones_caso') or [])
        creadas = self._cargar_rondas(simulacion, datos['rondas'])
        archivos = self._cargar_archivos(simulacion, datos.get('archivos') or [], base)
        juegos = self._cargar_juegos(simulacion, materia_malla, tema, datos.get('juegos') or [])

        total_rondas, alternativas = servicio_rondas.materializar(simulacion)

        self.stdout.write(
            f'    {simulacion.titulo}'
            f'\n      materia: {materia_malla.etiqueta_corta}'
            f'\n      modo: {simulacion.get_modo_ejecucion_display()}'
            f'\n      rondas: {creadas} (motor: {total_rondas}, alternativas: {alternativas})'
            f'\n      archivos: {archivos} | juegos: {juegos}'
            f'\n      estado: {simulacion.estado}'
        )
        return simulacion

    def _resolver_materia(self, datos):
        """Encuentra la materia de la malla, creando lo que falte del catalogo.

        La ficha puede traer solo `materia_malla_id` cuando la malla ya existe,
        o describir carrera/malla/nivel/materia para montarlo de cero.
        """
        if datos.get('materia_malla_id'):
            try:
                return MateriaMalla.objects.get(pk=datos['materia_malla_id'])
            except MateriaMalla.DoesNotExist:
                raise FichaInvalida(
                    f'No existe la materia de malla {datos["materia_malla_id"]}.'
                )

        codigo_materia = _requerido(datos, 'codigo', 'materia')
        codigo_malla = datos.get('malla_codigo')

        if not codigo_malla:
            encontrada = MateriaMalla.objects.filter(
                materia__codigo=codigo_materia, activo=True,
            ).select_related('malla', 'nivel', 'materia').first()
            if not encontrada:
                raise FichaInvalida(
                    f'La materia {codigo_materia} no esta en ninguna malla. '
                    'Agrega "malla_codigo" a la ficha para crearla.'
                )
            return encontrada

        carrera, _ = Carrera.objects.get_or_create(
            codigo=datos.get('carrera_codigo') or codigo_malla,
            defaults={'nombre': datos.get('carrera') or codigo_malla},
        )
        malla, _ = Malla.objects.get_or_create(
            carrera=carrera,
            codigo=codigo_malla,
            defaults={'nombre': datos.get('malla') or codigo_malla},
        )
        numero_nivel = int(datos.get('nivel') or 1)
        nivel, _ = NivelMalla.objects.get_or_create(
            malla=malla,
            numero=numero_nivel,
            defaults={'nombre': f'Nivel {numero_nivel}'},
        )
        materia, _ = Materia.objects.get_or_create(
            codigo=codigo_materia,
            defaults={
                'nombre': datos.get('nombre') or codigo_materia,
                'creditos': int(datos.get('creditos') or 0),
                'horas': int(datos.get('horas') or 0),
            },
        )
        materia_malla, _ = MateriaMalla.objects.get_or_create(
            malla=malla,
            materia=materia,
            defaults={'nivel': nivel, 'orden': int(datos.get('orden') or 1)},
        )
        return materia_malla

    def _resolver_tema(self, materia_malla, nombre):
        if not nombre:
            return None
        tema, _ = TemaMateria.objects.get_or_create(
            materia_malla=materia_malla,
            nombre=nombre,
            defaults={'orden': (materia_malla.temas.count() or 0) + 1},
        )
        return tema

    def _resolver_simulacion(self, caso, materia_malla, tema, publicar):
        modo = caso.get('modo') or Simulacion.MODO_CASO_INDEPENDIENTE
        if modo not in dict(Simulacion.MODOS_EJECUCION):
            raise FichaInvalida(
                f'modo "{modo}" no existe. Usa: '
                f'{", ".join(dict(Simulacion.MODOS_EJECUCION))}.'
            )
        estado = Simulacion.PUBLICADA if publicar else Simulacion.BORRADOR
        autor = _algun_admin()
        simulacion, _ = Simulacion.objects.update_or_create(
            materia_malla=materia_malla,
            titulo=caso['titulo'],
            defaults={
                'tema_materia': tema,
                'profesor': autor,
                'usuario_creacion': autor,
                'modo_ejecucion': modo,
                # El arbol lo juega el motor sin IA; los otros dos modos usan la
                # evaluacion dinamica de la rubrica.
                'tipo_simulacion': (
                    Simulacion.TIPO_SIN_IA_ARBOL
                    if modo == Simulacion.MODO_ARBOL_DECISION
                    else Simulacion.TIPO_CON_IA_DINAMICA
                ),
                'tema': caso.get('tema') or '',
                'rol_estudiante': caso.get('rol_estudiante') or '',
                'contexto': caso.get('contexto') or '',
                'objetivo': caso.get('objetivo') or '',
                'resultado_aprendizaje': caso.get('resultado_aprendizaje') or '',
                'situacion_inicial': caso.get('situacion_inicial') or caso.get('contexto') or '',
                'nivel_dificultad': caso.get('dificultad') or Simulacion.DIFICULTAD_MEDIA,
                'tiempo_estimado': int(caso.get('tiempo_estimado') or 30),
                'guia_debriefing': caso.get('guia_debriefing') or '',
                'retroalimentacion_base': caso.get('retroalimentacion_base') or '',
                'instrucciones_ia': caso.get('instrucciones_ia') or '',
                # Un caso que ya trae respuesta correcta, puntaje por alternativa
                # y rubrica no necesita IA: se corrige con aritmetica y palabras
                # clave, igual que el simulador del docente del que salio.
                'ia_habilitada': not bool(caso.get('sin_ia')),
                'estado': estado,
                'fecha_publicacion': timezone.now() if publicar else None,
            },
        )
        return simulacion

    def _cargar_indicadores(self, simulacion, items):
        for item in items:
            IndicadorSimulacion.objects.update_or_create(
                simulacion=simulacion,
                codigo=_requerido(item, 'codigo', 'indicador'),
                defaults={
                    'nombre': item.get('nombre') or item['codigo'],
                    'valor_inicial': _decimal(item.get('inicial', 50)),
                    'valor_minimo': _decimal(item.get('minimo', 0)),
                    'valor_maximo': _decimal(item.get('maximo', 100), '100'),
                    'direccion_optima': item.get('direccion') or IndicadorSimulacion.DIRECCION_ALTO,
                    'unidad': item.get('unidad') or '',
                    'es_critico': bool(item.get('critico')),
                    'activo': True,
                },
            )

    def _cargar_criterios(self, simulacion, items):
        for item in items:
            CriterioEvaluacion.objects.update_or_create(
                simulacion=simulacion,
                nombre=_requerido(item, 'nombre', 'criterio'),
                defaults={
                    'descripcion': item.get('descripcion') or item['nombre'],
                    'peso': _decimal(item.get('peso', 0)),
                    'activo': True,
                },
            )

    def _cargar_matriz(self, simulacion, items):
        for orden, item in enumerate(items, start=1):
            MatrizEvaluacionCaso.objects.update_or_create(
                simulacion=simulacion,
                criterio=_requerido(item, 'criterio', 'matriz'),
                defaults={
                    'peso': _decimal(item.get('peso', 0)),
                    'evalua': item.get('evalua') or '',
                    'orden': orden,
                    'activo': True,
                },
            )

    def _cargar_opciones_caso(self, simulacion, items):
        for orden, item in enumerate(items, start=1):
            OpcionCasoSimulacion.objects.update_or_create(
                simulacion=simulacion,
                nombre=_requerido(item, 'nombre', 'alternativa del caso'),
                defaults={
                    'subtitulo': item.get('subtitulo') or '',
                    'valor_referencia': item.get('valor_referencia') or '',
                    'fortaleza': item.get('fortaleza') or '',
                    'riesgo': item.get('riesgo') or '',
                    'resultados': item.get('resultados') or [],
                    'orden': orden,
                    'activo': True,
                },
            )

    def _cargar_rondas(self, simulacion, items):
        vistas = []
        for indice, item in enumerate(items, start=1):
            numero = int(item.get('numero') or indice)
            ronda, _ = RondaSimulacion.objects.update_or_create(
                simulacion=simulacion,
                numero=numero,
                defaults={
                    'titulo': item['titulo'],
                    'situacion': item['situacion'],
                    'instrucciones': item.get('instrucciones') or '',
                    'datos': item.get('datos') or {},
                    'tipo_respuesta': item.get('tipo_respuesta') or RondaSimulacion.OPCION_UNICA,
                    'campos': item.get('campos') or [],
                    'requiere_justificacion': bool(item.get('requiere_justificacion', True)),
                    'puntaje_maximo': _decimal(item.get('puntaje_maximo', 100), '100'),
                    'respuesta_modelo': item.get('respuesta_modelo') or '',
                    'retroalimentacion': item.get('retroalimentacion') or '',
                    'activo': True,
                },
            )
            vistas.append(ronda.pk)
            self._cargar_opciones_ronda(ronda, item.get('opciones') or [])
            self._cargar_conceptos(simulacion, numero, item.get('conceptos') or [])

        # Recargar la ficha despues de quitarle una ronda no debe dejarla viva.
        RondaSimulacion.objects.filter(
            simulacion=simulacion, activo=True,
        ).exclude(pk__in=vistas).update(activo=False)
        return len(vistas)

    def _cargar_opciones_ronda(self, ronda, items):
        vistas = []
        for orden, item in enumerate(items, start=1):
            opcion, _ = OpcionRondaSimulacion.objects.update_or_create(
                ronda=ronda,
                texto=_requerido(item, 'texto', f'alternativa de la ronda {ronda.numero}'),
                defaults={
                    'descripcion': item.get('descripcion') or '',
                    'puntaje': _decimal(item.get('puntaje', 0)),
                    'retroalimentacion': item.get('retroalimentacion') or '',
                    'impacto': item.get('impacto') or {},
                    'orden': orden,
                    'activo': True,
                },
            )
            vistas.append(opcion.pk)
        OpcionRondaSimulacion.objects.filter(
            ronda=ronda, activo=True,
        ).exclude(pk__in=vistas).update(activo=False)

    def _cargar_conceptos(self, simulacion, numero, items):
        for item in items:
            ConceptoEsperadoRonda.objects.update_or_create(
                simulacion=simulacion,
                numero_ronda=numero,
                nombre=_requerido(item, 'nombre', f'rubrica de la ronda {numero}'),
                defaults={
                    'descripcion': item.get('descripcion') or '',
                    'palabras_clave': item.get('palabras_clave') or item['nombre'],
                    'peso': _decimal(item.get('peso', 0)),
                    'retroalimentacion_si_cumple': item.get('si_cumple') or '',
                    'retroalimentacion_si_falta': item.get('si_falta') or '',
                    'es_critico': bool(item.get('critico')),
                    'activo': True,
                },
            )

    def _cargar_archivos(self, simulacion, items, base):
        vistos = []
        for orden, item in enumerate(items, start=1):
            ronda = None
            if item.get('ronda'):
                ronda = RondaSimulacion.objects.filter(
                    simulacion=simulacion, numero=int(item['ronda']),
                ).first()
            recurso, _ = RecursoSimulacionArchivo.objects.update_or_create(
                simulacion=simulacion,
                nombre=_requerido(item, 'nombre', 'archivo'),
                defaults={
                    'ronda': ronda,
                    'tipo': item.get('tipo') or RecursoSimulacionArchivo.OTRO,
                    'descripcion': item.get('descripcion') or '',
                    'orden': orden,
                    'activo': True,
                },
            )
            for clave, campo in (('ruta', 'archivo'), ('vista_previa', 'vista_previa')):
                origen = item.get(clave)
                if not origen:
                    continue
                camino = (base / origen).resolve()
                if not camino.exists():
                    self.stdout.write(self.style.WARNING(
                        f'    aviso: no encontre {camino}, el caso queda sin ese archivo'
                    ))
                    continue
                guardado = getattr(recurso, campo)
                # Recargar la ficha no debe dejar una copia nueva del mismo
                # Excel en media/ cada vez. Solo se sube si cambio el tamano.
                if guardado and Path(guardado.name).stem.startswith(camino.stem):
                    try:
                        if guardado.size == camino.stat().st_size:
                            continue
                    except (OSError, ValueError):
                        pass
                with camino.open('rb') as manejador:
                    guardado.save(camino.name, File(manejador), save=True)
            vistos.append(recurso.pk)
        return len(vistos)

    def _cargar_juegos(self, simulacion, materia_malla, tema, items):
        """Los juegos de la materia. Si el juego dice `exigir_antes_del_caso`,
        ademas se ata al caso y hace de preparacion previa obligatoria."""
        if not items:
            return 0

        creador = simulacion.usuario_creacion or simulacion.profesor or _algun_admin()
        if not creador:
            self.stdout.write(self.style.WARNING(
                '    aviso: no hay usuario al que atribuir los juegos, se omiten'
            ))
            return 0

        creados = 0
        for orden, item in enumerate(items, start=1):
            motor = _requerido(item, 'motor', 'juego')
            try:
                plugin = get_plugin(motor)
            except PluginError as error:
                raise FichaInvalida(f'juego "{item.get("titulo")}": {error}')

            configuracion = plugin.normalize_config(item.get('configuracion') or {})
            errores = plugin.validate_config(configuracion)
            if errores:
                raise FichaInvalida(
                    f'juego "{item.get("titulo")}": ' + ' '.join(errores)
                )

            titulo = _requerido(item, 'titulo', 'juego')
            existente = ActividadInteractiva.objects.filter(
                materia_malla=materia_malla, titulo=titulo,
            ).order_by('pk').first()
            valores = {
                'tema': tema,
                'simulacion': simulacion if item.get('exigir_antes_del_caso') else None,
                'creador': creador,
                'motor': motor,
                'instrucciones': item.get('instrucciones') or '',
                'configuracion': configuracion,
                'orden': orden,
                'obligatoria': bool(item.get('exigir_antes_del_caso')),
                'publicada': bool(item.get('publicada', True)),
                'activo': True,
            }
            if existente:
                for campo, valor in valores.items():
                    setattr(existente, campo, valor)
                existente.save()
            else:
                ActividadInteractiva.objects.create(
                    materia_malla=materia_malla, titulo=titulo, **valores,
                )
            creados += 1
        return creados
