# /// script
# requires-python = ">=3.10"
# dependencies = ["yt-dlp>=2025.1.1", "opencv-python-headless>=4.9", "numpy>=1.26", "pyyaml>=6"]
# ///
"""vault.py - mechanical half of the YouTube -> Obsidian study-note pipeline.

The judgement half (reading, choosing screenshots, writing the note) is done by
Claude through the /lesson skill. This script only does what a script does well.
RULE: one video per run.

Subcommands:
  init                    create vault.config.json, the vault folders and topics.md
  fetch  <url|id>         metadata, subtitles, 480p video, transcript_raw.md, words.json,
                          screenshot candidates and contact sheets (all temporary, in work/<id>/).
                          Refuses if the video already has a note.
  quote  <id> "phrase"    exact word-level timestamp of a phrase from the transcript
  pick   <id> 3,7,12      copy the chosen candidates into the vault and print the embeds
  grab   <id> mm:ss ...   manual frame capture at specific moments, straight into the vault
  check  [id]             validate the vault (YAML, fields, sections, links, topics, captures)
  finish <id>             check + delete work/<id> entirely + rebuild index and concept notes
  index                   rebuild the index note and every concept note's automatic section
  template                print the exact note template for the configured language
  pending                 channel videos that have no note yet (cached inventory)
  candidates <topics>     existing notes worth linking to, ranked by shared topics

Config: vault.config.json next to this script (see vault.config.example.json).
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import unicodedata
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
WORK = HERE / "work"
CONFIG_FILE = HERE / "vault.config.json"
TOPICS_FILE = HERE / "topics.md"
CHANNEL_CACHE = HERE / ".channel.json"

AUTO_START, AUTO_END = "<!-- auto:lessons -->", "<!-- /auto:lessons -->"


# ---------- language schemas ----------
# Field names and headings the notes use. `check` validates against the active one,
# so the template and the validator can never drift apart.

SCHEMAS = {
    "es": {
        "lesson_type": "leccion",
        "concept_type": "concepto",
        "fields": {"type": "tipo", "video_id": "video_id", "date": "fecha_video",
                   "duration": "duracion", "topics": "temas", "summary": "resumen"},
        "headings": ["## Idea central", "## Estructura", "## Conceptos principales",
                     "## Ideas clave", "## Preguntas y respuestas", "## Relación y fuentes"],
        "dirs": {"lessons": "Lecciones", "concepts": "Conceptos", "attachments": "_adjuntos"},
        "index_name": "Índice {short}.md",
        "auto_heading": "## Lecciones que lo tratan",
        "auto_empty": "- (ninguna todavía)",
        "labels": {
            "index_title": "Índice — {author}",
            "index_intro": "Biblioteca de lecciones generadas a partir de videos de {author}. "
                           "{lessons} {lesson_w}, {concepts} {concept_w}.",
            "plurals": {"lesson": ("lección", "lecciones"), "concept": ("nota-concepto", "notas-concepto")},
            "lessons_h": "## Lecciones", "concepts_h": "## Conceptos", "topics_h": "## Por tema",
            "table_head": "| Lección | Fecha video | Duración | Temas |",
            "none_concepts": "- (ninguno todavía)",
            "topics_title": "Vocabulario de temas — {author}",
        },
    },
    "en": {
        "lesson_type": "lesson",
        "concept_type": "concept",
        "fields": {"type": "type", "video_id": "video_id", "date": "video_date",
                   "duration": "duration", "topics": "topics", "summary": "summary"},
        "headings": ["## Core idea", "## Structure", "## Main concepts",
                     "## Key ideas", "## Questions and answers", "## Links and sources"],
        "dirs": {"lessons": "Lessons", "concepts": "Concepts", "attachments": "_attachments"},
        "index_name": "{short} Index.md",
        "auto_heading": "## Lessons that cover it",
        "auto_empty": "- (none yet)",
        "labels": {
            "index_title": "Index — {author}",
            "index_intro": "Library of study notes built from {author}'s videos. "
                           "{lessons} {lesson_w}, {concepts} {concept_w}.",
            "plurals": {"lesson": ("lesson", "lessons"), "concept": ("concept note", "concept notes")},
            "lessons_h": "## Lessons", "concepts_h": "## Concepts", "topics_h": "## By topic",
            "table_head": "| Lesson | Video date | Duration | Topics |",
            "none_concepts": "- (none yet)",
            "topics_title": "Topic vocabulary — {author}",
        },
    },
}

TEMPLATES = {
    "es": """---
tipo: leccion
video_id: <id>
fecha_video: <YYYY-MM-DD>
duracion: "<mm:ss>"
temas: [<{min_topics}-{max_topics} temas del vocabulario>]
resumen: "<una sola línea: qué enseña el video>"
---
# <Nombre corto>

> [!abstract] Cómo leer esta nota
> Texto normal y bloques `[!quote]` = lo que dice {author}. `[!info]` = explicación adicional de Claude. `[!tip]` = conexión o inferencia de Claude.

