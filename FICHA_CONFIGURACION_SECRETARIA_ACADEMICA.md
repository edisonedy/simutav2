# Ficha completa de configuracion

## Simulacion base

Usar esta ficha para volver a cargar el caso en otro servidor o para replicar la misma estructura en otros casos.

## 1. Nueva simulacion

### Campos basicos

`Materia`
: `Procesos Administrativos`

`Modo de simulacion`
: `Con IA - Simulacion dinamica`

`Titulo del caso`
: `Mejora de atención estudiantil en secretaría académica`

`Tema`
: `Organización de trámites, prioridades y control de tiempos de respuesta`

`Nivel de dificultad`
: `Media`

`Rondas que tendra el caso`
: `3`

`Tiempo estimado`
: `30`

`Rol estudiante`
: `Asistente administrativo de coordinación académica`

`Contexto del caso`
: `La secretaría académica de una carrera universitaria recibe muchas solicitudes de estudiantes sobre certificados, matrículas, cambios de paralelo y corrección de notas. Actualmente los trámites se atienden sin un orden claro, algunos estudiantes preguntan varias veces por el estado de su solicitud y no existe un control preciso del tiempo de respuesta.

La coordinación necesita mejorar la atención sin contratar más personal ni aumentar el presupuesto.`

`Objetivo del estudiante`
: `Analizar el problema administrativo y proponer una forma ordenada de atender las solicitudes estudiantiles, definiendo prioridades, responsables y controles básicos para reducir demoras.`

`Situacion inicial`
: `Hoy llegan varias solicitudes al mismo tiempo: estudiantes que necesitan certificados, cambios de paralelo, revisión de matrícula y corrección de notas. El equipo administrativo atiende según quién pregunta primero, pero no existe una lista de prioridad ni un registro claro del estado de cada trámite.

El estudiante debe decidir cuál es el primer paso para ordenar el proceso de atención.`

## 2. Configurar > Caso

### Caso y aprendizaje

Debe quedar con estos mismos textos:

`Contexto`
: igual al campo `Contexto del caso`

`Objetivo`
: igual al campo `Objetivo del estudiante`

`Situacion inicial`
: igual al campo `Situacion inicial`

### Datos visibles del caso

No se configuró nada en este caso.

`Opciones del caso`
: ninguna

`Matriz de evaluacion`
: ninguna

## 3. Configurar > Evaluacion con IA

### Indicadores

Cargar estos 5 indicadores:

1. `Orden del proceso`
   `codigo`: `orden_proceso`
   `valor inicial`: `30`
   `valor minimo`: `0`
   `valor maximo`: `100`
   `optimo`: `Mejor cuando es alto`
   `critico`: `Si`
   `unidad`: vacio

2. `Trámites pendientes`
   `codigo`: `tramites_pendientes`
   `valor inicial`: `70`
   `valor minimo`: `0`
   `valor maximo`: `100`
   `optimo`: `Mejor cuando es bajo`
   `critico`: `Si`
   `unidad`: vacio

3. `Solicitudes atendidas a tiempo`
   `codigo`: `solicitudes_a_tiempo`
   `valor inicial`: `45`
   `valor minimo`: `0`
   `valor maximo`: `100`
   `optimo`: `Mejor cuando es alto`
   `critico`: `Si`
   `unidad`: vacio

4. `Satisfacción estudiantil`
   `codigo`: `satisfaccion_estudiantil`
   `valor inicial`: `40`
   `valor minimo`: `0`
   `valor maximo`: `100`
   `optimo`: `Mejor cuando es alto`
   `critico`: `Si`
   `unidad`: vacio

5. `Errores o reprocesos`
   `codigo`: `errores_reprocesos`
   `valor inicial`: `35`
   `valor minimo`: `0`
   `valor maximo`: `100`
   `optimo`: `Mejor cuando es bajo`
   `critico`: `No`
   `unidad`: vacio

### Restricciones

No se configuró ninguna.

### Conceptos esperados por ronda

## Ronda 1 - Diagnostico del problema

### Concepto 1

`Nombre`
: `Identifica desorden en la atención`

`Descripcion`
: `Reconoce que la secretaría atiende solicitudes sin un proceso claro, sin orden definido y sin una forma organizada de gestionar los trámites estudiantiles.`

`Palabras clave`
: `desorden, sin orden, atención desorganizada, falta de proceso, no hay proceso, trámites desordenados, solicitudes sin control, atención improvisada`

`Peso`
: `30`

`Critico`
: `Si`

