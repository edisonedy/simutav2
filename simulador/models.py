from django.conf import settings
from django.core.validators import MinValueValidator
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
    maximo_decisiones = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        help_text='Cantidad exacta de rondas que necesita el caso.',
    )
    tiempo_estimado = models.IntegerField(default=30, help_text='Tiempo estimado en minutos')
    peso_rubrica_decision = models.PositiveSmallIntegerField(
        'peso de la calidad de la decision (%)',
        default=30,
        help_text='Cuanto de la nota de cada ronda mide COMO decide el estudiante '
                  '(postura, evidencia del caso, trade-off y consecuencia medible) en vez '
                  'de que conceptos del temario menciono. El resto lo aportan tus conceptos.',
    )
    # Bonificaciones a la nota FINAL. Son bonificacion y no peso a proposito: el
    # pronostico y la reflexion son opcionales para el estudiante, asi que
    # cobrarlos como porcentaje castigaria a quien los deja en blanco y premiaria
    # saltarselos. Como bonificacion solo pueden sumar.
    bonus_pronostico = models.PositiveSmallIntegerField(
        'bonificacion por pronosticar bien (puntos)', default=8,
        help_text='Puntos extra si el estudiante anticipa correctamente hacia donde se movera '
                  'un indicador antes de decidir. 0 lo desactiva.',
    )
    bonus_reflexion = models.PositiveSmallIntegerField(
        'bonificacion por reflexionar (puntos)', default=6,
        help_text='Puntos extra por escribir su reflexion despues de ver las consecuencias.',
    )
    bonus_adaptacion = models.PositiveSmallIntegerField(
        'bonificacion por adaptarse (puntos)', default=6,
        help_text='Puntos extra si mejora de una ronda a la siguiente: premia corregir el rumbo, '
                  'no solo acertar de entrada.',
    )

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
    prompt_version = models.CharField(max_length=40, blank=True, default='simuta-rubrica-v2')
    esquema_ia_version = models.CharField(max_length=40, blank=True, default='rubrica-docente-v2')
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
    DIRECCION_OBJETIVO = 'OBJETIVO'
    DIRECCION_RANGO = 'RANGO'
    DIRECCIONES_OPTIMAS = [
        (DIRECCION_ALTO, 'Mejor cuando es alto'),
        (DIRECCION_BAJO, 'Mejor cuando es bajo'),
        (DIRECCION_OBJETIVO, 'Mejor cerca de un valor objetivo'),
        (DIRECCION_RANGO, 'Mejor dentro de un rango objetivo'),
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
        help_text='Define si conviene subir, bajar, acercarse a un valor o permanecer en un rango.',
    )
    valor_objetivo = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text='Solo se usa cuando el indicador debe acercarse a un valor concreto.',
    )
    valor_objetivo_min = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text='Límite inferior deseable cuando la dirección óptima es un rango.',
    )
    valor_objetivo_max = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text='Límite superior deseable cuando la dirección óptima es un rango.',
    )
    peso_salud = models.DecimalField(
        max_digits=6, decimal_places=2, default=1,
        help_text=(
            'Peso relativo de este indicador en la salud del caso. '
            'No necesita sumar 100; el sistema normaliza todos los pesos.'
        ),
    )
    es_critico = models.BooleanField(default=False)
    unidad = models.CharField(max_length=50, blank=True, default='')

    class Meta:
        ordering = ['nombre']
        unique_together = [('simulacion', 'codigo')]

    def __str__(self):
        return f'{self.nombre} ({self.valor_inicial})'


class InvestigacionSimulacion(ModeloBase):
    """Informacion oculta que el estudiante puede COMPRAR antes de decidir.

    Es lo que convierte "elegir entre tres candidatos parecidos" en una decision
    de verdad: con presupuesto limitado no se pueden pagar todas las
    averiguaciones, asi que hay que apostar a cuales dan mas informacion por lo
    que cuestan. Sirve igual para pruebas a candidatos, auditorias a proveedores,
    encuestas a segmentos o estudios de mercado.
    """
    simulacion = models.ForeignKey(
        Simulacion, on_delete=models.CASCADE, related_name='investigaciones',
    )
    sujeto = models.CharField(
        max_length=120, blank=True, default='',
        help_text='Sobre quien o que averigua: "Candidato B", "Proveedor Sur", '
                  '"Segmento jovenes". Se usa para agrupar. Opcional.',
    )
    nombre = models.CharField(
        max_length=200, help_text='Lo que el estudiante ve antes de pagar: "Prueba tecnica".',
    )
    descripcion = models.TextField(
        blank=True, default='',
        help_text='Que obtiene si la paga, sin revelar el hallazgo.',
    )
    hallazgo = models.TextField(
        help_text='Lo que se revela al pagarla. Aqui va la informacion oculta.',
    )
    costo_recursos = models.JSONField(
        default=dict, blank=True,
        help_text='Cuanto cuesta, por codigo de recurso. Ejemplo: {"presupuesto": 60}.',
    )
    disponible_desde_ronda = models.PositiveIntegerField(default=1)
    orden = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = 'investigacion'
        verbose_name_plural = 'investigaciones'
        ordering = ['simulacion', 'sujeto', 'orden', 'nombre']

    def __str__(self):
        return f'{self.sujeto} - {self.nombre}' if self.sujeto else self.nombre


