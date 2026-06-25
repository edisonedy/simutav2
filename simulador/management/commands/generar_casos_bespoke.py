"""Genera, con IA (DeepSeek/OpenAI), simulaciones BESPOKE para las materias:
cada una recibe sus INDICADORES PROPIOS (no los 5 genericos), un caso real,
conceptos con impactos y decisiones. Pensado para reemplazar las simulaciones
genericas por casos a la medida de cada materia.

Uso:
  python manage.py generar_casos_bespoke --limit 3        # 3 materias genericas
  python manage.py generar_casos_bespoke --materia 45     # una materia_malla puntual
  python manage.py generar_casos_bespoke --limit 5 --reemplazar  # archiva la generica previa
"""
import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from academico.models import MateriaMalla
from simulador.ia_service import generar_caso_ia, orden_proveedores
from simulador.models import (
    AccionSugeridaSimulacion, ConceptoEsperadoRonda, CriterioEvaluacion,
    IndicadorSimulacion, RestriccionSimulacion, Simulacion,
)

User = get_user_model()
GENERICOS = {'calidad_analisis', 'viabilidad', 'riesgo', 'impacto', 'claridad'}


def _dec(valor, defecto='0'):
    try:
        return Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(defecto)


def _materias_genericas():
    """MateriaMalla cuyas simulaciones activas son genericas o no tienen simulacion."""
    objetivo = []
    for mm in MateriaMalla.objects.filter(activo=True).select_related('materia', 'nivel', 'malla'):
        sims = list(Simulacion.objects.filter(materia_malla=mm, activo=True).prefetch_related('indicadores'))
        if not sims:
            objetivo.append(mm)
            continue
        tiene_bespoke = False
        for s in sims:
            cods = set(s.indicadores.values_list('codigo', flat=True))
            if cods and not (cods <= GENERICOS):
                tiene_bespoke = True
                break
        if not tiene_bespoke:
            objetivo.append(mm)
    return objetivo


