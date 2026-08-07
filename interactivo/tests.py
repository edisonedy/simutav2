from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from academico.models import Carrera, Malla, Materia, MateriaMalla, NivelMalla
from core.models import PerfilUsuario
from simulador.models import Simulacion, TemaMateria

from .models import ActividadInteractiva, IntentoActividadInteractiva
from .plugins.registry import all_plugins, get_plugin


class MotoresTests(TestCase):
    """Cada motor califica solo. Si un motor nuevo se registra mal, se nota aqui
    antes de que un estudiante se lleve una nota equivocada."""

    def test_todos_los_motores_tienen_codigo_y_nombre(self):
        motores = all_plugins()
        self.assertGreaterEqual(len(motores), 7)
        for motor in motores:
            with self.subTest(motor=motor.codigo):
                self.assertTrue(motor.codigo)
                self.assertTrue(motor.nombre)

    def test_seleccion_unica_acierta_y_falla(self):
        plugin = get_plugin('seleccion_unica')
        config = plugin.normalize_config({'preguntas': [
            {'enunciado': '2+2', 'opciones': '3\n4', 'correcta': 2},
        ]})
        self.assertEqual(plugin.validate_config(config), [])
        pregunta = config['preguntas'][0]
        buena = plugin.grade(config, {'respuestas': {pregunta['id']: pregunta['correcta_id']}})
        mala = plugin.grade(config, {'respuestas': {pregunta['id']: 'otra'}})
        self.assertEqual(buena['porcentaje'], 100)
        self.assertEqual(mala['porcentaje'], 0)

    def test_la_configuracion_publica_no_lleva_la_respuesta(self):
        """Si el correcto viaja al navegador, el juego se gana mirando el HTML."""
        plugin = get_plugin('seleccion_unica')
        config = plugin.normalize_config({'preguntas': [
            {'enunciado': 'x', 'opciones': 'a\nb', 'correcta': 1, 'explicacion': 'porque si'},
        ]})
        publica = plugin.public_config(config)
        self.assertNotIn('correcta_id', publica['preguntas'][0])
        self.assertNotIn('explicacion', publica['preguntas'][0])

    def test_verdadero_falso_sin_responder_no_suma(self):
        plugin = get_plugin('verdadero_falso')
        config = plugin.normalize_config({'preguntas': [
            {'enunciado': 'El cielo es azul', 'correcta': True},
        ]})
        self.assertEqual(plugin.grade(config, {'respuestas': {}})['porcentaje'], 0)

    def test_ordenar_cuenta_las_posiciones_correctas(self):
        plugin = get_plugin('ordenar')
        config = plugin.normalize_config({'elementos': [
            {'texto': 'uno'}, {'texto': 'dos'},
        ]})
        ids = [e['id'] for e in config['elementos']]
        self.assertEqual(plugin.grade(config, {'orden': ids})['porcentaje'], 100)
        self.assertEqual(plugin.grade(config, {'orden': list(reversed(ids))})['porcentaje'], 0)

    def test_completar_espacios_ignora_tildes_y_mayusculas(self):
        plugin = get_plugin('completar_espacios')
        config = plugin.normalize_config({'texto': 'La capital es [[Quito]].'})
        espacio = config['respuestas'][0]['id']
        resultado = plugin.grade(config, {'respuestas': {espacio: '  QUÍTO '}})
        self.assertEqual(resultado['porcentaje'], 100)


class _MateriaMixin:
    @classmethod
    def _armar(cls):
        cls.docente = User.objects.create_user('docente_juegos', password='x')
        PerfilUsuario.objects.create(usuario=cls.docente, rol=PerfilUsuario.PROFESOR)
        cls.alumno = User.objects.create_user('alumno_juegos', password='x')
        PerfilUsuario.objects.create(usuario=cls.alumno, rol=PerfilUsuario.ESTUDIANTE)

        carrera = Carrera.objects.create(nombre='Administracion', codigo='ADM')
        cls.malla = Malla.objects.create(carrera=carrera, nombre='Malla', codigo='MJ')
        nivel = NivelMalla.objects.create(malla=cls.malla, numero=1, nombre='Nivel 1')
        materia = Materia.objects.create(codigo='CONTA', nombre='Contabilidad')
        cls.materia_malla = MateriaMalla.objects.create(
            malla=cls.malla, nivel=nivel, materia=materia,
        )
        cls.tema = TemaMateria.objects.create(
            materia_malla=cls.materia_malla, nombre='Asientos contables', orden=1,
        )

    @classmethod
    def _juego(cls, **extra):
        datos = {
            'materia_malla': cls.materia_malla,
            'creador': cls.docente,
            'motor': 'seleccion_unica',
            'titulo': 'Juego de prueba',
            'publicada': True,
            'configuracion': get_plugin('seleccion_unica').normalize_config({
                'preguntas': [{'enunciado': '2+2', 'opciones': '3\n4', 'correcta': 2}],
            }),
        }
        datos.update(extra)
        return ActividadInteractiva.objects.create(**datos)


