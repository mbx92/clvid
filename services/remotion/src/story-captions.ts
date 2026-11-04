export type StoryCaption = {start_ms: number; end_ms: number; text: string};
export type StoryCaptionSource = {
  narration: string;
  duration_ms: number;
  audio_id: string|null;
  show_caption: boolean;
  captions?: StoryCaption[];
  caption_audio_id?: string|null;
  caption_narration?: string;
};

export function captionChunks(text: string): string[] {
  const chunks: string[] = [];
  for (const word of text.trim().split(/\s+/u).filter(Boolean)) {
    if (!chunks.length || chunks[chunks.length - 1].length + word.length + 1 > 70) chunks.push(word);
    else chunks[chunks.length - 1] += ' ' + word;
  }
  return chunks;
}

export function hasTimedStoryCaptions(shot: StoryCaptionSource): boolean {
  return Boolean(shot.captions?.length && shot.audio_id && shot.caption_audio_id === shot.audio_id
    && shot.caption_narration === shot.narration);
}

export function storyCaptionAtFrame(shot: StoryCaptionSource, frame: number, fps: number): string|undefined {
  if (!shot.show_caption || frame < 0 || frame >= Math.round(shot.duration_ms * fps / 1000)) return undefined;
  if (hasTimedStoryCaptions(shot)) {
    const time = frame * 1000 / fps;
    return shot.captions!.find(cue => cue.start_ms <= time && time < cue.end_ms)?.text;
  }
  const chunks = captionChunks(shot.narration);
  const frames = Math.round(shot.duration_ms * fps / 1000);
  return chunks[Math.min(chunks.length - 1, Math.floor(frame / frames * chunks.length))];
}
