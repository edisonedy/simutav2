from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from core.funciones import conservar_seleccion_actual
from core.models import Institucion, PerfilUsuario

AYUDA_ROL = (
    'Administrador y Coordinador administran el sistema. '
    'Profesor entra al panel docente. Estudiante solo a sus simulaciones.'
)


def _instituciones():
    return Institucion.objects.filter(activo=True)


class UsuarioPerfilCreationForm(UserCreationForm):
    """Crea el usuario y su perfil de una sola vez."""
    first_name = forms.CharField(label='Nombres', required=False)
    last_name = forms.CharField(label='Apellidos', required=False)
    email = forms.EmailField(label='Correo', required=False)
    rol = forms.ChoiceField(label='Rol', choices=PerfilUsuario.ROLES, help_text=AYUDA_ROL)
    institucion = forms.ModelChoiceField(
        label='Institucion', queryset=Institucion.objects.none(), required=False,
    )
    identificacion = forms.CharField(label='Identificacion', required=False)
    telefono = forms.CharField(label='Telefono', required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'password1', 'password2']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['institucion'].queryset = _instituciones()

    def save(self, commit=True, creado_por=None):
        usuario = super().save(commit=False)
        usuario.first_name = self.cleaned_data['first_name']
        usuario.last_name = self.cleaned_data['last_name']
        usuario.email = self.cleaned_data['email']
        usuario.save()
        PerfilUsuario.objects.create(
            usuario=usuario,
            rol=self.cleaned_data['rol'],
            institucion=self.cleaned_data['institucion'],
            identificacion=self.cleaned_data['identificacion'],
            telefono=self.cleaned_data['telefono'],
            usuario_creacion=creado_por,
        )
        return usuario


class PerfilUsuarioForm(forms.ModelForm):
    """Edita el perfil de un usuario que ya existe: rol, institucion y estado."""
    first_name = forms.CharField(label='Nombres', required=False)
    last_name = forms.CharField(label='Apellidos', required=False)
    email = forms.EmailField(label='Correo', required=False)
    activo = forms.BooleanField(
        label='Usuario activo', required=False,
        help_text='Si lo desmarcas, la persona deja de poder entrar al sistema.',
    )

    class Meta:
        model = PerfilUsuario
        fields = ['rol', 'institucion', 'identificacion', 'telefono', 'activo']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['rol'].help_text = AYUDA_ROL
        self.fields['institucion'].queryset = _instituciones()
        self.fields['institucion'].required = False
        conservar_seleccion_actual(self)
        if self.instance.pk:
            usuario = self.instance.usuario
            self.fields['first_name'].initial = usuario.first_name
            self.fields['last_name'].initial = usuario.last_name
            self.fields['email'].initial = usuario.email
            self.fields['activo'].initial = usuario.is_active and self.instance.activo

    def save(self, commit=True):
        perfil = super().save(commit=False)
        activo = self.cleaned_data['activo']
        perfil.activo = activo
        usuario = perfil.usuario
        usuario.first_name = self.cleaned_data['first_name']
        usuario.last_name = self.cleaned_data['last_name']
        usuario.email = self.cleaned_data['email']
        # Un solo interruptor: no tiene sentido un perfil activo con el login cerrado.
        usuario.is_active = activo
        if commit:
            usuario.save()
            perfil.save()
        return perfil


class AsignarPerfilForm(forms.Form):
    """Da un perfil a un usuario que no tiene ninguno: por ejemplo el superusuario
    creado por consola, que sin esto ni siquiera aparece en el listado."""
    usuario = forms.ModelChoiceField(label='Usuario', queryset=User.objects.none())
    rol = forms.ChoiceField(label='Rol', choices=PerfilUsuario.ROLES, help_text=AYUDA_ROL)
    institucion = forms.ModelChoiceField(
        label='Institucion', queryset=Institucion.objects.none(), required=False,
    )
    identificacion = forms.CharField(label='Identificacion', required=False)
    telefono = forms.CharField(label='Telefono', required=False)

    def __init__(self, *args, usuario_fijo=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['institucion'].queryset = _instituciones()
        campo = self.fields['usuario']
        campo.queryset = User.objects.filter(perfil__isnull=True).order_by('username')
        campo.label_from_instance = (
            lambda u: f'{u.get_full_name()} ({u.username})' if u.get_full_name() else u.username
        )
        if usuario_fijo is not None:
            campo.initial = usuario_fijo.pk

    def save(self, creado_por=None):
        return PerfilUsuario.objects.create(
            usuario=self.cleaned_data['usuario'],
            rol=self.cleaned_data['rol'],
            institucion=self.cleaned_data['institucion'],
            identificacion=self.cleaned_data['identificacion'],
            telefono=self.cleaned_data['telefono'],
            usuario_creacion=creado_por,
        )