class JuegosDeLaMateriaTests(_MateriaMixin, TestCase):
    """El juego vive en la materia. El docente crea los que quiera, por tema o
    para toda la materia, y amarrarlo a un caso es opcional."""

    @classmethod
    def setUpTestData(cls):
        cls._armar()

    def test_el_juego_puede_ser_de_un_tema_o_de_toda_la_materia(self):
        suelto = self._juego(titulo='General')
        del_tema = self._juego(titulo='Del tema', tema=self.tema)

        self.assertIsNone(suelto.tema)
        self.assertEqual(del_tema.tema, self.tema)
        self.assertEqual(self.materia_malla.actividades_interactivas.count(), 2)

    def test_el_tema_tiene_que_ser_de_la_misma_materia(self):
        otra_materia = MateriaMalla.objects.create(
            malla=self.malla,
            nivel=self.materia_malla.nivel,
            materia=Materia.objects.create(codigo='FIN', nombre='Finanzas'),
        )
        ajeno = TemaMateria.objects.create(materia_malla=otra_materia, nombre='Ajeno')

        juego = ActividadInteractiva(
            materia_malla=self.materia_malla, creador=self.docente,
            motor='seleccion_unica', titulo='X', tema=ajeno,
        )
        with self.assertRaises(ValidationError):
            juego.clean()

    def test_el_docente_ve_sus_juegos_agrupados_por_tema(self):
        self._juego(titulo='General')
        self._juego(titulo='Del tema', tema=self.tema)
        self.client.force_login(self.docente)

        pagina = self.client.get(reverse('interactivo:lista', args=[self.materia_malla.pk]))

        self.assertEqual(pagina.status_code, 200)
        self.assertContains(pagina, 'Asientos contables')
        self.assertContains(pagina, 'Toda la materia')
        self.assertContains(pagina, 'Del tema')

    def test_el_estudiante_no_ve_los_borradores(self):
        self._juego(titulo='Publicado')
        self._juego(titulo='Borrador', publicada=False)
        self.client.force_login(self.alumno)

        pagina = self.client.get(reverse('interactivo:lista', args=[self.materia_malla.pk]))

        self.assertContains(pagina, 'Publicado')
        self.assertNotContains(pagina, 'Borrador')

    def test_el_estudiante_no_puede_crear_juegos(self):
        self.client.force_login(self.alumno)

        respuesta = self.client.get(reverse('interactivo:crear', args=[self.materia_malla.pk]))

        self.assertEqual(respuesta.status_code, 403)