class RecursoSimulacion(ModeloBase):
    simulacion = models.ForeignKey(Simulacion, on_delete=models.CASCADE, related_name='recursos')
    codigo = models.CharField(max_length=50)
    nombre = models.CharField(max_length=150)
    valor_inicial = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    valor_minimo = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    valor_maximo = models.DecimalField(max_digits=12, decimal_places=2, default=100)
    unidad = models.CharField(max_length=50, blank=True, default='')
    es_critico = models.BooleanField(default=False)

    class Meta:
        ordering = ['simulacion', 'nombre']
        unique_together = [('simulacion', 'codigo')]

    def __str__(self):
        return f'{self.simulacion} / {self.nombre} ({self.valor_inicial})'


class RestriccionSimulacion(ModeloBase):
    OPERADORES = [
        ('>', '>'),
        ('>=', '>='),
        ('<', '<'),
        ('<=', '<='),
        ('=', '='),
        ('ABS<=', 'Valor absoluto <='),
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


class OpcionCasoSimulacion(ModeloBase):
    """Alternativa visible del caso: proveedor, candidato, estrategia, ruta, etc.

    No califica por si sola. Sirve para que el estudiante tenga datos concretos
    para comparar y justificar su decision.
    """
    simulacion = models.ForeignKey(Simulacion, on_delete=models.CASCADE, related_name='opciones_caso')
    nombre = models.CharField(max_length=200)
    subtitulo = models.CharField(max_length=200, blank=True, default='')
    valor_referencia = models.CharField(max_length=80, blank=True, default='')
    fortaleza = models.TextField(blank=True, default='')
    riesgo = models.TextField(blank=True, default='')
    resultados = models.JSONField(default=list, blank=True)
    orden = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['simulacion', 'orden', 'nombre']

    def __str__(self):
        return f'{self.simulacion} / {self.nombre}'


class MatrizEvaluacionCaso(ModeloBase):
    """Criterio visible para comparar alternativas del caso.

    La nota formal sigue saliendo de ConceptoEsperadoRonda; esta matriz es el
    material de apoyo que el estudiante debe usar en su respuesta.
    """
    simulacion = models.ForeignKey(Simulacion, on_delete=models.CASCADE, related_name='matriz_caso')
    criterio = models.CharField(max_length=200)
    peso = models.DecimalField(max_digits=5, decimal_places=2)
    evalua = models.TextField(blank=True, default='')
    orden = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['simulacion', 'orden', 'criterio']

    def __str__(self):
        return f'{self.simulacion} / {self.criterio} ({self.peso}%)'


class AccionSugeridaSimulacion(ModeloBase):
    simulacion = models.ForeignKey(Simulacion, on_delete=models.CASCADE, related_name='acciones_sugeridas')
    opcion_caso = models.ForeignKey(
        OpcionCasoSimulacion, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='acciones_vinculadas',
        help_text='Alternativa visible a la que pertenece esta consecuencia, si aplica.',
    )
    requiere_accion_previa = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='acciones_dependientes',
        help_text=(
            'Si se configura, esta decisión solo aparece cuando el estudiante '
            'eligió previamente la decisión indicada.'
        ),
    )
    bloqueada_por_accion_previa = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='acciones_bloqueadas',
        help_text=(
            'Si el estudiante eligió previamente esta decisión, la alternativa '
            'actual deja de estar disponible.'
        ),
    )
    maximo_ejecuciones = models.PositiveSmallIntegerField(
        default=1,
        help_text='Número máximo de veces que puede ejecutarse en un intento. 0 significa sin límite.',
    )
    numero_ronda = models.PositiveIntegerField(null=True, blank=True)
    texto = models.CharField(max_length=300)
    descripcion = models.TextField(blank=True, default='')
    impacto_base = models.JSONField(default=dict, blank=True)
    costo_recursos = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['simulacion', 'numero_ronda', 'texto']

    def __str__(self):
        return self.texto_visible

    @property
    def texto_visible(self):
        return self.opcion_caso.nombre if self.opcion_caso_id else self.texto

    @property
    def descripcion_visible(self):
        if self.opcion_caso_id:
            return self.opcion_caso.subtitulo or self.descripcion
        return self.descripcion


