from django.conf import settings
from django.db import models
from django.utils import timezone

from academico.models import MateriaMalla
from core.models import ModeloBase


class PerfilMateriaIA(ModeloBase):
    materia_malla = models.OneToOneField(
        MateriaMalla,
        on_delete=models.CASCADE,
        related_name='perfil_ia',
    )
    rol_profesional = models.CharField(max_length=200, blank=True, default='')
    enfoque = models.TextField(blank=True, default='')
    competencias = models.JSONField(default=list, blank=True)
    resultados_aprendizaje = models.JSONField(default=list, blank=True)
    temas_clave = models.JSONField(default=list, blank=True)
    conceptos_clave = models.JSONField(default=list, blank=True)
    indicadores_sugeridos = models.JSONField(default=list, blank=True)
    restricciones_contexto = models.TextField(blank=True, default='')
    criterios_calidad = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ['materia_malla__materia__nombre']
        verbose_name = 'perfil IA de materia'
        verbose_name_plural = 'perfiles IA de materias'

    def __str__(self):
        return f'Perfil IA - {self.materia_malla}'


class PlantillaSimulacion(ModeloBase):
    TIPO_GLOBAL = 'GLOBAL'
    TIPO_MATERIA = 'MATERIA'
    TIPOS_PLANTILLA = [
        (TIPO_GLOBAL, 'Global'),
        (TIPO_MATERIA, 'Por materia'),
    ]

    nombre = models.CharField(max_length=200)
    codigo = models.CharField(max_length=60, unique=True)
    tipo = models.CharField(max_length=20, choices=TIPOS_PLANTILLA, default=TIPO_GLOBAL)
    descripcion = models.TextField(blank=True, default='')
    materia_malla = models.ForeignKey(
        MateriaMalla,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='plantillas_simulacion',
    )
    maximo_decisiones = models.PositiveIntegerField(default=3)
    tiempo_estimado = models.PositiveIntegerField(default=30)
    nivel_dificultad = models.CharField(max_length=20, blank=True, default='MEDIA')
    rol_base = models.CharField(max_length=200, blank=True, default='Responsable de decision')
    contexto_base = models.TextField(blank=True, default='')
    objetivo_base = models.TextField(blank=True, default='')
    resultado_base = models.TextField(blank=True, default='')
    instrucciones_ia = models.TextField(blank=True, default='')
    version = models.PositiveIntegerField(default=1)
    es_predeterminada = models.BooleanField(default=False)

    class Meta:
        ordering = ['tipo', 'nombre']

    def __str__(self):
        return f'{self.nombre} v{self.version}'


class PlantillaRonda(ModeloBase):
    plantilla = models.ForeignKey(PlantillaSimulacion, on_delete=models.CASCADE, related_name='rondas')
    numero = models.PositiveIntegerField()
    titulo = models.CharField(max_length=150)
    proposito = models.TextField(blank=True, default='')
    consigna_base = models.TextField(blank=True, default='')
    opciones_decision = models.JSONField(default=list, blank=True)
    etiqueta_decision = models.CharField(max_length=120, blank=True, default='Decision')
    etiqueta_justificacion = models.CharField(max_length=120, blank=True, default='Justificacion')

    class Meta:
        ordering = ['plantilla', 'numero']
        unique_together = [('plantilla', 'numero')]

    def __str__(self):
        return f'{self.plantilla} / Ronda {self.numero}: {self.titulo}'


class PlantillaIndicador(ModeloBase):
    plantilla = models.ForeignKey(PlantillaSimulacion, on_delete=models.CASCADE, related_name='indicadores')
    codigo = models.CharField(max_length=50)
    nombre = models.CharField(max_length=150)
    valor_inicial = models.DecimalField(max_digits=12, decimal_places=2, default=50)
    valor_minimo = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    valor_maximo = models.DecimalField(max_digits=12, decimal_places=2, default=100)
    direccion_optima = models.CharField(max_length=10, default='ALTO')
    es_critico = models.BooleanField(default=False)
    unidad = models.CharField(max_length=50, blank=True, default='pts')

    class Meta:
        ordering = ['plantilla', 'nombre']
        unique_together = [('plantilla', 'codigo')]

    def __str__(self):
        return f'{self.plantilla} / {self.codigo}'


