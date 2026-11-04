import {AbsoluteFill, Audio, Img, OffthreadVideo, Sequence, interpolate, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {useCaptionFont} from './Captions';
import {StoryIllustration, type StoryVisual} from './StoryIllustration';
import {storyCaptionAtFrame, type StoryCaptionSource} from './story-captions';
export {captionChunks} from './story-captions';

export type StoryTheme = {background: string; foreground: string; accent: string; font: 'sans'|'serif'|'mono'; motion: 'fade'|'rise'|'zoom'|'none'; align: 'left'|'center'; font_size: number; uppercase: boolean};
export type StoryShot = StoryCaptionSource & {id: string; layout: 'title'|'split'|'quote'|'stat'; title: string; text: string; asset_id: string|null; media_start_ms: number; visual?: StoryVisual};
export type StoryProps = {document: {theme: StoryTheme; scenes: StoryShot[]}; assets: Record<string, {url: string; kind: string}>; width: number; height: number; fps: number; fontUrl?: string};
export const storyDuration = (props: StoryProps) => props.document.scenes.reduce((n, s) => n + Math.round(s.duration_ms * props.fps / 1000), 0);
function Shot({shot, theme, assets, index}: {shot: StoryShot; theme: StoryTheme; assets: StoryProps['assets']; index: number}) {
  const frame = useCurrentFrame();
  const {width, height, fps} = useVideoConfig();
  const scale = Math.min(width, height) / 1080;
  const frames = Math.round(shot.duration_ms * fps / 1000);
  const entrance = theme.motion === 'none' ? 1 : interpolate(frame, [0, Math.min(12, frames / 3)], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const asset = shot.asset_id ? assets[shot.asset_id] : undefined;
  const audio = shot.audio_id ? assets[shot.audio_id] : undefined;
  const illustrated = !asset && shot.visual && shot.visual.kind !== 'none';
  const split = shot.layout === 'split';
  const landscape = width > height;
  const contentStyle = {opacity: entrance, transform: theme.motion === 'rise' ? `translateY(${(1 - entrance) * 45 * scale}px)` : theme.motion === 'zoom' ? `scale(${.92 + .08 * entrance})` : undefined};
  const mediaStyle = {width: '100%', height: '100%', objectFit: 'cover' as const};
  const caption = storyCaptionAtFrame(shot, frame, fps);
  const baseTitle = theme.font_size * scale * (shot.title.length > 70 ? .75 : 1) * (shot.layout === 'stat' ? 1.4 : 1);
  const baseBody = (shot.text.length > 200 ? 30 : 36) * scale;
  const areaWidth = (illustrated || split && asset) && landscape ? width * .45 - 64 * scale : width - 128 * scale;
  const areaHeight = illustrated && !landscape ? height * .38 - 230 * scale : split && asset && !landscape ? height * .47 - 230 * scale : height - 390 * scale;
  const estimate = Math.max(1, Math.ceil(shot.title.length * baseTitle * .62 / areaWidth)) * baseTitle * 1.16
    + (shot.text ? Math.ceil(shot.text.length * baseBody * .58 / areaWidth) * baseBody * 1.55 + 28 * scale : 0)
    + (shot.layout === 'quote' ? 96 * scale : 0);
  const fit = Math.min(1, Math.sqrt(Math.max(60, areaHeight) / Math.max(1, estimate)) * .94);
  const titleSize = baseTitle * fit;
  return <AbsoluteFill data-story-scene={shot.id} style={{background: theme.background, color: theme.foreground, overflow: 'hidden'}}>
    {asset && <div style={{position: 'absolute', inset: 0, ...(split ? landscape ? {right: '50%'} : {bottom: '52%'} : {}), opacity: split ? 1 : .32}}>
      {asset.kind === 'image' ? <Img src={asset.url} style={mediaStyle}/> : <OffthreadVideo src={asset.url} muted startFrom={Math.round(shot.media_start_ms * fps / 1000)} style={mediaStyle}/>}
    </div>}
    {illustrated && shot.visual && <div style={{position:'absolute', left:'5%', right:landscape?'51%':'5%', top:landscape?'16%':'11%', bottom:landscape?'22%':'40%'}}><StoryIllustration visual={shot.visual} frame={frame} fps={fps} accent={theme.accent}/></div>}
    <div style={{position: 'absolute', top: 54 * scale, left: 64 * scale, right: 64 * scale, display: 'flex', justifyContent: 'space-between', fontSize: 20 * scale, letterSpacing: 3 * scale, color: theme.accent}}><span>CLIP {String(index + 1).padStart(2, '0')}</span><span style={{width: 70 * scale, height: 4 * scale, background: theme.accent, marginTop: 12 * scale}}/></div>
    <div style={{position: 'absolute', inset: `${160 * scale}px ${64 * scale}px ${230 * scale}px`, display: 'flex', flexDirection: 'column', justifyContent: 'center', textAlign: theme.align,
      ...(illustrated ? landscape ? {left:'55%'} : {top:'62%'} : split && asset ? landscape ? {left: '55%'} : {top: '53%'} : {}), ...contentStyle}}>
      {shot.layout === 'quote' && <div style={{fontSize: 120 * scale, color: theme.accent, lineHeight: .8}}>&ldquo;</div>}
      <h1 style={{fontSize: titleSize, lineHeight: 1.16, margin: 0, letterSpacing: -1 * scale, overflowWrap: 'anywhere', textTransform: theme.uppercase ? 'uppercase' : 'none', color: shot.layout === 'stat' ? theme.accent : theme.foreground}}>{shot.title}</h1>
      {shot.text && <p style={{fontSize: baseBody * fit, lineHeight: 1.55, margin: `${28 * scale}px 0 0`, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere'}}>{shot.text}</p>}
    </div>
    {shot.show_caption && caption && <div style={{position: 'absolute', bottom: 90 * scale, left: '8%', right: '8%', textAlign: 'center', fontFamily: 'Clipper Noto Sans', fontSize: 34 * scale, lineHeight: 1.45, color: '#fff'}}><span style={{background: '#000c', padding: `${8 * scale}px ${14 * scale}px`, boxDecorationBreak: 'clone'}}>{caption}</span></div>}
    {audio && <Audio src={audio.url}/>}
    <div style={{position: 'absolute', bottom: 0, left: 0, height: 6 * scale, width: `${(frame + 1) / frames * 100}%`, background: theme.accent}}/>
  </AbsoluteFill>;
}

export function StoryScene(props: StoryProps) {
  const ready = useCaptionFont(props.fontUrl || staticFile('fonts/NotoSans-Regular.ttf'));
  if (!ready) return null;
  const fontFamily = {sans: 'Clipper Noto Sans', serif: 'Georgia, serif', mono: 'monospace'}[props.document.theme.font];
  let offset = 0;
  return <AbsoluteFill style={{fontFamily, background: props.document.theme.background}}>{props.document.scenes.map((shot, index) => {
    const from = offset, duration = Math.round(shot.duration_ms * props.fps / 1000);
    offset += duration;
    return <Sequence key={shot.id} from={from} durationInFrames={duration}><Shot shot={shot} theme={props.document.theme} assets={props.assets} index={index}/></Sequence>;
  })}</AbsoluteFill>;
}

export const defaultStory: StoryProps = {width: 720, height: 1280, fps: 30, assets: {}, document: {theme: {background: '#132923', foreground: '#ffffff', accent: '#d9f279', font: 'sans', motion: 'rise', align: 'left', font_size: 72, uppercase: false}, scenes: [{id: 'intro', layout: 'title', title: 'Cerita Anda dimulai di sini', text: '', narration: '', duration_ms: 5000, asset_id: null, audio_id: null, media_start_ms: 0, show_caption: true}]}};
