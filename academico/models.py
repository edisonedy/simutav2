from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from core.models import ModeloBase


# ============================================================
# MODALIDAD
# ============================================================

class Modalidad(ModeloBase):
    nombre = models.CharField(
        max_length=100,
        unique=True,
    )

    descripcion = models.TextField(
        blank=True,
    )

    class Meta:
        verbose_name = 'modalidad'
        verbose_name_plural = 'modalidades'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


# ============================================================
# CARRERA
# ============================================================

class Carrera(ModeloBase):
    nombre = models.CharField(
        max_length=200,
    )

    codigo = models.CharField(
        max_length=30,
        unique=True,
    )

    descripcion = models.TextField(
        blank=True,
    )

    titulo_otorga = models.CharField(
        max_length=200,
        blank=True,
    )

    modalidad = models.ForeignKey(
        Modalidad,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='carreras',
    )

    duracion_periodos = models.PositiveIntegerField(
        default=0,
    )

    class Meta:
        verbose_name = 'carrera'
        verbose_name_plural = 'carreras'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre

# ============================================================
# CATÁLOGO GENERAL DE MATERIAS
# ============================================================

class Materia(ModeloBase):
    """
    Catálogo general de asignaturas.

    Ejemplos:
        Finanzas
        Contabilidad
        Marketing
        Talento Humano
    """

    codigo = models.CharField(
        max_length=30,
        unique=True,
    )

    nombre = models.CharField(
        max_length=200,
    )

    descripcion = models.TextField(
        blank=True,
    )

    creditos = models.PositiveIntegerField(
        default=0,
    )

    horas = models.PositiveIntegerField(
        default=0,
    )

    class Meta:
        verbose_name = 'materia'
        verbose_name_plural = 'materias'
        ordering = ['nombre']

    def __str__(self):
        return f'{self.codigo} - {self.nombre}'


# ============================================================
# MALLA
# ============================================================

class Malla(ModeloBase):
    """
    Plan de estudios de una carrera.

    Ejemplo:
        Administración 2026
    """

    carrera = models.ForeignKey(
        Carrera,
        on_delete=models.PROTECT,
        related_name='mallas',
    )

    nombre = models.CharField(
        max_length=200,
    )

    codigo = models.CharField(
        max_length=30,
    )

    fecha_inicio = models.DateField(
        null=True,
        blank=True,
    )

    fecha_fin = models.DateField(
        null=True,
        blank=True,
    )

    vigente = models.BooleanField(
        default=True,
    )

    class Meta:
        verbose_name = 'malla'
        verbose_name_plural = 'mallas'

        ordering = [
            'carrera__nombre',
            'nombre',
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    'carrera',
                    'codigo',
                ],
                name='uq_malla_carrera_codigo',
            ),
        ]

    def __str__(self):
        return f'{self.carrera} - {self.nombre}'

    def clean(self):
        super().clean()

        if (
            self.fecha_inicio
            and self.fecha_fin
            and self.fecha_fin < self.fecha_inicio
        ):
            raise ValidationError({
                'fecha_fin': (
                    'La fecha final no puede ser '
                    'anterior a la fecha inicial.'
                )
            })

# ============================================================
# NIVEL DE LA MALLA
# ============================================================

class NivelMalla(ModeloBase):
    """
    Sirve únicamente para organizar las materias
    dentro de la malla.

    Ejemplos:
        Nivel 1
        Nivel 2
        Nivel 3
    """

    malla = models.ForeignKey(
        Malla,
        on_delete=models.CASCADE,
        related_name='niveles',
    )

    numero = models.PositiveIntegerField()

    nombre = models.CharField(
        max_length=100,
        blank=True,
    )

    class Meta:
        verbose_name = 'nivel de malla'
        verbose_name_plural = 'niveles de malla'

        ordering = [
            'malla',
            'numero',
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    'malla',
                    'numero',
                ],
                name='uq_malla_nivel',
            ),
        ]

    def __str__(self):
        return self.nombre or f'Nivel {self.numero}'


# ============================================================
# MATERIA DENTRO DE UNA MALLA
# ============================================================

