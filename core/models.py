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
    # De mayor a menor alcance. Cuando alguien tiene varios perfiles, el primero
    # de esta lista es el principal: manda en el dashboard y en el listado.
    PRECEDENCIA = [ADMIN, COORDINADOR, PROFESOR, ESTUDIANTE]

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
    rol = models.CharField(
        'rol principal', max_length=20, choices=ROLES, default=ESTUDIANTE,
        help_text='Se calcula solo: el de mayor alcance entre los perfiles de la persona.',
    )
    identificacion = models.CharField(max_length=20, blank=True)
    telefono = models.CharField(max_length=50, blank=True)

    class Meta:
        verbose_name = 'perfil de usuario'
        verbose_name_plural = 'perfiles de usuario'
        ordering = ['usuario__last_name', 'usuario__first_name', 'usuario__username']

    def __str__(self):
        return f'{self.usuario.get_full_name() or self.usuario.username} - {self.get_rol_display()}'

    @property
    def roles(self):
        """Todos los perfiles de la persona. Una misma persona puede ser a la vez
        administrador y profesor, o profesor y estudiante."""
        adicionales = {r.rol for r in self.roles_adicionales.all() if r.activo}
        return {self.rol} | adicionales

    def tiene_rol(self, *roles):
        return bool(self.roles.intersection(roles))

    @classmethod
    def rol_principal(cls, roles):
        """El de mayor alcance entre los que tenga la persona."""
        for rol in cls.PRECEDENCIA:
            if rol in roles:
                return rol
        return cls.ESTUDIANTE

    def fijar_roles(self, roles, usuario_creacion=None):
        """Deja los perfiles de la persona exactamente en `roles`: el principal en
        el propio perfil y el resto en la tabla de adicionales."""
        roles = {r for r in roles if r in dict(self.ROLES)} or {self.ESTUDIANTE}
        self.rol = self.rol_principal(roles)
        adicionales = roles - {self.rol}
        self.roles_adicionales.exclude(rol__in=adicionales).delete()
        for rol in adicionales:
            RolAdicional.objects.update_or_create(
                perfil=self, rol=rol, defaults={'activo': True, 'usuario_creacion': usuario_creacion},
            )
        return self.rol

    @property
    def roles_secundarios(self):
        """Los perfiles que no son el principal, para mostrarlos en el listado."""
        etiquetas = dict(self.ROLES)
        return [etiquetas[r] for r in self.PRECEDENCIA if r in self.roles and r != self.rol]


class RolAdicional(ModeloBase):
    """Los perfiles extra de una persona, ademas del principal."""
    perfil = models.ForeignKey(
        PerfilUsuario, on_delete=models.CASCADE, related_name='roles_adicionales',
    )
    rol = models.CharField(max_length=20, choices=PerfilUsuario.ROLES)

    class Meta:
        verbose_name = 'perfil adicional'
        verbose_name_plural = 'perfiles adicionales'
        unique_together = [('perfil', 'rol')]
        ordering = ['rol']

    def __str__(self):
        return f'{self.perfil.usuario.username} - {self.get_rol_display()}'