class JugarTests(_MateriaMixin, TestCase):
    """El servidor califica. Lo que manda el navegador es la respuesta del
    estudiante, nunca la nota."""

    @classmethod
    def setUpTestData(cls):
        cls._armar()
        cls.juego = cls._juego(puntaje_minimo=70)

    def setUp(self):
        self.client.force_login(self.alumno)

    def _jugar(self):
        return self.client.get(reverse('interactivo:jugar', args=[self.juego.pk]))

    def test_entrar_abre_un_intento(self):
        respuesta = self._jugar()

        self.assertEqual(respuesta.status_code, 200)
        intento = IntentoActividadInteractiva.objects.get(estudiante=self.alumno)
        self.assertEqual(intento.numero_intento, 1)
        self.assertEqual(intento.estado, IntentoActividadInteractiva.EN_PROCESO)

    def test_volver_a_entrar_no_abre_otro_intento(self):
        self._jugar()
        self._jugar()

        self.assertEqual(IntentoActividadInteractiva.objects.count(), 1)

    def test_responder_bien_aprueba(self):
        self._jugar()
        intento = IntentoActividadInteractiva.objects.get(estudiante=self.alumno)
        pregunta = self.juego.configuracion['preguntas'][0]

        respuesta = self.client.post(
            reverse('interactivo:finalizar', args=[intento.pk]),
            data={'respuesta': {'respuestas': {pregunta['id']: pregunta['correcta_id']}}},
            content_type='application/json',
        )

        self.assertTrue(respuesta.json()['ok'], respuesta.json())
        intento.refresh_from_db()
        self.assertTrue(intento.aprobado)
        self.assertEqual(intento.porcentaje, 100)
        self.assertEqual(intento.estado, IntentoActividadInteractiva.APROBADO)

    def test_responder_mal_no_aprueba(self):
        self._jugar()
        intento = IntentoActividadInteractiva.objects.get(estudiante=self.alumno)
        pregunta = self.juego.configuracion['preguntas'][0]

        self.client.post(
            reverse('interactivo:finalizar', args=[intento.pk]),
            data={'respuesta': {'respuestas': {pregunta['id']: 'nada'}}},
            content_type='application/json',
        )

        intento.refresh_from_db()
        self.assertFalse(intento.aprobado)
        self.assertEqual(intento.estado, IntentoActividadInteractiva.NO_APROBADO)

    def test_un_intento_ya_cerrado_no_se_vuelve_a_calificar(self):
        self._jugar()
        intento = IntentoActividadInteractiva.objects.get(estudiante=self.alumno)
        url = reverse('interactivo:finalizar', args=[intento.pk])
        cuerpo = {'respuesta': {'respuestas': {}}}
        self.client.post(url, data=cuerpo, content_type='application/json')

        repetido = self.client.post(url, data=cuerpo, content_type='application/json')

        self.assertEqual(repetido.status_code, 409)

    def test_no_se_puede_jugar_un_borrador_ajeno(self):
        borrador = self._juego(titulo='Borrador', publicada=False)

        respuesta = self.client.get(reverse('interactivo:jugar', args=[borrador.pk]))

        self.assertEqual(respuesta.status_code, 403)


class CandadoAntesDelCasoTests(_MateriaMixin, TestCase):
    """Un juego obligatorio amarrado a un caso hay que aprobarlo antes de entrar."""

    @classmethod
    def setUpTestData(cls):
        cls._armar()
        cls.caso = Simulacion.objects.create(
            materia_malla=cls.materia_malla, titulo='Caso de costos', maximo_decisiones=1,
        )
        cls.juego = cls._juego(simulacion=cls.caso, obligatoria=True)

    def test_con_el_juego_pendiente_el_caso_no_arranca(self):
        from interactivo.services import actividades_pendientes, puede_iniciar_simulacion

        self.assertEqual(actividades_pendientes(self.caso, self.alumno), [self.juego])
        self.assertFalse(puede_iniciar_simulacion(self.caso, self.alumno))

    def test_aprobado_el_juego_el_caso_se_abre(self):
        from interactivo.services import puede_iniciar_simulacion

        IntentoActividadInteractiva.objects.create(
            actividad=self.juego, estudiante=self.alumno,
            completado=True, aprobado=True, porcentaje=100,
        )

        self.assertTrue(puede_iniciar_simulacion(self.caso, self.alumno))

    def test_un_juego_opcional_no_bloquea(self):
        from interactivo.services import puede_iniciar_simulacion

        self.juego.obligatoria = False
        self.juego.save()

        self.assertTrue(puede_iniciar_simulacion(self.caso, self.alumno))

    def test_el_caso_tiene_que_ser_de_la_misma_materia(self):
        otra_materia = MateriaMalla.objects.create(
            malla=self.malla,
            nivel=self.materia_malla.nivel,
            materia=Materia.objects.create(codigo='MKT', nombre='Marketing'),
        )
        caso_ajeno = Simulacion.objects.create(
            materia_malla=otra_materia, titulo='Ajeno', maximo_decisiones=1,
        )

        juego = ActividadInteractiva(
            materia_malla=self.materia_malla, creador=self.docente,
            motor='seleccion_unica', titulo='X', simulacion=caso_ajeno,
        )
        with self.assertRaises(ValidationError):
            juego.clean()
