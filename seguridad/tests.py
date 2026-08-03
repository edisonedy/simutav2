from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import Institucion, PerfilUsuario


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
            'rol': PerfilUsuario.PROFESOR, 'institucion': self.institucion.pk,
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
            'rol': PerfilUsuario.PROFESOR, 'institucion': self.institucion.pk,
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
            'rol': PerfilUsuario.ADMIN, 'institucion': self.institucion.pk,
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
            'rol': PerfilUsuario.ESTUDIANTE, 'institucion': self.institucion.pk,
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
