from django import forms

from .models import (
    Carrera,
    InscripcionMalla,
    Malla,
    Materia,
    MateriaMalla,
    NivelMalla,
    PeriodoAcademico,
    ProfesorMateria,
)


class DateInput(forms.DateInput):
    input_type = 'date'

    def __init__(self, attrs=None):
        super().__init__(attrs=attrs, format='%Y-%m-%d')


class ActiveQuerysetsMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            queryset = getattr(field, 'queryset', None)
            if queryset is not None and hasattr(queryset.model, 'activo'):
                field.queryset = queryset.filter(activo=True)


def validate_date_range(cleaned_data):
    fecha_inicio = cleaned_data.get('fecha_inicio')
    fecha_fin = cleaned_data.get('fecha_fin')
    if fecha_inicio and fecha_fin and fecha_fin < fecha_inicio:
        raise forms.ValidationError('La fecha fin no puede ser anterior a la fecha inicio.')


class CarreraForm(ActiveQuerysetsMixin, forms.ModelForm):
    class Meta:
        model = Carrera
        fields = [
            'institucion',
            'nombre',
            'codigo',
            'titulo_otorga',
            'modalidad',
            'duracion_periodos',
            'descripcion',
            'activo',
        ]


class MallaForm(ActiveQuerysetsMixin, forms.ModelForm):
    class Meta:
        model = Malla
        fields = ['carrera', 'nombre', 'codigo', 'fecha_inicio', 'fecha_fin', 'vigente', 'activo']
        widgets = {'fecha_inicio': DateInput(), 'fecha_fin': DateInput()}

    def clean(self):
        cleaned = super().clean()
        validate_date_range(cleaned)
        return cleaned


class NivelMallaForm(forms.ModelForm):
    class Meta:
        model = NivelMalla
        fields = ['numero', 'nombre', 'activo']


class MateriaForm(ActiveQuerysetsMixin, forms.ModelForm):
    class Meta:
        model = Materia
        fields = ['institucion', 'codigo', 'nombre', 'descripcion', 'creditos', 'horas', 'activo']


class MateriaMallaForm(ActiveQuerysetsMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.malla = kwargs.pop('malla', None)
        super().__init__(*args, **kwargs)
        if self.malla:
            self.fields['nivel'].queryset = NivelMalla.objects.filter(malla=self.malla, activo=True)
            self.fields['materia'].queryset = Materia.objects.filter(
                institucion=self.malla.carrera.institucion,
                activo=True,
            )

    class Meta:
        model = MateriaMalla
        fields = ['nivel', 'materia', 'orden', 'obligatoria', 'activo']

    def clean(self):
        cleaned = super().clean()
        nivel = cleaned.get('nivel')
        materia = cleaned.get('materia')
        if self.malla and nivel and nivel.malla_id != self.malla.id:
            raise forms.ValidationError('El nivel seleccionado no pertenece a esta malla.')
        if self.malla and materia and materia.institucion_id != self.malla.carrera.institucion_id:
            raise forms.ValidationError('La materia seleccionada no pertenece a la institucion de la carrera.')
        return cleaned


class PeriodoAcademicoForm(ActiveQuerysetsMixin, forms.ModelForm):
    class Meta:
        model = PeriodoAcademico
        fields = ['institucion', 'nombre', 'fecha_inicio', 'fecha_fin', 'activo_matricula', 'activo']
        widgets = {'fecha_inicio': DateInput(), 'fecha_fin': DateInput()}

    def clean(self):
        cleaned = super().clean()
        validate_date_range(cleaned)
        return cleaned


class InscripcionMallaForm(ActiveQuerysetsMixin, forms.ModelForm):
    class Meta:
        model = InscripcionMalla
        fields = ['estudiante', 'malla', 'periodo', 'estado', 'activo']

    def clean(self):
        cleaned = super().clean()
        malla = cleaned.get('malla')
        periodo = cleaned.get('periodo')
        if malla and periodo and malla.carrera.institucion_id != periodo.institucion_id:
            raise forms.ValidationError('La malla y el periodo deben pertenecer a la misma institucion.')
        return cleaned


class ProfesorMateriaForm(ActiveQuerysetsMixin, forms.ModelForm):
    class Meta:
        model = ProfesorMateria
        fields = ['profesor', 'materia_malla', 'periodo', 'activo']

    def clean(self):
        cleaned = super().clean()
        materia_malla = cleaned.get('materia_malla')
        periodo = cleaned.get('periodo')
        if (
            materia_malla
            and periodo
            and materia_malla.malla.carrera.institucion_id != periodo.institucion_id
        ):
            raise forms.ValidationError('La materia y el periodo deben pertenecer a la misma institucion.')
        return cleaned
