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





from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

try:
    r = client.responses.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        input="Responde solo con la palabra OK"
    )

    print("✅ API RESPONDE")
    print("Respuesta:", r.output_text)

    if hasattr(r, "usage") and r.usage:
        print("Uso tokens:", r.usage)

except Exception as e:
    print("❌ API NO RESPONDE")
    print("Tipo error:", type(e).__name__)
    print("Detalle:", str(e))