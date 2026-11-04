from sqlalchemy import select
from app.domain.models import TranscriptSegment
from app.media.word_captions import highlight_events, word_events


def source_words(db, revision, start=None, end=None):
    if not revision.transcript_id:
        return []
    start = revision.start_ms if start is None else start
    end = revision.end_ms if end is None else end
    segments = db.scalars(select(TranscriptSegment).where(
        TranscriptSegment.transcript_id == revision.transcript_id,
        TranscriptSegment.start_ms < end, TranscriptSegment.end_ms > start).order_by(TranscriptSegment.order))
    result = []
    for segment in segments:
        for word in segment.words_json or []:
            if (isinstance(word, dict) and isinstance(word.get('word'), str)
                    and isinstance(word.get('start_ms'), int) and isinstance(word.get('end_ms'), int)
                    and word['end_ms'] > start and word['start_ms'] < end):
                result.append({key: word[key] for key in ('word', 'start_ms', 'end_ms')})
    return result


def subtitle_events(db, revision, cues):
    style = revision.subtitle_style_json
    if style.get('enabled', True) and style.get('renderer') == 'remotion' and style.get('remotion_template') == 'podcast':
        return highlight_events(cues, source_words(db, revision), revision.start_ms)
    if revision.subtitle_style_json.get('enabled', True) and revision.subtitle_style_json.get('display_mode') == 'words':
        return word_events(cues, source_words(db, revision), revision.start_ms)
    return cues