class CondicionExitoSimulacion(ModeloBase):
    OPERADORES = [
        ('>', '>'),
        ('>=', '>='),
        ('<', '<'),
        ('<=', '<='),
        ('=', '='),
        ('ABS<=', 'Valor absoluto <='),
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


class EventoSimulacion(ModeloBase):
    OPERADORES = [
        ('', 'Sin condicion'),
        ('>', '>'),
        ('>=', '>='),
        ('<', '<'),
        ('<=', '<='),
        ('=', '='),
    ]

    simulacion = models.ForeignKey(Simulacion, on_delete=models.CASCADE, related_name='eventos')
    nombre = models.CharField(max_length=200)
    mensaje = models.TextField()
    ronda = models.PositiveIntegerField(null=True, blank=True)
    codigo_indicador_condicion = models.CharField(max_length=50, blank=True, default='')
    operador_condicion = models.CharField(max_length=5, choices=OPERADORES, blank=True, default='')
    valor_condicion = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    efecto = models.JSONField(default=dict, blank=True)
    prioridad = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['simulacion', 'prioridad', 'ronda', 'nombre']

    def __str__(self):
        return f'{self.simulacion} / {self.nombre}'


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
    resultado_aprendizaje = models.ForeignKey(
        'ResultadoAprendizaje', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='conceptos',
    )
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
    asignacion = models.ForeignKey(
        'Asignacion', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='intentos',
    )
    equipo = models.ForeignKey(
        'Equipo', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='intentos',
    )
    intento_origen = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reintentos',
    )
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
    recursos_actuales = models.JSONField(default=dict, blank=True)
    investigaciones_compradas = models.JSONField(default=list, blank=True)
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
    prompt_ia_enviado = models.TextField(
        blank=True, default='',
        help_text='Prompt efectivo enviado al proveedor para auditoría de la evaluación.',
    )
    impacto_calculado = models.JSONField(default=dict, blank=True)
    estado_antes = models.JSONField(default=dict, blank=True)
    estado_despues = models.JSONField(default=dict, blank=True)
    costo_recursos = models.JSONField(default=dict, blank=True)
    recursos_antes = models.JSONField(default=dict, blank=True)
    recursos_despues = models.JSONField(default=dict, blank=True)
    puntaje_ia_sugerido = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    puntaje_paso = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    alertas_restricciones = models.JSONField(default=list, blank=True)
    penalizacion_aplicada = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    siguiente_situacion = models.TextField(blank=True, default='')
    # Reflexion del estudiante tras ver las consecuencias (ciclo de Kolb) y la
    # repregunta socratica del tutor IA. Convierte la experiencia en aprendizaje.
    reflexion = models.TextField(blank=True, default='')
    reflexion_feedback = models.TextField(blank=True, default='')
    # Pronostico previo a decidir (metacognicion): el estudiante predice que
    # indicador cambiara y luego compara su hipotesis con el resultado real.
    pronostico_indicador = models.CharField(max_length=80, blank=True, default='')
    pronostico_direccion = models.CharField(max_length=20, blank=True, default='')
    pronostico_justificacion = models.TextField(blank=True, default='')
    pronostico_resultado = models.JSONField(default=dict, blank=True)
    tradeoff_aceptado = models.TextField(blank=True, default='')
    tradeoff_resultado = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['intento', 'numero']
        unique_together = [('intento', 'numero')]

    def __str__(self):
        return f'{self.intento} / Paso {self.numero}'


class PistaTutor(ModeloBase):
    intento = models.ForeignKey(IntentoSimulacion, on_delete=models.CASCADE, related_name='pistas_tutor')
    numero_ronda = models.PositiveIntegerField(default=1)
    pregunta_estudiante = models.TextField(blank=True, default='')
    pista = models.TextField()
    conceptos_referidos = models.JSONField(default=list, blank=True)
    usada = models.BooleanField(default=False)

    class Meta:
        ordering = ['intento', 'numero_ronda', 'fecha_creacion']

    def __str__(self):
        return f'{self.intento} / Pista ronda {self.numero_ronda}'


class RetoRefuerzo(ModeloBase):
    estudiante = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='retos_refuerzo',
    )
    simulacion = models.ForeignKey(Simulacion, on_delete=models.CASCADE, related_name='retos_refuerzo')
    intento_origen = models.ForeignKey(
        IntentoSimulacion, on_delete=models.CASCADE, related_name='retos_refuerzo',
    )
    concepto = models.CharField(max_length=200, blank=True, default='')
    pregunta = models.TextField()
    respuesta = models.TextField(blank=True, default='')
    feedback = models.TextField(blank=True, default='')
    fecha_disponible = models.DateTimeField()
    completado = models.BooleanField(default=False)
    fecha_completado = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['completado', 'fecha_disponible', '-fecha_creacion']

    def __str__(self):
        return f'{self.estudiante} / {self.simulacion} / {self.concepto or "refuerzo"}'


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


