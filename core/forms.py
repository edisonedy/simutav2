from django import forms

from .models import Institucion


class InstitucionForm(forms.ModelForm):
    class Meta:
        model = Institucion
        fields = ['nombre', 'siglas', 'ruc', 'direccion', 'telefono', 'email', 'activo']