class PlantillaRestriccion(ModeloBase):
    plantilla = models.ForeignKey(PlantillaSimulacion, on_delete=models.CASCADE, related_name='restricciones')
    descripcion = models.TextField()
    codigo_indicador = models.CharField(max_length=50)
    operador = models.CharField(max_length=5, default='>=')
    valor_limite = models.DecimalField(max_digits=12, decimal_places=2)
    penalizacion = models.DecimalField(max_digits=5, decimal_places=2, default=10)

    class Meta:
        ordering = ['plantilla', 'codigo_indicador']

    def __str__(self):
        return f'{self.plantilla} / {self.codigo_indicador} {self.operador} {self.valor_limite}'


class PlantillaConcepto(ModeloBase):
    ronda = models.ForeignKey(PlantillaRonda, on_delete=models.CASCADE, related_name='conceptos')
    nombre = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True, default='')
    regla_evaluacion = models.JSONField(default=dict, blank=True)
    peso = models.DecimalField(max_digits=5, decimal_places=2)
    impacto_si_cumple = models.JSONField(default=dict, blank=True)
    impacto_si_falta = models.JSONField(default=dict, blank=True)
    retroalimentacion_si_cumple = models.TextField(blank=True, default='')
    retroalimentacion_si_falta = models.TextField(blank=True, default='')
    es_critico = models.BooleanField(default=False)

    class Meta:
        ordering = ['ronda', 'nombre']
        unique_together = [('ronda', 'nombre')]

    def __str__(self):
        return f'{self.ronda} / {self.nombre}'


class Simulacion(ModeloBase):
    TIPO_SIN_IA_ARBOL = 'SIN_IA_ARBOL'
    TIPO_CON_IA_DINAMICA = 'CON_IA_DINAMICA'
    TIPOS_SIMULACION = [
        (TIPO_SIN_IA_ARBOL, 'Sin IA - Arbol de decisiones'),
        (TIPO_CON_IA_DINAMICA, 'Con IA - Simulacion dinamica'),
    ]

    DIFICULTAD_BASICA = 'BASICA'
    DIFICULTAD_MEDIA = 'MEDIA'
    DIFICULTAD_AVANZADA = 'AVANZADA'
    DIFICULTADES = [
        (DIFICULTAD_BASICA, 'Basica'),
        (DIFICULTAD_MEDIA, 'Media'),
        (DIFICULTAD_AVANZADA, 'Avanzada'),
    ]
    AYUDA_BAJA = 'BAJA'
    AYUDA_MEDIA = 'MEDIA'
    AYUDA_ALTA = 'ALTA'
    NIVELES_AYUDA = [
        (AYUDA_BAJA, 'Baja'),
        (AYUDA_MEDIA, 'Media'),
        (AYUDA_ALTA, 'Alta'),
    ]
    BORRADOR = 'BORRADOR'
    PUBLICADA = 'PUBLICADA'
    ARCHIVADA = 'ARCHIVADA'
    ESTADOS = [
        (BORRADOR, 'Borrador'),
        (PUBLICADA, 'Publicada'),
        (ARCHIVADA, 'Archivada'),
    ]

    materia_malla = models.ForeignKey(MateriaMalla, on_delete=models.PROTECT, related_name='simulaciones')
    plantilla_origen = models.ForeignKey(
        PlantillaSimulacion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='simulaciones_generadas',
    )
    perfil_materia_ia = models.ForeignKey(
        PerfilMateriaIA,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='simulaciones',
    )
    tipo_simulacion = models.CharField(
        max_length=30,
        choices=TIPOS_SIMULACION,
        default=TIPO_SIN_IA_ARBOL,
    )
    profesor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name='simulaciones_creadas',
    )
    titulo = models.CharField(max_length=300)
    tema = models.CharField(max_length=300, blank=True)
    nivel_dificultad = models.CharField(max_length=20, choices=DIFICULTADES, default=DIFICULTAD_MEDIA)
    maximo_decisiones = models.IntegerField(default=5)
    tiempo_estimado = models.IntegerField(default=30, help_text='Tiempo estimado en minutos')

    rol_estudiante = models.CharField(max_length=200, blank=True)
    contexto = models.TextField(blank=True)
    objetivo = models.TextField(blank=True)
    resultado_aprendizaje = models.TextField(blank=True)
    situacion_inicial = models.TextField(blank=True)

    instrucciones_ia = models.TextField(blank=True, default='')
    nivel_ayuda_ia = models.CharField(max_length=20, choices=NIVELES_AYUDA, default=AYUDA_MEDIA)
    tono_retroalimentacion = models.CharField(max_length=100, blank=True, default='Formativo y claro')

    guia_debriefing = models.TextField(blank=True, default='')
    retroalimentacion_base = models.TextField(blank=True, default='')

    parametros = models.JSONField(default=dict, blank=True)
    metadata_generacion = models.JSONField(default=dict, blank=True)
    configuracion_snapshot = models.JSONField(default=dict, blank=True)
    version_configuracion = models.PositiveIntegerField(default=1)
    configuracion_bloqueada = models.BooleanField(default=False)
    fecha_bloqueo = models.DateTimeField(null=True, blank=True)
    api_ia = models.CharField(max_length=40, blank=True, default='responses')
    modelo_ia = models.CharField(max_length=80, blank=True, default='')
    prompt_version = models.CharField(max_length=40, blank=True, default='simuta-rubrica-v1')
    esquema_ia_version = models.CharField(max_length=40, blank=True, default='rubrica-docente-v1')
    ia_habilitada = models.BooleanField(default=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default=BORRADOR)
    fecha_publicacion = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['materia_malla__materia__nombre', 'titulo']

    def __str__(self):
        return self.titulo


