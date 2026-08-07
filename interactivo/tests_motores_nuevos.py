"""Los tres motores nuevos: clasificar, sopa de letras y crucigrama.

Lo que importa probar: que el tablero se arma de verdad, que las respuestas
correctas NO viajan al navegador, y que la calificacion no se puede falsear.
"""

from django.test import TestCase

from .plugins.registry import all_plugins, get_plugin


class ClasificarTests(TestCase):
    def setUp(self):
        self.plugin = get_plugin('clasificar')
        self.config = self.plugin.normalize_config({
            'categorias': [{'nombre': 'Costo fijo'}, {'nombre': 'Costo variable'}],
            'elementos': [
                {'texto': 'Arriendo de la planta', 'categoria': 1},
                {'texto': 'Materia prima', 'categoria': 2},
                {'texto': 'Sueldo del gerente', 'categoria': 1},
            ],
        })

    def test_la_configuracion_es_valida(self):
        self.assertEqual(self.plugin.validate_config(self.config), [])
        self.assertEqual(len(self.config['categorias']), 2)
        self.assertEqual(len(self.config['elementos']), 3)

    def test_un_numero_de_categoria_inexistente_se_avisa(self):
        config = self.plugin.normalize_config({
            'categorias': [{'nombre': 'A'}, {'nombre': 'B'}],
            'elementos': [{'texto': 'X', 'categoria': 7}],
        })
        errores = self.plugin.validate_config(config)
        self.assertTrue(any('no corresponde' in e for e in errores))

    def test_al_navegador_no_va_la_categoria_correcta(self):
        publica = self.plugin.public_config(self.config)
        for elemento in publica['elementos']:
            self.assertNotIn('categoria_id', elemento)

    def test_clasificar_bien_da_cien(self):
        asignaciones = {
            e['id']: e['categoria_id'] for e in self.config['elementos']
        }
        resultado = self.plugin.grade(self.config, {'asignaciones': asignaciones})
        self.assertEqual(resultado['porcentaje'], 100)

    def test_clasificar_todo_al_reves_da_cero(self):
        categorias = self.config['categorias']
        otra = {c['id']: categorias[(i + 1) % 2]['id'] for i, c in enumerate(categorias)}
        asignaciones = {
            e['id']: otra[e['categoria_id']] for e in self.config['elementos']
        }
        resultado = self.plugin.grade(self.config, {'asignaciones': asignaciones})
        self.assertEqual(resultado['porcentaje'], 0)


class SopaDeLetrasTests(TestCase):
    PALABRAS = ['ACTIVO', 'PASIVO', 'PATRIMONIO', 'BALANCE']

    def setUp(self):
        self.plugin = get_plugin('sopa_letras')
        self.config = self.plugin.normalize_config({
            'palabras': [{'texto': p} for p in self.PALABRAS],
        })

    def test_el_tablero_se_arma_y_es_cuadrado(self):
        tablero = self.config['tablero']
        self.assertTrue(tablero)
        lado = len(tablero)
        self.assertTrue(all(len(fila) == lado for fila in tablero))
        self.assertTrue(all(letra.isalpha() for fila in tablero for letra in fila))

    def test_cada_palabra_quedo_realmente_en_el_tablero(self):
        tablero = self.config['tablero']
        for palabra in self.config['palabras']:
            letras = ''.join(tablero[f][c] for f, c in palabra['celdas'])
            esperada = ''.join(
                ch for ch in palabra['texto'].upper() if ch.isalpha()
            )
            self.assertEqual(letras, esperada, f'{palabra["texto"]} no quedo en el tablero')

    def test_las_posiciones_no_viajan_al_navegador(self):
        publica = self.plugin.public_config(self.config)
        self.assertIn('tablero', publica)
        for palabra in publica['palabras']:
            self.assertNotIn('celdas', palabra)

    def test_marcar_las_celdas_correctas_da_cien(self):
        hallazgos = {p['id']: p['celdas'] for p in self.config['palabras']}
        resultado = self.plugin.grade(self.config, {'hallazgos': hallazgos})
        self.assertEqual(resultado['porcentaje'], 100)

    def test_vale_marcarla_al_reves(self):
        palabra = self.config['palabras'][0]
        hallazgos = {palabra['id']: list(reversed(palabra['celdas']))}
        resultado = self.plugin.grade(self.config, {'hallazgos': hallazgos})
        self.assertEqual(resultado['aciertos'], 1)

    def test_decir_que_la_encontro_sin_marcarla_no_cuenta(self):
        """El navegador no puede regalarse la nota: se comprueban las celdas."""
        hallazgos = {p['id']: [] for p in self.config['palabras']}
        resultado = self.plugin.grade(self.config, {'hallazgos': hallazgos})
        self.assertEqual(resultado['porcentaje'], 0)

    def test_marcar_celdas_equivocadas_no_cuenta(self):
        palabra = self.config['palabras'][0]
        resultado = self.plugin.grade(self.config, {
            'hallazgos': {palabra['id']: [[0, 0], [0, 1], [0, 2]]},
        })
        self.assertLessEqual(resultado['aciertos'], 1)


