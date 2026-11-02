# RAG Context Packer 📚📦

Convierte fragmentos ya recuperados y puntuados en un contexto que respeta un **presupuesto estricto de caracteres**. Quita duplicados, limita cuántos fragmentos se toman de cada fuente y conserva referencias por ID, fuente y líneas. Genera un manifiesto con los motivos de descarte.

Creado el **2 de noviembre de 2026**. Python **3.10+**, solo biblioteca estándar: sin paquetes externos, claves, modelos ni servicios. Código y datos ficticios originales, licencia MIT.

## Instalación y demo

```bash
git clone https://github.com/alvaroalcalaa/rag-context-packer.git
cd rag-context-packer
python packer.py examples/chunks.json --budget 300 --per-source 1
python -m unittest -v
```

Se crean `build/context.txt` y `build/manifest.json`. La demo elige `save` y `route`: **198 de 300 caracteres**. Puedes comparar el contexto con `examples/expected-context.txt`. El texto no termina con un salto de línea añadido: el archivo completo debe respetar el presupuesto.

El ejemplo representa datos inventados de Bruma. Las fuentes y líneas son metadatos ficticios suministrados en el JSON; no apuntan a documentos adicionales incluidos en este repositorio.

## Formato de entrada

```json
{
  "chunks": [
    {
      "id": "key",
      "source": "manual.md",
      "line_start": 12,
      "line_end": 13,
      "score": 0.95,
      "text": "La llave azul abre la puerta del bosque."
    }
  ]
}
```

Todos los campos mostrados son obligatorios. El programa no calcula `score`: adapta la salida de tu recuperador a un número finito entre 0 y 1, donde mayor significa más prioritario. Si tu motor devuelve distancias con el significado inverso, conviértelas antes de usarlas. Las puntuaciones deben ser comparables dentro de la entrada.

El campo `source` es una etiqueta de una línea, no una ruta que se abre ni una URL que se visita. Los rangos de líneas se conservan tal cual: no se comprueba su correspondencia con el texto o un archivo. La selección no constituye una verificación de las citas.

## Elegir la política

```bash
# Priorizar relevancia suministrada, en lugar de puntuación por tamaño
python packer.py examples/chunks.json --mode score --budget 300 --per-source 1 --out-dir build-score
```

| Opción | Predeterminado | Función |
|---|---|---|
| `--budget` | 4000 | Máximo de caracteres Unicode de Python; de 1 a 1000000 |
| `--per-source` | 2 | Máximo de fragmentos seleccionados por etiqueta de fuente; de 1 a 50 |
| `--mode` | `density` | `density`: puntuación / tamaño del bloque; `score`: puntuación descendente |
| `--out-dir` | `build` | Carpeta de salida; se crea si falta |

Primero se normalizan los textos con Unicode NFC, `casefold` y colapso de espacios para quitar duplicados. Se conserva el de mayor puntuación; en empate, el ID lexicográficamente menor. No se eliminan acentos ni puntuación y no se detectan paráfrasis. El representante conserva su **texto original**, sin normalizarlo en el contexto.

Después se ordenan los representantes por la política elegida; los empates se resuelven por puntuación y después por ID. Se recorre esa lista una vez y se añade cada fragmento completo si tiene puntuación positiva, queda cuota de fuente y cabe. Un fragmento demasiado grande se omite y se continúa con los siguientes. El orden del contexto es el orden de selección. No hay truncamiento ni rotación de fragmentos.

La demo hace visible un compromiso: `density` escoge el fragmento corto `save` del manual antes que `key`, aunque este tenga mayor puntuación. Con una cuota de uno por fuente, `key` ya no entra. Usa `score` si prefieres dar prioridad directa a la puntuación y evalúa el resultado con tus preguntas reales. Ninguna política garantiza el conjunto óptimo ni que los fragmentos contengan la respuesta.

## Contexto y manifiesto

Cada bloque se escribe como:

```text
[key] manual.md (líneas 12-13)
La llave azul abre la puerta del bosque.
```

Hay dos saltos de línea entre bloques. El presupuesto incluye todos los caracteres de las cabeceras, textos y separadores. El manifiesto muestra `budget_chars`, `used_chars`, `remaining_chars`, `selected`, `source_counts` y `skipped`.

| Motivo de descarte | Significado |
|---|---|
| `duplicate` | Se conservó otro representante del texto normalizado; incluye `duplicate_of` |
| `zero_score` | Puntuación cero |
| `per_source_limit` | Se alcanzó la cuota de esa fuente |
| `over_budget` | El bloque completo y su separador no caben |

Se registra el primer motivo aplicable en ese orden. La deduplicación ocurre antes de empaquetar: un duplicado puede apuntar a un representante que finalmente también se descarte. El límite por fuente compara etiquetas literales; dos rutas distintas del mismo documento se cuentan como fuentes distintas. No fuerza cubrir un número mínimo de documentos ni rellena el presupuesto a toda costa.

## Límites y uso con modelos

**Caracteres no son tokens, bytes ni el tamaño visual del texto.** Un emoji cuenta como un carácter de Python aunque ocupe varios bytes UTF-8; algunas combinaciones Unicode contienen varios caracteres. Antes de enviar el contexto a un modelo, usa su tokenizador y reserva espacio para instrucciones, pregunta y respuesta. Este proyecto no calcula ese límite.

El contexto incluye contenido original suministrado por el usuario. No es un filtro de prompt injection ni un saneador de documentos: trata los fragmentos como datos no confiables y aplica las protecciones correspondientes en tu aplicación. El manifiesto omite los textos, pero sí incluye IDs, fuentes y líneas; el contexto contiene los textos seleccionados.

Entrada UTF-8 de hasta 2 MiB, de 0 a 500 fragmentos, cada texto no vacío de hasta 20000 caracteres. IDs únicos ASCII de hasta 64 caracteres (letras, números, guion y guion bajo), fuentes de hasta 200 caracteres y líneas enteras positivas hasta 10000000. Se rechazan claves JSON duplicadas, rangos invertidos y puntuaciones no finitas. Los campos desconocidos se ignoran.

No recupera documentos, genera respuestas, descarga fuentes ni conecta con una base vectorial. **No se ha probado integración con ningún modelo o framework externo.** Las pruebas verifican tamaños exactos, citas, separadores, Unicode, cuotas, deduplicación, determinismo, selección alternativa, límites y exportación CLI sobre datos sintéticos.

Los archivos de salida existentes se reemplazan, pero se impide sobrescribir la entrada. Un fallo de escritura puede dejar una salida parcial. Códigos de salida: **0** al menos un fragmento seleccionado; **1** contexto vacío (por datos vacíos, puntuaciones cero o presupuesto insuficiente); **2** error de argumentos, datos o escritura.

## Dependencias y licencia

Solo módulos estándar de Python (`json`, `unicodedata`, `collections`, `argparse`, etc.). No se envían datos por red. Consulta `LICENSE` (MIT).
