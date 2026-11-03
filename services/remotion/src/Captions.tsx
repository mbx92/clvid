import {useEffect, useState, type CSSProperties} from 'react';
import {AbsoluteFill, continueRender, delayRender, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {captionLayout} from './layout';
import {captionMotion, cueAtFrame} from './timing';
import type {CaptionProps} from './types';
import {TitleOverlay} from './TitleOverlay';

const fontLoads = new Map<string, Promise<void>>();
function loadFont(url: string) {
  if (!fontLoads.has(url)) {
    const face = new FontFace('Clipper Noto Sans', `url(${JSON.stringify(url)})`, {weight: '400', style: 'normal'});
    fontLoads.set(url, face.load().then(loaded => {document.fonts.add(loaded);}));
  }
  return fontLoads.get(url)!;
}

function useCaptionFont(url: string) {
  const [handle] = useState(() => delayRender('Loading local subtitle font'));
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let active = true;
    setReady(false);
    setFailed(false);
    loadFont(url).then(() => {
      if (active) setReady(true);
      continueRender(handle);
    }, () => {if (active) setFailed(true); continueRender(handle);});
    return () => {active = false; continueRender(handle);};
  }, [url, handle]);
  if (failed) throw new Error('Subtitle font unavailable');
  return ready;
}

/** The exact same transparent layer is used by the Vue preview and MP4 scene. */
export function CaptionScene(props: CaptionProps) {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const fontReady = useCaptionFont(props.fontUrl || staticFile('fonts/NotoSans-Regular.ttf'));
  if (!fontReady) return null;
  return <AbsoluteFill style={{pointerEvents: 'none', overflow: 'hidden'}}>
    <CaptionLayer {...props} frame={frame} fps={fps} width={width} height={height} />
    <TitleOverlay style={props.style} timeMs={frame * 1000 / fps} durationMs={props.durationMs} width={width} />
  </AbsoluteFill>;
}

function CaptionLayer(props: CaptionProps & {frame: number}) {
  if (!props.style.enabled) return null;
  const {frame, fps, width, height} = props;
  const cue = cueAtFrame(props.cues, frame, fps);
  if (!cue) return null;
  const style = props.style;
  const text = style.uppercase ? cue.text.toUpperCase() : cue.text;
  const layout = captionLayout(text, style.font_size, style.auto_fit);
  if (layout.tooLong) throw new Error('Subtitle exceeds available layout');
  const scale = width / 1080;
  const motion = captionMotion(style, frame * 1000 / fps - cue.start_ms, cue.end_ms - cue.start_ms, fps);
  const appearance: CSSProperties = {
    position: 'absolute', left: '50%',
    [style.position === 'top' ? 'top' : 'bottom']: height * style.safe_margin,
    width: 'max-content', maxWidth: '80%', boxSizing: 'border-box',
    transform: `translateX(-50%) translateY(${motion.y * scale}px) scale(${motion.scale})`,
    transformOrigin: style.position === 'top' ? 'center top' : 'center bottom',
    opacity: motion.opacity,
    color: style.text_color,
    fontFamily: '"Clipper Noto Sans", sans-serif',
    fontSize: layout.fontSize * scale,
    fontWeight: style.bold ? 700 : 400,
    fontStyle: style.italic ? 'italic' : 'normal',
    fontSynthesis: 'weight style',
    lineHeight: 1.25, textAlign: 'center', whiteSpace: 'pre',
    backgroundColor: style.background ? `${style.background_color}b7` : 'transparent',
    padding: style.background ? 8 * scale : 0,
    borderRadius: style.background && style.remotion_template !== 'minimal' ? 12 * scale : 0,
    WebkitTextStroke: style.background ? '0px' : `${style.outline_width * scale}px ${style.outline_color}`,
    paintOrder: 'stroke fill',
    textShadow: style.shadow ? `${style.shadow * scale}px ${style.shadow * scale}px 0 #0008` : 'none',
  };
  return <div style={appearance}>{layout.text}</div>;
}
