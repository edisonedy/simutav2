from django.conf import settings
from django.db import models

from core.models import Institucion, ModeloBase


class Carrera(ModeloBase):
    institucion = models.ForeignKey(Institucion, on_delete=models.PROTECT, related_name='carreras')
    nombre = models.CharField(max_length=200)
    codigo = models.CharField(max_length=30)
    descripcion = models.TextField(blank=True)
    titulo_otorga = models.CharField(max_length=200, blank=True)
    modalidad = models.CharField(max_length=80, blank=True)
    duracion_periodos = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['nombre']
        unique_together = [('institucion', 'codigo')]

    def __str__(self):
        return self.nombre


class Malla(ModeloBase):
    carrera = models.ForeignKey(Carrera, on_delete=models.PROTECT, related_name='mallas')
    nombre = models.CharField(max_length=200)
    codigo = models.CharField(max_length=30)
    fecha_inicio = models.DateField(null=True, blank=True)
    fecha_fin = models.DateField(null=True, blank=True)
    vigente = models.BooleanField(default=True)

    class Meta:
        ordering = ['carrera__nombre', 'nombre']
        unique_together = [('carrera', 'codigo')]

    def __str__(self):
        return f'{self.carrera} - {self.nombre}'


class NivelMalla(ModeloBase):
    malla = models.ForeignKey(Malla, on_delete=models.CASCADE, related_name='niveles')
    numero = models.PositiveIntegerField()
    nombre = models.CharField(max_length=100)

    class Meta:
        ordering = ['malla', 'numero']
        unique_together = [('malla', 'numero')]

    def __str__(self):
        return f'{self.malla} / Nivel {self.numero}'


class Materia(ModeloBase):
    institucion = models.ForeignKey(Institucion, on_delete=models.PROTECT, related_name='materias')
    codigo = models.CharField(max_length=30)
    nombre = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True)
    creditos = models.PositiveIntegerField(default=0)
    horas = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['nombre']
        unique_together = [('institucion', 'codigo')]

    def __str__(self):
        return f'{self.codigo} - {self.nombre}'


class MateriaMalla(ModeloBase):
    malla = models.ForeignKey(Malla, on_delete=models.CASCADE, related_name='materias_malla')
    nivel = models.ForeignKey(NivelMalla, on_delete=models.PROTECT, related_name='materias_malla')
    materia = models.ForeignKey(Materia, on_delete=models.PROTECT, related_name='mallas')
    orden = models.PositiveIntegerField(default=1)
    obligatoria = models.BooleanField(default=True)

    class Meta:
        ordering = ['malla', 'nivel__numero', 'orden', 'materia__nombre']
        unique_together = [('malla', 'materia')]

    def __str__(self):
        return f'{self.malla} / {self.materia}'


class PeriodoAcademico(ModeloBase):
    institucion = models.ForeignKey(Institucion, on_delete=models.PROTECT, related_name='periodos')
    nombre = models.CharField(max_length=150)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    activo_matricula = models.BooleanField(default=False)

    class Meta:
        ordering = ['-fecha_inicio']

    def __str__(self):
        return self.nombre


class InscripcionMalla(ModeloBase):
    ACTIVA = 'ACTIVA'
    RETIRADA = 'RETIRADA'
    FINALIZADA = 'FINALIZADA'
    ESTADOS = [
        (ACTIVA, 'Activa'),
        (RETIRADA, 'Retirada'),
        (FINALIZADA, 'Finalizada'),
    ]

    estudiante = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='inscripciones_malla',
    )
    malla = models.ForeignKey(Malla, on_delete=models.PROTECT, related_name='inscripciones')
    periodo = models.ForeignKey(PeriodoAcademico, on_delete=models.PROTECT, related_name='inscripciones')
    fecha_inscripcion = models.DateField(auto_now_add=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default=ACTIVA)

    class Meta:
        ordering = ['-fecha_inscripcion']
        unique_together = [('estudiante', 'malla', 'periodo')]

    def __str__(self):
        return f'{self.estudiante} - {self.malla}'


class ProfesorMateria(ModeloBase):
    profesor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='materias_asignadas',
    )
    materia_malla = models.ForeignKey(MateriaMalla, on_delete=models.PROTECT, related_name='profesores')
    periodo = models.ForeignKey(PeriodoAcademico, on_delete=models.PROTECT, related_name='profesores_materia')
    fecha_asignacion = models.DateField(auto_now_add=True)

    class Meta:
        ordering = ['periodo', 'materia_malla__materia__nombre']
        unique_together = [('profesor', 'materia_malla', 'periodo')]

    def __str__(self):
        return f'{self.profesor} - {self.materia_malla}'

