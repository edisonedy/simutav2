from django.conf import settings
from django.db import models


class ModeloBase(models.Model):
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)
    usuario_creacion = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(class)s_creados',
    )

    class Meta:
        abstract = True


class Institucion(ModeloBase):
    nombre = models.CharField(max_length=200)
    siglas = models.CharField(max_length=30, blank=True)
    ruc = models.CharField(max_length=20, blank=True)
    direccion = models.CharField(max_length=250, blank=True)
    telefono = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)

    class Meta:
        verbose_name = 'institucion'
        verbose_name_plural = 'instituciones'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class PerfilUsuario(ModeloBase):
    ADMIN = 'ADMIN'
    PROFESOR = 'PROFESOR'
    ESTUDIANTE = 'ESTUDIANTE'
    COORDINADOR = 'COORDINADOR'

    ROLES = [
        (ADMIN, 'Administrador'),
        (PROFESOR, 'Profesor'),
        (ESTUDIANTE, 'Estudiante'),
        (COORDINADOR, 'Coordinador'),
    ]

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='perfil',
    )
    institucion = models.ForeignKey(
        Institucion,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='perfiles',
    )
    rol = models.CharField(max_length=20, choices=ROLES, default=ESTUDIANTE)
    identificacion = models.CharField(max_length=20, blank=True)
    telefono = models.CharField(max_length=50, blank=True)

    class Meta:
        verbose_name = 'perfil de usuario'
        verbose_name_plural = 'perfiles de usuario'
        ordering = ['usuario__last_name', 'usuario__first_name', 'usuario__username']

    def __str__(self):
        return f'{self.usuario.get_full_name() or self.usuario.username} - {self.get_rol_display()}'

