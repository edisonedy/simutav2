from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from simulador.models import (
    AccionSugeridaSimulacion,
    CriterioEvaluacion,
    RestriccionSimulacion,
    Simulacion,
)


class Command(BaseCommand):
    help = 'Prepara restricciones, criterios y acciones para el flujo de IA mock por pasos.'

    def handle(self, *args, **options):
        usuario = User.objects.filter(is_superuser=True).first()
        total = 0
        for simulacion in Simulacion.objects.filter(
            estado=Simulacion.PUBLICADA,
            activo=True,
        ).select_related('materia_malla__materia'):
            CriterioEvaluacion.objects.get_or_create(
                simulacion=simulacion,
                nombre='Coherencia de la decision',
                defaults={
                    'descripcion': 'La decision responde al contexto, rol del estudiante y objetivo de aprendizaje.',
                    'peso': 30,
                    'usuario_creacion': usuario,
                },
            )
            CriterioEvaluacion.objects.get_or_create(
                simulacion=simulacion,
                nombre='Uso de indicadores',
                defaults={
                    'descripcion': 'La justificacion considera indicadores actuales, restricciones y consecuencias.',
                    'peso': 40,
                    'usuario_creacion': usuario,
                },
            )
            CriterioEvaluacion.objects.get_or_create(
                simulacion=simulacion,
                nombre='Argumentacion profesional',
                defaults={
                    'descripcion': 'La respuesta explica supuestos, riesgos y razones de la decision.',
                    'peso': 30,
                    'usuario_creacion': usuario,
                },
            )

            RestriccionSimulacion.objects.get_or_create(
                simulacion=simulacion,
                codigo_indicador='caja',
                operador='>=',
                valor_limite=0,
                defaults={
                    'descripcion': 'La caja no puede quedar negativa.',
                    'usuario_creacion': usuario,
                },
            )
            RestriccionSimulacion.objects.get_or_create(
                simulacion=simulacion,
                codigo_indicador='riesgo',
                operador='<=',
                valor_limite=80,
                defaults={
                    'descripcion': 'El riesgo no debe superar el umbral critico.',
                    'usuario_creacion': usuario,
                },
            )

            materia = simulacion.materia_malla.materia.nombre.lower()
            if 'talento humano' in materia or 'comportamiento organizacional' in materia:
                acciones = [
                    ('Definir perfil por competencias', 'Construir matriz de competencias antes de seleccionar.', {'caja': -250, 'riesgo': -8, 'productividad': 5, 'clima_laboral': 6}),
                    ('Aplicar entrevista estructurada', 'Evaluar candidatos con preguntas, evidencias y prueba situacional.', {'caja': -300, 'riesgo': -10, 'productividad': 8, 'clima_laboral': 5}),
                    ('Contratar con plan de induccion', 'Acompanamiento de 90 dias con objetivos y seguimiento.', {'caja': -450, 'riesgo': -6, 'productividad': 10, 'clima_laboral': 8}),
                ]
            else:
                acciones = [
                    ('Analizar datos e indicadores', 'Validar informacion antes de intervenir.', {'caja': -200, 'riesgo': -7, 'productividad': 5}),
                    ('Implementar piloto controlado', 'Probar la solucion con responsables y tablero de seguimiento.', {'caja': -500, 'riesgo': -10, 'productividad': 9, 'clientes': 4}),
                    ('Ajustar plan con evidencia', 'Revisar resultados y corregir decisiones con base en indicadores.', {'riesgo': -5, 'rentabilidad': 5, 'productividad': 4}),
                ]

            for texto, descripcion, impacto in acciones:
                AccionSugeridaSimulacion.objects.get_or_create(
                    simulacion=simulacion,
                    texto=texto,
                    defaults={
                        'descripcion': descripcion,
                        'impacto_base': impacto,
                        'usuario_creacion': usuario,
                    },
                )
            total += 1

        self.stdout.write(self.style.SUCCESS(f'Demo mock preparado para {total} simulaciones publicadas.'))
