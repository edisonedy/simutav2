"""Paquete de servicios del simulador.

El motor principal vive en `core.py`; el motor de opciones dinamicas en
`motor_dinamico.py`. Se reexporta todo aqui para que el resto de la app pueda
seguir usando `from simulador.services import ...` sin cambios.
"""

from .core import *  # noqa: F401,F403
# Nombres con guion bajo usados fuera del paquete (no entran con import *).
from .core import _normalizar_texto  # noqa: F401
from . import motor_dinamico  # noqa: F401
