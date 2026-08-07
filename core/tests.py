from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import PerfilUsuario, RolAdicional
from simulador.ia_status import _clasificar_error


class ErrorProveedor(Exception):
    def __init__(self, mensaje, status_code):
        super().__init__(mensaje)
        self.status_code = status_code


class EstadoIATests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user('admin-ia', password='x')
        PerfilUsuario.objects.create(usuario=self.admin, rol=PerfilUsuario.ADMIN)
        self.estudiante = User.objects.create_user('estudiante-ia', password='x')
        PerfilUsuario.objects.create(usuario=self.estudiante, rol=PerfilUsuario.ESTUDIANTE)

    def test_solo_administrador_puede_consultar_estado(self):
        self.client.force_login(self.estudiante)
        self.assertEqual(self.client.get(reverse('core:estado_ia')).status_code, 403)

    def test_panel_admin_incluye_monitor_de_ia(self):
        self.client.force_login(self.admin)
        respuesta = self.client.get(reverse('dashboard'))
        self.assertContains(respuesta, 'Estado de la IA')
        self.assertContains(respuesta, reverse('core:estado_ia'))
        self.assertContains(respuesta, 'comprobar(false)')

    def test_monitor_es_visible_con_admin_como_rol_adicional(self):
        usuario = User.objects.create_user('profesor-admin-ia', password='x')
        perfil = PerfilUsuario.objects.create(usuario=usuario, rol=PerfilUsuario.PROFESOR)
        RolAdicional.objects.create(perfil=perfil, rol=PerfilUsuario.ADMIN)
        self.client.force_login(usuario)

        respuesta = self.client.get(reverse('dashboard'))

        self.assertContains(respuesta, 'Estado de la IA')
        self.assertContains(respuesta, reverse('core:estado_ia'))

    @patch('simulador.ia_status.comprobar_estado_ia')
    def test_devuelve_estado_normalizado(self, comprobar):
        comprobar.return_value = {
            'proveedores': [{'nombre': 'DeepSeek', 'estado': 'disponible'}],
            'comprobado_en': '2026-08-03T21:00:00-05:00',
            'comprobado_texto': '03/08/2026 21:00:00',
        }
        self.client.force_login(self.admin)
        respuesta = self.client.get(reverse('core:estado_ia'), {'refresh': '1'})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()['proveedores'][0]['estado'], 'disponible')

    def test_clasifica_saturacion_y_falta_de_creditos(self):
        self.assertEqual(_clasificar_error(ErrorProveedor('Service is too busy', 503))[0], 'saturado')
        self.assertEqual(_clasificar_error(ErrorProveedor('You have no credits remaining', 429))[0], 'sin_creditos')

# Create your tests here.
