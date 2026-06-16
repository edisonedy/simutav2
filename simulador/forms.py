from django import forms

from .models import (
    AccionSugeridaSimulacion,
    CondicionExitoSimulacion,
    ConceptoEsperadoRonda,
    CriterioEvaluacion,
    DecisionConfigurada,
    EscenarioSimulacion,
    IndicadorSimulacion,
    IntentoSimulacion,
    PerfilMateriaIA,
    PlantillaConcepto,
    PlantillaIndicador,
    PlantillaRestriccion,
    PlantillaRonda,
    PlantillaSimulacion,
    RestriccionSimulacion,
    Simulacion,
)


class SimulacionForm(forms.ModelForm):
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

    decision = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4}),
    )
    justificacion = forms.CharField(
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
