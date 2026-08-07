from django.contrib import admin

from .models import PerfilUsuario


@admin.register(PerfilUsuario)
class PerfilUsuarioAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'rol', 'activo')
    list_filter = ('rol', 'activo')
    search_fields = ('usuario__username', 'usuario__first_name', 'usuario__last_name', 'identificacion')

# Register your models here.
