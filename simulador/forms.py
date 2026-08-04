from django import forms

from django.utils.html import format_html

from academico.forms import _ayuda_por_rol
from core.funciones import conservar_seleccion_actual
from core.models import PerfilUsuario
from core.permisos import usuarios_con_rol

from .models import (
    AccionSugeridaSimulacion,
    Asignacion,
    CondicionExitoSimulacion,
    ConceptoEsperadoRonda,
    CriterioEvaluacion,
    DecisionConfigurada,
    Equipo,
    EscenarioSimulacion,
    EventoSimulacion,
    IndicadorSimulacion,
    IntentoSimulacion,
    InvestigacionSimulacion,
    MatrizEvaluacionCaso,
    OpcionCasoSimulacion,
    PerfilMateriaIA,
    PlantillaConcepto,
    PlantillaIndicador,
    PlantillaRestriccion,
    PlantillaRonda,
    PlantillaSimulacion,
    RecursoSimulacion,
    ResultadoAprendizaje,
    RestriccionSimulacion,
    Seccion,
    Simulacion,
)


class _DateTimeInput(forms.DateTimeInput):
    input_type = 'datetime-local'

    def __init__(self, attrs=None):
        super().__init__(attrs=attrs, format='%Y-%m-%dT%H:%M')


class SeccionForm(forms.ModelForm):
    class Meta:
        model = Seccion
        fields = ['materia_malla', 'periodo', 'paralelo', 'estudiantes', 'activo']
        widgets = {'estudiantes': forms.SelectMultiple(attrs={'size': 8})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['materia_malla'].label = 'Materia'
        self.fields['paralelo'].help_text = 'Ejemplo: A, B, "Matutino".'
        estudiantes = self.fields['estudiantes']
        estudiantes.queryset = usuarios_con_rol(PerfilUsuario.ESTUDIANTE).order_by(
            'last_name', 'first_name', 'username',
        )
        estudiantes.label_from_instance = lambda u: u.get_full_name() or u.username
        estudiantes.help_text = format_html(
            'Elige los estudiantes del paralelo (Ctrl/Cmd para varios). {}',
            _ayuda_por_rol('Estudiante'),
        )
        conservar_seleccion_actual(self)


class AsignacionForm(forms.ModelForm):
    class Meta:
        model = Asignacion
        fields = [
            'simulacion', 'titulo', 'fecha_apertura', 'fecha_limite',
            'ponderacion', 'nota_minima_aprobacion', 'permite_reintento',
            'trabajo_en_equipo', 'publicada', 'activo',
        ]
        widgets = {
            'fecha_apertura': _DateTimeInput(),
            'fecha_limite': _DateTimeInput(),
        }

    def __init__(self, *args, simulaciones=None, **kwargs):
        super().__init__(*args, **kwargs)
        if simulaciones is not None:
            self.fields['simulacion'].queryset = simulaciones
        self.fields['titulo'].help_text = 'Si lo dejas vacio se usa el titulo de la simulacion.'
        self.fields['fecha_limite'].help_text = 'Opcional. Despues de esta fecha la tarea queda cerrada.'
        self.fields['ponderacion'].label = 'Peso en la nota (%)'
        self.fields['nota_minima_aprobacion'].label = 'Nota minima para aprobar'
        conservar_seleccion_actual(self)


class ResultadoAprendizajeForm(forms.ModelForm):
    class Meta:
        model = ResultadoAprendizaje
        fields = ['materia_malla', 'codigo', 'descripcion', 'nivel_bloom', 'activo']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['materia_malla'].label = 'Materia'
        self.fields['codigo'].help_text = 'Ejemplo: RA1, RA2.'
        self.fields['nivel_bloom'].label = 'Nivel de Bloom'


class EquipoForm(forms.ModelForm):
    class Meta:
        model = Equipo
        fields = ['nombre', 'integrantes', 'activo']
        widgets = {'integrantes': forms.SelectMultiple(attrs={'size': 6})}

    def __init__(self, *args, estudiantes=None, **kwargs):
        super().__init__(*args, **kwargs)
        integrantes = self.fields['integrantes']
        if estudiantes is not None:
            integrantes.queryset = estudiantes
        integrantes.label_from_instance = lambda u: u.get_full_name() or u.username
        conservar_seleccion_actual(self)


class SimulacionForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['materia_malla'].label = 'Materia'
        self.fields['materia_malla'].help_text = 'Elige la materia donde se publicara la simulacion.'
        self.fields['perfil_materia_ia'].label = 'Perfil IA de la materia'
        self.fields['perfil_materia_ia'].help_text = 'Configuracion avanzada de apoyo para la materia.'
        self.fields['tipo_simulacion'].label = 'Modo de simulacion'
        self.fields['tipo_simulacion'].help_text = 'Elige si la simulacion usara IA para evaluar respuestas o si trabajara como arbol de decisiones.'
        self.fields['titulo'].label = 'Titulo del caso'
        self.fields['titulo'].help_text = 'Ejemplo: Compra de computadoras para laboratorio.'
        self.fields['tema'].label = 'Tema'
        self.fields['tema'].help_text = 'Ejemplo: Evaluacion de proveedores, presupuesto y riesgo.'
        self.fields['nivel_dificultad'].label = 'Nivel de dificultad'
        self.fields['peso_rubrica_decision'].label = 'Peso de la calidad de la decision (%)'
        self.fields['peso_rubrica_decision'].help_text = (
            'Metodo del caso: cuanto de la nota mide COMO decide el estudiante (toma postura, '
            'usa evidencia del caso, reconoce el trade-off y anticipa una consecuencia medible) '
            'en vez de que conceptos del temario menciono. Con 0 solo cuentan tus conceptos. '
            'Recomendado: 30.'
        )
        for nombre, etiqueta in (
            ('bonus_pronostico', 'Bonificacion por pronosticar bien'),
            ('bonus_reflexion', 'Bonificacion por reflexionar'),
            ('bonus_adaptacion', 'Bonificacion por mejorar entre rondas'),
        ):
            self.fields[nombre].label = etiqueta
        self.fields['maximo_decisiones'].label = 'Cantidad exacta de rondas'
        self.fields['maximo_decisiones'].help_text = (
            'Pon únicamente las rondas necesarias para lograr el aprendizaje. '
            'No existe una cantidad fija.'
        )
        self.fields['maximo_decisiones'].widget.attrs.update({'min': 1, 'step': 1})
        self.fields['contexto'].label = 'Contexto del caso'
        self.fields['contexto'].help_text = 'Cuenta el problema general que vivira el estudiante.'
        self.fields['objetivo'].label = 'Objetivo del estudiante'
        self.fields['objetivo'].help_text = 'Di que debe lograr el estudiante al final.'
        self.fields['resultado_aprendizaje'].label = 'Resultado de aprendizaje'
        self.fields['situacion_inicial'].label = 'Situacion inicial'
        self.fields['situacion_inicial'].help_text = 'Primera situacion que vera el estudiante antes de tomar la decision.'
        self.fields['instrucciones_ia'].label = 'Instrucciones para la IA'
        self.fields['nivel_ayuda_ia'].label = 'Nivel de ayuda de la IA'
        self.fields['tono_retroalimentacion'].label = 'Tono de la retroalimentacion'
        self.fields['guia_debriefing'].label = 'Guia de cierre'
        self.fields['retroalimentacion_base'].label = 'Retroalimentacion base'
        self.fields['modelo_ia'].label = 'Modelo de IA'
        self.fields['prompt_version'].label = 'Version del prompt'
        self.fields['esquema_ia_version'].label = 'Version del esquema de IA'
        self.fields['ia_habilitada'].label = 'IA habilitada'
        self.fields['activo'].label = 'Activo'

    def clean_maximo_decisiones(self):
        cantidad = self.cleaned_data.get('maximo_decisiones')
        if cantidad is None or cantidad < 1:
            raise forms.ValidationError('El caso debe tener al menos una ronda.')
        return cantidad
    class Meta:
        model = Simulacion
        fields = [
            'materia_malla', 'plantilla_origen', 'perfil_materia_ia',
            'tipo_simulacion', 'titulo', 'tema',
            'nivel_dificultad', 'maximo_decisiones', 'tiempo_estimado',
            'peso_rubrica_decision', 'bonus_pronostico', 'bonus_reflexion', 'bonus_adaptacion',
            'rol_estudiante', 'contexto', 'objetivo',
            'resultado_aprendizaje', 'situacion_inicial',
            'instrucciones_ia', 'nivel_ayuda_ia', 'tono_retroalimentacion',
            'guia_debriefing', 'retroalimentacion_base',
            'modelo_ia', 'prompt_version', 'esquema_ia_version',
            'ia_habilitada', 'activo',
        ]
        widgets = {
            'contexto': forms.Textarea(attrs={'rows': 4}),
            'objetivo': forms.Textarea(attrs={'rows': 3}),
            'resultado_aprendizaje': forms.Textarea(attrs={'rows': 3}),
            'situacion_inicial': forms.Textarea(attrs={'rows': 3}),
            'instrucciones_ia': forms.Textarea(attrs={'rows': 3}),
            'guia_debriefing': forms.Textarea(attrs={'rows': 3}),
            'retroalimentacion_base': forms.Textarea(attrs={'rows': 3}),
        }


class PerfilMateriaIAForm(forms.ModelForm):
    class Meta:
        model = PerfilMateriaIA
        fields = [
            'materia_malla', 'rol_profesional', 'enfoque', 'competencias',
            'resultados_aprendizaje', 'temas_clave', 'conceptos_clave',
            'indicadores_sugeridos', 'restricciones_contexto',
            'criterios_calidad', 'activo',
        ]
        widgets = {
            'enfoque': forms.Textarea(attrs={'rows': 3}),
            'restricciones_contexto': forms.Textarea(attrs={'rows': 3}),
        }


class PlantillaSimulacionForm(forms.ModelForm):
    class Meta:
        model = PlantillaSimulacion
        fields = [
            'nombre', 'codigo', 'tipo', 'descripcion', 'materia_malla',
            'tiempo_estimado', 'nivel_dificultad',
            'rol_base', 'contexto_base', 'objetivo_base', 'resultado_base',
            'instrucciones_ia', 'version', 'es_predeterminada', 'activo',
        ]
        widgets = {
            'descripcion': forms.Textarea(attrs={'rows': 3}),
            'contexto_base': forms.Textarea(attrs={'rows': 3}),
            'objetivo_base': forms.Textarea(attrs={'rows': 3}),
            'resultado_base': forms.Textarea(attrs={'rows': 3}),
            'instrucciones_ia': forms.Textarea(attrs={'rows': 3}),
        }


class PlantillaRondaForm(forms.ModelForm):
    class Meta:
        model = PlantillaRonda
        fields = [
            'plantilla', 'numero', 'titulo', 'proposito', 'consigna_base',
            'opciones_decision', 'etiqueta_decision', 'etiqueta_justificacion', 'activo',
        ]
        widgets = {
            'proposito': forms.Textarea(attrs={'rows': 2}),
            'consigna_base': forms.Textarea(attrs={'rows': 3}),
        }


class PlantillaIndicadorForm(forms.ModelForm):
    class Meta:
        model = PlantillaIndicador
        fields = [
            'plantilla', 'codigo', 'nombre', 'valor_inicial', 'valor_minimo',
            'valor_maximo', 'direccion_optima', 'es_critico', 'unidad', 'activo',
        ]


class PlantillaRestriccionForm(forms.ModelForm):
    class Meta:
        model = PlantillaRestriccion
        fields = [
            'plantilla', 'descripcion', 'codigo_indicador', 'operador',
            'valor_limite', 'penalizacion', 'activo',
        ]
        widgets = {'descripcion': forms.Textarea(attrs={'rows': 2})}


class PlantillaConceptoForm(forms.ModelForm):
    class Meta:
        model = PlantillaConcepto
        fields = [
            'ronda', 'nombre', 'descripcion', 'regla_evaluacion', 'peso',
            'impacto_si_cumple', 'impacto_si_falta',
            'retroalimentacion_si_cumple', 'retroalimentacion_si_falta',
            'es_critico', 'activo',
        ]
        widgets = {
            'descripcion': forms.Textarea(attrs={'rows': 2}),
            'retroalimentacion_si_cumple': forms.Textarea(attrs={'rows': 2}),
            'retroalimentacion_si_falta': forms.Textarea(attrs={'rows': 2}),
        }


class IndicadorSimulacionForm(forms.ModelForm):
    class Meta:
        model = IndicadorSimulacion
        fields = [
            'simulacion', 'nombre', 'codigo', 'valor_inicial', 'valor_minimo',
            'valor_maximo', 'direccion_optima', 'valor_objetivo',
            'valor_objetivo_min', 'valor_objetivo_max',
            'peso_salud', 'es_critico', 'unidad', 'activo',
        ]

    def clean(self):
        cleaned = super().clean()
        minimo = cleaned.get('valor_minimo')
        maximo = cleaned.get('valor_maximo')
        objetivo = cleaned.get('valor_objetivo')
        objetivo_min = cleaned.get('valor_objetivo_min')
        objetivo_max = cleaned.get('valor_objetivo_max')
        direccion = cleaned.get('direccion_optima')
        peso_salud = cleaned.get('peso_salud')
        if minimo is not None and maximo is not None and minimo >= maximo:
            raise forms.ValidationError('El valor minimo debe ser menor que el maximo.')
        if direccion == IndicadorSimulacion.DIRECCION_OBJETIVO:
            if objetivo is None:
                raise forms.ValidationError('Ingresa el valor objetivo de este indicador.')
            if minimo is not None and maximo is not None and not (minimo <= objetivo <= maximo):
                raise forms.ValidationError('El valor objetivo debe estar entre el minimo y el maximo.')
        if direccion == IndicadorSimulacion.DIRECCION_RANGO:
            if objetivo_min is None or objetivo_max is None:
                raise forms.ValidationError('Ingresa los dos límites del rango objetivo.')
            if objetivo_min >= objetivo_max:
                raise forms.ValidationError('El límite inferior del rango debe ser menor que el superior.')
            if minimo is not None and maximo is not None and not (
                minimo <= objetivo_min < objetivo_max <= maximo
            ):
                raise forms.ValidationError('El rango objetivo debe quedar dentro del mínimo y máximo del indicador.')
        if peso_salud is not None and peso_salud < 0:
            raise forms.ValidationError('El peso de salud no puede ser negativo.')
        return cleaned


class RecursoSimulacionForm(forms.ModelForm):
    class Meta:
        model = RecursoSimulacion
        fields = ['simulacion', 'nombre', 'codigo', 'valor_inicial', 'valor_minimo', 'valor_maximo', 'unidad', 'es_critico', 'activo']


class InvestigacionSimulacionForm(forms.ModelForm):
    """El costo no se pide como JSON: se arma con una casilla por recurso."""

    class Meta:
        model = InvestigacionSimulacion
        fields = ['simulacion', 'sujeto', 'nombre', 'descripcion', 'hallazgo',
                  'disponible_desde_ronda', 'orden', 'activo']
        widgets = {
            'descripcion': forms.Textarea(attrs={'rows': 2}),
            'hallazgo': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['nombre'].label = 'Que puede averiguar'
        self.fields['descripcion'].label = 'Que obtiene (sin revelar el hallazgo)'
        self.fields['hallazgo'].label = 'Hallazgo que se revela al pagarla'
        self.fields['disponible_desde_ronda'].label = 'Disponible desde la ronda'


class RestriccionSimulacionForm(forms.ModelForm):
    class Meta:
        model = RestriccionSimulacion
        fields = ['simulacion', 'descripcion', 'codigo_indicador', 'operador', 'valor_limite', 'penalizacion', 'activo']
        widgets = {'descripcion': forms.Textarea(attrs={'rows': 2})}

    def clean(self):
        cleaned = super().clean()
        simulacion = cleaned.get('simulacion')
        codigo = cleaned.get('codigo_indicador')
        limite = cleaned.get('valor_limite')
        if simulacion and codigo:
            indicador = simulacion.indicadores.filter(codigo=codigo, activo=True).first()
            if not indicador:
                raise forms.ValidationError('El indicador seleccionado no pertenece a esta simulacion.')
            if limite is not None and cleaned.get('operador') != 'ABS<=':
                if limite < indicador.valor_minimo or limite > indicador.valor_maximo:
                    raise forms.ValidationError('El limite debe estar dentro del rango del indicador.')
        return cleaned


class CriterioEvaluacionForm(forms.ModelForm):
    class Meta:
        model = CriterioEvaluacion
        fields = ['simulacion', 'nombre', 'descripcion', 'peso', 'puntaje_maximo', 'activo']
        widgets = {'descripcion': forms.Textarea(attrs={'rows': 2})}


class MatrizEvaluacionCasoForm(forms.ModelForm):
    class Meta:
        model = MatrizEvaluacionCaso
        fields = ['simulacion', 'criterio', 'peso', 'evalua', 'orden', 'activo']
        widgets = {'evalua': forms.Textarea(attrs={'rows': 2})}


class OpcionCasoSimulacionForm(forms.ModelForm):
    resultados_texto = forms.CharField(
        required=False,
        label='Resultados visibles',
        help_text='Una linea por dato. Ej: TCO=34000 o Garantia=3 anios.',
        widget=forms.Textarea(attrs={'rows': 4}),
    )

    class Meta:
        model = OpcionCasoSimulacion
        fields = [
            'simulacion', 'nombre', 'subtitulo', 'valor_referencia',
            'fortaleza', 'riesgo', 'orden', 'activo',
        ]
        widgets = {
            'fortaleza': forms.Textarea(attrs={'rows': 2}),
            'riesgo': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            lineas = []
            for item in self.instance.resultados or []:
                criterio = str(item.get('criterio', '')).strip()
                valor = str(item.get('valor', '')).strip()
                if criterio or valor:
                    lineas.append(f'{criterio}={valor}' if criterio else valor)
            self.fields['resultados_texto'].initial = '\n'.join(lineas)

    def save(self, commit=True):
        obj = super().save(commit=False)
        resultados = []
        texto = self.cleaned_data.get('resultados_texto') or ''
        for linea in texto.splitlines():
            linea = linea.strip()
            if not linea:
                continue
            if '=' in linea:
                criterio, valor = linea.split('=', 1)
            elif ':' in linea:
                criterio, valor = linea.split(':', 1)
            else:
                criterio, valor = '', linea
            resultados.append({'criterio': criterio.strip(), 'valor': valor.strip()})
        obj.resultados = resultados
        if commit:
            obj.save()
            self.save_m2m()
        return obj


class AccionSugeridaForm(forms.ModelForm):
    # impacto_base se arma con una casilla por indicador (UI amigable),
    # no se pide JSON al profesor. Ver _impacto_desde_post en pro_simulaciones.
    class Meta:
        model = AccionSugeridaSimulacion
        fields = [
            'simulacion', 'numero_ronda', 'opcion_caso', 'requiere_accion_previa',
            'bloqueada_por_accion_previa', 'maximo_ejecuciones',
            'texto', 'descripcion', 'activo',
        ]
        widgets = {
            'descripcion': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, simulacion_obj=None, **kwargs):
        super().__init__(*args, **kwargs)
        simulacion_obj = simulacion_obj or getattr(self.instance, 'simulacion', None)
        maximo = int(getattr(simulacion_obj, 'maximo_decisiones', 0) or 0)
        rondas = (getattr(simulacion_obj, 'parametros', None) or {}).get('rondas') or []
        titulos = {
            int(item.get('numero')): str(item.get('titulo') or '').strip()
            for item in rondas if isinstance(item, dict) and item.get('numero')
        }
        choices = [('', 'Todas las rondas (solo si realmente aplica a todas)')]
        choices.extend(
            (numero, f'Ronda {numero}' + (f' · {titulos[numero]}' if titulos.get(numero) else ''))
            for numero in range(1, maximo + 1)
        )
        self.fields['numero_ronda'] = forms.TypedChoiceField(
            choices=choices, coerce=int, empty_value=None, required=False,
            label='Ronda en la que aparece',
            widget=forms.Select(attrs={'class': 'form-select'}),
        )
        self.fields['opcion_caso'].queryset = OpcionCasoSimulacion.objects.filter(
            simulacion=simulacion_obj, activo=True,
        ) if simulacion_obj else OpcionCasoSimulacion.objects.none()
        self.fields['opcion_caso'].required = False
        self.fields['opcion_caso'].label = 'Alternativa visible vinculada'
        previas = AccionSugeridaSimulacion.objects.none()
        if simulacion_obj:
            previas = AccionSugeridaSimulacion.objects.filter(
                simulacion=simulacion_obj, activo=True,
                numero_ronda__isnull=False,
            )
            if self.instance and self.instance.pk:
                previas = previas.exclude(pk=self.instance.pk)
        self.fields['requiere_accion_previa'].queryset = previas.order_by('numero_ronda', 'texto')
        self.fields['requiere_accion_previa'].required = False
        self.fields['requiere_accion_previa'].label = 'Decisión previa requerida'
        self.fields['bloqueada_por_accion_previa'].queryset = previas.order_by('numero_ronda', 'texto')
        self.fields['bloqueada_por_accion_previa'].required = False
        self.fields['bloqueada_por_accion_previa'].label = 'Decisión previa que la bloquea'
        self.fields['texto'].required = False

    def clean(self):
        cleaned = super().clean()
        opcion = cleaned.get('opcion_caso')
        previa = cleaned.get('requiere_accion_previa')
        bloqueante = cleaned.get('bloqueada_por_accion_previa')
        texto = (cleaned.get('texto') or '').strip()
        simulacion = cleaned.get('simulacion') or getattr(self.instance, 'simulacion', None)
        if opcion and simulacion and opcion.simulacion_id != simulacion.id:
            raise forms.ValidationError('La alternativa vinculada debe pertenecer a esta simulación.')
        if previa and simulacion and previa.simulacion_id != simulacion.id:
            raise forms.ValidationError('La decisión previa debe pertenecer a esta simulación.')
        numero = cleaned.get('numero_ronda')
        if previa and (not numero or not previa.numero_ronda or previa.numero_ronda >= numero):
            raise forms.ValidationError('La decisión requerida debe pertenecer a una ronda anterior.')
        if bloqueante and simulacion and bloqueante.simulacion_id != simulacion.id:
            raise forms.ValidationError('La decisión que bloquea debe pertenecer a esta simulación.')
        if bloqueante and (not numero or not bloqueante.numero_ronda or bloqueante.numero_ronda >= numero):
            raise forms.ValidationError('La decisión que bloquea debe pertenecer a una ronda anterior.')
        if previa and bloqueante and previa.pk == bloqueante.pk:
            raise forms.ValidationError('Una misma decisión no puede habilitar y bloquear la alternativa.')
        if not opcion and not texto:
            raise forms.ValidationError('Selecciona una alternativa visible o escribe la decisión.')
        if opcion and not texto:
            cleaned['texto'] = f'Seleccionar {opcion.nombre}'
        return cleaned


class CondicionExitoForm(forms.ModelForm):
    class Meta:
        model = CondicionExitoSimulacion
        fields = ['simulacion', 'descripcion', 'codigo_indicador', 'operador', 'valor_objetivo', 'bonificacion', 'activo']

    def clean(self):
        cleaned = super().clean()
        simulacion = cleaned.get('simulacion')
        codigo = cleaned.get('codigo_indicador')
        objetivo = cleaned.get('valor_objetivo')
        if simulacion and codigo:
            indicador = simulacion.indicadores.filter(codigo=codigo, activo=True).first()
            if not indicador:
                raise forms.ValidationError('El indicador seleccionado no pertenece a esta simulacion.')
            if objetivo is not None and cleaned.get('operador') != 'ABS<=':
                if objetivo < indicador.valor_minimo or objetivo > indicador.valor_maximo:
                    raise forms.ValidationError('La meta debe estar dentro del rango del indicador.')
        return cleaned


class EventoSimulacionForm(forms.ModelForm):
    codigo_indicador_condicion = forms.ChoiceField(required=False, choices=[])

    class Meta:
        model = EventoSimulacion
        fields = [
            'simulacion', 'nombre', 'mensaje', 'ronda',
            'codigo_indicador_condicion', 'operador_condicion', 'valor_condicion',
            'prioridad', 'activo',
        ]
        widgets = {
            'mensaje': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        simulacion = kwargs.pop('simulacion_obj', None)
        super().__init__(*args, **kwargs)
        if simulacion is None:
            simulacion = getattr(self.instance, 'simulacion', None)
        opciones = [('', 'Sin condicion por indicador')]
        if simulacion:
            opciones.extend(
                (ind.codigo, f'{ind.nombre} ({ind.codigo})')
                for ind in simulacion.indicadores.filter(activo=True).order_by('nombre')
            )
        self.fields['codigo_indicador_condicion'].choices = opciones

    def clean(self):
        cleaned = super().clean()
        codigo = cleaned.get('codigo_indicador_condicion')
        operador = cleaned.get('operador_condicion')
        valor = cleaned.get('valor_condicion')
        if codigo and not operador:
            cleaned['operador_condicion'] = '>='
        if codigo and valor is None:
            raise forms.ValidationError('Si eliges un indicador de condicion, debes ingresar el valor limite.')
        if not codigo:
            cleaned['operador_condicion'] = ''
            cleaned['valor_condicion'] = None
        return cleaned


class EscenarioSimulacionForm(forms.ModelForm):
    class Meta:
        model = EscenarioSimulacion
        fields = ['simulacion', 'titulo', 'situacion', 'orden', 'es_inicial', 'es_final', 'retroalimentacion_final', 'activo']
        widgets = {
            'situacion': forms.Textarea(attrs={'rows': 4}),
            'retroalimentacion_final': forms.Textarea(attrs={'rows': 3}),
        }


class DecisionConfiguradaForm(forms.ModelForm):
    class Meta:
        model = DecisionConfigurada
        fields = ['escenario', 'texto', 'descripcion', 'impacto', 'puntaje_base', 'retroalimentacion', 'siguiente_escenario', 'activo']
        widgets = {
            'descripcion': forms.Textarea(attrs={'rows': 2}),
            'impacto': forms.Textarea(attrs={'rows': 3}),
            'retroalimentacion': forms.Textarea(attrs={'rows': 3}),
        }


class ConceptoEsperadoRondaForm(forms.ModelForm):
    class Meta:
        model = ConceptoEsperadoRonda
        # palabras_clave e impactos NO se piden como JSON: se arman con UI
        # amigable (texto + modo, casillas por indicador) en pro_simulaciones.
        fields = [
            'simulacion', 'escenario', 'numero_ronda', 'nombre', 'descripcion',
            'resultado_aprendizaje', 'peso',
            'retroalimentacion_si_cumple', 'retroalimentacion_si_falta',
            'es_critico', 'activo',
        ]
        widgets = {
            'descripcion': forms.Textarea(attrs={'rows': 2}),
            'retroalimentacion_si_cumple': forms.Textarea(attrs={'rows': 2}),
            'retroalimentacion_si_falta': forms.Textarea(attrs={'rows': 2}),
        }

    def clean_peso(self):
        peso = self.cleaned_data['peso']
        if peso < 0 or peso > 100:
            raise forms.ValidationError('El peso debe estar entre 0 y 100.')
        return peso

    def clean(self):
        cleaned = super().clean()
        simulacion = cleaned.get('simulacion')
        escenario = cleaned.get('escenario')
        numero_ronda = cleaned.get('numero_ronda')
        peso = cleaned.get('peso')

        if not simulacion and not escenario:
            raise forms.ValidationError('Debe seleccionar una simulacion o un escenario.')

        if simulacion and escenario and escenario.simulacion_id != simulacion.id:
            raise forms.ValidationError('El escenario no pertenece a la simulacion seleccionada.')

        if peso is not None:
            qs = ConceptoEsperadoRonda.objects.filter(activo=True)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if escenario:
                qs = qs.filter(escenario=escenario, simulacion__isnull=True, numero_ronda=numero_ronda)
            elif simulacion:
                qs = qs.filter(simulacion=simulacion, escenario__isnull=True, numero_ronda=numero_ronda)
            suma = sum(item.peso for item in qs) + peso
            if suma > 100:
                raise forms.ValidationError(f'La suma de pesos de esta ronda no puede superar 100 (actual: {suma}).')

        return cleaned


class PasoSimulacionForm(forms.Form):
    # required=False para que el campo (oculto en modo hibrido cuando se elige una
    # opcion) no bloquee el envio por validacion HTML. El servidor valida igual.
    decision = forms.CharField(
        required=False,
        max_length=600,
        widget=forms.Textarea(attrs={'rows': 2, 'maxlength': 600}),
    )
    justificacion = forms.CharField(
        required=False,
        max_length=600,
        widget=forms.Textarea(attrs={'rows': 2, 'maxlength': 600}),
    )

    def __init__(self, *args, **kwargs):
        kwargs.pop('ronda', 1)  # Compatibilidad con llamadas existentes.
        super().__init__(*args, **kwargs)
        self.fields['decision'].label = 'Tu respuesta'
        self.fields['decision'].widget.attrs['placeholder'] = 'Escribe una decisión concreta en una frase'
        self.fields['justificacion'].label = 'Explica tu razonamiento'
        self.fields['justificacion'].widget.attrs['placeholder'] = 'Una frase breve: dato del caso + por qué conviene'
