from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.utils import timezone
from datetime import date
from types import SimpleNamespace

from academico.models import Carrera, Malla, Materia, MateriaMalla, NivelMalla, PeriodoAcademico, ProfesorMateria
from core.models import Institucion
from simulador.models import (
    AccionSugeridaSimulacion,
    ConceptoEsperadoRonda,
    CondicionExitoSimulacion,
    DecisionConfigurada,
    EscenarioSimulacion,
    EventoSimulacion,
    IndicadorSimulacion,
    IntentoSimulacion,
    OpcionCasoSimulacion,
    PasoSimulacion,
    RecursoSimulacion,
    ResultadoAprendizaje,
    RetoRefuerzo,
    Simulacion,
)
from simulador.generator_service import generar_simulacion_desde_plantilla, serializar_configuracion_simulacion
from simulador.services import (
    TIPO_ERROR_BASURA,
    TIPO_ERROR_GENERICA,
    TIPO_ERROR_OK,
    TIPO_ERROR_VACIA,
    _normalizar_texto,
    aplicar_costo_recursos,
    aplicar_impacto,
    aplicar_eventos,
    calcular_puntaje_final,
    construir_recursos_iniciales,
    cumple_operador,
    desempeno_indicador,
    detectar_accion_sugerida,
    evaluar_pronostico,
    evaluar_tradeoff,
    indicador_mejora,
    evaluar_conceptos_esperados,
    validar_recursos,
    validar_respuesta_estudiante,
    situacion_de_ronda,
)


class SemanticaIndicadoresTests(TestCase):
    def test_indicador_objetivo_premia_acercarse_no_solo_bajar(self):
        indicador = SimpleNamespace(
            valor_minimo=10, valor_maximo=20,
            direccion_optima='OBJETIVO', valor_objetivo=15,
        )
        self.assertEqual(desempeno_indicador(indicador, 15), 100)
        self.assertTrue(indicador_mejora(indicador, 11, 13))
        self.assertFalse(indicador_mejora(indicador, 13, 11))

    def test_operador_absoluto_controla_desviaciones_positivas_y_negativas(self):
        self.assertTrue(cumple_operador('ABS<=', 4500, 5000))
        self.assertTrue(cumple_operador('ABS<=', -4500, 5000))
        self.assertFalse(cumple_operador('ABS<=', -7000, 5000))

    def test_indicador_rango_premia_permanecer_entre_sus_dos_limites(self):
        indicador = SimpleNamespace(
            valor_minimo=0, valor_maximo=100,
            direccion_optima='RANGO', valor_objetivo=None,
            valor_objetivo_min=40, valor_objetivo_max=60,
        )
        self.assertEqual(desempeno_indicador(indicador, 40), 100)
        self.assertEqual(desempeno_indicador(indicador, 50), 100)
        self.assertEqual(desempeno_indicador(indicador, 60), 100)
        self.assertLess(desempeno_indicador(indicador, 20), 100)
        self.assertTrue(indicador_mejora(indicador, 20, 35))
        self.assertTrue(indicador_mejora(indicador, 75, 65))

    def test_meta_configurada_equivale_a_desempeno_aceptable(self):
        from simulador.alu_simulaciones import _desempeno_con_meta
        indicador = SimpleNamespace(
            valor_minimo=0, valor_maximo=100,
            direccion_optima='ALTO', valor_objetivo=None,
        )
        meta = {'operador': '>=', 'valor_objetivo': 40}
        self.assertEqual(_desempeno_con_meta(indicador, 40, meta), 70)
        self.assertGreater(_desempeno_con_meta(indicador, 60, meta), 70)
        self.assertLess(_desempeno_con_meta(indicador, 20, meta), 70)


class EstructuraGenericaPorFasesTests(TestCase):
    def setUp(self):
        self.profesor = User.objects.create_user(username='prof_fases')
        self.estudiante = User.objects.create_user(username='alu_fases')
        institucion = Institucion.objects.create(
            nombre='Institucion fases', usuario_creacion=self.profesor,
        )
        carrera = Carrera.objects.create(
            institucion=institucion, nombre='Carrera fases', usuario_creacion=self.profesor,
        )
        malla = Malla.objects.create(
            carrera=carrera, nombre='Malla fases', usuario_creacion=self.profesor,
        )
        nivel = NivelMalla.objects.create(
            malla=malla, numero=1, nombre='Primero', usuario_creacion=self.profesor,
        )
        materia = Materia.objects.create(
            institucion=institucion, nombre='Materia fases', usuario_creacion=self.profesor,
        )
        mm = MateriaMalla.objects.create(
            malla=malla, materia=materia, nivel=nivel, usuario_creacion=self.profesor,
        )
        self.sim = Simulacion.objects.create(
            materia_malla=mm, profesor=self.profesor, titulo='Caso genérico por fases',
            contexto='Caso con dos resultados medibles.', situacion_inicial='Decide.',
            maximo_decisiones=2,
            parametros={'rondas': [
                {'numero': 1, 'titulo': 'Observar', 'situacion': 'Obtén evidencia.',
                 'indicadores_modificables': ['informacion']},
                {'numero': 2, 'titulo': 'Actuar', 'situacion': 'Elige la intervención.',
                 'indicadores_modificables': ['resultado']},
            ]},
            usuario_creacion=self.profesor,
        )
        self.info = IndicadorSimulacion.objects.create(
            simulacion=self.sim, nombre='Información', codigo='informacion',
            valor_inicial=50, valor_minimo=0, valor_maximo=100,
            peso_salud=0, usuario_creacion=self.profesor,
        )
        self.resultado = IndicadorSimulacion.objects.create(
            simulacion=self.sim, nombre='Resultado', codigo='resultado',
            valor_inicial=20, valor_minimo=0, valor_maximo=100,
            peso_salud=4, usuario_creacion=self.profesor,
        )

    def test_un_evento_no_modifica_un_indicador_congelado_en_la_fase(self):
        EventoSimulacion.objects.create(
            simulacion=self.sim, nombre='Evento mixto', mensaje='Ocurre un cambio.', ronda=1,
            efecto={'informacion': 10, 'resultado': 70}, usuario_creacion=self.profesor,
        )
        estado, _ = aplicar_eventos(
            self.sim, {'informacion': 50, 'resultado': 20}, 1,
            serializar_configuracion_simulacion(self.sim),
        )
        self.assertEqual(estado['informacion'], 60)
        self.assertEqual(estado['resultado'], 20)

    def test_el_texto_de_una_opcion_no_regala_el_concepto(self):
        concepto = ConceptoEsperadoRonda.objects.create(
            simulacion=self.sim, numero_ronda=1, nombre='Análisis técnico',
            palabras_clave='analisis', peso=100, usuario_creacion=self.profesor,
        )
        evaluacion = evaluar_conceptos_esperados(
            self.sim, 1, 'Opción con análisis técnico', 'porque es conveniente', 'Decide',
            evaluaciones_ia=[{
                'concepto_id': concepto.id, 'cumple': True, 'nivel_evidencia': 'completa',
                'evidencia': 'análisis técnico', 'retroalimentacion': '',
                'fuente_evidencia': 'opcion',
            }],
            opcion_predefinida=True,
        )
        self.assertEqual(evaluacion['puntaje_sugerido'], 0)
        self.assertEqual(evaluacion['detalle_conceptos'][0]['fuente_evidencia'], 'opcion')

    def test_la_salud_ignora_indicadores_informativos_con_peso_cero(self):
        from simulador.alu_simulaciones import _salud_indicadores
        intento = IntentoSimulacion.objects.create(
            simulacion=self.sim, estudiante=self.estudiante,
            estado_actual={'informacion': 0, 'resultado': 80},
            configuracion_snapshot=serializar_configuracion_simulacion(self.sim),
        )
        self.assertEqual(_salud_indicadores(intento), 80)

    def test_alertas_ignoran_datos_informativos_y_metas_ya_cumplidas(self):
        from simulador.alu_simulaciones import _explicacion_resultado
        CondicionExitoSimulacion.objects.create(
            simulacion=self.sim, descripcion='Resultado aceptable',
            codigo_indicador='resultado', operador='>=', valor_objetivo=60,
            usuario_creacion=self.profesor,
        )
        intento = IntentoSimulacion.objects.create(
            simulacion=self.sim, estudiante=self.estudiante,
            estado_actual={'informacion': 0, 'resultado': 65},
            configuracion_snapshot=serializar_configuracion_simulacion(self.sim),
            puntuacion_final=70,
        )

        explicacion = _explicacion_resultado(intento)

        self.assertEqual(explicacion['alertas'], [])

    def test_no_se_publica_si_la_tabla_y_las_decisiones_no_son_las_mismas(self):
        from simulador.pro_simulaciones import _errores_publicacion_pedagogica
        opcion_a = OpcionCasoSimulacion.objects.create(
            simulacion=self.sim, nombre='Alternativa A', orden=1,
            usuario_creacion=self.profesor,
        )
        OpcionCasoSimulacion.objects.create(
            simulacion=self.sim, nombre='Alternativa B', orden=2,
            usuario_creacion=self.profesor,
        )
        AccionSugeridaSimulacion.objects.create(
            simulacion=self.sim, numero_ronda=2, opcion_caso=opcion_a,
            texto='Elegir A', impacto_base={'resultado': 10}, usuario_creacion=self.profesor,
        )
        AccionSugeridaSimulacion.objects.create(
            simulacion=self.sim, numero_ronda=2, texto='Elegir una alternativa distinta',
            impacto_base={'resultado': -5}, usuario_creacion=self.profesor,
        )
        parametros = dict(self.sim.parametros)
        parametros['rondas'][1].update({
            'modo': 'elegir', 'proposito': 'Comparar alternativas',
            'alternativas_desde_datos_caso': True,
        })
        parametros['rondas'][0]['proposito'] = 'Obtener evidencia'
        self.sim.parametros = parametros
        self.sim.save(update_fields=['parametros'])
        errores = _errores_publicacion_pedagogica(self.sim)
        self.assertTrue(any('deben vincularse con una alternativa visible' in e for e in errores))
        self.assertTrue(any('exactamente las mismas alternativas' in e for e in errores))

    def test_contradiccion_explicita_no_avanza_ni_aplica_impacto(self):
        from simulador.services.core import ejecutar_ronda_ia_dinamica
        accion = AccionSugeridaSimulacion.objects.create(
            simulacion=self.sim, numero_ronda=1,
            texto='Aceptar la oferta del proveedor',
            impacto_base={'informacion': 30}, usuario_creacion=self.profesor,
        )
        intento = IntentoSimulacion.objects.create(
            simulacion=self.sim, estudiante=self.estudiante,
            estado_actual={'informacion': 50, 'resultado': 20},
            configuracion_snapshot=serializar_configuracion_simulacion(self.sim),
            situacion_actual='Evalúa la oferta del proveedor.', numero_ronda_actual=1,
        )

        paso = ejecutar_ronda_ia_dinamica(
            intento, '',
            'No aceptar la oferta del proveedor; recomiendo negociar otra condición.',
            accion=accion,
        )
        intento.refresh_from_db()

        self.assertFalse(paso.es_valido)
        self.assertEqual(paso.evaluacion_detalle['tipo_error'], 'CONTRADICCION')
        self.assertEqual(paso.impacto_calculado, {})
        self.assertEqual(intento.estado_actual['informacion'], 50)
        self.assertEqual(intento.numero_ronda_actual, 1)

    def test_contradiccion_semantica_detectada_por_ia_conserva_auditoria(self):
        from unittest.mock import patch
        from simulador.services.core import ejecutar_ronda_ia_dinamica
        accion = AccionSugeridaSimulacion.objects.create(
            simulacion=self.sim, numero_ronda=1,
            texto='Aplicar estrategia A', impacto_base={'informacion': 20},
            usuario_creacion=self.profesor,
        )
        intento = IntentoSimulacion.objects.create(
            simulacion=self.sim, estudiante=self.estudiante,
            estado_actual={'informacion': 50, 'resultado': 20},
            configuracion_snapshot=serializar_configuracion_simulacion(self.sim),
            situacion_actual='Elige una estrategia para obtener evidencia.', numero_ronda_actual=1,
        )
        respuesta = {
            'evaluacion': 'La opción y la explicación no coinciden.',
            'evaluacion_detalle': {
                'decision_justificacion_coherentes': False,
                'coherencia_motivo': 'La explicación desarrolla la estrategia B.',
            },
            'respuesta_ia_estructurada': {'decision_justificacion_coherentes': False},
            'modelo_ia': 'modelo-prueba', 'api_ia': 'prueba',
            'prompt_version': 'v-prueba', 'esquema_ia_version': 'e-prueba',
            'tokens_entrada': 10, 'tokens_salida': 5,
            'prompt_ia_enviado': 'PROMPT AUDITABLE',
        }

        with patch('simulador.ia_service.orden_proveedores', return_value=['prueba']), patch(
            'simulador.ia_service.evaluar_ronda_con_proveedores', return_value=respuesta,
        ):
            paso = ejecutar_ronda_ia_dinamica(
                intento, '',
                'La evidencia del caso sustenta una estrategia diferente y medible.',
                accion=accion,
            )

        self.assertFalse(paso.es_valido)
        self.assertEqual(paso.impacto_calculado, {})
        self.assertEqual(paso.modelo_ia, 'modelo-prueba')
        self.assertEqual(paso.prompt_ia_enviado, 'PROMPT AUDITABLE')

    def test_prompt_evalua_todos_los_campos_escritos_por_el_estudiante(self):
        from simulador.ia_service import IAServiceLLM
        servicio = IAServiceLLM()
        prompt = servicio._construir_prompt_semantico(
            self.sim, 'Situación', 'Decisión', 'Justificación', 1, [], [],
            pronostico={'indicador': 'resultado', 'direccion': 'sube'},
            tradeoff_aceptado='Acepto mayor costo inicial.',
        )
        self.assertIn('Pronostico previo', prompt)
        self.assertIn('resultado', prompt)
        self.assertIn('Acepto mayor costo inicial', prompt)
        self.assertIn('pronostico, tradeoff, multiples', prompt)

    def test_prompt_respeta_las_fuentes_de_evidencia_habilitadas(self):
        from simulador.ia_service import IAServiceLLM
        prompt = IAServiceLLM()._construir_prompt_semantico(
            self.sim, 'Situación', 'Decisión', 'Justificación', 1, [], [],
            pronostico={'indicador': 'resultado', 'direccion': 'sube'},
            tradeoff_aceptado='Acepto mayor costo.',
            fuentes_evaluacion=['justificacion'],
        )
        self.assertIn('["justificacion"]', prompt)
        self.assertIn('Solo cuenta evidencia de las fuentes habilitadas', prompt)

    def test_opciones_condicionales_solo_aparecen_tras_la_decision_requerida(self):
        from simulador.alu_simulaciones import _acciones_del_intento
        previa = AccionSugeridaSimulacion.objects.create(
            simulacion=self.sim, numero_ronda=1, texto='Elegir alianza',
            impacto_base={'informacion': 10}, usuario_creacion=self.profesor,
        )
        dependiente = AccionSugeridaSimulacion.objects.create(
            simulacion=self.sim, numero_ronda=2, texto='Ejecutar piloto con socio',
            impacto_base={'resultado': 20}, requiere_accion_previa=previa,
            usuario_creacion=self.profesor,
        )
        intento = IntentoSimulacion.objects.create(
            simulacion=self.sim, estudiante=self.estudiante,
            estado_actual={'informacion': 50, 'resultado': 20},
            configuracion_snapshot=serializar_configuracion_simulacion(self.sim),
            numero_ronda_actual=2,
        )
        self.assertNotIn(dependiente.pk, [a.pk for a in _acciones_del_intento(intento, 2)])
        PasoSimulacion.objects.create(
            intento=intento, numero=1, es_valido=True, tipo_paso='VALIDO',
            situacion_presentada='Elegir entrada', decision_estudiante=previa.texto,
            justificacion_estudiante='Con evidencia.',
            evaluacion_detalle={'seleccion_registrada': {'accion_id': previa.pk}},
        )
        self.assertIn(dependiente.pk, [a.pk for a in _acciones_del_intento(intento, 2)])

    def test_opcion_condicional_forzada_fuera_de_ruta_es_invalida(self):
        from simulador.services.core import ejecutar_ronda_ia_dinamica
        previa = AccionSugeridaSimulacion.objects.create(
            simulacion=self.sim, numero_ronda=1, texto='Elegir adquisición',
            impacto_base={'informacion': 10}, usuario_creacion=self.profesor,
        )
        dependiente = AccionSugeridaSimulacion.objects.create(
            simulacion=self.sim, numero_ronda=2, texto='Integrar empresa adquirida',
            impacto_base={'resultado': 40}, requiere_accion_previa=previa,
            usuario_creacion=self.profesor,
        )
        intento = IntentoSimulacion.objects.create(
            simulacion=self.sim, estudiante=self.estudiante,
            estado_actual={'informacion': 50, 'resultado': 20},
            configuracion_snapshot=serializar_configuracion_simulacion(self.sim),
            situacion_actual='Ejecuta el plan.', numero_ronda_actual=2,
        )

        paso = ejecutar_ronda_ia_dinamica(
            intento, '', 'Aplicaré hitos y responsables para controlar el resultado.',
            accion=dependiente,
        )

        self.assertFalse(paso.es_valido)
        self.assertEqual(paso.evaluacion_detalle['tipo_error'], 'ACCION_NO_DISPONIBLE')
        self.assertEqual(paso.impacto_calculado, {})

    def test_opcion_bloqueada_por_una_decision_previa_no_aparece(self):
        from simulador.alu_simulaciones import _acciones_del_intento
        bloqueante = AccionSugeridaSimulacion.objects.create(
            simulacion=self.sim, numero_ronda=1, texto='Descartar la compra',
            impacto_base={'informacion': 5}, usuario_creacion=self.profesor,
        )
        bloqueada = AccionSugeridaSimulacion.objects.create(
            simulacion=self.sim, numero_ronda=2, texto='Integrar la empresa comprada',
            impacto_base={'resultado': 20}, bloqueada_por_accion_previa=bloqueante,
            usuario_creacion=self.profesor,
        )
        intento = IntentoSimulacion.objects.create(
            simulacion=self.sim, estudiante=self.estudiante,
            estado_actual={'informacion': 50, 'resultado': 20},
            configuracion_snapshot=serializar_configuracion_simulacion(self.sim),
            numero_ronda_actual=2,
        )
        PasoSimulacion.objects.create(
            intento=intento, numero=1, es_valido=True, tipo_paso='VALIDO',
            situacion_presentada='Diagnóstico', decision_estudiante=bloqueante.texto,
            evaluacion_detalle={'seleccion_registrada': {'accion_id': bloqueante.pk}},
        )
        self.assertNotIn(bloqueada.pk, [a.pk for a in _acciones_del_intento(intento, 2)])

    def test_opcion_no_se_repite_mas_del_maximo_configurado(self):
        from simulador.alu_simulaciones import _acciones_del_intento
        accion = AccionSugeridaSimulacion.objects.create(
            simulacion=self.sim, numero_ronda=None, texto='Comprar la empresa',
            impacto_base={'resultado': 20}, maximo_ejecuciones=1,
            usuario_creacion=self.profesor,
        )
        intento = IntentoSimulacion.objects.create(
            simulacion=self.sim, estudiante=self.estudiante,
            estado_actual={'informacion': 50, 'resultado': 20},
            configuracion_snapshot=serializar_configuracion_simulacion(self.sim),
            numero_ronda_actual=2,
        )
        PasoSimulacion.objects.create(
            intento=intento, numero=1, es_valido=True, tipo_paso='VALIDO',
            situacion_presentada='Entrada', decision_estudiante=accion.texto,
            evaluacion_detalle={'seleccion_registrada': {'accion_id': accion.pk}},
        )
        self.assertNotIn(accion.pk, [a.pk for a in _acciones_del_intento(intento, 2)])

    def test_campos_obligatorios_impiden_ejecutar_sin_responderlos(self):
        from simulador.services.core import ejecutar_ronda_ia_dinamica
        parametros = dict(self.sim.parametros)
        parametros['rondas'][0] = {
            **parametros['rondas'][0],
            'pronostico_obligatorio': True,
            'tradeoff_obligatorio': True,
        }
        self.sim.parametros = parametros
        self.sim.save(update_fields=['parametros'])
        intento = IntentoSimulacion.objects.create(
            simulacion=self.sim, estudiante=self.estudiante,
            estado_actual={'informacion': 50, 'resultado': 20},
            configuracion_snapshot=serializar_configuracion_simulacion(self.sim),
            situacion_actual='Decide con anticipación.', numero_ronda_actual=1,
        )
        paso = ejecutar_ronda_ia_dinamica(
            intento, 'Aplicar un piloto', 'La evidencia del caso sustenta el piloto.',
        )
        self.assertFalse(paso.es_valido)
        self.assertEqual(paso.evaluacion_detalle['tipo_error'], 'PRONOSTICO_REQUERIDO')

    def test_publicacion_rechaza_requisito_oculto_y_fuentes_vacias(self):
        from simulador.pro_simulaciones import _errores_publicacion_pedagogica
        parametros = dict(self.sim.parametros)
        parametros['rondas'][0] = {
            **parametros['rondas'][0],
            'proposito': 'Practicar una decisión con evidencia.',
            'pronostico_obligatorio': True,
            'pedir_pronostico': False,
            'fuentes_evaluacion': [],
        }
        parametros['rondas'][1]['proposito'] = 'Aplicar la evidencia reunida.'
        self.sim.parametros = parametros
        self.sim.save(update_fields=['parametros'])
        errores = _errores_publicacion_pedagogica(self.sim)
        self.assertTrue(any('fuente de evidencia' in error for error in errores))
        self.assertTrue(any('pronóstico está oculto' in error for error in errores))


