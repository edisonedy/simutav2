# Manual de usuario del simulador

## 1. Para que sirve

Este simulador permite que un docente cree un caso, defina como se evalua con IA y publique una actividad donde el estudiante:

- lee una situacion
- toma una decision
- justifica su respuesta
- recibe una nota segun la rubrica del profesor
- ve como cambian los indicadores del caso

La IA no inventa la nota. La IA solo compara la respuesta del estudiante con la rubrica y los conceptos esperados que configuro el profesor.

## 2. Flujo general de trabajo

El trabajo del profesor queda asi:

1. Crear una simulacion nueva.
2. Llenar lo basico del caso.
3. Entrar a `Configurar`.
4. Completar `Caso`.
5. Completar `Evaluacion con IA`.
6. Si hace falta, completar `Opciones avanzadas`.
7. Publicar.

## 3. Crear una simulacion nueva

En la lista de simulaciones, haz clic en `Nueva simulacion`.

En esa ventana solo aparecen los campos basicos:

- `Materia`
- `Modo de simulacion`
- `Titulo del caso`
- `Tema`
- `Nivel de dificultad`
- `Rondas que tendra el caso`
- `Tiempo estimado`
- `Rol estudiante`
- `Contexto del caso`
- `Objetivo del estudiante`
- `Situacion inicial`

### Que significa cada campo

`Materia`
: la materia donde se usara la simulacion.

`Modo de simulacion`
: si usas `Con IA - Simulacion dinamica`, la IA evaluara la justificacion del estudiante segun tu rubrica.

`Titulo del caso`
: nombre visible de la simulacion.

`Tema`
: tema general del caso.

`Nivel de dificultad`
: nivel academico esperado.

`Rondas que tendra el caso`
: cuantas decisiones o etapas tendra la actividad.

`Tiempo estimado`
: minutos aproximados para resolverla.

`Rol estudiante`
: papel que tendra el estudiante dentro del caso.

`Contexto del caso`
: problema general que vive la organizacion.

`Objetivo del estudiante`
: que debe lograr al resolver el caso.

`Situacion inicial`
: primer escenario o primer texto que vera el estudiante antes de decidir.

## 4. Que significa Configurar

Despues de crear la simulacion, entra a `Configurar`.

La pantalla se divide en tres partes:

- `Caso`
- `Evaluacion con IA`
- `Opciones avanzadas`

## 5. Caso

Aqui defines lo que el estudiante va a leer.

### 5.1 Caso y aprendizaje

Aqui van:

- contexto
- objetivo
- situacion inicial

Esto es obligatorio.

### 5.2 Datos visibles del caso

Esto es opcional.

Sirve para mostrarle al estudiante informacion concreta para comparar, por ejemplo:

- proveedores
- candidatos
- tipos de tramite
- criterios
- tablas

No pone la nota por si solo. Solo ayuda a que el estudiante justifique mejor.

## 6. Evaluacion con IA

Esta es la parte mas importante.

Aqui defines que revisa la IA y como se calcula la nota.

### 6.1 Indicadores

Los indicadores son los marcadores del caso.

Ejemplos:

- satisfaccion estudiantil
- tramites pendientes
- orden del proceso
- solicitudes atendidas a tiempo

Cada decision puede hacer que un indicador:

- suba
- baje
- no cambie

#### Como leer + y -

Si un concepto o una decision tiene `+5`, ese indicador sube.

Si tiene `-5`, ese indicador baja.

Eso no significa automaticamente que sea bueno o malo.

Depende de si el indicador conviene:

- `alto`
- `bajo`

Ejemplo:

- en `satisfaccion estudiantil`, subir suele ser bueno
- en `errores o reprocesos`, bajar suele ser bueno

### 6.2 Conceptos esperados por ronda

Esta es la rubrica.

La rubrica define:

- que idea debe mencionar el estudiante
- cuanto vale esa idea
- si es critica
- que indicadores cambia si cumple o si falla

Cada concepto tiene:

`Nombre`
: titulo corto del concepto.

`Descripcion`
: que esperas que haga o mencione el estudiante.

`Palabras clave`
: palabras o frases que ayudan a reconocer ese concepto.

`Peso`
: cuanto vale dentro de la ronda.

`Critico`
: si falta, limita la nota de la ronda.

`Si cumple`
: que indicadores cambian a favor o en contra.

`Si falta`
: que indicadores cambian a favor o en contra.

#### Regla importante

Los pesos de cada ronda deben sumar `100`.

#### Vista previa del impacto

Antes de guardar un concepto, la pantalla muestra una vista previa para que veas:

- que cambia si el concepto se cumple
- que cambia si el concepto falta

#### Recomendaciones automaticas

La pantalla de conceptos tambien muestra avisos automaticos, por ejemplo:

- si una ronda no suma 100
- si no hay conceptos criticos
- si faltan palabras clave
- si la rubrica parece demasiado facil

## 7. Opciones avanzadas

Estas opciones mejoran la simulacion, pero no son obligatorias para empezar.

### 7.1 Restricciones

Sirven para penalizar cuando un indicador queda en mala zona.

Ejemplo:

`tramites pendientes > 80`

### 7.2 Recursos

Sirven para representar costo, tiempo o capacidad limitada.

Ejemplo:

- horas del personal
- presupuesto
- capacidad operativa

### 7.3 Decisiones sugeridas

Son ejemplos de respuesta que el estudiante puede elegir.

El estudiante tambien puede escribir su propia decision.

### 7.4 Eventos dinamicos

Son cambios que ocurren en ciertas rondas o bajo cierta condicion.

Ejemplo:

- se cae el sistema
- aumenta la demanda
- llega una queja masiva

### 7.5 Opciones que cambian indicadores

Sirven cuando quieres que una opcion predefinida cambie indicadores de forma automatica.

## 8. Publicar

La simulacion puede publicarse cuando tenga, como minimo:

- titulo
- contexto
- objetivo
- situacion inicial
- indicadores
- conceptos esperados

No es obligatorio llenar todos los campos avanzados para publicar.

## 9. Como interpreta el estudiante el resultado

En el resultado final se muestran dos cosas distintas:

`Puntaje academico`
: mide que tan bien cumplio la rubrica.

`Salud del caso`
: mide como terminaron los indicadores del caso.

Por eso un estudiante puede sacar `100/100` en puntaje academico y aun asi dejar la `salud del caso` en un valor menor.

Ejemplo:

- cumplio todos los conceptos de la rubrica
- pero algunos indicadores quedaron todavia bajos

Eso significa que justifico bien academicamente, pero la situacion del caso aun no quedo totalmente resuelta.

## 10. Ejemplo completo

### Caso

Titulo:
`Mejora de atencion estudiantil en secretaria academica`

Tema:
`Procesos administrativos`

Rol estudiante:
`Asistente administrativo de coordinacion academica`

Contexto:
La secretaria academica recibe muchas solicitudes de estudiantes: matriculas, certificados, cambios de paralelo y correcciones de notas. La atencion es lenta y desordenada, y eso genera acumulacion de tramites y quejas.

Objetivo:
Organizar la atencion de los tramites para reducir pendientes, mejorar el orden del proceso y aumentar la satisfaccion estudiantil.

Situacion inicial:
En la primera semana del periodo academico se acumulan solicitudes de estudiantes y el personal no tiene un orden claro de atencion. Debes proponer como organizar el trabajo para responder mejor.

### Indicadores

- `Orden del proceso`
- `Tramites pendientes`
- `Solicitudes atendidas a tiempo`
- `Satisfaccion estudiantil`
- `Errores o reprocesos`

### Ronda 1

Objetivo:
Que el estudiante diagnostique el problema.

Conceptos esperados:

- identifica desorden en la atencion
- reconoce falta de prioridades
- detecta falta de seguimiento
- menciona impacto en estudiantes

### Ronda 2

Objetivo:
Que el estudiante proponga una organizacion de trabajo.

Conceptos esperados:

- clasifica los tipos de tramite
- define prioridades de atencion
- asigna responsables
- propone un registro de seguimiento

### Ronda 3

Objetivo:
Que el estudiante proponga control y mejora.

Conceptos esperados:

- define tiempos maximos de respuesta
- propone indicadores de control
- evalua reduccion de pendientes
- justifica la mejora del proceso

### Impactos de ejemplo

Si cumple un concepto clave:

- `orden del proceso +5`
- `tramites pendientes -5`

Si falta un concepto clave:

- `orden del proceso -5`
- `tramites pendientes +5`

## 11. Forma recomendada de trabajar

Si eres docente nuevo, trabaja asi:

1. Crea la simulacion.
2. Llena bien el caso.
3. Agrega 3 a 5 indicadores claros.
4. Crea la rubrica por ronda.
5. Revisa que cada ronda sume 100.
6. Prueba la simulacion.
7. Solo despues agrega recursos, eventos o restricciones si de verdad los necesitas.

## 12. Errores comunes

`La ronda no suma 100`
: la nota quedara mal configurada.

`Demasiadas palabras clave sueltas`
: la IA puede marcar como correcto algo muy superficial.

`Indicadores sin sentido`
: el resultado final no explicara bien lo que paso en el caso.

`Querer configurar todo desde el inicio`
: complica el trabajo del profesor. Primero crea el caso y la rubrica.

## 13. Resumen corto

Lo esencial para que funcione bien es:

- un caso claro
- buenos indicadores
- una rubrica bien hecha

Todo lo demas mejora la experiencia, pero no reemplaza esas tres cosas.
