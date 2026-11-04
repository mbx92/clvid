# Story Studio

Open `/studio` to create a video without a source clip. The editor tabs are
Naskah, Adegan, Produksi, Gaya, and Hasil. DeepSeek is optional; the paragraph splitter and
scene editor work without an API key. The existing DeepSeek environment settings
are reused. Produksi defaults to local image/speech models; DeepSeek still handles
the explicitly selected AI storyboard and theme actions. Paragraph/table import,
local generation, synchronization and export can run without paid API calls.

The Adegan tab can now fill empty visuals locally or ask DeepSeek to plan
illustrations for all eligible scenes or the selected scene. Both return a
versioned proposal for review and application. Visual-only AI changes preserve
every other field, including narration, timing, theme and recorded audio.
Uploaded images/video take priority and are excluded from illustration planning.

Scenes have a backward-compatible `visual` recipe: `none`, `coffee_compare`,
`coffee_flat`, `coffee_pair`, `coffee_separate`, `coffee_peaberry`, `coffee_reveal`,
`diagram`, `comparison` or `steps`. The six coffee recipes illustrate the bean
quiz, side view, two-seed fruit, separation, single-seed fruit and answer reveal.
Table import fills these automatically when their visual directions match.
General recipes support up to four labeled icons: bean, cup, leaf, water, sun,
person, box, check, question. Motion can be gentle or still; reveal delay is
editable. These are animated SVG illustrations, not generated photographs.

`StoryIllustration.tsx` is shared by preview and export. Extend its catalog,
Python `Visual` schema, frontend `visualOptions` / `visualIcons` and server
manifest validator together when adding new illustration types. AI output is
limited to these recipes. Story renderer version 2 includes illustrations;
version 3 adds timed captions; legacy version 1/2 snapshots remain renderable.

Timed tables can be pasted as Markdown or as tab-separated browser clipboard
text. Use Waktu, Visual dan suara, and Narasi siap rekam columns. “Impor tabel
storyboard” creates a proposal without AI, preserving row durations and visual
directions. AI generation parses the same rows first: when preserving the script,
each narration is copied from its source row, while AI can enrich titles and
screen text. Citations and formatting are not spoken; the original pasted source
is retained in the script. Ranges must be contiguous from zero and respect the
same scene/video duration limits.

Each storyboard is a versioned document with 1–20 scenes and at most 180 seconds.
Edits use optimistic version checks. AI responses are validated and stored as
job proposals; applying a proposal is an explicit editor action. An obsolete
proposal cannot replace a newer saved version or unsaved edits. “Pertahankan
naskah” verifies narration text against the original, ignoring whitespace only.
Style prompts may change the theme, but cannot change scenes.

Themes contain validated colors, typography, alignment, title size, and entrance
motion. Three built-ins live in `app/story/schemas.py` (`PRESETS`). Users can save
and remove personal themes at any time through the Gaya tab. Templates are copied
into documents, so changing or deleting a saved theme never alters existing
videos. Prompt output is data, never executable React, JavaScript, CSS or URLs.

To introduce a new scene layout, extend `Scene.layout` in the Python schema, the
`StoryShot` type and layout rendering in `StoryScene.tsx`, the server manifest
validator, and the editor selector/types. Add representative render coverage and
bump the story renderer version in the render queue and handler. Existing
caption-only Remotion compositions remain separate.

Images (PNG/JPEG), videos (MP4), and recordings (MP3/WAV/M4A) are uploaded per
storyboard, normalized with FFmpeg, and ownership-checked before save and export.
Limits: 60 MB, 180 seconds, 4096 pixels per side. Video source audio is muted;
use a recording for each scene. Manual scene duration controls audio trimming.
Production extends a scene when necessary to finish its narration (at most 30
seconds per scene, 180 seconds total); it refuses audio that exceeds those limits
or its underlying video. It never silently speeds up or truncates generated voice.

Produksi can fill missing images and narration, or synchronize existing audio.
Whole-story generation retains existing uploaded assets and selected SVG illustrations;
the explicit Images action can generate photos for illustrated scenes. Replacing uploaded media requires
selecting one scene and explicitly enabling replacement. Every result is a
versioned proposal, with generated assets available for image/audio preview before
application. Model/quality settings are frozen in the job snapshot. Successful raw
provider responses are persisted before normalization and reused on retry; completed
assets are reused too. Worker-loss recovery can retry local production. It does not
automatically repeat cloud production because a request may have been billed
without returning a response. Manual retry
after that error may incur provider charges. Cancellation cannot retract a request
already sent to a provider.