class IndicadorSimulacion(ModeloBase):
    DIRECCION_ALTO = 'ALTO'
    DIRECCION_BAJO = 'BAJO'
    DIRECCIONES_OPTIMAS = [
        (DIRECCION_ALTO, 'Mejor cuando es alto'),
        (DIRECCION_BAJO, 'Mejor cuando es bajo'),
    ]

    simulacion = models.ForeignKey(Simulacion, on_delete=models.CASCADE, related_name='indicadores')
    nombre = models.CharField(max_length=150)
    codigo = models.CharField(max_length=50, default='')
    valor_inicial = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    valor_minimo = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    valor_maximo = models.DecimalField(max_digits=12, decimal_places=2, default=100)
    direccion_optima = models.CharField(
        max_length=10,
        choices=DIRECCIONES_OPTIMAS,
        default=DIRECCION_ALTO,
        help_text='Define si un valor alto o bajo representa un buen desempeno en este indicador.',
    )
    es_critico = models.BooleanField(default=False)
    unidad = models.CharField(max_length=50, blank=True, default='')

    class Meta:
        ordering = ['nombre']
        unique_together = [('simulacion', 'codigo')]

    def __str__(self):
        return f'{self.nombre} ({self.valor_inicial})'


class RestriccionSimulacion(ModeloBase):
    OPERADORES = [
        ('>', '>'),
        ('>=', '>='),
        ('<', '<'),
        ('<=', '<='),
        ('=', '='),
    ]
    simulacion = models.ForeignKey(Simulacion, on_delete=models.CASCADE, related_name='restricciones')
    descripcion = models.TextField()
    codigo_indicador = models.CharField(max_length=50)
    operador = models.CharField(max_length=5, choices=OPERADORES)
    valor_limite = models.DecimalField(max_digits=12, decimal_places=2)
    penalizacion = models.DecimalField(max_digits=5, decimal_places=2, default=5)

    class Meta:
        ordering = ['simulacion', 'codigo_indicador']

    def __str__(self):
        return f'{self.codigo_indicador} {self.operador} {self.valor_limite}'


class CriterioEvaluacion(ModeloBase):
    simulacion = models.ForeignKey(Simulacion, on_delete=models.CASCADE, related_name='criterios')
    nombre = models.CharField(max_length=200)
    descripcion = models.TextField()
    peso = models.DecimalField(max_digits=5, decimal_places=2)
    puntaje_maximo = models.DecimalField(max_digits=5, decimal_places=2, default=100)

    class Meta:
        ordering = ['simulacion', 'nombre']

    def __str__(self):
        return f'{self.nombre} ({self.peso}%)'


