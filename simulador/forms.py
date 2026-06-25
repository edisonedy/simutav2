from django import forms

from .models import (
    AccionSugeridaSimulacion,
    CondicionExitoSimulacion,
    ConceptoEsperadoRonda,
    CriterioEvaluacion,
    DecisionConfigurada,
    EscenarioSimulacion,
    EventoSimulacion,
    IndicadorSimulacion,
    IntentoSimulacion,
    MatrizEvaluacionCaso,
    OpcionCasoSimulacion,
    PerfilMateriaIA,
    PlantillaConcepto,
    PlantillaIndicador,
    PlantillaRestriccion,
    PlantillaRonda,
    PlantillaSimulacion,
    RecursoSimulacion,
    RestriccionSimulacion,
    Simulacion,
)


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
        self.fields['maximo_decisiones'].label = 'Rondas que tendra el caso'
        self.fields['maximo_decisiones'].help_text = 'Cuantas decisiones o etapas tendra la simulacion.'
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
    class Meta:
        model = Simulacion
        fields = [
            'materia_malla', 'plantilla_origen', 'perfil_materia_ia',
            'tipo_simulacion', 'titulo', 'tema',
            'nivel_dificultad', 'maximo_decisiones', 'tiempo_estimado',
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
            'maximo_decisiones', 'tiempo_estimado', 'nivel_dificultad',
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
        fields = ['simulacion', 'nombre', 'codigo', 'valor_inicial', 'valor_minimo', 'valor_maximo', 'direccion_optima', 'es_critico', 'unidad', 'activo']


class RecursoSimulacionForm(forms.ModelForm):
    class Meta:
        model = RecursoSimulacion
        fields = ['simulacion', 'nombre', 'codigo', 'valor_inicial', 'valor_minimo', 'valor_maximo', 'unidad', 'es_critico', 'activo']


class RestriccionSimulacionForm(forms.ModelForm):
    class Meta:
        model = RestriccionSimulacion
        fields = ['simulacion', 'descripcion', 'codigo_indicador', 'operador', 'valor_limite', 'penalizacion', 'activo']
        widgets = {'descripcion': forms.Textarea(attrs={'rows': 2})}


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
        fields = ['simulacion', 'numero_ronda', 'texto', 'descripcion', 'activo']
        widgets = {
            'descripcion': forms.Textarea(attrs={'rows': 2}),
        }


class CondicionExitoForm(forms.ModelForm):
    class Meta:
        model = CondicionExitoSimulacion
        fields = ['simulacion', 'descripcion', 'codigo_indicador', 'operador', 'valor_objetivo', 'bonificacion', 'activo']


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
            'peso',
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
    LABELS_POR_RONDA = {
        1: ('Diagnóstico', 'Justificación del diagnóstico'),
        2: ('Decisión', 'Justificación de la decisión'),
        3: ('Plan de implementación', 'Justificación, control y seguimiento'),
    }

    # required=False para que el campo (oculto en modo hibrido cuando se elige una
    # opcion) no bloquee el envio por validacion HTML. El servidor valida igual.
    decision = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 4}),
    )
    justificacion = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 4}),
    )

    def __init__(self, *args, **kwargs):
        ronda = kwargs.pop('ronda', 1)
        super().__init__(*args, **kwargs)
        labels = self.LABELS_POR_RONDA.get(ronda, ('Decisión', 'Justificación'))
        self.fields['decision'].label = labels[0]
        self.fields['decision'].widget.attrs['placeholder'] = f'Describe {labels[0].lower()} para esta situacion'
        self.fields['justificacion'].label = labels[1]
        self.fields['justificacion'].widget.attrs['placeholder'] = f'Explica {labels[1].lower()}'
