from django import forms

from .models import ActividadInteractiva
from .plugins.registry import plugin_choices


class ActividadInteractivaForm(forms.ModelForm):
    motor = forms.ChoiceField(label='Tipo de actividad', choices=())
    configuracion_json = forms.CharField(widget=forms.HiddenInput(), required=False)

    class Meta:
        model = ActividadInteractiva
        fields = [
            'motor',
            'titulo',
            'instrucciones',
            'tema',
            'simulacion',
            'orden',
            'puntaje_minimo',
            'intentos_permitidos',
            'tiempo_limite_segundos',
            'obligatoria',
            'publicada',
        ]
        widgets = {
            'instrucciones': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, materia_malla=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['motor'].choices = plugin_choices()

        self.materia_malla = materia_malla or getattr(self.instance, 'materia_malla', None)
        tema = self.fields['tema']
        caso = self.fields['simulacion']
        tema.label = 'Tema de la materia'
        tema.empty_label = 'Toda la materia'
        caso.label = 'Caso al que prepara'
        caso.empty_label = 'Ninguno: es un juego suelto de la materia'
        if self.materia_malla is None:
            tema.queryset = tema.queryset.none()
            caso.queryset = caso.queryset.none()
        else:
            tema.queryset = tema.queryset.filter(
                materia_malla=self.materia_malla, activo=True,
            )
            caso.queryset = caso.queryset.filter(
                materia_malla=self.materia_malla, activo=True,
            )
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault('class', 'form-check-input')
            elif not isinstance(field.widget, forms.HiddenInput):
                field.widget.attrs.setdefault('class', 'form-control')

    def clean_configuracion_json(self):
        import json

        raw = self.cleaned_data.get('configuracion_json') or '{}'
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError(f'La configuración no es JSON válido: {exc}')
        if not isinstance(value, dict):
            raise forms.ValidationError('La configuración debe ser un objeto JSON.')
        return value
