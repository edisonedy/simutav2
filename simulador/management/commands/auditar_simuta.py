import csv
import json
import os
from collections import defaultdict
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Count, Q

from academico.models import Materia, MateriaMalla
from simulador.models import (
    ConceptoEsperadoRonda,
    IndicadorSimulacion,
    RestriccionSimulacion,
    Simulacion,
)


class Command(BaseCommand):
    help = 'Audita todas las simulaciones Simuta y genera reportes JSON/CSV.'

    def add_arguments(self, parser):
        parser.add_argument('--output-dir', type=str, default='',
                            help='Directorio de salida para los reportes (default: BASE_DIR)')

    def handle(self, *args, **options):
        output_dir = options.get('output_dir') or settings.BASE_DIR
        os.makedirs(output_dir, exist_ok=True)

        auditoria = []
        materias_sin_simulacion = []
        simulaciones_con_problemas = []
        resumen_rows = []

        todas_materias_malla = MateriaMalla.objects.filter(activo=True).select_related(
            'materia', 'nivel', 'malla'
        )
        materias_con_simulacion = set(
            Simulacion.objects.filter(activo=True)
            .values_list('materia_malla_id', flat=True)
            .distinct()
        )

        for mm in todas_materias_malla:
            if mm.pk not in materias_con_simulacion:
                materias_sin_simulacion.append({
                    'materia': mm.materia.nombre,
                    'nivel': mm.nivel.numero,
                    'malla': mm.malla.nombre,
                    'codigo_materia': mm.materia.codigo,
                })

        for simulacion in Simulacion.objects.filter(activo=True).select_related(
            'materia_malla__materia', 'materia_malla__nivel'
        ):
            problemas = []
            info = {
                'id': simulacion.pk,
                'titulo': simulacion.titulo,
                'materia': simulacion.materia_malla.materia.nombre,
                'estado': simulacion.estado,
                'dificultad': simulacion.nivel_dificultad,
            }

            # Check indicators
            num_indicadores = simulacion.indicadores.filter(activo=True).count()
            if num_indicadores == 0:
                problemas.append('Sin indicadores')
            elif num_indicadores < 3:
                problemas.append(f'Solo {num_indicadores} indicadores (minimo recomendado: 3)')

            # Check restrictions
            num_restricciones = simulacion.restricciones.filter(activo=True).count()
            if num_restricciones == 0:
                problemas.append('Sin restricciones')

            # Check concepts
            conceptos = ConceptoEsperadoRonda.objects.filter(
                Q(simulacion=simulacion) | Q(escenario__simulacion=simulacion),
                activo=True,
            )
            num_conceptos = conceptos.count()
            if num_conceptos == 0:
                problemas.append('Sin conceptos esperados')

            # Check weight sums per round
            rondas = set(conceptos.filter(numero_ronda__isnull=False).values_list('numero_ronda', flat=True))
            for ronda in sorted(rondas):
                suma = sum(
                    (c.peso for c in conceptos.filter(numero_ronda=ronda)),
                    Decimal('0'),
                )
                if suma != Decimal('100'):
                    problemas.append(f'Ronda {ronda}: pesos suman {suma} (debe ser 100)')

            # Check critical concepts without enough keywords
            for c in conceptos.filter(es_critico=True):
                texto_palabras = (c.palabras_clave or '').strip()
                if len(texto_palabras) < 10:
                    problemas.append(
                        f'Concepto critico "{c.nombre}" (ronda {c.numero_ronda}) '
                        f'tiene pocas palabras clave'
                    )

            # Check context is not too generic
            contexto = (simulacion.contexto or '').lower()
            palabras_genericas = ['empresa', 'gestion', 's.a.s', 's.a', 'ltda']
            if any(p in contexto for p in palabras_genericas):
                problemas.append('Contexto posiblemente generico (contiene empresa generica)')

            # Check if empresa/case is repeated across subjects
            info['problemas'] = problemas
            auditoria.append(info)

            if problemas:
                simulaciones_con_problemas.append(info)
                resumen_rows.append({
                    'titulo': simulacion.titulo,
                    'materia': simulacion.materia_malla.materia.nombre,
                    'estado': simulacion.estado,
                    'dificultad': simulacion.nivel_dificultad,
                    'indicadores': num_indicadores,
                    'restricciones': num_restricciones,
                    'conceptos': num_conceptos,
                    'problemas': '; '.join(problemas),
                })

        # Detect repeated empresas/casos across subjects
        casos_por_empresa = defaultdict(list)
        for s in Simulacion.objects.filter(activo=True).select_related('materia_malla__materia'):
            empresa = (s.parametros or {}).get('empresa', '')
            if empresa:
                casos_por_empresa[empresa].append(s.materia_malla.materia.nombre)
        empresas_repetidas = {k: v for k, v in casos_por_empresa.items() if len(v) > 1}
        if empresas_repetidas:
            auditoria.append({
                'tipo': 'empresas_repetidas',
                'detalle': dict(empresas_repetidas),
            })

        # Write audit JSON
        json_path = os.path.join(output_dir, 'auditoria_simuta.json')
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(auditoria, f, ensure_ascii=False, indent=2, default=str)
        self.stdout.write(self.style.SUCCESS(f'Auditoria JSON: {json_path}'))

        # Write problems CSV
        csv_path = os.path.join(output_dir, 'resumen_auditoria_simuta.csv')
        if resumen_rows:
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=resumen_rows[0].keys())
                writer.writeheader()
                writer.writerows(resumen_rows)
            self.stdout.write(self.style.SUCCESS(f'Resumen CSV: {csv_path}'))

        # Write subjects without simulation
        sin_sim_path = os.path.join(output_dir, 'materias_sin_simulacion.json')
        with open(sin_sim_path, 'w', encoding='utf-8') as f:
            json.dump(materias_sin_simulacion, f, ensure_ascii=False, indent=2)
        self.stdout.write(self.style.SUCCESS(f'Materias sin simulacion: {sin_sim_path}'))

        # Write simulations with problems
        prob_path = os.path.join(output_dir, 'simulaciones_con_problemas.json')
        with open(prob_path, 'w', encoding='utf-8') as f:
            json.dump(simulaciones_con_problemas, f, ensure_ascii=False, indent=2)
        self.stdout.write(self.style.SUCCESS(f'Simulaciones con problemas: {prob_path}'))

        # Summary
        total_materias = todas_materias_malla.count()
        total_simulaciones = Simulacion.objects.filter(activo=True).count()
        self.stdout.write('--- RESUMEN ---')
        self.stdout.write(f'Total materias en mallas: {total_materias}')
        self.stdout.write(f'Total simulaciones activas: {total_simulaciones}')
        self.stdout.write(f'Materias sin simulacion: {len(materias_sin_simulacion)}')
        self.stdout.write(f'Simulaciones con problemas: {len(simulaciones_con_problemas)}')
        self.stdout.write(f'Publicadas con problemas: {sum(1 for s in simulaciones_con_problemas if s.get("estado") == "PUBLICADA")}')
        if empresas_repetidas:
            self.stdout.write(self.style.WARNING(f'Empresas repetidas: {len(empresas_repetidas)}'))
            for emp, mats in empresas_repetidas.items():
                self.stdout.write(f'  {emp}: {", ".join(mats)}')