class ResultadoAprendizaje(ModeloBase):
    """Resultado de aprendizaje (RA) de una materia, con su nivel de Bloom.
    Permite mapear los conceptos de la rubrica a RAs y generar reportes de
    logro por curso (acreditacion tipo CACES)."""
    RECORDAR = 'RECORDAR'
    COMPRENDER = 'COMPRENDER'
    APLICAR = 'APLICAR'
    ANALIZAR = 'ANALIZAR'
    EVALUAR = 'EVALUAR'
    CREAR = 'CREAR'
    NIVELES_BLOOM = [
        (RECORDAR, 'Recordar'),
        (COMPRENDER, 'Comprender'),
        (APLICAR, 'Aplicar'),
        (ANALIZAR, 'Analizar'),
        (EVALUAR, 'Evaluar'),
        (CREAR, 'Crear'),
    ]

    materia_malla = models.ForeignKey(
        MateriaMalla, on_delete=models.CASCADE, related_name='resultados_aprendizaje',
    )
    codigo = models.CharField(max_length=30)
    descripcion = models.TextField()
    nivel_bloom = models.CharField(max_length=20, choices=NIVELES_BLOOM, default=APLICAR)

    class Meta:
        ordering = ['materia_malla', 'codigo']
        unique_together = [('materia_malla', 'codigo')]
        verbose_name = 'resultado de aprendizaje'
        verbose_name_plural = 'resultados de aprendizaje'

    def __str__(self):
        return f'{self.codigo} - {self.descripcion[:60]}'


class Seccion(ModeloBase):
    """Grupo/paralelo de estudiantes de una materia en un periodo, a cargo de un
    profesor. Es la 'capa de curso' sobre la que se asignan simulaciones."""
    materia_malla = models.ForeignKey(
        MateriaMalla, on_delete=models.PROTECT, related_name='secciones',
    )
    periodo = models.ForeignKey(
        'academico.PeriodoAcademico', on_delete=models.PROTECT, related_name='secciones',
    )
    profesor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='secciones_dictadas',
    )
    paralelo = models.CharField(max_length=20, default='A')
    estudiantes = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name='secciones_inscritas',
    )

    class Meta:
        ordering = ['periodo', 'materia_malla__materia__nombre', 'paralelo']
        unique_together = [('materia_malla', 'periodo', 'paralelo')]

    def __str__(self):
        return f'{self.materia_malla.materia} - {self.paralelo} ({self.periodo})'


class Asignacion(ModeloBase):
    """Simulacion asignada a una seccion, con fecha limite y ponderacion.
    Convierte una simulacion de juego libre en una tarea evaluable del curso."""
    seccion = models.ForeignKey(Seccion, on_delete=models.CASCADE, related_name='asignaciones')
    simulacion = models.ForeignKey(Simulacion, on_delete=models.PROTECT, related_name='asignaciones')
    titulo = models.CharField(max_length=200, blank=True, default='')
    fecha_apertura = models.DateTimeField(default=timezone.now)
    fecha_limite = models.DateTimeField(null=True, blank=True)
    ponderacion = models.DecimalField(max_digits=5, decimal_places=2, default=100)
    nota_minima_aprobacion = models.DecimalField(max_digits=5, decimal_places=2, default=70)
    permite_reintento = models.BooleanField(default=True)
    trabajo_en_equipo = models.BooleanField(default=False)
    publicada = models.BooleanField(default=True)

    class Meta:
        ordering = ['-fecha_apertura']
        unique_together = [('seccion', 'simulacion')]

    def __str__(self):
        return self.titulo or f'{self.simulacion.titulo} ({self.seccion})'

    @property
    def cerrada(self):
        return bool(self.fecha_limite and timezone.now() > self.fecha_limite)


class Equipo(ModeloBase):
    """Equipo de estudiantes que resuelve una asignacion en conjunto."""
    asignacion = models.ForeignKey(Asignacion, on_delete=models.CASCADE, related_name='equipos')
    nombre = models.CharField(max_length=120)
    integrantes = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name='equipos_simulacion',
    )

    class Meta:
        ordering = ['asignacion', 'nombre']
        unique_together = [('asignacion', 'nombre')]

    def __str__(self):
        return f'{self.nombre} ({self.asignacion})'