class MateriaMalla(ModeloBase):
    """
    Relaciona una materia del catálogo con una malla.

    Ejemplo:

        Malla:
            Administración 2026

        Nivel:
            Nivel 2

        Materia:
            Finanzas
    """

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
        related_name='materias_malla',
    )

    orden = models.PositiveIntegerField(
        default=1,
    )

    obligatoria = models.BooleanField(
        default=True,
    )

    class Meta:
        verbose_name = 'materia de malla'
        verbose_name_plural = 'materias de malla'

        ordering = [
            'malla',
            'nivel__numero',
            'orden',
            'materia__nombre',
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    'malla',
                    'materia',
                ],
                name='uq_malla_materia',
            ),
        ]

    def __str__(self):
        return (
            f'{self.materia.nombre} - '
            f'Nivel {self.nivel.numero}'
        )

    @property
    def nombre(self):
        return self.materia.nombre

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

    def clean(self):
        super().clean()

        if not self.malla_id or not self.nivel_id:
            return

        if self.nivel.malla_id != self.malla_id:
            raise ValidationError({
                'nivel': (
                    'El nivel seleccionado no pertenece '
                    'a esta malla.'
                )
            })

    def predecesoras_activas(self):
        ids = self.predecesoras.filter(
            activo=True,
        ).values_list(
            'predecesora_id',
            flat=True,
        )

        return MateriaMalla.objects.filter(
            id__in=ids,
            activo=True,
        ).select_related(
            'materia',
            'nivel',
        ).order_by(
            'nivel__numero',
            'orden',
            'materia__nombre',
        )


# ============================================================
# PREDECESORAS DE UNA MATERIA DE MALLA
# ============================================================

class MateriaMallaPredecesora(ModeloBase):
    """
    Define los requisitos anteriores de una materia
    dentro de la malla.

    Ejemplo:

        Finanzas II
            ↓ requiere
        Finanzas I


    Esto solamente configura la estructura de la malla.

    No estamos creando:
        - récord académico
        - aprobación de materias
        - matrícula académica
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
        verbose_name = 'materia predecesora'
        verbose_name_plural = 'materias predecesoras'

        ordering = [
            'materia_malla__nivel__numero',
            'materia_malla__materia__nombre',
            'predecesora__nivel__numero',
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    'materia_malla',
                    'predecesora',
                ],
                name='uq_materia_predecesora',
            ),
        ]

    def __str__(self):
        return (
            f'{self.materia_malla.materia.nombre} '
            f'requiere '
            f'{self.predecesora.materia.nombre}'
        )

    def genera_ciclo(self):
        """
        True si el requisito cierra un círculo, por ejemplo:

            A requiere B
            B requiere A

        La regla de niveles ya lo impide, pero la detección no depende de
        ella: si mañana se relaja el nivel, una malla imposible de cursar
        seguiría sin poder guardarse.
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

        if (
            not self.materia_malla_id
            or not self.predecesora_id
        ):
            return

        # --------------------------------------------
        # Una materia no puede ser predecesora
        # de ella misma.
        # --------------------------------------------

        if (
            self.materia_malla_id
            == self.predecesora_id
        ):
            raise ValidationError({
                'predecesora': (
                    'Una materia no puede ser '
                    'predecesora de sí misma.'
                )
            })

        # --------------------------------------------
        # Ambas tienen que pertenecer a la misma malla.
        # --------------------------------------------

        if (
            self.materia_malla.malla_id
            != self.predecesora.malla_id
        ):
            raise ValidationError({
                'predecesora': (
                    'La materia predecesora debe '
                    'pertenecer a la misma malla.'
                )
            })

        # --------------------------------------------
        # La predecesora debe estar en un nivel anterior.
        # --------------------------------------------

        if (
            self.predecesora.nivel.numero
            >= self.materia_malla.nivel.numero
        ):
            raise ValidationError({
                'predecesora': (
                    'La materia predecesora debe estar '
                    'en un nivel anterior.'
                )
            })

        if self.genera_ciclo():
            raise ValidationError({
                'predecesora': (
                    'Ese requisito cierra un círculo: la materia '
                    'terminaría siendo requisito de sí misma.'
                )
            })


# ============================================================
# PERIODO
# ============================================================

class PeriodoAcademico(ModeloBase):
    """
    El periodo solamente sirve para organizar
    el uso de materias y simulaciones.

    SimutaV2 no será un SGA.

    Ejemplos:
        A26
        B26
        A27
    """

    nombre = models.CharField(
        max_length=100,
        unique=True,
    )

    fecha_inicio = models.DateField()

    fecha_fin = models.DateField()

    class Meta:
        verbose_name = 'periodo'
        verbose_name_plural = 'periodos'

        ordering = [
            '-fecha_inicio',
        ]

    def __str__(self):
        return self.nombre

    def clean(self):
        super().clean()

        if (
            self.fecha_inicio
            and self.fecha_fin
            and self.fecha_fin < self.fecha_inicio
        ):
            raise ValidationError({
                'fecha_fin': (
                    'La fecha final no puede ser '
                    'anterior a la fecha inicial.'
                )
            })


# ============================================================
# MALLA ABIERTA EN UN PERIODO
# ============================================================

