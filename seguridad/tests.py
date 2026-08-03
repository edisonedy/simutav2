from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from academico.forms import InscripcionMallaForm
from core.models import Institucion, PerfilUsuario
from core.permisos import es_administrativo, es_docente, usuarios_con_rol


class GestionPerfilesTests(TestCase):
    """El modulo solo sabia crear usuarios: no habia forma de corregir un rol mal
    puesto ni de darle perfil a un usuario creado por consola."""

    @classmethod
    def setUpTestData(cls):
        cls.institucion = Institucion.objects.create(nombre='UTA')
        cls.admin = User.objects.create_user('rector', password='x')
        PerfilUsuario.objects.create(
            usuario=cls.admin, institucion=cls.institucion, rol=PerfilUsuario.ADMIN,
        )

    def setUp(self):
        self.client.force_login(self.admin)
        self.url = reverse('seguridad:usuarios')

    def _crear(self, username, rol, **extra):
        usuario = User.objects.create_user(username, password='x', **extra)
        perfil = PerfilUsuario.objects.create(
            usuario=usuario, institucion=self.institucion, rol=rol,
        )
        return usuario, perfil

    def test_alta_crea_usuario_con_el_perfil_elegido(self):
        respuesta = self.client.post(self.url, {
            'action': 'add',
            'username': 'nueva.docente', 'password1': 'ClaveLarga123!', 'password2': 'ClaveLarga123!',
            'first_name': 'Ana', 'last_name': 'Vega', 'email': 'ana@uta.edu.ec',
            'roles': [PerfilUsuario.PROFESOR], 'institucion': self.institucion.pk,
            'identificacion': '1804', 'telefono': '099',
        }, headers={'x-requested-with': 'XMLHttpRequest'})
        self.assertTrue(respuesta.json()['result'], respuesta.json())
        usuario = User.objects.get(username='nueva.docente')
        self.assertEqual(usuario.perfil.rol, PerfilUsuario.PROFESOR)
        self.assertEqual(usuario.perfil.institucion, self.institucion)
        self.assertEqual(usuario.first_name, 'Ana')
        self.assertTrue(usuario.check_password('ClaveLarga123!'))

    def test_editar_corrige_un_rol_mal_puesto(self):
        usuario, perfil = self._crear('confundido', PerfilUsuario.ESTUDIANTE)
        respuesta = self.client.post(self.url, {
            'action': 'edit', 'pk': perfil.pk,
            'roles': [PerfilUsuario.PROFESOR], 'institucion': self.institucion.pk,
            'identificacion': '', 'telefono': '', 'activo': 'on',
            'first_name': 'Luis', 'last_name': 'Paz', 'email': '',
        }, headers={'x-requested-with': 'XMLHttpRequest'})
        self.assertTrue(respuesta.json()['result'], respuesta.json())
        perfil.refresh_from_db()
        usuario.refresh_from_db()
        self.assertEqual(perfil.rol, PerfilUsuario.PROFESOR)
        self.assertEqual(usuario.first_name, 'Luis')

    def test_asignar_perfil_a_un_usuario_que_no_tenia(self):
        huerfano = User.objects.create_superuser('root_consola', password='x')
        self.assertFalse(hasattr(huerfano, 'perfil'))
        respuesta = self.client.post(self.url, {
            'action': 'asignar', 'usuario': huerfano.pk,
            'roles': [PerfilUsuario.ADMIN], 'institucion': self.institucion.pk,
            'identificacion': '', 'telefono': '',
        }, headers={'x-requested-with': 'XMLHttpRequest'})
        self.assertTrue(respuesta.json()['result'], respuesta.json())
        huerfano.refresh_from_db()
        self.assertEqual(huerfano.perfil.rol, PerfilUsuario.ADMIN)

    def test_listado_muestra_a_los_usuarios_sin_perfil(self):
        User.objects.create_user('sin_perfil', password='x')
        html = self.client.get(self.url).content.decode()
        self.assertIn('sin_perfil', html)
        self.assertIn('Sin perfil', html)

    def test_listado_agrupa_por_perfil_y_omite_los_grupos_vacios(self):
        self._crear('docente1', PerfilUsuario.PROFESOR)
        self._crear('alumno1', PerfilUsuario.ESTUDIANTE)
        User.objects.create_user('huerfano', password='x')

        grupos = self.client.get(self.url).context['grupos']
        titulos = [g['titulo'] for g in grupos]

        self.assertEqual(titulos, ['Administradores', 'Profesores', 'Estudiantes', 'Sin perfil'])
        self.assertNotIn('Coordinadores', titulos, 'un grupo sin nadie no debe aparecer')
        por_titulo = {g['titulo']: [u.username for u in g['usuarios']] for g in grupos}
        self.assertEqual(por_titulo['Profesores'], ['docente1'])
        self.assertEqual(por_titulo['Sin perfil'], ['huerfano'])
        self.assertEqual(por_titulo['Administradores'], ['rector'])

    def test_desactivar_cierra_el_acceso_sin_borrar_nada(self):
        usuario, perfil = self._crear('saliente', PerfilUsuario.PROFESOR)
        respuesta = self.client.post(self.url, {
            'action': 'delete', 'pk': perfil.pk,
        }, headers={'x-requested-with': 'XMLHttpRequest'})
        self.assertTrue(respuesta.json()['result'], respuesta.json())
        usuario.refresh_from_db()
        perfil.refresh_from_db()
        self.assertFalse(usuario.is_active)
        self.assertFalse(perfil.activo)
        self.assertTrue(User.objects.filter(pk=usuario.pk).exists())

    def test_un_admin_no_puede_quitarse_a_si_mismo_el_acceso(self):
        """Si no, el ultimo administrador se deja fuera y toca entrar por consola."""
        respuesta = self.client.post(self.url, {
            'action': 'edit', 'pk': self.admin.perfil.pk,
            'roles': [PerfilUsuario.ESTUDIANTE], 'institucion': self.institucion.pk,
            'identificacion': '', 'telefono': '', 'activo': 'on',
            'first_name': '', 'last_name': '', 'email': '',
        }, headers={'x-requested-with': 'XMLHttpRequest'})
        self.assertFalse(respuesta.json()['result'])
        self.admin.perfil.refresh_from_db()
        self.assertEqual(self.admin.perfil.rol, PerfilUsuario.ADMIN)

    def test_modales_publican_a_una_url_existente(self):
        _, perfil = self._crear('alguien', PerfilUsuario.ESTUDIANTE)
        casos = [
            ({'action': 'add'}, 'add'),
            ({'action': 'edit', 'pk': perfil.pk}, 'edit'),
            ({'action': 'delete', 'pk': perfil.pk}, 'delete'),
            ({'action': 'asignar'}, 'asignar'),
        ]
        for parametros, accion in casos:
            with self.subTest(accion=accion):
                html = self.client.get(self.url, parametros).content.decode()
                self.assertIn(f'action="{self.url}"', html)
                self.assertIn(f'name="action" value="{accion}"', html)


