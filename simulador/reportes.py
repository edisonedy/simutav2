"""Generacion del reporte de acreditacion (logro de resultados de aprendizaje)
de un curso, en PDF, con reportlab. Pensado para evidencia tipo CACES."""

from io import BytesIO

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from simulador import cursos_service

GUINDA = colors.HexColor('#9e1b34')
GUINDA_OSCURO = colors.HexColor('#6f1124')
GRIS = colors.HexColor('#5d6675')
LINEA = colors.HexColor('#d7dce6')
PAPEL = colors.HexColor('#f6f7fb')


def _estilos():
    base = getSampleStyleSheet()
    return {
        'titulo': ParagraphStyle('t', parent=base['Title'], fontSize=16, textColor=GUINDA_OSCURO, spaceAfter=2),
        'sub': ParagraphStyle('s', parent=base['Normal'], fontSize=9, textColor=GRIS, spaceAfter=1),
        'seccion': ParagraphStyle('h', parent=base['Heading2'], fontSize=11, textColor=GUINDA, spaceBefore=12, spaceAfter=6),
        'celda': ParagraphStyle('c', parent=base['Normal'], fontSize=8.5, leading=11),
        'celda_b': ParagraphStyle('cb', parent=base['Normal'], fontSize=8.5, leading=11, textColor=colors.white),
        'pie': ParagraphStyle('p', parent=base['Normal'], fontSize=7.5, textColor=GRIS, alignment=TA_CENTER),
    }


def _encabezado_tabla(estilos, columnas):
    return [Paragraph(f'<b>{c}</b>', estilos['celda_b']) for c in columnas]


def reporte_acreditacion_pdf(seccion):
    """Devuelve los bytes de un PDF con el logro de RA del curso."""
    est = _estilos()
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=14 * mm,
        title='Reporte de acreditacion',
    )
    analitica = cursos_service.analitica_seccion(seccion)
    resultados = cursos_service.logro_resultados_aprendizaje(seccion)
    materia = seccion.materia_malla.materia
    institucion = getattr(materia, 'institucion', None)
    profesor = seccion.profesor.get_full_name() or seccion.profesor.username

    elementos = []
    elementos.append(Paragraph(institucion.nombre if institucion else 'Institucion', est['titulo']))
    elementos.append(Paragraph('Reporte de logro de resultados de aprendizaje', est['sub']))
    elementos.append(Spacer(1, 6))

    datos_curso = [
        ['Materia', materia.nombre, 'Periodo', str(seccion.periodo)],
        ['Paralelo', seccion.paralelo, 'Profesor', profesor],
        ['Estudiantes', str(analitica['total_estudiantes']), 'Emitido', timezone.now().strftime('%d/%m/%Y %H:%M')],
    ]
    t_curso = Table(datos_curso, colWidths=[28 * mm, 62 * mm, 24 * mm, 60 * mm])
    t_curso.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 8.5),
        ('TEXTCOLOR', (0, 0), (0, -1), GUINDA),
        ('TEXTCOLOR', (2, 0), (2, -1), GUINDA),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 0), (-1, -1), PAPEL),
        ('BOX', (0, 0), (-1, -1), 0.5, LINEA),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, LINEA),
        ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
    ]))
    elementos.append(t_curso)

    # Tabla de resultados de aprendizaje
    elementos.append(Paragraph('Resultados de aprendizaje', est['seccion']))
    filas = [_encabezado_tabla(est, ['RA', 'Descripcion', 'Nivel Bloom', 'Logro', 'Sims'])]
    for r in resultados:
        logro = f"{r['promedio']:.2f} ({r['logro_pct']}%)" if r['logro_pct'] is not None else 'Sin datos'
        filas.append([
            Paragraph(r['ra'].codigo, est['celda']),
            Paragraph(r['ra'].descripcion, est['celda']),
            Paragraph(r['ra'].get_nivel_bloom_display(), est['celda']),
            Paragraph(logro, est['celda']),
            Paragraph(str(r['simulaciones']), est['celda']),
        ])
    if len(filas) == 1:
        filas.append([Paragraph('No hay resultados de aprendizaje registrados.', est['celda']), '', '', '', ''])
    t_ra = Table(filas, colWidths=[16 * mm, 84 * mm, 28 * mm, 30 * mm, 16 * mm], repeatRows=1)
    t_ra.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), GUINDA),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, PAPEL]),
        ('BOX', (0, 0), (-1, -1), 0.5, LINEA),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, LINEA),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
    ]))
    elementos.append(t_ra)

    # Tabla de tareas
    elementos.append(Paragraph('Detalle por tarea', est['seccion']))
    filas_t = [_encabezado_tabla(est, ['Tarea', 'Entrega', 'Aprobacion', 'Promedio'])]
    for r in analitica['asignaciones']:
        titulo = r['asignacion'].titulo or r['asignacion'].simulacion.titulo
        filas_t.append([
            Paragraph(titulo, est['celda']),
            Paragraph(f"{r['entregados']}/{r['total']} ({r['pct_entrega']}%)", est['celda']),
            Paragraph(f"{r['pct_aprobacion']}%", est['celda']),
            Paragraph('-' if r['promedio'] is None else f"{r['promedio']:.2f}", est['celda']),
        ])
    if len(filas_t) == 1:
        filas_t.append([Paragraph('No hay tareas asignadas.', est['celda']), '', '', ''])
    t_tareas = Table(filas_t, colWidths=[86 * mm, 36 * mm, 30 * mm, 22 * mm], repeatRows=1)
    t_tareas.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), GUINDA),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, PAPEL]),
        ('BOX', (0, 0), (-1, -1), 0.5, LINEA),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, LINEA),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
    ]))
    elementos.append(t_tareas)

    promedio = analitica['promedio_curso']
    elementos.append(Spacer(1, 10))
    elementos.append(Paragraph(
        f"<b>Promedio general del curso:</b> {'-' if promedio is None else promedio}", est['sub']))

    elementos.append(Spacer(1, 18))
    elementos.append(Paragraph(
        'Documento generado automaticamente por SimutaV2 - Simulador academico. '
        'El logro de cada RA es el promedio del mejor intento por estudiante en las '
        'simulaciones cuyos conceptos estan mapeados a ese resultado de aprendizaje.',
        est['pie']))

    doc.build(elementos)
    return buffer.getvalue()
