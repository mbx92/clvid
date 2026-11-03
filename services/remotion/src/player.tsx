import {createRoot} from 'react-dom/client';
import {flushSync} from 'react-dom';
import {Player, type PlayerRef} from '@remotion/player';
import {CaptionScene} from './Captions';
import {clampFrame, frameCount} from './timing';
import type {CaptionProps} from './types';
import {videoMotion} from './effects';

function videoStyle(props: CaptionProps, frame: number) {
  return videoMotion(props.style.remotion_effects, clampFrame(frame, props.durationMs, props.fps) * 1000 / props.fps, props.durationMs);
}

export interface PreviewHandle {
  updateProps(props: CaptionProps): void;
  setFrame(frame: number): void;
  destroy(): void;
}

function mount(element: HTMLElement, initialProps: CaptionProps): PreviewHandle {
  const root = createRoot(element);
  let props = initialProps;
  let player: PlayerRef | null = null;
  let desiredFrame = 0;
  let disposed = false;
  let errorQueued = false;
  const notifyFailure = () => {
    if (disposed || errorQueued) return;
    errorQueued = true;
    // Vue may unmount us in response. Defer until React's commit has finished.
    queueMicrotask(() => {if (!disposed) element.dispatchEvent(new CustomEvent('clipper-remotion-error'));});
  };
  const seek = () => player?.seekTo(clampFrame(desiredFrame, props.durationMs, props.fps));
  const ref = (value: PlayerRef | null) => {player = value; if (value) seek();};
  const draw = () => flushSync(() => root.render(<Player ref={ref} component={CaptionScene} inputProps={props}
    durationInFrames={frameCount(props.durationMs, props.fps)} fps={props.fps}
    compositionWidth={props.width} compositionHeight={props.height}
    controls={false} autoPlay={false} loop={false} clickToPlay={false}
    numberOfSharedAudioTags={0} initiallyMuted={true} browserMediaControlsBehavior={{mode: 'do-nothing'}}
    doubleClickToFullscreen={false} spaceKeyToPlayOrPause={false}
    showVolumeControls={false} allowFullscreen={false} moveToBeginningWhenEnded={false}
    errorFallback={() => {notifyFailure(); return <div role="alert" style={{padding: 24, color: '#fff', background: '#7f1d1d', fontFamily: 'sans-serif', fontSize: 32}}>Pratinjau Remotion gagal. Muat ulang halaman atau pilih renderer Standar.</div>;}}
    style={{width: '100%', height: '100%', backgroundColor: 'transparent', pointerEvents: 'none'}}
  />));
  draw();
  return {
    updateProps(next) {if (!disposed) {props = next; draw(); seek();}},
    setFrame(frame) {if (!disposed) {desiredFrame = frame; seek();}},
    destroy() {if (!disposed) {disposed = true; player = null; root.unmount();}},
  };
}

declare global {
  interface Window {ClipperRemotion: {mount: typeof mount; videoStyle: typeof videoStyle}}
}
window.ClipperRemotion = {mount, videoStyle};
