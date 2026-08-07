from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from core.models import ModeloBase


class Modalidad(ModeloBase):
    """Presencial, En linea, Semipresencial...

    Era un campo de texto libre en Carrera, y ya convivian 'Presencial' y
    'PRESENCIAL' como si fueran cosas distintas. Un catalogo se elige de una
    lista y no se escribe, que es justo lo que evita esa basura.
    """

    nombre = models.CharField(max_length=80, unique=True)
    descripcion = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = 'modalidad'
        verbose_name_plural = 'modalidades'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class Carrera(ModeloBase):
    nombre = models.CharField(max_length=200)
    codigo = models.CharField(max_length=30, unique=True)
    descripcion = models.TextField(blank=True)
    titulo_otorga = models.CharField(max_length=200, blank=True)
    modalidad = models.ForeignKey(
        Modalidad,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='carreras',
    )
    duracion_periodos = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class Malla(ModeloBase):
    carrera = models.ForeignKey(
        Carrera,
        on_delete=models.PROTECT,
        related_name='mallas',
    )
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
    malla = models.ForeignKey(
        Malla,
        on_delete=models.CASCADE,
        related_name='niveles',
    )
    numero = models.PositiveIntegerField()
    nombre = models.CharField(max_length=100)

    class Meta:
        ordering = ['malla', 'numero']
        unique_together = [('malla', 'numero')]

    def __str__(self):
        return f'{self.malla} / Nivel {self.numero}'


class Materia(ModeloBase):
    codigo = models.CharField(max_length=30, unique=True)
    nombre = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True)
    creditos = models.PositiveIntegerField(default=0)
    horas = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['nombre']

    def __str__(self):
        return f'{self.codigo} - {self.nombre}'


class MateriaMalla(ModeloBase):
    malla = models.ForeignKey(
        Malla,
        on_delete=models.CASCADE,
        related_name='materias_malla',
    )
    nivel = models.ForeignKey(
        NivelMalla,
        on_delete=models.PROTECT,
        related_name='materias_malla',
    )
    materia = models.ForeignKey(
        Materia,
        on_delete=models.PROTECT,
        related_name='mallas',
    )
    orden = models.PositiveIntegerField(default=1)
    obligatoria = models.BooleanField(default=True)

    class Meta:
        ordering = [
            'malla',
            'nivel__numero',
            'orden',
            'materia__nombre',
        ]
        unique_together = [('malla', 'materia')]

    def __str__(self):
        return f'{self.malla} / {self.materia}'

    @property
    def etiqueta(self):
        """
        Como se nombra una materia curricular en TODO el sistema:
        de qué malla es, en qué nivel va y cuál es.

        Sin esto, en los desplegables y listados aparecían materias
        sueltas sin saber a qué plan de estudios pertenecen.
        """
        return (
            f'{self.malla.codigo} / Nivel {self.nivel.numero} - '
            f'{self.materia.codigo} {self.materia.nombre}'
        )

    @property
    def etiqueta_corta(self):
        """
        La misma idea para cuando la malla ya está clara
        por el contexto.
        """
        return f'Nivel {self.nivel.numero} - {self.materia.nombre}'

    def predecesoras_activas(self):
        """
        Las materias que hay que aprobar antes de tomar esta.
        """
        return MateriaMalla.objects.filter(
            sucesoras__materia_malla=self,
            sucesoras__activo=True,
            activo=True,
        ).select_related(
            'materia',
            'nivel',
        ).distinct()