class MallaPeriodo(ModeloBase):
    periodo = models.ForeignKey(
        PeriodoAcademico,
        on_delete=models.PROTECT,
        related_name='mallas_periodo',
    )

    malla = models.ForeignKey(
        Malla,
        on_delete=models.PROTECT,
        related_name='mallas_periodo',
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
            'periodo',
            'malla__nombre',
            'nombre',
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    'periodo',
                    'malla',
                    'nombre',
                ],
                name='uq_periodo_malla_nombre',
            ),
        ]

    def __str__(self):
        return f'{self.nombre} - {self.periodo}'

    @classmethod
    def abrir(cls, malla, periodo, nombre='', usuario=None):
        """Abre una malla en un periodo, o devuelve la apertura que ya existe.

        Es el atajo que usan los sembradores y los cargadores de casos: una
        malla se puede abrir varias veces en el mismo periodo (matutina,
        vespertina...), asi que la apertura se identifica por su nombre.
        """
        objeto, _ = cls.objects.get_or_create(
            periodo=periodo,
            malla=malla,
            nombre=nombre or '',
            defaults={'usuario_creacion': usuario},
        )
        return objeto

    @property
    def nombre_visible(self):
        """El nombre propio si lo pusieron; si no, el nombre de la malla."""
        return self.nombre or self.malla.nombre

    def niveles(self):
        return self.malla.niveles.filter(
            activo=True,
        ).order_by(
            'numero',
        )

    def materias_creadas(self):
        return self.materias.filter(
            activo=True,
        ).select_related(
            'materia_malla',
            'materia_malla__materia',
            'materia_malla__nivel',
        ).order_by(
            'materia_malla__nivel__numero',
            'materia_malla__orden',
            'materia_malla__materia__nombre',
        )

    def asignaturas_disponibles(self):
        creadas = self.materias.filter(
            activo=True,
        ).values_list(
            'materia_malla_id',
            flat=True,
        )

        return self.malla.materias_malla.filter(
            activo=True,
            nivel__activo=True,
        ).exclude(
            id__in=creadas,
        ).select_related(
            'materia',
            'nivel',
        ).order_by(
            'nivel__numero',
            'orden',
            'materia__nombre',
        )

    def estudiantes_activos(self):
        return self.inscripciones.filter(
            activo=True,
            estado=InscripcionMalla.ACTIVA,
        ).select_related(
            'estudiante',
        )


# ============================================================
# MATERIA DEL PERIODO
# ============================================================

