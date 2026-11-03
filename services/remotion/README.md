# Clipper Remotion renderer

The same React caption layer powers the Vue editor overlay and server MP4 export.
The player has no video or audio; Vue drives its frame using the existing video
clock. Exports compose an already cropped, muted `OffthreadVideo` and that layer.
Python retains the original audio and muxes it into the final export.

## Build and checks

Use Node 24 or newer, from this directory:

```sh
npm ci
npm run typecheck
npm test
npm run build
npm run browser:install
```

Build needs `../backend/fonts/NotoSans-Regular.ttf` and its `OFL.txt`. It outputs
`dist/composition`, `dist/player.js`, and `dist/THIRD-PARTY-NOTICES.txt`. Ship the
notices with the browser bundle. Tests read the shared wrapping fixtures at
`../../tests/fixtures/subtitle-layout.json`; they do not call external services.

Install Chromium at image build time. On Debian, use the libraries listed in the
[Remotion Docker guide](https://www.remotion.dev/docs/docker). `remotion browser
ensure` stores Chrome under `node_modules/.remotion/chrome-headless-shell/` in this
package. Set `REMOTION_BROWSER_EXECUTABLE` to the installed executable; this CLI
deliberately refuses to download a browser during a render job.

## Runtime

```sh
REMOTION_BROWSER_EXECUTABLE=/opt/remotion/chrome-headless-shell node /opt/remotion/render.mjs /media/job/render.json
```

Manifest version 1 contains `videoPath`, `outputPath`, `durationMs`, `width`,
`height`, `fps`, `cues`, and `style`. Supported portrait sizes are 720×1280 and
1080×1920 at 30 fps. Cue timestamps are local integer milliseconds. Style uses
the existing subtitle fields plus `renderer: "remotion"` and
`remotion_template: "minimal" | "gaming" | "cinematic"`.

Both paths must stay inside the manifest's directory, including after resolving
symlinks. The source must be an existing MP4 and the output must not exist. The
CLI serves only the opened video through a random, tokenized loopback URL with
byte-range support. It produces a muted H.264/yuv420p MP4 and emits progress as
`segment_end_ms=<milliseconds>`. Failures emit only `remotion_error=<code>`;
SIGTERM/SIGINT cancel rendering and clean up the partial output.

## Browser bridge

Load `player.js` once. `window.ClipperRemotion.mount(element, props)` returns
`updateProps(props)`, `setFrame(frame)`, and `destroy()`. Props are `cues`, `style`,
`durationMs`, `width`, `height`, `fps`, and optionally a local `fontUrl`. Mount and
updates commit before returning; a following seek uses the latest props. The
overlay is transparent and has no controls, autoplay, media elements or audio.
Frame timing is deterministic when playing, pausing, or seeking backwards.
An asynchronous composition/font error dispatches `clipper-remotion-error` on
the mount element after React commits; Vue can then safely destroy the player
and show its own localized message. No error payload exposes media data.

`window.ClipperRemotion.videoStyle(props, frame)` returns the exact deterministic
`opacity`, `transform`, and `transformOrigin` applied to the prepared video in the
export. Apply it to the native video/framing layer only, inside an overflow-hidden
container; keep the Remotion overlay separate. The player itself stays media-free.

The Minimal template preserves the chosen ordinary animation. Gaming applies a
spring entrance; Cinematic applies a gentle fade and movement. All templates
retain the user's typography, placement, and colors. `style.remotion_effects`
adds clip-relative entrance/exit transitions (`none`, `fade`, `slide`), intro/outro
title overlays, and up to 20 zoom ranges. `transition_ms` defaults to 300; each
title is `{enabled, text, duration_ms}` (default disabled, empty text, 1200 ms).
Each zoom is `{start_ms, end_ms, scale, x, y}`, with scale 1–2 and normalized focus
coordinates. Overlapping zooms use the strongest interpolated scale, with smooth
ramps no longer than 250 ms. On a very short clip where titles overlap, the outro
takes precedence. Title text is limited to 80 Unicode code points. Enabled titles
need text for export; the preview allows incomplete drafts without showing them.

All effects stay inside the existing clip duration and preserve audio. Transitions
and zoom affect only the video; titles remain available when captions are disabled.
Speech recognition, cue editing, and the surrounding timeline belong to Clipper.

Remotion has its own [license](https://www.remotion.pro/license). Dependency and
font licenses are included in the generated third-party notices.
