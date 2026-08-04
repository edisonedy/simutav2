"""Genera las alternativas comparables de un caso: sin ellas no hay decision.

Un caso sin alternativas obliga al estudiante a redactar, no a elegir. Este
comando le pide a la IA las opciones propias de la materia, la matriz de
criterios ponderados, las condiciones de exito y los eventos, y valida en
codigo lo que no se le puede confiar al modelo.

    python manage.py generar_datos_caso --malla ADM-UTA-2026 --limite 10
    python manage.py generar_datos_caso --materia "Emprendimiento" --rehacer
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from simulador.ia_service import generar_datos_caso_ia
from simulador.models import (
    CondicionExitoSimulacion, EventoSimulacion, MatrizEvaluacionCaso,
    OpcionCasoSimulacion, Simulacion,
)

OPERADORES = {'>=', '<=', '>', '<', '==', '=', 'ABS<='}


class Command(BaseCommand):
    help = 'Genera con IA las alternativas, criterios, condiciones de exito y eventos de cada caso.'

    def add_arguments(self, parser):
        parser.add_argument('--simulacion', type=int)
        parser.add_argument('--materia', type=str)
        parser.add_argument('--malla', type=str)
        parser.add_argument('--todas', action='store_true')
        parser.add_argument('--limite', type=int, default=5)
        parser.add_argument('--rehacer', action='store_true')

    def handle(self, *args, **opciones):
        casos = self._seleccionar(opciones)
        if not casos:
            raise CommandError('Ningun caso coincide. Usa --simulacion, --materia, --malla o --todas.')

        hechos = fallidos = 0
        for simulacion in casos:
            resultado = self._generar(simulacion, opciones['rehacer'])
            if resultado is None:
                self.stderr.write(self.style.ERROR(f'x {simulacion.titulo[:50]}: la IA no respondio'))
                fallidos += 1
                continue
            hechos += 1
            n_alt, n_cri, n_exi, n_evt, aviso = resultado
            linea = (f'+ {simulacion.titulo[:50]}: {n_alt} alternativas, {n_cri} criterios, '
                     f'{n_exi} condiciones, {n_evt} eventos')
            self.stdout.write(self.style.SUCCESS(linea))
            if aviso:
                self.stdout.write(self.style.WARNING(f'    aviso: {aviso}'))

        self.stdout.write(f'\nGenerados {hechos}, fallidos {fallidos}.')

    def _seleccionar(self, opciones):
        qs = Simulacion.objects.filter(estado=Simulacion.PUBLICADA, activo=True).select_related(
            'materia_malla__materia')
        if opciones.get('simulacion'):
            return list(qs.filter(pk=opciones['simulacion']))
        if opciones.get('materia'):
            return list(qs.filter(materia_malla__materia__nombre__icontains=opciones['materia']))
        if opciones.get('malla'):
            qs = qs.filter(materia_malla__malla__codigo=opciones['malla'])
        elif not opciones.get('todas'):
            return []
        if not opciones['rehacer']:
            qs = qs.exclude(opciones_caso__activo=True)
        return list(qs.distinct()[:opciones['limite']])

    @transaction.atomic
    def _generar(self, simulacion, rehacer):
        # Una alternativa vinculada ya es la misma entidad que una decisión y
        # su consecuencia. Regenerar solo la tabla rompería esa relación; en
        # ese caso se conserva el conjunto completo y se exige crear una nueva
        # versión del caso para rediseñarlo.
        if rehacer and simulacion.acciones_sugeridas.filter(
            activo=True, opcion_caso__isnull=False,
        ).exists():
            return (
                simulacion.opciones_caso.filter(activo=True).count(),
                simulacion.matriz_caso.filter(activo=True).count(),
                simulacion.condiciones_exito.filter(activo=True).count(),
                simulacion.eventos.filter(activo=True).count(),
                'No se regeneró: las alternativas ya están vinculadas a consecuencias. '
                'Crea una nueva versión para reemplazar todo el conjunto.',
            )
        indicadores = list(simulacion.indicadores.filter(activo=True).values(
            'codigo', 'nombre', 'direccion_optima', 'valor_inicial',
            'valor_minimo', 'valor_maximo', 'unidad',
        ))
        if not indicadores:
            return None
        codigos = {i['codigo'] for i in indicadores}

        data = generar_datos_caso_ia(simulacion, indicadores)
        if not data:
            return None

        criterios = self._criterios(data.get('criterios'))
        if not criterios:
            return None
        alternativas = self._alternativas(data.get('alternativas'), {c[0] for c in criterios})
        if len(alternativas) < 2:
            return None

        OpcionCasoSimulacion.objects.filter(simulacion=simulacion).delete()
        MatrizEvaluacionCaso.objects.filter(simulacion=simulacion).delete()
        if rehacer:
            CondicionExitoSimulacion.objects.filter(simulacion=simulacion).delete()

        for orden, (criterio, peso, evalua) in enumerate(criterios, start=1):
            MatrizEvaluacionCaso.objects.create(
                simulacion=simulacion, criterio=criterio, peso=peso, evalua=evalua, orden=orden)

        for orden, alt in enumerate(alternativas, start=1):
            OpcionCasoSimulacion.objects.create(
                simulacion=simulacion, nombre=alt['nombre'][:200],
                subtitulo=alt['subtitulo'][:300], valor_referencia=alt['valor_referencia'][:100],
                fortaleza=alt['fortaleza'], riesgo=alt['riesgo'],
                resultados=alt['resultados'], orden=orden)

        n_exi = self._condiciones(simulacion, data.get('condiciones_exito'), codigos)
        n_evt = self._eventos(simulacion, data.get('eventos'), codigos)
        return len(alternativas), len(criterios), n_exi, n_evt, self._dominante(alternativas)

    def _criterios(self, crudos):
        """Cuatro criterios con pesos que sumen 100. Si la IA no los normaliza,
        se normalizan aqui: no puede quedar una matriz que sume 87."""
        limpios = []
        for item in (crudos or [])[:5]:
            nombre = str((item or {}).get('criterio') or '').strip()
            try:
                peso = float(item.get('peso') or 0)
            except (TypeError, ValueError):
                continue
            if nombre and peso > 0:
                limpios.append([nombre[:150], peso, str(item.get('evalua') or '').strip()])
        if len(limpios) < 2:
            return []
        total = sum(p for _, p, _ in limpios)
        for fila in limpios:
            fila[1] = round(fila[1] * 100 / total, 2)
        return [tuple(f) for f in limpios]

    def _alternativas(self, crudas, criterios_validos):
        limpias = []
        for item in (crudas or [])[:4]:
            nombre = str((item or {}).get('nombre') or '').strip()
            if not nombre:
                continue
            resultados = []
            for r in (item.get('resultados') or []):
                criterio = str((r or {}).get('criterio') or '').strip()
                try:
                    valor = max(0, min(100, float(r.get('valor'))))
                except (TypeError, ValueError):
                    continue
                if criterio in criterios_validos:
                    resultados.append({'criterio': criterio, 'valor': round(valor)})
            limpias.append({
                'nombre': nombre,
                'subtitulo': str(item.get('subtitulo') or '').strip(),
                'valor_referencia': str(item.get('valor_referencia') or '').strip(),
                'fortaleza': str(item.get('fortaleza') or '').strip(),
                'riesgo': str(item.get('riesgo') or '').strip(),
                'resultados': resultados,
            })
        return limpias

    @staticmethod
    def _dominante(alternativas):
        """Si una alternativa gana en TODOS los criterios, no hay dilema: el
        estudiante solo tiene que leer la tabla. Se avisa para revisarlo."""
        por_criterio = {}
        for alt in alternativas:
            for r in alt['resultados']:
                por_criterio.setdefault(r['criterio'], []).append((r['valor'], alt['nombre']))
        if not por_criterio:
            return 'las alternativas no traen puntajes por criterio'
        ganadores = {max(v)[1] for v in por_criterio.values()}
        if len(ganadores) == 1:
            return f'"{ganadores.pop()}" gana en todos los criterios: revisa que haya dilema real'
        return ''

    def _condiciones(self, simulacion, crudas, codigos):
        creadas = 0
        for item in (crudas or [])[:3]:
            indicador = str((item or {}).get('indicador') or '').strip()
            operador = str(item.get('operador') or '').strip()
            if indicador not in codigos or operador not in OPERADORES:
                continue
            try:
                objetivo = float(item.get('objetivo'))
            except (TypeError, ValueError):
                continue
            CondicionExitoSimulacion.objects.update_or_create(
                simulacion=simulacion, codigo_indicador=indicador, operador=operador,
                defaults={
                    'descripcion': str(item.get('descripcion') or f'Lleva {indicador} a {operador} {objetivo:g}')[:200],
                    'valor_objetivo': objetivo, 'bonificacion': 5, 'activo': True,
                },
            )
            creadas += 1
        return creadas

    def _eventos(self, simulacion, crudos, codigos):
        creados = 0
        for item in (crudos or [])[:3]:
            nombre = str((item or {}).get('nombre') or '').strip()
            mensaje = str(item.get('mensaje') or '').strip()
            efecto = {k: v for k, v in (item.get('efecto') or {}).items()
                      if k in codigos and isinstance(v, (int, float))}
            if not nombre or not mensaje or not efecto:
                continue
            try:
                ronda = max(1, int(item.get('ronda') or 2))
            except (TypeError, ValueError):
                ronda = 2
            EventoSimulacion.objects.update_or_create(
                simulacion=simulacion, nombre=nombre[:200],
                defaults={'mensaje': mensaje, 'ronda': ronda, 'efecto': efecto,
                          'prioridad': 1, 'activo': True},
            )
            creados += 1
        return creados