class MateriaPeriodo(ModeloBase):
    """
    Materia activa dentro de SimutaV2.

    Ejemplo:

        MallaPeriodo:
            Administración 2026 - B26

        MateriaMalla:
            Finanzas


    Resultado:

        Finanzas - B26


    Esta materia tendrá:

        - Docente(s)
        - Casos
        - Juegos
        - Simulaciones
        - Resultados


    Los estudiantes NO se inscriben materia por materia.

    Si están inscritos en la MallaPeriodo mediante
    InscripcionMalla, pueden ver las materias activas
    de esa MallaPeriodo.
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
        verbose_name='asignatura',
    )

    # ========================================================
    # DOCENTES
    # ========================================================

    docentes = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='materias_como_docente',
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

        constraints = [
            models.UniqueConstraint(
                fields=[
                    'malla_periodo',
                    'materia_malla',
                ],
                name='uq_materia_periodo',
            ),
        ]

    def __str__(self):
        return (
            f'{self.materia_malla.materia.nombre} - '
            f'{self.malla_periodo.periodo.nombre}'
        )

    # ========================================================
    # PROPIEDADES
    # ========================================================

    @property
    def materia(self):
        return self.materia_malla.materia

    # 'asignatura' es como se llama la materia del catalogo cuando ya esta
    # colgada de una malla. Se mantiene el nombre porque asi la nombran las
    # pantallas y los sembradores.
    asignatura = materia

    @property
    def nombre(self):
        return self.materia_malla.materia.nombre

    @property
    def nivel(self):
        return self.materia_malla.nivel

    @property
    def malla(self):
        return self.malla_periodo.malla

    @property
    def periodo(self):
        return self.malla_periodo.periodo

    # ========================================================
    # DOCENTE
    # ========================================================

    def es_docente(self, usuario):
        if not usuario:
            return False

        if not usuario.is_authenticated:
            return False

        return self.docentes.filter(
            pk=usuario.pk,
        ).exists()

    # ========================================================
    # ESTUDIANTE
    # ========================================================

    def es_estudiante(self, usuario):
        """
        El estudiante puede acceder si tiene
        una InscripcionMalla activa en esta
        MallaPeriodo.
        """

        if not usuario:
            return False

        if not usuario.is_authenticated:
            return False

        return self.malla_periodo.inscripciones.filter(
            estudiante=usuario,
            estado=InscripcionMalla.ACTIVA,
            activo=True,
        ).exists()

    # ========================================================
    # ACCESO
    # ========================================================

    def puede_acceder(self, usuario):
        return (
            self.es_docente(usuario)
            or self.es_estudiante(usuario)
        )

    # ========================================================
    # VALIDACIÓN
    # ========================================================

    def clean(self):
        super().clean()

        if (
            not self.malla_periodo_id
            or not self.materia_malla_id
        ):
            return

        # La materia seleccionada tiene que pertenecer
        # a la misma malla de MallaPeriodo.
        if (
            self.materia_malla.malla_id
            != self.malla_periodo.malla_id
        ):
            raise ValidationError({
                'materia_malla': (
                    'La asignatura seleccionada '
                    'no pertenece a esta malla.'
                )
            })


# ============================================================
# INSCRIPCIÓN DEL ESTUDIANTE EN LA MALLA
# ============================================================

class InscripcionMalla(ModeloBase):
    """
    Relaciona al estudiante con una MallaPeriodo.

    NO es una matrícula académica tipo SGA.

    Su única finalidad es determinar qué conjunto
    de materias, casos y juegos puede visualizar
    el estudiante.


    Ejemplo:

        Juan
            ↓
        Administración 2026 - B26
            ↓

        puede ver:

            Contabilidad
            Finanzas
            Marketing
            etc.
    """

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

    malla_periodo = models.ForeignKey(
        MallaPeriodo,
        on_delete=models.CASCADE,
        related_name='inscripciones',
    )

    estado = models.PositiveSmallIntegerField(
        choices=ESTADOS,
        default=ACTIVA,
    )

    class Meta:
        verbose_name = 'inscripción en malla'
        verbose_name_plural = 'inscripciones en malla'

        ordering = [
            '-fecha_creacion',
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    'estudiante',
                    'malla_periodo',
                ],
                name='uq_estudiante_malla_periodo',
            ),
        ]

    def __str__(self):
        nombre = (
            self.estudiante.get_full_name()
            or self.estudiante.username
        )

        return (
            f'{nombre} - '
            f'{self.malla_periodo}'
        )

    # ========================================================
    # MATERIAS DEL ESTUDIANTE
    # ========================================================

    def materias(self):
        """
        Devuelve todas las materias activas
        de la MallaPeriodo.

        NO existe InscripcionMateria.
        """

        if (
            not self.activo
            or self.estado != self.ACTIVA
        ):
            return MateriaPeriodo.objects.none()

        return self.malla_periodo.materias.filter(
            activo=True,
        ).select_related(
            'materia_malla__materia',
            'materia_malla__nivel',
            'malla_periodo__periodo',
            'malla_periodo__malla',
        ).order_by(
            'materia_malla__nivel__numero',
            'materia_malla__orden',
            'materia_malla__materia__nombre',
        )

    # ========================================================
    # ACCESO A UNA MATERIA
    # ========================================================

    def tiene_acceso_materia(self, materia_periodo):
        if (
            not self.activo
            or self.estado != self.ACTIVA
        ):
            return False

        return (
            materia_periodo.activo
            and
            materia_periodo.malla_periodo_id
            == self.malla_periodo_id
        )


# ============================================================
# PROFESOR - MATERIA
# ============================================================

class ProfesorMateria(ModeloBase):
    """
    Relación general entre un profesor y una
    asignatura de una malla.

    NO depende del periodo.

    Ejemplo:

        Profesor:
            Carlos Pérez

        MateriaMalla:
            Finanzas
            Administración 2026
            Nivel 2

    Esto significa que Carlos está relacionado
    o habilitado para trabajar con esa materia.

    La asignación concreta por periodo se maneja
    mediante MateriaPeriodo.docentes.
    """

    profesor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='profesor_materias',
    )

    materia_malla = models.ForeignKey(
        MateriaMalla,
        on_delete=models.CASCADE,
        related_name='profesores',
    )

    class Meta:
        verbose_name = 'profesor de materia'
        verbose_name_plural = 'profesores de materias'

        ordering = [
            'materia_malla__malla__nombre',
            'materia_malla__nivel__numero',
            'materia_malla__materia__nombre',
            'profesor__last_name',
            'profesor__first_name',
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    'profesor',
                    'materia_malla',
                ],
                name='uq_profesor_materia_malla',
            ),
        ]

    def __str__(self):
        nombre = (
            self.profesor.get_full_name()
            or self.profesor.username
        )

        return (
            f'{nombre} - '
            f'{self.materia_malla.materia.nombre} - '
            f'Nivel {self.materia_malla.nivel.numero}'
        )