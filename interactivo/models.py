from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models import ModeloBase


class ActividadInteractiva(ModeloBase):
    """Un juego de una materia.

    Vive en la asignatura de la malla, igual que ActividadMateria: el docente
    crea los que quiera, sueltos por materia o colgados de un tema. Puede
    ademas amarrarse a un caso, y entonces hace de preparacion previa.
    """

    materia_malla = models.ForeignKey(
        'academico.MateriaMalla',
        on_delete=models.CASCADE,
        related_name='actividades_interactivas',
    )
    tema = models.ForeignKey(
        'simulador.TemaMateria',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='actividades_interactivas',
        help_text='Vacio cuando el juego abarca toda la materia.',
    )
    simulacion = models.ForeignKey(
        'simulador.Simulacion',
        on_delete=models.CASCADE,
        related_name='actividades_interactivas',
        null=True,
        blank=True,
        help_text='Si se elige un caso, el juego se exige antes de empezarlo.',
    )
    creador = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='actividades_interactivas_creadas',
    )
    motor = models.CharField(max_length=80, db_index=True)
    motor_version = models.CharField(max_length=20, default='1.0.0')
    titulo = models.CharField(max_length=250)
    instrucciones = models.TextField(blank=True, default='')
    configuracion = models.JSONField(default=dict, blank=True)
    orden = models.PositiveIntegerField(default=1)
    puntaje_minimo = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('70.00'),
    )
    intentos_permitidos = models.PositiveIntegerField(
        default=0,
        help_text='Cero significa intentos ilimitados.',
    )
    tiempo_limite_segundos = models.PositiveIntegerField(default=0)
    obligatoria = models.BooleanField(default=True)
    publicada = models.BooleanField(default=False)

    class Meta:
        ordering = ['materia_malla', 'tema__orden', 'orden', 'titulo']
        verbose_name = 'actividad interactiva'
        verbose_name_plural = 'actividades interactivas'

    def __str__(self):
        return self.titulo

    def clean(self):
        super().clean()
        if (
            self.tema_id
            and self.materia_malla_id
            and self.tema.materia_malla_id != self.materia_malla_id
        ):
            raise ValidationError('El tema debe pertenecer a la misma materia de la malla.')
        if (
            self.simulacion_id
            and self.materia_malla_id
            and self.simulacion.materia_malla_id != self.materia_malla_id
        ):
            raise ValidationError('El caso debe pertenecer a la misma materia de la malla.')

    @property
    def motor_instalado(self):
        from .plugins.registry import get_plugin
        return get_plugin(self.motor)

    @property
    def motor_nombre(self):
        """Como se llama el motor en pantalla. Si el plugin ya no esta
        instalado se muestra el codigo, en vez de reventar el listado."""
        from .plugins.base import PluginError
        from .plugins.registry import get_plugin
        try:
            return get_plugin(self.motor).nombre
        except PluginError:
            return self.motor

    def mejor_intento(self, estudiante):
        return self.intentos.filter(
            estudiante=estudiante,
            completado=True,
        ).order_by('-porcentaje', 'tiempo_segundos').first()

    def aprobada_por(self, estudiante):
        return self.intentos.filter(
            estudiante=estudiante,
            aprobado=True,
        ).exists()


class RecursoActividadInteractiva(ModeloBase):
    TIPO_IMAGEN = 'IMAGEN'
    TIPO_AUDIO = 'AUDIO'
    TIPO_VIDEO = 'VIDEO'
    TIPO_DOCUMENTO = 'DOCUMENTO'
    TIPOS = [
        (TIPO_IMAGEN, 'Imagen'),
        (TIPO_AUDIO, 'Audio'),
        (TIPO_VIDEO, 'Video'),
        (TIPO_DOCUMENTO, 'Documento'),
    ]

    actividad = models.ForeignKey(
        ActividadInteractiva,
        on_delete=models.CASCADE,
        related_name='recursos',
    )
    tipo = models.CharField(max_length=20, choices=TIPOS)
    nombre = models.CharField(max_length=200)
    archivo = models.FileField(upload_to='interactivo/recursos/%Y/%m/')
    descripcion = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['actividad', 'nombre']

    def __str__(self):
        return self.nombre


class IntentoActividadInteractiva(ModeloBase):
    EN_PROCESO = 'EN_PROCESO'
    APROBADO = 'APROBADO'
    NO_APROBADO = 'NO_APROBADO'
    ABANDONADO = 'ABANDONADO'
    ESTADOS = [
        (EN_PROCESO, 'En proceso'),
        (APROBADO, 'Aprobado'),
        (NO_APROBADO, 'No aprobado'),
        (ABANDONADO, 'Abandonado'),
    ]

    actividad = models.ForeignKey(
        ActividadInteractiva,
        on_delete=models.PROTECT,
        related_name='intentos',
    )
    estudiante = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='intentos_actividades_interactivas',
    )
    numero_intento = models.PositiveIntegerField(default=1)
    estado = models.CharField(
        max_length=20,
        choices=ESTADOS,
        default=EN_PROCESO,
    )
    fecha_inicio = models.DateTimeField(default=timezone.now)
    fecha_fin = models.DateTimeField(null=True, blank=True)
    tiempo_segundos = models.PositiveIntegerField(default=0)
    puntaje = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    puntaje_maximo = models.DecimalField(max_digits=8, decimal_places=2, default=100)
    porcentaje = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    aciertos = models.PositiveIntegerField(default=0)
    errores = models.PositiveIntegerField(default=0)
    total_elementos = models.PositiveIntegerField(default=0)
    completado = models.BooleanField(default=False)
    aprobado = models.BooleanField(default=False)
    respuesta = models.JSONField(default=dict, blank=True)
    detalle_resultado = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-fecha_inicio']
        constraints = [
            models.UniqueConstraint(
                fields=['actividad', 'estudiante', 'numero_intento'],
                name='intento_interactivo_numero_unico',
            ),
        ]

    def __str__(self):
        return f'{self.estudiante} - {self.actividad} - intento {self.numero_intento}'


class EventoActividadInteractiva(ModeloBase):
    intento = models.ForeignKey(
        IntentoActividadInteractiva,
        on_delete=models.CASCADE,
        related_name='eventos',
    )
    verbo = models.CharField(max_length=50)
    elemento_id = models.CharField(max_length=120, blank=True, default='')
    tiempo_segundos = models.PositiveIntegerField(default=0)
    datos = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['fecha_creacion', 'pk']

    def __str__(self):
        return f'{self.intento_id} - {self.verbo}'