**Video:** [<título original>](https://www.youtube.com/watch?v=<id>) · <duración> · publicado <fecha> · <monólogo | tutorial | entrevista>

## Idea central
<2-4 líneas: la tesis del video y por qué importa>

## Estructura
1. [mm:ss](...) **<Bloque/paso 1 tal como lo nombra {short}>** — una línea
2. ...

## Conceptos principales
### 1. <Concepto> — [mm:ss](...)
<qué dice {short}, por qué importa, cómo lo aplica; ejemplos y argumentos del video van aquí, junto al concepto>
![[<id>_mm-ss.jpg]]
*Captura [mm:ss](...): muestra <qué>*
> [!quote] {short} — [mm:ss](...)
> "<cita literal>"
> [!info] Explicación adicional (Claude)
> <solo si hace falta>

## Ideas clave
- <≤ {max_key_ideas} frases cortas para memorizar; citas literales entre comillas con timestamp>

## Preguntas y respuestas
1. **<Pregunta>** — <respuesta breve; ≤ {max_questions} preguntas, las de más valor>

## Relación y fuentes
- [[<Lección>]] — <por qué>
- Conceptos: [[<concepto>]] (solo si existe la nota)
- Video: <url> (subtítulos automáticos de YouTube)
- <Estudio/libro/autor citado por {short}> — citado en [mm:ss](...); no verificado
""",
    "en": """---
type: lesson
video_id: <id>
video_date: <YYYY-MM-DD>
duration: "<mm:ss>"
topics: [<{min_topics}-{max_topics} topics from the vocabulary>]
summary: "<a single line: what the video teaches>"
---
# <Short name>

> [!abstract] How to read this note
> Plain text and `[!quote]` blocks = what {author} says. `[!info]` = Claude's added explanation. `[!tip]` = Claude's connection or inference.

**Video:** [<original title>](https://www.youtube.com/watch?v=<id>) · <duration> · published <date> · <monologue | tutorial | interview>

## Core idea
<2-4 lines: the video's thesis and why it matters>

## Structure
1. [mm:ss](...) **<Block/step 1 as {short} names it>** — one line
2. ...

## Main concepts
### 1. <Concept> — [mm:ss](...)
<what {short} says, why it matters, how it is applied; the video's examples and arguments go here, next to the concept>
![[<id>_mm-ss.jpg]]
*Screenshot [mm:ss](...): shows <what>*
> [!quote] {short} — [mm:ss](...)
> "<literal quote>"
> [!info] Added explanation (Claude)
> <only if needed>

## Key ideas
- <≤ {max_key_ideas} short lines to memorise; literal quotes in quotation marks with a timestamp>

## Questions and answers
1. **<Question>** — <short answer; ≤ {max_questions} questions, the most valuable ones>

## Links and sources
- [[<Lesson>]] — <why>
- Concepts: [[<concept>]] (only if the note exists)
- Video: <url> (YouTube automatic subtitles)
- <Study/book/author cited by {short}> — cited at [mm:ss](...); not verified
""",
}

CONCEPT_TEMPLATES = {
    "es": """---
tipo: concepto
resumen: "<una línea: qué es según {short}>"
---
# <Tema>

## Qué dice {short}
<definición consolidada con enlaces [[Lección]] y timestamps; si varios videos lo matizan, un párrafo por video>

## Cómo aplicarlo
<solo lo que {short} propone; nada inventado>

<!-- auto:lessons -->
## Lecciones que lo tratan
<!-- /auto:lessons -->
""",
    "en": """---
type: concept
summary: "<one line: what it is according to {short}>"
---
# <Topic>

## What {short} says
<consolidated definition with [[Lesson]] links and timestamps; one paragraph per video if several add nuance>

## How to apply it
<only what {short} proposes; nothing invented>

<!-- auto:lessons -->
## Lessons that cover it
<!-- /auto:lessons -->
""",
}

DEFAULT_LIMITS = {"max_captures": 6, "max_key_ideas": 10, "max_questions": 7,
                  "min_topics": 3, "max_topics": 6, "max_concepts_per_video": 2}


# ---------- config ----------

class Config:
    def __init__(self, data: dict, path: Path):
        self.path = path
        ch = data.get("channel") or {}
        self.author = ch.get("name") or "Unknown channel"
        self.short = ch.get("short_name") or self.author.split()[0]
        self.channel_url = ch.get("url") or ""
        self.language = data.get("language") or "es"
        if self.language not in SCHEMAS:
            sys.exit(f"ERROR: language '{self.language}' has no schema. Available: {', '.join(SCHEMAS)}")
        self.schema = SCHEMAS[self.language]
        self.subtitle_langs = data.get("subtitle_langs") or [f"{self.language}-orig", self.language, "en"]
        self.limits = {**DEFAULT_LIMITS, **(data.get("limits") or {})}
        self.skip_title_pattern = data.get("skip_title_pattern") or ""
        self.vault = ROOT / (data.get("vault_dir") or self.author)

    # convenience accessors
    @property
    def f(self) -> dict:
        return self.schema["fields"]

    def dir(self, key: str) -> Path:
        return self.vault / self.schema["dirs"][key]

    @property
    def index_name(self) -> str:
        return self.schema["index_name"].format(short=self.short, author=self.author)

    def label(self, key: str, **kw) -> str:
        return self.schema["labels"][key].format(author=self.author, short=self.short, **kw)

    def plural(self, key: str, n: int) -> str:
        singular, plural = self.schema["labels"]["plurals"][key]
        return singular if n == 1 else plural


def load_config(path: Path | None = None) -> Config:
    p = path or CONFIG_FILE
    if not p.exists():
        sys.exit(f"ERROR: no config at {p}\nRun:  uv run vault/vault.py init --help")
    return Config(json.loads(p.read_text(encoding="utf-8")), p)


# ---------- utilities ----------

def ts(seconds: float, sep: str = ":") -> str:
    s = int(round(seconds))
    h, m, s = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}{sep}{m:02d}{sep}{s:02d}" if h else f"{m:02d}{sep}{s:02d}"


def video_id_from(url_or_id: str) -> str:
    m = re.search(r"(?:v=|youtu\.be/|shorts/|embed/|live/)([\w-]{11})", url_or_id)
    return m.group(1) if m else url_or_id.strip()


def safe_name(title: str, limit: int = 90) -> str:
    """Note name valid on Windows and in Obsidian (no # ^ [ ] | \\ / : * ? " < >)."""
    t = re.sub(r'[\\/:*?"<>|#^\[\]]', "", title)
    t = re.sub(r"\s+", " ", t).strip(" .")
    return t[:limit].rstrip(" .") or "untitled"


def split_frontmatter(text: str) -> tuple[str | None, str]:
    if not text.startswith("---"):
        return None, text
    end = text.find("\n---", 3)
    if end < 0:
        return None, text
    return text[3:end].strip("\n"), text[end + 4:]


def read_frontmatter(path: Path) -> dict:
    import yaml
    fm, _ = split_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
    if fm is None:
        return {}
    try:
        data = yaml.safe_load(fm)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9ñ ]+", " ", s).strip()


# ---------- topic vocabulary ----------

def load_topics() -> dict[str, str]:
    """topics.md: lines '- topic - definition'. Returns {topic: definition}."""
    topics: dict[str, str] = {}
    if not TOPICS_FILE.exists():
        return topics
    for line in TOPICS_FILE.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^- +([^—:]+?)\s*(?:—|:)\s*(.*)$", line.strip())
        if m:
            topics[m.group(1).strip().lower()] = m.group(2).strip()
    return topics


def print_topics(cfg: Config):
    topics = load_topics()
    print(f"\n=== TOPIC VOCABULARY ({len(topics)}; file {TOPICS_FILE}) ===")
    if not topics:
        print("(empty - the first notes define it; add each topic with a one-line definition)")
    for k, v in topics.items():
        print(f"- {k} — {v}")


# ---------- fetch ----------

def pick_sub_lang(info: dict, wanted: list[str]) -> tuple[str | None, str]:
    """Manual subtitles beat automatic ones; within each kind, the configured order wins.

    Put `<lang>-orig` before `<lang>` in the config: among automatic captions, `es` is
    YouTube's *translation* of the original track, while `es-orig` is the original itself.
    Transcribing the translation of a Spanish video back into Spanish loses wording.
    """
    manual = info.get("subtitles") or {}
    auto = info.get("automatic_captions") or {}
    for lang in wanted:
        if lang in manual:
            return lang, "manual"
    for lang in wanted:
        if lang in auto:
            return lang, "auto"
    return None, "none"


def parse_json3(path: Path) -> list[tuple[float, str]]:
    """Returns [(seconds, word)] from json3 subtitles."""
    data = json.loads(path.read_text(encoding="utf-8"))
    words: list[tuple[float, str]] = []
    for ev in data.get("events", []):
        t0 = ev.get("tStartMs", 0)
        for seg in ev.get("segs") or []:
            txt = seg.get("utf8", "")
            if not txt.strip():
                continue
            t = (t0 + seg.get("tOffsetMs", 0)) / 1000.0
            words.append((t, txt.strip()))
    return words


def build_raw_transcript(words, chapters, meta) -> str:
    """Paragraph blocks, compact on purpose so reading it does not burn context.

    One line per block (`[mm:ss] text`, no blank line after) and a block every ~60 words
    instead of every sentence: a block timestamp only has to locate the start of a section.
    Exact quote timestamps come from `quote`, which reads words.json and does not depend
    on this format.
    """
    out = [f"# {meta['title']} — raw transcript", "",
           f"Video: {meta['url']}  |  Duration: {ts(meta['duration'])}  |  Subtitles: {meta['sub_lang']} ({meta['sub_kind']})",
           "~60-word blocks. The timestamp locates the start of the block; for one phrase use `quote`.", ""]
    chaps = chapters or [{"start_time": 0, "end_time": meta["duration"], "title": "Full video"}]
    ci = 0
    block: list[str] = []
    block_t = None
    last_t = None

    def flush():
        nonlocal block, block_t
        if block:
            out.append(f"[{ts(block_t)}] " + " ".join(block))
        block, block_t = [], None

    out.append(f"## {ts(chaps[0]['start_time'])} {chaps[0]['title']}")
    for t, w in words:
        while ci + 1 < len(chaps) and t >= chaps[ci + 1]["start_time"]:
            flush()
            ci += 1
            out.append("")
            out.append(f"## {ts(chaps[ci]['start_time'])} {chaps[ci]['title']}")
        # hard cut, or a long pause once the block already has some body
        if block and (len(block) >= 110 or (len(block) >= 40 and last_t is not None and t - last_t > 2.5)):
            flush()
        if not block:
            block_t = t
        block.append(w)
        last_t = t
        if len(block) >= 55 and w[-1] in ".?!…":
            flush()
    flush()
    return "\n".join(out)


BLANK_STD = 4.0  # below this the frame is uniform (black/white) and never a candidate
FLAT_STD = 35.0  # grey std (64x36) below which the frame is a graphic/text card
HASH_W, HASH_H = 17, 16  # 256-bit dHash: 64 bits cannot tell apart different graphics on the same light background


def dhash(gray_small):
    """256-bit boolean vector (horizontal gradient)."""
    return (gray_small[:, 1:] > gray_small[:, :-1]).flatten()


def hamming(a, b) -> int:
    return int((a != b).sum())


def hash_hex(bits) -> str:
    import numpy as np
    return np.packbits(bits).tobytes().hex()


def extract_candidates(video: Path, out_dir: Path, interval: float, change_t: int, dup_t: int, min_samples: int,
                       cluster_t: int, dup_plain: int = 60):
    import cv2
    import numpy as np

    frames_dir = out_dir / "frames"
    sheets_dir = out_dir / "sheets"
    for d in (frames_dir, sheets_dir):
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True)

    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    step = max(1, int(round(fps * interval)))
    print(f"[frames] {video.name}: {fps:.1f} fps, {total} frames, sampling every {interval}s ({step} frames)")

    segments = []  # {start, end, hash, ref, frame, n, std}
    cur = None
    i = 0
    while True:
        if not cap.grab():
            break
        if i % step == 0:
            ok, frame = cap.retrieve()
            if not ok:
                break
            t = i / fps
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            h = dhash(cv2.resize(gray, (HASH_W, HASH_H), interpolation=cv2.INTER_AREA))
            std = float(cv2.resize(gray, (64, 36), interpolation=cv2.INTER_AREA).std())
            # cut when it changes from the previous sample, or drifts too far from the segment start
            if cur is None or hamming(h, cur["hash"]) > change_t or hamming(h, cur["ref"]) > 2 * change_t:
                if cur is not None:
                    segments.append(cur)
                cur = {"start": t, "end": t, "hash": h, "ref": h, "frame": frame, "n": 1, "std": std,
                       "last_frame": frame, "last_hash": h, "last_std": std}
            else:
                cur["end"] = t
                cur["n"] += 1
                # representative = highest-contrast sample: the complete graphic, never a fade or a transition
                if std > cur["std"]:
                    cur["frame"], cur["hash"], cur["std"] = frame, h, std
                cur["last_frame"], cur["last_hash"], cur["last_std"] = frame, h, std
        i += 1
    if cur is not None:
        segments.append(cur)
    cap.release()
    print(f"[frames] visual segments detected: {len(segments)}")

    # long segments (whiteboard, screen, a drawing being completed): the FINAL state is a candidate too
    extra = []
    for seg in segments:
        if seg["n"] >= 6 and hamming(seg["last_hash"], seg["hash"]) > 10 and seg["last_std"] >= BLANK_STD:
            extra.append({"start": seg["end"], "end": seg["end"], "hash": seg["last_hash"], "ref": seg["last_hash"],
                          "frame": seg["last_frame"], "n": 2, "std": seg["last_std"], "end_state": True})
    segments = sorted(segments + extra, key=lambda x: x["start"])
    if extra:
        print(f"[frames] end states of long segments added: {len(extra)}")

    # candidates: stable segments that do not duplicate one already kept
    kept = []
    for seg in segments:
        seg["dur"] = seg["end"] - seg["start"] + interval
        if seg["n"] < min_samples or seg["std"] < BLANK_STD:  # transitions, or black/white frames
            continue
        seg["card"] = seg["std"] <= FLAT_STD
        # between talking-head/b-roll shots the duplicate threshold is looser: gestures do not matter
        dup = next((k for k in kept if hamming(k["hash"], seg["hash"]) <= (dup_t if (seg["card"] or k["card"]) else dup_plain)), None)
        if dup:
            dup["dur_total"] += seg["dur"]
            dup["repeats"] += 1
            continue
        seg["dur_total"] = seg["dur"]
        seg["repeats"] = 1
        kept.append(seg)

    # dominant clusters (the same talking-head framing over and over): >=90 s accumulated and >=4 members
    # -> keep only 2 examples. Graphic cards (flat images) are never suppressed.
    clusters: list[list] = []
    for seg in kept:
        for cl in clusters:
            if hamming(cl[0]["hash"], seg["hash"]) <= cluster_t:
                cl.append(seg)
                break
        else:
            clusters.append([seg])
    drop = set()
    for cl in clusters:
        cl = [x for x in cl if not x["card"]]
        total_dur = sum(x["dur_total"] for x in cl)
        if total_dur >= 90 and len(cl) >= 4:
            drop |= {id(x) for x in cl[2:]}
            print(f"[frames] fixed shot ({total_dur:.0f}s, {len(cl)} candidates): keeping 2, dropped: "
                  + ", ".join(ts(x["start"]) for x in cl[2:]))
    kept = [k for k in kept if id(k) not in drop]

    cands = []
    for idx, seg in enumerate(kept, start=1):
        name = f"cand_{idx:03d}.jpg"
        cv2.imwrite(str(frames_dir / name), seg["frame"], [cv2.IMWRITE_JPEG_QUALITY, 88])
        cands.append({"id": idx, "t": round(seg["start"], 1), "ts": ts(seg["start"]), "dur": round(seg["dur"], 1),
                      "dur_total": round(seg["dur_total"], 1), "repeats": seg["repeats"], "file": name,
                      "kind": "card" if seg["card"] else "shot", "std": round(seg["std"], 1),
                      "end_state": bool(seg.get("end_state")), "hash": hash_hex(seg["hash"])})

    # contact sheets: 4x5 thumbnails, 320x180, labelled
    tw, th, lab, cols, rows = 320, 180, 26, 4, 5
    per = cols * rows
    sheets = []
    for s in range(0, len(cands), per):
        chunk = cands[s:s + per]
        canvas = np.full((rows * (th + lab), cols * tw, 3), 255, dtype=np.uint8)
        for j, c in enumerate(chunk):
            r, col = divmod(j, cols)
            img = cv2.imread(str(frames_dir / c["file"]))
            thumb = cv2.resize(img, (tw, th), interpolation=cv2.INTER_AREA)
            y, x = r * (th + lab), col * tw
            canvas[y:y + th, x:x + tw] = thumb
            label = f"#{c['id']}  {c['ts']}  ({c['dur']:.0f}s" + (f" x{c['repeats']}" if c["repeats"] > 1 else "") + ")" \
                    + ("  [T]" if c["kind"] == "card" else "") + (" end" if c.get("end_state") else "")
            cv2.putText(canvas, label, (x + 6, y + th + 19), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2, cv2.LINE_AA)
        used_rows = (len(chunk) + cols - 1) // cols
        canvas = canvas[: used_rows * (th + lab)]
        name = f"sheet_{len(sheets) + 1:02d}.jpg"
        cv2.imwrite(str(sheets_dir / name), canvas, [cv2.IMWRITE_JPEG_QUALITY, 82])
        sheets.append(name)
    print(f"[frames] unique candidates: {len(cands)}  ->  contact sheets: {len(sheets)}")
    return cands, sheets


def existing_lesson_for(cfg: Config, vid: str):
    return next((fm for fm in lessons(cfg) if str(fm.get(cfg.f["video_id"], "")) == vid), None)


def cmd_fetch(args, cfg: Config):
    import yt_dlp

    vid = video_id_from(args.url)
    url = f"https://www.youtube.com/watch?v={vid}"

    dup = existing_lesson_for(cfg, vid)
    if dup and not args.force:
        print(f"ALREADY PROCESSED: video {vid} already has a note: [[{dup['_name']}]] ({dup['_path']}).")
        print("Nothing done. To rebuild it on purpose: fetch --force (and delete/adjust the old note).")
        sys.exit(2)

    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
        info = ydl.extract_info(url, download=False)
    lang, kind = pick_sub_lang(info, cfg.subtitle_langs)
    if lang is None:
        sys.exit("ERROR: the video has no subtitles (neither manual nor automatic). Cannot continue.")
    work = WORK / vid
    work.mkdir(parents=True, exist_ok=True)

    video_path = work / "video.mp4"
    opts = {
        "quiet": True, "no_warnings": True, "noprogress": True,
        "outtmpl": str(work / "video.%(ext)s"),
        "format": f"bv*[height<={args.height}][ext=mp4][vcodec^=avc1]/bv*[height<={args.height}][ext=mp4]/bv*[height<={args.height}]/bv*",
        "writesubtitles": kind == "manual", "writeautomaticsub": kind == "auto",
        "subtitleslangs": [lang], "subtitlesformat": "json3",
        "skip_download": args.no_video or video_path.exists(),
    }
    print(f"[fetch] {info['title']}  ({ts(info['duration'])})  subtitles: {lang}/{kind}")
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
    except yt_dlp.utils.DownloadError as e:
        if "429" in str(e):
            sys.exit("ERROR: YouTube is rate-limiting this machine (HTTP 429). Wait a few "
                     "minutes and run fetch again; the workspace is kept, so nothing is lost.")
        sys.exit(f"ERROR: download failed: {e}")

    sub_file = next(work.glob(f"video.{lang}.json3"), None) or next(work.glob("video.*.json3"), None)
    if not sub_file:
        sys.exit("ERROR: the subtitle file was not downloaded.")
    words = parse_json3(sub_file)
    (work / "words.json").write_text(json.dumps([[round(t, 2), w] for t, w in words], ensure_ascii=False), encoding="utf-8")

    upload = info.get("upload_date") or ""
    meta = {
        "id": vid, "url": url, "title": info.get("title"), "channel": info.get("channel") or info.get("uploader"),
        "upload_date": f"{upload[:4]}-{upload[4:6]}-{upload[6:]}" if len(upload) == 8 else upload,
        "duration": info.get("duration") or 0, "duration_ts": ts(info.get("duration") or 0),
        "description": info.get("description") or "",
        "chapters": info.get("chapters") or [],
        "sub_lang": lang, "sub_kind": kind, "word_count": len(words),
        "note_name": safe_name(info.get("title") or vid),
    }
    (work / "transcript_raw.md").write_text(build_raw_transcript(words, meta["chapters"], meta), encoding="utf-8")

    cands, sheets = ([], [])
    if not args.no_video and video_path.exists():
        cands, sheets = extract_candidates(video_path, work, args.interval, args.change, args.dup,
                                           args.min_samples, args.cluster, args.dup_plain)
    meta["candidates"] = cands
    meta["sheets"] = [str(work / "sheets" / s) for s in sheets]
    (work / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== SUMMARY ===")
    print(f"workspace   : {work}")
    print(f"title       : {meta['title']}")
    print(f"channel     : {meta['channel']}   date: {meta['upload_date']}   duration: {meta['duration_ts']}")
    print(f"chapters    : {len(meta['chapters'])}   words: {len(words)}   subtitles: {lang} ({kind})")
    print(f"transcript  : {work / 'transcript_raw.md'}")
    print(f"candidates  : {len(cands)}   contact sheets: {len(sheets)}")
    for s in meta["sheets"]:
        print(f"  - {s}")
    print(f"suggested   : {meta['note_name']}")
    print_topics(cfg)
    print("\n=== EXISTING NOTES AND CONCEPTS (to link) ===")
    print_catalog(cfg)


# ---------- quote ----------

def cmd_quote(args, cfg: Config):
    work = WORK / args.id
    words = json.loads((work / "words.json").read_text(encoding="utf-8"))
    toks = [(t, norm(w)) for t, w in words]
    q = norm(args.text).split()
    if not q:
        sys.exit("empty phrase")
    for n in (len(q), min(len(q), 5), min(len(q), 3)):
        target = q[:n]
        hits = []
        for i in range(len(toks) - n + 1):
            if [x[1] for x in toks[i:i + n]] == target:
                hits.append(toks[i][0])
        if hits:
            label = "" if n == len(q) else f" (matched the first {n} words)"
            for t in hits[:5]:
                print(f"{ts(t)}  https://youtu.be/{args.id}?t={int(t)}{label}")
            return
    sys.exit("not found; try different opening words")


# ---------- grab / pick / finish ----------

def ensure_video(vid: str, height: int = 480) -> Path:
    """Path to the workspace's low-res video; downloads it if missing (e.g. after finish)."""
    import yt_dlp
    work = WORK / vid
    work.mkdir(parents=True, exist_ok=True)
    video_path = work / "video.mp4"
    if not video_path.exists():
        opts = {"quiet": True, "no_warnings": True, "noprogress": True, "outtmpl": str(work / "video.%(ext)s"),
                "format": f"bv*[height<={height}][ext=mp4][vcodec^=avc1]/bv*[height<={height}][ext=mp4]/bv*[height<={height}]/bv*"}
        print(f"[grab] downloading video {vid} ({height}p)...")
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={vid}"])
    return video_path


def parse_ts(text: str) -> float:
    parts = [float(x) for x in text.strip().split(":")]
    while len(parts) < 3:
        parts.insert(0, 0.0)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def cmd_grab(args, cfg: Config):
    """Capture frames at exact moments (mm:ss) straight into the vault."""
    import cv2
    video = ensure_video(args.id)
    dest = cfg.dir("attachments") / args.id
    dest.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(video))
    for t_text in args.times:
        t = parse_ts(t_text)
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok:
            print(f"{t_text}: could not read the frame")
            continue
        name = f"{args.id}_{ts(t, '-')}.jpg"
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 88])  # imwrite fails on non-ASCII paths on Windows
        (dest / name).write_bytes(buf.tobytes())
        print(f"{ts(t):>8}  ->  ![[{name}]]")
    cap.release()
    print(f"\n{len(args.times)} screenshots in {dest}")