class MateriaMallaPredecesora(ModeloBase):
    """
    Requisito curricular: para tomar `materia_malla` hay que
    haber aprobado `predecesora`.

    Las dos viven en la misma malla y el requisito va en un
    nivel anterior, que es la regla con la que se arman las mallas.
    """

    materia_malla = models.ForeignKey(
        MateriaMalla,
        on_delete=models.CASCADE,
        related_name='predecesoras',
    )
    predecesora = models.ForeignKey(
        MateriaMalla,
        on_delete=models.CASCADE,
        related_name='sucesoras',
    )

    class Meta:
        verbose_name = 'predecesora'
        verbose_name_plural = 'predecesoras'
        ordering = [
            'materia_malla__nivel__numero',
            'materia_malla__materia__nombre',
        ]
        unique_together = [
            ('materia_malla', 'predecesora'),
        ]

    def __str__(self):
        return (
            f'{self.materia_malla.materia} requiere '
            f'{self.predecesora.materia}'
        )

    def genera_ciclo(self):
        """
        True si el requisito cierra un círculo, por ejemplo:

            A requiere B
            B requiere A

        Recorre la cadena de requisitos hacia arriba.
        """
        if not self.materia_malla_id or not self.predecesora_id:
            return False

        pendientes = [self.predecesora_id]
        vistos = set()

        while pendientes:
            actual = pendientes.pop()

            if actual == self.materia_malla_id:
                return True

            if actual in vistos:
                continue

            vistos.add(actual)

            arriba = MateriaMallaPredecesora.objects.filter(
                materia_malla_id=actual,
                activo=True,
            )

            if self.pk:
                arriba = arriba.exclude(pk=self.pk)

            pendientes.extend(
                arriba.values_list(
                    'predecesora_id',
                    flat=True,
                )
            )

        return False

    def clean(self):
        super().clean()

        if not self.materia_malla_id or not self.predecesora_id:
            return

        if self.materia_malla_id == self.predecesora_id:
            raise ValidationError(
                'Una materia no puede ser requisito de sí misma.'
            )

        if self.materia_malla.malla_id != self.predecesora.malla_id:
            raise ValidationError(
                'El requisito debe pertenecer a la misma malla.'
            )

        if (
            self.predecesora.nivel.numero
            >= self.materia_malla.nivel.numero
        ):
            raise ValidationError(
                'El requisito debe estar en un nivel anterior '
                'al de la materia.'
            )

        if self.genera_ciclo():
            raise ValidationError(
                'Ese requisito cierra un círculo: la materia '
                'terminaría siendo requisito de sí misma.'
            )


class PeriodoAcademico(ModeloBase):
    nombre = models.CharField(max_length=150)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    activo_matricula = models.BooleanField(default=False)

    class Meta:
        ordering = ['-fecha_inicio']

    def __str__(self):
        return self.nombre


class MallaPeriodo(ModeloBase):
    """
    La malla puesta en marcha en un periodo. Nada más:
    conecta las dos cosas.

    Es el escalón intermedio del recorrido:

        malla
        -> malla en el periodo
        -> niveles y asignaturas
        -> materias

    Al entrar se ven TODOS los niveles y asignaturas de la malla.

    Esta conexión no filtra nada, solo dice sobre qué periodo
    se está trabajando y cómo se le llama:

        Software 2026-1 matutina

    Lo operativo de cada curso, como profesor y estudiantes,
    vive en la Seccion.
    """

    periodo = models.ForeignKey(
        PeriodoAcademico,
        on_delete=models.PROTECT,
        related_name='mallas_periodo',
    )
    malla = models.ForeignKey(
        Malla,
        on_delete=models.PROTECT,
        related_name='periodos',
    )
    nombre = models.CharField(
        max_length=150,
        blank=True,
        help_text=(
            'Cómo se llama esta malla en el periodo. '
            'Si lo dejas vacío se usa el nombre de la malla.'
        ),
    )

    class Meta:
        verbose_name = 'malla en el periodo'
        verbose_name_plural = 'mallas en el periodo'
        ordering = [
            '-periodo__fecha_inicio',
            'malla__nombre',
        ]
        # Una misma malla se puede abrir VARIAS veces en el mismo periodo, y
        # cada apertura lleva su nombre: 'Software 2026-1 matutina' y
        # 'Software 2026-1 vespertina' son dos. Lo unico que no se repite es el
        # nombre dentro de la misma malla y periodo.
        unique_together = [
            ('periodo', 'malla', 'nombre'),
        ]

    def __str__(self):
        return f'{self.nombre_visible} ({self.periodo})'

    @property
    def nombre_visible(self):
        """
        El nombre propio si lo pusieron;
        si no, el nombre de la malla.
        """
        return self.nombre or self.malla.nombre

    def niveles(self):
        """
        Todos los niveles de la malla.

        La conexión con el periodo no recorta los niveles.
        """
        return NivelMalla.objects.filter(
            malla=self.malla,
            activo=True,
        )

    def asignaturas_disponibles(self):
        """
        Las asignaturas de la malla a las que todavía no
        se les creó materia en este periodo.

        Es lo que se ofrece al crear una materia.
        """
        ya_creadas = MateriaPeriodo.objects.filter(
            malla_periodo=self,
            activo=True,
        ).values(
            'materia_malla_id',
        )

        return MateriaMalla.objects.filter(
            malla=self.malla,
            activo=True,
        ).exclude(
            pk__in=ya_creadas,
        ).select_related(
            'materia',
            'nivel',
        )


