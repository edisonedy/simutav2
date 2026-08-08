# Casos de SimutaV2

Un caso es un archivo `.json`, no un programa. Se carga con:

```bash
py manage.py cargar_caso simulador/casos/sag_benchmarking.json --publicar
```

o toda la carpeta de una vez:

```bash
py manage.py cargar_caso simulador/casos --publicar
```

Antes de cargar conviene revisar la ficha sin escribir nada:

```bash
py manage.py cargar_caso simulador/casos/sag_benchmarking.json --dry-run
```

Volver a cargar la misma ficha **actualiza** el caso, no lo duplica: se busca por
materia + título. Si le quitas una ronda a la ficha, esa ronda se desactiva.

## Estructura de la ficha

```jsonc
{
  "materia": {
    "codigo": "AE-06-05",          // materia del catálogo
    "nombre": "Habilidades Gerenciales",
    "malla_codigo": "ADM-UTA-2026", // opcional: si falta, se busca la materia
    "nivel": 6                      //   en la malla donde ya exista
  },
  "tema": "Benchmarking",           // opcional; agrupa dentro de la materia

  "caso": {
    "titulo": "...",
    "modo": "CASO_INDEPENDIENTE",   // o ARBOL_DECISION / SIMULACION_ENCADENADA
    "rol_estudiante": "...",
    "contexto": "...",
    "objetivo": "...",
    "resultado_aprendizaje": "...",
    "situacion_inicial": "...",
    "dificultad": "MEDIA",          // BASICA / MEDIA / AVANZADA
    "tiempo_estimado": 30,
    "guia_debriefing": "...",
    "retroalimentacion_base": "..."
  },

  "archivos": [                     // Excel, PDF, imágenes del caso
    {
      "tipo": "EXCEL",              // EXCEL / PDF / IMAGEN / DOCUMENTO / OTRO
      "nombre": "Workbook FCFF",
      "ruta": "adjuntos/fcff.xlsx", // relativa a la ficha
      "vista_previa": "adjuntos/fcff.png",
      "descripcion": "...",
      "ronda": 2                    // opcional: solo aparece en esa ronda
    }
  ],

  "criterios": [ { "nombre": "...", "peso": 25, "descripcion": "..." } ],
  "matriz":    [ { "criterio": "...", "peso": 30, "evalua": "..." } ],
  "indicadores": [                  // solo hacen falta en SIMULACION_ENCADENADA
    { "codigo": "caja", "nombre": "Caja", "inicial": 8000,
      "minimo": 0, "maximo": 50000, "direccion": "ALTO", "unidad": "USD" }
  ],
  "opciones_caso": [                // alternativas visibles de todo el caso
    { "nombre": "Proveedor A", "subtitulo": "...", "fortaleza": "...", "riesgo": "..." }
  ],

  "rondas": [
    {
      "numero": 1,
      "titulo": "...",
      "situacion": "...",
      "instrucciones": "...",
      "tipo_respuesta": "OPCION_UNICA",   // OPCION_UNICA / OPCION_MULTIPLE /
                                          // TEXTO / NUMERICA / ARCHIVO / MIXTA
      "requiere_justificacion": true,
      "puntaje_maximo": 100,
      "datos": {
        "formula": "EBIT = Ventas − Costos − Gastos operativos",
        "tablas": [
          { "titulo": "Estado de Resultados 2025",
            "columnas": ["Concepto", "USD"],
            "filas": [["Ventas netas", "5.800.000"]] }
        ],
        "nota": "..."
      },
      "campos": [                         // obligatorio si es NUMERICA
        { "clave": "ebit", "etiqueta": "EBIT (USD)", "tipo": "numero",
          "objetivo": 1225000, "tolerancia": 1, "unidad": "USD" }
      ],
      "opciones": [                       // obligatorio si es de elección
        { "texto": "...", "descripcion": "...", "puntaje": 100,
          "retroalimentacion": "...", "impacto": {"caja": -500} }
      ],
      "conceptos": [                      // rúbrica de la ronda
        { "nombre": "Usa la brecha", "palabras_clave": "brecha, diferencia",
          "peso": 40, "si_cumple": "...", "si_falta": "..." }
      ],
      "respuesta_modelo": "El desarrollo del docente.",
      "retroalimentacion": "..."
    }
  ],

  "juegos": [                       // opcional: refuerzo antes del caso
    { "motor": "relacionar", "titulo": "...", "instrucciones": "...",
      "exigir_antes_del_caso": true,
      "configuracion": { /* según el motor */ } }
  ]
}
```

## Los tres modos

| Modo | Cuándo | Qué hace |
| --- | --- | --- |
| `CASO_INDEPENDIENTE` | La mayoría | Cada ronda es una situación ya preparada. Lo que contestó en la ronda 1 no cambia la ronda 2. |
| `ARBOL_DECISION` | Rutas que se abren | Cada elección lleva a un escenario distinto (usa `EscenarioSimulacion`). |
| `SIMULACION_ENCADENADA` | Simulación de Negocios | La decisión mueve los indicadores y la ronda siguiente arranca con la empresa como quedó. Sólo aquí se aplica `impacto`. |

## Qué se corrige sin IA

- `campos` de tipo `numero` con `objetivo`: aritmética pura, dentro de la
  tolerancia vale completo.
- `opciones` con `puntaje`: la alternativa elegida trae su nota.
- `conceptos`: rúbrica por palabras clave.

La IA sólo agrega matiz sobre la justificación escrita; el caso funciona sin ella.
