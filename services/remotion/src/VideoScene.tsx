import {AbsoluteFill, OffthreadVideo, useCurrentFrame} from 'remotion';
import {CaptionScene} from './Captions';
import type {VideoProps} from './types';
import {videoMotion} from './effects';

export function VideoScene(props: VideoProps) {
  const frame = useCurrentFrame();
  const motion = videoMotion(props.style.remotion_effects, frame * 1000 / props.fps, props.durationMs);
  return <AbsoluteFill style={{backgroundColor: '#000', overflow: 'hidden'}}>
    <AbsoluteFill style={motion}>
      {props.videoUrl && <OffthreadVideo src={props.videoUrl} muted style={{width: '100%', height: '100%', objectFit: 'fill'}} />}
    </AbsoluteFill>
    <CaptionScene {...props} />
  </AbsoluteFill>;
}
