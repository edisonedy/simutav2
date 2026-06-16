from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone
import json

from academico.models import (
    Carrera,
    InscripcionMalla,
    Malla,
    Materia,
    MateriaMalla,
    NivelMalla,
    PeriodoAcademico,
    ProfesorMateria,
)
from core.models import Institucion, PerfilUsuario
from simulador.models import (
    ConceptoEsperadoRonda,
    CondicionExitoSimulacion,
    IndicadorSimulacion,
    RestriccionSimulacion,
    Simulacion,
)


class Command(BaseCommand):
    help = 'Carga un ejemplo completo para evaluar una respuesta abierta sobre compra de computadora.'

    def handle(self, *args, **options):
        profesor, _ = User.objects.get_or_create(
            username='profesor_demo',
            defaults={
                'first_name': 'Profesor',
                'last_name': 'Demo',
                'email': 'profesor.demo@example.com',
            },
        )
        profesor.set_password('demo12345')
        profesor.save()

        estudiante, _ = User.objects.get_or_create(
            username='estudiante_demo',
            defaults={
                'first_name': 'Estudiante',
                'last_name': 'Demo',
                'email': 'estudiante.demo@example.com',
            },
        )
        estudiante.set_password('demo12345')
        estudiante.save()

        institucion, _ = Institucion.objects.get_or_create(
            nombre='Instituto Demo SimutaV2',
            defaults={
                'siglas': 'IDSM',
                'direccion': 'Ambato',
                'usuario_creacion': profesor,
            },
        )
        PerfilUsuario.objects.update_or_create(
            usuario=profesor,
            defaults={
                'rol': PerfilUsuario.PROFESOR,
                'institucion': institucion,
                'usuario_creacion': profesor,
            },
        )
        PerfilUsuario.objects.update_or_create(
            usuario=estudiante,
            defaults={
                'rol': PerfilUsuario.ESTUDIANTE,
                'institucion': institucion,
                'usuario_creacion': profesor,
            },
        )

        carrera, _ = Carrera.objects.get_or_create(
            institucion=institucion,
            codigo='TI-DEMO',
            defaults={
                'nombre': 'Tecnologia de la Informacion',
                'titulo_otorga': 'Tecnologo/a en TI',
                'modalidad': 'Presencial',
                'duracion_periodos': 4,
                'usuario_creacion': profesor,
            },
        )
        malla, _ = Malla.objects.get_or_create(
            carrera=carrera,
            codigo='TI-COMP-2026',
            defaults={
                'nombre': 'Malla Demo Computadoras 2026',
                'vigente': True,
                'usuario_creacion': profesor,
            },
        )
        nivel, _ = NivelMalla.objects.get_or_create(
            malla=malla,
            numero=1,
            defaults={'nombre': 'Primer periodo', 'usuario_creacion': profesor},
        )
        materia, _ = Materia.objects.get_or_create(
            institucion=institucion,
            codigo='COMP-DEC',
            defaults={
                'nombre': 'Toma de decisiones tecnicas',
                'descripcion': 'Evaluacion de alternativas, requisitos y costos.',
                'creditos': 3,
                'horas': 48,
                'usuario_creacion': profesor,
            },
        )
        materia_malla, _ = MateriaMalla.objects.get_or_create(
            malla=malla,
            materia=materia,
            defaults={
                'nivel': nivel,
                'orden': 1,
                'obligatoria': True,
                'usuario_creacion': profesor,
            },
        )
        periodo, _ = PeriodoAcademico.objects.get_or_create(
            institucion=institucion,
            nombre='Demo Computadoras 2026',
            defaults={
                'fecha_inicio': timezone.datetime(2026, 1, 1).date(),
                'fecha_fin': timezone.datetime(2026, 12, 31).date(),
                'activo_matricula': True,
                'usuario_creacion': profesor,
            },
        )
        ProfesorMateria.objects.get_or_create(
            profesor=profesor,
            materia_malla=materia_malla,
            periodo=periodo,
            defaults={'usuario_creacion': profesor},
        )
        InscripcionMalla.objects.get_or_create(
            estudiante=estudiante,
            malla=malla,
            periodo=periodo,
            defaults={'usuario_creacion': profesor},
        )

        simulacion, _ = Simulacion.objects.update_or_create(
            materia_malla=materia_malla,
            titulo='Elegir una computadora para laboratorio',
            defaults={
                'profesor': profesor,
                'tipo_simulacion': Simulacion.TIPO_CON_IA_DINAMICA,
                'tema': 'Compra tecnica de una computadora',
                'nivel_dificultad': Simulacion.DIFICULTAD_BASICA,
                'maximo_decisiones': 1,
                'tiempo_estimado': 10,
                'rol_estudiante': 'Asistente tecnico de TI',
                'contexto': (
                    'La institucion necesita comprar una computadora para un laboratorio '
                    'donde se usaran navegadores, ofimatica, programacion basica, Visual Studio Code '
                    'y una maquina virtual ligera.'
                ),
                'objetivo': (
                    'Elegir una computadora adecuada justificando requisitos, especificaciones, '
                    'presupuesto y riesgos de compra.'
                ),
                'resultado_aprendizaje': (
                    'El estudiante compara alternativas tecnicas y justifica una decision con criterios medibles.'
                ),
                'situacion_inicial': (
                    'Debes recomendar una computadora para el laboratorio. Explica que especificaciones '
                    'elegirias, por que, como controlas el presupuesto y que riesgos evitas.'
                ),
                'instrucciones_ia': (
                    'Evaluar contra la rubrica configurada. No inventar puntaje fuera de los conceptos esperados.'
                ),
                'estado': Simulacion.PUBLICADA,
                'fecha_publicacion': timezone.now(),
                'usuario_creacion': profesor,
            },
        )

        indicadores = [
            ('rendimiento', 'Rendimiento esperado', 50, 0, 100, 'ALTO', True),
            ('costo', 'Costo total', 50, 0, 100, 'BAJO', True),
            ('mantenibilidad', 'Mantenibilidad', 50, 0, 100, 'ALTO', False),
            ('riesgo_compra', 'Riesgo de mala compra', 50, 0, 100, 'BAJO', True),
        ]
        for codigo, nombre, inicial, minimo, maximo, direccion, critico in indicadores:
            IndicadorSimulacion.objects.update_or_create(
                simulacion=simulacion,
                codigo=codigo,
                defaults={
                    'nombre': nombre,
                    'valor_inicial': inicial,
                    'valor_minimo': minimo,
                    'valor_maximo': maximo,
                    'direccion_optima': direccion,
                    'es_critico': critico,
                    'usuario_creacion': profesor,
                },
            )

        restricciones = [
            ('No elegir una opcion demasiado costosa.', 'costo', '<=', 75, 10),
            ('No dejar rendimiento por debajo de lo aceptable.', 'rendimiento', '>=', 45, 10),
            ('Reducir el riesgo de compra equivocada.', 'riesgo_compra', '<=', 70, 8),
        ]
        for descripcion, indicador, operador, limite, penalizacion in restricciones:
            RestriccionSimulacion.objects.update_or_create(
                simulacion=simulacion,
                descripcion=descripcion,
                defaults={
                    'codigo_indicador': indicador,
                    'operador': operador,
                    'valor_limite': limite,
                    'penalizacion': penalizacion,
                    'usuario_creacion': profesor,
                },
            )

        CondicionExitoSimulacion.objects.update_or_create(
            simulacion=simulacion,
            descripcion='Decision equilibrada con riesgo bajo.',
            codigo_indicador='riesgo_compra',
            defaults={
                'operador': '<=',
                'valor_objetivo': 30,
                'bonificacion': 5,
                'usuario_creacion': profesor,
            },
        )

        conceptos = [
            {
                'nombre': 'Requisitos de uso',
                'descripcion': 'Identifica para que se usara la computadora antes de elegir componentes.',
                'palabras_clave': 'requisitos, uso, laboratorio, programacion, ofimatica, navegador, maquina virtual, visual studio code',
                'peso': 25,
                'impacto': {'riesgo_compra': -10, 'mantenibilidad': 4},
                'cumple': 'Define el uso real antes de comprar.',
                'falta': 'Falta explicar para que se usara la computadora.',
                'critico': True,
            },
            {
                'nombre': 'Especificaciones tecnicas',
                'descripcion': 'Propone una configuracion minima adecuada: i5/Ryzen 5, RAM suficiente y SSD.',
                'palabras_clave': json.dumps({
                    'all': ['ram', 'ssd'],
                    'any': ['i5', 'core i5', 'ryzen 5', 'ryzen5'],
                    'none': ['i3', 'core i3', 'celeron', 'pentium', 'hdd'],
                }),
                'peso': 30,
                'impacto': {'rendimiento': 18, 'riesgo_compra': -8},
                'cumple': 'Propone especificaciones tecnicas verificables.',
                'falta': 'Faltan especificaciones minimas: i5/Ryzen 5, RAM y SSD; o se menciona una opcion no recomendada como i3/Celeron/Pentium/HDD.',
                'critico': True,
            },
            {
                'nombre': 'Presupuesto y costo total',
                'descripcion': 'Considera presupuesto, garantia, mantenimiento o licencias.',
                'palabras_clave': 'presupuesto, costo, garantia, mantenimiento, licencia, precio, costo total',
                'peso': 20,
                'impacto': {'costo': -12, 'mantenibilidad': 6},
                'cumple': 'Controla el costo total de la compra.',
                'falta': 'Falta considerar presupuesto o costos asociados.',
                'critico': False,
            },
            {
                'nombre': 'Justificacion comparativa',
                'descripcion': 'Compara alternativas y justifica por que una es mejor.',
                'palabras_clave': 'comparar, alternativa, compararia, compararía, rendimiento, beneficio, limitacion, limitación',
                'peso': 25,
                'impacto': {'riesgo_compra': -10, 'rendimiento': 6},
                'cumple': 'La decision compara y justifica la alternativa elegida.',
                'falta': 'Falta comparar alternativas o justificar la eleccion.',
                'critico': False,
            },
        ]
        for concepto in conceptos:
            ConceptoEsperadoRonda.objects.update_or_create(
                simulacion=simulacion,
                escenario=None,
                numero_ronda=1,
                nombre=concepto['nombre'],
                defaults={
                    'descripcion': concepto['descripcion'],
                    'palabras_clave': concepto['palabras_clave'],
                    'peso': concepto['peso'],
                    'impacto_si_cumple': concepto['impacto'],
                    'retroalimentacion_si_cumple': concepto['cumple'],
                    'retroalimentacion_si_falta': concepto['falta'],
                    'es_critico': concepto['critico'],
                    'usuario_creacion': profesor,
                },
            )

        self.stdout.write(self.style.SUCCESS('Demo cargada correctamente.'))
        self.stdout.write(f'Profesor: profesor_demo / demo12345')
        self.stdout.write(f'Estudiante: estudiante_demo / demo12345')
        self.stdout.write(f'Simulacion publicada: {simulacion.titulo} (ID {simulacion.id})')
