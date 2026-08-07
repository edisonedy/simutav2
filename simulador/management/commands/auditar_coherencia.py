"""Revisa que lo que el estudiante LEE coincida con lo que el sistema MIDE.

Un caso puede estar completo y aun asi no ensenar nada: si la alternativa dice
"VAN 92.000" y el indicador van vive en el rango 0-10, el alumno elige bien y el
tablero le dice que no creo valor. Ahi no aprende, se confunde.

    python manage.py auditar_coherencia
    python manage.py auditar_coherencia --malla ADM-UTA-2026 --detalle
    python manage.py auditar_coherencia --simulacion 203 --arreglar
"""
import re

from django.core.management.base import BaseCommand
from django.db import transaction

from simulador.models import Simulacion

GRAVE = 'GRAVE'
AVISO = 'AVISO'


class Command(BaseCommand):
    help = 'Detecta incoherencias entre lo que el caso muestra y lo que el motor mide.'

    def add_arguments(self, parser):
        parser.add_argument('--simulacion', type=int)
        parser.add_argument('--malla', type=str)
        parser.add_argument('--materia', type=str)
        parser.add_argument('--detalle', action='store_true', help='muestra tambien los casos sanos')
        parser.add_argument('--arreglar', action='store_true',
                            help='corrige lo que tiene una unica respuesta correcta')

    def handle(self, *args, **opciones):
        casos = self._seleccionar(opciones)
        totales = {GRAVE: 0, AVISO: 0}
        sanos = arreglados = 0

        for simulacion in casos:
            hallazgos = self.revisar(simulacion)
            if opciones['arreglar']:
                arreglados += self._arreglar(simulacion, hallazgos)
                hallazgos = self.revisar(simulacion)
            if not hallazgos:
                sanos += 1
                if opciones['detalle']:
                    self.stdout.write(self.style.SUCCESS(f'OK  {simulacion.titulo[:56]}'))
                continue
            self.stdout.write(f'\n{simulacion.materia_malla.materia.nombre[:40]} | {simulacion.titulo[:44]}')
            for nivel, mensaje in hallazgos:
                totales[nivel] += 1
                estilo = self.style.ERROR if nivel == GRAVE else self.style.WARNING
                self.stdout.write(estilo(f'   {nivel:5} {mensaje}'))

        self.stdout.write(
            f'\n{len(casos)} casos revisados: {sanos} sin hallazgos, '
            f'{totales[GRAVE]} graves, {totales[AVISO]} avisos.')
        if opciones['arreglar']:
            self.stdout.write(f'Arreglados automaticamente: {arreglados}.')
        elif totales[GRAVE] or totales[AVISO]:
            self.stdout.write('Corre con --arreglar para lo que tiene una unica respuesta correcta.')

    def _seleccionar(self, opciones):
        qs = Simulacion.objects.filter(estado=Simulacion.PUBLICADA, activo=True).select_related(
            'materia_malla__materia')
        if opciones.get('simulacion'):
            qs = qs.filter(pk=opciones['simulacion'])
        if opciones.get('malla'):
            qs = qs.filter(materia_malla__malla__codigo=opciones['malla'])
        if opciones.get('materia'):
            qs = qs.filter(materia_malla__materia__nombre__icontains=opciones['materia'])
        return list(qs)

    # ------------------------------------------------------------------ checks
    def revisar(self, simulacion):
        hallazgos = []
        indicadores = list(simulacion.indicadores.filter(activo=True))
        acciones = list(simulacion.acciones_sugeridas.filter(activo=True))
        alternativas = list(simulacion.opciones_caso.filter(activo=True))
        rondas = (simulacion.parametros or {}).get('rondas') or []

        hallazgos += self._sin_margen_de_mejora(indicadores)
        hallazgos += self._escala_incoherente(alternativas, indicadores)
        hallazgos += self._alternativas_sin_consecuencia(alternativas, acciones)
        hallazgos += self._acciones_sin_ronda(acciones, simulacion)
        hallazgos += self._acciones_que_no_mueven_nada(acciones, indicadores)
        hallazgos += self._sin_decision(alternativas, acciones)
        hallazgos += self._averiguaciones_invisibles(simulacion, rondas)
        hallazgos += self._numeros_fuera_de_escala(simulacion, indicadores)
        return hallazgos

    @staticmethod
    def _numeros_fuera_de_escala(simulacion, indicadores):
        """Un efecto o una meta escritos en otra escala que su indicador. Es el
        error mas silencioso: nadie lo ve hasta que un evento tumba a cero un
        indicador que vivia entre 0 y 1, o una meta se cumple sola.
        """
        rangos = {i.codigo: (float(i.valor_minimo), float(i.valor_maximo)) for i in indicadores}
        salida = []

        for evento in simulacion.eventos.filter(activo=True):
            for codigo, delta in (evento.efecto or {}).items():
                if codigo not in rangos or not isinstance(delta, (int, float)):
                    continue
                minimo, maximo = rangos[codigo]
                amplitud = maximo - minimo
                if amplitud > 0 and abs(delta) > amplitud:
                    salida.append((GRAVE, f'el evento "{evento.nombre[:28]}" mueve "{codigo}" en {delta:g}, '
                                          f'mas que todo su rango ({amplitud:g}): lo lleva al extremo de un golpe'))

        for condicion in simulacion.condiciones_exito.filter(activo=True):
            codigo = condicion.codigo_indicador
            if codigo not in rangos:
                continue
            minimo, maximo = rangos[codigo]
            objetivo = float(condicion.valor_objetivo)
            if objetivo < minimo or objetivo > maximo:
                salida.append((GRAVE, f'la meta de "{codigo}" pide {condicion.operador} {objetivo:g}, fuera de '
                                      f'su rango [{minimo:g}, {maximo:g}]: se cumple sola o es imposible'))
        return salida

    @staticmethod
    def _sin_margen_de_mejora(indicadores):
        salida = []
        for i in indicadores:
            inicial, minimo, maximo = float(i.valor_inicial), float(i.valor_minimo), float(i.valor_maximo)
            if i.direccion_optima == 'ALTO' and inicial >= maximo:
                salida.append((GRAVE, f'"{i.codigo}" arranca en su maximo ({inicial:g}) y lo optimo es ALTO: '
                                      'no hay nada que mejorar, solo se puede empeorar'))
            elif i.direccion_optima == 'BAJO' and inicial <= minimo:
                salida.append((GRAVE, f'"{i.codigo}" arranca en su minimo ({inicial:g}) y lo optimo es BAJO: '
                                      'cualquier decision real lo empeora'))
        return salida

    @staticmethod
    def _escala_incoherente(alternativas, indicadores):
        """La alternativa dice una cifra que no cabe en ningun indicador: el
        alumno lee una escala y el tablero mide otra."""
        if not alternativas or not indicadores:
            return []
        techo = max(abs(float(i.valor_maximo)) for i in indicadores)
        salida = []
        for alt in alternativas:
            texto = f'{alt.valor_referencia} {alt.subtitulo}'
            numeros = [float(n.replace('.', '').replace(',', '.'))
                       for n in re.findall(r'\d[\d.,]{3,}', texto)]
            grandes = [n for n in numeros if n > techo * 10]
            if grandes:
                salida.append((GRAVE, f'"{alt.nombre[:32]}" muestra {grandes[0]:,.0f} pero el indicador mas '
                                      f'grande del caso llega a {techo:g}: el alumno lee una escala y el '
                                      'tablero mide otra'))
        return salida

    @staticmethod
    def _alternativas_sin_consecuencia(alternativas, acciones):
        if not alternativas:
            return []
        vinculadas = {a.opcion_caso_id for a in acciones if a.opcion_caso_id}
        sueltas = [a for a in alternativas if a.id not in vinculadas]
        if len(sueltas) == len(alternativas):
            return [(GRAVE, f'ninguna de las {len(alternativas)} alternativas esta vinculada a una decision: '
                            'el motor no sabe que consecuencia aplicar cuando el alumno elige una')]
        if sueltas:
            return [(AVISO, f'{len(sueltas)} alternativa(s) sin decision vinculada: '
                            + ', '.join(a.nombre[:22] for a in sueltas[:3]))]
        return []

    @staticmethod
    def _acciones_sin_ronda(acciones, simulacion):
        if simulacion.maximo_decisiones <= 1:
            return []
        sueltas = [a for a in acciones if a.numero_ronda is None]
        if sueltas and len(sueltas) == len(acciones):
            return [(AVISO, f'las {len(sueltas)} decisiones valen para todas las rondas: el alumno puede '
                            'repetir la misma en la ronda de diagnostico y en la de plan')]
        return []

    @staticmethod
    def _acciones_que_no_mueven_nada(acciones, indicadores):
        codigos = {i.codigo for i in indicadores}
        mudas = []
        for a in acciones:
            impacto = {k: v for k, v in (a.impacto_base or {}).items()
                       if k in codigos and isinstance(v, (int, float)) and v}
            if not impacto:
                mudas.append(a.texto[:26])
        if mudas:
            return [(AVISO, f'{len(mudas)} decision(es) no mueven ningun indicador: '
                            + ', '.join(mudas[:3]))]
        return []

    @staticmethod
    def _sin_decision(alternativas, acciones):
        if not alternativas and not acciones:
            return [(GRAVE, 'no hay alternativas ni decisiones: el estudiante solo puede redactar, '
                            'no decidir')]
        return []

    @staticmethod
    def _averiguaciones_invisibles(simulacion, rondas):
        if not simulacion.investigaciones.filter(activo=True).exists():
            return []
        visible = any(isinstance(r, dict) and r.get('mostrar_investigaciones') for r in rondas)
        if not visible:
            return [(GRAVE, 'tiene averiguaciones configuradas pero ninguna ronda las muestra: '
                            'el estudiante nunca puede investigar')]
        return []

    @staticmethod
    def _vincular_por_nombre(simulacion):
        """Une la alternativa con la decision que la ejecuta cuando el nombre de
        la alternativa aparece en el texto de la decision. No inventa nada:
        reconoce una correspondencia que ya existe pero no estaba declarada.
        """
        alternativas = list(simulacion.opciones_caso.filter(activo=True))
        if not alternativas:
            return 0
        sueltas = list(simulacion.acciones_sugeridas.filter(activo=True, opcion_caso__isnull=True))
        if not sueltas:
            return 0

        def normalizar(texto):
            return re.sub(r'[^a-z0-9 ]', '', (texto or '').lower())

        vinculadas = 0
        for accion in sueltas:
            texto = normalizar(accion.texto)
            candidatas = []
            for alternativa in alternativas:
                # Se corta ANTES de normalizar: normalizar borra los dos puntos.
                # "Proyecto A: planta propia" -> "proyecto a".
                bruto = alternativa.nombre.split(':')[0] if ':' in alternativa.nombre else alternativa.nombre
                clave = normalizar(bruto).strip()
                if clave and len(clave) >= 4 and clave in texto:
                    candidatas.append((len(clave), alternativa))
            if len(candidatas) != 1:
                # Ambiguo o sin correspondencia: lo decide el docente.
                continue
            accion.opcion_caso = candidatas[0][1]
            accion.save(update_fields=['opcion_caso'])
            vinculadas += 1
        return vinculadas

    # ----------------------------------------------------------------- arreglo
    @transaction.atomic
    def _arreglar(self, simulacion, hallazgos):
        """Solo lo que tiene una unica respuesta correcta. Lo demas lo decide
        el docente: no inventamos contenido."""
        from simulador.management.commands.generar_investigaciones import Command as Generador

        arreglados = 0
        mensajes = ' '.join(m for _, m in hallazgos)

        if 'ninguna ronda las muestra' in mensajes:
            if Generador._mostrar_en_las_rondas(simulacion):
                arreglados += 1

        arreglados += self._vincular_por_nombre(simulacion)

        # Un indicador que arranca en su extremo optimo no deja margen. Se corre
        # el arranque al 20% del rango desde el lado malo, que es lo unico
        # razonable sin inventar el contenido del caso.
        for i in simulacion.indicadores.filter(activo=True):
            inicial, minimo, maximo = float(i.valor_inicial), float(i.valor_minimo), float(i.valor_maximo)
            rango = maximo - minimo
            if rango <= 0:
                continue
            if i.direccion_optima == 'ALTO' and inicial >= maximo:
                i.valor_inicial = round(minimo + rango * 0.2, 2)
            elif i.direccion_optima == 'BAJO' and inicial <= minimo:
                i.valor_inicial = round(maximo - rango * 0.2, 2)
            else:
                continue
            i.save(update_fields=['valor_inicial'])
            arreglados += 1
        return arreglados
