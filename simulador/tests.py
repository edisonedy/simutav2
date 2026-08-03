from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.utils import timezone
from datetime import date

from academico.models import Carrera, Malla, Materia, MateriaMalla, NivelMalla, PeriodoAcademico, ProfesorMateria
from core.models import Institucion
from simulador.models import (
    AccionSugeridaSimulacion,
    ConceptoEsperadoRonda,
    DecisionConfigurada,
    EscenarioSimulacion,
    EventoSimulacion,
    IndicadorSimulacion,
    IntentoSimulacion,
    PasoSimulacion,
    RecursoSimulacion,
    ResultadoAprendizaje,
    RetoRefuerzo,
    Simulacion,
)
from simulador.generator_service import generar_simulacion_desde_plantilla
from simulador.services import (
    TIPO_ERROR_BASURA,
    TIPO_ERROR_GENERICA,
    TIPO_ERROR_OK,
    TIPO_ERROR_VACIA,
    _normalizar_texto,
    aplicar_costo_recursos,
    aplicar_eventos,
    calcular_puntaje_final,
    construir_recursos_iniciales,
    detectar_accion_sugerida,
    evaluar_pronostico,
    evaluar_tradeoff,
    evaluar_conceptos_esperados,
    validar_recursos,
    validar_respuesta_estudiante,
)


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
