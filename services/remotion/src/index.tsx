import {Composition, registerRoot} from 'remotion';
import {VideoScene} from './VideoScene';
import {defaultProps} from './types';
import {frameCount} from './timing';

const Root = () => <Composition id="ClipperVideo" component={VideoScene}
  durationInFrames={30} fps={30} width={1080} height={1920} defaultProps={defaultProps}
  calculateMetadata={({props}) => ({durationInFrames: frameCount(props.durationMs, props.fps), fps: props.fps, width: props.width, height: props.height})} />;

registerRoot(Root);
