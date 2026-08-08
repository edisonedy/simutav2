from django.conf import settings
from django.core.exceptions import ValidationError
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


class PerfilUsuario(ModeloBase):
    ADMIN = 'ADMIN'
    PROFESOR = 'PROFESOR'
    ESTUDIANTE = 'ESTUDIANTE'
    COORDINADOR = 'COORDINADOR'

    ROLES = [
        (ADMIN, 'Administrador'),
        (COORDINADOR, 'Coordinador'),
        (PROFESOR, 'Profesor'),
        (ESTUDIANTE, 'Estudiante'),
    ]

    PRECEDENCIA = [
        ADMIN,
        COORDINADOR,
        PROFESOR,
        ESTUDIANTE,
    ]

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='perfil',
    )

    rol = models.CharField(
        'rol principal',
        max_length=20,
        choices=ROLES,
        default=ESTUDIANTE,
        help_text=(
            'Rol principal de la persona. '
            'Se calcula según la precedencia de sus perfiles.'
        ),
    )

    identificacion = models.CharField(
        max_length=20,
        blank=True,
    )

    telefono = models.CharField(
        max_length=50,
        blank=True,
    )

    class Meta:
        verbose_name = 'perfil de usuario'
        verbose_name_plural = 'perfiles de usuario'
        ordering = [
            'usuario__last_name',
            'usuario__first_name',
            'usuario__username',
        ]

    def __str__(self):
        nombre = self.usuario.get_full_name() or self.usuario.username
        return f'{nombre} - {self.get_rol_display()}'

    @property
    def roles(self):
        """
        Todos los roles activos de la persona.

        Ejemplo:
            ADMIN + PROFESOR + ESTUDIANTE
        """

        adicionales = set(
            self.roles_adicionales.filter(
                activo=True
            ).values_list(
                'rol',
                flat=True,
            )
        )

        return {self.rol} | adicionales

    def tiene_rol(self, *roles):
        """
        True si la persona tiene cualquiera de los roles indicados.
        """

        return bool(
            self.roles.intersection(roles)
        )

    @classmethod
    def rol_principal(cls, roles):
        """
        Determina cuál de todos los roles será el principal.
        """

        for rol in cls.PRECEDENCIA:
            if rol in roles:
                return rol

        return cls.ESTUDIANTE

    def fijar_roles(self, roles, usuario_creacion=None):
        """
        Deja exactamente los roles indicados.

        Ejemplo:

            perfil.fijar_roles([
                PerfilUsuario.ADMIN,
                PerfilUsuario.PROFESOR,
                PerfilUsuario.ESTUDIANTE,
            ])

        Resultado:

            principal = ADMIN

            adicionales:
                PROFESOR
                ESTUDIANTE
        """

        roles_validos = dict(self.ROLES)

        roles = {
            rol
            for rol in roles
            if rol in roles_validos
        }

        if not roles:
            roles = {self.ESTUDIANTE}

        nuevo_principal = self.rol_principal(roles)

        self.rol = nuevo_principal

        if self.pk:
            self.save(
                update_fields=[
                    'rol',
                    'fecha_modificacion',
                ]
            )
        else:
            self.save()

        adicionales = roles - {nuevo_principal}

        # Borrar roles que ya no debe tener.
        self.roles_adicionales.exclude(
            rol__in=adicionales
        ).delete()

        # Crear o reactivar los adicionales.
        for rol in adicionales:
            defaults = {
                'activo': True,
            }

            if usuario_creacion is not None:
                defaults['usuario_creacion'] = usuario_creacion

            RolAdicional.objects.update_or_create(
                perfil=self,
                rol=rol,
                defaults=defaults,
            )

        return nuevo_principal

    @property
    def roles_secundarios(self):
        etiquetas = dict(self.ROLES)

        return [
            etiquetas[rol]
            for rol in self.PRECEDENCIA
            if rol in self.roles and rol != self.rol
        ]


class RolAdicional(ModeloBase):
    """
    Roles adicionales de una persona.

    Una persona puede ser simultáneamente:
    ADMIN + PROFESOR + ESTUDIANTE, etc.
    """

    perfil = models.ForeignKey(
        PerfilUsuario,
        on_delete=models.CASCADE,
        related_name='roles_adicionales',
    )

    rol = models.CharField(
        max_length=20,
        choices=PerfilUsuario.ROLES,
    )

    class Meta:
        verbose_name = 'perfil adicional'
        verbose_name_plural = 'perfiles adicionales'
        ordering = ['rol']

        constraints = [
            models.UniqueConstraint(
                fields=[
                    'perfil',
                    'rol',
                ],
                name='uq_perfil_rol_adicional',
            ),
        ]

    def clean(self):
        super().clean()

        if (
            self.perfil_id
            and self.rol == self.perfil.rol
        ):
            raise ValidationError({
                'rol': 'Ese rol ya es el rol principal de la persona.'
            })

    def __str__(self):
        return (
            f'{self.perfil.usuario.username} - '
            f'{self.get_rol_display()}'
        )