class AccionSugeridaSimulacion(ModeloBase):
    simulacion = models.ForeignKey(Simulacion, on_delete=models.CASCADE, related_name='acciones_sugeridas')
    numero_ronda = models.PositiveIntegerField(null=True, blank=True)
    texto = models.CharField(max_length=300)
    descripcion = models.TextField(blank=True, default='')
    impacto_base = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['simulacion', 'numero_ronda', 'texto']

    def __str__(self):
        return self.texto


class CondicionExitoSimulacion(ModeloBase):
    OPERADORES = [
        ('>', '>'),
        ('>=', '>='),
        ('<', '<'),
        ('<=', '<='),
        ('=', '='),
    ]
    simulacion = models.ForeignKey(Simulacion, on_delete=models.CASCADE, related_name='condiciones_exito')
    descripcion = models.CharField(max_length=300)
    codigo_indicador = models.CharField(max_length=50)
    operador = models.CharField(max_length=5, choices=OPERADORES)
    valor_objetivo = models.DecimalField(max_digits=12, decimal_places=2)
    bonificacion = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta:
        ordering = ['simulacion', 'codigo_indicador']

    def __str__(self):
        return f'{self.codigo_indicador} {self.operador} {self.valor_objetivo}'


class EscenarioSimulacion(ModeloBase):
    simulacion = models.ForeignKey(Simulacion, on_delete=models.CASCADE, related_name='escenarios_arbol')
    titulo = models.CharField(max_length=200)
    situacion = models.TextField()
    orden = models.PositiveIntegerField(default=1)
    es_inicial = models.BooleanField(default=False)
    es_final = models.BooleanField(default=False)
    retroalimentacion_final = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['simulacion', 'orden', 'titulo']

    def __str__(self):
        return f'{self.simulacion} / {self.titulo}'


class DecisionConfigurada(ModeloBase):
    escenario = models.ForeignKey(EscenarioSimulacion, on_delete=models.CASCADE, related_name='decisiones')
    texto = models.CharField(max_length=300)
    descripcion = models.TextField(blank=True, default='')
    impacto = models.JSONField(default=dict, blank=True)
    puntaje_base = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    retroalimentacion = models.TextField(blank=True, default='')
    siguiente_escenario = models.ForeignKey(
        EscenarioSimulacion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='decisiones_entrada',
    )

    class Meta:
        ordering = ['escenario', 'texto']

    def __str__(self):
        return self.texto


class ConceptoEsperadoRonda(ModeloBase):
    escenario = models.ForeignKey(
        EscenarioSimulacion,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='conceptos_esperados',
    )
    simulacion = models.ForeignKey(
        Simulacion,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='conceptos_esperados',
    )
    numero_ronda = models.PositiveIntegerField(null=True, blank=True)
    nombre = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True, default='')
    palabras_clave = models.TextField(help_text='Separar por comas o ingresar una lista JSON.')
    regla_evaluacion = models.JSONField(default=dict, blank=True)
    peso = models.DecimalField(max_digits=5, decimal_places=2)
    impacto_si_cumple = models.JSONField(default=dict, blank=True)
    impacto_si_falta = models.JSONField(default=dict, blank=True)
    retroalimentacion_si_cumple = models.TextField(blank=True, default='')
    retroalimentacion_si_falta = models.TextField(blank=True, default='')
    es_critico = models.BooleanField(default=False)

    class Meta:
        ordering = ['simulacion', 'escenario', 'numero_ronda', 'nombre']
        constraints = [
            models.CheckConstraint(
                name='concepto_tiene_simulacion_o_escenario',
                condition=(
                    models.Q(simulacion__isnull=False, escenario__isnull=True)
                    | models.Q(simulacion__isnull=True, escenario__isnull=False)
                ),
            ),
        ]

    def __str__(self):
        destino = self.simulacion or self.escenario
        return f'{destino} / {self.nombre}'


