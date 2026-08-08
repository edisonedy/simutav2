"""El motor configurable: rondas como datos, no como codigo.

Antes, meter un caso nuevo era escribir un comando de Python por caso. Estos
tests fijan lo contrario: una ficha JSON entra completa, se puede volver a
cargar sin duplicar nada, y lo que el docente configura llega tal cual al motor
que juega el estudiante.
"""

import json
import shutil
import tempfile
from datetime import date
from pathlib import Path

from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse

from academico.models import (
    Carrera,
    InscripcionMalla,
    Malla,
    MallaPeriodo,
    Materia,
    MateriaMalla,
    NivelMalla,
    PeriodoAcademico,
)
from core.models import PerfilUsuario
from interactivo.models import ActividadInteractiva
from simulador.models import (
    AccionSugeridaSimulacion,
    ActividadMateria,
    ConceptoEsperadoRonda,
    IntentoSimulacion,
    OpcionRondaSimulacion,
    RecursoSimulacionArchivo,
    RondaSimulacion,
    Simulacion,
)
from simulador.services import rondas as servicio_rondas


FICHA_MINIMA = {
    'materia': {
        'codigo': 'FIN-1',
        'nombre': 'Administracion Financiera',
        'malla_codigo': 'M-TEST',
        'carrera_codigo': 'C-TEST',
        'carrera': 'Administracion',
        'malla': 'Malla de prueba',
        'nivel': 3,
    },
    'tema': 'Flujos de caja',
    'caso': {
        'titulo': 'Caso de prueba',
        'modo': 'CASO_INDEPENDIENTE',
        'contexto': 'La empresa necesita saber cuanto efectivo genera.',
        'objetivo': 'Calcular el flujo.',
        'tiempo_estimado': 20,
    },
    'criterios': [
        {'nombre': 'Exactitud', 'peso': 60, 'descripcion': 'El numero coincide.'},
        {'nombre': 'Justificacion', 'peso': 40, 'descripcion': 'Explica el ajuste.'},
    ],
    'rondas': [
        {
            'numero': 1,
            'titulo': 'Calcular el EBIT',
            'situacion': 'Con el estado de resultados, identifica el EBIT.',
            'tipo_respuesta': 'NUMERICA',
            'campos': [
                {'clave': 'ebit', 'etiqueta': 'EBIT', 'tipo': 'numero',
                 'objetivo': 1225000, 'tolerancia': 1, 'unidad': 'USD'},
            ],
            'conceptos': [
                {'nombre': 'Excluye intereses', 'palabras_clave': 'intereses, financiamiento',
                 'peso': 100},
            ],
            'respuesta_modelo': 'EBIT = 1.225.000.',
        },
        {
            'numero': 2,
            'titulo': 'Elegir el tratamiento',
            'situacion': 'Que se hace con las depreciaciones?',
            'tipo_respuesta': 'OPCION_UNICA',
            'opciones': [
                {'texto': 'Sumarlas de vuelta', 'puntaje': 100,
                 'retroalimentacion': 'Correcto: no salieron de caja.'},
                {'texto': 'Dejarlas fuera', 'puntaje': 0,
                 'retroalimentacion': 'No: redujeron la utilidad sin salir de caja.'},
            ],
        },
    ],
}


def _escribir(directorio, nombre, datos):
    ruta = Path(directorio) / nombre
    ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding='utf-8')
    return str(ruta)