class EvaluacionRubricaTests(TestCase):
    def setUp(self):
        usuario = User.objects.create_user(username='profesor')
        institucion = Institucion.objects.create(nombre='Demo', usuario_creacion=usuario)
        carrera = Carrera.objects.create(
            institucion=institucion,
            nombre='Software',
            codigo='SW',
            usuario_creacion=usuario,
        )
        malla = Malla.objects.create(
            carrera=carrera,
            nombre='Malla',
            codigo='M1',
            usuario_creacion=usuario,
        )
        nivel = NivelMalla.objects.create(
            malla=malla,
            numero=1,
            nombre='Nivel 1',
            usuario_creacion=usuario,
        )
        materia = Materia.objects.create(
            institucion=institucion,
            codigo='DJ',
            nombre='Django',
            usuario_creacion=usuario,
        )
        materia_malla = MateriaMalla.objects.create(
            malla=malla,
            nivel=nivel,
            materia=materia,
            usuario_creacion=usuario,
        )
        self.simulacion = Simulacion.objects.create(
            materia_malla=materia_malla,
            profesor=usuario,
            tipo_simulacion=Simulacion.TIPO_CON_IA_DINAMICA,
            titulo='Inscripciones Django',
            contexto='Evitar duplicados y sobrecupos.',
            objetivo='Evaluar una solucion backend.',
            resultado_aprendizaje='Aplica restricciones y transacciones.',
            situacion_inicial='Proponga una solucion.',
            instrucciones_ia='Evaluar con rubrica.',
            maximo_decisiones=1,
            usuario_creacion=usuario,
        )
        for codigo in ['seguridad', 'calidad_codigo', 'riesgo_errores']:
            IndicadorSimulacion.objects.create(
                simulacion=self.simulacion,
                codigo=codigo,
                nombre=codigo,
                valor_inicial=50,
                valor_minimo=0,
                valor_maximo=100,
                usuario_creacion=usuario,
            )
        ConceptoEsperadoRonda.objects.create(
            simulacion=self.simulacion,
            numero_ronda=1,
            nombre='Evitar duplicados',
            palabras_clave='unique, unique_together, uniqueconstraint, duplicado',
            peso=40,
            impacto_si_cumple={'seguridad': 10},
            retroalimentacion_si_cumple='Evita duplicados.',
            retroalimentacion_si_falta='Falta evitar duplicados.',
            usuario_creacion=usuario,
        )
        ConceptoEsperadoRonda.objects.create(
            simulacion=self.simulacion,
            numero_ronda=1,
            nombre='Concurrencia',
            palabras_clave='transaction.atomic, select_for_update, concurrencia',
            peso=60,
            impacto_si_cumple={'riesgo_errores': -20},
            retroalimentacion_si_cumple='Controla concurrencia.',
            retroalimentacion_si_falta='Falta controlar concurrencia.',
            es_critico=True,
            usuario_creacion=usuario,
        )

    def test_evalua_respuesta_abierta_con_rubrica_y_detalle(self):
        resultado = evaluar_conceptos_esperados(
            self.simulacion,
            1,
            'Usaria UniqueConstraint y transaction.atomic con select_for_update.',
            'Esto mantiene la integridad porque evita duplicados y controla concurrencia.',
            'Proponga una solucion.',
        )

        # With partial scoring, the response gets credit for matched keywords
        # Concept "Evitar duplicados" (40pts): detects "unique"(substring), "uniqueconstraint", "duplicado"(substring) = 3/4 → 30pts
        # Concept "Concurrencia" (60pts): detects all 3 → 60pts
        # Total: 90 (not 100 because "unique_together" is missing)
        self.assertEqual(resultado['puntaje_sugerido'], 90)
        self.assertIn('Evitar duplicados', resultado['conceptos_cumplidos'])
        self.assertIn('Concurrencia', resultado['conceptos_cumplidos'])
        self.assertEqual(resultado['conceptos_faltantes'], [])
        self.assertEqual(resultado['impacto_sugerido'], {'seguridad': 7.5, 'riesgo_errores': -20.0})

        # Verify partial evidence is captured in detail
        detalle_dd = [d for d in resultado['detalle_conceptos'] if d['nombre'] == 'Evitar duplicados'][0]
        self.assertTrue(detalle_dd['cumple'])
        self.assertEqual(detalle_dd['puntos_obtenidos'], 30)
        self.assertGreater(detalle_dd['factor_coincidencia'], 0)
        self.assertLess(detalle_dd['factor_coincidencia'], 1)

    def test_no_otorga_puntos_por_conceptos_no_detectados(self):
        resultado = evaluar_conceptos_esperados(
            self.simulacion,
            1,
            'Haria una validacion normal en el formulario.',
            'Porque ayuda a controlar los datos ingresados.',
            'Proponga una solucion.',
        )

        self.assertEqual(resultado['puntaje_sugerido'], 0)
        self.assertEqual(resultado['conceptos_cumplidos'], [])
        self.assertCountEqual(resultado['conceptos_faltantes'], ['Evitar duplicados', 'Concurrencia'])

    def test_ia_clasifica_evidencia_y_el_motor_calcula_los_puntos(self):
        conceptos = list(self.simulacion.conceptos_esperados.order_by('peso'))
        evaluaciones_ia = [
            {
                'concepto_id': conceptos[0].id,
                'cumple': True,
                'nivel_evidencia': 'completa',
                'evidencia': 'UniqueConstraint',
                'retroalimentacion': '',
            },
            {
                'concepto_id': conceptos[1].id,
                'cumple': False,
                'nivel_evidencia': 'parcial',
                'evidencia': 'Menciona transacciones sin explicar concurrencia',
                'retroalimentacion': '',
            },
        ]

        resultado = evaluar_conceptos_esperados(
            self.simulacion, 1, 'Decision concreta', 'Justificacion tecnica',
            'Proponga una solucion.', evaluaciones_ia=evaluaciones_ia,
        )

        # Los pesos docentes (40 y 60) convierten completa/parcial en 40 + 30.
        self.assertEqual(resultado['puntaje_sugerido'], 70)
        self.assertEqual(resultado['puntaje_conceptos'], 70)

    def test_genera_simulacion_desde_plantilla_global(self):
        simulacion = generar_simulacion_desde_plantilla(
            self.simulacion.materia_malla,
            self.simulacion.profesor,
        )

        self.assertEqual(simulacion.tipo_simulacion, Simulacion.TIPO_CON_IA_DINAMICA)
        self.assertIsNotNone(simulacion.plantilla_origen)
        self.assertIsNotNone(simulacion.perfil_materia_ia)
        self.assertEqual(simulacion.indicadores.filter(activo=True).count(), 5)
        self.assertEqual(simulacion.restricciones.filter(activo=True).count(), 4)
        self.assertEqual(simulacion.conceptos_esperados.filter(activo=True).count(), 12)
        self.assertEqual(simulacion.acciones_sugeridas.filter(activo=True).count(), 9)
        self.assertEqual(simulacion.acciones_sugeridas.filter(activo=True, numero_ronda=1).count(), 3)
        self.assertEqual((simulacion.parametros or {}).get('modo'), 'toma_decisiones')
        self.assertTrue(simulacion.configuracion_snapshot)


class ValidacionIntentoTests(TestCase):
    """Regla corregida: solo vacio/basura/fuera-de-tema invalidan la ronda.
    Una respuesta basica pero relacionada es valida con nota baja."""

    def test_decision_vacia_es_invalida(self):
        r = validar_respuesta_estudiante('', 'cualquier justificacion larga aqui')
        self.assertFalse(r['valida'])
        self.assertEqual(r['tipo_error'], TIPO_ERROR_VACIA)

    def test_texto_basura_es_invalido(self):
        r = validar_respuesta_estudiante('asdf', 'qwerty')
        self.assertFalse(r['valida'])
        self.assertEqual(r['tipo_error'], TIPO_ERROR_BASURA)

    def test_respuesta_basica_relacionada_es_valida_con_nota_baja(self):
        # Antes esto se marcaba INVALIDO (35/100). Ahora avanza como ronda valida.
        r = validar_respuesta_estudiante(
            'Diagnosticar el problema de liquidez revisando el flujo de caja de la empresa',
            'me parece',
        )
        self.assertTrue(r['valida'])
        self.assertEqual(r['tipo_error'], TIPO_ERROR_GENERICA)
        self.assertLessEqual(r['puntaje_maximo'], 60)

    def test_respuesta_completa_es_valida_sin_tope(self):
        r = validar_respuesta_estudiante(
            'Implementar un control de inventario con indicadores de rotacion',
            'Porque permite reducir el inventario lento y mejorar el flujo de caja de forma sostenida.',
        )
        self.assertTrue(r['valida'])
        self.assertEqual(r['tipo_error'], TIPO_ERROR_OK)
        self.assertEqual(r['puntaje_maximo'], 100)

    def test_justificacion_obligatoria_no_permite_avanzar_vacia_o_breve(self):
        decision = 'Revisar la tasa CIF con los datos reales de horas maquina'
        vacia = validar_respuesta_estudiante(
            decision, '', requerir_justificacion=True,
        )
        breve = validar_respuesta_estudiante(
            decision, 'Porque mejora el costo.', requerir_justificacion=True,
        )
        completa = validar_respuesta_estudiante(
            decision,
            'Con los CIF reales y las horas máquina calcularé la variación, mediré la tasa aplicada y corregiré el ajuste sin ocultar el riesgo operativo.',
            requerir_justificacion=True,
        )
        self.assertFalse(vacia['valida'])
        self.assertTrue(breve['valida'])
        self.assertLess(breve['puntaje_maximo'], 100)
        self.assertTrue(completa['valida'])


class CalculoNotaFinalTests(TestCase):
    def setUp(self):
        usuario = User.objects.create_user(username='prof2')
        institucion = Institucion.objects.create(nombre='Demo', usuario_creacion=usuario)
        carrera = Carrera.objects.create(
            institucion=institucion, nombre='Software', codigo='SW2', usuario_creacion=usuario)
        malla = Malla.objects.create(
            carrera=carrera, nombre='Malla', codigo='M2', usuario_creacion=usuario)
        nivel = NivelMalla.objects.create(
            malla=malla, numero=1, nombre='Nivel 1', usuario_creacion=usuario)
        materia = Materia.objects.create(
            institucion=institucion, codigo='FIN', nombre='Finanzas', usuario_creacion=usuario)
        materia_malla = MateriaMalla.objects.create(
            malla=malla, nivel=nivel, materia=materia, usuario_creacion=usuario)
        self.simulacion = Simulacion.objects.create(
            materia_malla=materia_malla, profesor=usuario,
            tipo_simulacion=Simulacion.TIPO_CON_IA_DINAMICA,
            titulo='Caso financiero', maximo_decisiones=3, usuario_creacion=usuario)
        self.estudiante = User.objects.create_user(username='alumno1')
        self.intento = IntentoSimulacion.objects.create(
            estudiante=self.estudiante, simulacion=self.simulacion, usuario_creacion=usuario)

    def _crear_paso(self, numero, puntaje, es_valido=True):
        return self.intento.pasos.create(
            numero=numero, es_valido=es_valido,
            tipo_paso='VALIDO' if es_valido else 'INVALIDO',
            situacion_presentada='s', decision_estudiante='d', justificacion_estudiante='j',
            puntaje_paso=puntaje)

    def test_nota_final_es_promedio_de_pasos(self):
        # 100, 100, 75 -> 91.67 (no 100). Los indicadores no inflan la nota.
        self._crear_paso(1, 100)
        self._crear_paso(2, 100)
        self._crear_paso(3, 75)
        self.assertEqual(calcular_puntaje_final(self.intento), 91.67)

    def test_pasos_invalidos_no_cuentan(self):
        self._crear_paso(1, 80)
        self._crear_paso(2, 60)
        self._crear_paso(3, 0, es_valido=False)
        self.assertEqual(calcular_puntaje_final(self.intento), 70.0)

    def test_sin_pasos_validos_es_cero(self):
        self._crear_paso(1, 0, es_valido=False)
        self.assertEqual(calcular_puntaje_final(self.intento), 0.0)


class NormalizacionTextoTests(TestCase):
    def test_quita_tildes_y_minusculas(self):
        self.assertEqual(_normalizar_texto('Gestión Análisis'), 'gestion analisis')

    def test_colapsa_espacios_y_simbolos(self):
        self.assertEqual(_normalizar_texto('  control,  de   riesgo! '), 'control de riesgo')