class IntentoSimulacion(ModeloBase):
    estudiante = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='intentos_simulacion',
    )
    simulacion = models.ForeignKey(Simulacion, on_delete=models.PROTECT, related_name='intentos')
    escenario_actual = models.ForeignKey(
        EscenarioSimulacion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='intentos_actuales',
    )
    periodo = models.ForeignKey(
        'academico.PeriodoAcademico', on_delete=models.PROTECT,
        null=True, blank=True, related_name='intentos_simulacion',
    )
    estado_actual = models.JSONField(default=dict, blank=True)
    configuracion_snapshot = models.JSONField(default=dict, blank=True)
    situacion_actual = models.TextField(blank=True, default='')
    numero_ronda_actual = models.PositiveIntegerField(default=1)
    intentos_invalidos_actuales = models.PositiveIntegerField(default=0)
    max_intentos_invalidos_por_ronda = models.PositiveIntegerField(default=3)
    fecha_inicio = models.DateTimeField(default=timezone.now)
    fecha_fin = models.DateTimeField(null=True, blank=True)
    finalizado = models.BooleanField(default=False)
    puntuacion_final = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    nivel_resultado = models.CharField(max_length=50, blank=True, default='')
    retroalimentacion_final = models.TextField(blank=True, default='')
    debriefing_final = models.TextField(blank=True, default='')
    juego_contabilizado = models.BooleanField(default=False)

    class Meta:
        ordering = ['-fecha_inicio']

    def __str__(self):
        return f'{self.estudiante} - {self.simulacion}'


class PasoSimulacion(ModeloBase):
    TIPO_VALIDO = 'VALIDO'
    TIPO_INVALIDO = 'INVALIDO'
    TIPOS_PASO = [
        (TIPO_VALIDO, 'Valido'),
        (TIPO_INVALIDO, 'Invalido'),
    ]

    intento = models.ForeignKey(IntentoSimulacion, on_delete=models.CASCADE, related_name='pasos')
    numero = models.IntegerField()
    es_valido = models.BooleanField(default=True)
    tipo_paso = models.CharField(max_length=20, choices=TIPOS_PASO, default=TIPO_VALIDO)
    situacion_presentada = models.TextField()
    decision_estudiante = models.TextField()
    justificacion_estudiante = models.TextField()
    evaluacion_ia = models.TextField(blank=True, default='')
    evaluacion_detalle = models.JSONField(default=dict, blank=True)
    respuesta_ia_estructurada = models.JSONField(default=dict, blank=True)
    modelo_ia = models.CharField(max_length=80, blank=True, default='')
    api_ia = models.CharField(max_length=40, blank=True, default='')
    prompt_version = models.CharField(max_length=40, blank=True, default='')
    esquema_ia_version = models.CharField(max_length=40, blank=True, default='')
    tokens_entrada = models.PositiveIntegerField(default=0)
    tokens_salida = models.PositiveIntegerField(default=0)
    impacto_calculado = models.JSONField(default=dict, blank=True)
    estado_antes = models.JSONField(default=dict, blank=True)
    estado_despues = models.JSONField(default=dict, blank=True)
    puntaje_ia_sugerido = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    puntaje_paso = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    alertas_restricciones = models.JSONField(default=list, blank=True)
    penalizacion_aplicada = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    siguiente_situacion = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['intento', 'numero']
        unique_together = [('intento', 'numero')]

    def __str__(self):
        return f'{self.intento} / Paso {self.numero}'


class PerfilJuego(models.Model):
    """Progresion persistente del estudiante (capa de juego): XP acumulada,
    nivel, racha e insignias coleccionadas a lo largo de todas las simulaciones."""
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='perfil_juego',
    )
    xp_total = models.PositiveIntegerField(default=0)
    nivel = models.PositiveIntegerField(default=1)
    simulaciones_completadas = models.PositiveIntegerField(default=0)
    racha_actual = models.PositiveIntegerField(default=0)
    mejor_racha = models.PositiveIntegerField(default=0)
    mejor_nota = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    insignias = models.JSONField(default=list, blank=True)
    actualizado = models.DateTimeField(auto_now=True)

    XP_POR_NIVEL = 500

    class Meta:
        ordering = ['-xp_total']

    def __str__(self):
        return f'{self.usuario} - Nivel {self.nivel} ({self.xp_total} XP)'

    @property
    def xp_en_nivel(self):
        return self.xp_total % self.XP_POR_NIVEL

    @property
    def progreso_nivel_pct(self):
        return round(self.xp_en_nivel / self.XP_POR_NIVEL * 100, 1)