class CargarCasoDesdeFichaTests(TestCase):
    """Un caso entra como archivo de datos, sin escribir Python."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user('jefa_casos', password='x')
        PerfilUsuario.objects.create(usuario=cls.admin, rol=PerfilUsuario.ADMIN)

    def setUp(self):
        self.carpeta = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.carpeta, True)

    def _cargar(self, datos=None, **opciones):
        ficha = _escribir(self.carpeta, 'caso.json', datos or FICHA_MINIMA)
        call_command('cargar_caso', ficha, **opciones)
        return ficha

    def test_la_ficha_crea_el_caso_completo(self):
        self._cargar(publicar=True)

        simulacion = Simulacion.objects.get(titulo='Caso de prueba')
        self.assertEqual(simulacion.modo_ejecucion, Simulacion.MODO_CASO_INDEPENDIENTE)
        self.assertEqual(simulacion.estado, Simulacion.PUBLICADA)
        self.assertEqual(simulacion.materia_malla.materia.codigo, 'FIN-1')
        self.assertEqual(simulacion.tema_materia.nombre, 'Flujos de caja')
        self.assertEqual(simulacion.rondas.filter(activo=True).count(), 2)
        self.assertEqual(simulacion.criterios.filter(activo=True).count(), 2)

        primera = simulacion.rondas.get(numero=1)
        self.assertEqual(primera.tipo_respuesta, RondaSimulacion.NUMERICA)
        self.assertEqual(primera.campos[0]['objetivo'], 1225000)
        self.assertEqual(
            ConceptoEsperadoRonda.objects.filter(
                simulacion=simulacion, numero_ronda=1, activo=True,
            ).count(),
            1,
        )

        segunda = simulacion.rondas.get(numero=2)
        self.assertEqual([o.texto for o in segunda.opciones.order_by('orden')],
                         ['Sumarlas de vuelta', 'Dejarlas fuera'])

    def test_sin_publicar_el_caso_queda_en_borrador(self):
        self._cargar()
        self.assertEqual(
            Simulacion.objects.get(titulo='Caso de prueba').estado, Simulacion.BORRADOR,
        )

    def test_volver_a_cargar_actualiza_y_no_duplica(self):
        """Es lo que permite corregir la ficha y recargar sin ensuciar la base."""
        self._cargar(publicar=True)
        datos = json.loads(json.dumps(FICHA_MINIMA))
        datos['rondas'][0]['titulo'] = 'Calcular el EBIT (corregido)'
        self._cargar(datos, publicar=True)

        self.assertEqual(Simulacion.objects.filter(titulo='Caso de prueba').count(), 1)
        simulacion = Simulacion.objects.get(titulo='Caso de prueba')
        self.assertEqual(simulacion.rondas.filter(activo=True).count(), 2)
        self.assertEqual(
            simulacion.rondas.get(numero=1).titulo, 'Calcular el EBIT (corregido)',
        )

    def test_quitar_una_ronda_de_la_ficha_la_desactiva(self):
        self._cargar(publicar=True)
        datos = json.loads(json.dumps(FICHA_MINIMA))
        datos['rondas'] = datos['rondas'][:1]
        self._cargar(datos, publicar=True)

        simulacion = Simulacion.objects.get(titulo='Caso de prueba')
        self.assertEqual(simulacion.rondas.filter(activo=True).count(), 1)
        self.assertEqual(simulacion.maximo_decisiones, 1)
        # La ronda 2 no se borra: se archiva, para no perder los intentos viejos.
        self.assertTrue(RondaSimulacion.objects.filter(
            simulacion=simulacion, numero=2, activo=False,
        ).exists())

    def test_dry_run_no_escribe_nada(self):
        self._cargar(dry_run=True)
        self.assertFalse(Simulacion.objects.filter(titulo='Caso de prueba').exists())

    def test_una_ronda_de_eleccion_sin_alternativas_es_un_error_util(self):
        datos = json.loads(json.dumps(FICHA_MINIMA))
        datos['rondas'][1].pop('opciones')
        with self.assertRaises(CommandError) as fallo:
            self._cargar(datos)
        self.assertIn('no trae alternativas', str(fallo.exception))

    def test_una_ronda_numerica_sin_campos_es_un_error_util(self):
        datos = json.loads(json.dumps(FICHA_MINIMA))
        datos['rondas'][0].pop('campos')
        with self.assertRaises(CommandError) as fallo:
            self._cargar(datos)
        self.assertIn('falta "campos"', str(fallo.exception))

    def test_un_tipo_de_respuesta_inventado_no_pasa(self):
        datos = json.loads(json.dumps(FICHA_MINIMA))
        datos['rondas'][0]['tipo_respuesta'] = 'ADIVINANZA'
        with self.assertRaises(CommandError) as fallo:
            self._cargar(datos)
        self.assertIn('no existe', str(fallo.exception))

    def test_dos_rondas_con_el_mismo_numero_no_pasan(self):
        datos = json.loads(json.dumps(FICHA_MINIMA))
        datos['rondas'][1]['numero'] = 1
        with self.assertRaises(CommandError) as fallo:
            self._cargar(datos)
        self.assertIn('mismo numero', str(fallo.exception))

    def test_carga_una_carpeta_entera(self):
        _escribir(self.carpeta, 'a.json', FICHA_MINIMA)
        otro = json.loads(json.dumps(FICHA_MINIMA))
        otro['caso']['titulo'] = 'Segundo caso'
        _escribir(self.carpeta, 'b.json', otro)

        call_command('cargar_caso', self.carpeta, publicar=True)
        self.assertEqual(Simulacion.objects.count(), 2)

    def test_la_ficha_puede_traer_juegos_de_la_materia(self):
        datos = json.loads(json.dumps(FICHA_MINIMA))
        datos['juegos'] = [{
            'motor': 'ordenar',
            'titulo': 'Ordena los pasos del FCFF',
            'exigir_antes_del_caso': True,
            'configuracion': {'elementos': [{'texto': 'EBIT'}, {'texto': 'NOPAT'}]},
        }]
        self._cargar(datos, publicar=True)

        juego = ActividadInteractiva.objects.get(titulo='Ordena los pasos del FCFF')
        self.assertEqual(juego.motor, 'ordenar')
        self.assertTrue(juego.obligatoria)
        self.assertEqual(juego.simulacion.titulo, 'Caso de prueba')
        # El juego cuelga de la misma materia y del mismo tema que el caso.
        self.assertEqual(juego.materia_malla, juego.simulacion.materia_malla)
        self.assertEqual(juego.tema.nombre, 'Flujos de caja')

    def test_un_juego_mal_configurado_no_pasa(self):
        datos = json.loads(json.dumps(FICHA_MINIMA))
        datos['juegos'] = [{
            'motor': 'ordenar',
            'titulo': 'Juego roto',
            'configuracion': {'elementos': [{'texto': 'Unico'}]},
        }]
        with self.assertRaises(CommandError) as fallo:
            self._cargar(datos)
        self.assertIn('al menos dos elementos', str(fallo.exception))

    def test_un_motor_que_no_existe_no_pasa(self):
        datos = json.loads(json.dumps(FICHA_MINIMA))
        datos['juegos'] = [{'motor': 'telepatia', 'titulo': 'X', 'configuracion': {}}]
        with self.assertRaises(CommandError) as fallo:
            self._cargar(datos)
        self.assertIn('telepatia', str(fallo.exception))


class MaterializarRondasTests(TestCase):
    """Lo que el docente configura tiene que llegar tal cual al motor de juego,
    que sigue leyendo `parametros['rondas']` y `AccionSugeridaSimulacion`."""

    @classmethod
    def setUpTestData(cls):
        carrera = Carrera.objects.create(nombre='Administracion', codigo='ADM-R')
        malla = Malla.objects.create(carrera=carrera, nombre='Malla', codigo='MR')
        nivel = NivelMalla.objects.create(malla=malla, numero=1, nombre='Nivel 1')
        materia = Materia.objects.create(codigo='MR-1', nombre='Finanzas')
        cls.materia_malla = MateriaMalla.objects.create(
            malla=malla, nivel=nivel, materia=materia,
        )

    def _caso(self, modo=Simulacion.MODO_CASO_INDEPENDIENTE):
        return Simulacion.objects.create(
            materia_malla=self.materia_malla,
            titulo=f'Caso {modo}',
            modo_ejecucion=modo,
            maximo_decisiones=1,
        )

    def test_las_rondas_llegan_al_motor_con_su_configuracion(self):
        caso = self._caso()
        RondaSimulacion.objects.create(
            simulacion=caso, numero=1, titulo='Diagnostico',
            situacion='Que esta pasando?', instrucciones='Se breve.',
            tipo_respuesta=RondaSimulacion.TEXTO, requiere_justificacion=False,
        )
        RondaSimulacion.objects.create(
            simulacion=caso, numero=2, titulo='Decision',
            situacion='Que haces?', tipo_respuesta=RondaSimulacion.OPCION_UNICA,
        )

        total, _ = servicio_rondas.materializar(caso)
        caso.refresh_from_db()

        self.assertEqual(total, 2)
        self.assertEqual(caso.maximo_decisiones, 2)
        rondas = caso.parametros['rondas']
        self.assertEqual([r['numero'] for r in rondas], [1, 2])
        self.assertEqual(rondas[0]['titulo'], 'Diagnostico')
        self.assertEqual(rondas[0]['proposito'], 'Se breve.')
        # Solo texto -> el motor pide escribir; con alternativas y justificacion, hibrido.
        self.assertEqual(rondas[0]['modo'], 'escribir')
        self.assertEqual(rondas[1]['modo'], 'hibrido')

    def test_las_alternativas_se_ofrecen_en_su_ronda(self):
        caso = self._caso()
        ronda = RondaSimulacion.objects.create(
            simulacion=caso, numero=1, titulo='Elegir proveedor',
            situacion='Tres ofertas sobre la mesa.',
            tipo_respuesta=RondaSimulacion.OPCION_UNICA,
        )
        OpcionRondaSimulacion.objects.create(ronda=ronda, texto='Proveedor A', puntaje=100, orden=1)
        OpcionRondaSimulacion.objects.create(ronda=ronda, texto='Proveedor B', puntaje=20, orden=2)

        _, alternativas = servicio_rondas.materializar(caso)

        self.assertEqual(alternativas, 2)
        acciones = AccionSugeridaSimulacion.objects.filter(simulacion=caso, activo=True)
        self.assertEqual(acciones.count(), 2)
        self.assertEqual({a.numero_ronda for a in acciones}, {1})

    def test_en_decisiones_independientes_la_opcion_no_arrastra_impacto(self):
        """Es lo que separa el caso independiente de la simulacion encadenada:
        lo que el alumno decidio en la ronda 1 no debe mover la ronda 2."""
        caso = self._caso(Simulacion.MODO_CASO_INDEPENDIENTE)
        ronda = RondaSimulacion.objects.create(
            simulacion=caso, numero=1, titulo='Decidir', situacion='...',
            tipo_respuesta=RondaSimulacion.OPCION_UNICA,
        )
        OpcionRondaSimulacion.objects.create(
            ronda=ronda, texto='Invertir', puntaje=100, impacto={'caja': -500},
        )

        servicio_rondas.materializar(caso)

        accion = AccionSugeridaSimulacion.objects.get(simulacion=caso, texto='Invertir')
        self.assertEqual(accion.impacto_base, {})

    def test_en_simulacion_encadenada_el_impacto_si_se_aplica(self):
        caso = self._caso(Simulacion.MODO_SIMULACION_ENCADENADA)
        ronda = RondaSimulacion.objects.create(
            simulacion=caso, numero=1, titulo='Decidir', situacion='...',
            tipo_respuesta=RondaSimulacion.OPCION_UNICA,
        )
        OpcionRondaSimulacion.objects.create(
            ronda=ronda, texto='Invertir', puntaje=100, impacto={'caja': -500},
        )

        servicio_rondas.materializar(caso)

        accion = AccionSugeridaSimulacion.objects.get(simulacion=caso, texto='Invertir')
        self.assertEqual(accion.impacto_base, {'caja': -500})

    def test_desactivar_una_ronda_retira_sus_alternativas(self):
        caso = self._caso()
        ronda = RondaSimulacion.objects.create(
            simulacion=caso, numero=1, titulo='Decidir', situacion='...',
            tipo_respuesta=RondaSimulacion.OPCION_UNICA,
        )
        OpcionRondaSimulacion.objects.create(ronda=ronda, texto='Vieja', puntaje=50)
        servicio_rondas.materializar(caso)

        OpcionRondaSimulacion.objects.filter(ronda=ronda).update(activo=False)
        OpcionRondaSimulacion.objects.create(ronda=ronda, texto='Nueva', puntaje=90)
        servicio_rondas.materializar(caso)

        vigentes = AccionSugeridaSimulacion.objects.filter(simulacion=caso, activo=True)
        self.assertEqual([a.texto for a in vigentes], ['Nueva'])

    def test_un_caso_sin_rondas_configuradas_no_toca_nada(self):
        """Los casos viejos siguen viviendo en parametros['rondas']: si nadie
        configuro rondas, el materializador no los pisa."""
        caso = self._caso()
        caso.parametros = {'rondas': [{'numero': 1, 'titulo': 'Heredada'}]}
        caso.save(update_fields=['parametros'])

        self.assertEqual(servicio_rondas.materializar(caso), (0, 0))
        caso.refresh_from_db()
        self.assertEqual(caso.parametros['rondas'][0]['titulo'], 'Heredada')

    def test_un_archivo_no_puede_colgarse_de_la_ronda_de_otro_caso(self):
        from django.core.exceptions import ValidationError

        caso = self._caso()
        otro = Simulacion.objects.create(
            materia_malla=self.materia_malla, titulo='Otro caso', maximo_decisiones=1,
        )
        ronda_ajena = RondaSimulacion.objects.create(
            simulacion=otro, numero=1, titulo='Ajena', situacion='...',
        )
        archivo = RecursoSimulacionArchivo(
            simulacion=caso, ronda=ronda_ajena, nombre='Excel', tipo='EXCEL',
        )
        with self.assertRaises(ValidationError):
            archivo.full_clean()


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class PantallaDeMateriaTests(TestCase):
    """El estudiante ve dos bloques distintos: jugar para aprender y practicar
    para decidir. Mezclados, un memoria parecia lo mismo que un caso de rondas."""

    @classmethod
    def setUpTestData(cls):
        cls.alumno = User.objects.create_user('alumna_panel', password='x')
        PerfilUsuario.objects.create(usuario=cls.alumno, rol=PerfilUsuario.ESTUDIANTE)

        carrera = Carrera.objects.create(nombre='Administracion', codigo='ADM-P')
        cls.malla = Malla.objects.create(carrera=carrera, nombre='Malla', codigo='MP')
        nivel = NivelMalla.objects.create(malla=cls.malla, numero=1, nombre='Nivel 1')
        materia = Materia.objects.create(codigo='MP-1', nombre='Finanzas')
        cls.materia_malla = MateriaMalla.objects.create(
            malla=cls.malla, nivel=nivel, materia=materia,
        )
        periodo = PeriodoAcademico.objects.create(
            nombre='2026-1', fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 6, 30),
        )
        InscripcionMalla.objects.create(
            estudiante=cls.alumno,
            malla_periodo=MallaPeriodo.abrir(cls.malla, periodo),
        )

        cls.caso = Simulacion.objects.create(
            materia_malla=cls.materia_malla,
            titulo='Caso de flujo de caja',
            estado=Simulacion.PUBLICADA,
            maximo_decisiones=3,
            modo_ejecucion=Simulacion.MODO_CASO_INDEPENDIENTE,
        )
        cls.borrador = Simulacion.objects.create(
            materia_malla=cls.materia_malla,
            titulo='Caso todavia en borrador',
            estado=Simulacion.BORRADOR,
            maximo_decisiones=1,
        )
        cls.juego = ActividadInteractiva.objects.create(
            materia_malla=cls.materia_malla,
            creador=cls.alumno,
            motor='ordenar',
            titulo='Ordena los pasos',
            configuracion={'elementos': []},
            publicada=True,
        )
        ActividadInteractiva.objects.create(
            materia_malla=cls.materia_malla,
            creador=cls.alumno,
            motor='memoria',
            titulo='Memoria sin publicar',
            configuracion={'pares': []},
            publicada=False,
        )
        cls.trabajo = ActividadMateria.objects.create(
            materia_malla=cls.materia_malla,
            categoria=ActividadMateria.EVALUACION,
            tipo=ActividadMateria.GUIA_APE,
            titulo='Guia APE de estados financieros',
        )

    def setUp(self):
        self.client.force_login(self.alumno)

    def _pagina(self):
        return self.client.get(reverse('alu_simulaciones'), {'malla': self.malla.pk})

    def test_los_dos_bloques_aparecen_separados(self):
        html = self._pagina().content.decode()
        self.assertIn('Juegos', html)
        self.assertIn('Practicas reales', html)

    def test_el_juego_publicado_esta_en_el_bloque_de_juegos(self):
        materia = self._pagina().context['niveles'][0]['materias'][0]
        self.assertEqual(
            [j.titulo for j in materia.juegos_disponibles], ['Ordena los pasos'],
        )

    def test_el_caso_y_la_guia_estan_en_practicas(self):
        materia = self._pagina().context['niveles'][0]['materias'][0]
        self.assertEqual(
            [s.titulo for s in materia.simulaciones_disponibles], ['Caso de flujo de caja'],
        )
        self.assertEqual(
            [t.titulo for t in materia.trabajos_disponibles],
            ['Guia APE de estados financieros'],
        )
        self.assertEqual(materia.total_practicas, 2)

    def test_un_caso_en_borrador_no_se_le_muestra_al_estudiante(self):
        materia = self._pagina().context['niveles'][0]['materias'][0]
        titulos = [s.titulo for s in materia.simulaciones_disponibles]
        self.assertNotIn('Caso todavia en borrador', titulos)

    def test_los_contadores_del_encabezado_separan_juegos_de_casos(self):
        datos = self._pagina().context
        self.assertEqual(datos['total_juegos'], 1)
        self.assertEqual(datos['total_simulaciones'], 1)


class ContenidoPorMateriaOPorTemaTests(TestCase):
    """La pregunta de fondo: juegos y casos van en la materia o en el tema?

    Los dos. El tema es opcional: sirve para agrupar cuando la materia tiene
    varias unidades, y se deja vacio cuando el contenido abarca toda la materia.
    Lo que no se admite es colgar contenido de un tema de OTRA materia.
    """

    @classmethod
    def setUpTestData(cls):
        from simulador.models import TemaMateria

        carrera = Carrera.objects.create(nombre='Administracion', codigo='ADM-T')
        malla = Malla.objects.create(carrera=carrera, nombre='Malla', codigo='MT')
        nivel = NivelMalla.objects.create(malla=malla, numero=1, nombre='Nivel 1')
        cls.finanzas = MateriaMalla.objects.create(
            malla=malla, nivel=nivel,
            materia=Materia.objects.create(codigo='MT-1', nombre='Finanzas'),
        )
        cls.marketing = MateriaMalla.objects.create(
            malla=malla, nivel=nivel,
            materia=Materia.objects.create(codigo='MT-2', nombre='Marketing'),
        )
        cls.tema_finanzas = TemaMateria.objects.create(
            materia_malla=cls.finanzas, nombre='Flujos de caja',
        )
        cls.usuario = User.objects.create_user('docente_temas', password='x')

    def test_el_caso_puede_ir_suelto_en_la_materia(self):
        caso = Simulacion(
            materia_malla=self.finanzas, titulo='Caso general', maximo_decisiones=1,
        )
        caso.full_clean()

    def test_el_caso_puede_ir_colgado_de_un_tema(self):
        caso = Simulacion(
            materia_malla=self.finanzas, tema_materia=self.tema_finanzas,
            titulo='Caso del tema', maximo_decisiones=1,
        )
        caso.full_clean()

    def test_el_caso_no_puede_usar_el_tema_de_otra_materia(self):
        from django.core.exceptions import ValidationError

        caso = Simulacion(
            materia_malla=self.marketing, tema_materia=self.tema_finanzas,
            titulo='Caso cruzado', maximo_decisiones=1,
        )
        with self.assertRaises(ValidationError):
            caso.full_clean()

    def test_el_juego_no_puede_usar_el_tema_de_otra_materia(self):
        from django.core.exceptions import ValidationError

        juego = ActividadInteractiva(
            materia_malla=self.marketing, tema=self.tema_finanzas,
            creador=self.usuario, motor='memoria', titulo='Cruzado',
        )
        with self.assertRaises(ValidationError):
            juego.full_clean()

    def test_el_trabajo_no_puede_usar_el_tema_de_otra_materia(self):
        from django.core.exceptions import ValidationError

        trabajo = ActividadMateria(
            materia_malla=self.marketing, tema=self.tema_finanzas,
            categoria=ActividadMateria.EVALUACION, tipo=ActividadMateria.GUIA_APE,
            titulo='Cruzado',
        )
        with self.assertRaises(ValidationError):
            trabajo.full_clean()


class SinIATests(TestCase):
    """Los simuladores del docente no usan IA: traen respuesta correcta, puntaje
    por alternativa y rubrica. Con `ia_habilitada=False` el motor no debe
    siquiera llamar al proveedor, y elegir mal no puede valer lo mismo que
    elegir bien."""

    @classmethod
    def setUpTestData(cls):
        from simulador.models import ConceptoEsperadoRonda

        carrera = Carrera.objects.create(nombre='Administracion', codigo='ADM-S')
        malla = Malla.objects.create(carrera=carrera, nombre='Malla', codigo='MS')
        nivel = NivelMalla.objects.create(malla=malla, numero=1, nombre='Nivel 1')
        cls.materia_malla = MateriaMalla.objects.create(
            malla=malla, nivel=nivel,
            materia=Materia.objects.create(codigo='MS-1', nombre='Gerencia'),
        )
        cls.alumno = User.objects.create_user('alumno_sin_ia', password='x')
        PerfilUsuario.objects.create(usuario=cls.alumno, rol=PerfilUsuario.ESTUDIANTE)

        cls.caso = Simulacion.objects.create(
            materia_malla=cls.materia_malla,
            titulo='Caso sin IA',
            estado=Simulacion.PUBLICADA,
            modo_ejecucion=Simulacion.MODO_CASO_INDEPENDIENTE,
            tipo_simulacion=Simulacion.TIPO_CON_IA_DINAMICA,
            ia_habilitada=False,
            maximo_decisiones=1,
        )
        ronda = RondaSimulacion.objects.create(
            simulacion=cls.caso, numero=1, titulo='Elegir proveedor',
            situacion='Tres ofertas sobre la mesa.',
            tipo_respuesta=RondaSimulacion.OPCION_UNICA,
            requiere_justificacion=True,
        )
        OpcionRondaSimulacion.objects.create(
            ronda=ronda, texto='Proveedor A', puntaje=100, orden=1,
            retroalimentacion='Correcto: gana por equilibrio integral.',
        )
        OpcionRondaSimulacion.objects.create(
            ronda=ronda, texto='Proveedor B', puntaje=0, orden=2,
            retroalimentacion='El mas barato sin soporte sale caro.',
        )
        ConceptoEsperadoRonda.objects.create(
            simulacion=cls.caso, numero_ronda=1, nombre='Usa varios criterios',
            palabras_clave='experiencia, calidad, soporte', peso=100,
        )
        servicio_rondas.materializar(cls.caso)

    def _jugar(self, texto_opcion, justificacion='Elijo por experiencia, calidad y soporte del proveedor.'):
        from simulador.generator_service import serializar_configuracion_simulacion
        from simulador.services import (
            construir_estado_inicial, construir_recursos_iniciales, ejecutar_ronda_ia_dinamica,
        )

        intento = IntentoSimulacion.objects.create(
            estudiante=self.alumno, simulacion=self.caso,
            estado_actual=construir_estado_inicial(self.caso),
            recursos_actuales=construir_recursos_iniciales(self.caso),
            configuracion_snapshot=serializar_configuracion_simulacion(self.caso),
        )
        accion = AccionSugeridaSimulacion.objects.get(
            simulacion=self.caso, numero_ronda=1, texto=texto_opcion, activo=True,
        )
        return ejecutar_ronda_ia_dinamica(intento, '', justificacion, accion=accion)

    def test_no_llama_al_proveedor_de_ia(self):
        """La prueba de fuego: si el motor intentara usar IA, esto reventaria."""
        import simulador.ia_service as ia_service

        def prohibido(*args, **kwargs):
            raise AssertionError('El motor llamo a la IA en un caso sin IA.')

        with patch.object(ia_service, 'evaluar_ronda_con_proveedores', prohibido):
            paso = self._jugar('Proveedor A')
        self.assertTrue(paso.es_valido)
        self.assertGreater(float(paso.puntaje_paso), 0)

    def test_elegir_bien_puntua_mas_que_elegir_mal(self):
        bien = self._jugar('Proveedor A')
        mal = self._jugar('Proveedor B')
        self.assertGreater(float(bien.puntaje_paso), float(mal.puntaje_paso))
        self.assertEqual((bien.evaluacion_detalle or {}).get('puntaje_opcion'), 100.0)
        self.assertEqual((mal.evaluacion_detalle or {}).get('puntaje_opcion'), 0.0)

    def test_con_justificacion_se_promedia_opcion_y_rubrica(self):
        paso = self._jugar('Proveedor A')
        detalle = paso.evaluacion_detalle or {}
        esperado = round((detalle['puntaje_opcion'] + detalle['puntaje_rubrica_previo']) / 2, 2)
        self.assertEqual(detalle['puntaje_combinado'], esperado)

    def test_la_retroalimentacion_de_la_opcion_llega_al_estudiante(self):
        paso = self._jugar('Proveedor B')
        self.assertIn('El mas barato sin soporte sale caro.', paso.evaluacion_ia)

    def test_una_alternativa_sin_puntaje_propio_no_altera_la_rubrica(self):
        """Los casos viejos no tienen puntaje por alternativa: siguen igual."""
        AccionSugeridaSimulacion.objects.filter(simulacion=self.caso).update(puntaje=None)
        paso = self._jugar('Proveedor A')
        self.assertIsNone((paso.evaluacion_detalle or {}).get('puntaje_opcion'))

    def test_el_snapshot_del_intento_conserva_el_puntaje(self):
        """Si no viajara en el snapshot, un intento en curso perderia la
        correccion determinista al recargar la configuracion."""
        from simulador.generator_service import serializar_configuracion_simulacion

        snapshot = serializar_configuracion_simulacion(self.caso)
        acciones = {a['texto']: a for a in snapshot['acciones_sugeridas']}
        self.assertEqual(float(acciones['Proveedor A']['puntaje']), 100.0)
        self.assertEqual(float(acciones['Proveedor B']['puntaje']), 0.0)

    def test_la_ficha_marca_el_caso_como_sin_ia(self):
        import json
        import shutil
        import tempfile

        carpeta = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, carpeta, True)
        PerfilUsuario.objects.get_or_create(
            usuario=User.objects.create_user('jefa_sin_ia', password='x'),
            defaults={'rol': PerfilUsuario.ADMIN},
        )
        datos = json.loads(json.dumps(FICHA_MINIMA))
        datos['caso']['titulo'] = 'Caso declarado sin IA'
        datos['caso']['sin_ia'] = True
        ruta = _escribir(carpeta, 'caso.json', datos)
        call_command('cargar_caso', ruta, publicar=True)

        self.assertFalse(
            Simulacion.objects.get(titulo='Caso declarado sin IA').ia_habilitada,
        )


class ProgresoEnLaPantallaDeMateriaTests(TestCase):
    """La pantalla de la materia es un tablero, no un indice.

    Antes era una lista de titulos: el estudiante no sabia que ya habia
    aprobado, que dejo a medias ni cuanto le faltaba. Estos tests fijan que el
    estado real de cada pieza llegue a la plantilla.
    """

    @classmethod
    def setUpTestData(cls):
        from interactivo.models import IntentoActividadInteractiva

        cls.alumno = User.objects.create_user('alumna_progreso', password='x')
        PerfilUsuario.objects.create(usuario=cls.alumno, rol=PerfilUsuario.ESTUDIANTE)

        carrera = Carrera.objects.create(nombre='Administracion', codigo='ADM-G')
        cls.malla = Malla.objects.create(carrera=carrera, nombre='Malla', codigo='MG')
        nivel = NivelMalla.objects.create(malla=cls.malla, numero=1, nombre='Nivel 1')
        cls.materia_malla = MateriaMalla.objects.create(
            malla=cls.malla, nivel=nivel,
            materia=Materia.objects.create(codigo='MG-1', nombre='Gerencia'),
        )
        periodo = PeriodoAcademico.objects.create(
            nombre='2026-1', fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 6, 30),
        )
        InscripcionMalla.objects.create(
            estudiante=cls.alumno,
            malla_periodo=MallaPeriodo.abrir(cls.malla, periodo),
        )

        def caso(titulo):
            return Simulacion.objects.create(
                materia_malla=cls.materia_malla, titulo=titulo,
                estado=Simulacion.PUBLICADA, maximo_decisiones=3,
            )

        cls.caso_hecho = caso('Caso terminado')
        cls.caso_a_medias = caso('Caso a medias')
        cls.caso_nuevo = caso('Caso sin empezar')

        def juego(titulo):
            return ActividadInteractiva.objects.create(
                materia_malla=cls.materia_malla, creador=cls.alumno,
                motor='ordenar', titulo=titulo, configuracion={'elementos': []},
                publicada=True, puntaje_minimo=70,
            )

        cls.juego_aprobado = juego('Juego aprobado')
        cls.juego_reprobado = juego('Juego reprobado')

        IntentoSimulacion.objects.create(
            estudiante=cls.alumno, simulacion=cls.caso_hecho,
            finalizado=True, puntuacion_final=82,
        )
        IntentoSimulacion.objects.create(
            estudiante=cls.alumno, simulacion=cls.caso_a_medias,
            finalizado=False, numero_ronda_actual=2,
        )
        IntentoActividadInteractiva.objects.create(
            actividad=cls.juego_aprobado, estudiante=cls.alumno,
            completado=True, aprobado=True, porcentaje=100,
        )
        IntentoActividadInteractiva.objects.create(
            actividad=cls.juego_reprobado, estudiante=cls.alumno,
            completado=True, aprobado=False, porcentaje=40,
        )

    def setUp(self):
        self.client.force_login(self.alumno)

    def _materia(self):
        respuesta = self.client.get(reverse('alu_simulaciones'), {'malla': self.malla.pk})
        return respuesta, respuesta.context['niveles'][0]['materias'][0]

    def test_marca_lo_aprobado_y_lo_reprobado(self):
        _, materia = self._materia()
        por_titulo = {j.titulo: j for j in materia.juegos_disponibles}
        self.assertTrue(por_titulo['Juego aprobado'].aprobado_por_mi)
        self.assertEqual(por_titulo['Juego aprobado'].mi_porcentaje, 100)
        self.assertFalse(por_titulo['Juego reprobado'].aprobado_por_mi)
        # Jugado pero no aprobado: se ve el intento, no un check.
        self.assertTrue(por_titulo['Juego reprobado'].jugado)

    def test_muestra_la_nota_del_caso_terminado(self):
        _, materia = self._materia()
        por_titulo = {s.titulo: s for s in materia.simulaciones_disponibles}
        self.assertEqual(por_titulo['Caso terminado'].mi_nota, 82.0)
        self.assertIsNone(por_titulo['Caso terminado'].mi_intento_en_curso)

    def test_recuerda_en_que_ronda_quedo(self):
        _, materia = self._materia()
        a_medias = {s.titulo: s for s in materia.simulaciones_disponibles}['Caso a medias']
        self.assertIsNone(a_medias.mi_nota)
        self.assertEqual(a_medias.mi_ronda, 2)

    def test_un_caso_sin_empezar_no_tiene_estado(self):
        _, materia = self._materia()
        nuevo = {s.titulo: s for s in materia.simulaciones_disponibles}['Caso sin empezar']
        self.assertIsNone(nuevo.mi_nota)
        self.assertIsNone(nuevo.mi_intento_en_curso)

    def test_el_avance_cuenta_juegos_aprobados_y_casos_terminados(self):
        """5 piezas (2 juegos + 3 casos), 2 hechas -> 40%."""
        respuesta, materia = self._materia()
        self.assertEqual(materia.piezas_totales, 5)
        self.assertEqual(materia.piezas_hechas, 2)
        self.assertEqual(materia.avance, 40)
        self.assertFalse(materia.completa)
        self.assertEqual(respuesta.context['avance_malla'], 40)

    def test_la_mejor_nota_manda_cuando_hay_varios_intentos(self):
        IntentoSimulacion.objects.create(
            estudiante=self.alumno, simulacion=self.caso_hecho,
            finalizado=True, puntuacion_final=91,
        )
        _, materia = self._materia()
        hecho = {s.titulo: s for s in materia.simulaciones_disponibles}['Caso terminado']
        self.assertEqual(hecho.mi_nota, 91.0)

    def test_el_progreso_de_otro_estudiante_no_se_mezcla(self):
        otra = User.objects.create_user('otra_alumna', password='x')
        PerfilUsuario.objects.create(usuario=otra, rol=PerfilUsuario.ESTUDIANTE)
        InscripcionMalla.objects.create(
            estudiante=otra,
            malla_periodo=MallaPeriodo.objects.get(malla=self.malla),
        )
        self.client.force_login(otra)
        respuesta, materia = self._materia()
        self.assertEqual(materia.piezas_hechas, 0)
        self.assertEqual(respuesta.context['avance_malla'], 0)

    def test_los_juegos_y_los_casos_estan_en_la_misma_pantalla(self):
        """No hay que saltar a otra pantalla para ver los juegos."""
        respuesta, _ = self._materia()
        html = respuesta.content.decode()
        self.assertIn('Juego aprobado', html)
        self.assertIn('Caso terminado', html)


class MedallasPorRondaTests(TestCase):
    """El premio se entrega al cerrar la ronda, no al final del caso.

    Las insignias del perfil solo se veian en "Mi carrera": para cuando
    llegaban, el estudiante ya no recordaba que habia hecho bien.
    """

    @classmethod
    def setUpTestData(cls):
        carrera = Carrera.objects.create(nombre='Administracion', codigo='ADM-M')
        malla = Malla.objects.create(carrera=carrera, nombre='Malla', codigo='MM')
        nivel = NivelMalla.objects.create(malla=malla, numero=1, nombre='Nivel 1')
        cls.materia_malla = MateriaMalla.objects.create(
            malla=malla, nivel=nivel,
            materia=Materia.objects.create(codigo='MM-1', nombre='Gerencia'),
        )
        cls.alumno = User.objects.create_user('alumno_medallas', password='x')
        PerfilUsuario.objects.create(usuario=cls.alumno, rol=PerfilUsuario.ESTUDIANTE)
        cls.caso = Simulacion.objects.create(
            materia_malla=cls.materia_malla, titulo='Caso con medallas',
            estado=Simulacion.PUBLICADA, maximo_decisiones=3,
        )

    def _intento(self, **extra):
        return IntentoSimulacion.objects.create(
            estudiante=self.alumno, simulacion=self.caso, **extra,
        )

    def _paso(self, intento, numero, nota, **extra):
        from simulador.models import PasoSimulacion

        return PasoSimulacion.objects.create(
            intento=intento, numero=numero, es_valido=True,
            situacion_presentada='...', decision_estudiante='...',
            justificacion_estudiante='...', puntaje_paso=nota, **extra,
        )

    def _nombres(self, intento, paso):
        from simulador.alu_simulaciones import _medallas_de_la_ronda

        return [m['nombre'] for m in _medallas_de_la_ronda(intento, paso)]

    def test_una_ronda_excelente_da_certero(self):
        intento = self._intento()
        paso = self._paso(intento, 1, 95)
        self.assertIn('Certero', self._nombres(intento, paso))

    def test_una_ronda_floja_no_da_medallas(self):
        intento = self._intento()
        paso = self._paso(intento, 1, 45)
        self.assertEqual(self._nombres(intento, paso), [])

    def test_mejorar_veinte_puntos_da_remontada(self):
        intento = self._intento()
        self._paso(intento, 1, 50)
        paso = self._paso(intento, 2, 75)
        self.assertIn('Remontada', self._nombres(intento, paso))

    def test_mejorar_poco_no_da_remontada(self):
        intento = self._intento()
        self._paso(intento, 1, 70)
        paso = self._paso(intento, 2, 75)
        self.assertNotIn('Remontada', self._nombres(intento, paso))

    def test_acertar_el_pronostico_da_vidente(self):
        intento = self._intento()
        paso = self._paso(
            intento, 1, 60, pronostico_indicador='caja',
            pronostico_resultado={'estado': 'acierto'},
        )
        self.assertIn('Vidente', self._nombres(intento, paso))

    def test_terminar_el_caso_da_caso_cerrado(self):
        intento = self._intento(finalizado=True)
        paso = self._paso(intento, 3, 80)
        self.assertIn('Caso cerrado', self._nombres(intento, paso))

    def test_un_paso_invalido_no_premia(self):
        from simulador.models import PasoSimulacion

        intento = self._intento()
        paso = PasoSimulacion.objects.create(
            intento=intento, numero=1, es_valido=False,
            situacion_presentada='...', decision_estudiante='',
            justificacion_estudiante='', puntaje_paso=0,
        )
        self.assertEqual(self._nombres(intento, paso), [])

    def test_sin_paso_previo_no_hay_medallas(self):
        self.assertEqual(self._nombres(self._intento(), None), [])

    def test_el_avance_de_la_mision_cuenta_rondas_resueltas(self):
        from simulador.alu_simulaciones import _avance_mision

        intento = self._intento()
        self._paso(intento, 1, 70)
        avance = _avance_mision(intento, 2, 3)
        self.assertEqual(avance['hechas'], 1)
        self.assertEqual(avance['pct'], 33)


class RondaNumericaSeAceptaTests(TestCase):
    """En una ronda de calculo, el numero ES la decision.

    El estudiante escribia el valor en el campo numerico, dejaba vacio el texto
    libre -que esa ronda nunca le pidio- y el motor le rechazaba la jugada con
    "Debe ingresar una decision concreta". Se quedaba atascado en la ronda 1.
    """

    @classmethod
    def setUpTestData(cls):
        cls.alumno = User.objects.create_user('alumna_numerica', password='x')
        PerfilUsuario.objects.create(usuario=cls.alumno, rol=PerfilUsuario.ESTUDIANTE)
        PerfilUsuario.objects.create(
            usuario=User.objects.create_user('jefa_numerica', password='x'),
            rol=PerfilUsuario.ADMIN,
        )

        carrera = Carrera.objects.create(nombre='Administracion', codigo='ADM-N')
        malla = Malla.objects.create(carrera=carrera, nombre='Malla', codigo='MN')
        nivel = NivelMalla.objects.create(malla=malla, numero=1, nombre='Nivel 1')
        cls.materia_malla = MateriaMalla.objects.create(
            malla=malla, nivel=nivel,
            materia=Materia.objects.create(codigo='MN-1', nombre='Finanzas'),
        )
        periodo = PeriodoAcademico.objects.create(
            nombre='2026-1', fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 6, 30),
        )
        InscripcionMalla.objects.create(
            estudiante=cls.alumno, malla_periodo=MallaPeriodo.abrir(malla, periodo),
        )

        cls.caso = Simulacion.objects.create(
            materia_malla=cls.materia_malla, titulo='Caso de calculo',
            estado=Simulacion.PUBLICADA, ia_habilitada=False, maximo_decisiones=2,
            tipo_simulacion=Simulacion.TIPO_CON_IA_DINAMICA,
        )
        for numero, titulo in ((1, 'Calcular el EBIT'), (2, 'Calcular el NOPAT')):
            RondaSimulacion.objects.create(
                simulacion=cls.caso, numero=numero, titulo=titulo,
                situacion='Con el estado de resultados, calcula.',
                tipo_respuesta=RondaSimulacion.NUMERICA,
                requiere_justificacion=True,
                campos=[{
                    'clave': 'valor', 'etiqueta': 'Valor', 'tipo': 'numero',
                    'objetivo': 1225000, 'tolerancia': 1, 'unidad': 'USD',
                    'obligatorio': True,
                }],
            )
            ConceptoEsperadoRonda.objects.create(
                simulacion=cls.caso, numero_ronda=numero, nombre='Explica el ajuste',
                palabras_clave='operativa, intereses', peso=100,
            )
        servicio_rondas.materializar(cls.caso)

    def setUp(self):
        self.client.force_login(self.alumno)

    def _iniciar(self):
        self.client.post(
            reverse('alu_simulaciones') + '?action=iniciar',
            {'simulacion_id': self.caso.pk},
            headers={'x-requested-with': 'XMLHttpRequest'},
        )
        return IntentoSimulacion.objects.filter(
            estudiante=self.alumno, simulacion=self.caso,
        ).latest('fecha_inicio')

    def _responder(self, intento, valor, justificacion, decision=''):
        return self.client.post(
            reverse('alu_simulaciones') + '?action=ejecutar_paso',
            {
                'intento_id': intento.pk, 'valor': valor,
                'decision': decision, 'justificacion': justificacion,
            },
            headers={'x-requested-with': 'XMLHttpRequest'},
        )

    def test_el_numero_solo_ya_es_una_jugada_valida(self):
        intento = self._iniciar()
        self._responder(
            intento, '1225000',
            'La utilidad operativa excluye los intereses porque el EBIT mide la operacion.',
        )
        paso = intento.pasos.latest('numero')
        self.assertTrue(paso.es_valido, paso.evaluacion_ia)
        self.assertGreater(float(paso.puntaje_paso), 0)

    def test_la_decision_registrada_dice_que_valor_puso(self):
        intento = self._iniciar()
        self._responder(
            intento, '1225000',
            'La utilidad operativa excluye los intereses porque el EBIT mide la operacion.',
        )
        paso = intento.pasos.latest('numero')
        self.assertIn('1225000', paso.decision_estudiante)
        self.assertIn('Valor', paso.decision_estudiante)

    def test_avanza_a_la_ronda_siguiente(self):
        intento = self._iniciar()
        self._responder(
            intento, '1225000',
            'La utilidad operativa excluye los intereses porque el EBIT mide la operacion.',
        )
        intento.refresh_from_db()
        self.assertEqual(intento.numero_ronda_actual, 2)

    def test_si_escribe_su_propia_decision_se_respeta(self):
        intento = self._iniciar()
        self._responder(
            intento, '1225000',
            'El EBIT mide la operacion antes de intereses e impuestos.',
            decision='El EBIT del ejercicio es 1.225.000 dolares.',
        )
        paso = intento.pasos.latest('numero')
        self.assertEqual(paso.decision_estudiante, 'El EBIT del ejercicio es 1.225.000 dolares.')

    def test_sin_el_numero_la_ronda_no_pasa(self):
        intento = self._iniciar()
        respuesta = self._responder(intento, '', 'Explico sin poner el valor pedido.')
        self.assertFalse(respuesta.json()['result'])
        self.assertEqual(intento.pasos.count(), 0)


class ModoYMotorCoherentesTests(TestCase):
    """El modo y el motor son la misma decision contada dos veces.

    Se podia guardar "Decisiones independientes" con el motor en arbol, y el
    caso solo fallaba cuando el alumno le daba a jugar: "La simulacion no tiene
    un escenario actual configurado". Debe fallar al configurar, no ante el
    estudiante.
    """

    @classmethod
    def setUpTestData(cls):
        carrera = Carrera.objects.create(nombre='Administracion', codigo='ADM-C')
        malla = Malla.objects.create(carrera=carrera, nombre='Malla', codigo='MC2')
        nivel = NivelMalla.objects.create(malla=malla, numero=1, nombre='Nivel 1')
        cls.materia_malla = MateriaMalla.objects.create(
            malla=malla, nivel=nivel,
            materia=Materia.objects.create(codigo='MC2-1', nombre='Gerencia'),
        )

    def _caso(self, modo, tipo):
        return Simulacion(
            materia_malla=self.materia_malla, titulo='Caso', maximo_decisiones=1,
            modo_ejecucion=modo, tipo_simulacion=tipo,
        )

    def test_independiente_con_motor_de_arbol_no_se_guarda(self):
        from django.core.exceptions import ValidationError

        caso = self._caso(Simulacion.MODO_CASO_INDEPENDIENTE, Simulacion.TIPO_SIN_IA_ARBOL)
        with self.assertRaises(ValidationError) as fallo:
            caso.full_clean()
        self.assertIn('modo_ejecucion', fallo.exception.message_dict)

    def test_arbol_con_motor_dinamico_no_se_guarda(self):
        from django.core.exceptions import ValidationError

        caso = self._caso(Simulacion.MODO_ARBOL_DECISION, Simulacion.TIPO_CON_IA_DINAMICA)
        with self.assertRaises(ValidationError):
            caso.full_clean()

    def test_las_combinaciones_coherentes_pasan(self):
        for modo, tipo in (
            (Simulacion.MODO_CASO_INDEPENDIENTE, Simulacion.TIPO_CON_IA_DINAMICA),
            (Simulacion.MODO_SIMULACION_ENCADENADA, Simulacion.TIPO_CON_IA_DINAMICA),
            (Simulacion.MODO_ARBOL_DECISION, Simulacion.TIPO_SIN_IA_ARBOL),
        ):
            with self.subTest(modo=modo):
                self._caso(modo, tipo).full_clean()

    def test_el_formulario_deduce_el_motor_del_modo(self):
        """El docente elige el modo; el motor no se lo preguntamos dos veces."""
        from simulador.forms import SimulacionForm

        for modo, esperado in (
            (Simulacion.MODO_ARBOL_DECISION, Simulacion.TIPO_SIN_IA_ARBOL),
            (Simulacion.MODO_CASO_INDEPENDIENTE, Simulacion.TIPO_CON_IA_DINAMICA),
            (Simulacion.MODO_SIMULACION_ENCADENADA, Simulacion.TIPO_CON_IA_DINAMICA),
        ):
            with self.subTest(modo=modo):
                form = SimulacionForm({
                    'materia_malla': self.materia_malla.pk,
                    'titulo': 'Caso desde el formulario',
                    'modo_ejecucion': modo,
                    # A proposito al reves de lo que corresponde: el form manda.
                    'tipo_simulacion': (
                        Simulacion.TIPO_CON_IA_DINAMICA
                        if modo == Simulacion.MODO_ARBOL_DECISION
                        else Simulacion.TIPO_SIN_IA_ARBOL
                    ),
                    'nivel_dificultad': Simulacion.DIFICULTAD_MEDIA,
                    'maximo_decisiones': 1, 'tiempo_estimado': 20,
                    'peso_resultado': 30, 'peso_rubrica_decision': 30,
                    'bonus_pronostico': 0, 'bonus_reflexion': 0, 'bonus_adaptacion': 0,
                    'nivel_ayuda_ia': Simulacion.AYUDA_MEDIA,
                    'activo': 'on',
                })
                self.assertTrue(form.is_valid(), form.errors)
                self.assertEqual(form.cleaned_data['tipo_simulacion'], esperado)
