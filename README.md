# youtube-vault

Turn a YouTube channel into a study library in Obsidian — one video at a time, with Claude Code doing the reading and the writing.

You point it at a video. It pulls the transcript, samples the video for screenshots worth keeping, and writes a note you can actually study from: the central idea, the real structure of the video, the concepts with their timestamps, the memorable quotes, key ideas to memorise, and questions and answers. Then it deletes everything temporary and rebuilds the index.

**The transcript never ends up in your vault.** It exists only long enough to write the note.

[Español](README.es.md)

---

## What a note looks like

```markdown
---
type: lesson
video_id: ls_lWYa4zRg
video_date: 2023-05-27
duration: "14:41"
topics: [study, social relationships, money, discipline]
summary: "Six reasons university is a strategic decision rather than lost time."
---
# Why university is worth it (6 pillars)

> [!abstract] How to read this note
> Plain text and `[!quote]` blocks = what the speaker says. `[!info]` = Claude's added
> explanation. `[!tip]` = Claude's connection or inference.

## Core idea
...

## Structure
1. [02:23](https://youtu.be/ls_lWYa4zRg?t=143) **Networking and synergies** — the people you meet
2. [04:37](https://youtu.be/ls_lWYa4zRg?t=277) **Student societies and talks** — initiative outside class

## Main concepts
### 3. A foundation of concrete — [07:41](https://youtu.be/ls_lWYa4zRg?t=461)
...
![[ls_lWYa4zRg_07-58.jpg]]
*Screenshot [07:58](https://youtu.be/ls_lWYa4zRg?t=478): shows the table of occupations
most exposed to AI that he uses as the reference for this argument*

> [!quote] Speaker — [12:22](https://youtu.be/ls_lWYa4zRg?t=742)
> "you cook it yourself, you eat it yourself, like life itself"
```

The vault it builds:

```
<Channel Name>/
├── <Channel> Index.md          ← generated: table of every note, plus a by-topic index
├── Lessons/<Short name>.md     ← one study note per video
├── Concepts/<Topic>.md         ← only for ideas reusable across videos
└── _attachments/<video_id>/    ← the screenshots that earned their place
```

---

## Why it is split in two

The script does only what a script is good at: downloading, transcribing, sampling frames, hashing them, validating the vault, rebuilding the index. It makes no judgement calls.

Claude does the part a script cannot: reading the whole transcript, working out the video's real structure, deciding which screenshots carry information and which are just a person talking, writing fidelity-preserving prose, and deciding what is worth linking to what.

The rules Claude follows live in [`.claude/skills/lesson/SKILL.md`](.claude/skills/lesson/SKILL.md). That file is the actual product — read it if you want to know how the notes come out the way they do.

---

## Requirements

