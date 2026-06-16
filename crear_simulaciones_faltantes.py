import os, sys, json, django
from pathlib import Path
from decimal import Decimal

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.contrib.auth.models import User
from django.db import transaction
from academico.models import MateriaMalla
from simulador.models import (
    Simulacion, IndicadorSimulacion, RestriccionSimulacion,
    CriterioEvaluacion, ConceptoEsperadoRonda
)

admin_user = User.objects.filter(is_superuser=True).first()

simulaciones_faltantes = [
    {
        "materia_malla_id": 32,
        "titulo": "Examen SimutaV2 - Programacion Web con Django",
        "tema": "Desarrollo de aplicaciones web con Django",
        "nivel_dificultad": "MEDIA",
        "maximo_decisiones": 3,
        "tiempo_estimado": 30,
        "rol_estudiante": "Desarrollador Web Django",
        "contexto": "WebTech Solutions necesita desarrollar un modulo de gestion de usuarios para su plataforma SaaS. El equipo debe decidir entre usar Class-Based Views o Function-Based Views, implementar autenticacion JWT o sesiones, y elegir entre PostgreSQL o MySQL para la base de datos.",
        "objetivo": "Aplicar conceptos de Django para disenar una solucion web completa, evaluando alternativas tecnicas y buenas practicas de desarrollo.",
        "resultado_aprendizaje": "El estudiante entrega una decision tecnica sustentada con arquitectura, seguridad y rendimiento.",
        "situacion_inicial": "WebTech Solutions tiene una plataforma SaaS con 500 usuarios activos. Necesita implementar un modulo de gestion de usuarios con registro, autenticacion y perfiles. Como desarrollador Django, disena la arquitectura del modulo y justifica tus decisiones tecnicas.",
        "instrucciones_ia": "Evalua solo contra la rubrica configurada. No inventes puntos.",
        "nivel_ayuda_ia": "MEDIA",
        "tono_retroalimentacion": "Formativo y claro",
        "indicadores": [
            {"codigo": "arquitectura", "nombre": "Calidad de la arquitectura", "valor_inicial": 50, "valor_minimo": 0, "valor_maximo": 100, "direccion_optima": "ALTO", "es_critico": True, "unidad": "pts"},
            {"codigo": "seguridad", "nombre": "Nivel de seguridad", "valor_inicial": 50, "valor_minimo": 0, "valor_maximo": 100, "direccion_optima": "ALTO", "es_critico": True, "unidad": "pts"},
            {"codigo": "rendimiento", "nombre": "Rendimiento esperado", "valor_inicial": 50, "valor_minimo": 0, "valor_maximo": 100, "direccion_optima": "ALTO", "es_critico": False, "unidad": "pts"},
            {"codigo": "mantenibilidad", "nombre": "Mantenibilidad del codigo", "valor_inicial": 50, "valor_minimo": 0, "valor_maximo": 100, "direccion_optima": "ALTO", "es_critico": False, "unidad": "pts"},
        ],
        "restricciones": [
            {"descripcion": "La arquitectura debe ser escalable", "codigo_indicador": "arquitectura", "operador": ">=", "valor_limite": 40, "penalizacion": 15},
            {"descripcion": "Debe incluir medidas de seguridad basicas", "codigo_indicador": "seguridad", "operador": ">=", "valor_limite": 40, "penalizacion": 15},
        ],
        "criterios": [
            {"nombre": "Arquitectura y diseno", "descripcion": "Evaluacion de la arquitectura propuesta", "peso": 35, "puntaje_maximo": 100},
            {"nombre": "Seguridad y buenas practicas", "descripcion": "Evaluacion de seguridad y codigo limpio", "peso": 30, "puntaje_maximo": 100},
            {"nombre": "Justificacion tecnica", "descripcion": "Claridad en la justificacion de decisiones", "peso": 20, "puntaje_maximo": 100},
            {"nombre": "Completitud", "descripcion": "Completitud de la solucion propuesta", "peso": 15, "puntaje_maximo": 100},
        ],
        "conceptos_por_ronda": {
            1: [
                {"nombre": "Analisis tecnico", "descripcion": "Identifica requerimientos y restricciones", "palabras_clave": '{"any": ["requisito", "requerimiento", "analisis", "necesidad", "alcance", "restriccion"]}', "peso": 35, "es_critico": True, "impacto_si_cumple": {"arquitectura": 15, "seguridad": 5}, "impacto_si_falta": {"arquitectura": -10}, "retroalimentacion_si_cumple": "Buen analisis tecnico", "retroalimentacion_si_falta": "Falta analisis tecnico"},
                {"nombre": "Alternativas tecnologicas", "descripcion": "Compara opciones tecnologicas", "palabras_clave": '{"any": ["alternativa", "opcion", "comparar", "versus", "ventaja", "desventaja", "evaluar"]}', "peso": 25, "es_critico": False, "impacto_si_cumple": {"arquitectura": 10, "mantenibilidad": 5}, "impacto_si_falta": {}, "retroalimentacion_si_cumple": "Buen analisis de alternativas", "retroalimentacion_si_falta": "Falta analisis de alternativas"},
                {"nombre": "Conceptos de Django", "descripcion": "Aplica conceptos de Django correctamente", "palabras_clave": '{"any": ["django", "modelo", "vista", "template", "orm", "url", "middleware", "admin"]}', "peso": 30, "es_critico": True, "impacto_si_cumple": {"arquitectura": 12, "mantenibilidad": 10}, "impacto_si_falta": {"arquitectura": -15}, "retroalimentacion_si_cumple": "Buen uso de conceptos Django", "retroalimentacion_si_falta": "Faltan conceptos Django"},
            ],
            2: [
                {"nombre": "Decision de diseno", "descripcion": "Toma una decision de diseno concreta", "palabras_clave": '{"any": ["decision", "elegir", "implementar", "usar", "adoptar", "disenar", "crear"]}', "peso": 35, "es_critico": True, "impacto_si_cumple": {"arquitectura": 12, "rendimiento": 10}, "impacto_si_falta": {"rendimiento": -10}, "retroalimentacion_si_cumple": "Decision de diseno clara", "retroalimentacion_si_falta": "Falta decision de diseno"},
                {"nombre": "Plan de implementacion", "descripcion": "Propone un plan de implementacion viable", "palabras_clave": '{"any": ["plan", "implementacion", "paso", "etapa", "fase", "cronograma", "tarea"]}', "peso": 30, "es_critico": False, "impacto_si_cumple": {"rendimiento": 8, "mantenibilidad": 8}, "impacto_si_falta": {}, "retroalimentacion_si_cumple": "Plan de implementacion claro", "retroalimentacion_si_falta": "Falta plan de implementacion"},
            ],
            3: [
                {"nombre": "Metricas y control", "descripcion": "Define metricas para evaluar el exito", "palabras_clave": '{"any": ["metrica", "indicador", "medir", "evaluar", "control", "kpi", "monitoreo"]}', "peso": 35, "es_critico": True, "impacto_si_cumple": {"seguridad": 10, "rendimiento": 12}, "impacto_si_falta": {"seguridad": -10}, "retroalimentacion_si_cumple": "Buenas metricas de control", "retroalimentacion_si_falta": "Faltan metricas de control"},
                {"nombre": "Conclusion y entregables", "descripcion": "Presenta conclusiones y entregables claros", "palabras_clave": '{"any": ["conclusion", "entregable", "resultado", "producto", "final", "resumen", "cierre"]}', "peso": 25, "es_critico": False, "impacto_si_cumple": {"mantenibilidad": 10}, "impacto_si_falta": {}, "retroalimentacion_si_cumple": "Conclusion clara", "retroalimentacion_si_falta": "Falta conclusion"},
            ],
        }
    },
    {
        "materia_malla_id": 33,
        "titulo": "Examen SimutaV2 - Toma de decisiones tecnicas",
        "tema": "Analisis y resolucion de problemas tecnicos",
        "nivel_dificultad": "MEDIA",
        "maximo_decisiones": 3,
        "tiempo_estimado": 25,
        "rol_estudiante": "Analista de Decisiones Tecnicas",
        "contexto": "TechSolve Consulting enfrenta un problema de decision tecnica: migrar su infraestructura a la nube, optimizar procesos actuales o redisenar su arquitectura de software.",
        "objetivo": "Aplicar metodologias de toma de decisiones tecnicas para analizar, evaluar alternativas y proponer una implementacion viable.",
        "resultado_aprendizaje": "El estudiante entrega una decision tecnica profesional con analisis de riesgos, indicadores y acciones verificables.",
        "situacion_inicial": "TechSolve Consulting tiene 50 empleados, opera con servidores locales al 85% de capacidad, su tiempo de respuesta promedio es 4.2s, y reporta 12 incidentes de seguridad al mes. Como analista, identifica el problema principal y las alternativas viables.",
        "instrucciones_ia": "Evalua solo contra la rubrica configurada. No inventes puntos.",
        "nivel_ayuda_ia": "MEDIA",
        "tono_retroalimentacion": "Formativo y claro",
        "indicadores": [
            {"codigo": "calidad_analisis", "nombre": "Calidad del analisis", "valor_inicial": 50, "valor_minimo": 0, "valor_maximo": 100, "direccion_optima": "ALTO", "es_critico": True, "unidad": "pts"},
            {"codigo": "viabilidad", "nombre": "Viabilidad de la propuesta", "valor_inicial": 50, "valor_minimo": 0, "valor_maximo": 100, "direccion_optima": "ALTO", "es_critico": True, "unidad": "pts"},
            {"codigo": "riesgo", "nombre": "Riesgo de la decision", "valor_inicial": 50, "valor_minimo": 0, "valor_maximo": 100, "direccion_optima": "BAJO", "es_critico": True, "unidad": "pts"},
            {"codigo": "claridad", "nombre": "Claridad de justificacion", "valor_inicial": 50, "valor_minimo": 0, "valor_maximo": 100, "direccion_optima": "ALTO", "es_critico": False, "unidad": "pts"},
        ],
        "restricciones": [
            {"descripcion": "El analisis debe ser tecnico y completo", "codigo_indicador": "calidad_analisis", "operador": ">=", "valor_limite": 40, "penalizacion": 15},
            {"descripcion": "La decision debe ser viable", "codigo_indicador": "viabilidad", "operador": ">=", "valor_limite": 40, "penalizacion": 15},
            {"descripcion": "El riesgo no debe superar el limite", "codigo_indicador": "riesgo", "operador": "<=", "valor_limite": 80, "penalizacion": 20},
        ],
        "criterios": [
            {"nombre": "Analisis inicial", "descripcion": "Evaluacion del analisis situacional", "peso": 30, "puntaje_maximo": 100},
            {"nombre": "Decision y alternativas", "descripcion": "Evaluacion de alternativas y decision", "peso": 30, "puntaje_maximo": 100},
            {"nombre": "Implementacion y control", "descripcion": "Plan de implementacion y control", "peso": 25, "puntaje_maximo": 100},
            {"nombre": "Justificacion", "descripcion": "Claridad y solidez de la justificacion", "peso": 15, "puntaje_maximo": 100},
        ],
        "conceptos_por_ronda": {
            1: [
                {"nombre": "Analisis del problema", "descripcion": "Identifica el problema principal", "palabras_clave": '{"any": ["analisis", "causa", "problema", "situacion", "evaluacion", "sintoma"]}', "peso": 35, "es_critico": True, "impacto_si_cumple": {"calidad_analisis": 15, "riesgo": -5}, "impacto_si_falta": {"riesgo": 10}, "retroalimentacion_si_cumple": "Buen analisis", "retroalimentacion_si_falta": "Falta analisis"},
                {"nombre": "Criterios de decision", "descripcion": "Define criterios para evaluar opciones", "palabras_clave": '{"any": ["criterio", "factor", "variable", "ponderar", "priorizar", "evaluar", "comparar"]}', "peso": 25, "es_critico": False, "impacto_si_cumple": {"calidad_analisis": 10, "claridad": 8}, "impacto_si_falta": {}, "retroalimentacion_si_cumple": "Criterios bien definidos", "retroalimentacion_si_falta": "Faltan criterios"},
                {"nombre": "Indicadores tecnicos", "descripcion": "Usa indicadores tecnicos relevantes", "palabras_clave": '{"any": ["indicador", "kpi", "metrica", "dato", "medicion", "porcentaje", "tiempo", "costo"]}', "peso": 20, "es_critico": False, "impacto_si_cumple": {"calidad_analisis": 10, "riesgo": -5}, "impacto_si_falta": {}, "retroalimentacion_si_cumple": "Buenos indicadores", "retroalimentacion_si_falta": "Faltan indicadores"},
            ],
            2: [
                {"nombre": "Alternativas comparadas", "descripcion": "Compara alternativas viables", "palabras_clave": '{"any": ["alternativa", "comparar", "opcion", "ventaja", "desventaja", "versus", "evaluacion"]}', "peso": 30, "es_critico": True, "impacto_si_cumple": {"calidad_analisis": 12, "viabilidad": 10}, "impacto_si_falta": {"riesgo": 12}, "retroalimentacion_si_cumple": "Alternativas bien comparadas", "retroalimentacion_si_falta": "Falta comparacion"},
                {"nombre": "Decision concreta", "descripcion": "Propone una decision clara y concreta", "palabras_clave": '{"any": ["decision", "elegir", "seleccionar", "optar", "adoptar", "implementar", "aplicar"]}', "peso": 35, "es_critico": True, "impacto_si_cumple": {"viabilidad": 15, "claridad": 10}, "impacto_si_falta": {"viabilidad": -10}, "retroalimentacion_si_cumple": "Decision clara", "retroalimentacion_si_falta": "Falta decision concreta"},
            ],
            3: [
                {"nombre": "Plan de accion", "descripcion": "Propone un plan de accion detallado", "palabras_clave": '{"any": ["plan", "accion", "implementacion", "paso", "fase", "cronograma", "recurso"]}', "peso": 35, "es_critico": True, "impacto_si_cumple": {"viabilidad": 12, "riesgo": -8}, "impacto_si_falta": {"riesgo": 10}, "retroalimentacion_si_cumple": "Buen plan de accion", "retroalimentacion_si_falta": "Falta plan de accion"},
                {"nombre": "Control y seguimiento", "descripcion": "Define mecanismos de control", "palabras_clave": '{"any": ["control", "seguimiento", "monitoreo", "evaluar", "medir", "ajustar", "retroalimentacion"]}', "peso": 25, "es_critico": False, "impacto_si_cumple": {"riesgo": -8, "claridad": 10}, "impacto_si_falta": {}, "retroalimentacion_si_cumple": "Buen control", "retroalimentacion_si_falta": "Falta control"},
            ],
        }
    }
]

