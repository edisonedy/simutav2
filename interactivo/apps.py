from django.apps import AppConfig


class InteractivoConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'interactivo'
    verbose_name = 'Simuta Interactivo'

    def ready(self):
        from .plugins.registry import autodiscover_plugins
        autodiscover_plugins()
