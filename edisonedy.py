import os
import sys
import csv
import json
import django
from pathlib import Path
from decimal import Decimal
from datetime import date, datetime
from collections import defaultdict

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

# Usa el mismo settings que ya te funcionó
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

django.setup()



import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django

django.setup()

from django.db import connection, transaction



from django.contrib.auth.models import User
from core.permisos import es_administrativo

usuario = User.objects.get(username='emoyolema')

print(usuario.is_superuser)
print(usuario.perfil.rol)
print(es_administrativo(usuario))