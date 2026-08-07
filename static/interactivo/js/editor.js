/* Editor de actividades interactivas.
 *
 * No sabe nada de ningun motor concreto: pide el schema del motor elegido y
 * arma los campos a partir de el. Un motor nuevo aparece aqui solo, sin tocar
 * este archivo.
 */
(function () {
    'use strict';

    var datos = document.getElementById('editor-datos');
    var contenedor = document.getElementById('config-editor');
    var descripcion = document.getElementById('config-descripcion');
    var campoMotor = document.getElementById('id_motor');
    var campoJson = document.getElementById('id_configuracion_json');
    var formulario = document.getElementById('form-actividad');
    if (!datos || !contenedor || !campoMotor || !campoJson) {
        return;
    }

    var plantillaUrl = datos.dataset.urlSchema;
    var schemaActual = null;
    var motorCargado = null;

    function configuracionInicial() {
        var nodo = document.getElementById('configuracion-inicial');
        if (!nodo) {
            return {};
        }
        try {
            var valor = JSON.parse(nodo.textContent);
            return valor && typeof valor === 'object' ? valor : {};
        } catch (error) {
            return {};
        }
    }

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

    /* Un control suelto (no de lista). `valor` es el que trae la configuracion. */
    function control(campo, valor) {
        var nodo;
        if (campo.type === 'textarea') {
            nodo = crear('textarea', 'form-control');
            nodo.rows = campo.rows || 4;
            nodo.value = valor === undefined || valor === null ? '' : String(valor);
        } else if (campo.type === 'boolean') {
            nodo = crear('input', 'form-check-input');
            nodo.type = 'checkbox';
            nodo.checked = Boolean(valor);
        } else {
            nodo = crear('input', 'form-control');
            nodo.type = campo.type === 'number' ? 'number' : 'text';
            if (campo.min !== undefined) {
                nodo.min = campo.min;
            }
            nodo.value = valor === undefined || valor === null ? '' : String(valor);
        }
        nodo.dataset.campo = campo.name;
        nodo.dataset.tipo = campo.type;
        return nodo;
    }

    function bloqueCampo(campo, valor) {
        var envoltorio = crear('div', 'mb-3');
        if (campo.type === 'boolean') {
            var check = crear('div', 'form-check');
            var entrada = control(campo, valor);
            var etiquetaCheck = crear('label', 'form-check-label', campo.label || campo.name);
            check.appendChild(entrada);
            check.appendChild(etiquetaCheck);
            envoltorio.appendChild(check);
            return envoltorio;
        }
        envoltorio.appendChild(crear('label', 'form-label', campo.label || campo.name));
        envoltorio.appendChild(control(campo, valor));
        return envoltorio;
    }

    /* Un elemento de una lista: tarjeta con sus campos y el boton de quitar. */
    function bloqueItem(campoLista, valores, indice) {
        var tarjeta = crear('div', 'module-card p-3 mb-2');
        tarjeta.dataset.item = campoLista.name;

        var cabecera = crear('div', 'd-flex justify-content-between align-items-center mb-2');
        cabecera.appendChild(crear('span', 'page-kicker', '#' + (indice + 1)));
        var quitar = crear('button', 'btn btn-sm btn-outline-secondary', 'Quitar');
        quitar.type = 'button';
        quitar.addEventListener('click', function () {
            var lista = tarjeta.parentNode;
            tarjeta.remove();
            renumerar(lista);
        });
        cabecera.appendChild(quitar);
        tarjeta.appendChild(cabecera);

        (campoLista.item_fields || []).forEach(function (subcampo) {
            tarjeta.appendChild(bloqueCampo(subcampo, (valores || {})[subcampo.name]));
        });
        return tarjeta;
    }

    function renumerar(lista) {
        if (!lista) {
            return;
        }
        Array.prototype.forEach.call(lista.children, function (tarjeta, indice) {
            var kicker = tarjeta.querySelector('.page-kicker');
            if (kicker) {
                kicker.textContent = '#' + (indice + 1);
            }
        });
    }

    function bloqueLista(campo, valores) {
        var envoltorio = crear('div', 'mb-3');
        envoltorio.appendChild(crear('label', 'form-label', campo.label || campo.name));

        var lista = crear('div', '');
        lista.dataset.lista = campo.name;
        envoltorio.appendChild(lista);

        var elementos = Array.isArray(valores) ? valores : [];
        var minimo = campo.min_items || 1;
        while (elementos.length < minimo) {
            elementos.push({});
        }
        elementos.forEach(function (valor, indice) {
            lista.appendChild(bloqueItem(campo, valor, indice));
        });

        var agregar = crear('button', 'btn btn-sm btn-outline-primary', '+ Agregar');
        agregar.type = 'button';
        agregar.addEventListener('click', function () {
            lista.appendChild(bloqueItem(campo, {}, lista.children.length));
        });
        envoltorio.appendChild(agregar);
        return envoltorio;
    }

    function pintar(schema, configuracion) {
        contenedor.innerHTML = '';
        (schema.fields || []).forEach(function (campo) {
            if (campo.type === 'list') {
                contenedor.appendChild(bloqueLista(campo, configuracion[campo.name]));
            } else {
                contenedor.appendChild(bloqueCampo(campo, configuracion[campo.name]));
            }
        });
    }

    function leerControl(nodo) {
        if (nodo.dataset.tipo === 'boolean') {
            return nodo.checked;
        }
        if (nodo.dataset.tipo === 'number') {
            return nodo.value === '' ? '' : Number(nodo.value);
        }
        return nodo.value;
    }

    function recolectar() {
        var configuracion = {};
        if (!schemaActual) {
            return configuracion;
        }
        (schemaActual.fields || []).forEach(function (campo) {
            if (campo.type === 'list') {
                var lista = contenedor.querySelector('[data-lista="' + campo.name + '"]');
                var elementos = [];
                if (lista) {
                    Array.prototype.forEach.call(lista.children, function (tarjeta) {
                        var item = {};
                        Array.prototype.forEach.call(
                            tarjeta.querySelectorAll('[data-campo]'),
                            function (nodo) {
                                item[nodo.dataset.campo] = leerControl(nodo);
                            }
                        );
                        elementos.push(item);
                    });
                }
                configuracion[campo.name] = elementos;
            } else {
                var nodo = contenedor.querySelector('[data-campo="' + campo.name + '"]');
                if (nodo) {
                    configuracion[campo.name] = leerControl(nodo);
                }
            }
        });
        return configuracion;
    }

    function cargarSchema(codigo, configuracion) {
        if (!codigo) {
            return;
        }
        var url = plantillaUrl.replace('CODIGO', encodeURIComponent(codigo));
        fetch(url, {headers: {'X-Requested-With': 'XMLHttpRequest'}})
            .then(function (respuesta) { return respuesta.json(); })
            .then(function (datosSchema) {
                if (!datosSchema.ok) {
                    contenedor.innerHTML = '';
                    contenedor.appendChild(
                        crear('div', 'alert alert-danger', datosSchema.error || 'Motor no disponible.')
                    );
                    return;
                }
                schemaActual = datosSchema.schema || {fields: []};
                motorCargado = codigo;
                if (descripcion) {
                    descripcion.textContent = datosSchema.descripcion || '';
                }
                pintar(schemaActual, configuracion || {});
            })
            .catch(function () {
                contenedor.innerHTML = '';
                contenedor.appendChild(
                    crear('div', 'alert alert-danger', 'No se pudo cargar la configuracion del motor.')
                );
            });
    }

    campoMotor.addEventListener('change', function () {
        // Al cambiar de motor la configuracion anterior ya no aplica.
        cargarSchema(campoMotor.value, {});
    });

    if (formulario) {
        formulario.addEventListener('submit', function () {
            campoJson.value = JSON.stringify(recolectar());
        });
    }

    // El motor guardado manda; si es alta, el primero de la lista.
    var inicial = configuracionInicial();
    cargarSchema(campoMotor.value, inicial);
    void motorCargado;
}());
