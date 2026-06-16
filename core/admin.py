from django.contrib import admin

from .models import Institucion, PerfilUsuario


@admin.register(Institucion)
class InstitucionAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'siglas', 'ruc', 'activo')
    search_fields = ('nombre', 'siglas', 'ruc')


@admin.register(PerfilUsuario)
class PerfilUsuarioAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'rol', 'institucion', 'activo')
    list_filter = ('rol', 'institucion', 'activo')
    search_fields = ('usuario__username', 'usuario__first_name', 'usuario__last_name', 'identificacion')

# Register your models here.