def cmd_pick(args, cfg: Config):
    work = WORK / args.id
    meta = json.loads((work / "meta.json").read_text(encoding="utf-8"))
    by_id = {c["id"]: c for c in meta["candidates"]}
    dest = cfg.dir("attachments") / args.id
    dest.mkdir(parents=True, exist_ok=True)
    ids = [int(x) for x in re.split(r"[,\s]+", args.ids.strip()) if x]
    limit = cfg.limits["max_captures"]
    if len(ids) > limit:
        print(f"WARNING: {len(ids)} screenshots; the maximum is {limit} and only the ones that help (check will fail).")
    for i in ids:
        c = by_id[i]
        name = f"{args.id}_{ts(c['t'], '-')}.jpg"
        shutil.copy2(work / "frames" / c["file"], dest / name)
        print(f"#{i:<3} {c['ts']:>8}  ->  ![[{name}]]")
    print(f"\n{len(ids)} screenshots in {dest}")


def cmd_finish(args, cfg: Config):
    problems = run_check(cfg, args.id)
    if any(p.startswith("ERROR") for p in problems):
        print("\n[finish] NOT cleaning up: fix the errors and run finish again.")
        sys.exit(1)
    work = WORK / args.id
    shutil.rmtree(work, ignore_errors=True)
    print(f"[finish] removed the temporary workspace {work}")
    do_index(cfg)
    print("[finish] OK - this video is done.")


