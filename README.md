# AutoShorts

A Python CLI and local Flask interface that turn an educational topic into a narrated, animated vertical
MP4. OpenAI or OpenRouter generates scripts when configured; Pexels supplies scene photos when
configured. Speech stays local through macOS `say`.

## Setup

Requires macOS, Python 3.9+, the Samantha speech voice, and `ffmpeg` / `ffprobe`
on PATH with H.264 (`libx264`) and AAC encoders. Use the existing environment:

```sh
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
open output/autoshorts.mp4
```

When prompted with `Enter your topic or question:`, type your own question and
press Enter. AutoShorts uses it to generate the video. You can also pass it
directly, for example `python main.py "Why is the sky blue?"`.

Pillow and Flask are the required dependencies. Install the optional OpenAI SDK for
arbitrary-topic scripts through either provider:

```sh
python -m pip install -r requirements-ai.txt
```

## Local browser interface

```sh
source .venv/bin/activate
python -m pip install -r requirements-ai.txt
python web.py
```

Open **http://127.0.0.1:5000**, enter a topic, and click **Generate Video**. Wait
with the page open, then preview the video and click **Download MP4**. Your
existing project-root `.env` settings are used automatically by the generator;
keys are not sent to the browser. No separate frontend setup is needed.

The page uses plain HTML/CSS and a small JavaScript fetch request. The Flask
request synchronously invokes the existing `main.py` CLI with the virtual
environment's Python, so the script, narration, animation, encoding, and full
video validation stay in one pipeline. There is no background job system.
The form is disabled while rendering; a server lock rejects concurrent renders
with a helpful error. Failures are displayed on the page; diagnostic details
stay in the server terminal.

Each render saves a unique UUID-named MP4 and its JSON/SRT sidecars under
`output/web/`. Older videos remain available and can be deleted manually when
no longer needed. Preview requests support byte ranges for seeking; downloads
return MP4 attachments. Only generated MP4 filenames are served, not `.env`,
source files, or manifests. The CLI and its default output remain available.

This is a local development server, bound to `127.0.0.1`, with debug mode and
automatic reload disabled. Use one server process. A generation request has a
10-minute timeout; free AI service availability can affect completion time.
Stop the server with Ctrl-C. This interface is not a deployed production service.

The complete browser flow was verified in installed Chrome on October 11, 2026:
typing “How do batteries store energy?”, clicking Generate, observing loading,
previewing advancing HTML5 playback, and retrieving the MP4 download. The live
OpenRouter render produced a 32.27-second H.264/AAC file at 1080×1920 / 30 fps.
The downloaded bytes matched the generated file and passed full FFmpeg decoding.
Double-clicking sent one request, a concurrent request returned 409, seeking
used a successful 206 byte-range response, and the mobile layout had no
horizontal overflow. The report is `output/web/browser-validation.json`.
All 16 Python tests passed, including web validation, errors, and file serving.

Set credentials in the environment of the terminal that runs the command, or
copy `.env.example` to the project-root `.env` and fill your chosen provider key.
AutoShorts loads simple `KEY=value` lines from `.env` automatically; existing
shell variables take precedence. It accepts optional matching quotes and comment
lines, without shell expansion. `.env` is Git-ignored. Never commit secrets.

```sh
# Read keys without echoing them or storing their values in shell history (zsh).
read -rs 'OPENAI_API_KEY?OpenAI API key: '; export OPENAI_API_KEY
read -rs 'PEXELS_API_KEY?Pexels API key (optional): '; export PEXELS_API_KEY
python main.py "How do solar panels work?" --output output/solar.mp4
```