Subtitle synchronization runs local Whisper over the full audio with word
timestamps. It maps matching narration to the observed speech windows and preserves
silence. Small spelling differences use their observed phrase span and produce a
review warning; missing phrases or a missing narration tail fail explicitly. Empty
narration is transcribed from the recording, with review warnings for filtered
segments or a long unverified tail. These are ASR timestamps, not perfect forced
alignment or translated word-level karaoke. Users can edit cue text and timing.

Scenes store `captions`, `caption_audio_id`, and `caption_narration`. Preview and
SRT use those times only while audio and narration still match; changing a source
clears timing in the editor. Overlap and out-of-bounds cues are rejected. The old
evenly distributed narration remains the fallback for documents without timed
captions. Hidden captions are omitted from both video and SRT.

## Provider configuration

`STORY_MEDIA_PROVIDER=local` is the default. On the NVIDIA Docker installation run
`powershell -File scripts/setup_story_local.ps1` once. The helper downloads pinned,
checksum-verified weights into `.runtime/story-models` on the repository drive,
builds the isolated inference runtime, enables `STORY_LOCAL_ENABLED=true`, and
recreates the services. `-ModelsOnly` only downloads/verifies models. Downloads are
about 3.5 GB plus the Docker runtime.

The GPU compose file builds `/opt/story-local`, a separate Python environment from
Whisper. Images use [Stable Diffusion 1.5](https://huggingface.co/stable-diffusion-v1-5/stable-diffusion-v1-5)
at 512×768, 768×512 or 512×512 with 20 sampling steps. Indonesian visual directions
are translated on CPU by [Marian ID–EN](https://huggingface.co/Helsinki-NLP/opus-mt-id-en)
before image generation. Short prompts work best; the image model has a limited
prompt length and can make mistakes in counts, anatomy and diagrams. Use the
existing SVG illustrations or your own media when exact scientific details matter.

Indonesian narration uses the 6-layer [Pocket TTS Indonesian](https://huggingface.co/anak10thn/pocket-tts-indonesian)
model on CPU, with two supplied Common Voice reference recordings. The English
option uses eSpeak NG and has a more synthetic sound. Numbers in Indonesian are
expanded for speech while the original narration stays in the document. Long or
unclear pronunciation can still fail audio/text validation; revise the narration
or select another voice and review the recording before applying it.

Model licenses/cards and attribution are stored beside their weights. SD1.5 uses
CreativeML OpenRAIL-M; Marian ID–EN uses Apache 2.0; Pocket Indonesian is CC BY 4.0
with credit to anak10thn, Kyutai Pocket TTS and the LEMAS Project. Voice reference
files are Common Voice 22.0 CC0. Generated speech assets retain attribution metadata.

Inference runs offline in short-lived child processes, releasing GPU memory before
Whisper runs. Models are mounted read-only. Cancellation terminates the child.
Local mode never switches to a paid provider, even if a cloud key is configured.
The UI distinguishes installed models from unavailable generation. For CPU-only
custom builds, set `WITH_LOCAL_STUDIO=1`, `WITH_CUDA=0` and
`STORY_LOCAL_IMAGE_DEVICE=cpu`; image generation will be slower.

`.env.example` documents model root, inference Python, image steps/device, prompt
language and timeout. The default prompt language is Indonesian; English visual
directions are also accepted. `STORY_LOCAL_PROMPT_LANGUAGE=en` explicitly disables
translation. No API key is needed for local assets, synchronization or export.

Cloud remains optional: explicitly select `STORY_MEDIA_PROVIDER=openai`, set
`OPENAI_API_KEY` in the backend `.env`, then recreate API and workers. Never expose
the key in frontend variables. Cloud model defaults are `gpt-image-1-mini` and
`gpt-4o-mini-tts`; account access and provider billing apply only in this mode.

The image adapter follows the [Images API](https://developers.openai.com/api/reference/resources/images/methods/generate).
The optional cloud [Speech API](https://developers.openai.com/api/reference/resources/audio/subresources/speech/methods/create)
is scheduled for retirement on January 6, 2027 according to the documentation
checked November 4, 2026. Migrate the isolated speech adapter to its successor
before that date; changing a model name alone does not migrate API interfaces.

The same `StoryScene` is used by the interactive player and MP4 renderer.
Exports use immutable job snapshots and produce 720×1280, 1280×720 or 1080×1080
H.264/AAC video and SRT. Render assets are copied into an attempt directory and
served only through tokenized localhost URLs. Existing job retry/cancel and
ownership controls apply. API migrations include `94de30010001`.

Verification: `test_storyboard.py` covers persistence, ownership, asset and
document validation, proposals and idempotency; `test_story_media.py` runs real
renders in the built worker; `story-studio.spec.ts` covers editor, templates,
proposal review and export requests with isolated mocked API data. Provider contract
tests mock HTTP; they do not establish live account access. Production integration
tests cover asset checkpoints, stale proposals, idempotency, and duration limits.