@transaction.atomic
def _crear_desde_spec(mm, spec, profesor, reemplazar):
    codigos_validos = set()
    sim = Simulacion.objects.create(
        materia_malla=mm, profesor=profesor,
        tipo_simulacion=Simulacion.TIPO_CON_IA_DINAMICA,
        titulo=(spec.get('empresa') and f"{spec.get('tema','Caso')} - {spec['empresa']}")[:300] or f'Caso - {mm.materia.nombre}',
        tema=str(spec.get('tema', ''))[:300],
        nivel_dificultad=Simulacion.DIFICULTAD_MEDIA,
        maximo_decisiones=3, tiempo_estimado=30,
        rol_estudiante=str(spec.get('rol_estudiante', ''))[:200],
        contexto=spec.get('contexto', ''), objetivo=spec.get('objetivo', ''),
        resultado_aprendizaje=spec.get('resultado_aprendizaje', ''),
        situacion_inicial=spec.get('situacion_inicial', ''),
        instrucciones_ia='Evalua solo contra la rubrica configurada. La nota la calcula SimutaV2.',
        parametros={'empresa': spec.get('empresa', ''), 'area': mm.materia.nombre,
                    'rondas': spec.get('rondas', []), 'origen': 'generar_casos_bespoke'},
        estado=Simulacion.PUBLICADA, fecha_publicacion=timezone.now(),
        activo=True, usuario_creacion=profesor,
    )

    for ind in spec.get('indicadores', []) or []:
        codigo = str(ind.get('codigo', '')).strip()
        if not codigo:
            continue
        codigos_validos.add(codigo)
        IndicadorSimulacion.objects.create(
            simulacion=sim, codigo=codigo, nombre=str(ind.get('nombre', codigo))[:150],
            valor_inicial=_dec(ind.get('valor_inicial', 50)), valor_minimo=_dec(ind.get('valor_minimo', 0)),
            valor_maximo=_dec(ind.get('valor_maximo', 100)),
            direccion_optima='BAJO' if str(ind.get('direccion_optima', 'ALTO')).upper() == 'BAJO' else 'ALTO',
            es_critico=bool(ind.get('es_critico', False)), unidad=str(ind.get('unidad', ''))[:50],
            usuario_creacion=profesor,
        )

    for res in spec.get('restricciones', []) or []:
        cod = str(res.get('codigo_indicador', '')).strip()
        op = res.get('operador', '>=')
        if cod not in codigos_validos or op not in ('>', '>=', '<', '<=', '='):
            continue
        RestriccionSimulacion.objects.create(
            simulacion=sim, descripcion=str(res.get('descripcion', ''))[:500], codigo_indicador=cod,
            operador=op, valor_limite=_dec(res.get('valor_limite', 0)),
            penalizacion=min(_dec(res.get('penalizacion', 10)), Decimal('25')), usuario_creacion=profesor,
        )

    def _filtra_impacto(d):
        out = {}
        for k, v in (d or {}).items():
            if str(k) in codigos_validos and isinstance(v, (int, float)):
                out[str(k)] = v
        return out

    for ronda in spec.get('rondas', []) or []:
        try:
            numero = int(ronda.get('numero', 1))
        except (TypeError, ValueError):
            numero = 1
        for c in ronda.get('conceptos', []) or []:
            palabras = c.get('palabras_clave', '')
            if isinstance(palabras, list):
                palabras = ', '.join(str(x) for x in palabras)
            ConceptoEsperadoRonda.objects.create(
                simulacion=sim, numero_ronda=numero, nombre=str(c.get('nombre', 'Concepto'))[:200],
                descripcion=str(c.get('descripcion', ''))[:500],
                palabras_clave=json.dumps({'any': [p.strip() for p in str(palabras).split(',') if p.strip()]}, ensure_ascii=False),
                peso=_dec(c.get('peso', 25)),
                impacto_si_cumple=_filtra_impacto(c.get('impacto_si_cumple')),
                impacto_si_falta=_filtra_impacto(c.get('impacto_si_falta')),
                retroalimentacion_si_cumple=f"Cumple {c.get('nombre','')}.",
                retroalimentacion_si_falta=f"Falta {c.get('nombre','')}.",
                es_critico=bool(c.get('es_critico', False)), usuario_creacion=profesor,
            )

    for a in spec.get('acciones', []) or []:
        AccionSugeridaSimulacion.objects.create(
            simulacion=sim, texto=str(a.get('texto', ''))[:300], descripcion=str(a.get('descripcion', ''))[:500],
            impacto_base=_filtra_impacto(a.get('impacto')), usuario_creacion=profesor,
        )

    for nombre, peso in [('Diagnostico', 30), ('Decision', 30), ('Plan', 25), ('Justificacion', 15)]:
        CriterioEvaluacion.objects.create(
            simulacion=sim, nombre=nombre, descripcion=f'Criterio orientativo: {nombre}.', peso=peso,
            usuario_creacion=profesor)

    if reemplazar:
        Simulacion.objects.filter(materia_malla=mm, activo=True).exclude(pk=sim.pk).update(
            estado=Simulacion.ARCHIVADA, activo=False)

    return sim


class Command(BaseCommand):
    help = 'Genera simulaciones bespoke (indicadores propios) por IA para las materias.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=3, help='Cuantas materias genericas procesar.')
        parser.add_argument('--materia', type=int, default=0, help='ID de MateriaMalla puntual.')
        parser.add_argument('--reemplazar', action='store_true', help='Archiva las simulaciones genericas previas.')

    def handle(self, *args, **options):
        if not orden_proveedores():
            self.stderr.write(self.style.ERROR('No hay proveedor IA con API key (configura OPENAI o DEEPSEEK).'))
            return
        profesor = User.objects.filter(is_staff=True, is_active=True).first() or User.objects.filter(is_active=True).first()

        if options['materia']:
            materias = list(MateriaMalla.objects.filter(pk=options['materia'], activo=True).select_related('materia', 'nivel'))
        else:
            materias = _materias_genericas()[:options['limit']]

        self.stdout.write(f'Materias a procesar: {len(materias)}')
        ok = err = 0
        for mm in materias:
            nivel = mm.nivel.numero if mm.nivel else 1
            self.stdout.write(f'  {mm.materia.nombre}... ', ending='')
            spec = generar_caso_ia(mm.materia.nombre, nivel)
            if not spec:
                err += 1
                self.stdout.write(self.style.ERROR('IA no devolvio caso'))
                continue
            try:
                sim = _crear_desde_spec(mm, spec, profesor, options['reemplazar'])
                inds = list(sim.indicadores.values_list('codigo', flat=True))
                ok += 1
                self.stdout.write(self.style.SUCCESS(f"OK [{spec.get('_proveedor')}] indicadores: {', '.join(inds)}"))
            except Exception as e:
                err += 1
                self.stdout.write(self.style.ERROR(f'error al crear: {e}'))

        self.stdout.write('---')
        self.stdout.write(self.style.SUCCESS(f'Creadas: {ok} | Errores: {err}'))