# ---------- index / catalog / concepts ----------

def _notes_of_type(directory: Path, type_field: str, type_value: str):
    if not directory.exists():
        return []
    rows = []
    for p in sorted(directory.glob("*.md")):
        fm = read_frontmatter(p)
        if fm.get(type_field) != type_value:
            continue
        fm["_path"] = p
        fm["_name"] = p.stem
        rows.append(fm)
    return rows


def lessons(cfg: Config):
    return _notes_of_type(cfg.dir("lessons"), cfg.f["type"], cfg.schema["lesson_type"])


def concepts(cfg: Config):
    return _notes_of_type(cfg.dir("concepts"), cfg.f["type"], cfg.schema["concept_type"])


def topics_of(fm: dict, cfg: Config) -> list[str]:
    t = fm.get(cfg.f["topics"]) or []
    if isinstance(t, str):
        t = [x.strip() for x in t.split(",")]
    return [str(x).strip().lower() for x in t if str(x).strip()]


def print_catalog(cfg: Config):
    """Name and topics only: printing every summary cost ~4k tokens per fetch and grows
    with the vault. To read a candidate's summary: grep the `summary:` line of that file."""
    rows = lessons(cfg)
    if not rows:
        print("(no notes yet)")
    for fm in rows:
        print(f"- [[{fm['_name']}]]  topics: {', '.join(topics_of(fm, cfg))}")
    cs = concepts(cfg)
    print(f"Concept notes ({len(cs)}): " + (", ".join(f"[[{c['_name']}]]" for c in cs) if cs else "(none)"))
    print(f"One note's summary: grep '^{cfg.f['summary']}:' \"<vault>/{cfg.schema['dirs']['lessons']}/<Name>.md\"")