class PermisosPanelProfesorTests(TestCase):
    def setUp(self):
        self.profesor1 = User.objects.create_user(username='profesor_panel_1', is_staff=True)
        self.profesor2 = User.objects.create_user(username='profesor_panel_2', is_staff=True)
        self.estudiante = User.objects.create_user(username='estudiante_panel')
        institucion = Institucion.objects.create(nombre='Institucion panel', usuario_creacion=self.profesor1)
        carrera = Carrera.objects.create(
            institucion=institucion, nombre='Carrera panel', codigo='CP', usuario_creacion=self.profesor1)
        malla = Malla.objects.create(
            carrera=carrera, nombre='Malla panel', codigo='MP', usuario_creacion=self.profesor1)
        nivel = NivelMalla.objects.create(
            malla=malla, numero=1, nombre='Nivel 1', usuario_creacion=self.profesor1)
        periodo = PeriodoAcademico.objects.create(
            institucion=institucion,
            nombre='Periodo panel',
            fecha_inicio=date(2026, 1, 1),
            fecha_fin=date(2026, 6, 30),
            usuario_creacion=self.profesor1,
        )
        materia1 = Materia.objects.create(
            institucion=institucion, codigo='P1', nombre='Materia 1', usuario_creacion=self.profesor1)
        materia2 = Materia.objects.create(
            institucion=institucion, codigo='P2', nombre='Materia 2', usuario_creacion=self.profesor1)
        self.mm1 = MateriaMalla.objects.create(
            malla=malla, nivel=nivel, materia=materia1, usuario_creacion=self.profesor1)
        self.mm2 = MateriaMalla.objects.create(
            malla=malla, nivel=nivel, materia=materia2, usuario_creacion=self.profesor1)
        ProfesorMateria.objects.create(
            profesor=self.profesor1, materia_malla=self.mm1, periodo=periodo, usuario_creacion=self.profesor1)
        ProfesorMateria.objects.create(
            profesor=self.profesor2, materia_malla=self.mm2, periodo=periodo, usuario_creacion=self.profesor1)
        self.sim1 = self._crear_simulacion(self.mm1, self.profesor1, 'Sim profesor 1')
        self.sim2 = self._crear_simulacion(self.mm2, self.profesor2, 'Sim profesor 2')

    def _crear_simulacion(self, materia_malla, profesor, titulo):
        return Simulacion.objects.create(
            materia_malla=materia_malla,
            profesor=profesor,
            tipo_simulacion=Simulacion.TIPO_CON_IA_DINAMICA,
            titulo=titulo,
            contexto='Contexto',
            objetivo='Objetivo',
            resultado_aprendizaje='Resultado',
            situacion_inicial='Situacion inicial',
            instrucciones_ia='Evaluar',
            usuario_creacion=profesor,
        )

    def test_profesor_solo_accede_a_simulaciones_de_su_materia(self):
        client = Client()
        client.force_login(self.profesor1)

        propia = client.get(f'/simulador/pro_simulaciones?action=configuracion&id={self.sim1.pk}')
        ajena = client.get(f'/simulador/pro_simulaciones?action=configuracion&id={self.sim2.pk}')

        self.assertEqual(propia.status_code, 200)
        self.assertEqual(ajena.status_code, 404)

    def test_estudiante_no_accede_al_panel_profesor(self):
        client = Client()
        client.force_login(self.estudiante)

        response = client.get(f'/simulador/pro_simulaciones?action=configuracion&id={self.sim1.pk}')

        self.assertEqual(response.status_code, 302)

    def test_listado_muestra_auditoria_calidad(self):
        client = Client()
        client.force_login(self.profesor1)

        response = client.get('/simulador/pro_simulaciones')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Calidad')
        self.assertContains(response, 'Sim profesor 1')
        self.assertNotContains(response, 'Sim profesor 2')

    def test_nueva_version_copia_configuracion_y_no_toca_publicada(self):
        self.sim1.estado = Simulacion.PUBLICADA
        self.sim1.configuracion_bloqueada = True
        self.sim1.save(update_fields=['estado', 'configuracion_bloqueada'])
        IndicadorSimulacion.objects.create(
            simulacion=self.sim1, codigo='costo', nombre='Costo',
            valor_inicial=50, valor_minimo=0, valor_maximo=100,
        )
        client = Client()
        client.force_login(self.profesor1)

        response = client.post('/simulador/pro_simulaciones', {
            'action': 'nueva_version', 'pk': self.sim1.pk,
        })

        self.assertEqual(response.status_code, 200)
        nueva = Simulacion.objects.exclude(pk=self.sim1.pk).get(titulo__contains='· v2')
        self.assertEqual(nueva.estado, Simulacion.BORRADOR)
        self.assertFalse(nueva.configuracion_bloqueada)
        self.assertTrue(nueva.indicadores.filter(codigo='costo').exists())
        self.sim1.refresh_from_db()
        self.assertEqual(self.sim1.estado, Simulacion.PUBLICADA)

    def test_export_auditoria_calidad_csv_respeta_permisos(self):
        client = Client()
        client.force_login(self.profesor1)

        response = client.get('/simulador/pro_simulaciones?action=auditoria_export')
        body = response.content.decode('utf-8-sig')

        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response['Content-Type'])
        self.assertIn('simulacion,materia,estado,tipo,nivel_calidad,puntaje', body)
        self.assertIn('Sim profesor 1', body)
        self.assertNotIn('Sim profesor 2', body)

    def test_analitica_muestra_metacognicion_y_refuerzo(self):
        self._crear_intento_con_evidencia_metacognitiva()
        client = Client()
        client.force_login(self.profesor1)

        response = client.get(f'/simulador/pro_simulaciones?action=analitica&id={self.sim1.pk}')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Reflexion')
        self.assertContains(response, '50,0%')
        self.assertContains(response, 'Estudiantes que requieren refuerzo')
        self.assertContains(response, 'estudiante_panel')
        self.assertContains(response, 'Pronosticos fallidos')

    def test_export_analitica_csv_incluye_metacognicion(self):
        self._crear_intento_con_evidencia_metacognitiva()
        client = Client()
        client.force_login(self.profesor1)

        response = client.get(f'/simulador/pro_simulaciones?action=analitica_export&id={self.sim1.pk}')
        body = response.content.decode('utf-8-sig')

        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response['Content-Type'])
        self.assertIn('estudiante,intento_id,finalizado,nota,pasos_validos,reflexiones', body)
        self.assertIn('estudiante_panel', body)
        self.assertIn('65.00,2,1,2,1,1,1,1,1,0,si', body)

    def _crear_intento_con_evidencia_metacognitiva(self):
        intento = IntentoSimulacion.objects.create(
            estudiante=self.estudiante,
            simulacion=self.sim1,
            finalizado=True,
            puntuacion_final=65,
            usuario_creacion=self.estudiante,
        )
        PasoSimulacion.objects.create(
            intento=intento,
            numero=1,
            es_valido=True,
            situacion_presentada='Situacion',
            decision_estudiante='Decision',
            justificacion_estudiante='Justificacion',
            reflexion='Explique la causa con evidencia.',
            pronostico_indicador='calidad',
            pronostico_resultado={'estado': 'acierto'},
            tradeoff_aceptado='Acepto gastar presupuesto.',
            tradeoff_resultado={'estado': 'tradeoff_real'},
            puntaje_paso=80,
            usuario_creacion=self.estudiante,
        )
        PasoSimulacion.objects.create(
            intento=intento,
            numero=2,
            es_valido=True,
            situacion_presentada='Situacion',
            decision_estudiante='Decision',
            justificacion_estudiante='Justificacion',
            pronostico_indicador='costo',
            pronostico_resultado={'estado': 'diferencia'},
            puntaje_paso=50,
            usuario_creacion=self.estudiante,
        )
        RetoRefuerzo.objects.create(
            estudiante=self.estudiante,
            simulacion=self.sim1,
            intento_origen=intento,
            concepto='Analisis de indicadores',
            pregunta='Explica que indicador revisarias primero.',
            fecha_disponible=timezone.now(),
            usuario_creacion=self.estudiante,
        )
        return intento


class EventosDinamicosTests(TestCase):
    def setUp(self):
        self.profesor = User.objects.create_user(username='prof_eventos', is_staff=True)
        institucion = Institucion.objects.create(nombre='Eventos Demo', usuario_creacion=self.profesor)
        carrera = Carrera.objects.create(
            institucion=institucion,
            nombre='TI',
            codigo='TI-EVT',
            usuario_creacion=self.profesor,
        )
        malla = Malla.objects.create(
            carrera=carrera,
            nombre='Malla eventos',
            codigo='EVT',
            usuario_creacion=self.profesor,
        )
        nivel = NivelMalla.objects.create(
            malla=malla,
            numero=1,
            nombre='Nivel 1',
            usuario_creacion=self.profesor,
        )
        materia = Materia.objects.create(
            institucion=institucion,
            codigo='RED-EVT',
            nombre='Redes',
            usuario_creacion=self.profesor,
        )
        materia_malla = MateriaMalla.objects.create(
            malla=malla,
            nivel=nivel,
            materia=materia,
            usuario_creacion=self.profesor,
        )
        self.simulacion = Simulacion.objects.create(
            materia_malla=materia_malla,
            profesor=self.profesor,
            tipo_simulacion=Simulacion.TIPO_CON_IA_DINAMICA,
            titulo='Eventos de red',
            maximo_decisiones=3,
            usuario_creacion=self.profesor,
        )
        IndicadorSimulacion.objects.create(
            simulacion=self.simulacion,
            codigo='saturacion_wan',
            nombre='Saturacion WAN',
            valor_inicial=70,
            valor_minimo=0,
            valor_maximo=100,
            direccion_optima=IndicadorSimulacion.DIRECCION_BAJO,
            usuario_creacion=self.profesor,
        )
        self.evento = EventoSimulacion.objects.create(
            simulacion=self.simulacion,
            nombre='Trafico inesperado',
            mensaje='La campana eleva el trafico WAN.',
            ronda=2,
            codigo_indicador_condicion='saturacion_wan',
            operador_condicion='>=',
            valor_condicion=60,
            efecto={'saturacion_wan': 10},
            usuario_creacion=self.profesor,
        )

    def test_evento_db_se_dispara_por_ronda_y_condicion(self):
        estado, mensajes = aplicar_eventos(self.simulacion, {'saturacion_wan': 70}, 2)

        self.assertEqual(estado['saturacion_wan'], 80)
        self.assertEqual(mensajes, ['La campana eleva el trafico WAN.'])
        self.assertIn(f'db:{self.evento.pk}', estado['__eventos__'])

    def test_evento_db_no_se_repite(self):
        estado, _ = aplicar_eventos(self.simulacion, {'saturacion_wan': 70}, 2)
        estado_repetido, mensajes = aplicar_eventos(self.simulacion, estado, 2)

        self.assertEqual(estado_repetido['saturacion_wan'], 80)
        self.assertEqual(mensajes, [])

    def test_evento_json_heredado_no_duplica_si_hay_evento_db(self):
        self.simulacion.parametros = {
            'eventos': [
                {
                    'id': 'legacy',
                    'ronda': 2,
                    'mensaje': 'Evento heredado',
                    'efecto': {'saturacion_wan': 10},
                },
            ],
        }
        self.simulacion.save(update_fields=['parametros'])

        estado, mensajes = aplicar_eventos(self.simulacion, {'saturacion_wan': 70}, 2)

        self.assertEqual(estado['saturacion_wan'], 80)
        self.assertEqual(mensajes, ['La campana eleva el trafico WAN.'])
        self.assertEqual(estado['__eventos__'], [f'db:{self.evento.pk}'])


class RecursosTradeOffTests(TestCase):
    def setUp(self):
        self.profesor = User.objects.create_user(username='prof_recursos', is_staff=True)
        institucion = Institucion.objects.create(nombre='Recursos Demo', usuario_creacion=self.profesor)
        carrera = Carrera.objects.create(
            institucion=institucion,
            nombre='Software',
            codigo='SW-REC',
            usuario_creacion=self.profesor,
        )
        malla = Malla.objects.create(
            carrera=carrera,
            nombre='Malla recursos',
            codigo='REC',
            usuario_creacion=self.profesor,
        )
        nivel = NivelMalla.objects.create(
            malla=malla,
            numero=1,
            nombre='Nivel 1',
            usuario_creacion=self.profesor,
        )
        materia = Materia.objects.create(
            institucion=institucion,
            codigo='ARQ-REC',
            nombre='Arquitectura',
            usuario_creacion=self.profesor,
        )
        materia_malla = MateriaMalla.objects.create(
            malla=malla,
            nivel=nivel,
            materia=materia,
            usuario_creacion=self.profesor,
        )
        self.simulacion = Simulacion.objects.create(
            materia_malla=materia_malla,
            profesor=self.profesor,
            tipo_simulacion=Simulacion.TIPO_CON_IA_DINAMICA,
            titulo='Trade-offs de arquitectura',
            maximo_decisiones=3,
            usuario_creacion=self.profesor,
        )
        RecursoSimulacion.objects.create(
            simulacion=self.simulacion,
            codigo='presupuesto',
            nombre='Presupuesto',
            valor_inicial=100,
            valor_minimo=0,
            valor_maximo=100,
            unidad='pts',
            usuario_creacion=self.profesor,
        )
        AccionSugeridaSimulacion.objects.create(
            simulacion=self.simulacion,
            numero_ronda=2,
            texto='Refactorizar consultas criticas con cache',
            descripcion='Mejora rendimiento con costo tecnico y de equipo.',
            impacto_base={'rendimiento': 12},
            costo_recursos={'presupuesto': 35},
            usuario_creacion=self.profesor,
        )

    def test_recursos_iniciales_y_consumo(self):
        recursos = construir_recursos_iniciales(self.simulacion)

        self.assertEqual(recursos, {'presupuesto': 100.0})
        recursos = aplicar_costo_recursos(recursos, {'presupuesto': 35})

        self.assertEqual(recursos['presupuesto'], 65.0)
        self.assertEqual(validar_recursos(self.simulacion, {'presupuesto': 0})[0]['recurso'], 'presupuesto')

    def test_detecta_decision_sugerida_por_texto(self):
        accion = detectar_accion_sugerida(
            self.simulacion,
            'Vamos a refactorizar consultas criticas con cache para estabilizar el sistema.',
        )

        self.assertIsNotNone(accion)
        self.assertEqual(accion.costo_recursos, {'presupuesto': 35})


class CapaCursoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from core.models import PerfilUsuario
        from simulador.models import Seccion, Asignacion, ResultadoAprendizaje
        cls.prof = User.objects.create_user(username="profe_c", password="x", is_staff=True)
        cls.e1 = User.objects.create_user(username="e1", password="x", first_name="Ana", last_name="Gomez")
        cls.e2 = User.objects.create_user(username="e2", password="x", first_name="Luis", last_name="Martinez")
        cls.e3 = User.objects.create_user(username="e3", password="x", first_name="Sin", last_name="Entrega")
        inst = Institucion.objects.create(nombre="UTA")
        for u in (cls.e1, cls.e2, cls.e3):
            PerfilUsuario.objects.create(usuario=u, institucion=inst, rol=PerfilUsuario.ESTUDIANTE)
        carrera = Carrera.objects.create(institucion=inst, nombre="Sis", codigo="S")
        malla = Malla.objects.create(carrera=carrera, nombre="M", codigo="M1")
        nivel = NivelMalla.objects.create(malla=malla, numero=1, nombre="N1")
        materia = Materia.objects.create(institucion=inst, codigo="DJ", nombre="Django")
        cls.mm = MateriaMalla.objects.create(malla=malla, nivel=nivel, materia=materia)
        cls.periodo = PeriodoAcademico.objects.create(institucion=inst, nombre="2026-1", fecha_inicio=date(2026,1,1), fecha_fin=date(2026,6,30))
        cls.sim = Simulacion.objects.create(materia_malla=cls.mm, profesor=cls.prof, titulo="Caso 1", maximo_decisiones=1)
        cls.seccion = Seccion.objects.create(materia_malla=cls.mm, periodo=cls.periodo, profesor=cls.prof, paralelo="A")
        cls.seccion.estudiantes.add(cls.e1, cls.e2, cls.e3)
        cls.asig = Asignacion.objects.create(seccion=cls.seccion, simulacion=cls.sim, titulo="Tarea 1")
        # e1: un intento 80; e2: dos intentos, mejor 90; e3: nada
        intento_e1 = IntentoSimulacion.objects.create(estudiante=cls.e1, simulacion=cls.sim, periodo=cls.periodo, finalizado=True, puntuacion_final=80)
        IntentoSimulacion.objects.create(estudiante=cls.e2, simulacion=cls.sim, periodo=cls.periodo, finalizado=True, puntuacion_final=60)
        intento_e2 = IntentoSimulacion.objects.create(estudiante=cls.e2, simulacion=cls.sim, periodo=cls.periodo, finalizado=True, puntuacion_final=90)
        cls.ra = ResultadoAprendizaje.objects.create(materia_malla=cls.mm, codigo="RA1", descripcion="Aplica restricciones")
        ConceptoEsperadoRonda.objects.create(simulacion=cls.sim, numero_ronda=1, nombre="C1", palabras_clave="unique", peso=100, resultado_aprendizaje=cls.ra)
        from simulador.models import PasoSimulacion
        PasoSimulacion.objects.create(
            intento=intento_e1, numero=1, situacion_presentada='s',
            decision_estudiante='d', justificacion_estudiante='j', puntaje_paso=80,
            evaluacion_detalle={'conceptos_faltantes': ['Transacciones']},
            pronostico_indicador='seguridad',
            pronostico_resultado={'estado': 'diferencia', 'indicador': 'seguridad'},
            tradeoff_resultado={'sacrificios': [{'nombre': 'Presupuesto'}]},
            impacto_calculado={'seguridad': -5},
        )
        PasoSimulacion.objects.create(
            intento=intento_e2, numero=1, situacion_presentada='s',
            decision_estudiante='d', justificacion_estudiante='j', puntaje_paso=90,
            evaluacion_detalle={'conceptos_faltantes': []},
            reflexion='Identifique la causa.',
        )

    def test_libro_notas_mejor_intento_y_estados(self):
        from simulador import cursos_service
        filas = {f["estudiante"].username: f for f in cursos_service.libro_notas(self.asig)}
        self.assertEqual(float(filas["e1"]["nota"]), 80.0)
        self.assertEqual(float(filas["e2"]["nota"]), 90.0)
        self.assertEqual(filas["e2"]["intentos"], 2)
        self.assertIsNone(filas["e3"]["nota"])
        self.assertEqual(filas["e1"]["estado"], "APROBADO")
        self.assertEqual(filas["e3"]["estado"], "SIN_ENTREGAR")

    def test_resumen_y_posiciones(self):
        from simulador import cursos_service
        r = cursos_service.resumen_asignacion(self.asig)
        self.assertEqual(r["total"], 3)
        self.assertEqual(r["entregados"], 2)
        self.assertEqual(r["aprobados"], 2)
        self.assertEqual(float(r["promedio"]), 85.0)
        pos = cursos_service.tabla_posiciones(self.asig)
        self.assertEqual(pos[0]["nombre"], "Luis Martinez")
        self.assertEqual(pos[0]["posicion"], 1)

    def test_logro_resultados_aprendizaje(self):
        from simulador import cursos_service
        filas = cursos_service.logro_resultados_aprendizaje(self.seccion)
        self.assertEqual(len(filas), 1)
        self.assertEqual(float(filas[0]["promedio"]), 85.0)

    def test_vista_y_export_csv(self):
        c = Client(); c.force_login(self.prof)
        self.assertEqual(c.get("/simulador/pro_cursos").status_code, 200)
        self.assertEqual(c.get(f"/simulador/pro_cursos?action=seccion&pk={self.seccion.pk}").status_code, 200)
        self.assertEqual(c.get(f"/simulador/pro_cursos?action=notas&pk={self.asig.pk}").status_code, 200)
        r = c.get(f"/simulador/pro_cursos?action=export&pk={self.asig.pk}")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/csv", r["Content-Type"])
        cuerpo = r.content.decode("utf-8")
        self.assertIn("Ana Gomez", cuerpo)
        self.assertIn("90.00", cuerpo)

    def test_diagnostico_errores_asignacion(self):
        from simulador import cursos_service
        d = cursos_service.diagnostico_errores_asignacion(self.asig)
        self.assertEqual(d['conceptos_faltantes'][0]['nombre'], 'Transacciones')
        self.assertEqual(d['pronosticos_fallidos'][0]['nombre'], 'seguridad')
        self.assertEqual(d['tradeoffs_sacrificados'][0]['nombre'], 'Presupuesto')
        self.assertTrue(any(r['motivo'] == 'Sin entrega' for r in d['estudiantes_riesgo']))
        self.assertIn('auditoria_caso', d)
        self.assertIn('puntaje', d['auditoria_caso'])

    def test_vista_diagnostico_renderiza(self):
        c = Client(); c.force_login(self.prof)
        r = c.get(f"/simulador/pro_cursos?action=diagnostico&pk={self.asig.pk}")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Conceptos faltantes")
        self.assertContains(r, "Transacciones")
        self.assertContains(r, "Calidad del caso")

    def test_export_diagnostico_csv(self):
        c = Client(); c.force_login(self.prof)
        r = c.get(f"/simulador/pro_cursos?action=diagnostico_export&pk={self.asig.pk}")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/csv", r["Content-Type"])
        cuerpo = r.content.decode("utf-8")
        self.assertIn("Concepto faltante", cuerpo)
        self.assertIn("Auditoria del caso", cuerpo)

    def test_estudiante_no_entra_a_cursos(self):
        c = Client(); c.force_login(self.e1)
        self.assertEqual(c.get("/simulador/pro_cursos").status_code, 302)


class CandadoTareaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from datetime import timedelta
        from django.utils import timezone
        from core.models import PerfilUsuario
        from simulador.models import Seccion, Asignacion, Equipo
        cls.est = User.objects.create_user('al1', password='x')
        inst = Institucion.objects.create(nombre='UTA')
        PerfilUsuario.objects.create(usuario=cls.est, institucion=inst, rol=PerfilUsuario.ESTUDIANTE)
        prof = User.objects.create_user('pr1', password='x', is_staff=True)
        carrera = Carrera.objects.create(institucion=inst, nombre='S', codigo='S')
        malla = Malla.objects.create(carrera=carrera, nombre='M', codigo='M')
        nivel = NivelMalla.objects.create(malla=malla, numero=1, nombre='N')
        materia = Materia.objects.create(institucion=inst, codigo='C', nombre='Caso')
        mm = MateriaMalla.objects.create(malla=malla, nivel=nivel, materia=materia)
        cls.periodo = PeriodoAcademico.objects.create(institucion=inst, nombre='P', fecha_inicio=date(2026,1,1), fecha_fin=date(2026,12,31), activo_matricula=True)
        cls.sim = Simulacion.objects.create(materia_malla=mm, profesor=prof, titulo='Asignada', estado=Simulacion.PUBLICADA, maximo_decisiones=1)
        cls.sim_libre = Simulacion.objects.create(materia_malla=mm, profesor=prof, titulo='Libre', estado=Simulacion.PUBLICADA, maximo_decisiones=1)
        cls.sec = Seccion.objects.create(materia_malla=mm, periodo=cls.periodo, profesor=prof, paralelo='A')
        cls.sec.estudiantes.add(cls.est)
        cls.asig = Asignacion.objects.create(
            seccion=cls.sec, simulacion=cls.sim, titulo='Tarea',
            fecha_limite=timezone.now() - timedelta(days=1), trabajo_en_equipo=True,
        )
        cls.equipo = Equipo.objects.create(asignacion=cls.asig, nombre='Equipo 1')
        cls.equipo.integrantes.add(cls.est)

    def test_asignacion_para_detecta_tarea_y_libre(self):
        from simulador import cursos_service
        self.assertEqual(cursos_service.asignacion_para(self.est, self.sim), self.asig)
        self.assertIsNone(cursos_service.asignacion_para(self.est, self.sim_libre))

    def test_equipo_de(self):
        from simulador import cursos_service
        self.assertEqual(cursos_service.equipo_de(self.est, self.asig), self.equipo)

    def test_tarea_cerrada_bloquea_inicio(self):
        from simulador.models import IntentoSimulacion
        c = Client(); c.force_login(self.est)
        r = c.post('/simulador/alu_simulaciones', {'action': 'iniciar', 'simulacion_id': self.sim.pk},
                   HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()['result'])
        self.assertIn('cerrada', r.json()['mensaje'])
        self.assertFalse(IntentoSimulacion.objects.filter(estudiante=self.est, simulacion=self.sim).exists())


class EquiposYMapeoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from core.models import PerfilUsuario
        from simulador.models import Seccion, Asignacion, ResultadoAprendizaje
        cls.prof = User.objects.create_user('pm', password='x', is_staff=True)
        cls.e1 = User.objects.create_user('m1', password='x', first_name='A', last_name='A')
        cls.e2 = User.objects.create_user('m2', password='x', first_name='B', last_name='B')
        inst = Institucion.objects.create(nombre='UTA')
        for u in (cls.e1, cls.e2):
            PerfilUsuario.objects.create(usuario=u, institucion=inst, rol=PerfilUsuario.ESTUDIANTE)
        carrera = Carrera.objects.create(institucion=inst, nombre='S', codigo='S')
        malla = Malla.objects.create(carrera=carrera, nombre='M', codigo='M')
        nivel = NivelMalla.objects.create(malla=malla, numero=1, nombre='N')
        materia = Materia.objects.create(institucion=inst, codigo='C', nombre='Caso')
        cls.mm = MateriaMalla.objects.create(malla=malla, nivel=nivel, materia=materia)
        periodo = PeriodoAcademico.objects.create(institucion=inst, nombre='P', fecha_inicio=date(2026,1,1), fecha_fin=date(2026,12,31))
        cls.sim = Simulacion.objects.create(materia_malla=cls.mm, profesor=cls.prof, titulo='S1', maximo_decisiones=1)
        cls.sec = Seccion.objects.create(materia_malla=cls.mm, periodo=periodo, profesor=cls.prof, paralelo='A')
        cls.sec.estudiantes.add(cls.e1, cls.e2)
        cls.asig = Asignacion.objects.create(seccion=cls.sec, simulacion=cls.sim, titulo='T', trabajo_en_equipo=True)
        cls.ra = ResultadoAprendizaje.objects.create(materia_malla=cls.mm, codigo='RA1', descripcion='desc')
        cls.concepto = ConceptoEsperadoRonda.objects.create(simulacion=cls.sim, numero_ronda=1, nombre='C1', palabras_clave='x', peso=100)

    def test_crear_equipo_via_post(self):
        from simulador.models import Equipo
        c = Client(); c.force_login(self.prof)
        r = c.post('/simulador/pro_cursos', {
            'action': 'add_equipo', 'asignacion': self.asig.pk,
            'nombre': 'Los Cracks', 'integrantes': [self.e1.pk, self.e2.pk], 'activo': 'on',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertTrue(r.json()['result'])
        eq = Equipo.objects.get(asignacion=self.asig, nombre='Los Cracks')
        self.assertEqual(eq.integrantes.count(), 2)

    def test_mapear_concepto_a_ra(self):
        c = Client(); c.force_login(self.prof)
        r = c.post('/simulador/pro_cursos', {
            'action': 'map_concepto', 'seccion': self.sec.pk,
            'concepto': self.concepto.pk, 'resultado': self.ra.pk,
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertTrue(r.json()['result'])
        self.concepto.refresh_from_db()
        self.assertEqual(self.concepto.resultado_aprendizaje, self.ra)
        # desenlazar
        c.post('/simulador/pro_cursos', {
            'action': 'map_concepto', 'seccion': self.sec.pk,
            'concepto': self.concepto.pk, 'resultado': '',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.concepto.refresh_from_db()
        self.assertIsNone(self.concepto.resultado_aprendizaje)

    def test_paginas_equipos_y_mapeo_renderizan(self):
        c = Client(); c.force_login(self.prof)
        self.assertEqual(c.get(f'/simulador/pro_cursos?action=equipos&pk={self.asig.pk}').status_code, 200)
        self.assertEqual(c.get(f'/simulador/pro_cursos?action=mapeo&pk={self.sec.pk}').status_code, 200)


class ReporteAcreditacionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from core.models import PerfilUsuario
        from simulador.models import Seccion, Asignacion, ResultadoAprendizaje
        cls.prof = User.objects.create_user('pr2', password='x', is_staff=True)
        cls.est = User.objects.create_user('es2', password='x', first_name='Ana', last_name='Gomez')
        inst = Institucion.objects.create(nombre='Universidad Tecnica de Ambato')
        PerfilUsuario.objects.create(usuario=cls.est, institucion=inst, rol=PerfilUsuario.ESTUDIANTE)
        carrera = Carrera.objects.create(institucion=inst, nombre='Sis', codigo='S')
        malla = Malla.objects.create(carrera=carrera, nombre='M', codigo='M')
        nivel = NivelMalla.objects.create(malla=malla, numero=1, nombre='N')
        materia = Materia.objects.create(institucion=inst, codigo='CC', nombre='Caso')
        mm = MateriaMalla.objects.create(malla=malla, nivel=nivel, materia=materia)
        periodo = PeriodoAcademico.objects.create(institucion=inst, nombre='2026-1', fecha_inicio=date(2026,1,1), fecha_fin=date(2026,12,31))
        cls.sim = Simulacion.objects.create(materia_malla=mm, profesor=cls.prof, titulo='Caso 1', maximo_decisiones=1)
        cls.sec = Seccion.objects.create(materia_malla=mm, periodo=periodo, profesor=cls.prof, paralelo='A')
        cls.sec.estudiantes.add(cls.est)
        cls.asig = Asignacion.objects.create(seccion=cls.sec, simulacion=cls.sim, titulo='T1')
        ra = ResultadoAprendizaje.objects.create(materia_malla=mm, codigo='RA1', descripcion='Aplica')
        ConceptoEsperadoRonda.objects.create(simulacion=cls.sim, numero_ronda=1, nombre='C', palabras_clave='x', peso=100, resultado_aprendizaje=ra)
        IntentoSimulacion.objects.create(estudiante=cls.est, simulacion=cls.sim, finalizado=True, puntuacion_final=82)

    def test_descarga_pdf_valido(self):
        c = Client(); c.force_login(self.prof)
        r = c.get(f'/simulador/pro_cursos?action=reporte_pdf&pk={self.sec.pk}')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'application/pdf')
        self.assertIn('attachment', r['Content-Disposition'])
        self.assertTrue(r.content.startswith(b'%PDF-'))
        self.assertGreater(len(r.content), 1000)

    def test_reporte_funcion_genera_bytes(self):
        from simulador import reportes
        pdf = reportes.reporte_acreditacion_pdf(self.sec)
        self.assertTrue(pdf.startswith(b'%PDF-'))

    def test_estudiante_no_descarga_reporte(self):
        c = Client(); c.force_login(self.est)
        self.assertEqual(c.get(f'/simulador/pro_cursos?action=reporte_pdf&pk={self.sec.pk}').status_code, 302)


class PenalizacionJustaTests(TestCase):
    """Premiar el avance: un indicador que el estudiante MEJORO este turno no se
    penaliza aunque siga fuera de rango (defectos 15% -> 7% va por buen camino)."""

    def test_magnitud_violacion(self):
        from simulador.services.core import _magnitud_violacion
        self.assertEqual(_magnitud_violacion('<=', 4, 7), 3.0)   # 7 > 4: viola por 3
        self.assertEqual(_magnitud_violacion('<=', 4, 4), 0.0)   # cumple
        self.assertEqual(_magnitud_violacion('>=', 80, 70), 10.0)  # 70 < 80: viola por 10
        self.assertEqual(_magnitud_violacion('>=', 80, 90), 0.0)   # cumple

    def test_restriccion_mejoro_premia_el_avance(self):
        from simulador.services.core import _restriccion_mejoro
        alerta = {'indicador': 'defectos', 'operador': '<=', 'limite': 4}
        # bajo defectos de 15 a 7: mejoro (aunque siga > 4)
        self.assertTrue(_restriccion_mejoro(alerta, {'defectos': 15}, {'defectos': 7}))
        # subio defectos de 7 a 10: empeoro
        self.assertFalse(_restriccion_mejoro(alerta, {'defectos': 7}, {'defectos': 10}))
        # sin cambio: no mejoro
        self.assertFalse(_restriccion_mejoro(alerta, {'defectos': 7}, {'defectos': 7}))


from django.test import override_settings


@override_settings(OPENAI_API_KEY='', DEEPSEEK_API_KEY='')
class ReflexionKolbTests(TestCase):
    """Fase 1 pedagogica: reflexion por ronda (ciclo de Kolb). Con IA desactivada
    el guardado debe funcionar igual (feedback vacio, fallback)."""

    @classmethod
    def setUpTestData(cls):
        cls.est = User.objects.create_user('refl', password='x')
        inst = Institucion.objects.create(nombre='UTA')
        carrera = Carrera.objects.create(institucion=inst, nombre='S', codigo='S')
        malla = Malla.objects.create(carrera=carrera, nombre='M', codigo='M')
        nivel = NivelMalla.objects.create(malla=malla, numero=1, nombre='N')
        materia = Materia.objects.create(institucion=inst, codigo='C', nombre='Caso')
        mm = MateriaMalla.objects.create(malla=malla, nivel=nivel, materia=materia)
        cls.sim = Simulacion.objects.create(materia_malla=mm, profesor=cls.est, titulo='S1', maximo_decisiones=2)
        cls.it = IntentoSimulacion.objects.create(estudiante=cls.est, simulacion=cls.sim, numero_ronda_actual=2)
        from simulador.models import PasoSimulacion
        cls.paso = PasoSimulacion.objects.create(
            intento=cls.it, numero=1, es_valido=True, situacion_presentada='s',
            decision_estudiante='Decidi diagnosticar el problema.', justificacion_estudiante='j', puntaje_paso=60,
        )

    def test_reflexionar_guarda_reflexion(self):
        c = Client(); c.force_login(self.est)
        r = c.post('/simulador/alu_simulaciones', {
            'action': 'reflexionar', 'intento_id': self.it.pk, 'numero': 1,
            'reflexion': 'La empresa mejoro porque ataque la causa raiz.',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['result'])
        self.paso.refresh_from_db()
        self.assertIn('causa raiz', self.paso.reflexion)

    def test_reflexion_vacia_se_rechaza(self):
        c = Client(); c.force_login(self.est)
        r = c.post('/simulador/alu_simulaciones', {
            'action': 'reflexionar', 'intento_id': self.it.pk, 'numero': 1, 'reflexion': '   ',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertFalse(r.json()['result'])

    def test_debrief_funciona_sin_ia(self):
        from simulador.services.core import generar_debriefing_final
        deb = generar_debriefing_final(self.it)
        self.assertIn('RESUMEN', deb)  # cae al debrief mecanico, no se rompe


class PronosticoPrevioTests(TestCase):
    """Fase 2 pedagogica: el estudiante anticipa el impacto antes de decidir y
    luego compara su hipotesis con la reaccion real de la empresa."""

    @classmethod
    def setUpTestData(cls):
        cls.est = User.objects.create_user('pron', password='x')
        inst = Institucion.objects.create(nombre='UTA')
        carrera = Carrera.objects.create(institucion=inst, nombre='S', codigo='S')
        malla = Malla.objects.create(carrera=carrera, nombre='M', codigo='M')
        nivel = NivelMalla.objects.create(malla=malla, numero=1, nombre='N')
        materia = Materia.objects.create(institucion=inst, codigo='C2', nombre='Caso 2')
        mm = MateriaMalla.objects.create(malla=malla, nivel=nivel, materia=materia)
        cls.sim = Simulacion.objects.create(
            materia_malla=mm,
            profesor=cls.est,
            titulo='S2',
            tipo_simulacion=Simulacion.TIPO_SIN_IA_ARBOL,
            estado=Simulacion.PUBLICADA,
            maximo_decisiones=2,
        )
        IndicadorSimulacion.objects.create(
            simulacion=cls.sim,
            codigo='ventas',
            nombre='Ventas',
            valor_inicial=10,
            valor_minimo=0,
            valor_maximo=100,
            direccion_optima=IndicadorSimulacion.DIRECCION_ALTO,
        )
        cls.escenario = EscenarioSimulacion.objects.create(
            simulacion=cls.sim, titulo='Inicio', situacion='s', es_inicial=True,
        )
        cls.siguiente = EscenarioSimulacion.objects.create(
            simulacion=cls.sim, titulo='Siguiente', situacion='s2', orden=2,
        )
        cls.decision = DecisionConfigurada.objects.create(
            escenario=cls.escenario,
            texto='Invertir en ventas',
            descripcion='d',
            impacto={'ventas': 15},
            puntaje_base=80,
            retroalimentacion='Subieron las ventas.',
            siguiente_escenario=cls.siguiente,
        )

    def test_evaluar_pronostico_detecta_acierto(self):
        resultado = evaluar_pronostico(
            {'indicador': 'ventas', 'direccion': 'sube', 'justificacion': 'campana comercial'},
            {'ventas': 10},
            {'ventas': 25},
        )
        self.assertEqual(resultado['estado'], 'acierto')
        self.assertEqual(resultado['direccion_real'], 'sube')

    def test_ejecutar_paso_guarda_pronostico_previo(self):
        intento = IntentoSimulacion.objects.create(
            estudiante=self.est,
            simulacion=self.sim,
            estado_actual={'ventas': 10},
            escenario_actual=self.escenario,
            situacion_actual='s',
            numero_ronda_actual=1,
        )
        c = Client(); c.force_login(self.est)
        r = c.post('/simulador/alu_simulaciones', {
            'action': 'ejecutar_paso',
            'intento_id': intento.pk,
            'decision_id': self.decision.pk,
            'pronostico_indicador': 'ventas',
            'pronostico_direccion': 'sube',
            'pronostico_justificacion': 'La inversion deberia generar demanda.',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(r.status_code, 200)
        paso = intento.pasos.get(numero=1)
        self.assertEqual(paso.pronostico_indicador, 'ventas')
        self.assertEqual(paso.pronostico_resultado['estado'], 'acierto')


class TradeoffExplicitoTests(TestCase):
    """Fase 3 pedagogica: hacer visible que una buena decision suele tener costo,
    riesgo o deterioro de otra variable."""

    @classmethod
    def setUpTestData(cls):
        cls.est = User.objects.create_user('trade', password='x')
        inst = Institucion.objects.create(nombre='UTA')
        carrera = Carrera.objects.create(institucion=inst, nombre='S', codigo='S')
        malla = Malla.objects.create(carrera=carrera, nombre='M', codigo='M')
        nivel = NivelMalla.objects.create(malla=malla, numero=1, nombre='N')
        materia = Materia.objects.create(institucion=inst, codigo='C3', nombre='Caso 3')
        mm = MateriaMalla.objects.create(malla=malla, nivel=nivel, materia=materia)
        cls.sim = Simulacion.objects.create(
            materia_malla=mm,
            profesor=cls.est,
            titulo='S3',
            tipo_simulacion=Simulacion.TIPO_CON_IA_DINAMICA,
            estado=Simulacion.PUBLICADA,
            maximo_decisiones=2,
        )
        IndicadorSimulacion.objects.create(
            simulacion=cls.sim, codigo='calidad', nombre='Calidad',
            valor_inicial=50, valor_minimo=0, valor_maximo=100,
            direccion_optima=IndicadorSimulacion.DIRECCION_ALTO,
        )
        IndicadorSimulacion.objects.create(
            simulacion=cls.sim, codigo='defectos', nombre='Defectos',
            valor_inicial=10, valor_minimo=0, valor_maximo=50,
            direccion_optima=IndicadorSimulacion.DIRECCION_BAJO,
        )
        RecursoSimulacion.objects.create(
            simulacion=cls.sim, codigo='presupuesto', nombre='Presupuesto',
            valor_inicial=100, valor_minimo=0, valor_maximo=100,
        )

    def test_evaluar_tradeoff_detecta_ganancia_y_sacrificio(self):
        resultado = evaluar_tradeoff(
            self.sim,
            'Acepto gastar presupuesto para subir calidad.',
            {'calidad': 50, 'defectos': 10},
            {'calidad': 70, 'defectos': 15},
            {'presupuesto': 100},
            {'presupuesto': 70},
        )
        self.assertEqual(resultado['estado'], 'tradeoff_real')
        self.assertEqual(len(resultado['ganancias']), 1)
        self.assertEqual(len(resultado['sacrificios']), 2)

    @override_settings(OPENAI_API_KEY='', DEEPSEEK_API_KEY='')
    def test_ejecutar_paso_guarda_tradeoff_aceptado(self):
        accion = AccionSugeridaSimulacion.objects.create(
            simulacion=self.sim,
            numero_ronda=1,
            texto='Mejorar control de calidad',
            impacto_base={'calidad': 20, 'defectos': 5},
            costo_recursos={'presupuesto': 30},
        )
        intento = IntentoSimulacion.objects.create(
            estudiante=self.est,
            simulacion=self.sim,
            estado_actual={'calidad': 50, 'defectos': 10},
            recursos_actuales={'presupuesto': 100},
            situacion_actual='Debes mejorar calidad sin ignorar costos.',
            numero_ronda_actual=1,
        )
        c = Client(); c.force_login(self.est)
        r = c.post('/simulador/alu_simulaciones', {
            'action': 'ejecutar_paso',
            'intento_id': intento.pk,
            'accion_id': accion.pk,
            'justificacion': 'Uso control de calidad porque reduce riesgos operativos y prioriza evidencia medible.',
            'pronostico_indicador': 'calidad',
            'pronostico_direccion': 'sube',
            'pronostico_justificacion': 'El control deberia aumentar la calidad.',
            'tradeoff_aceptado': 'Acepto gastar presupuesto y tolerar carga inicial para subir calidad.',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(r.status_code, 200)
        paso = intento.pasos.get(numero=1)
        self.assertIn('presupuesto', paso.tradeoff_aceptado)
        self.assertEqual(paso.tradeoff_resultado['estado'], 'tradeoff_real')


class AndamiajeAdaptativoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.est = User.objects.create_user('anda', password='x')
        inst = Institucion.objects.create(nombre='UTA')
        carrera = Carrera.objects.create(institucion=inst, nombre='S', codigo='S')
        malla = Malla.objects.create(carrera=carrera, nombre='M', codigo='M')
        nivel = NivelMalla.objects.create(malla=malla, numero=1, nombre='N')
        materia = Materia.objects.create(institucion=inst, codigo='C4', nombre='Caso 4')
        mm = MateriaMalla.objects.create(malla=malla, nivel=nivel, materia=materia)
        cls.sim = Simulacion.objects.create(materia_malla=mm, profesor=cls.est, titulo='S4', maximo_decisiones=3)

    def test_andamiaje_sube_si_hay_paso_invalido(self):
        from simulador.alu_simulaciones import _andamiaje_adaptativo
        from simulador.models import PasoSimulacion
        intento = IntentoSimulacion.objects.create(estudiante=self.est, simulacion=self.sim, numero_ronda_actual=2)
        PasoSimulacion.objects.create(
            intento=intento, numero=1, es_valido=False, situacion_presentada='s',
            decision_estudiante='', justificacion_estudiante='', puntaje_paso=0,
        )
        ayuda = _andamiaje_adaptativo(intento)
        self.assertEqual(ayuda['nivel'], 'ALTO')
        self.assertTrue(ayuda['requiere_campos'])

    def test_andamiaje_se_desvanece_con_buen_desempeno(self):
        from simulador.alu_simulaciones import _andamiaje_adaptativo
        from simulador.models import PasoSimulacion
        intento = IntentoSimulacion.objects.create(estudiante=self.est, simulacion=self.sim, numero_ronda_actual=2)
        PasoSimulacion.objects.create(
            intento=intento, numero=1, es_valido=True, situacion_presentada='s',
            decision_estudiante='d', justificacion_estudiante='j', puntaje_paso=90,
            reflexion='Use evidencia del caso.', tradeoff_aceptado='Acepte gastar presupuesto.',
        )
        ayuda = _andamiaje_adaptativo(intento)
        self.assertEqual(ayuda['nivel'], 'BAJO')
        self.assertFalse(ayuda['requiere_campos'])

    def test_calidad_metacognitiva_resume_habitos(self):
        from simulador.alu_simulaciones import _calidad_metacognitiva
        from simulador.models import PasoSimulacion
        intento = IntentoSimulacion.objects.create(estudiante=self.est, simulacion=self.sim, numero_ronda_actual=2)
        PasoSimulacion.objects.create(
            intento=intento, numero=1, es_valido=True, situacion_presentada='s',
            decision_estudiante='d', justificacion_estudiante='j', puntaje_paso=90,
            reflexion='Identifique causa y evidencia.',
            pronostico_indicador='x', pronostico_resultado={'estado': 'acierto'},
            tradeoff_aceptado='Acepte costo.', tradeoff_resultado={'estado': 'tradeoff_real'},
        )
        calidad = _calidad_metacognitiva(intento)
        self.assertEqual(calidad['nivel'], 'Fuerte')
        self.assertEqual(calidad['puntaje'], 100)

    def test_metacognicion_ignora_intentos_invalidos(self):
        from simulador.alu_simulaciones import _calidad_metacognitiva
        intento = IntentoSimulacion.objects.create(
            estudiante=self.est, simulacion=self.sim, numero_ronda_actual=2,
        )
        PasoSimulacion.objects.create(
            intento=intento, numero=1, es_valido=True, situacion_presentada='s',
            decision_estudiante='d', justificacion_estudiante='j', puntaje_paso=80,
        )
        PasoSimulacion.objects.create(
            intento=intento, numero=2, es_valido=False, situacion_presentada='s',
            decision_estudiante='d', justificacion_estudiante='j', puntaje_paso=0,
            reflexion='No debe contar', pronostico_indicador='x',
            pronostico_resultado={'estado': 'acierto'}, tradeoff_aceptado='No debe contar',
            tradeoff_resultado={'estado': 'tradeoff_real'},
        )
        calidad = _calidad_metacognitiva(intento)
        self.assertEqual(calidad['total'], 1)
        self.assertEqual(calidad['reflexiones'], 0)
        self.assertEqual(calidad['pronosticos'], 0)
        self.assertEqual(calidad['tradeoffs'], 0)

    def test_snapshot_conserva_caso_indicadores_metas_y_rondas(self):
        from simulador.alu_simulaciones import _caso_del_intento, _objetivos_mision
        self.sim.titulo = 'Caso original'
        self.sim.situacion_inicial = 'Situacion original'
        self.sim.parametros = {'rondas': [
            {'numero': 1, 'situacion': 'Diagnostico original'},
            {'numero': 2, 'situacion': 'Decision original'},
        ]}
        self.sim.save()
        indicador = IndicadorSimulacion.objects.create(
            simulacion=self.sim, codigo='riesgo', nombre='Riesgo original',
            valor_inicial=50, valor_minimo=0, valor_maximo=100,
            direccion_optima='BAJO', unidad='pts',
        )
        condicion = CondicionExitoSimulacion.objects.create(
            simulacion=self.sim, descripcion='Mantener riesgo bajo',
            codigo_indicador='riesgo', operador='<=', valor_objetivo=35,
        )
        snapshot = serializar_configuracion_simulacion(self.sim)
        self.assertIn('recursos', snapshot)
        self.assertIn('investigaciones', snapshot)
        self.assertIn('eventos', snapshot)
        self.assertIn('valor_objetivo', snapshot['indicadores'][0])
        intento = IntentoSimulacion.objects.create(
            estudiante=self.est, simulacion=self.sim, estado_actual={'riesgo': 40.0},
            configuracion_snapshot=snapshot,
        )

        self.sim.titulo = 'Caso cambiado'
        self.sim.parametros = {'rondas': [{'situacion': 'Otra simulacion'}]}
        self.sim.save()
        indicador.nombre = 'Indicador cambiado'
        indicador.save()
        condicion.valor_objetivo = 10
        condicion.save()

        self.assertEqual(_caso_del_intento(intento)['titulo'], 'Caso original')
        self.assertEqual(_objetivos_mision(intento)[0]['meta'], '<= 35 pts')
        self.assertEqual(_objetivos_mision(intento)[0]['indicador'], 'Riesgo original')
        self.assertEqual(situacion_de_ronda(self.sim, 2, snapshot), 'Decision original')

    def test_impacto_decimal_no_deja_residuos_float(self):
        self.assertEqual(aplicar_impacto({'x': 0.1}, {'x': 0.2})['x'], 0.3)

    def test_rubrica_visible_incluye_conceptos(self):
        from simulador.alu_simulaciones import _rubrica_visible
        ConceptoEsperadoRonda.objects.create(
            simulacion=self.sim, numero_ronda=1, nombre='Criterio clave',
            palabras_clave='clave', peso=100,
        )
        intento = IntentoSimulacion.objects.create(estudiante=self.est, simulacion=self.sim, numero_ronda_actual=1)
        rubrica = _rubrica_visible(intento, 1)
        self.assertEqual(rubrica['conceptos'][0].nombre, 'Criterio clave')


class ComparacionReintentoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.est = User.objects.create_user('reint', password='x')
        inst = Institucion.objects.create(nombre='UTA')
        carrera = Carrera.objects.create(institucion=inst, nombre='S', codigo='S')
        malla = Malla.objects.create(carrera=carrera, nombre='M', codigo='M')
        nivel = NivelMalla.objects.create(malla=malla, numero=1, nombre='N')
        materia = Materia.objects.create(institucion=inst, codigo='C5', nombre='Caso 5')
        mm = MateriaMalla.objects.create(malla=malla, nivel=nivel, materia=materia)
        cls.sim = Simulacion.objects.create(materia_malla=mm, profesor=cls.est, titulo='S5', estado=Simulacion.PUBLICADA, maximo_decisiones=1)
        IndicadorSimulacion.objects.create(
            simulacion=cls.sim, codigo='calidad', nombre='Calidad',
            valor_inicial=50, valor_minimo=0, valor_maximo=100,
            direccion_optima=IndicadorSimulacion.DIRECCION_ALTO,
        )

    def test_comparacion_reintento_resume_mejoras(self):
        from simulador.alu_simulaciones import _comparacion_reintento
        from simulador.models import PasoSimulacion
        origen = IntentoSimulacion.objects.create(
            estudiante=self.est, simulacion=self.sim, finalizado=True,
            puntuacion_final=60, estado_actual={'calidad': 55},
        )
        actual = IntentoSimulacion.objects.create(
            estudiante=self.est, simulacion=self.sim, intento_origen=origen,
            finalizado=True, puntuacion_final=85, estado_actual={'calidad': 80},
        )
        PasoSimulacion.objects.create(
            intento=origen, numero=1, es_valido=False, situacion_presentada='s',
            decision_estudiante='', justificacion_estudiante='', puntaje_paso=0,
        )
        PasoSimulacion.objects.create(
            intento=actual, numero=1, es_valido=True, situacion_presentada='s',
            decision_estudiante='d', justificacion_estudiante='j', puntaje_paso=85,
            reflexion='Reflexione sobre la causa.',
            pronostico_resultado={'estado': 'acierto'},
            tradeoff_aceptado='Acepte gastar presupuesto.',
        )
        comp = _comparacion_reintento(actual)
        self.assertEqual(comp['delta_puntaje'], 25.0)
        self.assertEqual(comp['invalidos_origen'], 1)
        self.assertEqual(comp['invalidos_actual'], 0)
        self.assertEqual(comp['mejoras_indicadores'][0]['nombre'], 'Calidad')
        self.assertTrue(any('Subiste' in s for s in comp['senales']))

    def test_resultado_renderiza_comparacion_reintento(self):
        from simulador.models import PasoSimulacion
        origen = IntentoSimulacion.objects.create(
            estudiante=self.est, simulacion=self.sim, finalizado=True,
            puntuacion_final=60, estado_actual={'calidad': 55},
        )
        actual = IntentoSimulacion.objects.create(
            estudiante=self.est, simulacion=self.sim, intento_origen=origen,
            finalizado=True, puntuacion_final=85, estado_actual={'calidad': 80},
        )
        PasoSimulacion.objects.create(
            intento=actual, numero=1, es_valido=True, situacion_presentada='s',
            decision_estudiante='d', justificacion_estudiante='j', puntaje_paso=85,
        )
        c = Client(); c.force_login(self.est)
        r = c.get(f'/simulador/alu_simulaciones?action=resultado&intento_id={actual.pk}')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Comparacion con intento anterior')
        self.assertContains(r, 'Calidad')


class RetosRefuerzoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.est = User.objects.create_user('reto', password='x')
        inst = Institucion.objects.create(nombre='UTA')
        carrera = Carrera.objects.create(institucion=inst, nombre='S', codigo='S')
        malla = Malla.objects.create(carrera=carrera, nombre='M', codigo='M')
        nivel = NivelMalla.objects.create(malla=malla, numero=1, nombre='N')
        materia = Materia.objects.create(institucion=inst, codigo='C6', nombre='Caso 6')
        mm = MateriaMalla.objects.create(malla=malla, nivel=nivel, materia=materia)
        cls.sim = Simulacion.objects.create(materia_malla=mm, profesor=cls.est, titulo='S6', maximo_decisiones=1)

    def test_finalizar_intento_programa_retos_refuerzo(self):
        from simulador.models import PasoSimulacion, RetoRefuerzo
        from simulador.services.core import finalizar_intento
        intento = IntentoSimulacion.objects.create(estudiante=self.est, simulacion=self.sim, estado_actual={})
        PasoSimulacion.objects.create(
            intento=intento, numero=1, es_valido=True, situacion_presentada='s',
            decision_estudiante='d', justificacion_estudiante='j', puntaje_paso=80,
            evaluacion_detalle={'conceptos_faltantes': ['Causa raiz']},
        )
        finalizar_intento(intento)
        reto = RetoRefuerzo.objects.get(intento_origen=intento)
        self.assertEqual(reto.concepto, 'Causa raiz')
        self.assertFalse(reto.completado)

    def test_completar_reto_disponible(self):
        from datetime import timedelta
        from django.utils import timezone
        from simulador.models import RetoRefuerzo
        intento = IntentoSimulacion.objects.create(estudiante=self.est, simulacion=self.sim, finalizado=True)
        reto = RetoRefuerzo.objects.create(
            estudiante=self.est,
            simulacion=self.sim,
            intento_origen=intento,
            concepto='Indicadores',
            pregunta='Aplica indicadores en otro caso.',
            fecha_disponible=timezone.now() - timedelta(minutes=1),
        )
        c = Client(); c.force_login(self.est)
        r = c.post('/simulador/alu_simulaciones', {
            'action': 'completar_reto',
            'reto_id': reto.pk,
            'respuesta': 'Tomaria una decision basada en un indicador medible y aceptaria un trade-off de costo.',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(r.status_code, 200)
        reto.refresh_from_db()
        self.assertTrue(reto.completado)
        self.assertIn('refuerzo', reto.feedback.lower())


class CasosEquivalentesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.est = User.objects.create_user('transfer', password='x')
        inst = Institucion.objects.create(nombre='UTA')
        carrera = Carrera.objects.create(institucion=inst, nombre='S', codigo='S')
        malla = Malla.objects.create(carrera=carrera, nombre='M', codigo='M')
        nivel = NivelMalla.objects.create(malla=malla, numero=1, nombre='N')
        materia = Materia.objects.create(institucion=inst, codigo='C7', nombre='Caso 7')
        cls.mm = MateriaMalla.objects.create(malla=malla, nivel=nivel, materia=materia)
        cls.ra = ResultadoAprendizaje.objects.create(materia_malla=cls.mm, codigo='RA1', descripcion='Transferir decisiones')
        cls.sim = Simulacion.objects.create(materia_malla=cls.mm, profesor=cls.est, titulo='Caso base', estado=Simulacion.PUBLICADA)
        cls.eq = Simulacion.objects.create(materia_malla=cls.mm, profesor=cls.est, titulo='Caso equivalente', estado=Simulacion.PUBLICADA)
        ConceptoEsperadoRonda.objects.create(simulacion=cls.sim, numero_ronda=1, nombre='C', palabras_clave='x', peso=100, resultado_aprendizaje=cls.ra)
        ConceptoEsperadoRonda.objects.create(simulacion=cls.eq, numero_ronda=1, nombre='C2', palabras_clave='x', peso=100, resultado_aprendizaje=cls.ra)

    def test_casos_equivalentes_prioriza_ra_compartido(self):
        from simulador.alu_simulaciones import _casos_equivalentes
        intento = IntentoSimulacion.objects.create(estudiante=self.est, simulacion=self.sim, finalizado=True)
        casos = _casos_equivalentes(intento, self.est)
        self.assertEqual(casos[0]['simulacion'], self.eq)
        self.assertEqual(casos[0]['compartidos'], 1)

    def test_resultado_renderiza_casos_equivalentes(self):
        intento = IntentoSimulacion.objects.create(estudiante=self.est, simulacion=self.sim, finalizado=True)
        c = Client(); c.force_login(self.est)
        r = c.get(f'/simulador/alu_simulaciones?action=resultado&intento_id={intento.pk}')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Practica transferencia')
        self.assertContains(r, 'Caso equivalente')


class GuardrailsIATests(TestCase):
    @override_settings(SIMUTA_IA_MAX_PROMPT_CHARS=20)
    def test_limitar_prompt_trunca_texto_largo(self):
        from simulador.ia_service import _limitar_prompt
        texto = _limitar_prompt('x' * 100)
        self.assertLess(len(texto), 100)
        self.assertIn('Prompt truncado', texto)

    @override_settings(SIMUTA_IA_MAX_EVAL_CALLS_PER_INTENTO=0)
    def test_limite_ia_bloquea_evaluacion(self):
        from simulador.ia_service import evaluar_ronda_con_proveedores
        est = User.objects.create_user('guard', password='x')
        inst = Institucion.objects.create(nombre='UTA')
        carrera = Carrera.objects.create(institucion=inst, nombre='S', codigo='S')
        malla = Malla.objects.create(carrera=carrera, nombre='M', codigo='M')
        nivel = NivelMalla.objects.create(malla=malla, numero=1, nombre='N')
        materia = Materia.objects.create(institucion=inst, codigo='C8', nombre='Caso 8')
        mm = MateriaMalla.objects.create(malla=malla, nivel=nivel, materia=materia)
        sim = Simulacion.objects.create(materia_malla=mm, profesor=est, titulo='S8')
        intento = IntentoSimulacion.objects.create(estudiante=est, simulacion=sim)
        with self.assertRaises(RuntimeError):
            evaluar_ronda_con_proveedores(intento, 'decision valida', 'justificacion suficiente para pasar validacion')


class ObjetivoMisionTests(TestCase):
    def test_progreso_objetivo(self):
        from simulador.alu_simulaciones import _progreso_objetivo
        # meta >= 85, valor 58, rango 0-100 -> avance parcial
        self.assertEqual(_progreso_objetivo('>=', 58, 85, 0, 100), 68)
        # ya cumplida
        self.assertEqual(_progreso_objetivo('>=', 90, 85, 0, 100), 100)
        # meta <= 3, valor 12, rango 0-100 -> avance parcial
        self.assertEqual(_progreso_objetivo('<=', 12, 3, 0, 100), 91)
        # <= ya cumplida
        self.assertEqual(_progreso_objetivo('<=', 2, 3, 0, 100), 100)


class ReaccionNarradaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.u = User.objects.create_user('narr', password='x')
        inst = Institucion.objects.create(nombre='UTA')
        carrera = Carrera.objects.create(institucion=inst, nombre='S', codigo='S')
        malla = Malla.objects.create(carrera=carrera, nombre='M', codigo='M')
        nivel = NivelMalla.objects.create(malla=malla, numero=1, nombre='N')
        materia = Materia.objects.create(institucion=inst, codigo='C', nombre='Caso')
        mm = MateriaMalla.objects.create(malla=malla, nivel=nivel, materia=materia)
        cls.sim = Simulacion.objects.create(materia_malla=mm, profesor=cls.u, titulo='S', maximo_decisiones=2)
        IndicadorSimulacion.objects.create(simulacion=cls.sim, codigo='defectos', nombre='Defectos', valor_inicial=15, valor_minimo=0, valor_maximo=100, direccion_optima='BAJO')
        IndicadorSimulacion.objects.create(simulacion=cls.sim, codigo='productividad', nombre='Productividad', valor_inicial=50, valor_minimo=0, valor_maximo=100, direccion_optima='ALTO')

    def _paso(self, antes, despues, puntaje, valido=True):
        it = IntentoSimulacion.objects.create(estudiante=self.u, simulacion=self.sim)
        from simulador.models import PasoSimulacion
        return PasoSimulacion.objects.create(intento=it, numero=1, es_valido=valido, situacion_presentada='s',
            decision_estudiante='d', justificacion_estudiante='j', puntaje_paso=puntaje,
            estado_antes=antes, estado_despues=despues)

    def test_narracion_positiva_menciona_mejora(self):
        from simulador.alu_simulaciones import _reaccion_narrada
        p = self._paso({'defectos': 15, 'productividad': 50}, {'defectos': 7, 'productividad': 60}, 85)
        txt = _reaccion_narrada(p, self.sim)
        self.assertIn('responde bien', txt)
        self.assertTrue('Defectos' in txt or 'Productividad' in txt)

    def test_narracion_tensa_cuando_empeora(self):
        from simulador.alu_simulaciones import _reaccion_narrada
        p = self._paso({'defectos': 7}, {'defectos': 14}, 25)
        txt = _reaccion_narrada(p, self.sim)
        self.assertIn('tenso', txt)
        self.assertIn('resintió', txt)

    def test_paso_invalido_no_narra(self):
        from simulador.alu_simulaciones import _reaccion_narrada
        p = self._paso({'defectos': 15}, {'defectos': 15}, 0, valido=False)
        self.assertEqual(_reaccion_narrada(p, self.sim), '')


class EdicionMateriaSimulacionTests(TestCase):
    """El modal de editar debe mostrar la materia que ya tiene la simulacion,
    aunque quede fuera de las materias asignadas al profesor: materia_malla es
    obligatoria y con el select vacio no se puede guardar nada."""

    def setUp(self):
        self.profesor = User.objects.create_user(username='profesor_edicion', is_staff=True)
        institucion = Institucion.objects.create(nombre='Institucion edicion', usuario_creacion=self.profesor)
        carrera = Carrera.objects.create(
            institucion=institucion, nombre='Carrera edicion', codigo='CE', usuario_creacion=self.profesor)
        malla = Malla.objects.create(
            carrera=carrera, nombre='Malla edicion', codigo='ME', usuario_creacion=self.profesor)
        nivel = NivelMalla.objects.create(
            malla=malla, numero=1, nombre='Nivel 1', usuario_creacion=self.profesor)
        periodo = PeriodoAcademico.objects.create(
            institucion=institucion,
            nombre='Periodo edicion',
            fecha_inicio=date(2026, 1, 1),
            fecha_fin=date(2026, 6, 30),
            usuario_creacion=self.profesor,
        )
        asignada = Materia.objects.create(
            institucion=institucion, codigo='E1', nombre='Materia asignada', usuario_creacion=self.profesor)
        suelta = Materia.objects.create(
            institucion=institucion, codigo='E2', nombre='Materia suelta', usuario_creacion=self.profesor)
        self.mm_asignada = MateriaMalla.objects.create(
            malla=malla, nivel=nivel, materia=asignada, usuario_creacion=self.profesor)
        self.mm_suelta = MateriaMalla.objects.create(
            malla=malla, nivel=nivel, materia=suelta, usuario_creacion=self.profesor)
        ProfesorMateria.objects.create(
            profesor=self.profesor, materia_malla=self.mm_asignada, periodo=periodo,
            usuario_creacion=self.profesor)
        # El profesor es dueño de la simulacion, pero no esta asignado a su materia.
        self.simulacion = Simulacion.objects.create(
            materia_malla=self.mm_suelta,
            profesor=self.profesor,
            tipo_simulacion=Simulacion.TIPO_CON_IA_DINAMICA,
            titulo='Sim de materia suelta',
            contexto='Contexto',
            objetivo='Objetivo',
            resultado_aprendizaje='Resultado',
            situacion_inicial='Situacion inicial',
            instrucciones_ia='Evaluar',
            usuario_creacion=self.profesor,
        )
        self.client = Client()
        self.client.force_login(self.profesor)

    def test_modal_editar_preselecciona_la_materia_actual(self):
        respuesta = self.client.get(
            f'/simulador/pro_simulaciones?action=edit&id={self.simulacion.pk}',
            headers={'x-requested-with': 'XMLHttpRequest'},
        )
        self.assertEqual(respuesta.status_code, 200)
        html = respuesta.content.decode()
        self.assertIn(f'value="{self.mm_suelta.pk}" selected', html)

    def test_guardar_conserva_la_materia_actual(self):
        respuesta = self.client.post('/simulador/pro_simulaciones', {
            'action': 'edit',
            'id': self.simulacion.pk,
            'materia_malla': self.mm_suelta.pk,
            'tipo_simulacion': Simulacion.TIPO_CON_IA_DINAMICA,
            'titulo': 'Titulo editado',
            'tema': 'Tema',
            'nivel_dificultad': self.simulacion.nivel_dificultad,
            'maximo_decisiones': self.simulacion.maximo_decisiones,
            'tiempo_estimado': self.simulacion.tiempo_estimado,
            'peso_rubrica_decision': self.simulacion.peso_rubrica_decision,
            'bonus_pronostico': self.simulacion.bonus_pronostico,
            'bonus_reflexion': self.simulacion.bonus_reflexion,
            'bonus_adaptacion': self.simulacion.bonus_adaptacion,
            'rol_estudiante': 'Analista',
            'contexto': 'Contexto',
            'objetivo': 'Objetivo',
            'situacion_inicial': 'Situacion inicial',
        }, headers={'x-requested-with': 'XMLHttpRequest'})
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.json()['result'], respuesta.json())
        self.simulacion.refresh_from_db()
        self.assertEqual(self.simulacion.titulo, 'Titulo editado')
        self.assertEqual(self.simulacion.materia_malla_id, self.mm_suelta.pk)


class RubricaDecisionTests(TestCase):
    """Metodo del caso: la nota no depende solo de que conceptos del temario
    menciono el estudiante, sino de como decide. Es transversal a todos los
    casos, asi que el docente no tiene que escribirla."""

    def setUp(self):
        from simulador.services import CRITERIOS_DECISION
        self.claves = [c['clave'] for c in CRITERIOS_DECISION]
        usuario = User.objects.create_user(username='profesor_rubrica')
        institucion = Institucion.objects.create(nombre='UTA', usuario_creacion=usuario)
        carrera = Carrera.objects.create(institucion=institucion, nombre='C', codigo='C1', usuario_creacion=usuario)
        malla = Malla.objects.create(carrera=carrera, nombre='M', codigo='M1', usuario_creacion=usuario)
        nivel = NivelMalla.objects.create(malla=malla, numero=1, nombre='N1', usuario_creacion=usuario)
        materia = Materia.objects.create(institucion=institucion, codigo='X1', nombre='X', usuario_creacion=usuario)
        mm = MateriaMalla.objects.create(malla=malla, nivel=nivel, materia=materia, usuario_creacion=usuario)
        self.sim = Simulacion.objects.create(
            materia_malla=mm, profesor=usuario, tipo_simulacion=Simulacion.TIPO_CON_IA_DINAMICA,
            titulo='Caso', contexto='c', objetivo='o', resultado_aprendizaje='r',
            situacion_inicial='s', instrucciones_ia='i', peso_rubrica_decision=30,
            usuario_creacion=usuario,
        )
        ConceptoEsperadoRonda.objects.create(
            simulacion=self.sim, numero_ronda=1, nombre='Concepto del temario',
            peso=100, palabras_clave={'any': ['palabra_que_no_dira']}, usuario_creacion=usuario,
        )

    def _juicios(self, cumplidos):
        return [{'clave': c, 'cumple': c in cumplidos, 'evidencia': '', 'retroalimentacion': ''}
                for c in self.claves]

    def test_los_cuatro_criterios_suman_cien(self):
        from simulador.services import evaluar_rubrica_decision
        self.assertEqual(evaluar_rubrica_decision(self._juicios(self.claves))['puntaje'], 100)
        self.assertEqual(evaluar_rubrica_decision(self._juicios([]))['puntaje'], 0)
        self.assertEqual(evaluar_rubrica_decision(self._juicios(self.claves[:2]))['puntaje'], 50)

    def test_sin_juicios_de_la_ia_no_se_aplica(self):
        """La rubrica local por palabras clave no sabe juzgar como decide alguien,
        asi que sin IA el comportamiento anterior queda intacto."""
        from simulador.services import evaluar_rubrica_decision
        self.assertIsNone(evaluar_rubrica_decision([]))
        self.assertIsNone(evaluar_rubrica_decision(None))

    def test_una_buena_decision_ya_no_saca_cero_sin_las_palabras(self):
        from simulador.services import evaluar_conceptos_esperados
        texto = 'Decido consolidar envios porque el servicio esta en 88%, acepto mas costo unitario '
        sin_rubrica = evaluar_conceptos_esperados(
            self.sim, 1, texto, texto, 'situacion', evaluaciones_ia=[], evaluaciones_decision=[])
        con_rubrica = evaluar_conceptos_esperados(
            self.sim, 1, texto, texto, 'situacion', evaluaciones_ia=[],
            evaluaciones_decision=self._juicios(self.claves))

        self.assertEqual(sin_rubrica['puntaje_sugerido'], 0)
        self.assertEqual(con_rubrica['puntaje_sugerido'], 30)
        self.assertEqual(con_rubrica['puntaje_decision'], 100)
        self.assertEqual(con_rubrica['peso_decision'], 30)

    def test_una_decision_vaga_sigue_en_cero(self):
        from simulador.services import evaluar_conceptos_esperados
        texto = 'Hay que mejorar todo.'
        resultado = evaluar_conceptos_esperados(
            self.sim, 1, texto, texto, 'situacion', evaluaciones_ia=[],
            evaluaciones_decision=self._juicios([]))
        self.assertEqual(resultado['puntaje_sugerido'], 0)

    def test_el_peso_es_configurable_por_caso(self):
        from simulador.services import evaluar_conceptos_esperados
        texto = 'Decido algo concreto.'
        for peso, esperado in ((0, 0), (50, 50), (100, 100)):
            with self.subTest(peso=peso):
                self.sim.peso_rubrica_decision = peso
                resultado = evaluar_conceptos_esperados(
                    self.sim, 1, texto, texto, 'situacion', evaluaciones_ia=[],
                    evaluaciones_decision=self._juicios(self.claves))
                self.assertEqual(resultado['puntaje_sugerido'], esperado)


class BonificacionesProcesoTests(TestCase):
    """La nota no premia solo acertar: tambien pronosticar antes de decidir,
    reflexionar despues y corregir el rumbo entre rondas. Son bonificaciones y
    no pesos porque esos campos son opcionales para el estudiante."""

    def setUp(self):
        usuario = User.objects.create_user(username='alumno_bonos')
        institucion = Institucion.objects.create(nombre='UTA', usuario_creacion=usuario)
        carrera = Carrera.objects.create(institucion=institucion, nombre='C', codigo='CB', usuario_creacion=usuario)
        malla = Malla.objects.create(carrera=carrera, nombre='M', codigo='MB', usuario_creacion=usuario)
        nivel = NivelMalla.objects.create(malla=malla, numero=1, nombre='N', usuario_creacion=usuario)
        materia = Materia.objects.create(institucion=institucion, codigo='B1', nombre='B', usuario_creacion=usuario)
        mm = MateriaMalla.objects.create(malla=malla, nivel=nivel, materia=materia, usuario_creacion=usuario)
        self.sim = Simulacion.objects.create(
            materia_malla=mm, profesor=usuario, tipo_simulacion=Simulacion.TIPO_CON_IA_DINAMICA,
            titulo='Caso bonos', contexto='c', objetivo='o', resultado_aprendizaje='r',
            situacion_inicial='s', instrucciones_ia='i', usuario_creacion=usuario,
            bonus_pronostico=8, bonus_reflexion=6, bonus_adaptacion=6,
        )
        self.intento = IntentoSimulacion.objects.create(
            estudiante=usuario, simulacion=self.sim, usuario_creacion=usuario)

    def _paso(self, numero, puntaje, pronostico=None, reflexion=''):
        return PasoSimulacion.objects.create(
            intento=self.intento, numero=numero, es_valido=True, puntaje_paso=puntaje,
            decision_estudiante='d', justificacion_estudiante='j',
            pronostico_resultado={'estado': pronostico} if pronostico else {},
            reflexion=reflexion, usuario_creacion=self.intento.estudiante,
        )

    def test_sin_proceso_no_hay_bonificacion(self):
        from simulador.services import calcular_bonificaciones, calcular_puntaje_final
        self._paso(1, 60)
        self._paso(2, 60)
        self.assertEqual(calcular_bonificaciones(self.intento)['total'], 0)
        self.assertEqual(calcular_puntaje_final(self.intento), 60)

    def test_el_proceso_completo_suma_los_veinte_puntos(self):
        from simulador.services import calcular_bonificaciones, calcular_puntaje_final
        self._paso(1, 50, pronostico='acierto', reflexion='Aprendi que...')
        self._paso(2, 60, pronostico='acierto', reflexion='Ahora entiendo...')
        bonos = calcular_bonificaciones(self.intento)
        self.assertEqual(bonos['total'], 20)
        self.assertEqual(calcular_puntaje_final(self.intento), 75)  # 55 de base + 20

    def test_las_bonificaciones_son_proporcionales(self):
        from simulador.services import calcular_bonificaciones
        self._paso(1, 60, pronostico='acierto', reflexion='algo')
        self._paso(2, 50, pronostico='diferencia')
        detalle = {b['clave']: b['puntos'] for b in calcular_bonificaciones(self.intento)['detalle']}
        self.assertEqual(detalle['pronostico'], 4)   # 1 acierto de 2 pronosticos
        self.assertEqual(detalle['reflexion'], 3)    # 1 reflexion de 2 pasos
        self.assertEqual(detalle['adaptacion'], 0)   # empeoro

    def test_nunca_pasa_de_cien(self):
        from simulador.services import calcular_puntaje_final
        self._paso(1, 98, pronostico='acierto', reflexion='x')
        self._paso(2, 100, pronostico='acierto', reflexion='y')
        self.assertEqual(calcular_puntaje_final(self.intento), 100)

    def test_el_docente_puede_desactivarlas(self):
        from simulador.services import calcular_bonificaciones
        Simulacion.objects.filter(pk=self.sim.pk).update(
            bonus_pronostico=0, bonus_reflexion=0, bonus_adaptacion=0)
        self.intento.simulacion.refresh_from_db()
        self._paso(1, 50, pronostico='acierto', reflexion='algo')
        self._paso(2, 90, pronostico='acierto', reflexion='algo')
        self.assertEqual(calcular_bonificaciones(self.intento)['total'], 0)


class InvestigacionConPresupuestoTests(TestCase):
    """Informacion oculta que se compra: es lo que convierte "elegir entre
    alternativas parecidas" en una decision real, porque el presupuesto no
    alcanza para averiguarlo todo."""

    def setUp(self):
        from simulador.models import InvestigacionSimulacion, RecursoSimulacion
        usuario = User.objects.create_user(username='prof_inv')
        self.alumno = User.objects.create_user(username='alu_inv')
        institucion = Institucion.objects.create(nombre='UTA', usuario_creacion=usuario)
        carrera = Carrera.objects.create(institucion=institucion, nombre='C', codigo='CI', usuario_creacion=usuario)
        malla = Malla.objects.create(carrera=carrera, nombre='M', codigo='MI', usuario_creacion=usuario)
        nivel = NivelMalla.objects.create(malla=malla, numero=1, nombre='N', usuario_creacion=usuario)
        materia = Materia.objects.create(institucion=institucion, codigo='I1', nombre='I', usuario_creacion=usuario)
        mm = MateriaMalla.objects.create(malla=malla, nivel=nivel, materia=materia, usuario_creacion=usuario)
        self.sim = Simulacion.objects.create(
            materia_malla=mm, profesor=usuario, tipo_simulacion=Simulacion.TIPO_CON_IA_DINAMICA,
            titulo='Seleccion', contexto='c', objetivo='o', resultado_aprendizaje='r',
            situacion_inicial='s', instrucciones_ia='i', estado=Simulacion.PUBLICADA,
            usuario_creacion=usuario,
        )
        RecursoSimulacion.objects.create(
            simulacion=self.sim, codigo='presupuesto', nombre='Presupuesto',
            valor_inicial=100, valor_minimo=0, valor_maximo=100, usuario_creacion=usuario)
        self.barata = InvestigacionSimulacion.objects.create(
            simulacion=self.sim, sujeto='Candidato A', nombre='Entrevista',
            hallazgo='Culpa a sus companeros de todo.',
            costo_recursos={'presupuesto': 40}, usuario_creacion=usuario)
        self.cara = InvestigacionSimulacion.objects.create(
            simulacion=self.sim, sujeto='Todos', nombre='Assessment center',
            hallazgo='B lidera el grupo con naturalidad.',
            costo_recursos={'presupuesto': 90}, usuario_creacion=usuario)
        self.tardia = InvestigacionSimulacion.objects.create(
            simulacion=self.sim, sujeto='Candidato B', nombre='Segunda entrevista',
            hallazgo='Confirma su interes.', costo_recursos={'presupuesto': 10},
            disponible_desde_ronda=3, usuario_creacion=usuario)
        self.intento = IntentoSimulacion.objects.create(
            estudiante=self.alumno, simulacion=self.sim,
            recursos_actuales={'presupuesto': 100.0}, usuario_creacion=self.alumno)

    def test_el_hallazgo_esta_oculto_hasta_que_se_paga(self):
        from simulador.services import investigaciones_disponibles
        antes = {i['nombre']: i for i in investigaciones_disponibles(self.intento)}
        self.assertEqual(antes['Entrevista']['hallazgo'], '')
        self.assertFalse(antes['Entrevista']['pagada'])

    def test_comprar_cobra_y_revela(self):
        from simulador.services import comprar_investigacion
        resultado = comprar_investigacion(self.intento, self.barata)
        self.assertTrue(resultado['ok'])
        self.assertIn('Culpa a sus companeros', resultado['hallazgo'])
        self.intento.refresh_from_db()
        self.assertEqual(self.intento.recursos_actuales['presupuesto'], 60)
        self.assertEqual(self.intento.investigaciones_compradas, [self.barata.id])

    def test_no_se_cobra_dos_veces(self):
        from simulador.services import comprar_investigacion
        comprar_investigacion(self.intento, self.barata)
        repetida = comprar_investigacion(self.intento, self.barata)
        self.assertFalse(repetida['ok'])
        self.intento.refresh_from_db()
        self.assertEqual(self.intento.recursos_actuales['presupuesto'], 60)

    def test_el_presupuesto_obliga_a_elegir(self):
        """Con 100 no alcanza para las dos: hay que decidir cual conviene mas."""
        from simulador.services import comprar_investigacion
        self.assertTrue(comprar_investigacion(self.intento, self.barata)['ok'])
        segunda = comprar_investigacion(self.intento, self.cara)
        self.assertFalse(segunda['ok'])
        self.assertIn('alcanza', segunda['mensaje'])
        self.assertEqual(segunda['hallazgo'], '')

    def test_las_de_rondas_futuras_no_aparecen_todavia(self):
        from simulador.services import investigaciones_disponibles
        nombres = [i['nombre'] for i in investigaciones_disponibles(self.intento)]
        self.assertNotIn('Segunda entrevista', nombres)
        self.intento.numero_ronda_actual = 3
        self.assertIn('Segunda entrevista', [i['nombre'] for i in investigaciones_disponibles(self.intento)])

    def test_la_ia_recibe_solo_lo_que_el_estudiante_pago(self):
        from simulador.services import comprar_investigacion, hallazgos_conocidos
        self.assertEqual(hallazgos_conocidos(self.intento), [])
        comprar_investigacion(self.intento, self.barata)
        conocidos = hallazgos_conocidos(self.intento)
        self.assertEqual(len(conocidos), 1)
        self.assertEqual(conocidos[0]['sujeto'], 'Candidato A')

    def test_el_estudiante_no_puede_investigar_en_un_intento_ajeno(self):
        otro = User.objects.create_user(username='otro_alu')
        client = Client()
        client.force_login(otro)
        respuesta = client.post('/simulador/alu_simulaciones', {
            'action': 'investigar', 'intento_id': self.intento.pk,
            'investigacion_id': self.barata.pk,
        }, headers={'x-requested-with': 'XMLHttpRequest'})
        self.assertEqual(respuesta.status_code, 404)
        self.intento.refresh_from_db()
        self.assertEqual(self.intento.investigaciones_compradas, [])


class GeneracionInvestigacionesTests(TestCase):
    """El mecanismo solo funciona si el presupuesto NO alcanza para todas. Eso no
    puede quedar a criterio de la IA: se garantiza reescalando los costos."""

    def setUp(self):
        usuario = User.objects.create_user(username='prof_gen')
        institucion = Institucion.objects.create(nombre='UTA', usuario_creacion=usuario)
        carrera = Carrera.objects.create(institucion=institucion, nombre='C', codigo='CG', usuario_creacion=usuario)
        malla = Malla.objects.create(carrera=carrera, nombre='M', codigo='MG', usuario_creacion=usuario)
        nivel = NivelMalla.objects.create(malla=malla, numero=1, nombre='N', usuario_creacion=usuario)
        materia = Materia.objects.create(institucion=institucion, codigo='G1', nombre='G', usuario_creacion=usuario)
        mm = MateriaMalla.objects.create(malla=malla, nivel=nivel, materia=materia, usuario_creacion=usuario)
        self.sim = Simulacion.objects.create(
            materia_malla=mm, profesor=usuario, tipo_simulacion=Simulacion.TIPO_CON_IA_DINAMICA,
            titulo='Caso gen', contexto='c', objetivo='o', resultado_aprendizaje='r',
            situacion_inicial='s', instrucciones_ia='i', estado=Simulacion.PUBLICADA,
            usuario_creacion=usuario,
        )

    def _generar(self, items):
        from unittest.mock import patch
        from django.core.management import call_command
        with patch('simulador.management.commands.generar_investigaciones.generar_investigaciones_ia',
                   return_value=items):
            call_command('generar_investigaciones', simulacion=self.sim.pk, presupuesto=100, verbosity=0)

    def _items(self, costos):
        return [{'sujeto': f'S{n}', 'nombre': f'Prueba {n}', 'descripcion': 'd',
                 'hallazgo': f'Hallazgo {n}', 'costo': c} for n, c in enumerate(costos, start=1)]

    def test_si_la_ia_cobra_de_menos_igual_no_alcanza(self):
        from simulador.models import InvestigacionSimulacion
        self._generar(self._items([5, 5, 5, 5, 5]))  # 25 en total, con presupuesto 100
        total = sum(list(i.costo_recursos.values())[0]
                    for i in InvestigacionSimulacion.objects.filter(simulacion=self.sim))
        self.assertGreater(total, 100, 'el presupuesto no debe alcanzar para todas')
        self.assertAlmostEqual(total, 250, delta=25)

    def test_si_la_ia_cobra_de_mas_tampoco_se_dispara(self):
        from simulador.models import InvestigacionSimulacion
        self._generar(self._items([900, 800, 700, 600]))
        total = sum(list(i.costo_recursos.values())[0]
                    for i in InvestigacionSimulacion.objects.filter(simulacion=self.sim))
        self.assertAlmostEqual(total, 250, delta=25)

    def test_se_crea_el_presupuesto_si_el_caso_no_tenia(self):
        from simulador.models import RecursoSimulacion
        self._generar(self._items([10, 20, 30, 40]))
        recurso = RecursoSimulacion.objects.get(simulacion=self.sim, codigo='presupuesto_investigacion')
        self.assertEqual(float(recurso.valor_inicial), 100)

    def test_descarta_las_que_vienen_incompletas(self):
        from simulador.models import InvestigacionSimulacion
        items = self._items([10, 20, 30, 40])
        items[0]['hallazgo'] = ''
        items[1]['nombre'] = ''
        self._generar(items)
        self.assertEqual(InvestigacionSimulacion.objects.filter(simulacion=self.sim).count(), 2)


class EditorDeRondasTests(TestCase):
    """El modo de cada ronda (elegir / escribir / ambas) ya lo entendia el motor,
    pero solo se podia cambiar editando JSON a mano. Ahora se configura."""

    def setUp(self):
        self.profesor = User.objects.create_user(username='prof_rondas', is_staff=True)
        institucion = Institucion.objects.create(nombre='UTA', usuario_creacion=self.profesor)
        carrera = Carrera.objects.create(institucion=institucion, nombre='C', codigo='CR', usuario_creacion=self.profesor)
        malla = Malla.objects.create(carrera=carrera, nombre='M', codigo='MR', usuario_creacion=self.profesor)
        nivel = NivelMalla.objects.create(malla=malla, numero=1, nombre='N', usuario_creacion=self.profesor)
        materia = Materia.objects.create(institucion=institucion, codigo='R1', nombre='R', usuario_creacion=self.profesor)
        mm = MateriaMalla.objects.create(malla=malla, nivel=nivel, materia=materia, usuario_creacion=self.profesor)
        self.sim = Simulacion.objects.create(
            materia_malla=mm, profesor=self.profesor, tipo_simulacion=Simulacion.TIPO_CON_IA_DINAMICA,
            titulo='Caso rondas', contexto='c', objetivo='o', resultado_aprendizaje='r',
            situacion_inicial='s', instrucciones_ia='i', maximo_decisiones=3,
            usuario_creacion=self.profesor,
        )
        AccionSugeridaSimulacion.objects.create(
            simulacion=self.sim, texto='Opcion A', descripcion='d', usuario_creacion=self.profesor)
        self.client = Client()
        self.client.force_login(self.profesor)
        self.url = '/simulador/pro_simulaciones'

    def _guardar(self, modos, etiquetas=None):
        datos = {'action': 'guardar_rondas', 'id': self.sim.pk}
        for numero, modo in modos.items():
            datos[f'modo_{numero}'] = modo
            datos[f'etiqueta_decision_{numero}'] = (etiquetas or {}).get(numero, '')
            datos[f'etiqueta_justificacion_{numero}'] = ''
        return self.client.post(self.url, datos, headers={'x-requested-with': 'XMLHttpRequest'})

    def test_el_profesor_define_el_modo_de_cada_ronda(self):
        from simulador.alu_simulaciones import _modo_ronda
        respuesta = self._guardar({1: 'escribir', 2: 'elegir', 3: 'hibrido'})
        self.assertTrue(respuesta.json()['result'], respuesta.json())
        self.sim.refresh_from_db()
        self.assertEqual(_modo_ronda(self.sim, 1, True), 'escribir')
        self.assertEqual(_modo_ronda(self.sim, 2, True), 'elegir')
        self.assertEqual(_modo_ronda(self.sim, 3, True), 'hibrido')

    def test_las_etiquetas_llegan_a_la_consola_del_alumno(self):
        from simulador.alu_simulaciones import _etiquetas_ronda
        self._guardar({1: 'escribir', 2: 'elegir', 3: 'hibrido'},
                      etiquetas={1: 'Diagnostico de costos'})
        self.sim.refresh_from_db()
        self.assertEqual(_etiquetas_ronda(self.sim, 1)[0], 'Diagnostico de costos')

    def test_sin_opciones_configuradas_elegir_cae_a_escribir(self):
        """No se le puede pedir que elija si no hay entre que elegir."""
        from simulador.alu_simulaciones import _modo_ronda
        AccionSugeridaSimulacion.objects.filter(simulacion=self.sim).update(activo=False)
        self._guardar({1: 'elegir', 2: 'elegir', 3: 'elegir'})
        self.sim.refresh_from_db()
        self.assertEqual(_modo_ronda(self.sim, 1, False), 'escribir')

    def test_un_modo_invalido_cae_al_por_defecto(self):
        from simulador.alu_simulaciones import _modo_ronda
        self._guardar({1: 'cualquier_cosa', 2: 'hibrido', 3: 'hibrido'})
        self.sim.refresh_from_db()
        self.assertEqual(_modo_ronda(self.sim, 1, True), 'hibrido')

    def test_no_pisa_lo_que_puso_el_generador(self):
        """opciones_decision y situacion las escribe el generador de casos:
        el editor de rondas no debe borrarlas."""
        self.sim.parametros = {'rondas': [
            {'situacion': 'La planta esta parada', 'opciones_decision': ['A', 'B'], 'modo': 'hibrido'},
            {}, {},
        ]}
        self.sim.save(update_fields=['parametros'])
        self._guardar({1: 'escribir', 2: 'hibrido', 3: 'hibrido'})
        self.sim.refresh_from_db()
        ronda = self.sim.parametros['rondas'][0]
        self.assertEqual(ronda['modo'], 'escribir')
        self.assertEqual(ronda['situacion'], 'La planta esta parada')
        self.assertEqual(ronda['opciones_decision'], ['A', 'B'])

    def test_la_pantalla_lista_una_tarjeta_por_ronda(self):
        respuesta = self.client.get(self.url, {'action': 'rondas', 'id': self.sim.pk})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(respuesta.context['rondas']), 3)

    def test_admite_un_recorrido_con_titulos_y_controles_propios(self):
        datos = {'action': 'guardar_rondas', 'id': self.sim.pk}
        titulos = ['Comparar escenarios', 'Responder a la crisis', 'Reasignar recursos']
        for numero, titulo in enumerate(titulos, 1):
            datos.update({
                f'titulo_{numero}': titulo,
                f'proposito_{numero}': f'Aprendizaje {numero}',
                f'situacion_{numero}': f'Dato nuevo {numero}',
                f'modo_{numero}': 'hibrido' if numero != 2 else 'elegir',
                f'etiqueta_decision_{numero}': 'Alternativa seleccionada',
                f'etiqueta_justificacion_{numero}': 'Evidencia utilizada',
                f'mostrar_datos_caso_{numero}': 'on',
                f'mostrar_indicadores_{numero}': 'on',
            })
        respuesta = self.client.post(
            self.url, datos, headers={'x-requested-with': 'XMLHttpRequest'},
        )
        self.assertTrue(respuesta.json()['result'], respuesta.json())
        self.sim.refresh_from_db()
        rondas = self.sim.parametros['rondas']
        self.assertEqual([r['titulo'] for r in rondas], titulos)
        self.assertEqual(rondas[1]['modo'], 'elegir')
        self.assertFalse(rondas[1]['pedir_reflexion'])

        from simulador.alu_simulaciones import _pasos_stepper
        self.assertEqual(
            [p['nombre'] for p in _pasos_stepper(self.sim, 1)], titulos,
        )

    def test_las_etiquetas_del_caso_son_neutrales_o_especificas(self):
        from simulador.alu_simulaciones import _datos_visibles_caso
        self.sim.parametros = {
            'candidatos': [{'nombre': 'Opción histórica', 'salario_pretendido': '$10'}],
        }
        self.sim.save(update_fields=['parametros'])
        datos = _datos_visibles_caso(self.sim)
        self.assertEqual(datos['caso_labels']['alternativa_col'], 'Alternativa')
        self.assertEqual(datos['caso_labels']['valor_col'], 'Valor')
        self.assertEqual(datos['alternativas_caso'][0]['valor'], '$10')

        self.sim.parametros['caso_labels'] = {
            'alternativas_titulo': 'Cotizaciones recibidas',
            'alternativa_col': 'Proveedor',
            'valor_col': 'Costo total',
        }
        self.sim.save(update_fields=['parametros'])
        datos = _datos_visibles_caso(self.sim)
        self.assertEqual(datos['caso_labels']['alternativa_col'], 'Proveedor')
        self.assertEqual(datos['caso_labels']['valor_col'], 'Costo total')

    def test_el_formulario_de_alternativas_permite_asignarlas_por_ronda(self):
        from simulador.forms import AccionSugeridaForm
        self.sim.parametros = {'rondas': [
            {'numero': 1, 'titulo': 'Comparar ofertas'},
            {'numero': 2, 'titulo': 'Negociar condiciones'},
            {'numero': 3, 'titulo': 'Responder al retraso'},
        ]}
        self.sim.save(update_fields=['parametros'])
        form = AccionSugeridaForm(simulacion_obj=self.sim)
        etiquetas = dict(form.fields['numero_ronda'].choices)
        self.assertIn('Comparar ofertas', etiquetas[1])
        self.assertIn('Responder al retraso', etiquetas[3])

    def test_la_cantidad_de_rondas_no_tiene_un_tres_heredado(self):
        nueva = Simulacion.objects.create(
            materia_malla=self.sim.materia_malla,
            profesor=self.profesor,
            titulo='Caso de una sola decisión',
        )
        self.assertEqual(nueva.maximo_decisiones, 1)

        from simulador.pro_simulaciones import _sincronizar_cantidad_rondas
        nueva.maximo_decisiones = 7
        nueva.save(update_fields=['maximo_decisiones'])
        _sincronizar_cantidad_rondas(nueva, 1)
        nueva.refresh_from_db()
        self.assertEqual(len(nueva.parametros['rondas']), 7)
        self.assertEqual(nueva.parametros['rondas'][-1]['titulo'], 'Ronda 7')

    def test_reducir_rondas_no_deja_configuracion_fantasma(self):
        from simulador.models import EventoSimulacion
        from simulador.pro_simulaciones import _sincronizar_cantidad_rondas

        accion = AccionSugeridaSimulacion.objects.create(
            simulacion=self.sim, numero_ronda=3, texto='Opción final',
            usuario_creacion=self.profesor,
        )
        concepto = ConceptoEsperadoRonda.objects.create(
            simulacion=self.sim, numero_ronda=3, nombre='Control final',
            palabras_clave='control', peso=100, usuario_creacion=self.profesor,
        )
        evento = EventoSimulacion.objects.create(
            simulacion=self.sim, ronda=3, nombre='Cambio final', mensaje='Dato nuevo',
            usuario_creacion=self.profesor,
        )
        self.sim.maximo_decisiones = 1
        self.sim.save(update_fields=['maximo_decisiones'])
        _sincronizar_cantidad_rondas(self.sim, 3)

        self.sim.refresh_from_db()
        accion.refresh_from_db()
        concepto.refresh_from_db()
        evento.refresh_from_db()
        self.assertEqual(len(self.sim.parametros['rondas']), 1)
        self.assertFalse(accion.activo)
        self.assertFalse(concepto.activo)
        self.assertFalse(evento.activo)

    def test_el_docente_cambia_la_cantidad_desde_el_editor_de_rondas(self):
        respuesta = self.client.post(self.url, {
            'action': 'cambiar_cantidad_rondas',
            'id': self.sim.pk,
            'cantidad_rondas': 5,
        }, headers={'x-requested-with': 'XMLHttpRequest'})
        self.assertTrue(respuesta.json()['result'], respuesta.json())
        self.sim.refresh_from_db()
        self.assertEqual(self.sim.maximo_decisiones, 5)
        self.assertEqual(len(self.sim.parametros['rondas']), 5)

        invalida = self.client.post(self.url, {
            'action': 'cambiar_cantidad_rondas',
            'id': self.sim.pk,
            'cantidad_rondas': 0,
        }, headers={'x-requested-with': 'XMLHttpRequest'})
        self.assertFalse(invalida.json()['result'])

    def test_un_estudiante_no_puede_cambiar_las_rondas(self):
        estudiante = User.objects.create_user(username='alu_rondas')
        cliente = Client()
        cliente.force_login(estudiante)
        respuesta = cliente.post(self.url, {
            'action': 'guardar_rondas', 'id': self.sim.pk, 'modo_1': 'elegir',
        }, headers={'x-requested-with': 'XMLHttpRequest'})
        self.assertEqual(respuesta.status_code, 302)


class CalidadDeLosPromptsTests(TestCase):
    """Los prompts de generacion se editan a mano y es facil partir una frase o
    dejar un numero clavado. Estos tests vigilan lo que no se ve al leerlos."""

    def setUp(self):
        usuario = User.objects.create_user(username='prof_prompts')
        institucion = Institucion.objects.create(nombre='UTA', usuario_creacion=usuario)
        carrera = Carrera.objects.create(institucion=institucion, nombre='C', codigo='CP2', usuario_creacion=usuario)
        malla = Malla.objects.create(carrera=carrera, nombre='M', codigo='MP2', usuario_creacion=usuario)
        nivel = NivelMalla.objects.create(malla=malla, numero=1, nombre='N', usuario_creacion=usuario)
        materia = Materia.objects.create(institucion=institucion, codigo='P2', nombre='Costos', usuario_creacion=usuario)
        mm = MateriaMalla.objects.create(malla=malla, nivel=nivel, materia=materia, usuario_creacion=usuario)
        self.sim = Simulacion.objects.create(
            materia_malla=mm, profesor=usuario, tipo_simulacion=Simulacion.TIPO_CON_IA_DINAMICA,
            titulo='Caso prompts', contexto='c', objetivo='o', resultado_aprendizaje='r',
            situacion_inicial='s', instrucciones_ia='i', usuario_creacion=usuario,
        )
        self.indicadores = [{'codigo': 'tasa_cif', 'nombre': 'Tasa CIF', 'direccion_optima': 'BAJO'}]

    def test_la_regla_de_pantalla_tranquila_no_quedo_partida(self):
        """Estuvo rota: 'deja' seguido de otra instruccion, y su final tres
        oraciones despues. El modelo leia una frase sin sentido."""
        from simulador.ia_service import _prompt_generacion_caso
        texto = _prompt_generacion_caso('Costos', 1)
        inicio = texto.index('Mantén la pantalla tranquila: deja ')
        siguiente = texto[inicio:inicio + 160]
        self.assertIn('desactivados', siguiente)
        self.assertNotIn('Cada ronda debe declarar', siguiente)

    def test_datos_caso_anuncia_los_cuatro_entregables(self):
        """Anunciaba dos y pedia cuatro: condiciones y eventos salian flojos."""
        from simulador.ia_service import _prompt_datos_caso
        encabezado = _prompt_datos_caso(self.sim, self.indicadores).split('\n\n')[0]
        for pieza in ('alternativas', 'criterios', 'condiciones de exito', 'eventos'):
            self.assertIn(pieza, encabezado)

    def test_datos_caso_explica_para_que_sirve_la_direccion_optima(self):
        from simulador.ia_service import _prompt_datos_caso
        texto = _prompt_datos_caso(self.sim, self.indicadores)
        self.assertIn('CONTRA su direccion optima', texto)

    def test_las_cantidades_son_parametros_y_no_numeros_clavados(self):
        from simulador.ia_service import _prompt_datos_caso, _prompt_investigaciones
        libre = _prompt_datos_caso(self.sim, self.indicadores)
        self.assertIn('las que el caso justifique', libre)

        fijo = _prompt_datos_caso(self.sim, self.indicadores, n_alternativas=6, n_criterios=3)
        self.assertIn('exactamente 6 alternativas', fijo)
        self.assertIn('3 criterios de comparacion', fijo)
        self.assertNotIn('4 criterios de comparacion', fijo)

        inv = _prompt_investigaciones(self.sim, ['A'], 'presupuesto', 250, n_averiguaciones=5)
        self.assertIn('exactamente 5 averiguaciones', inv)

    def test_ningun_prompt_de_generacion_queda_vacio_o_truncado(self):
        from simulador.ia_service import (
            _prompt_datos_caso, _prompt_generacion_caso, _prompt_investigaciones,
        )
        textos = {
            'generacion_caso': _prompt_generacion_caso('Costos', 1),
            'datos_caso': _prompt_datos_caso(self.sim, self.indicadores),
            'investigaciones': _prompt_investigaciones(self.sim, ['A'], 'presupuesto', 250),
        }
        for nombre, texto in textos.items():
            with self.subTest(prompt=nombre):
                self.assertGreater(len(texto), 400, f'{nombre} quedo demasiado corto')
                self.assertIn('JSON', texto, f'{nombre} no pide JSON')
                # Una regla que termina en preposicion delata una frase partida
                # al insertar texto en medio, que es como se rompio la de arriba.
                for regla in texto.split('\n'):
                    self.assertFalse(
                        regla.rstrip().endswith((' deja', ' con', ' de', ' para', ' y', ' que')),
                        f'{nombre}: regla cortada -> ...{regla.rstrip()[-60:]}',
                    )


class VisibilidadDeInvestigacionesTests(TestCase):
    """Las averiguaciones existian en 7 de 8 casos pero ninguna ronda las
    mostraba: dato muerto. El interruptor arranca apagado a proposito, pero si
    el caso TIENE averiguaciones hay que encenderlo o el mecanismo no existe."""

    def setUp(self):
        from simulador.models import InvestigacionSimulacion
        usuario = User.objects.create_user(username='prof_vis')
        institucion = Institucion.objects.create(nombre='UTA', usuario_creacion=usuario)
        carrera = Carrera.objects.create(institucion=institucion, nombre='C', codigo='CV', usuario_creacion=usuario)
        malla = Malla.objects.create(carrera=carrera, nombre='M', codigo='MV', usuario_creacion=usuario)
        nivel = NivelMalla.objects.create(malla=malla, numero=1, nombre='N', usuario_creacion=usuario)
        materia = Materia.objects.create(institucion=institucion, codigo='V1', nombre='V', usuario_creacion=usuario)
        mm = MateriaMalla.objects.create(malla=malla, nivel=nivel, materia=materia, usuario_creacion=usuario)
        self.sim = Simulacion.objects.create(
            materia_malla=mm, profesor=usuario, tipo_simulacion=Simulacion.TIPO_CON_IA_DINAMICA,
            titulo='Caso visible', contexto='c', objetivo='o', resultado_aprendizaje='r',
            situacion_inicial='s', instrucciones_ia='i', estado=Simulacion.PUBLICADA,
            maximo_decisiones=3, usuario_creacion=usuario,
        )
        InvestigacionSimulacion.objects.create(
            simulacion=self.sim, sujeto='A', nombre='Prueba', hallazgo='dato oculto',
            costo_recursos={'presupuesto': 10}, disponible_desde_ronda=2, usuario_creacion=usuario)

    def _reparar(self):
        from django.core.management import call_command
        call_command('generar_investigaciones', solo_visibilidad=True,
                     simulacion=self.sim.pk, verbosity=0)
        self.sim.refresh_from_db()
        return (self.sim.parametros or {}).get('rondas') or []

    def test_se_encienden_desde_la_ronda_en_que_estan_disponibles(self):
        rondas = self._reparar()
        self.assertFalse(rondas[0].get('mostrar_investigaciones'), 'la ronda 1 no las tiene disponibles')
        self.assertTrue(rondas[1].get('mostrar_investigaciones'))
        self.assertTrue(rondas[2].get('mostrar_investigaciones'))

    def test_es_idempotente(self):
        self._reparar()
        antes = (self.sim.parametros or {}).get('rondas')
        self._reparar()
        self.assertEqual((self.sim.parametros or {}).get('rondas'), antes)

    def test_no_toca_las_otras_claves_de_la_ronda(self):
        self.sim.parametros = {'rondas': [
            {'modo': 'escribir', 'situacion': 'algo'}, {'modo': 'elegir'}, {},
        ]}
        self.sim.save(update_fields=['parametros'])
        rondas = self._reparar()
        self.assertEqual(rondas[0]['modo'], 'escribir')
        self.assertEqual(rondas[0]['situacion'], 'algo')
        self.assertEqual(rondas[1]['modo'], 'elegir')

    def test_un_caso_sin_averiguaciones_no_se_toca(self):
        from simulador.models import InvestigacionSimulacion
        InvestigacionSimulacion.objects.filter(simulacion=self.sim).update(activo=False)
        self.sim.parametros = {}
        self.sim.save(update_fields=['parametros'])
        self._reparar()
        self.assertFalse((self.sim.parametros or {}).get('rondas'))
