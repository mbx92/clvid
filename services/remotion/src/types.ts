export interface Cue {
  start_ms: number;
  end_ms: number;
  text: string;
  word_spans?: WordSpan[];
}

export interface WordSpan {start_ms: number; end_ms: number; start_word: number; end_word: number}

export interface TitleEffect {
  enabled: boolean;
  text: string;
  duration_ms: number;
}

export interface ZoomEffect {
  start_ms: number;
  end_ms: number;
  scale: number;
  x: number;
  y: number;
}

export interface RemotionEffects {
  transition_in: 'none' | 'fade' | 'slide';
  transition_out: 'none' | 'fade' | 'slide';
  transition_ms: number;
  intro: TitleEffect;
  outro: TitleEffect;
  zooms: ZoomEffect[];
}

export const defaultEffects: RemotionEffects = {
  transition_in: 'none', transition_out: 'none', transition_ms: 300,
  intro: {enabled: false, text: '', duration_ms: 1200},
  outro: {enabled: false, text: '', duration_ms: 1200},
  zooms: [],
};

export interface SubtitleStyle {
  enabled: boolean;
  renderer: 'remotion';
  remotion_template: 'minimal' | 'gaming' | 'cinematic' | 'podcast';
  remotion_effects?: RemotionEffects;
  display_mode: 'sentence' | 'words';
  animation: 'none' | 'fade' | 'pop' | 'rise';
  animation_ms: number;
  font_size: number;
  position: 'top' | 'bottom';
  background: boolean;
  safe_margin: number;
  auto_fit: boolean;
  bold: boolean;
  italic: boolean;
  uppercase: boolean;
  text_color: string;
  outline_color: string;
  background_color: string;
  outline_width: number;
  shadow: number;
}

export type CaptionProps = {
  cues: Cue[];
  style: SubtitleStyle;
  durationMs: number;
  width: number;
  height: number;
  fps: number;
  fontUrl?: string;
};

export type VideoProps = CaptionProps & { videoUrl: string };

export const defaultStyle: SubtitleStyle = {
  enabled: true,
  renderer: 'remotion',
  remotion_template: 'gaming',
  remotion_effects: defaultEffects,
  display_mode: 'sentence',
  animation: 'none',
  animation_ms: 180,
  font_size: 52,
  position: 'bottom',
  background: true,
  safe_margin: 0.15,
  auto_fit: true,
  bold: false,
  italic: false,
  uppercase: false,
  text_color: '#FFFFFF',
  outline_color: '#111111',
  background_color: '#000000',
  outline_width: 2.5,
  shadow: 0,
};

export const defaultProps: VideoProps = {
  cues: [], style: defaultStyle, durationMs: 1000,
  width: 1080, height: 1920, fps: 30, videoUrl: '',
};
