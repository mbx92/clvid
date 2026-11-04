import {useEffect, useState, type CSSProperties} from 'react';
import {AbsoluteFill, continueRender, delayRender, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {captionLayout} from './layout';
import {captionMotion, cueAtFrame} from './timing';
import type {CaptionProps, WordSpan} from './types';
import {TitleOverlay} from './TitleOverlay';

const fontLoads = new Map<string, Promise<void>>();
function loadFont(url: string) {
  if (!fontLoads.has(url)) {
    const face = new FontFace('Clipper Noto Sans', `url(${JSON.stringify(url)})`, {weight: '400', style: 'normal'});
    fontLoads.set(url, face.load().then(loaded => {document.fonts.add(loaded);}));
  }
  return fontLoads.get(url)!;
}

export function useCaptionFont(url: string) {
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
    lineHeight: style.remotion_template === 'podcast' ? 1.16 : 1.25, textAlign: 'center', whiteSpace: 'pre',
    backgroundColor: style.background ? `${style.background_color}b7` : 'transparent',
    padding: style.background ? 8 * scale : 0,
    borderRadius: style.background && style.remotion_template !== 'minimal' ? 12 * scale : 0,
    WebkitTextStroke: style.background ? '0px' : `${style.outline_width * scale}px ${style.outline_color}`,
    paintOrder: 'stroke fill',
    textShadow: style.shadow ? `${style.shadow * scale}px ${style.shadow * scale}px 0 #0008` : 'none',
  };
  return <div style={appearance} data-caption-template={style.remotion_template}>{style.remotion_template === 'podcast'
    ? <PodcastCaption text={layout.text} originalText={text} scale={scale} wordSpans={cue.word_spans} timeMs={frame * 1000 / fps} /> : layout.text}</div>;
}

/** Preserve wraps (including a long word split across lines) and token identity. */
export function podcastParts(text: string, originalText: string) {
  const lengths = originalText.trim().split(/\s+/u).map(word => word.length);
  let index = 0, offset = 0;
  return (text.match(/\s+|\S+/gu) || []).map(part => {
    if (/^\s/u.test(part)) return {text: part, word: null};
    while (index < lengths.length - 1 && offset >= lengths[index]!) { offset -= lengths[index]!; index++; }
    offset += part.length;
    return {text: part, word: index};
  });
}

/** Keep the whole sentence in place; only the observed spoken token is boxed. */
export function PodcastCaption({text, originalText = text, scale, wordSpans = [], timeMs}: {
  text: string; originalText?: string; scale: number; wordSpans?: WordSpan[]; timeMs: number;
}) {
  const active = wordSpans.find(span => span.start_ms <= timeMs && timeMs < span.end_ms);
  return <>{podcastParts(text, originalText).map((part, index) => {
    if (part.word === null) return part.text;
    const highlighted = !!active && part.word >= active.start_word && part.word < active.end_word;
    return <span key={index} data-podcast-word={part.word} data-active={highlighted}
      style={{position: 'relative', display: 'inline-block', isolation: 'isolate'}}>
      {highlighted && <span aria-hidden="true" data-podcast-highlight style={{position: 'absolute', zIndex: -1,
        inset: `${-2 * scale}px ${-8 * scale}px`, background: '#FFFFFF',
        border: `${2 * scale}px solid #111111`, borderRadius: 5 * scale,
        transform: 'rotate(-3deg)', boxShadow: `0 ${2 * scale}px ${2 * scale}px #0005`}} />}
      {part.text}</span>;
  })}</>;
}
