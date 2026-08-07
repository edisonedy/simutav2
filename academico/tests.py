import re
import shutil
import tempfile
from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from academico.forms import InscripcionMallaForm, ProfesorMateriaForm
from academico.models import (
    Carrera,
    InscripcionMalla,
    Malla,
    Materia,
    MateriaMalla,
    MateriaMallaPredecesora,
    MateriaPeriodo,
    Modalidad,
    NivelMalla,
    MallaPeriodo,
    PeriodoAcademico,
    ProfesorMateria,
    RecordAcademico,
)
from core.funciones import errores_formulario
from core.models import PerfilUsuario
from simulador.models import ActividadMateria, Simulacion, TemaMateria

User = get_user_model()


class FormulariosInscripcionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.carrera = Carrera.objects.create(nombre='Sistemas', codigo='SIS')
        cls.malla = Malla.objects.create(carrera=cls.carrera, nombre='Malla 2026', codigo='M26')
        cls.periodo = PeriodoAcademico.objects.create(
            nombre='2026-1',
            fecha_inicio=date(2026, 1, 1),
            fecha_fin=date(2026, 6, 30),
        )
        cls.estudiante = cls._usuario('est1', PerfilUsuario.ESTUDIANTE)
        cls.profesor = cls._usuario('prof1', PerfilUsuario.PROFESOR)
        cls.admin = cls._usuario('admin1', PerfilUsuario.ADMIN)
        cls.sin_perfil = User.objects.create_user('npc', password='x')

    @classmethod
    def _usuario(cls, username, rol):
        usuario = User.objects.create_user(username, password='x')
        PerfilUsuario.objects.create(usuario=usuario, rol=rol)
        return usuario

    def test_estudiante_dropdown_solo_muestra_estudiantes(self):
        opciones = list(InscripcionMallaForm().fields['estudiante'].queryset)
        self.assertIn(self.estudiante, opciones)
        self.assertNotIn(self.profesor, opciones)
        self.assertNotIn(self.admin, opciones)
        self.assertNotIn(self.sin_perfil, opciones)

    def test_profesor_dropdown_excluye_estudiantes(self):
        opciones = list(ProfesorMateriaForm().fields['profesor'].queryset)
        self.assertIn(self.profesor, opciones)
        self.assertIn(self.admin, opciones)
        self.assertNotIn(self.estudiante, opciones)
        self.assertNotIn(self.sin_perfil, opciones)

    def test_inscripcion_valida_se_guarda(self):
        form = InscripcionMallaForm({
            'estudiante': self.estudiante.pk,
            'malla': self.malla.pk,
            'periodo': self.periodo.pk,
            'estado': InscripcionMalla.ACTIVA,
            'activo': 'on',
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_inscripcion_duplicada_da_mensaje_legible(self):
        InscripcionMalla.objects.create(
            estudiante=self.estudiante, malla=self.malla, periodo=self.periodo,
        )
        form = InscripcionMallaForm({
            'estudiante': self.estudiante.pk,
            'malla': self.malla.pk,
            'periodo': self.periodo.pk,
            'estado': InscripcionMalla.ACTIVA,
            'activo': 'on',
        })
        self.assertFalse(form.is_valid())
        mensaje = errores_formulario(form)
        self.assertNotEqual(mensaje, 'Error en el formulario')
        self.assertIn('ya existe', mensaje)


class PermisosAdministracionTests(TestCase):
    """Antes de esto, cualquier usuario logueado podia crear carreras, inscribirse
    solo a una malla y darse de alta un usuario ADMIN. Solo pedia @login_required."""

    MODULOS = [
        'adm_carreras', 'adm_mallas', 'adm_periodos', 'adm_inscripciones',
    ]

    @classmethod
    def setUpTestData(cls):
        cls.carrera = Carrera.objects.create(nombre='Sistemas', codigo='SIS')
        cls.malla = Malla.objects.create(carrera=cls.carrera, nombre='Malla', codigo='M1')
        cls.periodo = PeriodoAcademico.objects.create(
            nombre='2026-1',
            fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 6, 30),
        )
        cls.estudiante = cls._usuario('alumno', PerfilUsuario.ESTUDIANTE)
        # Los profesores tienen is_staff, pero no administran el catalogo.
        cls.profesor = cls._usuario('docente', PerfilUsuario.PROFESOR, is_staff=True)
        cls.admin = cls._usuario('rector', PerfilUsuario.ADMIN)
        cls.superusuario = User.objects.create_superuser('root', password='x')

    @classmethod
    def _usuario(cls, username, rol, is_staff=False):
        usuario = User.objects.create_user(username, password='x', is_staff=is_staff)
        PerfilUsuario.objects.create(usuario=usuario, rol=rol)
        return usuario

    def test_estudiante_no_entra_a_ningun_modulo_academico(self):
        self.client.force_login(self.estudiante)
        for nombre in [*self.MODULOS, 'adm_materias']:
            with self.subTest(modulo=nombre):
                self.assertEqual(self.client.get(reverse(nombre)).status_code, 403)

    def test_profesor_entra_a_materias_pero_no_administra_el_catalogo(self):
        self.client.force_login(self.profesor)
        for nombre in self.MODULOS:
            with self.subTest(modulo=nombre):
                self.assertEqual(self.client.get(reverse(nombre)).status_code, 403)
        self.assertEqual(self.client.get(reverse('adm_materias')).status_code, 200)
        respuesta = self.client.post(
            reverse('adm_materias'),
            {'action': 'add', 'codigo': 'X', 'nombre': 'Materia ajena'},
            headers={'x-requested-with': 'XMLHttpRequest'},
        )
        self.assertEqual(respuesta.status_code, 403)

    def test_admin_y_superusuario_si_entran(self):
        for usuario in (self.admin, self.superusuario):
            self.client.force_login(usuario)
            for nombre in [*self.MODULOS, 'adm_materias']:
                with self.subTest(usuario=usuario.username, modulo=nombre):
                    self.assertEqual(self.client.get(reverse(nombre)).status_code, 200)

    def test_estudiante_no_puede_crear_una_carrera(self):
        self.client.force_login(self.estudiante)
        antes = Carrera.objects.count()
        respuesta = self.client.post(reverse('adm_carreras'), {
            'action': 'add', 'nombre': 'Carrera pirata', 'codigo': 'HACK',
            'duracion_periodos': 8, 'activo': 'on',
        }, headers={'x-requested-with': 'XMLHttpRequest'})
        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(Carrera.objects.count(), antes)

    def test_estudiante_no_puede_inscribirse_solo(self):
        self.client.force_login(self.estudiante)
        respuesta = self.client.post(reverse('adm_inscripciones'), {
            'action': 'add', 'estudiante': self.estudiante.pk,
            'malla': self.malla.pk, 'periodo': self.periodo.pk,
            'estado': InscripcionMalla.ACTIVA, 'activo': 'on',
        }, headers={'x-requested-with': 'XMLHttpRequest'})
        self.assertEqual(respuesta.status_code, 403)
        self.assertFalse(InscripcionMalla.objects.filter(estudiante=self.estudiante).exists())

    def test_estudiante_no_puede_desactivar_una_malla(self):
        self.client.force_login(self.estudiante)
        respuesta = self.client.post(reverse('adm_mallas'), {
            'action': 'delete', 'pk': self.malla.pk,
        }, headers={'x-requested-with': 'XMLHttpRequest'})
        self.assertEqual(respuesta.status_code, 403)
        self.malla.refresh_from_db()
        self.assertTrue(self.malla.activo)

    def test_estudiante_no_puede_crear_usuarios(self):
        """El peor caso: darse de alta a si mismo una cuenta ADMIN."""
        self.client.force_login(self.estudiante)
        antes = User.objects.count()
        respuesta = self.client.post(reverse('seguridad:usuarios'), {
            'action': 'add',
            'username': 'pirata', 'password1': 'ClaveLarga123!', 'password2': 'ClaveLarga123!',
            'first_name': 'P', 'last_name': 'U', 'email': 'p@x.com',
            'rol': PerfilUsuario.ADMIN, 'identificacion': '1', 'telefono': '1',
        })
        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(User.objects.count(), antes)

    def test_estudiante_no_ve_el_menu_de_administracion(self):
        self.client.force_login(self.estudiante)
        html = self.client.get(reverse('dashboard')).content.decode()
        self.assertNotIn(reverse('adm_carreras'), html)
        self.assertNotIn(reverse('adm_simulaciones'), html)
        self.assertIn(reverse('alu_simulaciones'), html)

    def test_admin_si_ve_el_menu_de_administracion(self):
        self.client.force_login(self.admin)
        html = self.client.get(reverse('dashboard')).content.decode()
        self.assertIn(reverse('adm_carreras'), html)


class ModalesAcademicoTests(TestCase):
    """Los modales publican por AJAX: si el action del form no apunta a una URL
    valida el navegador recibe un 404 y el usuario no puede guardar nada."""

    MODULOS = [
        'adm_carreras', 'adm_mallas', 'adm_materias', 'adm_periodos',
        'adm_inscripciones',
    ]

    @classmethod
    def setUpTestData(cls):
        cls.carrera = Carrera.objects.create(nombre='Sistemas', codigo='SIS')
        cls.malla = Malla.objects.create(carrera=cls.carrera, nombre='Malla 2026', codigo='M26')
        cls.periodo = PeriodoAcademico.objects.create(
            nombre='2026-1',
            fecha_inicio=date(2026, 1, 1),
            fecha_fin=date(2026, 6, 30),
        )
        cls.estudiante = User.objects.create_user('est1', password='x')
        PerfilUsuario.objects.create(
            usuario=cls.estudiante, rol=PerfilUsuario.ESTUDIANTE,
        )
        cls.admin = User.objects.create_user('admin1', password='x')
        PerfilUsuario.objects.create(
            usuario=cls.admin, rol=PerfilUsuario.ADMIN,
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def _action_del_form(self, html):
        coincidencia = re.search(r'<form[^>]*\saction="([^"]*)"', html)
        self.assertIsNotNone(coincidencia, 'El modal no tiene un formulario con action')
        return coincidencia.group(1)

    def test_modales_add_publican_a_una_url_existente(self):
        for nombre in self.MODULOS:
            with self.subTest(modulo=nombre):
                url = reverse(nombre)
                respuesta = self.client.get(url, {'action': 'add'})
                self.assertEqual(respuesta.status_code, 200)
                html = respuesta.content.decode()
                self.assertEqual(self._action_del_form(html), url)
                self.assertIn('name="action" value="add"', html)

    def test_modales_edit_y_delete_publican_a_una_url_existente(self):
        inscripcion = InscripcionMalla.objects.create(
            estudiante=self.estudiante, malla=self.malla, periodo=self.periodo,
        )
        url = reverse('adm_inscripciones')
        for accion in ('edit', 'delete'):
            with self.subTest(accion=accion):
                respuesta = self.client.get(url, {'action': accion, 'pk': inscripcion.pk})
                self.assertEqual(respuesta.status_code, 200)
                html = respuesta.content.decode()
                self.assertEqual(self._action_del_form(html), url)
                self.assertIn(f'name="action" value="{accion}"', html)

    def _datos_inscripcion(self):
        return {
            'action': 'add',
            'estudiante': self.estudiante.pk,
            'malla': self.malla.pk,
            'periodo': self.periodo.pk,
            'estado': InscripcionMalla.ACTIVA,
            'activo': 'on',
        }

    def test_alta_de_inscripcion_por_ajax_guarda(self):
        respuesta = self.client.post(
            reverse('adm_inscripciones'),
            self._datos_inscripcion(),
            headers={'x-requested-with': 'XMLHttpRequest'},
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.json()['result'], respuesta.json())
        self.assertTrue(
            InscripcionMalla.objects.filter(estudiante=self.estudiante, malla=self.malla).exists()
        )

    def test_alta_sin_javascript_guarda_y_redirige(self):
        """Si el navegador envia el formulario sin fetch, la vista no debe
        responder JSON crudo: guarda y devuelve al listado con un mensaje."""
        respuesta = self.client.post(reverse('adm_inscripciones'), self._datos_inscripcion())
        self.assertRedirects(respuesta, reverse('adm_inscripciones'))
        self.assertTrue(
            InscripcionMalla.objects.filter(estudiante=self.estudiante, malla=self.malla).exists()
        )

    def test_error_sin_javascript_muestra_mensaje_legible(self):
        InscripcionMalla.objects.create(
            estudiante=self.estudiante, malla=self.malla, periodo=self.periodo,
        )
        respuesta = self.client.post(
            reverse('adm_inscripciones'), self._datos_inscripcion(), follow=True,
        )
        self.assertEqual(respuesta.status_code, 200)
        textos = [str(m) for m in respuesta.context['messages']]
        self.assertTrue(any('ya existe' in t for t in textos), textos)

    def test_post_a_la_raiz_de_academico_es_404(self):
        """Reproduce el bug original: action='.' resolvia a /academico/."""
        self.assertEqual(self.client.post('/academico/', {'action': 'add'}).status_code, 404)

    def test_editar_conserva_al_estudiante_aunque_ya_no_tenga_ese_rol(self):
        """El dropdown solo lista estudiantes. Si a un inscrito le cambian el rol
        (o lo desactivan), el select salia vacio y guardar era imposible."""
        inscripcion = InscripcionMalla.objects.create(
            estudiante=self.estudiante, malla=self.malla, periodo=self.periodo,
        )
        perfil = self.estudiante.perfil
        perfil.rol = PerfilUsuario.ADMIN
        perfil.save(update_fields=['rol'])

        url = reverse('adm_inscripciones')
        modal = self.client.get(url, {'action': 'edit', 'pk': inscripcion.pk})
        self.assertIn(f'value="{self.estudiante.pk}" selected', modal.content.decode())

        respuesta = self.client.post(url, {
            'action': 'edit',
            'pk': inscripcion.pk,
            'estudiante': self.estudiante.pk,
            'malla': self.malla.pk,
            'periodo': self.periodo.pk,
            'estado': InscripcionMalla.FINALIZADA,
            'activo': 'on',
        }, headers={'x-requested-with': 'XMLHttpRequest'})
        self.assertTrue(respuesta.json()['result'], respuesta.json())
        inscripcion.refresh_from_db()
        self.assertEqual(inscripcion.estado, InscripcionMalla.FINALIZADA)


class AyudaDeRolEnFormulariosTests(TestCase):
    """Cuando falta alguien en un desplegable filtrado por rol, el modal debe
    decir por que y a donde ir, en vez de dejar al usuario adivinando."""

    def test_el_modal_de_inscripcion_explica_el_filtro_y_enlaza_a_usuarios(self):
        admin = User.objects.create_user('jefe', password='x')
        PerfilUsuario.objects.create(usuario=admin, rol=PerfilUsuario.ADMIN)
        self.client.force_login(admin)

        html = self.client.get(reverse('adm_inscripciones'), {'action': 'add'}).content.decode()

        self.assertIn('Solo aparecen los usuarios activos con perfil de', html)
        self.assertIn(reverse('seguridad:usuarios'), html)


class _BaseAcademicaMixin:
    """Una malla de tres niveles con una materia en cada uno, que es el minimo
    para probar su estructura, contenidos y requisitos."""

    @classmethod
    def _armar_malla(cls):
        cls.carrera = Carrera.objects.create(
            nombre='Sistemas', codigo='SIS',
        )
        cls.malla = Malla.objects.create(carrera=cls.carrera, nombre='Malla 2026', codigo='M26')
        cls.periodo = PeriodoAcademico.objects.create(
            nombre='2026-1',
            fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 6, 30),
        )
        cls.niveles = {
            numero: NivelMalla.objects.create(
                malla=cls.malla, numero=numero, nombre=f'Nivel {numero}',
            )
            for numero in (1, 2, 3)
        }
        cls.materias = {}
        for numero, codigo in ((1, 'PRG1'), (2, 'PRG2'), (3, 'PRG3')):
            materia = Materia.objects.create(
                codigo=codigo, nombre=f'Programacion {numero}',
            )
            cls.materias[numero] = MateriaMalla.objects.create(
                malla=cls.malla, nivel=cls.niveles[numero], materia=materia,
            )
        cls.malla_periodo = MallaPeriodo.objects.create(
            periodo=cls.periodo, malla=cls.malla,
        )

    @classmethod
    def _admin(cls, username='rector'):
        usuario = User.objects.create_user(username, password='x')
        PerfilUsuario.objects.create(
            usuario=usuario, rol=PerfilUsuario.ADMIN,
        )
        return usuario


class PredecesorasTests(_BaseAcademicaMixin, TestCase):
    """El requisito solo tiene sentido dentro de la misma malla y hacia atras.
    Si se acepta cualquier par, se puede armar una malla imposible de cursar."""

    @classmethod
    def setUpTestData(cls):
        cls._armar_malla()
        cls.admin = cls._admin()

    def setUp(self):
        self.client.force_login(self.admin)

    def _alta(self, materia_malla, predecesora):
        return self.client.post(reverse('adm_mallas'), {
            'action': 'add_predecesora',
            'materia_malla_id': materia_malla.pk,
            'predecesora': predecesora.pk,
        }, headers={'x-requested-with': 'XMLHttpRequest'})

    def test_requisito_de_un_nivel_anterior_se_guarda(self):
        respuesta = self._alta(self.materias[2], self.materias[1])
        self.assertTrue(respuesta.json()['result'], respuesta.json())
        self.assertEqual(
            list(self.materias[2].predecesoras_activas()), [self.materias[1]],
        )

    def test_no_acepta_una_materia_del_mismo_nivel_ni_posterior(self):
        otra = Materia.objects.create(codigo='BD', nombre='Bases')
        companera = MateriaMalla.objects.create(
            malla=self.malla, nivel=self.niveles[2], materia=otra,
        )
        for predecesora in (companera, self.materias[3]):
            with self.subTest(predecesora=predecesora):
                respuesta = self._alta(self.materias[2], predecesora)
                self.assertFalse(respuesta.json()['result'])
                self.assertFalse(
                    MateriaMallaPredecesora.objects.filter(
                        materia_malla=self.materias[2], predecesora=predecesora,
                    ).exists()
                )

    def test_no_acepta_una_materia_de_otra_malla(self):
        otra_malla = Malla.objects.create(carrera=self.carrera, nombre='Malla 2020', codigo='M20')
        nivel = NivelMalla.objects.create(malla=otra_malla, numero=1, nombre='Nivel 1')
        materia = Materia.objects.create(codigo='ALG', nombre='Algebra')
        ajena = MateriaMalla.objects.create(malla=otra_malla, nivel=nivel, materia=materia)

        respuesta = self._alta(self.materias[2], ajena)

        self.assertFalse(respuesta.json()['result'])
        self.assertEqual(MateriaMallaPredecesora.objects.count(), 0)

    def test_no_acepta_el_mismo_requisito_dos_veces(self):
        self._alta(self.materias[2], self.materias[1])
        respuesta = self._alta(self.materias[2], self.materias[1])
        self.assertFalse(respuesta.json()['result'])
        self.assertEqual(MateriaMallaPredecesora.objects.count(), 1)

    def test_detecta_el_circulo_aunque_los_niveles_lo_permitieran(self):
        """Programacion 3 <- 2 <- 1. Si ademas 1 pidiera 3, ninguna se podria
        tomar nunca. El nivel ya lo impide, pero la deteccion no depende de eso."""
        MateriaMallaPredecesora.objects.create(
            materia_malla=self.materias[2], predecesora=self.materias[1],
        )
        MateriaMallaPredecesora.objects.create(
            materia_malla=self.materias[3], predecesora=self.materias[2],
        )
        circulo = MateriaMallaPredecesora(
            materia_malla=self.materias[1], predecesora=self.materias[3],
        )
        self.assertTrue(circulo.genera_ciclo())

    def test_el_desplegable_solo_ofrece_niveles_anteriores(self):
        html = self.client.get(reverse('adm_mallas'), {
            'action': 'add_predecesora', 'materia_malla_id': self.materias[2].pk,
        }).content.decode()

        opciones = re.findall(r'<option value="(\d+)"', html)
        self.assertEqual(opciones, [str(self.materias[1].pk)])

    def test_la_estructura_muestra_los_requisitos_de_cada_materia(self):
        MateriaMallaPredecesora.objects.create(
            materia_malla=self.materias[2], predecesora=self.materias[1],
        )
        html = self.client.get(reverse('adm_mallas'), {
            'action': 'estructura', 'pk': self.malla.pk,
        }).content.decode()

        self.assertIn('Programacion 2', html)
        self.assertIn('N1 Programacion 1', html)

    def test_quitar_el_requisito_lo_desactiva(self):
        requisito = MateriaMallaPredecesora.objects.create(
            materia_malla=self.materias[2], predecesora=self.materias[1],
        )
        respuesta = self.client.post(reverse('adm_mallas'), {
            'action': 'del_predecesora', 'pk': requisito.pk,
        }, headers={'x-requested-with': 'XMLHttpRequest'})

        self.assertTrue(respuesta.json()['result'])
        requisito.refresh_from_db()
        self.assertFalse(requisito.activo)
        self.assertEqual(list(self.materias[2].predecesoras_activas()), [])


class RequisitosDelEstudianteTests(_BaseAcademicaMixin, TestCase):
    """Los requisitos se resuelven contra el historial, no contra la matricula
    del periodo en curso."""

    @classmethod
    def setUpTestData(cls):
        cls._armar_malla()
        cls.estudiante = User.objects.create_user('alumno', password='x')
        PerfilUsuario.objects.create(
            usuario=cls.estudiante, rol=PerfilUsuario.ESTUDIANTE,
        )
        cls.inscripcion = InscripcionMalla.objects.create(
            estudiante=cls.estudiante, malla=cls.malla, periodo=cls.periodo,
        )
        MateriaMallaPredecesora.objects.create(
            materia_malla=cls.materias[2], predecesora=cls.materias[1],
        )

    def test_sin_el_requisito_aprobado_no_puede_tomar_la_materia(self):
        self.assertFalse(self.inscripcion.puede_tomar_materia(self.materias[2]))
        self.assertEqual(
            self.inscripcion.predecesoras_pendientes(self.materias[2]), [self.materias[1]],
        )

    def test_haberla_cursado_sin_aprobar_no_alcanza(self):
        RecordAcademico.objects.create(
            estudiante=self.estudiante, materia_malla=self.materias[1],
            periodo=self.periodo, nota=45, aprobado=False,
        )
        self.assertFalse(self.inscripcion.puede_tomar_materia(self.materias[2]))

    def test_con_el_requisito_aprobado_si_puede(self):
        RecordAcademico.objects.create(
            estudiante=self.estudiante, materia_malla=self.materias[1],
            periodo=self.periodo, nota=80, aprobado=True,
        )
        self.assertTrue(self.inscripcion.puede_tomar_materia(self.materias[2]))

    def test_una_materia_sin_requisitos_siempre_se_puede_tomar(self):
        self.assertTrue(self.inscripcion.puede_tomar_materia(self.materias[1]))


class ContenidoDeMateriaTests(_BaseAcademicaMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls._armar_malla()
        cls.admin = cls._admin()
        cls.profesor = User.objects.create_user('docente_contenido', password='x')
        PerfilUsuario.objects.create(
            usuario=cls.profesor, rol=PerfilUsuario.PROFESOR,
        )
        ProfesorMateria.objects.create(
            profesor=cls.profesor,
            materia_malla=cls.materias[1],
            periodo=cls.periodo,
        )

    def setUp(self):
        self.media_temporal = tempfile.mkdtemp()
        self.media_override = override_settings(MEDIA_ROOT=self.media_temporal)
        self.media_override.enable()

    def tearDown(self):
        self.media_override.disable()
        shutil.rmtree(self.media_temporal, ignore_errors=True)

    def _post_ajax(self, datos):
        return self.client.post(
            reverse('adm_materias'), datos,
            headers={'x-requested-with': 'XMLHttpRequest'},
        )

    def test_administrador_crea_tema_y_actividad_en_sus_dos_secciones(self):
        self.client.force_login(self.admin)
        respuesta = self._post_ajax({
            'action': 'add_tema', 'materia_malla': self.materias[1].pk,
            'nombre': 'Reclutamiento', 'descripcion': 'Seleccion inicial',
            'orden': 1, 'activo': 'on',
        })
        self.assertTrue(respuesta.json()['result'], respuesta.json())
        tema = TemaMateria.objects.get(nombre='Reclutamiento')

        # Los juegos (relacionar, memoria, ordenar...) los hace ActividadInteractiva;
        # aqui solo van trabajos con instrucciones o archivo.
        for categoria, titulo, tipo in (
            (ActividadMateria.REFUERZO, 'Guia de reclutamiento', 'GUIA_APE'),
            (ActividadMateria.EVALUACION, 'Prueba corta', 'PRUEBA'),
        ):
            respuesta = self._post_ajax({
                'action': 'add_actividad', 'materia_malla': self.materias[1].pk,
                'tema': tema.pk, 'categoria': categoria, 'tipo': tipo,
                'titulo': titulo, 'descripcion': '', 'orden': 1, 'activo': 'on',
            })
            self.assertTrue(respuesta.json()['result'], respuesta.json())

        html = self.client.get(reverse('adm_materias'), {
            'action': 'detalle', 'pk': self.materias[1].pk,
        }).content.decode()
        self.assertIn('Reclutamiento', html)
        self.assertIn('Practicar y reforzar', html)
        self.assertIn('Guia de reclutamiento', html)
        self.assertIn('Evaluar y aplicar', html)
        self.assertIn('Prueba corta', html)

    def test_guia_ape_general_se_sube_y_se_puede_abrir(self):
        self.client.force_login(self.admin)
        archivo = SimpleUploadedFile(
            'guia-ape.pdf', b'%PDF-1.4 guia de practica', content_type='application/pdf',
        )
        respuesta = self._post_ajax({
            'action': 'add_actividad', 'materia_malla': self.materias[1].pk,
            'tema': '', 'categoria': ActividadMateria.EVALUACION,
            'tipo': 'GUIA_APE', 'titulo': 'Guia APE de laboratorio',
            'descripcion': 'Practica global', 'archivo': archivo,
            'orden': 1, 'activo': 'on',
        })
        self.assertTrue(respuesta.json()['result'], respuesta.json())
        actividad = ActividadMateria.objects.get(titulo='Guia APE de laboratorio')
        self.assertTrue(actividad.archivo.name.endswith('guia-ape.pdf'))

        html = self.client.get(reverse('adm_materias'), {
            'action': 'detalle', 'pk': self.materias[1].pk,
        }).content.decode()
        self.assertIn('Actividades generales', html)
        self.assertIn(actividad.archivo.url, html)

        estructura = self.client.get(reverse('adm_mallas'), {
            'action': 'estructura', 'pk': self.malla.pk,
        }).content.decode()
        self.assertIn('Guia APE de laboratorio', estructura)
        self.assertIn(actividad.archivo.url, estructura)

        self.assertTrue(actividad.archivo.storage.exists(actividad.archivo.name))
        with actividad.archivo.open('rb') as guia_guardada:
            self.assertTrue(guia_guardada.read().startswith(b'%PDF-1.4'))

    def test_profesor_solo_ve_y_edita_la_materia_asignada(self):
        # Las dos estan creadas en el periodo; el profesor solo debe ver la suya.
        MateriaPeriodo.objects.create(
            malla_periodo=self.malla_periodo, materia_malla=self.materias[1],
        )
        MateriaPeriodo.objects.create(
            malla_periodo=self.malla_periodo, materia_malla=self.materias[2],
        )
        self.client.force_login(self.profesor)
        listado = self.client.get(reverse('adm_materias'))
        self.assertContains(listado, self.malla.nombre)
        detalle_malla = self.client.get(reverse('adm_materias'), {
            'action': 'malla', 'pk': self.malla.pk,
        })
        self.assertContains(detalle_malla, 'Nivel 1')
        self.assertNotContains(detalle_malla, 'Nivel 2')
        self.assertContains(detalle_malla, 'Programacion 1')
        self.assertNotContains(detalle_malla, 'Programacion 2')

        respuesta = self._post_ajax({
            'action': 'add_tema', 'materia_malla': self.materias[1].pk,
            'nombre': 'Tema del profesor', 'descripcion': '',
            'orden': 1, 'activo': 'on',
        })
        self.assertTrue(respuesta.json()['result'], respuesta.json())
        self.assertEqual(
            self.client.get(reverse('adm_materias'), {
                'action': 'detalle', 'pk': self.materias[2].pk,
            }).status_code,
            404,
        )

    def test_guia_subida_desde_asignatura_malla_aparece_en_materias(self):
        self.client.force_login(self.admin)
        archivo = SimpleUploadedFile(
            'ape-desde-malla.pdf', b'%PDF-1.4 compartida', content_type='application/pdf',
        )
        respuesta = self._post_ajax({
            'action': 'add_actividad',
            'materia_malla': self.materias[1].pk,
            'solo_guia_ape': '1',
            'retorno_malla': '1',
            'tema': '',
            'categoria': ActividadMateria.EVALUACION,
            'tipo': ActividadMateria.GUIA_APE,
            'titulo': 'APE compartida desde la malla',
            'descripcion': '',
            'archivo': archivo,
            'orden': 1,
            'activo': 'on',
        })
        self.assertTrue(respuesta.json()['result'], respuesta.json())
        guia = ActividadMateria.objects.get(titulo='APE compartida desde la malla')
        self.assertEqual(guia.materia_malla, self.materias[1])
        self.assertEqual(guia.tipo, ActividadMateria.GUIA_APE)

        detalle = self.client.get(reverse('adm_materias'), {
            'action': 'detalle', 'pk': self.materias[1].pk,
        }).content.decode()
        self.assertIn(guia.titulo, detalle)
        self.assertIn(guia.archivo.url, detalle)

    def test_simulacion_se_muestra_en_evaluar_y_aplicar(self):
        self.client.force_login(self.admin)
        tema = TemaMateria.objects.create(
            materia_malla=self.materias[1], nombre='Seleccion', orden=1,
        )
        Simulacion.objects.create(
            materia_malla=self.materias[1], tema_materia=tema,
            profesor=self.admin, titulo='Escoger candidatos',
        )

        html = self.client.get(reverse('adm_materias'), {
            'action': 'detalle', 'pk': self.materias[1].pk,
        }).content.decode()
        self.assertIn('Evaluar y aplicar', html)
        self.assertIn('Escoger candidatos', html)

    def test_un_tema_no_puede_asignarse_a_otra_materia(self):
        tema = TemaMateria.objects.create(
            materia_malla=self.materias[1], nombre='Tema propio', orden=1,
        )
        simulacion = Simulacion(
            materia_malla=self.materias[2], tema_materia=tema, titulo='Invalida',
        )
        with self.assertRaises(ValidationError):
            simulacion.full_clean()

    def test_la_url_de_oferta_ya_no_existe(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get('/academico/adm_oferta').status_code, 404)


class SelectorDePeriodoTests(_BaseAcademicaMixin, TestCase):
    """Como en el SGA: el periodo se elige una vez arriba y las pantallas
    academicas trabajan sobre ese periodo, no sobre todo el historico."""

    @classmethod
    def setUpTestData(cls):
        cls._armar_malla()
        cls.admin = cls._admin()
        cls.periodo_viejo = PeriodoAcademico.objects.create(
            nombre='2025-2',
            fecha_inicio=date(2025, 7, 1), fecha_fin=date(2025, 12, 31),
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def _elegir(self, periodo):
        return self.client.post(reverse('core:cambiar_periodo'), {
            'periodo': periodo.pk, 'next': reverse('adm_mallas'),
        })

    def test_la_barra_muestra_los_periodos_y_el_elegido(self):
        self._elegir(self.periodo_viejo)
        html = self.client.get(reverse('adm_mallas')).content.decode()

        self.assertIn('name="periodo"', html)
        self.assertIn(f'<option value="{self.periodo_viejo.pk}" selected>', html)

    def test_el_listado_de_mallas_enlaza_a_sus_asignaturas_de_malla(self):
        respuesta = self.client.get(reverse('adm_mallas'))

        self.assertContains(respuesta, self.malla.nombre)
        self.assertContains(
            respuesta,
            f"{reverse('adm_mallas')}?action=estructura&pk={self.malla.pk}",
        )
        self.assertContains(respuesta, 'Asignaturas de la malla')

    def test_materias_primero_muestra_mallas_y_luego_sus_materias_creadas(self):
        NivelMalla.objects.create(malla=self.malla, numero=4, nombre='Nivel vacio 4')
        listado = self.client.get(reverse('adm_materias'))
        self.assertContains(listado, self.malla.nombre)
        self.assertContains(
            listado,
            f"{reverse('adm_materias')}?action=malla&pk={self.malla.pk}",
        )

        MateriaPeriodo.objects.create(
            malla_periodo=self.malla_periodo, materia_malla=self.materias[1],
        )
        detalle = self.client.get(reverse('adm_materias'), {
            'action': 'malla', 'pk': self.malla.pk,
        })
        # Solo la materia creada; el resto del plan no ocupa sitio.
        self.assertContains(detalle, 'Nivel 1')
        self.assertContains(detalle, 'Programacion 1')
        self.assertNotContains(detalle, 'Programacion 2')

    def test_crear_materia_desde_un_nivel_la_agrega_a_la_malla(self):
        nivel = self.niveles[2]
        respuesta = self.client.post(reverse('adm_materias'), {
            'action': 'add',
            'malla': self.malla.pk,
            'nivel': nivel.pk,
            'codigo': 'BD2',
            'nombre': 'Bases de datos 2',
            'creditos': 4,
            'horas': 64,
            'activo': 'on',
        })

        self.assertRedirects(
            respuesta,
            f"{reverse('adm_materias')}?action=malla&pk={self.malla.pk}",
        )
        materia_malla = MateriaMalla.objects.get(materia__codigo='BD2')
        self.assertEqual(materia_malla.malla, self.malla)
        self.assertEqual(materia_malla.nivel, nivel)

    def test_un_nivel_nuevo_se_ve_sin_tener_que_habilitarlo(self):
        """Un nivel nuevo aparece en cuanto se le crea una materia, sin tener que
        habilitar el nivel por separado."""
        nivel = NivelMalla.objects.create(
            malla=self.malla, numero=5, nombre='Nivel 5',
        )
        materia = Materia.objects.create(
            codigo='NV5', nombre='Materia del quinto',
        )
        asignatura = MateriaMalla.objects.create(
            malla=self.malla, nivel=nivel, materia=materia,
        )
        MateriaPeriodo.objects.create(
            malla_periodo=self.malla_periodo, materia_malla=asignatura,
        )

        pagina = self.client.get(reverse('adm_materias'), {
            'action': 'malla', 'pk': self.malla.pk,
        })

        self.assertIn(
            nivel.pk, [bloque['nivel'].pk for bloque in pagina.context['niveles']],
        )
        self.assertContains(pagina, 'Nivel 5')
        self.assertContains(pagina, 'Materia del quinto')

    def test_cambiar_periodo_devuelve_a_la_pantalla_de_origen(self):
        respuesta = self._elegir(self.periodo_viejo)
        self.assertRedirects(respuesta, reverse('adm_mallas'))
        self.assertEqual(self.client.session['periodo_id'], self.periodo_viejo.pk)

    def test_no_redirige_a_un_sitio_externo(self):
        """El 'next' viene del formulario: no puede convertirse en un salto a
        otro dominio."""
        respuesta = self.client.post(reverse('core:cambiar_periodo'), {
            'periodo': self.periodo.pk, 'next': 'https://sitio-malo.example.com/x',
        })
        self.assertRedirects(respuesta, reverse('dashboard'))

    def test_un_periodo_inexistente_no_rompe_la_pantalla(self):
        sesion = self.client.session
        sesion['periodo_id'] = 999999
        sesion.save()
        # Cae al periodo por defecto (el mas reciente) en vez de reventar.
        self.assertEqual(self.client.get(reverse('adm_mallas')).status_code, 200)

    def test_el_estudiante_no_ve_el_selector(self):
        estudiante = User.objects.create_user('alumno_sel', password='x')
        PerfilUsuario.objects.create(
            usuario=estudiante, rol=PerfilUsuario.ESTUDIANTE,
        )
        self.client.force_login(estudiante)

        html = self.client.get(reverse('dashboard')).content.decode()

        self.assertNotIn('id="selector-periodo"', html)


class AltaDelCatalogoAcademicoTests(TestCase):
    """El sistema es de una sola universidad: el catalogo no pregunta por la
    institucion ni la necesita para guardar."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user('rector', password='x')
        PerfilUsuario.objects.create(
            usuario=cls.admin, rol=PerfilUsuario.ADMIN,
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def test_los_modales_no_piden_la_institucion(self):
        for modulo in ('adm_carreras', 'adm_materias', 'adm_periodos'):
            with self.subTest(modulo=modulo):
                html = self.client.get(reverse(modulo), {'action': 'add'}).content.decode()
                self.assertNotIn('name="institucion"', html)

    def test_se_crea_una_carrera(self):
        presencial = Modalidad.objects.create(nombre='Presencial')

        respuesta = self.client.post(reverse('adm_carreras'), {
            'action': 'add', 'nombre': 'Software', 'codigo': 'SW',
            'modalidad': presencial.pk, 'duracion_periodos': 8, 'activo': 'on',
        }, headers={'x-requested-with': 'XMLHttpRequest'})

        self.assertTrue(respuesta.json()['result'], respuesta.json())
        self.assertEqual(Carrera.objects.get(codigo='SW').modalidad, presencial)

    def test_la_modalidad_se_elige_de_la_lista_no_se_escribe(self):
        """Antes era texto libre y convivian 'Presencial' y 'PRESENCIAL'."""
        Modalidad.objects.create(nombre='Presencial')

        html = self.client.get(reverse('adm_carreras'), {'action': 'add'}).content.decode()

        self.assertIn('<select name="modalidad"', html)
        self.assertIn('Presencial', html)

    def test_se_crea_un_periodo(self):
        respuesta = self.client.post(reverse('adm_periodos'), {
            'action': 'add', 'nombre': '2026-2',
            'fecha_inicio': '2026-08-01', 'fecha_fin': '2026-12-20', 'activo': 'on',
        }, headers={'x-requested-with': 'XMLHttpRequest'})

        self.assertTrue(respuesta.json()['result'], respuesta.json())
        self.assertTrue(PeriodoAcademico.objects.filter(nombre='2026-2').exists())

    def test_se_crea_una_materia(self):
        respuesta = self.client.post(reverse('adm_materias'), {
            'action': 'add', 'codigo': 'X', 'nombre': 'Materia', 'creditos': 1,
            'horas': 1, 'activo': 'on',
        }, headers={'x-requested-with': 'XMLHttpRequest'})

        self.assertTrue(respuesta.json()['result'], respuesta.json())
        self.assertTrue(Materia.objects.filter(codigo='X').exists())


class MallaEnElPeriodoTests(_BaseAcademicaMixin, TestCase):
    """El escalon intermedio conecta la malla con el periodo y lleva nombre
    propio. La pantalla lista SOLO las materias creadas: la materia aparece
    cuando se crea, porque es ahi donde viven sus temas, juegos y casos."""

    @classmethod
    def setUpTestData(cls):
        cls._armar_malla()
        cls.admin = cls._admin()

    def setUp(self):
        self.client.force_login(self.admin)

    def _pagina_malla(self):
        return self.client.get(reverse('adm_materias'), {'action': 'malla', 'pk': self.malla.pk})

    @staticmethod
    def _materias_listadas(pagina):
        return sum(len(bloque['filas']) for bloque in pagina.context['niveles'])

    def _crear_materia(self, asignatura):
        return MateriaPeriodo.objects.create(
            malla_periodo=self.malla_periodo, materia_malla=asignatura,
        )

    def test_se_abre_la_malla_en_el_periodo_con_nombre_propio(self):
        self.malla_periodo.delete()

        respuesta = self.client.post(reverse('adm_materias'), {
            'action': 'add_malla_periodo', 'malla': self.malla.pk,
            'nombre': 'Software 2026-1 matutina',
        }, headers={'x-requested-with': 'XMLHttpRequest'})

        self.assertTrue(respuesta.json()['result'], respuesta.json())
        enlace = MallaPeriodo.objects.get(periodo=self.periodo, malla=self.malla)
        self.assertEqual(enlace.nombre, 'Software 2026-1 matutina')
        self.assertContains(self._pagina_malla(), 'Software 2026-1 matutina')

    def test_sin_nombre_propio_se_usa_el_de_la_malla(self):
        self.malla_periodo.delete()
        self.client.post(reverse('adm_materias'), {
            'action': 'add_malla_periodo', 'malla': self.malla.pk, 'nombre': '   ',
        }, headers={'x-requested-with': 'XMLHttpRequest'})

        enlace = MallaPeriodo.objects.get(periodo=self.periodo, malla=self.malla)
        self.assertEqual(enlace.nombre, '')
        self.assertEqual(enlace.nombre_visible, self.malla.nombre)

    def test_la_misma_malla_se_llama_distinto_en_otro_periodo(self):
        otro_periodo = PeriodoAcademico.objects.create(
            nombre='2026-2',
            fecha_inicio=date(2026, 8, 1), fecha_fin=date(2026, 12, 20),
        )
        self.malla_periodo.nombre = 'Matutina'
        self.malla_periodo.save()
        MallaPeriodo.objects.create(
            periodo=otro_periodo, malla=self.malla, nombre='Vespertina',
        )
        self.client.post(reverse('core:cambiar_periodo'), {
            'periodo': self.periodo.pk, 'next': reverse('adm_materias'),
        })

        pagina = self._pagina_malla()
        self.assertContains(pagina, 'Matutina')
        self.assertNotContains(pagina, 'Vespertina')

    def test_renombrar_la_malla_en_el_periodo(self):
        respuesta = self.client.post(reverse('adm_materias'), {
            'action': 'edit_malla_periodo', 'pk': self.malla_periodo.pk,
            'nombre': 'Software vespertina',
        }, headers={'x-requested-with': 'XMLHttpRequest'})

        self.assertTrue(respuesta.json()['result'], respuesta.json())
        self.malla_periodo.refresh_from_db()
        self.assertEqual(self.malla_periodo.nombre, 'Software vespertina')

    def test_quitarla_del_periodo_no_toca_el_plan(self):
        self._crear_materia(self.materias[1])

        respuesta = self.client.post(reverse('adm_materias'), {
            'action': 'delete_malla_periodo', 'pk': self.malla_periodo.pk,
        }, headers={'x-requested-with': 'XMLHttpRequest'})

        self.assertTrue(respuesta.json()['result'], respuesta.json())
        self.malla_periodo.refresh_from_db()
        self.assertFalse(self.malla_periodo.activo)
        # Las asignaturas del plan siguen intactas; lo que se cierra es la apertura.
        self.assertEqual(MateriaMalla.objects.filter(malla=self.malla, activo=True).count(), 3)

    def test_solo_se_listan_las_materias_creadas(self):
        """La asignatura del plan sin materia NO aparece: salia con contadores de
        contenido que son del plan y no de la materia, y confundia."""
        self._crear_materia(self.materias[1])

        pagina = self._pagina_malla()

        self.assertEqual(self._materias_listadas(pagina), 1)
        self.assertContains(pagina, 'Programacion 1')
        self.assertNotContains(pagina, 'Programacion 2')
        self.assertNotContains(pagina, 'Programacion 3')

    def test_sin_abrirla_en_el_periodo_no_hay_materias(self):
        self.malla_periodo.delete()

        pagina = self._pagina_malla()

        self.assertIsNone(pagina.context['malla_periodo'])
        self.assertEqual(self._materias_listadas(pagina), 0)
        self.assertContains(pagina, 'Todavia no hay materias creadas')

    def test_las_materias_salen_agrupadas_y_en_orden_de_nivel(self):
        """Un nivel sin materias creadas no ocupa sitio."""
        self._crear_materia(self.materias[1])
        self._crear_materia(self.materias[3])

        pagina = self._pagina_malla()

        numeros = [bloque['nivel'].numero for bloque in pagina.context['niveles']]
        self.assertEqual(numeros, [1, 3])
        self.assertNotContains(pagina, 'Nivel 2')


class MateriaDelPeriodoTests(_BaseAcademicaMixin, TestCase):
    """Materia = MallaPeriodo + AsignaturaMalla.

    No guarda periodo, malla, asignatura ni nivel: los lee de sus dos
    relaciones, y valida que la asignatura sea de la misma malla."""

    @classmethod
    def setUpTestData(cls):
        cls._armar_malla()
        cls.admin = cls._admin()

    def setUp(self):
        self.client.force_login(self.admin)

    def _crear(self, asignatura_malla):
        return self.client.post(reverse('adm_materias'), {
            'action': 'add_materia_periodo',
            'malla_periodo': self.malla_periodo.pk,
            'materia_malla': asignatura_malla.pk,
        }, headers={'x-requested-with': 'XMLHttpRequest'})

    def _asignatura_de_otra_malla(self):
        otra_malla = Malla.objects.create(carrera=self.carrera, nombre='Malla 2020', codigo='M20')
        nivel = NivelMalla.objects.create(malla=otra_malla, numero=1, nombre='Nivel 1')
        asignatura = Materia.objects.create(
            codigo='ALG', nombre='Algebra',
        )
        return MateriaMalla.objects.create(malla=otra_malla, nivel=nivel, materia=asignatura)

    def test_la_materia_deriva_periodo_malla_asignatura_y_nivel(self):
        respuesta = self._crear(self.materias[2])

        self.assertTrue(respuesta.json()['result'], respuesta.json())
        materia = MateriaPeriodo.objects.get(malla_periodo=self.malla_periodo)
        self.assertEqual(materia.periodo, self.periodo)
        self.assertEqual(materia.malla, self.malla)
        self.assertEqual(materia.asignatura, self.materias[2].materia)
        self.assertEqual(materia.nivel, self.niveles[2])
        # Lo unico guardado son las dos relaciones: nada de datos repetidos.
        campos = {f.name for f in MateriaPeriodo._meta.get_fields() if f.concrete}
        self.assertNotIn('periodo', campos)
        self.assertNotIn('malla', campos)
        self.assertNotIn('nivel', campos)

    def test_no_acepta_una_asignatura_de_otra_malla(self):
        ajena = self._asignatura_de_otra_malla()

        with self.assertRaises(ValidationError):
            MateriaPeriodo(malla_periodo=self.malla_periodo, materia_malla=ajena).full_clean()

        respuesta = self._crear(ajena)
        self.assertFalse(respuesta.json()['result'])
        self.assertEqual(MateriaPeriodo.objects.count(), 0)

    def test_no_se_repite_la_misma_asignatura_en_el_mismo_periodo(self):
        self._crear(self.materias[1])

        respuesta = self._crear(self.materias[1])

        self.assertFalse(respuesta.json()['result'])
        self.assertEqual(MateriaPeriodo.objects.count(), 1)

    def test_la_misma_asignatura_si_puede_estar_en_otro_periodo(self):
        # Primero la del periodo en curso: crear otro periodo posterior movería
        # el periodo de la barra y la pantalla dejaria de mirar a este.
        self.assertTrue(self._crear(self.materias[1]).json()['result'])
        otro_periodo = PeriodoAcademico.objects.create(
            nombre='2026-2',
            fecha_inicio=date(2026, 8, 1), fecha_fin=date(2026, 12, 20),
        )
        otro_enlace = MallaPeriodo.objects.create(periodo=otro_periodo, malla=self.malla)

        MateriaPeriodo.objects.create(
            malla_periodo=otro_enlace, materia_malla=self.materias[1],
        )

        self.assertEqual(
            MateriaPeriodo.objects.filter(materia_malla=self.materias[1]).count(), 2,
        )

    def test_el_desplegable_solo_ofrece_asignaturas_de_la_malla_sin_materia(self):
        from academico.forms import MateriaPeriodoForm

        ajena = self._asignatura_de_otra_malla()
        MateriaPeriodo.objects.create(
            malla_periodo=self.malla_periodo, materia_malla=self.materias[1],
        )

        opciones = list(
            MateriaPeriodoForm(malla_periodo=self.malla_periodo).fields['materia_malla'].queryset
        )

        self.assertNotIn(ajena, opciones)             # es de otra malla
        self.assertNotIn(self.materias[1], opciones)  # ya tiene materia
        self.assertIn(self.materias[2], opciones)
        self.assertIn(self.materias[3], opciones)

    def test_creacion_en_bloque(self):
        respuesta = self.client.post(reverse('adm_materias'), {
            'action': 'add_materias_bloque',
            'malla_periodo': self.malla_periodo.pk,
            'asignaturas': [self.materias[1].pk, self.materias[3].pk],
        }, headers={'x-requested-with': 'XMLHttpRequest'})

        self.assertTrue(respuesta.json()['result'], respuesta.json())
        self.assertIn('2 materias', respuesta.json()['mensaje'])
        creadas = MateriaPeriodo.objects.filter(malla_periodo=self.malla_periodo)
        self.assertCountEqual(
            [m.materia_malla_id for m in creadas],
            [self.materias[1].pk, self.materias[3].pk],
        )

    def test_el_bloque_ignora_lo_que_no_corresponde(self):
        """Aunque llegue una asignatura de otra malla o una ya creada, solo se
        crean las pendientes de esta malla."""
        ajena = self._asignatura_de_otra_malla()
        MateriaPeriodo.objects.create(
            malla_periodo=self.malla_periodo, materia_malla=self.materias[1],
        )

        self.client.post(reverse('adm_materias'), {
            'action': 'add_materias_bloque',
            'malla_periodo': self.malla_periodo.pk,
            'asignaturas': [ajena.pk, self.materias[1].pk, self.materias[2].pk],
        }, headers={'x-requested-with': 'XMLHttpRequest'})

        creadas = MateriaPeriodo.objects.filter(malla_periodo=self.malla_periodo)
        self.assertCountEqual(
            [m.materia_malla_id for m in creadas],
            [self.materias[1].pk, self.materias[2].pk],
        )

    def test_el_bloque_sin_marcar_nada_avisa(self):
        respuesta = self.client.post(reverse('adm_materias'), {
            'action': 'add_materias_bloque', 'malla_periodo': self.malla_periodo.pk,
        }, headers={'x-requested-with': 'XMLHttpRequest'})

        self.assertFalse(respuesta.json()['result'])
        self.assertEqual(MateriaPeriodo.objects.count(), 0)

    def test_la_pantalla_cuenta_lo_creado_y_lo_que_falta(self):
        MateriaPeriodo.objects.create(
            malla_periodo=self.malla_periodo, materia_malla=self.materias[1],
        )

        pagina = self.client.get(reverse('adm_materias'), {
            'action': 'malla', 'pk': self.malla.pk,
        })

        self.assertEqual(pagina.context['total_materias'], 1)
        self.assertEqual(pagina.context['pendientes'], 2)
        # Se lista la creada; las dos que faltan solo se cuentan.
        self.assertContains(pagina, 'Programacion 1')
        self.assertNotContains(pagina, 'Programacion 2')

    def test_quitar_la_materia_no_borra_la_asignatura_de_la_malla(self):
        materia = MateriaPeriodo.objects.create(
            malla_periodo=self.malla_periodo, materia_malla=self.materias[1],
        )

        respuesta = self.client.post(reverse('adm_materias'), {
            'action': 'delete_materia_periodo', 'pk': materia.pk,
        }, headers={'x-requested-with': 'XMLHttpRequest'})

        self.assertTrue(respuesta.json()['result'], respuesta.json())
        materia.refresh_from_db()
        self.assertFalse(materia.activo)
        self.assertTrue(
            MateriaMalla.objects.filter(pk=self.materias[1].pk, activo=True).exists()
        )

    def test_un_estudiante_no_crea_materias(self):
        estudiante = User.objects.create_user('alumno_mp', password='x')
        PerfilUsuario.objects.create(
            usuario=estudiante, rol=PerfilUsuario.ESTUDIANTE,
        )
        self.client.force_login(estudiante)

        respuesta = self.client.post(reverse('adm_materias'), {
            'action': 'add_materia_periodo',
            'malla_periodo': self.malla_periodo.pk,
            'materia_malla': self.materias[1].pk,
        }, headers={'x-requested-with': 'XMLHttpRequest'})

        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(MateriaPeriodo.objects.count(), 0)
