import os, sys, json, django
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.utils import timezone
from django.contrib.auth.models import User
from django.db import transaction
from core.models import Institucion
from academico.models import Carrera, Malla, NivelMalla, Materia, MateriaMalla
from simulador.models import (
    Simulacion, IndicadorSimulacion, RestriccionSimulacion,
    CriterioEvaluacion, ConceptoEsperadoRonda,
    EscenarioSimulacion, DecisionConfigurada
)

admin_user = User.objects.filter(is_superuser=True).first()
now = timezone.now()

def safe_bool(v, default=False):
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.lower() in ("true", "1", "yes", "si")
    return default

def safe_int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default

def safe_decimal(v, default=0):
    from decimal import Decimal
    if v is None or v == "":
        return Decimal(str(default))
    try:
        return Decimal(str(v))
    except Exception:
        return Decimal(str(default))

with open(BASE_DIR / "materias_simuta.json", "r", encoding="utf-8") as f:
    materias_data = json.load(f)

print(f"Loaded {len(materias_data)} materias from JSON")

institucion = None
carrera = None
mallas_cache = {}
niveles_cache = {}
materias_cache = {}
materias_malla_cache = {}

@transaction.atomic
def import_all():
    global institucion, carrera

    # --- INSTITUCION ---
    entry = materias_data[0]
    inst_name = entry["datos_materia"]["institucion"]["texto"]
    institucion, created = Institucion.objects.get_or_create(
        nombre=inst_name,
        defaults={
            "siglas": "UTA",
            "ruc": "9999999999999",
            "direccion": "Ambato, Ecuador",
            "usuario_creacion": admin_user,
        }
    )
    if created:
        print(f"Created Institution: {institucion.nombre}")
    else:
        print(f"Found Institution: {institucion.nombre}")

    # --- CARRERA ---
    carrera_name = entry["datos_malla"]["carrera"]["texto"]
    carrera, created = Carrera.objects.get_or_create(
        nombre=carrera_name,
        institucion=institucion,
        defaults={
            "codigo": "ADM-UTA",
            "descripcion": f"Carrera de {carrera_name}",
            "titulo_otorga": "Licenciado/a en Administracion de Empresas",
            "modalidad": "Presencial",
            "duracion_periodos": 8,
            "usuario_creacion": admin_user,
        }
    )
    if created:
        print(f"Created Carrera: {carrera.nombre}")
    else:
        print(f"Found Carrera: {carrera.nombre}")

    for item in materias_data:
        dm = item["datos_materia"]
        dn = item["datos_nivel"]
        dmalla = item["datos_malla"]
        dmm = item["datos_materia_malla"]

        # --- MALLA ---
        malla_key = dmalla["id"]
        if malla_key not in mallas_cache:
            malla_obj, created = Malla.objects.get_or_create(
                carrera=carrera,
                codigo=dmalla["codigo"],
                defaults={
                    "nombre": dmalla["nombre"],
                    "vigente": safe_bool(dmalla.get("vigente"), True),
                    "usuario_creacion": admin_user,
                }
            )
            mallas_cache[malla_key] = malla_obj
            status = "Created" if created else "Found"
            print(f"  {status} Malla: {malla_obj.nombre}")

        # --- NIVEL ---
        nivel_key = dn["id"]
        if nivel_key not in niveles_cache:
            malla_ref = mallas_cache[dmalla["id"]]
            nivel_obj, created = NivelMalla.objects.get_or_create(
                malla=malla_ref,
                numero=safe_int(dn["numero"]),
                defaults={
                    "nombre": dn["nombre"],
                    "usuario_creacion": admin_user,
                }
            )
            niveles_cache[nivel_key] = nivel_obj
            status = "Created" if created else "Found"
            print(f"    {status} Nivel: {nivel_obj.nombre} (semestre {nivel_obj.numero})")

        # --- MATERIA ---
        materia_key = dm["id"]
        if materia_key not in materias_cache:
            materia_obj, created = Materia.objects.get_or_create(
                institucion=institucion,
                codigo=dm["codigo"],
                defaults={
                    "nombre": dm["nombre"],
                    "descripcion": dm.get("descripcion", ""),
                    "creditos": safe_int(dm.get("creditos")),
                    "horas": safe_int(dm.get("horas")),
                    "usuario_creacion": admin_user,
                }
            )
            materias_cache[materia_key] = materia_obj
            status = "Created" if created else "Found"

        # --- MATERIA MALLA ---
        dmm_id_str = str(item["materia_malla_id"])
        mm_obj, created = MateriaMalla.objects.get_or_create(
            malla=mallas_cache[dmalla["id"]],
            materia=materias_cache[materia_key],
            defaults={
                "nivel": niveles_cache[nivel_key],
                "orden": item["orden"],
                "obligatoria": item["obligatoria"],
                "usuario_creacion": admin_user,
            }
        )
        materias_malla_cache[item["materia_malla_id"]] = mm_obj
        if created:
            print(f"      Created MateriaMalla #{item['materia_malla_id']}: {materias_cache[materia_key].nombre} (orden {item['orden']})")

    print(f"\nImport complete: {len(mallas_cache)} mallas, {len(niveles_cache)} niveles, {len(materias_cache)} materias, {len(materias_malla_cache)} materia-malla links")

import_all()