def refresh_concept_notes(cfg: Config, rows: list[dict]):
    for c in concepts(cfg):
        key = c["_name"].lower()
        related = [fm for fm in rows if key in topics_of(fm, cfg)]
        body = [AUTO_START, cfg.schema["auto_heading"]]
        body += [f"- [[{fm['_name']}]] — {fm.get(cfg.f['summary'], '')}" for fm in related] \
            or [cfg.schema["auto_empty"]]
        body.append(AUTO_END)
        block = "\n".join(body)
        text = c["_path"].read_text(encoding="utf-8")
        if AUTO_START in text and AUTO_END in text:
            new = text[: text.index(AUTO_START)] + block + text[text.index(AUTO_END) + len(AUTO_END):]
        else:
            new = text.rstrip("\n") + "\n\n" + block + "\n"
        if new != text:
            c["_path"].write_text(new, encoding="utf-8")


def do_index(cfg: Config):
    rows = lessons(cfg)
    cs = concepts(cfg)
    by_topic: dict[str, list] = {}
    for fm in rows:
        for t in topics_of(fm, cfg):
            by_topic.setdefault(t, []).append(fm["_name"])
    concept_names = {c["_name"].lower(): c["_name"] for c in cs}
    out = ["---", "type: index", f"author: {cfg.author}", f"updated: {date.today().isoformat()}", "---", "",
           f"# {cfg.label('index_title')}", "",
           cfg.label("index_intro", lessons=len(rows), concepts=len(cs),
                     lesson_w=cfg.plural("lesson", len(rows)), concept_w=cfg.plural("concept", len(cs))), "",
           cfg.label("lessons_h"), "", cfg.label("table_head"), "|---|---|---|---|"]
    for fm in sorted(rows, key=lambda r: str(r.get(cfg.f["date"], "")), reverse=True):
        out.append(f"| [[{fm['_name']}]] | {fm.get(cfg.f['date'], '')} | {fm.get(cfg.f['duration'], '')} | "
                   f"{', '.join(topics_of(fm, cfg))} |")
    out += ["", cfg.label("concepts_h"), ""]
    out += [f"- [[{c['_name']}]] — {c.get(cfg.f['summary'], '')}" for c in cs] or [cfg.schema["labels"]["none_concepts"]]
    out += ["", cfg.label("topics_h"), ""]
    for t in sorted(by_topic):
        label = f"[[{concept_names[t]}]]" if t in concept_names else f"**{t}**"
        out.append(f"- {label}: " + ", ".join(f"[[{n}]]" for n in by_topic[t]))
    path = cfg.vault / cfg.index_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    refresh_concept_notes(cfg, rows)
    print(f"[index] {path}  ({len(rows)} lessons, {len(cs)} concepts, {len(by_topic)} topics)")


