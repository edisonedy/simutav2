from __future__ import annotations

from copy import deepcopy
from typing import Any


class PluginError(ValueError):
    pass


class PluginActividadBase:
    codigo = ''
    nombre = ''
    descripcion = ''
    version = '1.0.0'
    schema: dict[str, Any] = {'fields': []}
    renderer = ''
    player_js = ''
    player_css = ''

    def normalize_config(self, config: dict[str, Any]) -> dict[str, Any]:
        return deepcopy(config)

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        return []

    def editor_config(self, config: dict[str, Any]) -> dict[str, Any]:
        return deepcopy(config)

    def public_config(self, config: dict[str, Any]) -> dict[str, Any]:
        return deepcopy(config)

    def grade(self, config: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @staticmethod
    def result(aciertos: int, total: int, detalle: dict | None = None) -> dict[str, Any]:
        total = max(int(total), 0)
        aciertos = min(max(int(aciertos), 0), total) if total else 0
        errores = max(total - aciertos, 0)
        porcentaje = round((aciertos * 100 / total), 2) if total else 0
        return {
            'aciertos': aciertos,
            'errores': errores,
            'total': total,
            'puntaje': porcentaje,
            'puntaje_maximo': 100,
            'porcentaje': porcentaje,
            'detalle': detalle or {},
        }