class MateriaPeriodo(ModeloBase):
    """
    La materia que de verdad se dicta:

        Materia = MallaPeriodo + AsignaturaMalla

    En este proyecto la AsignaturaMalla se llama MateriaMalla
    y la asignatura del catálogo se llama Materia; por eso el
    modelo lleva este nombre.

    NO repite periodo, malla, asignatura ni nivel.

    Todo eso se lee a través de las dos relaciones, que es
    justamente lo que evita que los datos se contradigan.
    """

    malla_periodo = models.ForeignKey(
        MallaPeriodo,
        on_delete=models.CASCADE,
        related_name='materias',
    )
    materia_malla = models.ForeignKey(
        MateriaMalla,
        on_delete=models.PROTECT,
        related_name='materias_periodo',
        verbose_name='asignatura de la malla',
    )

    class Meta:
        verbose_name = 'materia del periodo'
        verbose_name_plural = 'materias del periodo'
        ordering = [
            'malla_periodo',
            'materia_malla__nivel__numero',
            'materia_malla__orden',
            'materia_malla__materia__nombre',
        ]
        unique_together = [
            ('malla_periodo', 'materia_malla'),
        ]

    def __str__(self):
        return f'{self.asignatura} - {self.malla_periodo}'

    # Todo lo de abajo se deriva.
    # No hay una sola copia guardada.

    @property
    def periodo(self):
        return self.malla_periodo.periodo

    @property
    def malla(self):
        return self.malla_periodo.malla

    @property
    def asignatura(self):
        return self.materia_malla.materia

    @property
    def nivel(self):
        return self.materia_malla.nivel

    def clean(self):
        super().clean()

        if not self.malla_periodo_id or not self.materia_malla_id:
            return

        if (
            self.materia_malla.malla_id
            != self.malla_periodo.malla_id
        ):
            raise ValidationError(
                'Esa asignatura es de otra malla: debe ser de '
                'la malla que este periodo tiene abierta.'
            )


class InscripcionMalla(ModeloBase):
    ACTIVA = 1
    RETIRADA = 2
    FINALIZADA = 3

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
    malla = models.ForeignKey(
        Malla,
        on_delete=models.PROTECT,
        related_name='inscripciones',
    )
    periodo = models.ForeignKey(
        PeriodoAcademico,
        on_delete=models.PROTECT,
        related_name='inscripciones',
    )
    fecha_inscripcion = models.DateField(auto_now_add=True)

    estado = models.PositiveSmallIntegerField(
        choices=ESTADOS,
        default=ACTIVA,
    )

    class Meta:
        ordering = ['-fecha_inscripcion']
        unique_together = [
            ('estudiante', 'malla', 'periodo'),
        ]

    def __str__(self):
        return f'{self.estudiante} - {self.malla}'

    def materias_aprobadas(self):
        return set(
            RecordAcademico.objects.filter(
                estudiante_id=self.estudiante_id,
                aprobado=True,
                activo=True,
            ).values_list(
                'materia_malla_id',
                flat=True,
            )
        )

    def predecesoras_pendientes(self, materia_malla):
        aprobadas = self.materias_aprobadas()

        return [
            requisito
            for requisito in materia_malla.predecesoras_activas()
            if requisito.pk not in aprobadas
        ]

    def puede_tomar_materia(self, materia_malla):
        return not self.predecesoras_pendientes(materia_malla)


class RecordAcademico(ModeloBase):
    """
    Historial consolidado de una materia de la malla.

    Es la fuente única con la que se resuelven las predecesoras:
    cuenta lo aprobado alguna vez, no solamente lo del periodo
    en curso.
    """

    estudiante = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='record_academico',
    )
    materia_malla = models.ForeignKey(
        MateriaMalla,
        on_delete=models.PROTECT,
        related_name='records',
    )
    periodo = models.ForeignKey(
        PeriodoAcademico,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='records',
        help_text='Periodo en que la aprobó o reprobó.',
    )
    nota = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    aprobado = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'record académico'
        verbose_name_plural = 'records académicos'
        ordering = [
            'estudiante',
            'materia_malla__nivel__numero',
        ]
        unique_together = [
            ('estudiante', 'materia_malla'),
        ]

    def __str__(self):
        estado = 'aprobada' if self.aprobado else 'no aprobada'

        return (
            f'{self.estudiante} - '
            f'{self.materia_malla.materia} ({estado})'
        )


class ProfesorMateria(ModeloBase):
    profesor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='materias_asignadas',
    )
    materia_malla = models.ForeignKey(
        MateriaMalla,
        on_delete=models.PROTECT,
        related_name='profesores',
    )
    periodo = models.ForeignKey(
        PeriodoAcademico,
        on_delete=models.PROTECT,
        related_name='profesores_materia',
    )
    fecha_asignacion = models.DateField(auto_now_add=True)

    class Meta:
        ordering = [
            'periodo',
            'materia_malla__materia__nombre',
        ]
        unique_together = [
            ('profesor', 'materia_malla', 'periodo'),
        ]

    def __str__(self):
        return f'{self.profesor} - {self.materia_malla}'