# ---------- check ----------

def run_check(cfg: Config, vid: str | None = None) -> list[str]:
    import yaml
    root = cfg.vault
    problems: list[str] = []
    E, W = problems.append, problems.append
    vocab = load_topics()
    mds = [p for p in root.rglob("*.md") if ".obsidian" not in p.parts]
    names = {p.stem for p in mds} | {p.name for p in root.rglob("*") if p.suffix.lower() in (".jpg", ".png", ".jpeg", ".webp")}
    rows = lessons(cfg)
    cs = concepts(cfg)
    F = cfg.f
    limit = cfg.limits["max_captures"]

    for p in mds:
        text = p.read_text(encoding="utf-8", errors="replace")
        rel = p.relative_to(root).as_posix()
        if re.search(r'[\\/:*?"<>|#^\[\]]', p.stem):
            E(f"ERROR invalid Obsidian name: {rel}")
        fm, _ = split_frontmatter(text)
        if fm is None:
            E(f"ERROR no frontmatter: {rel}")
        else:
            try:
                yaml.safe_load(fm)
            except Exception as e:
                E(f"ERROR invalid YAML in {rel}: {e}")
        for link in re.findall(r"!?\[\[([^\]|#]+)", text):
            if link.strip() not in names:
                E(f"ERROR broken link in {rel}: [[{link}]]")

    for fm in rows:
        if vid and str(fm.get(F["video_id"])) != vid:
            continue
        name, path = fm["_name"], fm["_path"]
        text = path.read_text(encoding="utf-8")
        for f in F.values():
            if f not in fm:
                E(f"ERROR note {name}: missing field '{f}' in the frontmatter")
        for h in cfg.schema["headings"]:
            if h not in text:
                E(f"ERROR note {name}: missing section '{h}'")
        for t in topics_of(fm, cfg):
            if t not in vocab:
                E(f"ERROR note {name}: topic '{t}' is not in {TOPICS_FILE.name} "
                  f"(add it with a definition, or use an existing one)")
        n_topics = len(topics_of(fm, cfg))
        if n_topics > cfg.limits["max_topics"] or n_topics < cfg.limits["min_topics"]:
            W(f"WARNING note {name}: {n_topics} topics; the rule is "
              f"{cfg.limits['min_topics']}-{cfg.limits['max_topics']}")
        # screenshots
        vid_id = str(fm.get(F["video_id"], ""))
        adir = cfg.dir("attachments") / vid_id
        embedded = set(re.findall(r"!\[\[([^\]|]+)", text))
        files = {p.name for p in adir.glob("*")} if adir.exists() else set()
        for f in files - embedded:
            E(f"ERROR orphan screenshot (not used in note {name}): "
              f"{cfg.schema['dirs']['attachments']}/{vid_id}/{f} - delete it or use it")
        if len(embedded) > limit:
            E(f"ERROR note {name}: {len(embedded)} screenshots; the maximum is {limit} and only the ones that help")

    for c in cs:
        if c["_name"].lower() not in vocab:
            E(f"ERROR concept note {c['_name']}: its name is not a topic in the vocabulary")
        if F["summary"] not in c:
            W(f"WARNING concept note {c['_name']}: missing '{F['summary']}' in the frontmatter (one line)")
        ctext = c["_path"].read_text(encoding="utf-8")
        if AUTO_START not in ctext:
            W(f"WARNING concept note {c['_name']}: no automatic section (index will add it)")
    n_err = sum(p.startswith("ERROR") for p in problems)
    print(f"[check] {len(rows)} lessons, {len(cs)} concepts, {len(mds)} notes - {n_err} errors, {len(problems) - n_err} warnings")
    for p in problems:
        print("  " + p)
    return problems


