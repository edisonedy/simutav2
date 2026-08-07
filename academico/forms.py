from django import forms
from django.urls import reverse_lazy
from django.utils.html import format_html

from core.funciones import conservar_seleccion_actual
from core.models import PerfilUsuario
from core.permisos import usuarios_con_rol


def etiqueta_materia_malla(materia_malla):
    """Un unico nombre para la materia curricular en todos los desplegables del
    sistema: MALLA / Nivel N - CODIGO Nombre."""
    return materia_malla.etiqueta


def _ayuda_por_rol(quienes):
    """Explica por que la lista sale corta y donde se arregla, en vez de dejar
    al usuario adivinando por que falta alguien."""
    return format_html(
        'Solo aparecen los usuarios activos con perfil de <strong>{}</strong>. '
        'Si falta alguien, cambiale el rol en <a href="{}" target="_blank">Usuarios y perfiles</a>.',
        quienes, reverse_lazy('seguridad:usuarios'),
    )

from .models import (
    Carrera,
    InscripcionMalla,
    Malla,
    Materia,
    MateriaMalla,
    MateriaMallaPredecesora,
    MateriaPeriodo,
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
        conservar_seleccion_actual(self)


def validate_date_range(cleaned_data):
    fecha_inicio = cleaned_data.get('fecha_inicio')
    fecha_fin = cleaned_data.get('fecha_fin')
    if fecha_inicio and fecha_fin and fecha_fin < fecha_inicio:
        raise forms.ValidationError('La fecha fin no puede ser anterior a la fecha inicio.')


class CarreraForm(ActiveQuerysetsMixin, forms.ModelForm):
    class Meta:
        model = Carrera
        fields = [
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
        fields = ['codigo', 'nombre', 'descripcion', 'creditos', 'horas', 'activo']


class MateriaMallaForm(ActiveQuerysetsMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.malla = kwargs.pop('malla', None)
        super().__init__(*args, **kwargs)
        self.fields['materia'].label = 'Asignatura del catalogo'
        self.fields['nivel'].label = 'Nivel de la malla'
        if self.malla:
            self.fields['nivel'].queryset = NivelMalla.objects.filter(malla=self.malla, activo=True)
            self.fields['materia'].queryset = Materia.objects.filter(activo=True)
            conservar_seleccion_actual(self)

    class Meta:
        model = MateriaMalla
        fields = ['nivel', 'materia', 'orden', 'obligatoria', 'activo']

    def clean(self):
        cleaned = super().clean()
        nivel = cleaned.get('nivel')
        if self.malla and nivel and nivel.malla_id != self.malla.id:
            raise forms.ValidationError('El nivel seleccionado no pertenece a esta malla.')
        return cleaned


class MateriaMallaPredecesoraForm(forms.ModelForm):
    """Alta de un requisito. Solo ofrece materias de la misma malla que esten en
    un nivel anterior, que es la unica combinacion que el modelo acepta."""

    class Meta:
        model = MateriaMallaPredecesora
        fields = ['predecesora']

    def __init__(self, *args, **kwargs):
        self.materia_malla = kwargs.pop('materia_malla', None)
        super().__init__(*args, **kwargs)
        campo = self.fields['predecesora']
        campo.label = 'Requisito'
        if self.materia_malla is None:
            campo.queryset = MateriaMalla.objects.none()
            return
        self.instance.materia_malla = self.materia_malla
        ya_puestas = self.materia_malla.predecesoras.filter(activo=True).values_list(
            'predecesora_id', flat=True,
        )
        campo.queryset = MateriaMalla.objects.filter(
            malla_id=self.materia_malla.malla_id,
            nivel__numero__lt=self.materia_malla.nivel.numero,
            activo=True,
        ).exclude(pk__in=list(ya_puestas)).select_related('materia', 'nivel')
        campo.label_from_instance = lambda mm: f'Nivel {mm.nivel.numero} - {mm.materia}'
        campo.help_text = 'Solo materias de niveles anteriores de esta misma malla.'

    def clean_predecesora(self):
        predecesora = self.cleaned_data['predecesora']
        # El unique_together no lo revisa el formulario porque materia_malla no
        # es un campo suyo; hay que comprobarlo a mano.
        if self.materia_malla and MateriaMallaPredecesora.objects.filter(
            materia_malla=self.materia_malla, predecesora=predecesora, activo=True,
        ).exists():
            raise forms.ValidationError('Ese requisito ya esta registrado.')
        return predecesora


class MateriaPeriodoForm(forms.ModelForm):
    """Crea UNA materia dentro de una malla abierta en el periodo.

    Solo ofrece asignaturas de esa misma malla y que no tengan materia todavia,
    que son las dos reglas que el modelo valida."""

    class Meta:
        model = MateriaPeriodo
        fields = ['materia_malla']

    def __init__(self, *args, malla_periodo=None, nivel=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.malla_periodo = malla_periodo
        self.nivel = nivel
        campo = self.fields['materia_malla']
        campo.label = 'Asignatura de la malla'
        if malla_periodo is None:
            campo.queryset = MateriaMalla.objects.none()
            return
        self.instance.malla_periodo = malla_periodo
        campo.queryset = malla_periodo.asignaturas_disponibles()
        campo.help_text = (
            'Solo las asignaturas de esta malla que aun no tienen materia en el periodo.'
        )
        if nivel is not None:
            # Se entro desde un nivel concreto: no tiene sentido ofrecer los otros.
            campo.queryset = campo.queryset.filter(nivel=nivel)
            campo.label_from_instance = lambda mm: str(mm.materia)
            campo.help_text = (
                f'Solo las asignaturas del nivel {nivel.numero} que aun no tienen '
                'materia en el periodo.'
            )
        else:
            campo.label_from_instance = lambda mm: f'Nivel {mm.nivel.numero} - {mm.materia}'

    def clean_materia_malla(self):
        materia_malla = self.cleaned_data['materia_malla']
        # El unique_together lleva malla_periodo, que no es campo del
        # formulario, asi que Django se lo salta y hay que mirarlo a mano.
        if self.malla_periodo and MateriaPeriodo.objects.filter(
            malla_periodo=self.malla_periodo, materia_malla=materia_malla, activo=True,
        ).exists():
            raise forms.ValidationError('Esa asignatura ya tiene materia en este periodo.')
        return materia_malla


class PeriodoAcademicoForm(ActiveQuerysetsMixin, forms.ModelForm):
    class Meta:
        model = PeriodoAcademico
        fields = ['nombre', 'fecha_inicio', 'fecha_fin', 'activo_matricula', 'activo']
        widgets = {'fecha_inicio': DateInput(), 'fecha_fin': DateInput()}

    def clean(self):
        cleaned = super().clean()
        validate_date_range(cleaned)
        return cleaned


class InscripcionMallaForm(ActiveQuerysetsMixin, forms.ModelForm):
    class Meta:
        model = InscripcionMalla
        fields = ['estudiante', 'malla', 'periodo', 'estado', 'activo']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        estudiante = self.fields['estudiante']
        estudiante.queryset = usuarios_con_rol(PerfilUsuario.ESTUDIANTE).order_by(
            'last_name', 'first_name', 'username',
        )
        estudiante.label_from_instance = self._etiqueta_estudiante
        estudiante.help_text = _ayuda_por_rol('Estudiante')
        conservar_seleccion_actual(self)

    @staticmethod
    def _etiqueta_estudiante(usuario):
        nombre = usuario.get_full_name() or usuario.username
        identificacion = getattr(getattr(usuario, 'perfil', None), 'identificacion', '')
        return f'{nombre} ({identificacion})' if identificacion else nombre


class ProfesorMateriaForm(ActiveQuerysetsMixin, forms.ModelForm):
    ROLES_DOCENTES = [PerfilUsuario.PROFESOR, PerfilUsuario.COORDINADOR, PerfilUsuario.ADMIN]

    class Meta:
        model = ProfesorMateria
        fields = ['profesor', 'materia_malla', 'periodo', 'activo']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        materia = self.fields['materia_malla']
        materia.label = 'Materia de la malla'
        materia.queryset = materia.queryset.select_related('malla', 'nivel', 'materia')
        materia.label_from_instance = etiqueta_materia_malla
        profesor = self.fields['profesor']
        profesor.queryset = usuarios_con_rol(*self.ROLES_DOCENTES).order_by(
            'last_name', 'first_name', 'username',
        )
        profesor.label_from_instance = lambda u: u.get_full_name() or u.username
        profesor.help_text = _ayuda_por_rol('Profesor, Coordinador o Administrador')
        conservar_seleccion_actual(self)
