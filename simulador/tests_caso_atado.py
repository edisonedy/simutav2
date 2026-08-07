"""El caso real SIEMPRE pertenece a una materia.

El modelo ya lo exigia, pero el formulario ofrecia un desplegable con la opcion
vacia y hacia parecer que el caso podia quedar suelto. Estos tests fijan las
dos mitades: que el servidor no acepta un caso sin materia, y que cuando se
crea desde una materia esa materia no se puede cambiar.
"""

from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from academico.models import (
    Carrera,
    Malla,
    Materia,
    MateriaMalla,
    NivelMalla,
    PeriodoAcademico,
    ProfesorMateria,
)
from core.models import PerfilUsuario
from simulador.forms import SimulacionForm
from simulador.models import Simulacion


class CasoAtadoAMateriaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.profesor = User.objects.create_user('prof_atado', password='x', is_staff=True)
        PerfilUsuario.objects.create(usuario=cls.profesor, rol=PerfilUsuario.PROFESOR)

        carrera = Carrera.objects.create(nombre='Administracion', codigo='ADMA')
        malla = Malla.objects.create(carrera=carrera, nombre='Malla', codigo='MA1')
        nivel = NivelMalla.objects.create(malla=malla, numero=1, nombre='Nivel 1')
        cls.periodo = PeriodoAcademico.objects.create(
            nombre='2026-1',
            fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 6, 30),
            activo_matricula=True,
        )
        cls.materia = MateriaMalla.objects.create(
            malla=malla, nivel=nivel,
            materia=Materia.objects.create(codigo='COST1', nombre='Costos'),
        )
        cls.otra_materia = MateriaMalla.objects.create(
            malla=malla, nivel=nivel,
            materia=Materia.objects.create(codigo='FIN1', nombre='Finanzas'),
        )
        for materia in (cls.materia, cls.otra_materia):
            ProfesorMateria.objects.create(
                profesor=cls.profesor, materia_malla=materia, periodo=cls.periodo,
            )

    def setUp(self):
        self.client.force_login(self.profesor)

    def _crear(self, datos):
        return self.client.post(
            reverse('pro_simulaciones') + '?action=add',
            datos,
            headers={'x-requested-with': 'XMLHttpRequest'},
        )

    def _datos(self, **extra):
        datos = {
            'titulo': 'Caso de costos',
            'tipo_simulacion': Simulacion.TIPO_CON_IA_DINAMICA,
            'nivel_dificultad': Simulacion.DIFICULTAD_MEDIA,
            'maximo_decisiones': 3,
            'tiempo_estimado': 30,
            'peso_resultado': 30,
            'peso_rubrica_decision': 30,
            'bonus_pronostico': 8,
            'bonus_reflexion': 6,
            'bonus_adaptacion': 6,
        }
        datos.update(extra)
        return datos

    def test_sin_materia_el_caso_no_se_crea(self):
        respuesta = self._crear(self._datos())

        self.assertFalse(respuesta.json()['result'], respuesta.json())
        self.assertEqual(Simulacion.objects.count(), 0)

    def test_con_materia_el_caso_se_crea_y_queda_atado(self):
        respuesta = self._crear(self._datos(materia_malla=self.materia.pk))

        self.assertTrue(respuesta.json()['result'], respuesta.json())
        caso = Simulacion.objects.get(titulo='Caso de costos')
        self.assertEqual(caso.materia_malla, self.materia)

    def test_el_modelo_no_admite_un_caso_sin_materia(self):
        campo = Simulacion._meta.get_field('materia_malla')
        self.assertFalse(campo.null)
        self.assertFalse(campo.blank)

    def test_creando_desde_una_materia_no_se_ofrece_cambiarla(self):
        """El desplegable con '---------' hacia parecer que podia quedar suelto."""
        html = self.client.get(reverse('pro_simulaciones'), {
            'action': 'add', 'materia_malla': self.materia.pk,
        }, headers={'x-requested-with': 'XMLHttpRequest'}).content.decode()

        self.assertNotIn('<select name="materia_malla"', html)
        self.assertIn('name="materia_malla"', html)   # sigue viajando, oculto
        self.assertIn('Costos', html)
        self.assertIn('queda amarrado a esta materia', html)

    def test_sin_materia_en_la_url_el_desplegable_lo_pide(self):
        html = self.client.get(reverse('pro_simulaciones'), {
            'action': 'add',
        }, headers={'x-requested-with': 'XMLHttpRequest'}).content.decode()

        self.assertIn('<select name="materia_malla"', html)
        # La opcion vacia del desplegable de materia dice que hay que elegir,
        # en vez del '---------' que parecia "sin materia y ya".
        self.assertIn('<option value="" selected>Elige la materia</option>', html)

    def test_no_se_puede_colgar_el_caso_de_una_materia_ajena(self):
        ajeno = User.objects.create_user('prof_ajeno', password='x', is_staff=True)
        PerfilUsuario.objects.create(usuario=ajeno, rol=PerfilUsuario.PROFESOR)
        suya = MateriaMalla.objects.create(
            malla=self.materia.malla, nivel=self.materia.nivel,
            materia=Materia.objects.create(codigo='MKT1', nombre='Marketing'),
        )
        ProfesorMateria.objects.create(
            profesor=ajeno, materia_malla=suya, periodo=self.periodo,
        )
        self.client.force_login(ajeno)

        # Manda el id de una materia que no dicta.
        respuesta = self._crear(self._datos(materia_malla=self.materia.pk))

        self.assertFalse(respuesta.json()['result'], respuesta.json())
        self.assertEqual(Simulacion.objects.count(), 0)


class FormularioDelCasoTests(TestCase):
    def test_la_materia_es_obligatoria_en_el_formulario(self):
        self.assertTrue(SimulacionForm().fields['materia_malla'].required)

    def test_con_materia_fija_el_campo_va_oculto(self):
        carrera = Carrera.objects.create(nombre='C', codigo='CF')
        malla = Malla.objects.create(carrera=carrera, nombre='M', codigo='MF')
        nivel = NivelMalla.objects.create(malla=malla, numero=1, nombre='N1')
        materia = MateriaMalla.objects.create(
            malla=malla, nivel=nivel,
            materia=Materia.objects.create(codigo='X1', nombre='X'),
        )

        form = SimulacionForm(materia_fija=materia)

        self.assertEqual(form.initial['materia_malla'], materia.pk)
        self.assertTrue(form.fields['materia_malla'].widget.is_hidden)
        self.assertTrue(form.fields['materia_malla'].required)