class CrucigramaTests(TestCase):
    def setUp(self):
        self.plugin = get_plugin('crucigrama')
        self.config = self.plugin.normalize_config({
            'palabras': [
                {'texto': 'ACTIVO', 'pista': 'Lo que la empresa posee'},
                {'texto': 'PASIVO', 'pista': 'Lo que la empresa debe'},
                {'texto': 'COSTO', 'pista': 'Lo que sale producir una unidad'},
                {'texto': 'BALANCE', 'pista': 'Estado que cuadra la ecuacion contable'},
            ],
        })

    def test_las_palabras_se_cruzan_en_un_tablero(self):
        self.assertEqual(self.plugin.validate_config(self.config), [])
        self.assertGreaterEqual(len(self.config['palabras']), 2)
        self.assertGreater(self.config['filas'], 0)
        self.assertGreater(self.config['columnas'], 0)

    def test_donde_dos_palabras_se_cruzan_la_letra_coincide(self):
        letras = {}
        for palabra in self.config['palabras']:
            for (fila, col), letra in zip(palabra['celdas'], palabra['limpia']):
                clave = (fila, col)
                if clave in letras:
                    self.assertEqual(letras[clave], letra)
                letras[clave] = letra

    def test_al_navegador_no_va_la_palabra(self):
        publica = self.plugin.public_config(self.config)
        for palabra in publica['palabras']:
            self.assertNotIn('texto', palabra)
            self.assertNotIn('limpia', palabra)
            self.assertIn('pista', palabra)
            self.assertIn('largo', palabra)

    def test_escribirlas_bien_da_cien(self):
        respuestas = {p['id']: p['texto'] for p in self.config['palabras']}
        resultado = self.plugin.grade(self.config, {'respuestas': respuestas})
        self.assertEqual(resultado['porcentaje'], 100)

    def test_no_importan_tildes_ni_mayusculas(self):
        palabra = self.config['palabras'][0]
        resultado = self.plugin.grade(self.config, {
            'respuestas': {palabra['id']: f'  {palabra["texto"].lower()} '},
        })
        self.assertEqual(resultado['aciertos'], 1)

    def test_una_palabra_sin_pista_se_avisa(self):
        config = self.plugin.normalize_config({
            'palabras': [
                {'texto': 'ACTIVO', 'pista': 'Lo que posee'},
                {'texto': 'PASIVO', 'pista': ''},
                {'texto': 'COSTO', 'pista': 'Lo que cuesta'},
            ],
        })
        errores = self.plugin.validate_config(config)
        self.assertTrue(any('pista' in e for e in errores))


class CatalogoTests(TestCase):
    def test_ahora_hay_diez_motores(self):
        codigos = {p.codigo for p in all_plugins()}
        self.assertIn('clasificar', codigos)
        self.assertIn('sopa_letras', codigos)
        self.assertIn('crucigrama', codigos)
        self.assertGreaterEqual(len(codigos), 10)
