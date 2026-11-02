# youtube-vault

Convierte un canal de YouTube en una biblioteca de estudio en Obsidian — un video cada vez, con Claude Code haciendo la lectura y la redacción.

Le pasas un video. Saca la transcripción, muestrea el video en busca de capturas que valgan la pena y escribe una nota con la que de verdad puedes estudiar: la idea central, la estructura real del video, los conceptos con sus timestamps, las citas memorables, ideas clave para memorizar y preguntas con respuesta. Después borra todo lo temporal y regenera el índice.

**La transcripción nunca acaba en tu vault.** Existe solo el tiempo necesario para escribir la nota.

[English](README.md)

---

## Cómo queda una nota

```markdown
---
tipo: leccion
video_id: ls_lWYa4zRg
fecha_video: 2023-05-27
duracion: "14:41"
temas: [estudio, relaciones sociales, dinero, disciplina]
resumen: "Seis razones por las que la universidad es una decisión estratégica y no tiempo perdido."
---
# Por qué ir a la universidad (6 pilares)

> [!abstract] Cómo leer esta nota
> Texto normal y bloques `[!quote]` = lo que dice el autor. `[!info]` = explicación
> adicional de Claude. `[!tip]` = conexión o inferencia de Claude.

## Idea central
...

## Estructura
1. [02:23](https://youtu.be/ls_lWYa4zRg?t=143) **Networking y sinergias** — la gente que conoces
2. [04:37](https://youtu.be/ls_lWYa4zRg?t=277) **Asociaciones y conferencias** — iniciativa fuera del aula

## Conceptos principales
### 3. La base de cemento — [07:41](https://youtu.be/ls_lWYa4zRg?t=461)
...
![[ls_lWYa4zRg_07-58.jpg]]
*Captura [07:58](https://youtu.be/ls_lWYa4zRg?t=478): muestra la tabla de ocupaciones con
mayor exposición a la IA que usa como referencia de este argumento*

> [!quote] Autor — [12:22](https://youtu.be/ls_lWYa4zRg?t=742)
> "tú te lo guisas tú te lo comes como la vida misma"
```

El vault que construye:

```
<Nombre del canal>/
├── Índice <Canal>.md           ← generado: tabla de todas las notas y un índice por tema
├── Lecciones/<Nombre corto>.md ← una nota de estudio por video
├── Conceptos/<Tema>.md         ← solo para ideas reutilizables entre videos
└── _adjuntos/<video_id>/       ← las capturas que se ganaron su sitio
```

---

## Por qué está partido en dos

El script hace solo lo que un script hace bien: descargar, transcribir, muestrear fotogramas, hashearlos, validar el vault, regenerar el índice. No toma ni una decisión de criterio.

Claude hace lo que un script no puede: leer la transcripción entera, deducir la estructura real del video, decidir qué capturas llevan información y cuáles son solo una persona hablando, redactar con fidelidad a lo que se dijo, y decidir qué merece enlazarse con qué.

Las reglas que sigue Claude están en [`.claude/skills/lesson/SKILL.md`](.claude/skills/lesson/SKILL.md). Ese archivo es el producto de verdad: léelo si quieres entender por qué las notas salen como salen.

---

## Requisitos

