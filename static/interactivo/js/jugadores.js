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

        /* Cuanto llevas resuelto. Cuenta los grupos que ya tienen respuesta, sin
         * saber nada del motor: sirve igual para preguntas, pares y espacios. */
        var barra = document.querySelector('.juego-progreso-barra');
        function actualizarProgreso() {
            if (!barra) {
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