`Si cumple`
: `orden_proceso +10`
: `errores_reprocesos +3`
: `tramites_pendientes -5`
: `solicitudes_a_tiempo +4`
: `satisfaccion_estudiantil +5`

`Si falta`
: `orden_proceso -8`
: `errores_reprocesos -3`
: `tramites_pendientes +5`
: `solicitudes_a_tiempo -4`
: `satisfaccion_estudiantil -5`

### Concepto 2

`Nombre`
: `Reconoce falta de prioridades`

`Descripcion`
: `Identifica que las solicitudes estudiantiles no se atienden según urgencia, importancia o tipo de trámite, sino de forma improvisada o por orden de presión del estudiante.`

`Palabras clave`
: `prioridad, prioridades, urgencia, trámite urgente, ordenar solicitudes, importancia del trámite, primero lo urgente, clasificación de solicitudes`

`Peso`
: `25`

`Critico`
: `Si`

`Si cumple`
: `orden_proceso +8`
: `errores_reprocesos -2`
: `tramites_pendientes -6`
: `solicitudes_a_tiempo +6`
: `satisfaccion_estudiantil +5`

`Si falta`
: `orden_proceso -6`
: `errores_reprocesos +3`
: `tramites_pendientes +6`
: `solicitudes_a_tiempo -5`
: `satisfaccion_estudiantil -5`

### Concepto 3

`Nombre`
: `Detecta falta de seguimiento`

`Descripcion`
: `Reconoce que la secretaría no tiene un registro claro para saber en qué estado está cada solicitud, quién la está atendiendo y si ya fue resuelta.`

`Palabras clave`
: `seguimiento, estado del trámite, registro, trazabilidad, control de solicitudes, saber en qué estado está, solicitudes pendientes, historial del trámite`

`Peso`
: `25`

`Critico`
: `Si`

`Si cumple`
: `orden_proceso +8`
: `errores_reprocesos -4`
: `tramites_pendientes -7`
: `solicitudes_a_tiempo +5`
: `satisfaccion_estudiantil +4`

`Si falta`
: `orden_proceso -7`
: `errores_reprocesos +4`
: `tramites_pendientes +7`
: `solicitudes_a_tiempo -5`
: `satisfaccion_estudiantil -5`

### Concepto 4

`Nombre`
: `Menciona impacto en estudiantes`

`Descripcion`
: `Reconoce que el desorden en la atención afecta directamente a los estudiantes, causando demoras, molestias, incertidumbre y repetición de consultas sobre sus trámites.`

`Palabras clave`
: `estudiantes afectados, quejas, demora, molestias, insatisfacción, incertidumbre, estudiantes preguntan varias veces, mala atención, retrasos en trámites`

`Peso`
: `20`

`Critico`
: `Si`

`Si cumple`
: `orden_proceso +4`
: `errores_reprocesos -2`
: `tramites_pendientes -3`
: `solicitudes_a_tiempo +3`
: `satisfaccion_estudiantil +8`

`Si falta`
: `orden_proceso -3`
: `errores_reprocesos +2`
: `tramites_pendientes +3`
: `solicitudes_a_tiempo -3`
: `satisfaccion_estudiantil -8`

## Ronda 2 - Decision / propuesta de organizacion

### Concepto 1

`Nombre`
: `Clasifica los tipos de tramite`

`Descripcion`
: `Propone separar las solicitudes por tipo de tramite para atenderlas con mayor orden.`

`Palabras clave`
: `clasificar, tipos de tramite, certificados, matriculas, cambios de paralelo, correccion de notas, separar solicitudes`

`Peso`
: `25`

`Critico`
: `Si`

`Si cumple`
: `orden_proceso +5`
: `tramites_pendientes -5`

`Si falta`
: `orden_proceso -5`
: `tramites_pendientes +5`

### Concepto 2

`Nombre`
: `Define prioridades de atencion`

`Descripcion`
: `Propone atender primero los tramites mas urgentes o importantes segun plazo e impacto academico.`

`Palabras clave`
: `prioridad, urgencia, primero lo urgente, plazo, importancia, orden de atencion`

`Peso`
: `30`

`Critico`
: `Si`

`Si cumple`
: `orden_proceso +5`
: `tramites_pendientes -5`

`Si falta`
: `orden_proceso -5`
: `tramites_pendientes +5`

### Concepto 3

`Nombre`
: `Asigna responsables`

`Descripcion`
: `Define quien debe encargarse de cada tipo de solicitud para evitar confusion o duplicacion de trabajo.`