# ---------- pending ----------

def channel_inventory(cfg: Config, refresh: bool) -> list[dict]:
    if not refresh and CHANNEL_CACHE.exists():
        return json.loads(CHANNEL_CACHE.read_text(encoding="utf-8"))
    import yt_dlp
    if not cfg.channel_url:
        sys.exit("ERROR: channel.url is not set in the config; `pending` needs it.")
    opts = {"quiet": True, "no_warnings": True, "extract_flat": "in_playlist", "skip_download": True}
    url = cfg.channel_url.rstrip("/")
    if not url.endswith("/videos"):
        url += "/videos"
    with yt_dlp.YoutubeDL(opts) as y:
        pl = y.extract_info(url, download=False)
    rows = [{"id": e.get("id"), "title": e.get("title"), "duration": e.get("duration") or 0}
            for e in (pl.get("entries") or []) if e.get("id")]
    CHANNEL_CACHE.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return rows


def cmd_pending(args, cfg: Config):
    rows = channel_inventory(cfg, args.refresh)
    done = {str(fm.get(cfg.f["video_id"], "")).strip() for fm in lessons(cfg)}
    pend = [r for r in rows
            if r["id"] not in done
            and r["duration"] >= args.min * 60
            and (not args.max or r["duration"] <= args.max * 60)]
    if cfg.skip_title_pattern:
        pat = re.compile(cfg.skip_title_pattern, re.I)
        pend = [r for r in pend if not pat.match(r["title"] or "")]

    no_subs = []
    if args.subs:
        import yt_dlp
        for r in pend[:args.subs]:
            try:
                with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as y:
                    i = y.extract_info("https://www.youtube.com/watch?v=" + r["id"], download=False)
                if pick_sub_lang(i, cfg.subtitle_langs)[0] is None:
                    no_subs.append(r["id"])
            except Exception:
                no_subs.append(r["id"])

    print("done: %d   pending: %d   (filter: %d-%s min%s)"
          % (len(done), len(pend), args.min, args.max or "inf",
             ", title pattern skipped" if cfg.skip_title_pattern else ""))
    if args.subs:
        print("checked subtitles for %d; WITHOUT subtitles (skip): %s"
              % (args.subs, ", ".join(no_subs) or "none"))
    print()
    for r in pend:
        if r["id"] in no_subs:
            continue
        print("%s  %3d:%02d  %s" % (r["id"], r["duration"] // 60, r["duration"] % 60, r["title"]))


# ---------- candidates (notes worth linking) ----------

def cmd_candidates(args, cfg: Config):
    """Short list of notes worth linking to, by shared topics. Replaces the full catalog
    when handing a task to a subagent: only the n closest notes."""
    wanted = {t.strip().lower() for t in args.topics.split(",") if t.strip()}
    rows = []
    for fm in lessons(cfg):
        shared = wanted & set(topics_of(fm, cfg))
        rows.append((len(shared), fm["_name"], sorted(shared), str(fm.get(cfg.f["summary"], ""))))
    rows.sort(key=lambda r: (-r[0], r[1]))
    for score, name, shared, summary in rows[:args.n]:
        if score == 0:
            break
        print("- [[%s]] (%s) — %s" % (name, ", ".join(shared), summary[:160]))


# ---------- template ----------

def cmd_template(args, cfg: Config):
    kw = {"author": cfg.author, "short": cfg.short, **cfg.limits}
    which = TEMPLATES if args.what == "lesson" else CONCEPT_TEMPLATES
    print(which[cfg.language].format(**kw))


# ---------- init ----------

def cmd_init(args, cfg_unused=None):
    if CONFIG_FILE.exists() and not args.force:
        sys.exit(f"ERROR: {CONFIG_FILE} already exists. Use --force to overwrite it.")
    lang = args.lang
    if lang not in SCHEMAS:
        sys.exit(f"ERROR: unsupported language '{lang}'. Available: {', '.join(SCHEMAS)}")
    name = args.name
    url = args.channel or ""
    if not name and url:
        import yt_dlp
        print("[init] reading the channel name from YouTube...")
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "extract_flat": "in_playlist"}) as y:
            info = y.extract_info(url.rstrip("/"), download=False)
        name = info.get("channel") or info.get("uploader") or info.get("title") or ""
    if not name:
        sys.exit("ERROR: pass --name \"Channel Name\" (or --channel <url> so it can be read from YouTube).")
    short = args.short or name.split()[0]
    vault_dir = args.vault_dir or safe_name(name)
    subs = args.subtitle_langs.split(",") if args.subtitle_langs else \
        ([f"{lang}-orig", lang, "en"] if lang != "en" else ["en-orig", "en"])

    cfg_data = {
        "channel": {"name": name, "short_name": short, "url": url},
        "vault_dir": vault_dir,
        "language": lang,
        "subtitle_langs": subs,
        "limits": DEFAULT_LIMITS,
        "skip_title_pattern": "",
    }
    CONFIG_FILE.write_text(json.dumps(cfg_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[init] config written: {CONFIG_FILE}")

    cfg = Config(cfg_data, CONFIG_FILE)
    for key in ("lessons", "concepts", "attachments"):
        cfg.dir(key).mkdir(parents=True, exist_ok=True)
    print(f"[init] vault folders created under: {cfg.vault}")

    if not TOPICS_FILE.exists() or args.force:
        header = {
            "es": [f"# {cfg.label('topics_title')}", "",
                   f"Lista controlada. Cada nota usa {cfg.limits['min_topics']}–{cfg.limits['max_topics']} "
                   "temas de esta lista (en minúsculas, tal cual).",
                   "Solo se añade un tema nuevo si es recurrente en el canal (no una idea de un solo video), "
                   "con una definición de una línea.", "",
                   "<!-- Ejemplo del formato; borra estas líneas y pon los temas de tu canal: -->",
                   "<!-- - hábitos — rutinas y sistemas diarios -->", ""],
            "en": [f"# {cfg.label('topics_title')}", "",
                   f"Controlled list. Each note uses {cfg.limits['min_topics']}–{cfg.limits['max_topics']} "
                   "topics from this list (lowercase, exactly as written).",
                   "Only add a new topic if it recurs across the channel (not a one-video idea), "
                   "with a one-line definition.", "",
                   "<!-- Format example; delete these lines and add your channel's topics: -->",
                   "<!-- - habits — daily routines and systems -->", ""],
        }[lang]
        TOPICS_FILE.write_text("\n".join(header), encoding="utf-8")
        print(f"[init] topic vocabulary created: {TOPICS_FILE}")

    do_index(cfg)
    print(f"\nReady. Next:  /lesson <youtube url>")


# ---------- main ----------

def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", help="path to vault.config.json")
    ap.add_argument("--vault", help="override the vault folder")
    sub = ap.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("init", help="create config, vault folders and topics.md")
    i.add_argument("--channel", help="channel URL (https://www.youtube.com/@handle)")
    i.add_argument("--name", help="channel name as it should appear in the notes")
    i.add_argument("--short", help="short name used in the notes ('Adrià')")
    i.add_argument("--lang", default="es", help=f"note language: {', '.join(SCHEMAS)} (default es)")
    i.add_argument("--vault-dir", help="vault folder name (default: the channel name)")
    i.add_argument("--subtitle-langs", help="comma-separated subtitle preference, e.g. es,es-orig,en")
    i.add_argument("--force", action="store_true")
    i.set_defaults(fn=cmd_init, needs_config=False)

    f = sub.add_parser("fetch")
    f.add_argument("url")
    f.add_argument("--height", type=int, default=480)
    f.add_argument("--interval", type=float, default=1.5, help="seconds between samples")
    f.add_argument("--change", type=int, default=40, help="bits (of 256) to count as a scene change between samples")
    f.add_argument("--dup", type=int, default=18, help="bits (of 256) to count a graphic card as duplicate (they are static)")
    f.add_argument("--min-samples", type=int, default=2, help="minimum samples for a segment to be a candidate")
    f.add_argument("--dup-plain", type=int, default=60, help="bits (of 256) to count two talking-head/b-roll shots as duplicates")
    f.add_argument("--cluster", type=int, default=48, help="bits (of 256) to group the dominant shot (talking to camera)")
    f.add_argument("--no-video", action="store_true", help="transcript/metadata only")
    f.add_argument("--force", action="store_true", help="process even if a note already exists for this video_id")
    f.set_defaults(fn=cmd_fetch)

    q = sub.add_parser("quote")
    q.add_argument("id")
    q.add_argument("text")
    q.set_defaults(fn=cmd_quote)

    g = sub.add_parser("grab")
    g.add_argument("id")
    g.add_argument("times", nargs="+", help="moments as mm:ss (or h:mm:ss)")
    g.set_defaults(fn=cmd_grab)

    p = sub.add_parser("pick")
    p.add_argument("id")
    p.add_argument("ids", help="candidate ids, e.g. 3,7,12")
    p.set_defaults(fn=cmd_pick)

    c = sub.add_parser("check")
    c.add_argument("id", nargs="?")
    c.set_defaults(fn=lambda a, cfg: sys.exit(1 if any(x.startswith("ERROR") for x in run_check(cfg, a.id)) else 0))

    fi = sub.add_parser("finish")
    fi.add_argument("id")
    fi.set_defaults(fn=cmd_finish)

    sub.add_parser("index").set_defaults(fn=lambda a, cfg: do_index(cfg))

    t = sub.add_parser("template", help="print the note template for the configured language")
    t.add_argument("what", nargs="?", default="lesson", choices=["lesson", "concept"])
    t.set_defaults(fn=cmd_template)

    pe = sub.add_parser("pending", help="channel videos without a note yet")
    pe.add_argument("--min", type=int, default=10, help="minimum duration in minutes")
    pe.add_argument("--max", type=int, default=0, help="maximum duration in minutes (0 = no cap)")
    pe.add_argument("--subs", type=int, default=0, help="check subtitles for the first N")
    pe.add_argument("--refresh", action="store_true", help="re-inventory the channel")
    pe.set_defaults(fn=cmd_pending)

    ca = sub.add_parser("candidates", help="existing notes worth linking, by shared topics")
    ca.add_argument("topics", help="comma-separated topics, e.g. money,sales")
    ca.add_argument("n", nargs="?", type=int, default=12)
    ca.set_defaults(fn=cmd_candidates)

    args = ap.parse_args()
    if getattr(args, "needs_config", True):
        cfg = load_config(Path(args.config) if args.config else None)
        if args.vault:
            cfg.vault = Path(args.vault)
        args.fn(args, cfg)
    else:
        args.fn(args)


if __name__ == "__main__":
    main()
