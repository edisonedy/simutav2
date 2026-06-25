"""Prueba un flujo completo de decisiones + rubrica + IA.

Uso:
  python manage.py probar_flujo_decisiones_ia
  python manage.py probar_flujo_decisiones_ia --camino malo
  python manage.py probar_flujo_decisiones_ia --deepseek
  python manage.py probar_flujo_decisiones_ia --simulacion 147 --camino bueno
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.test import override_settings

from simulador.ia_service import orden_proveedores
from simulador.models import IntentoSimulacion, Simulacion
from simulador.services.core import (
    construir_estado_inicial,
    construir_recursos_iniciales,
    ejecutar_ronda_ia_dinamica,
    situacion_de_ronda,
)

User = get_user_model()


CAMINOS_TALENTO = {
    'bueno': [
        (
            'Aplicar prueba integral',
            'Elijo una prueba integral porque el perfil requiere Django, DRF, ORM, testing y comunicacion. '
            'La rubrica ponderada compara mini feature, code review, pruebas, consultas y entrevista por competencias.',
        ),
        (
            'Contratar a Ana Reyes',
            'Elijo a Ana porque comparo resultados: mini feature 84, code review 82, testing 88, ORM 76 y comunicacion 82. '
            'Aunque Luis domina DRF, su testing 45 y riesgo de rotacion 48 elevan el riesgo. Ana ajusta mejor al perfil.',
        ),
        (
            'Ejecutar onboarding 30-60-90',
            'Propongo onboarding 30-60-90 con mentor, objetivos por semana, feedback, seguimiento de desempeno y plan de carrera '
            'para reducir riesgo de rotacion y acelerar productividad.',
        ),
    ],
    'malo': [
        (
            'Hacer solo entrevista informal',
            'Me parece suficiente porque se conversa rapido.',
        ),
        (
            'Contratar al candidato de menor salario',
            'Porque necesitamos para la siguiente semana y cuesta menos.',
        ),
        (
            'Hacer una induccion de un dia',
            'Arranca rapido y ya aprende solo.',
        ),
    ],
}


class Command(BaseCommand):
    help = 'Ejecuta un intento temporal para verificar decisiones, recursos, indicadores e IA/DeepSeek.'

    def add_arguments(self, parser):
        parser.add_argument('--simulacion', type=int, default=0, help='ID de simulacion. Default: caso Talento Django.')
        parser.add_argument('--camino', choices=['bueno', 'malo'], default='bueno', help='Camino de prueba.')
        parser.add_argument('--deepseek', action='store_true', help='Fuerza DeepSeek como proveedor principal para esta prueba.')

    def handle(self, *args, **options):
        simulacion = self._obtener_simulacion(options['simulacion'])
        usuario = User.objects.filter(is_active=True).first()
        if not usuario:
            raise CommandError('No hay usuario activo para ejecutar la prueba.')

        ctx = override_settings(IA_PROVIDER='deepseek', IA_FALLBACK_PROVIDER='') if options['deepseek'] else _nullcontext()
        with ctx:
            self._imprimir_configuracion(simulacion)
            self.stdout.write('')
            self.stdout.write(self.style.WARNING('Proveedor IA configurado para esta prueba:'))
            self.stdout.write(f"  IA_PROVIDER={getattr(settings, 'IA_PROVIDER', '')}")
            self.stdout.write(f"  IA_FALLBACK_PROVIDER={getattr(settings, 'IA_FALLBACK_PROVIDER', '')}")
            self.stdout.write(f"  orden_proveedores()={orden_proveedores() or 'sin proveedor; usa rubrica local'}")
            self.stdout.write('')

            with transaction.atomic():
                intento = IntentoSimulacion.objects.create(
                    estudiante=usuario,
                    simulacion=simulacion,
                    estado_actual=construir_estado_inicial(simulacion),
                    recursos_actuales=construir_recursos_iniciales(simulacion),
                    situacion_actual=simulacion.situacion_inicial or simulacion.contexto,
                    numero_ronda_actual=1,
                )
                self._ejecutar_camino(intento, options['camino'])
                transaction.set_rollback(True)
                self.stdout.write('')
                self.stdout.write(self.style.WARNING('Prueba temporal revertida: no se guardo el intento.'))

    def _obtener_simulacion(self, simulacion_id):
        if simulacion_id:
            try:
                return Simulacion.objects.get(pk=simulacion_id, activo=True)
            except Simulacion.DoesNotExist:
                raise CommandError(f'Simulacion {simulacion_id} no existe o no esta activa.')
        sim = Simulacion.objects.filter(
            titulo='Contratar 1 de 3 desarrolladores Django en TechAndes',
            activo=True,
        ).first()
        if not sim:
            raise CommandError('No encontre el caso de Talento Django. Ejecuta crear_caso_talento_django.')
        return sim

    def _imprimir_configuracion(self, simulacion):
        self.stdout.write(self.style.SUCCESS(f'Simulacion: {simulacion.titulo}'))
        self.stdout.write(f'Materia: {simulacion.materia_malla.materia.nombre}')
        self.stdout.write('')
        self.stdout.write('Indicadores configurados:')
        for ind in simulacion.indicadores.filter(activo=True).order_by('nombre'):
            direccion = 'alto es mejor' if ind.direccion_optima == ind.DIRECCION_ALTO else 'bajo es mejor'
            self.stdout.write(f'  - {ind.codigo}: {ind.nombre} inicial={ind.valor_inicial} ({direccion})')

        recursos = list(simulacion.recursos.filter(activo=True).order_by('nombre'))
        self.stdout.write('')
        self.stdout.write('Recursos configurados por el docente:')
        if recursos:
            for rec in recursos:
                self.stdout.write(f'  - {rec.codigo}: {rec.nombre} inicial={rec.valor_inicial} {rec.unidad}')
        else:
            self.stdout.write('  - Ninguno. No se mostraran ni afectaran el intento.')

        self.stdout.write('')
        self.stdout.write('Acciones configuradas por ronda:')
        for ronda in range(1, (simulacion.maximo_decisiones or 3) + 1):
            acciones = simulacion.acciones_sugeridas.filter(activo=True, numero_ronda=ronda).order_by('id')
            self.stdout.write(f'  Ronda {ronda}:')
            for accion in acciones:
                self.stdout.write(f'    - {accion.texto}')
                self.stdout.write(f'      impacto={accion.impacto_base or {}} costo_recursos={accion.costo_recursos or {}}')

    def _ejecutar_camino(self, intento, camino):
        pasos = CAMINOS_TALENTO.get(camino) if intento.simulacion.titulo == 'Contratar 1 de 3 desarrolladores Django en TechAndes' else None
        if not pasos:
            pasos = self._camino_generico(intento.simulacion)

        for numero, (texto_accion, justificacion) in enumerate(pasos, start=1):
            intento.refresh_from_db()
            intento.situacion_actual = situacion_de_ronda(intento.simulacion, numero) or intento.situacion_actual
            intento.numero_ronda_actual = numero
            intento.save(update_fields=['situacion_actual', 'numero_ronda_actual'])
            accion = self._buscar_accion(intento.simulacion, numero, texto_accion)
            decision = accion.texto if accion else texto_accion
            paso = ejecutar_ronda_ia_dinamica(intento, decision, justificacion, accion=accion)
            detalle = paso.evaluacion_detalle or {}
            self.stdout.write(self.style.SUCCESS(f'Ronda {numero}: {decision}'))
            self.stdout.write(f'  Justificacion: {justificacion}')
            self.stdout.write(f"  Motor evaluacion: {detalle.get('tipo', 'sin detalle')}")
            if detalle.get('proveedor'):
                self.stdout.write(f"  Proveedor IA: {detalle.get('proveedor')} / {detalle.get('modelo', '')}")
            if detalle.get('error_ia'):
                self.stdout.write(f"  Error IA y fallback local: {detalle.get('error_ia')}")
            self.stdout.write(f'  Puntaje paso: {paso.puntaje_paso} | Penalizacion: {paso.penalizacion_aplicada}')
            self.stdout.write(f'  Impacto real: {paso.impacto_calculado}')
            self.stdout.write(f'  Recursos antes -> despues: {paso.recursos_antes} -> {paso.recursos_despues}')
            self.stdout.write(f'  Estado antes -> despues: {paso.estado_antes} -> {paso.estado_despues}')
            self.stdout.write(f'  Evaluacion: {paso.evaluacion_ia}')
            self.stdout.write('')

    def _buscar_accion(self, simulacion, ronda, texto):
        return simulacion.acciones_sugeridas.filter(
            activo=True,
            numero_ronda=ronda,
            texto__icontains=texto,
        ).first()

    def _camino_generico(self, simulacion):
        pasos = []
        for ronda in range(1, (simulacion.maximo_decisiones or 3) + 1):
            accion = simulacion.acciones_sugeridas.filter(activo=True, numero_ronda=ronda).order_by('id').first()
            if accion:
                pasos.append((accion.texto, 'Justifico la decision con datos, indicadores y restricciones del caso.'))
            else:
                pasos.append(('Analizar indicadores y tomar una decision concreta', 'Justifico con indicadores del caso.'))
        return pasos


class _nullcontext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False