- [Claude Code](https://claude.com/claude-code)
- [uv](https://docs.astral.sh/uv/) — it installs the Python dependencies on first run, from the header of `vault.py`. Nothing to `pip install`.
- A video with subtitles, manual or automatic. Without them the pipeline stops rather than guessing.

No ffmpeg needed: it downloads a video-only stream and never has to mux anything.

---

## Setup

```bash
git clone https://github.com/d4v1d1126-oss/youtube-vault.git
cd youtube-vault
```

```bash
uv run vault/vault.py init --channel "https://www.youtube.com/@handle" --lang en
```

`init` reads the channel's name from YouTube, writes `vault/vault.config.json`, creates the vault folders and an empty topic vocabulary. Options:

| Flag | What it does |
|---|---|
| `--channel <url>` | channel URL; also used by `pending` |
| `--name "Channel Name"` | the name as it should appear in the notes (read from YouTube if omitted) |
| `--short "Name"` | the short form used in quote attributions |
| `--lang es\|en` | note language (default `es`) |
| `--vault-dir "Folder"` | vault folder name (default: the channel name) |
| `--subtitle-langs es,es-orig,en` | subtitle preference order |

Then open the folder in Claude Code and:

```
/lesson https://www.youtube.com/watch?v=XXXXXXXXXXX
```

One video per run. When it finishes, `/clear` and the next `/lesson <URL>` — a fresh context per video is what keeps the notes sharp.

---

## The topic vocabulary

`vault/topics.md` is a controlled list. Every note tags itself with 3–6 topics from it, and `check` rejects a topic that is not on the list. This is the thing that stops a growing vault from turning into 200 notes with 400 one-off tags.

```markdown
- habits — daily routines and systems (morning, night, sleep, food)
- discipline — doing what you decided even when you don't feel like it
- study — learning techniques, notes, exams, academic organisation
```

Start empty. Add a topic the first time a video needs one, with its one-line definition, and only if it recurs across the channel. A topic that earns a standalone `Concepts/<Topic>.md` note is rarer still — most videos add none.

---

## Commands

```bash
uv run vault/vault.py init [--channel <url>] [--lang es|en]   # one-time setup
uv run vault/vault.py fetch <url|id>     # transcript + frame candidates + contact sheets
uv run vault/vault.py quote <id> "..."   # exact word-level timestamp of a phrase
uv run vault/vault.py pick <id> 3,7,12   # copy chosen screenshots into the vault
uv run vault/vault.py grab <id> 02:59    # capture a specific moment by hand
uv run vault/vault.py check [id]         # validate the vault
uv run vault/vault.py finish <id>        # check + delete the workspace + rebuild the index
uv run vault/vault.py index              # rebuild the index note on its own
uv run vault/vault.py template [lesson|concept]   # print the note template
uv run vault/vault.py pending            # channel videos that have no note yet
uv run vault/vault.py candidates a,b 10  # existing notes worth linking, by shared topics
```

`check` is what keeps the vault honest. It validates YAML, required fields and sections, broken `[[links]]`, topics against the vocabulary, the screenshot cap, orphaned screenshots (copied but never used in a note), and Obsidian-illegal filenames. `finish` refuses to clean up while any error stands.

---

## How screenshots get chosen

`fetch` samples one frame every 1.5 s of a 480p copy, groups them into visual segments with a 256-bit dHash, and keeps the highest-contrast frame of each segment — so you get the finished graphic, never a fade mid-transition. Then it:

- adds the **final state** of long segments, which is how a whiteboard or a diagram being drawn gets captured once it is complete;
- treats flat, low-variance frames as **graphic/text cards** and deduplicates them strictly, since they are static;
- deduplicates talking-head and b-roll shots loosely, because gestures are not information;
- detects the **dominant shot** — the same framing of someone talking to camera, recurring across the video — and keeps only two examples of it.

What survives goes into labelled 4×5 contact sheets. Claude reads those, not the raw frames, and picks by id. Then the real filter applies, and it is a judgement one: a screenshot goes in only if it can be described as "shows X". A shot of the person talking, a card repeating the section title, an icon, a fade — all out. **Zero screenshots is a valid and common outcome**, especially for interviews. The cap is six.

Tuning flags, if a channel's editing style needs it: `--interval --change --dup --dup-plain --cluster --min-samples --height`. For small on-screen text, `fetch --height 720`.

---

## Configuration

`vault/vault.config.json`:

```json
{
  "channel": { "name": "...", "short_name": "...", "url": "https://www.youtube.com/@handle" },
  "vault_dir": "Channel Name",
  "language": "es",
  "subtitle_langs": ["es", "es-ES", "es-419", "es-orig", "en"],
  "limits": { "max_captures": 6, "max_key_ideas": 10, "max_questions": 7,
              "min_topics": 3, "max_topics": 6, "max_concepts_per_video": 2 },
  "skip_title_pattern": ""
}
```

`skip_title_pattern` is a regex matched against titles in `pending`. Its use case: channels that re-upload dubbed versions of their own videos, which would otherwise produce duplicate notes.

**Adding a language.** Field names, section headings, folder names and the note template live in the `SCHEMAS` and `TEMPLATES` dicts at the top of `vault/vault.py`. Copy the `en` entry, translate the strings, and set `language` to your key. `check` validates against the same schema the template comes from, so the two cannot drift apart.

---

## Limitations

- The video must have subtitles. Automatic ones are fine — Claude marks doubtful names and figures with `[?]` rather than silently guessing.
- Screenshots are taken at 480p by default.
- Quality tracks the transcript's. On a channel with heavy jargon, expect `[?]` marks on proper nouns.
- Interviews work, but the notes are leaner: fewer screenshots, and the attribution work of keeping host and guest apart is the main cost.
- One channel per clone. For a second channel, clone again — the config, vocabulary and vault are all per-repository.

---

## Credits

Built with [Claude Code](https://claude.com/claude-code). Generalised from a private project that used it on a single Spanish-language channel, where it produced 127 study notes before being opened up.

MIT — see [LICENSE](LICENSE).