class VariosPerfilesPorPersonaTests(TestCase):
    """Una misma persona puede ser administradora y ademas profesora o estudiante."""

    @classmethod
    def setUpTestData(cls):
        cls.institucion = Institucion.objects.create(nombre='UTA')
        cls.admin = User.objects.create_user('rectora', password='x')
        PerfilUsuario.objects.create(
            usuario=cls.admin, institucion=cls.institucion, rol=PerfilUsuario.ADMIN,
        )

    def setUp(self):
        self.client.force_login(self.admin)
        self.url = reverse('seguridad:usuarios')

    def _perfil(self, username, *roles):
        usuario = User.objects.create_user(username, password='x')
        perfil = PerfilUsuario.objects.create(usuario=usuario, institucion=self.institucion)
        perfil.fijar_roles(roles)
        perfil.save()
        return usuario, perfil

    def test_el_rol_principal_es_el_de_mayor_alcance(self):
        _, perfil = self._perfil('mixta', PerfilUsuario.ESTUDIANTE, PerfilUsuario.ADMIN)
        self.assertEqual(perfil.rol, PerfilUsuario.ADMIN)
        self.assertEqual(perfil.roles, {PerfilUsuario.ADMIN, PerfilUsuario.ESTUDIANTE})
        self.assertEqual(perfil.roles_secundarios, ['Estudiante'])

    def test_un_admin_que_ademas_es_estudiante_conserva_los_dos_accesos(self):
        usuario, _ = self._perfil('doble', PerfilUsuario.ADMIN, PerfilUsuario.ESTUDIANTE)
        self.assertTrue(es_administrativo(usuario))
        self.assertIn(usuario, usuarios_con_rol(PerfilUsuario.ESTUDIANTE))
        self.assertIn(usuario, InscripcionMallaForm().fields['estudiante'].queryset)

    def test_un_admin_que_ademas_es_profesor_entra_a_los_dos_paneles(self):
        usuario, _ = self._perfil('gestora', PerfilUsuario.ADMIN, PerfilUsuario.PROFESOR)
        self.assertTrue(es_administrativo(usuario))
        self.assertTrue(es_docente(usuario))
        self.client.force_login(usuario)
        self.assertEqual(self.client.get(reverse('adm_carreras')).status_code, 200)
        self.assertEqual(self.client.get(reverse('pro_simulaciones')).status_code, 200)

    def test_quitar_un_perfil_quita_el_acceso(self):
        usuario, perfil = self._perfil('temporal', PerfilUsuario.ADMIN, PerfilUsuario.ESTUDIANTE)
        perfil.fijar_roles([PerfilUsuario.ESTUDIANTE])
        perfil.save()
        self.assertFalse(es_administrativo(usuario))
        self.assertEqual(perfil.roles, {PerfilUsuario.ESTUDIANTE})

    def test_editar_marca_y_desmarca_perfiles(self):
        usuario, perfil = self._perfil('editable', PerfilUsuario.ESTUDIANTE)
        respuesta = self.client.post(self.url, {
            'action': 'edit', 'pk': perfil.pk,
            'roles': [PerfilUsuario.ADMIN, PerfilUsuario.PROFESOR],
            'institucion': self.institucion.pk,
            'identificacion': '', 'telefono': '', 'activo': 'on',
            'first_name': '', 'last_name': '', 'email': '',
        }, headers={'x-requested-with': 'XMLHttpRequest'})
        self.assertTrue(respuesta.json()['result'], respuesta.json())
        perfil.refresh_from_db()
        self.assertEqual(perfil.roles, {PerfilUsuario.ADMIN, PerfilUsuario.PROFESOR})
        self.assertEqual(perfil.rol, PerfilUsuario.ADMIN)

    def test_alta_admite_varios_perfiles_de_una_vez(self):
        respuesta = self.client.post(self.url, {
            'action': 'add',
            'username': 'multi', 'password1': 'ClaveLarga123!', 'password2': 'ClaveLarga123!',
            'first_name': '', 'last_name': '', 'email': '',
            'roles': [PerfilUsuario.PROFESOR, PerfilUsuario.ESTUDIANTE],
            'institucion': self.institucion.pk, 'identificacion': '', 'telefono': '',
        }, headers={'x-requested-with': 'XMLHttpRequest'})
        self.assertTrue(respuesta.json()['result'], respuesta.json())
        perfil = User.objects.get(username='multi').perfil
        self.assertEqual(perfil.roles, {PerfilUsuario.PROFESOR, PerfilUsuario.ESTUDIANTE})
        self.assertEqual(perfil.rol, PerfilUsuario.PROFESOR)

    def test_el_listado_muestra_los_perfiles_secundarios(self):
        self._perfil('conextras', PerfilUsuario.ADMIN, PerfilUsuario.PROFESOR)
        html = self.client.get(self.url).content.decode()
        self.assertIn('tambien Profesor', html)

    def test_comando_agrega_y_quita_sin_pisar_lo_demas(self):
        usuario, perfil = self._perfil('porconsola', PerfilUsuario.PROFESOR)
        call_command('asignar_rol', 'porconsola', '--agregar', 'ADMIN')
        perfil.refresh_from_db()
        self.assertEqual(perfil.roles, {PerfilUsuario.ADMIN, PerfilUsuario.PROFESOR})
        call_command('asignar_rol', 'porconsola', '--quitar', 'ADMIN')
        perfil.refresh_from_db()
        self.assertEqual(perfil.roles, {PerfilUsuario.PROFESOR})

    def test_comando_crea_el_perfil_de_quien_no_tiene(self):
        User.objects.create_superuser('desdeconsola', password='x')
        call_command('asignar_rol', 'desdeconsola', '--agregar', 'ADMIN')
        perfil = User.objects.get(username='desdeconsola').perfil
        self.assertEqual(perfil.roles, {PerfilUsuario.ADMIN})

    def test_el_comando_no_deja_a_nadie_sin_ningun_perfil(self):
        usuario, perfil = self._perfil('unico', PerfilUsuario.PROFESOR)
        call_command('asignar_rol', 'unico', '--quitar', 'PROFESOR')
        perfil.refresh_from_db()
        self.assertEqual(perfil.roles, {PerfilUsuario.PROFESOR})