`Palabras clave`
: `responsable, encargado, asignar, distribuir tareas, personal administrativo, funciones`

`Peso`
: `25`

`Critico`
: `Si`

`Si cumple`
: `orden_proceso +5`
: `tramites_pendientes -5`

`Si falta`
: `orden_proceso -5`
: `tramites_pendientes +5`

### Concepto 4

`Nombre`
: `Propone un registro de seguimiento`

`Descripcion`
: `Propone usar una lista, hoja, sistema o registro para controlar el estado de cada tramite.`

`Palabras clave`
: `registro, seguimiento, control, lista, hoja, sistema, estado del tramite`

`Peso`
: `20`

`Critico`
: `No`

`Si cumple`
: `orden_proceso +5`
: `tramites_pendientes -5`

`Si falta`
: `orden_proceso -5`
: `tramites_pendientes +5`

## Ronda 3 - Plan / control y mejora

### Concepto 1

`Nombre`
: `Define tiempos maximos de respuesta`

`Descripcion`
: `Establece plazos para responder o resolver cada tipo de tramite.`

`Palabras clave`
: `tiempo maximo, plazo, responder a tiempo, tiempo de respuesta, demora, dias de atencion`

`Peso`
: `25`

`Critico`
: `Si`

`Si cumple`
: `orden_proceso +5`
: `tramites_pendientes -5`

`Si falta`
: `orden_proceso -5`
: `tramites_pendientes +5`

### Concepto 2

`Nombre`
: `Propone indicadores de control`

`Descripcion`
: `Define indicadores para medir si la atencion mejora.`

`Palabras clave`
: `indicadores, medir, control, solicitudes atendidas, pendientes, satisfaccion, tiempo promedio`

`Peso`
: `30`

`Critico`
: `Si`

`Si cumple`
: `orden_proceso +5`
: `tramites_pendientes -5`

`Si falta`
: `orden_proceso -5`
: `tramites_pendientes +5`

### Concepto 3

`Nombre`
: `Evalua reduccion de pendientes`

`Descripcion`
: `Verifica si la propuesta disminuye la cantidad de tramites acumulados.`

`Palabras clave`
: `pendientes, reducir pendientes, acumulacion, tramites sin resolver, bajar carga, solicitudes acumuladas`

`Peso`
: `20`

`Critico`
: `Si`

`Si cumple`
: `orden_proceso +5`
: `tramites_pendientes -5`

`Si falta`
: `orden_proceso -5`
: `tramites_pendientes +5`

### Concepto 4

`Nombre`
: `Justifica la mejora del proceso`

`Descripcion`
: `Explica por que la propuesta mejora la atencion, el orden y el control administrativo.`

`Palabras clave`
: `mejora, organizacion, control, atencion, eficiencia, proceso administrativo, mejor servicio`

`Peso`
: `25`

`Critico`
: `No`

`Si cumple`
: `orden_proceso +5`
: `tramites_pendientes -5`

`Si falta`
: `orden_proceso -5`
: `tramites_pendientes +5`

## 4. Configurar > Opciones avanzadas

En este caso quedaron vacias:

`Datos visibles del caso`
: no configurado

`Restricciones`
: no configurado

`Recursos`
: no configurado

`Decisiones sugeridas`
: no configurado

`Eventos dinamicos`
: no configurado

`Condiciones de exito`
: no configurado

## 5. Estado final esperado

La simulacion debe quedar:

`Modo`
: `Con IA - Simulacion dinamica`

`Estado`
: `PUBLICADA`

`Rondas`
: `3`

`Indicadores`
: `5`

`Conceptos por ronda`
: `4` en cada ronda

`Peso por ronda`
: `100` en cada ronda

## 6. Plantilla para replicar en otros casos

Usa esta misma estructura:

### Nueva simulacion

`Titulo`
: [poner titulo]

`Tema`
: [poner tema]

`Rol estudiante`
: [poner rol]

`Contexto`
: [poner contexto]

`Objetivo`
: [poner objetivo]

`Situacion inicial`
: [poner situacion inicial]

`Rondas`
: [1, 2, 3 o mas]

### Indicadores

- [indicador 1]
- [indicador 2]
- [indicador 3]
- [indicador 4]

### Ronda 1

- concepto 1
- concepto 2
- concepto 3
- concepto 4

### Ronda 2

- concepto 1
- concepto 2
- concepto 3
- concepto 4

### Ronda 3

- concepto 1
- concepto 2
- concepto 3
- concepto 4

### Opcionales

- datos visibles
- restricciones
- recursos
- decisiones sugeridas
- eventos
