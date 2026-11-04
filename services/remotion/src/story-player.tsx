import {createRoot} from 'react-dom/client';
import {Player, type PlayerRef} from '@remotion/player';
import {StoryScene, storyDuration, type StoryProps} from './StoryScene';
function mount(element: HTMLElement, initial: StoryProps) {
  const root = createRoot(element);
  let props = initial;
  let player: PlayerRef | null = null;
  let desiredFrame = 12;
  const seek = () => player?.seekTo(Math.max(0, Math.min(storyDuration(props) - 1, desiredFrame)));
  const draw = () => root.render(<Player ref={ref => {player = ref; if (ref) seek();}} component={StoryScene} inputProps={props} durationInFrames={storyDuration(props)} fps={30} initialFrame={12}
    compositionWidth={props.width} compositionHeight={props.height} controls loop={false} autoPlay={false}
    style={{width: '100%', height: '100%'}} errorFallback={() => <div role="alert" style={{padding: 20, background: '#fff', color: '#922'}}>Preview gagal. Periksa aset lalu muat ulang.</div>}/>);
  draw();
  return {updateProps(next: StoryProps) {desiredFrame = player?.getCurrentFrame() ?? desiredFrame; props = next; draw();}, setFrame(frame: number) {desiredFrame = frame; player?.pause(); seek();}, destroy() {root.unmount();}};
}
declare global {interface Window {ClipperStory: {mount: typeof mount}}}
window.ClipperStory = {mount};