@transaction.atomic
def crear_simulaciones_faltantes():
    creadas = 0
    for data in simulaciones_faltantes:
        mm_id = data["materia_malla_id"]
        try:
            mm = MateriaMalla.objects.get(id=mm_id)
        except MateriaMalla.DoesNotExist:
            print(f"MateriaMalla #{mm_id} no encontrada")
            continue

        sim = Simulacion.objects.create(
            materia_malla=mm,
            usuario_creacion=admin_user,
            titulo=data["titulo"],
            estado="PUBLICADA",
            tipo_simulacion="CON_IA_DINAMICA",
            tema=data["tema"],
            nivel_dificultad=data["nivel_dificultad"],
            maximo_decisiones=data["maximo_decisiones"],
            tiempo_estimado=data["tiempo_estimado"],
            rol_estudiante=data["rol_estudiante"],
            contexto=data["contexto"],
            objetivo=data["objetivo"],
            resultado_aprendizaje=data["resultado_aprendizaje"],
            situacion_inicial=data["situacion_inicial"],
            instrucciones_ia=data["instrucciones_ia"],
            nivel_ayuda_ia=data["nivel_ayuda_ia"],
            tono_retroalimentacion=data["tono_retroalimentacion"],
        )

        for ind in data["indicadores"]:
            IndicadorSimulacion.objects.create(
                simulacion=sim,
                codigo=ind["codigo"],
                nombre=ind["nombre"],
                valor_inicial=Decimal(str(ind["valor_inicial"])),
                valor_minimo=Decimal(str(ind["valor_minimo"])),
                valor_maximo=Decimal(str(ind["valor_maximo"])),
                direccion_optima=ind["direccion_optima"],
                es_critico=ind["es_critico"],
                unidad=ind["unidad"],
            )

        for r in data["restricciones"]:
            RestriccionSimulacion.objects.create(
                simulacion=sim,
                descripcion=r["descripcion"],
                codigo_indicador=r["codigo_indicador"],
                operador=r["operador"],
                valor_limite=Decimal(str(r["valor_limite"])),
                penalizacion=Decimal(str(r["penalizacion"])),
            )

        for c in data["criterios"]:
            CriterioEvaluacion.objects.create(
                simulacion=sim,
                nombre=c["nombre"],
                descripcion=c["descripcion"],
                peso=Decimal(str(c["peso"])),
                puntaje_maximo=Decimal(str(c["puntaje_maximo"])),
            )

        for ronda_num, conceptos in data["conceptos_por_ronda"].items():
            for c in conceptos:
                ConceptoEsperadoRonda.objects.create(
                    simulacion=sim,
                    numero_ronda=ronda_num,
                    nombre=c["nombre"],
                    descripcion=c["descripcion"],
                    palabras_clave=c["palabras_clave"],
                    peso=Decimal(str(c["peso"])),
                    es_critico=c["es_critico"],
                    impacto_si_cumple=c.get("impacto_si_cumple", {}),
                    impacto_si_falta=c.get("impacto_si_falta", {}),
                    retroalimentacion_si_cumple=c.get("retroalimentacion_si_cumple", ""),
                    retroalimentacion_si_falta=c.get("retroalimentacion_si_falta", ""),
                )

        creadas += 1
        print(f"Creada simulacion #{creadas}: {data['titulo']}")

    print(f"\nTotal creadas: {creadas}")

crear_simulaciones_faltantes()
