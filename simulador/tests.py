from django.contrib.auth.models import User
from django.test import Client, TestCase
from datetime import date

from academico.models import Carrera, Malla, Materia, MateriaMalla, NivelMalla, PeriodoAcademico, ProfesorMateria
from core.models import Institucion
from simulador.models import (
    AccionSugeridaSimulacion,
    ConceptoEsperadoRonda,
    EventoSimulacion,
    IndicadorSimulacion,
    IntentoSimulacion,
    RecursoSimulacion,
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