`OPENAI_API_KEY` needs API credit and access to the chosen model. The default is
`gpt-4o-mini`; override with `OPENAI_MODEL` using a model supporting Chat
Completions JSON mode. `PEXELS_API_KEY` is optional; obtain it from
[Pexels API](https://www.pexels.com/api/). Photo requests use the official
[Pexels search API](https://www.pexels.com/api/documentation/).

### OpenRouter alternative

An OpenRouter key can replace the OpenAI key. The same installed SDK is reused,
following [OpenRouter's SDK integration](https://openrouter.ai/docs/guides/community/openai-sdk).

```sh
read -rs 'OPENROUTER_API_KEY?OpenRouter API key: '; export OPENROUTER_API_KEY
export OPENROUTER_MODEL='openrouter/free'
python main.py "How do solar panels work?" --provider openrouter --output output/solar.mp4
```

The model defaults to `openrouter/free`. Other OpenRouter model IDs must support
the `response_format` JSON-mode parameter. OpenRouter requests require parameter
support so routing does not silently discard the JSON-format requirement.
Use a key with sufficient credit or access to the chosen model. No separate
OpenAI key is needed for OpenRouter. Live OpenRouter generation was verified
with the free router on October 11, 2026 using solar panels and volcanoes.
The credentials stay in a local ignored `.env`, never in generated manifests.

For free-model routing, set `OPENROUTER_MODEL=openrouter/free` in `.env` or the
shell. This selects only free models through the
[OpenRouter free router](https://openrouter.ai/docs/guides/routing/routers/free-router).
Free routes can be slower or rate-limited; the application does not switch to a
paid model automatically.

`--provider auto` (the default) prefers OpenAI when its key is set, otherwise
OpenRouter. `--provider openai` or `--provider openrouter` selects explicitly;
keys are sent only to that provider's fixed endpoint. A provider error tries
the curated offline library; it does not switch to another paid provider.

## Exactly what works offline

Without either configured AI provider key, arbitrary-topic generation is **unavailable**. Only
these five authored educational scripts and their explicit aliases work:

- Why is the sky blue? / Rayleigh scattering
- Photosynthesis / How plants make food
- How rainbows form
- Gravity / How gravity works
- How do volcanoes erupt?

Unknown offline topics fail with a helpful error. They do not receive a generic
explanation. An API failure falls back only when the topic matches this library;
the console and JSON manifest label the script `curated_offline`.

Without `PEXELS_API_KEY`, visuals are animated **text cards**, not subject photos
or AI-generated illustrations. Their topic-specific titles, explanations,
narration captions, and scene-specific palettes differ, but the abstract
backgrounds do not depict the subject. This limitation is disclosed in the
console, video footer, and manifest. Pexels failures, empty results, duplicate
results, or invalid image downloads fall back per scene to text cards.

```sh
python main.py "Why is the sky blue?" --offline --output output/sky.mp4
python main.py "How do volcanoes erupt?" --offline --output output/volcanoes.mp4
python main.py "How do batteries work?" --cards-only  # Requires an AI provider key
```

`--offline` disables both APIs. `--cards-only` disables Pexels while retaining AI
script generation. The default destination is project-relative
`output/autoshorts.mp4`; custom paths are relative to the current directory.

## Pipeline and outputs

1. The selected AI provider generates 4–5 scenes containing a title, summary, narration,
   visual description, and concise stock-photo search keywords. Validation
   checks structure, limits, distinct searches, and 70–115 narration words.
   The prompt targets 85–100 words for about 30 seconds. See
   [OpenAI JSON mode documentation](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat).
2. Pexels searches each scene's keywords and downloads an unused result.
   Photos are center-cropped to portrait. API calls have timeouts and downloads
   have size limits. Search relevance is approximate; photos are illustrative
   and are not verified scientific diagrams. Photos use the
   [Pexels license](https://www.pexels.com/license/); photographer credits appear
   onscreen, with full photo and photographer links in the manifest.
3. `say` synthesizes each scene with Samantha at 200 words per minute.
   Set `AUTOSHORTS_VOICE` to another installed voice; list with `say -v '?'`.
4. `ffprobe` measures actual narration. Each scene gets 180 ms of lead silence
   and at least 300 ms of trailing silence, rounded to a whole 30 fps frame.
5. FFmpeg applies a subtle alternating zoom and pan to the still background.
   Pillow titles and progress indicators remain stationary for readability.
   Full narration captions appear only during that scene's speech interval.
   Captions are scene-level, **not word-aligned**; no forced alignment is claimed.
6. Join video segments and encode AAC once to avoid per-scene AAC padding drift.
   Final output is 1080×1920, 30 fps, H.264/AAC, yuv420p, and `+faststart`.
7. Check streams and timing, then decode the entire MP4 with FFmpeg before
   replacing the destination. Temporary files are cleaned on success and errors.

For `output/sky.mp4`, the generator also saves:

- `output/sky.json`: topic, script source, every scene's text and visual guidance,
  measured timings, photo source, and credits. No credentials are written.
- `output/sky.srt`: full narration captions with measured scene speech intervals.

MP4 publication uses an atomic replacement after validation. Sidecars are
replaced immediately afterward; all three files are not one atomic transaction.
Failed media generation preserves any previous MP4. Errors return a nonzero
exit status. Run from a normal macOS terminal if a sandbox blocks speech services.

## Validation

```sh
python -m unittest discover -s tests -v
ffprobe -v error -show_streams -show_format -of json output/sky.mp4
ffmpeg -v error -xerror -i output/sky.mp4 -f null -
ffprobe -v error -show_streams -show_format -of json output/volcanoes.mp4
ffmpeg -v error -xerror -i output/volcanoes.mp4 -f null -
```

Unit tests use mocked API responses to verify arbitrary input routing, response
validation, outages, image retrieval, credits, and offline rejection. They do
not establish live API availability or AI factual accuracy. The two real demo
renders use the explicitly authored offline sky and volcano scripts when no
credentials are present. Their manifests make the different explanations and
visual queries inspectable. Live arbitrary-topic and stock-photo generation
require configured keys. Additional real OpenRouter-generated demos are saved
as `output/solar-ai.mp4` and `output/volcanoes-ai.mp4`, with JSON/SRT sidecars.
Their script sources are `openrouter:openrouter/free`; Pexels photo retrieval
remains mock-tested because a Pexels key is not configured.

## Limitations and future improvements

AI explanations need editorial review; factual accuracy is not automatically
verified. Photo relevance depends on stock availability. Runtime varies with
the script and voice; roughly 30 seconds is a target. Visuals are still images
with motion, not generated video. Next steps: source-backed scripts, better
image ranking and focal-point cropping, word-aligned captions, and curated
visual diagrams. Keep rendering reliable before adding a web interface.
