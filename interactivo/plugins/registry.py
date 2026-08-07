from __future__ import annotations

import importlib
import pkgutil
from collections import OrderedDict

from .base import PluginActividadBase, PluginError


_REGISTRY: OrderedDict[str, PluginActividadBase] = OrderedDict()
_DISCOVERED = False


def register_plugin(plugin_class):
    plugin = plugin_class()
    if not plugin.codigo:
        raise PluginError(f'{plugin_class.__name__} no define codigo.')
    if plugin.codigo in _REGISTRY:
        raise PluginError(f'Plugin duplicado: {plugin.codigo}')
    _REGISTRY[plugin.codigo] = plugin
    return plugin_class


def autodiscover_plugins():
    global _DISCOVERED
    if _DISCOVERED:
        return
    package = importlib.import_module('interactivo.plugins')
    ignored = {'base', 'registry'}
    for module in pkgutil.iter_modules(package.__path__):
        if module.name.startswith('_') or module.name in ignored:
            continue
        importlib.import_module(f'interactivo.plugins.{module.name}')
    _DISCOVERED = True


def get_plugin(codigo: str) -> PluginActividadBase:
    autodiscover_plugins()
    plugin = _REGISTRY.get(codigo)
    if plugin is None:
        raise PluginError(f'No existe o no está instalado el motor "{codigo}".')
    return plugin


def all_plugins():
    autodiscover_plugins()
    return list(_REGISTRY.values())


def plugin_choices():
    return [(plugin.codigo, plugin.nombre) for plugin in all_plugins()]
