import re
import unicodedata

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from academico.models import Carrera, Malla, Materia, MateriaMalla, NivelMalla
from core.models import Institucion


def generar_codigo(nombre, numero_nivel, orden):
    texto = unicodedata.normalize('NFKD', nombre).encode('ascii', 'ignore').decode('ascii')
    texto = re.sub(r'[^A-Z0-9]+', '_', texto.upper()).strip('_')
    base = texto[:22] or 'MATERIA'
    return f'N{numero_nivel}M{orden}_{base}'[:30]


class Command(BaseCommand):
    help = 'Carga una malla inicial de prueba para Administracion de Empresas UTA'

    def handle(self, *args, **options):
        usuario = User.objects.filter(is_superuser=True).first()

        institucion, _ = Institucion.objects.get_or_create(
            nombre='Universidad Tecnica de Ambato',
            defaults={
                'siglas': 'UTA',
                'direccion': 'Ambato, Ecuador',
                'email': '',
                'usuario_creacion': usuario,
            },
        )

        carrera, _ = Carrera.objects.get_or_create(
            institucion=institucion,
            codigo='ADM-EMP',
            defaults={
                'nombre': 'Administracion de Empresas',
                'titulo_otorga': 'Licenciado/a en Administracion de Empresas',
                'modalidad': 'Presencial',
                'duracion_periodos': 8,
                'usuario_creacion': usuario,
            },
        )

        malla, _ = Malla.objects.get_or_create(
            carrera=carrera,
            codigo='ADM-UTA-2026',
            defaults={
                'nombre': 'Malla Administracion de Empresas UTA 2026',
                'vigente': True,
                'usuario_creacion': usuario,
            },
        )

        datos_malla = {
            1: [
                'Estadistica Descriptiva',
                'Contabilidad de Costos',
                'Procesos Administrativos',
                'Derecho Laboral',
            ],
            2: [
                'Desarrollo y Comportamiento Organizacional',
                'Metodologia de la Investigacion',
                'Derecho Empresarial',
            ],
            3: [
                'Administracion Financiera',
                'Gestion y Administracion del Talento Humano',
                'Tecnologias de la Informacion y la Comunicacion',
            ],
            4: [
                'Gerencia de la Calidad',
                'Administracion de la Produccion',
                'Etica Empresarial y Responsabilidad Social',
                'Nuevas Tendencias en Administracion',
            ],
            5: [
                'Emprendimiento',
                'Investigacion Operativa',
                'Administracion Estrategica',
                'Simulacion de Negocios',
                'Sistemas de Informacion Gerencial',
            ],
            6: [
                'Practicas Laborales',
                'Auditoria Administrativa',
                'Administracion de Operaciones',
                'MIPYMES, Marcas y Patentes',
                'Habilidades Gerenciales',
            ],
            7: [
                'Practicas de Servicio Comunitario',
                'Valoracion de Empresas',
                'Diseno, Desarrollo de Productos y Gestion de Productos y Servicios',
                'Diseno de Proyectos',
                'Comercio Exterior e Integracion',
            ],
            8: [
                'Titulacion',
                'Desarrollo de Proyectos',
            ],
        }

        total_materias = 0
        for numero_nivel, materias in datos_malla.items():
            nivel, _ = NivelMalla.objects.get_or_create(
                malla=malla,
                numero=numero_nivel,
                defaults={
                    'nombre': f'{numero_nivel} Periodo',
                    'usuario_creacion': usuario,
                },
            )

            for orden, nombre_materia in enumerate(materias, start=1):
                codigo = generar_codigo(nombre_materia, numero_nivel, orden)
                materia, _ = Materia.objects.get_or_create(
                    institucion=institucion,
                    codigo=codigo,
                    defaults={
                        'nombre': nombre_materia,
                        'horas': 0,
                        'creditos': 0,
                        'usuario_creacion': usuario,
                    },
                )

                MateriaMalla.objects.get_or_create(
                    malla=malla,
                    nivel=nivel,
                    materia=materia,
                    defaults={
                        'orden': orden,
                        'obligatoria': True,
                        'usuario_creacion': usuario,
                    },
                )
                total_materias += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Malla de Administracion de Empresas UTA cargada correctamente. Materias procesadas: {total_materias}.'
            )
        )
