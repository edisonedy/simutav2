import os, sys, json, django
from pathlib import Path
from decimal import Decimal
from collections import defaultdict

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.utils import timezone
from django.contrib.auth.models import User
from django.db import transaction
from academico.models import MateriaMalla
from simulador.models import (
    Simulacion, IndicadorSimulacion, RestriccionSimulacion,
    CriterioEvaluacion, ConceptoEsperadoRonda,
    EscenarioSimulacion
)

admin_user = User.objects.filter(is_superuser=True).first()
now = timezone.now()

def safe_decimal(v, default=0):
    if v is None or v == "":
        return Decimal(str(default))
    try:
        return Decimal(str(v))
    except Exception:
        return Decimal(str(default))

with open(BASE_DIR / "auditoria_simuta.json", "r", encoding="utf-8") as f:
    auditoria = json.load(f)

print(f"Loaded {len(auditoria)} entries from auditoria_simuta.json")
total_simulaciones = sum(len(e["simulaciones"]) for e in auditoria)
print(f"Total simulaciones to import: {total_simulaciones}")

created_count = 0
skipped_count = 0

@transaction.atomic
def import_simulaciones():
    global created_count, skipped_count

    for entry in auditoria:
        mm_id = entry["materia_malla_id"]
        try:
            mm = MateriaMalla.objects.get(id=mm_id)
        except MateriaMalla.DoesNotExist:
            print(f"  SKIP: MateriaMalla #{mm_id} not found in DB")
            continue

        for s in entry["simulaciones"]:
            # Check if already exists by title+materia_malla
            existing = Simulacion.objects.filter(
                materia_malla=mm,
                titulo=s["titulo"]
            ).first()
            if existing:
                skipped_count += 1
                continue

            # Create Simulacion
            simulacion = Simulacion.objects.create(
                materia_malla=mm,
                usuario_creacion=admin_user,
                titulo=s["titulo"],
                estado=s.get("estado", "PUBLICADA"),
                tipo_simulacion=s.get("tipo_simulacion", "CON_IA_DINAMICA"),
                tema=s.get("tema", ""),
                nivel_dificultad=s.get("nivel_dificultad", "MEDIA"),
                maximo_decisiones=s.get("maximo_decisiones", 3),
                tiempo_estimado=s.get("tiempo_estimado", 25),
                rol_estudiante=s.get("rol_estudiante", ""),
                contexto=s.get("contexto", ""),
                objetivo=s.get("objetivo", ""),
                resultado_aprendizaje=s.get("resultado_aprendizaje", ""),
                situacion_inicial=s.get("situacion_inicial", ""),
                instrucciones_ia=s.get("instrucciones_ia", ""),
                nivel_ayuda_ia=s.get("nivel_ayuda_ia", "MEDIA"),
                tono_retroalimentacion=s.get("tono_retroalimentacion", "Formativo y claro"),
            )

            # Create Indicadores
            for ind in s.get("indicadores", []):
                IndicadorSimulacion.objects.create(
                    simulacion=simulacion,
                    codigo=ind.get("codigo", ""),
                    nombre=ind.get("nombre", ""),
                    valor_inicial=safe_decimal(ind.get("valor_inicial"), 50),
                    valor_minimo=safe_decimal(ind.get("valor_minimo"), 0),
                    valor_maximo=safe_decimal(ind.get("valor_maximo"), 100),
                    direccion_optima=ind.get("direccion_optima", "ALTO"),
                    es_critico=ind.get("es_critico", False),
                    unidad=ind.get("unidad", "pts"),
                )

            # Create Restricciones
            for r in s.get("restricciones", []):
                RestriccionSimulacion.objects.create(
                    simulacion=simulacion,
                    descripcion=r.get("descripcion", ""),
                    codigo_indicador=r.get("codigo_indicador", ""),
                    operador=r.get("operador", ">="),
                    valor_limite=safe_decimal(r.get("valor_limite"), 0),
                    penalizacion=safe_decimal(r.get("penalizacion"), 5),
                )

            # Create Criterios
            for c in s.get("criterios", []):
                CriterioEvaluacion.objects.create(
                    simulacion=simulacion,
                    nombre=c.get("nombre", ""),
                    descripcion=c.get("descripcion", ""),
                    peso=safe_decimal(c.get("peso"), 0),
                    puntaje_maximo=safe_decimal(c.get("puntaje_maximo"), 100),
                )

            # Create ConceptosEsperados by round
            for ronda_str, conceptos in s.get("conceptos_por_ronda", {}).items():
                numero_ronda = int(ronda_str)
                for c in conceptos:
                    ConceptoEsperadoRonda.objects.create(
                        simulacion=simulacion,
                        numero_ronda=numero_ronda,
                        nombre=c.get("nombre", ""),
                        descripcion=c.get("descripcion", ""),
                        palabras_clave=c.get("palabras_clave", ""),
                        peso=safe_decimal(c.get("peso"), 0),
                        es_critico=c.get("es_critico", False),
                        impacto_si_cumple=c.get("impacto_si_cumple", {}),
                        impacto_si_falta=c.get("impacto_si_falta", {}),
                        retroalimentacion_si_cumple=c.get("retroalimentacion_si_cumple", ""),
                        retroalimentacion_si_falta=c.get("retroalimentacion_si_falta", ""),
                    )

            # Create Escenarios from preguntas_detectadas
            pd = s.get("preguntas_detectadas", {})
            for esc in pd.get("escenarios_arbol", []):
                EscenarioSimulacion.objects.create(
                    simulacion=simulacion,
                    titulo=esc.get("titulo", ""),
                    situacion=esc.get("situacion", ""),
                    orden=esc.get("orden", 1),
                    es_inicial=esc.get("es_inicial", False),
                    es_final=esc.get("es_final", False),
                    retroalimentacion_final=esc.get("retroalimentacion_final", ""),
                )

            created_count += 1
            if created_count % 5 == 0:
                print(f"  Created {created_count}/{total_simulaciones} simulaciones...")

import_simulaciones()
print(f"\nImport complete: {created_count} created, {skipped_count} skipped (duplicates)")
