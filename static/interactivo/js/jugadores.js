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
        var bloque = crear('div', 'module-card p-3 mb-3');
        bloque.appendChild(crear('div', 'page-kicker', 'Pregunta ' + numero));
        bloque.appendChild(crear('div', 'play-label', enunciado));
        return bloque;
    }

    /* Opcion clicable con el input escondido (lo pinta el CSS de la casa). */
    function opcion(tipo, nombre, valor, texto) {
        var etiqueta = crear('label', 'play-option mb-2');
        var entrada = crear('input', 'play-option-control');
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

            (config.elementos || []).forEach(function (elemento) {
                var fila = crear('div', 'play-option d-flex align-items-center gap-2 mb-2');
                fila.dataset.elemento = elemento.id;
                fila.appendChild(crear('span', 'flex-grow-1', elemento.texto));

                var subir = crear('button', 'btn btn-sm btn-outline-secondary', '↑');
                subir.type = 'button';
                subir.addEventListener('click', function () { mover(fila, -1); });

                var bajar = crear('button', 'btn btn-sm btn-outline-secondary', '↓');
                bajar.type = 'button';
                bajar.addEventListener('click', function () { mover(fila, 1); });

                fila.appendChild(subir);
                fila.appendChild(bajar);
                lista.appendChild(fila);
            });
            zona.appendChild(lista);
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
                var fila = crear('div', 'module-card p-3 mb-2 d-flex align-items-center gap-3 flex-wrap');
                fila.dataset.izquierda = izquierda.id;
                fila.appendChild(crear('div', 'play-label mb-0 flex-grow-1', izquierda.texto));

                var selector = crear('select', 'form-select');
                selector.style.maxWidth = '20rem';
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

            var tablero = crear('div', 'case-mini-grid');
            (config.tarjetas || []).forEach(function (tarjeta) {
                var carta = crear('button', 'play-option case-mini text-center');
                carta.type = 'button';
                carta.dataset.pareja = tarjeta.pareja;
                carta.textContent = '?';

                carta.addEventListener('click', function () {
                    if (bloqueado || carta.classList.contains('is-selected')) {
                        return;
                    }
                    carta.textContent = tarjeta.texto;
                    carta.classList.add('is-selected');
                    volteadas.push(carta);

                    if (volteadas.length < 2) {
                        return;
                    }
                    var primera = volteadas[0];
                    var segunda = volteadas[1];
                    if (primera.dataset.pareja === segunda.dataset.pareja) {
                        encontradas.push(primera.dataset.pareja);
                        zona.dataset.encontradas = encontradas.join(',');
                        primera.disabled = true;
                        segunda.disabled = true;
                        volteadas = [];
                        return;
                    }
                    bloqueado = true;
                    window.setTimeout(function () {
                        [primera, segunda].forEach(function (c) {
                            c.textContent = '?';
                            c.classList.remove('is-selected');
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
            var parrafo = crear('div', 'briefing-text');
            (config.partes || []).forEach(function (parte) {
                if (parte.tipo === 'espacio') {
                    var entrada = crear('input', 'form-control d-inline-block mx-1');
                    entrada.type = 'text';
                    entrada.style.width = '10rem';
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
