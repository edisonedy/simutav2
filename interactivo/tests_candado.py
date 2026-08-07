"""El candado visto desde la pantalla del estudiante.

Los tests de services ya prueban la regla; estos prueban que la regla de verdad
BLOQUEA la vista, que es lo que estaba suelto: la funcion existia y nadie la
llamaba.
"""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from academico.models import (
    Carrera,
    InscripcionMalla,
    Malla,
    Materia,
    MateriaMalla,
    NivelMalla,
    PeriodoAcademico,
)
from core.models import PerfilUsuario
from datetime import date

from interactivo.models import ActividadInteractiva, IntentoActividadInteractiva
from interactivo.plugins.registry import get_plugin
from simulador.models import IntentoSimulacion, Simulacion


class CandadoEnLaVistaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.docente = User.objects.create_user('doc_candado', password='x')
        PerfilUsuario.objects.create(usuario=cls.docente, rol=PerfilUsuario.PROFESOR)
        cls.alumno = User.objects.create_user('alu_candado', password='x')
        PerfilUsuario.objects.create(usuario=cls.alumno, rol=PerfilUsuario.ESTUDIANTE)

        carrera = Carrera.objects.create(nombre='Administracion', codigo='ADMC')
        malla = Malla.objects.create(carrera=carrera, nombre='Malla', codigo='MC')
        nivel = NivelMalla.objects.create(malla=malla, numero=1, nombre='Nivel 1')
        materia = Materia.objects.create(codigo='COSTC', nombre='Costos')
        cls.materia_malla = MateriaMalla.objects.create(
            malla=malla, nivel=nivel, materia=materia,
        )
        cls.periodo = PeriodoAcademico.objects.create(
            nombre='2026-1',
            fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 6, 30),
            activo_matricula=True,
        )
        InscripcionMalla.objects.create(
            estudiante=cls.alumno, malla=malla, periodo=cls.periodo,
        )
        cls.caso = Simulacion.objects.create(
            materia_malla=cls.materia_malla,
            titulo='Caso de costos',
            maximo_decisiones=1,
            estado=Simulacion.PUBLICADA,
        )
        cls.juego = ActividadInteractiva.objects.create(
            materia_malla=cls.materia_malla,
            simulacion=cls.caso,
            creador=cls.docente,
            motor='seleccion_unica',
            titulo='Calentamiento de costos',
            obligatoria=True,
            publicada=True,
            configuracion=get_plugin('seleccion_unica').normalize_config({
                'preguntas': [{'enunciado': '2+2', 'opciones': '3\n4', 'correcta': 2}],
            }),
        )

    def setUp(self):
        self.client.force_login(self.alumno)

    def _iniciar(self):
        return self.client.post(reverse('alu_simulaciones') + '?action=iniciar', {
            'simulacion_id': self.caso.pk,
        }, headers={'x-requested-with': 'XMLHttpRequest'})

    def _aprobar_el_juego(self):
        IntentoActividadInteractiva.objects.create(
            actividad=self.juego, estudiante=self.alumno,
            completado=True, aprobado=True, porcentaje=100,
        )

    def test_con_el_juego_pendiente_la_vista_no_deja_entrar(self):
        respuesta = self._iniciar()

        self.assertFalse(respuesta.json()['result'])
        self.assertIn('Calentamiento de costos', respuesta.json()['mensaje'])
        self.assertEqual(IntentoSimulacion.objects.count(), 0)

    def test_aprobado_el_juego_la_vista_deja_entrar(self):
        self._aprobar_el_juego()

        respuesta = self._iniciar()

        self.assertTrue(respuesta.json()['result'], respuesta.json())
        self.assertEqual(IntentoSimulacion.objects.count(), 1)

    def test_un_juego_opcional_no_bloquea_la_vista(self):
        self.juego.obligatoria = False
        self.juego.save()

        respuesta = self._iniciar()

        self.assertTrue(respuesta.json()['result'], respuesta.json())

    def test_la_portada_muestra_el_entrenamiento_y_el_boton_bloqueado(self):
        pagina = self.client.get(reverse('alu_simulaciones'), {
            'action': 'iniciar', 'simulacion_id': self.caso.pk,
        })

        self.assertContains(pagina, 'Calentamiento de costos')
        self.assertContains(pagina, 'Termina el entrenamiento para desbloquear')
        self.assertNotContains(pagina, 'Iniciar misión')

    def test_aprobado_el_juego_la_portada_ofrece_iniciar(self):
        self._aprobar_el_juego()

        pagina = self.client.get(reverse('alu_simulaciones'), {
            'action': 'iniciar', 'simulacion_id': self.caso.pk,
        })

        self.assertContains(pagina, 'Iniciar misión')
        self.assertNotContains(pagina, 'Termina el entrenamiento para desbloquear')
