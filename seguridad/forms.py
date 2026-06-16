from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from core.models import PerfilUsuario


class UsuarioPerfilCreationForm(UserCreationForm):
    first_name = forms.CharField(label='Nombres', required=False)
    last_name = forms.CharField(label='Apellidos', required=False)
    email = forms.EmailField(label='Correo', required=False)
    rol = forms.ChoiceField(label='Rol', choices=PerfilUsuario.ROLES)
    institucion = forms.ModelChoiceField(
        label='Institucion',
        queryset=PerfilUsuario._meta.get_field('institucion').remote_field.model.objects.all(),
        required=False,
    )
    identificacion = forms.CharField(label='Identificacion', required=False)
    telefono = forms.CharField(label='Telefono', required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'password1', 'password2']