- [Claude Code](https://claude.com/claude-code)
- [uv](https://docs.astral.sh/uv/) — instala las dependencias de Python en la primera ejecución, leyendo la cabecera de `vault.py`. No hay nada que `pip install`.
- Un video con subtítulos, manuales o automáticos. Sin ellos el pipeline se detiene en vez de inventar.

No hace falta ffmpeg: descarga una pista de solo video y nunca tiene que mezclar nada.

---

## Instalación

```bash
git clone https://github.com/d4v1d1126-oss/youtube-vault.git
cd youtube-vault
```

```bash
uv run vault/vault.py init --channel "https://www.youtube.com/@handle" --lang es
```

`init` lee el nombre del canal desde YouTube, escribe `vault/vault.config.json`, crea las carpetas del vault y un vocabulario de temas vacío. Opciones:

| Flag | Qué hace |
|---|---|
| `--channel <url>` | URL del canal; también la usa `pending` |
| `--name "Nombre del canal"` | el nombre tal como debe aparecer en las notas (se lee de YouTube si se omite) |
| `--short "Nombre"` | la forma corta que se usa al atribuir las citas |
| `--lang es\|en` | idioma de las notas (por defecto `es`) |
| `--vault-dir "Carpeta"` | nombre de la carpeta del vault (por defecto: el del canal) |
| `--subtitle-langs es,es-orig,en` | orden de preferencia de subtítulos |

Después abre la carpeta en Claude Code y:

```
/lesson https://www.youtube.com/watch?v=XXXXXXXXXXX
```

Un video por procesamiento. Al terminar, `/clear` y el siguiente `/lesson <URL>`: un contexto limpio por video es justo lo que mantiene las notas afiladas.

---

## El vocabulario de temas

`vault/topics.md` es una lista controlada. Cada nota se etiqueta con 3–6 temas de ahí, y `check` rechaza cualquier tema que no esté en la lista. Es lo que evita que un vault que crece acabe siendo 200 notas con 400 etiquetas de un solo uso.

```markdown
- hábitos — rutinas y sistemas diarios (mañana, noche, sueño, alimentación)
- disciplina — hacer lo decidido aunque no apetezca; constancia
- estudio — técnicas de aprendizaje, apuntes, exámenes y organización académica
```

Empieza vacío. Añade un tema la primera vez que un video lo necesite, con su definición de una línea, y solo si es recurrente en el canal. Que un tema se gane además una nota propia en `Conceptos/<Tema>.md` es más raro todavía: la mayoría de videos no añaden ninguna.

---

## Comandos

```bash
uv run vault/vault.py init [--channel <url>] [--lang es|en]   # configuración inicial
uv run vault/vault.py fetch <url|id>     # transcripción + candidatos + hojas de contacto
uv run vault/vault.py quote <id> "..."   # timestamp exacto de una frase
uv run vault/vault.py pick <id> 3,7,12   # copia las capturas elegidas al vault
uv run vault/vault.py grab <id> 02:59    # captura manual de un instante concreto
uv run vault/vault.py check [id]         # valida el vault
uv run vault/vault.py finish <id>        # check + borra el workspace + regenera el índice
uv run vault/vault.py index              # regenera solo el índice
uv run vault/vault.py template [lesson|concept]   # imprime la plantilla de nota
uv run vault/vault.py pending            # videos del canal que aún no tienen nota
uv run vault/vault.py candidates a,b 10  # notas candidatas a enlazar, por temas compartidos
```

Hay además un test de humo de las heurísticas de fotogramas, que no necesita red: monta un clip sintético y comprueba que las tarjetas, los planos de persona y una pizarra sobreviven cada uno como candidato propio. Pásalo antes de tocar cualquier umbral de `vault.py`:

```bash
uv run tests/test_frames.py
```

`check` es lo que mantiene el vault honesto. Valida el YAML, los campos y secciones obligatorios, los `[[enlaces]]` rotos, los temas contra el vocabulario, el tope de capturas, las capturas huérfanas (copiadas pero nunca usadas en una nota) y los nombres de archivo ilegales en Obsidian. `finish` se niega a limpiar mientras quede un solo error.

---

## Cómo se eligen las capturas

`fetch` muestrea un fotograma cada 1,5 s de una copia a 480p, los agrupa en segmentos visuales con un dHash de 256 bits y se queda con el fotograma de mayor contraste de cada segmento: así obtienes el gráfico terminado y nunca un fundido a medias. Además:

- añade el **estado final** de los segmentos largos, que es como se captura una pizarra o un esquema que se va dibujando, una vez está completo;
- trata los fotogramas planos y de poca varianza como **tarjetas gráficas o de texto** y los deduplica con rigor, porque son estáticas;
- deduplica los planos de persona y el b-roll con holgura, porque los gestos no son información;
- detecta el **plano dominante** — el mismo encuadre de alguien hablando a cámara, repetido a lo largo del video — y conserva solo dos ejemplares.

Lo que sobrevive se monta en hojas de contacto 4×5 etiquetadas. Claude lee esas hojas, no los fotogramas sueltos, y elige por id. Ahí entra el filtro de verdad, que es de criterio: una captura entra solo si se puede describir como "muestra X". Un plano de la persona hablando, una tarjeta que repite el título de la sección, un icono, un fundido: fuera. **Cero capturas es un resultado válido y frecuente**, sobre todo en entrevistas. El tope son seis.

Flags de ajuste, si el montaje de un canal lo pide: `--interval --change --dup --dup-plain --cluster --min-samples --height`. Para texto pequeño en pantalla, `fetch --height 720`.

---

## Configuración

`vault/vault.config.json`:

```json
{
  "channel": { "name": "...", "short_name": "...", "url": "https://www.youtube.com/@handle" },
  "vault_dir": "Nombre del canal",
  "language": "es",
  "subtitle_langs": ["es", "es-ES", "es-419", "es-orig", "en"],
  "limits": { "max_captures": 6, "max_key_ideas": 10, "max_questions": 7,
              "min_topics": 3, "max_topics": 6, "max_concepts_per_video": 2 },
  "skip_title_pattern": ""
}
```

`skip_title_pattern` es una regex que se compara con los títulos en `pending`. Su caso de uso: canales que resuben versiones dobladas de sus propios videos, que si no generarían notas duplicadas.

**Añadir un idioma.** Los nombres de campo, los encabezados de sección, los nombres de carpeta y la plantilla de nota están en los diccionarios `SCHEMAS` y `TEMPLATES`, al principio de `vault/vault.py`. Copia la entrada `en`, traduce los textos y pon tu clave en `language`. `check` valida contra el mismo esquema del que sale la plantilla, así que no pueden desincronizarse.

---

## Limitaciones

- El video debe tener subtítulos. Los automáticos sirven: Claude marca con `[?]` los nombres y cifras dudosos en vez de adivinar en silencio.
- Las capturas se toman a 480p por defecto.
- La calidad depende de la de la transcripción. En un canal con mucha jerga, cuenta con `[?]` en los nombres propios.
- Las entrevistas funcionan, pero dan notas más escuetas: menos capturas, y el trabajo de atribución (separar quién dice qué) es el coste principal.
- Un canal por clon. Para un segundo canal, vuelve a clonar: la config, el vocabulario y el vault son por repositorio.

---

## Créditos

Hecho con [Claude Code](https://claude.com/claude-code). Generalizado a partir de un proyecto privado que lo usaba sobre un único canal en español, donde produjo 127 notas de estudio antes de abrirse.

MIT — ver [LICENSE](LICENSE).
