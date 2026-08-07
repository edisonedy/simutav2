/* Jugadores de las actividades interactivas.
 *
 * Cada motor registra aqui como se dibuja y como se arma su respuesta. El
 * servidor vuelve a calificar siempre: lo que se manda desde aqui es la
 * respuesta del estudiante, nunca la nota.
 *
 * Un motor con jugador propio solo tiene que hacer
 * SimutaJugadores.registrar('mi_codigo', {dibujar, responder}) desde su
 * player_js, que se carga despues de este archivo.
 */
(function () {
    'use strict';

    var registro = {};

    var SimutaJugadores = {
        registrar: function (codigo, jugador) {
            registro[codigo] = jugador;
        },
        obtener: function (codigo) {
            return registro[codigo];
        }
    };
    window.SimutaJugadores = SimutaJugadores;

    function crear(etiqueta, clases, texto) {
        var nodo = document.createElement(etiqueta);
        if (clases) {
            nodo.className = clases;
        }
        if (texto !== undefined) {
            nodo.textContent = texto;
        }
        return nodo;
    }

    function bloquePregunta(numero, enunciado) {
        var bloque = crear('div', 'juego-pregunta');
        bloque.style.animationDelay = (numero - 1) * 0.05 + 's';
        var titulo = crear('div', 'juego-enunciado');
        titulo.appendChild(crear('span', 'juego-num', String(numero)));
        titulo.appendChild(document.createTextNode(enunciado));
        bloque.appendChild(titulo);
        return bloque;
    }

    /* Opcion clicable entera, con el input escondido: la marca la pinta el CSS. */
    function opcion(tipo, nombre, valor, texto) {
        var etiqueta = crear('label', 'juego-opcion');
        var entrada = document.createElement('input');
        entrada.type = tipo;
        entrada.name = nombre;
        entrada.value = valor;
        etiqueta.appendChild(entrada);
        etiqueta.appendChild(crear('span', '', texto));
        return etiqueta;
    }

    // ---------------------------------------------------------------- seleccion
    function jugadorSeleccion(multiple) {
        return {
            dibujar: function (zona, config) {
                (config.preguntas || []).forEach(function (pregunta, indice) {
                    var bloque = bloquePregunta(indice + 1, pregunta.enunciado);
                    (pregunta.opciones || []).forEach(function (op) {
                        bloque.appendChild(opcion(
                            multiple ? 'checkbox' : 'radio',
                            'p_' + pregunta.id,
                            op.id,
                            op.texto
                        ));
                    });
                    bloque.dataset.pregunta = pregunta.id;
                    zona.appendChild(bloque);
                });
            },
            responder: function (zona) {
                var respuestas = {};
                Array.prototype.forEach.call(
                    zona.querySelectorAll('[data-pregunta]'),
                    function (bloque) {
                        var marcadas = bloque.querySelectorAll('input:checked');
                        if (multiple) {
                            respuestas[bloque.dataset.pregunta] = Array.prototype.map.call(
                                marcadas, function (i) { return i.value; }
                            );
                        } else if (marcadas.length) {
                            respuestas[bloque.dataset.pregunta] = marcadas[0].value;
                        }
                    }
                );
                return {respuestas: respuestas};
            }
        };
    }

    SimutaJugadores.registrar('seleccion_unica', jugadorSeleccion(false));
    SimutaJugadores.registrar('seleccion_multiple', jugadorSeleccion(true));

    // --------------------------------------------------------- verdadero/falso
    SimutaJugadores.registrar('verdadero_falso', {
        dibujar: function (zona, config) {
            (config.preguntas || []).forEach(function (pregunta, indice) {
                var bloque = bloquePregunta(indice + 1, pregunta.enunciado);
                bloque.appendChild(opcion('radio', 'p_' + pregunta.id, 'true', 'Verdadero'));
                bloque.appendChild(opcion('radio', 'p_' + pregunta.id, 'false', 'Falso'));
                bloque.dataset.pregunta = pregunta.id;
                zona.appendChild(bloque);
            });
        },
        responder: function (zona) {
            var respuestas = {};
            Array.prototype.forEach.call(
                zona.querySelectorAll('[data-pregunta]'),
                function (bloque) {
                    var marcada = bloque.querySelector('input:checked');
                    if (marcada) {
                        respuestas[bloque.dataset.pregunta] = marcada.value === 'true';
                    }
                }
            );
            return {respuestas: respuestas};
        }
    });

    // ------------------------------------------------------------------ ordenar
    SimutaJugadores.registrar('ordenar', {
        dibujar: function (zona, config) {
            var lista = crear('div', '');
            lista.dataset.lista = 'orden';

            function mover(fila, salto) {
                var hermanos = Array.prototype.slice.call(lista.children);
                var posicion = hermanos.indexOf(fila);
                var destino = posicion + salto;
                if (destino < 0 || destino >= hermanos.length) {
                    return;
                }
                if (salto < 0) {
                    lista.insertBefore(fila, hermanos[destino]);
                } else {
                    lista.insertBefore(hermanos[destino], fila);
                }
            }

            function renumerar() {
                Array.prototype.forEach.call(lista.children, function (fila, i) {
                    fila.querySelector('.juego-orden-num').textContent = (i + 1) + '.';
                });
            }

            (config.elementos || []).forEach(function (elemento) {
                var fila = crear('div', 'juego-fila-orden');
                fila.dataset.elemento = elemento.id;
                fila.appendChild(crear('span', 'juego-orden-num', ''));
                fila.appendChild(crear('span', 'flex-grow-1', elemento.texto));

                var subir = crear('button', 'juego-mover', '↑');
                subir.type = 'button';
                subir.addEventListener('click', function () { mover(fila, -1); renumerar(); });

                var bajar = crear('button', 'juego-mover', '↓');
                bajar.type = 'button';
                bajar.addEventListener('click', function () { mover(fila, 1); renumerar(); });

                fila.appendChild(subir);
                fila.appendChild(bajar);
                lista.appendChild(fila);
            });
            zona.appendChild(lista);
            renumerar();
        },
        responder: function (zona) {
            var filas = zona.querySelectorAll('[data-elemento]');
            return {
                orden: Array.prototype.map.call(filas, function (f) {
                    return f.dataset.elemento;
                })
            };
        }
    });

    // --------------------------------------------------------------- relacionar
    SimutaJugadores.registrar('relacionar', {
        dibujar: function (zona, config) {
            (config.izquierdas || []).forEach(function (izquierda) {
                var fila = crear('div', 'juego-par');
                fila.dataset.izquierda = izquierda.id;
                fila.appendChild(crear('div', 'juego-par-izq', izquierda.texto));

                var selector = crear('select', 'form-select');
                selector.appendChild(new Option('Elige...', ''));
                (config.derechas || []).forEach(function (derecha) {
                    selector.appendChild(new Option(derecha.texto, derecha.id));
                });
                fila.appendChild(selector);
                zona.appendChild(fila);
            });
        },
        responder: function (zona) {
            var relaciones = {};
            Array.prototype.forEach.call(
                zona.querySelectorAll('[data-izquierda]'),
                function (fila) {
                    var selector = fila.querySelector('select');
                    if (selector && selector.value) {
                        relaciones[fila.dataset.izquierda] = selector.value;
                    }
                }
            );
            return {relaciones: relaciones};
        }
    });

    // ------------------------------------------------------------------ memoria
    SimutaJugadores.registrar('memoria', {
        dibujar: function (zona, config) {
            var encontradas = [];
            zona.dataset.encontradas = '';
            var volteadas = [];
            var bloqueado = false;

            var tablero = crear('div', 'juego-tablero');
            (config.tarjetas || []).forEach(function (tarjeta) {
                var carta = crear('button', 'juego-carta');
                carta.type = 'button';
                carta.dataset.pareja = tarjeta.pareja;
                carta.textContent = '?';

                carta.addEventListener('click', function () {
                    if (bloqueado || carta.classList.contains('is-vuelta')) {
                        return;
                    }
                    carta.textContent = tarjeta.texto;
                    carta.classList.add('is-vuelta');
                    volteadas.push(carta);

                    if (volteadas.length < 2) {
                        return;
                    }
                    var primera = volteadas[0];
                    var segunda = volteadas[1];
                    if (primera.dataset.pareja === segunda.dataset.pareja) {
                        encontradas.push(primera.dataset.pareja);
                        zona.dataset.encontradas = encontradas.join(',');
                        [primera, segunda].forEach(function (c) {
                            c.classList.add('is-pareja');
                            c.disabled = true;
                        });
                        volteadas = [];
                        return;
                    }
                    bloqueado = true;
                    window.setTimeout(function () {
                        [primera, segunda].forEach(function (c) {
                            c.textContent = '?';
                            c.classList.remove('is-vuelta');
                        });
                        volteadas = [];
                        bloqueado = false;
                    }, 700);
                });
                tablero.appendChild(carta);
            });
            zona.appendChild(tablero);
        },
        responder: function (zona) {
            var crudo = zona.dataset.encontradas || '';
            return {
                parejas_encontradas: crudo ? crudo.split(',') : []
            };
        }
    });

    // -------------------------------------------------------- completar espacios
    SimutaJugadores.registrar('completar_espacios', {
        dibujar: function (zona, config) {
            var parrafo = crear('div', 'juego-texto');
            (config.partes || []).forEach(function (parte) {
                if (parte.tipo === 'espacio') {
                    var entrada = crear('input', 'juego-espacio');
                    entrada.type = 'text';
                    entrada.dataset.espacio = parte.id;
                    parrafo.appendChild(entrada);
                } else {
                    parrafo.appendChild(document.createTextNode(parte.valor || ''));
                }
            });
            zona.appendChild(parrafo);
        },
        responder: function (zona) {
            var respuestas = {};
            Array.prototype.forEach.call(
                zona.querySelectorAll('[data-espacio]'),
                function (entrada) {
                    respuestas[entrada.dataset.espacio] = entrada.value;
                }
            );
            return {respuestas: respuestas};
        }
    });

    // --------------------------------------------------------------- clasificar
    SimutaJugadores.registrar('clasificar', {
        dibujar: function (zona, config) {
            var banco = crear('div', 'juego-banco');
            banco.dataset.banco = '1';

            function soltar(destino, ficha) {
                destino.appendChild(ficha);
                zona.dispatchEvent(new Event('change', {bubbles: true}));
            }

            (config.elementos || []).forEach(function (elemento) {
                var ficha = crear('button', 'juego-ficha', elemento.texto);
                ficha.type = 'button';
                ficha.dataset.elemento = elemento.id;
                ficha.addEventListener('click', function () {
                    // Un clic la selecciona; el siguiente clic en un grupo la manda alli.
                    var activa = zona.querySelector('.juego-ficha.is-activa');
                    if (activa) {
                        activa.classList.remove('is-activa');
                    }
                    if (activa !== ficha) {
                        ficha.classList.add('is-activa');
                    }
                });
                banco.appendChild(ficha);
            });

            var grupos = crear('div', 'juego-grupos');
            (config.categorias || []).forEach(function (categoria) {
                var caja = crear('div', 'juego-grupo');
                caja.dataset.categoria = categoria.id;
                caja.appendChild(crear('div', 'juego-grupo-nombre', categoria.nombre));
                var dentro = crear('div', 'juego-grupo-fichas');
                caja.appendChild(dentro);
                caja.addEventListener('click', function () {
                    var activa = zona.querySelector('.juego-ficha.is-activa');
                    if (activa) {
                        activa.classList.remove('is-activa');
                        soltar(dentro, activa);
                    }
                });
                grupos.appendChild(caja);
            });

            // Devolver al banco lo que se puso mal.
            banco.addEventListener('click', function (evento) {
                if (evento.target !== banco) {
                    return;
                }
                var activa = zona.querySelector('.juego-ficha.is-activa');
                if (activa) {
                    activa.classList.remove('is-activa');
                    soltar(banco, activa);
                }
            });

            zona.appendChild(crear('p', 'text-muted small mb-1',
                'Toca un elemento y despues el grupo al que pertenece.'));
            zona.appendChild(banco);
            zona.appendChild(grupos);
        },
        responder: function (zona) {
            var asignaciones = {};
            Array.prototype.forEach.call(
                zona.querySelectorAll('[data-categoria]'),
                function (caja) {
                    Array.prototype.forEach.call(
                        caja.querySelectorAll('[data-elemento]'),
                        function (ficha) {
                            asignaciones[ficha.dataset.elemento] = caja.dataset.categoria;
                        }
                    );
                }
            );
            return {asignaciones: asignaciones};
        },
        progreso: function (zona) {
            var total = zona.querySelectorAll('[data-elemento]').length;
            var banco = zona.querySelector('[data-banco]');
            var sueltas = banco ? banco.querySelectorAll('[data-elemento]').length : 0;
            return total ? (total - sueltas) / total : 1;
        }
    });

    // ------------------------------------------------------------ sopa de letras
    SimutaJugadores.registrar('sopa_letras', {
        dibujar: function (zona, config) {
            var hallazgos = {};
            zona.__hallazgos = hallazgos;
            var seleccionada = null;
            var primera = null;

            var tabla = crear('div', 'juego-sopa');
            var tablero = config.tablero || [];
            tabla.style.gridTemplateColumns = 'repeat(' + (tablero[0] || []).length + ', 1fr)';

            function celdasEntre(a, b) {
                var df = Math.sign(b[0] - a[0]);
                var dc = Math.sign(b[1] - a[1]);
                var largoF = Math.abs(b[0] - a[0]);
                var largoC = Math.abs(b[1] - a[1]);
                // Solo valen lineas rectas: horizontal, vertical o diagonal exacta.
                if (largoF && largoC && largoF !== largoC) {
                    return null;
                }
                var pasos = Math.max(largoF, largoC);
                var salida = [];
                for (var i = 0; i <= pasos; i += 1) {
                    salida.push([a[0] + df * i, a[1] + dc * i]);
                }
                return salida;
            }

            function pintar(celdas, clase) {
                celdas.forEach(function (par) {
                    var nodo = tabla.querySelector('[data-celda="' + par[0] + '-' + par[1] + '"]');
                    if (nodo) {
                        nodo.classList.add(clase);
                    }
                });
            }

            tablero.forEach(function (fila, f) {
                fila.forEach(function (letra, c) {
                    var celda = crear('button', 'juego-celda', letra);
                    celda.type = 'button';
                    celda.dataset.celda = f + '-' + c;
                    celda.addEventListener('click', function () {
                        if (!seleccionada) {
                            zona.querySelectorAll('.juego-celda.is-punta').forEach(function (n) {
                                n.classList.remove('is-punta');
                            });
                            return;
                        }
                        if (!primera) {
                            primera = [f, c];
                            celda.classList.add('is-punta');
                            return;
                        }
                        var camino = celdasEntre(primera, [f, c]);
                        tabla.querySelectorAll('.is-punta').forEach(function (n) {
                            n.classList.remove('is-punta');
                        });
                        primera = null;
                        if (!camino) {
                            return;
                        }
                        hallazgos[seleccionada.id] = camino;
                        pintar(camino, 'is-hallada');
                        seleccionada.nodo.classList.add('is-hallada');
                        seleccionada = null;
                        zona.dispatchEvent(new Event('change', {bubbles: true}));
                    });
                    tabla.appendChild(celda);
                });
            });

            var lista = crear('div', 'juego-palabras');
            (config.palabras || []).forEach(function (palabra) {
                var chip = crear('button', 'juego-palabra', palabra.texto);
                chip.type = 'button';
                chip.dataset.palabra = palabra.id;
                chip.title = palabra.pista || '';
                chip.addEventListener('click', function () {
                    zona.querySelectorAll('.juego-palabra.is-activa').forEach(function (n) {
                        n.classList.remove('is-activa');
                    });
                    chip.classList.add('is-activa');
                    seleccionada = {id: palabra.id, nodo: chip};
                    primera = null;
                });
                lista.appendChild(chip);
            });

            zona.appendChild(crear('p', 'text-muted small mb-1',
                'Elige una palabra de la lista y marca su primera y su ultima letra en el tablero.'));
            zona.appendChild(lista);
            zona.appendChild(tabla);
        },
        responder: function (zona) {
            return {hallazgos: zona.__hallazgos || {}};
        },
        progreso: function (zona) {
            var total = zona.querySelectorAll('[data-palabra]').length;
            var halladas = Object.keys(zona.__hallazgos || {}).length;
            return total ? halladas / total : 1;
        }
    });

    // ---------------------------------------------------------------- crucigrama
    SimutaJugadores.registrar('crucigrama', {
        dibujar: function (zona, config) {
            var filas = config.filas || 0;
            var columnas = config.columnas || 0;
            var tabla = crear('div', 'juego-crucigrama');
            tabla.style.gridTemplateColumns = 'repeat(' + columnas + ', 1fr)';

            var casillas = {};
            (config.palabras || []).forEach(function (palabra) {
                for (var i = 0; i < palabra.largo; i += 1) {
                    var f = palabra.fila + (palabra.horizontal ? 0 : i);
                    var c = palabra.columna + (palabra.horizontal ? i : 0);
                    casillas[f + '-' + c] = true;
                }
            });

            for (var f = 0; f < filas; f += 1) {
                for (var c = 0; c < columnas; c += 1) {
                    var clave = f + '-' + c;
                    if (!casillas[clave]) {
                        tabla.appendChild(crear('div', 'juego-cru-vacia'));
                        continue;
                    }
                    var entrada = crear('input', 'juego-cru-celda');
                    entrada.type = 'text';
                    entrada.maxLength = 1;
                    entrada.dataset.celda = clave;
                    entrada.addEventListener('input', function () {
                        this.value = this.value.toUpperCase();
                    });
                    tabla.appendChild(entrada);
                }
            }

            var pistas = crear('div', 'juego-pistas');
            [['Horizontales', true], ['Verticales', false]].forEach(function (par) {
                var grupo = (config.palabras || []).filter(function (p) {
                    return p.horizontal === par[1];
                });
                if (!grupo.length) {
                    return;
                }
                var caja = crear('div', '');
                caja.appendChild(crear('div', 'juego-pistas-titulo', par[0]));
                grupo.forEach(function (palabra) {
                    caja.appendChild(crear(
                        'div', 'juego-pista',
                        palabra.numero + '. ' + palabra.pista + ' (' + palabra.largo + ')'
                    ));
                });
                pistas.appendChild(caja);
            });

            zona.appendChild(tabla);
            zona.appendChild(pistas);
            zona.__palabras = config.palabras || [];
        },
        responder: function (zona) {
            var respuestas = {};
            (zona.__palabras || []).forEach(function (palabra) {
                var letras = '';
                for (var i = 0; i < palabra.largo; i += 1) {
                    var f = palabra.fila + (palabra.horizontal ? 0 : i);
                    var c = palabra.columna + (palabra.horizontal ? i : 0);
                    var celda = zona.querySelector('[data-celda="' + f + '-' + c + '"]');
                    letras += celda && celda.value ? celda.value : ' ';
                }
                respuestas[palabra.id] = letras.trim();
            });
            return {respuestas: respuestas};
        },
        progreso: function (zona) {
            var celdas = zona.querySelectorAll('.juego-cru-celda');
            if (!celdas.length) {
                return 1;
            }
            var llenas = 0;
            Array.prototype.forEach.call(celdas, function (celda) {
                llenas += celda.value.trim() ? 1 : 0;
            });
            return llenas / celdas.length;
        }
    });

    // ------------------------------------------------------------------ arranque
    document.addEventListener('DOMContentLoaded', function () {
        var zona = document.getElementById('zona-juego');
        var datos = document.getElementById('juego-datos');
        var boton = document.getElementById('btn-terminar');
        var aviso = document.getElementById('juego-error');
        var estado = document.getElementById('juego-estado');
        if (!zona || !datos || !boton) {
            return;
        }

        var nodoConfig = document.getElementById('configuracion-publica');
        var config = {};
        try {
            config = JSON.parse(nodoConfig.textContent) || {};
        } catch (error) {
            config = {};
        }

        var jugador = SimutaJugadores.obtener(zona.dataset.renderer);
        if (!jugador) {
            zona.appendChild(crear(
                'div', 'alert alert-warning',
                'Este tipo de actividad todavia no tiene jugador instalado.'
            ));
            boton.disabled = true;
            return;
        }
        jugador.dibujar(zona, config);

        var inicio = Date.now();
        var limite = parseInt(datos.dataset.tiempoLimite, 10) || 0;
        var terminado = false;

        function csrf() {
            var campo = document.querySelector('input[name="csrfmiddlewaretoken"]');
            return campo ? campo.value : '';
        }

        /* Telemetria: que hizo el estudiante y cuando. No afecta la nota; sirve
         * para saber donde se traba y cuantos abandonan sin terminar. */
        function registrar(verbo, elementoId, datos) {
            if (!datos_url_evento) {
                return;
            }
            fetch(datos_url_evento, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrf(),
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({
                    verbo: verbo,
                    elemento_id: elementoId || '',
                    tiempo_segundos: Math.round((Date.now() - inicio) / 1000),
                    datos: datos || {}
                })
            }).catch(function () { /* la telemetria nunca debe romper el juego */ });
        }

        var datos_url_evento = datos.dataset.urlEvento;
        registrar('inicio', '', {renderer: zona.dataset.renderer});

        /* Cuanto llevas resuelto. El motor puede decirlo con `progreso`; si no,
         * se cuentan los grupos que ya tienen respuesta, sin saber de que motor
         * se trata: sirve igual para preguntas, pares y espacios. */
        var barra = document.querySelector('.juego-progreso-barra');
        function actualizarProgreso() {
            if (!barra) {
                return;
            }
            if (typeof jugador.progreso === 'function') {
                barra.style.width = Math.round(jugador.progreso(zona) * 100) + '%';
                return;
            }
            var grupos = zona.querySelectorAll('[data-pregunta], [data-izquierda]');
            var espacios = zona.querySelectorAll('[data-espacio]');
            var total = grupos.length + espacios.length;
            if (!total) {
                barra.style.width = '100%';
                return;
            }
            var hechos = 0;
            Array.prototype.forEach.call(grupos, function (grupo) {
                var select = grupo.querySelector('select');
                if (select) {
                    hechos += select.value ? 1 : 0;
                } else if (grupo.querySelector('input:checked')) {
                    hechos += 1;
                }
            });
            Array.prototype.forEach.call(espacios, function (entrada) {
                hechos += entrada.value.trim() ? 1 : 0;
            });
            barra.style.width = Math.round((hechos * 100) / total) + '%';
        }

        // Cada vez que el estudiante toca algo, queda el rastro y avanza la barra.
        zona.addEventListener('change', function (evento) {
            var objetivo = evento.target;
            registrar('responde', objetivo.name || objetivo.dataset.espacio || '', {});
            actualizarProgreso();
        });
        zona.addEventListener('input', actualizarProgreso);
        zona.addEventListener('click', actualizarProgreso);

        function finalizar() {
            if (terminado) {
                return;
            }
            terminado = true;
            boton.disabled = true;
            aviso.classList.add('d-none');
            estado.textContent = 'Calificando...';

            fetch(datos.dataset.urlFinalizar, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrf(),
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({
                    respuesta: jugador.responder(zona),
                    tiempo_segundos: Math.round((Date.now() - inicio) / 1000)
                })
            })
                .then(function (respuesta) { return respuesta.json(); })
                .then(function (resultado) {
                    if (!resultado.ok) {
                        throw new Error(resultado.error || 'No se pudo calificar.');
                    }
                    registrar('finaliza', '', {porcentaje: resultado.porcentaje});
                    window.location.href = resultado.redirect_url;
                })
                .catch(function (error) {
                    terminado = false;
                    boton.disabled = false;
                    estado.textContent = '';
                    aviso.textContent = error.message;
                    aviso.classList.remove('d-none');
                });
        }

        boton.addEventListener('click', finalizar);

        if (limite > 0) {
            window.setInterval(function () {
                var restante = limite - Math.round((Date.now() - inicio) / 1000);
                if (restante <= 0) {
                    estado.textContent = 'Se acabo el tiempo.';
                    finalizar();
                    return;
                }
                estado.textContent = 'Quedan ' + restante + 's';
            }, 1000);
        }
    });
}());
