import re
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from academico.forms import InscripcionMallaForm, ProfesorMateriaForm
from academico.models import Carrera, InscripcionMalla, Malla, PeriodoAcademico
from core.funciones import errores_formulario
from core.models import Institucion, PerfilUsuario

User = get_user_model()


class FormulariosInscripcionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.institucion = Institucion.objects.create(nombre='UTA')
        cls.carrera = Carrera.objects.create(institucion=cls.institucion, nombre='Sistemas', codigo='SIS')
        cls.malla = Malla.objects.create(carrera=cls.carrera, nombre='Malla 2026', codigo='M26')
        cls.periodo = PeriodoAcademico.objects.create(
            institucion=cls.institucion,
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
        PerfilUsuario.objects.create(usuario=usuario, institucion=cls.institucion, rol=rol)
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

    MODULOS = ['adm_carreras', 'adm_mallas', 'adm_materias', 'adm_periodos', 'adm_inscripciones']

    @classmethod
    def setUpTestData(cls):
        cls.institucion = Institucion.objects.create(nombre='UTA')
        cls.carrera = Carrera.objects.create(institucion=cls.institucion, nombre='Sistemas', codigo='SIS')
        cls.malla = Malla.objects.create(carrera=cls.carrera, nombre='Malla', codigo='M1')
        cls.periodo = PeriodoAcademico.objects.create(
            institucion=cls.institucion, nombre='2026-1',
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
        PerfilUsuario.objects.create(usuario=usuario, institucion=cls.institucion, rol=rol)
        return usuario

    def test_estudiante_no_entra_a_ningun_modulo_academico(self):
        self.client.force_login(self.estudiante)
        for nombre in self.MODULOS:
            with self.subTest(modulo=nombre):
                self.assertEqual(self.client.get(reverse(nombre)).status_code, 403)

    def test_profesor_tampoco_administra_el_catalogo(self):
        self.client.force_login(self.profesor)
        for nombre in self.MODULOS:
            with self.subTest(modulo=nombre):
                self.assertEqual(self.client.get(reverse(nombre)).status_code, 403)

    def test_admin_y_superusuario_si_entran(self):
        for usuario in (self.admin, self.superusuario):
            self.client.force_login(usuario)
            for nombre in self.MODULOS:
                with self.subTest(usuario=usuario.username, modulo=nombre):
                    self.assertEqual(self.client.get(reverse(nombre)).status_code, 200)

    def test_estudiante_no_puede_crear_una_carrera(self):
        self.client.force_login(self.estudiante)
        antes = Carrera.objects.count()
        respuesta = self.client.post(reverse('adm_carreras'), {
            'action': 'add', 'institucion': self.institucion.pk,
            'nombre': 'Carrera pirata', 'codigo': 'HACK',
            'modalidad': 'PRESENCIAL', 'duracion_periodos': 8, 'activo': 'on',
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
            'rol': PerfilUsuario.ADMIN, 'institucion': self.institucion.pk,
            'identificacion': '1', 'telefono': '1',
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

    MODULOS = ['adm_carreras', 'adm_mallas', 'adm_materias', 'adm_periodos', 'adm_inscripciones']

    @classmethod
    def setUpTestData(cls):
        cls.institucion = Institucion.objects.create(nombre='UTA')
        cls.carrera = Carrera.objects.create(institucion=cls.institucion, nombre='Sistemas', codigo='SIS')
        cls.malla = Malla.objects.create(carrera=cls.carrera, nombre='Malla 2026', codigo='M26')
        cls.periodo = PeriodoAcademico.objects.create(
            institucion=cls.institucion,
            nombre='2026-1',
            fecha_inicio=date(2026, 1, 1),
            fecha_fin=date(2026, 6, 30),
        )
        cls.estudiante = User.objects.create_user('est1', password='x')
        PerfilUsuario.objects.create(
            usuario=cls.estudiante, institucion=cls.institucion, rol=PerfilUsuario.ESTUDIANTE,
        )
        cls.admin = User.objects.create_user('admin1', password='x')
        PerfilUsuario.objects.create(
            usuario=cls.admin, institucion=cls.institucion, rol=PerfilUsuario.ADMIN,
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
        institucion = Institucion.objects.create(nombre='UTA')
        admin = User.objects.create_user('jefe', password='x')
        PerfilUsuario.objects.create(usuario=admin, institucion=institucion, rol=PerfilUsuario.ADMIN)
        self.client.force_login(admin)

        html = self.client.get(reverse('adm_inscripciones'), {'action': 'add'}).content.decode()

        self.assertIn('Solo aparecen los usuarios activos con perfil de', html)
        self.assertIn(reverse('seguridad:usuarios'), html)
