# Ideas from Followers or Facts Studio (FoF)

Source repo: [dnewman1969/followers-or-facts-studio](https://github.com/dnewman1969/followers-or-facts-studio.git) (cloned for review, Nov 2026).

FoF is a **research → script → ComfyUI clips → FFmpeg timeline → YouTube** pipeline with **human approval between every stage**. Titan is a **live gaming session studio** (OBS gameplay, agents, telemetry) with **Phase 6–7** video/publish work planned. The overlap is **post-session finishing and YouTube**, not document fact-checking.

## What FoF does well (steal-worthy)

### 1. Publish without fighting the YouTube Data API

`fofstudio/youtube.py` and `publishkit.py` deliberately avoid Google Cloud OAuth for upload:

- Open `https://www.youtube.com/upload` in the browser.
- Ship a **publish folder**: `metadata.json`, `thumbnail.png`, `captions.srt`, `upload-kit.txt`, and a **checklist** (altered content, kids audience, private-first, paste link back).
- `record_upload()` parses the video ID from the pasted link and stores `studio_url` for copyright/ad checks.

**Titan fit:** Keep OAuth/resumable upload in the spec (Section 9.6 / Y4), but add an **M10/M7 “Publish kit” export** mirroring FoF for users who want zero API setup. Maps cleanly to Titan’s **approval gate** (private upload → human checks → public).

### 2. FFmpeg render engine (`engines/render.py`)

Battle-tested patterns documented as “OwlBox engine rewritten in Python”:

| Pattern | Why it matters for Titan |
|--------|---------------------------|
| Render **each shot to its own file**, then concat | Failures name the bad segment (game hilight vs agent VO vs bumper) |
| **NVENC** with **libx264** fallback | Same GPU story as OBS NVENC (spec D10) |
| **xfade** transition map | Highlight reels from session markers |
| **Ken Burns** on stills / depth parallax | Thumbnails, Comfy stills, replay frames |
| **Music ducking** under narration | Agent voices (track 3) vs bed music (track 4) |
| **-14 LUFS** loudness target (`loudness_lufs`) | YouTube-normal playback |
| **AI label overlay** PNG on generated clips | “Altered content” compliance in publish checklist |

**Titan fit:** Implement in `titan-worker-media` `tasks/video.py` (Phase 6) using FoF’s `Timeline` / `Segment` / `AudioCue` model as a **reference schema**, fed from Titan’s **`recording_tracks` + markers + session events`** instead of FoF’s `production.json`.

### 3. Timeline assembly (`stages/production.py` + `stages/render.py`)

FoF builds a JSON timeline: video track, speech, music cues, SFX, optional **presenter overlay** (Owl in corner + “moves” on painted sets).

**Titan fit:**

- **Live session:** OBS multi-track + FFmpeg webcam (spec D10) = source lanes.
- **Post session:** Worker remux/split tracks (already in spec), then a **non-linear “session reel” timeline** editor in desktop (M7/M8) similar to FoF Production page—lighter MVP: auto-assembly from markers only.

### 4. Captions (`stages/captions.py`)

- **faster-whisper** word timestamps, aligned back to script text (spellings fixed).
- Fallback: proportional word timing from script length.

**Titan fit:** Agent `chat.say` lines + separate agent-audio files → SRT for YouTube and for in-app replay. Reuse alignment idea so on-screen chat matches TTS/audio.

### 5. SEO package (`stages/publish.py`)

- Chapters from scene start times (`MM:SS` or `H:MM:SS`).
- LLM-generated **search phrases** + `sanitize_tags()` (500-char YouTube limit, dedupe, no spam tags).
- Description blocks: sources, credits, pinned-comment text.

**Titan fit:** Session **Director report** + event log → auto chapters (“Launch”, “Crash”, “Fine paid”). LLM call via existing `titan-models` scheduler; store in `publishing` tables (schema already has `generator` jsonb for Comfy).

### 6. Pipeline discipline (`pipeline.py`)

- Stages with **requires / dependents**; changing an early stage **invalidates** later approvals.
- Per-episode folder layout: `render/`, `publish/`, `audio/`.

**Titan fit:** Session lifecycle `recorded → remuxed → draft_rendered → packaged → upload_pending → published`. Expose in Ops Center as a **Publishing** panel (like FoF’s left rail statuses).

### 7. ComfyUI + local TTS (FoF `comfy.py`, `engines/tts.py`, `owl.py`)

- Comfy for storyboard clips and WAN animation.
- **Kokoro** default TTS; Chatterbox with **rights.json** gate.
- **Respellings** table for mispronounced names.

**Titan fit:**

- Comfy: thumbnails (spec Y3), agent portraits (you already stubbed `VITE_COMFYUI_VIEW_URL`).
- TTS: Titan’s `titan-voice` + FoF-style **engine interface** and **respellings** from game/persona YAML.
- FoF’s **corner presenter** overlay is analogous to **animated agent face** in desktop (speaking ring + optional Comfy loop), not Owlbert art.

### 8. What **not** to port wholesale

- FoF’s SQLite research DB, claim graph, and CourtListener agents—different product.
- Browser-only upload only—Titan still wants OAuth for team automation later.
- Full 12 style storyboard pipeline—Titan’s “editor” is session-first, not essay-first.

## Suggested Titan backlog (ordered)

1. **M8.T3+** Extend recording `manifest.json` with FoF-like **publish/** sibling paths.
2. **`titan-worker-media`**: Port minimal `Timeline` + segment render + loudness pass (no Owl overlay).
3. **Desktop**: “Export publish kit” button (zip: mp4, srt, thumb, metadata.json, checklist).
4. **Desktop**: Paste-back YouTube URL → `recordings.youtube_id` (FoF `record_upload` pattern).
5. **Phase 7**: Resumable API upload behind feature flag; publish kit remains default for solo creators.

## Files in FoF worth reading when implementing

| FoF path | Use in Titan |
|---------|----------------|
| `fofstudio/engines/render.py` | FFmpeg timeline executor |
| `fofstudio/publishkit.py` | Publish kit + checklist UI |
| `fofstudio/youtube.py` | Tag sanitizer, studio URLs |
| `fofstudio/stages/publish.py` | Metadata/chapters/keywords generation |
| `fofstudio/stages/captions.py` | SRT from agent audio |
| `fofstudio/pipeline.py` | Stage invalidation pattern |
| `fofstudio/comfy.py` | Comfy queue helpers (thumbnails) |

## Licensing note

FoF is your repo; Titan should **copy ideas and reimplement** in Titan’s packages (Apache-2.0) rather than vendoring `fofstudio` as a dependency—different domain, cleaner import boundaries (`import-linter`).
