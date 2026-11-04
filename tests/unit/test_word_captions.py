import pytest
from app.media.word_captions import align_words, highlight_events, word_events
import json
from pathlib import Path
from app.media.process import MediaError
from app.media.subtitles import to_ass


@pytest.mark.parametrize('item', json.loads((Path(__file__).parents[1] / 'fixtures' / 'podcast-timing.json').read_text(encoding='utf-8')), ids=lambda item: item['name'])
def test_podcast_timing_shared_with_preview(item):
    original = json.dumps(item)
    if item['spans'] is None:
        with pytest.raises(MediaError, match='timestamp'):
            highlight_events([item['cue']], item['words'], item['clip_start'])
    else:
        assert highlight_events([item['cue']], item['words'], item['clip_start']) == [dict(item['cue'], word_spans=item['spans'])]
    assert json.dumps(item) == original


def test_word_timing_preserves_silence_punctuation_and_trim():
    words = [{'word':' Ini', 'start_ms':10500,'end_ms':10900},
             {'word':' momen', 'start_ms':11400,'end_ms':11900},
             {'word':' seru.', 'start_ms':12800,'end_ms':13500}]
    cues = [{'start_ms':0,'end_ms':6000,'text':'INI momen seru!'}]
    events, missing = align_words(cues, words, 10000)
    assert missing == 0 and events == [
        {'start_ms':500,'end_ms':900,'text':'INI'},
        {'start_ms':1400,'end_ms':1900,'text':'momen'},
        {'start_ms':2800,'end_ms':3500,'text':'seru!'}]
    assert align_words([dict(cues[0], start_ms=600,end_ms=3000)],words,10000)[0] == [
        dict(events[0],start_ms=600),events[1],dict(events[2],end_ms=3000)]
    ass = to_ass(events,6000,{})
    assert '0:00:00.50,0:00:00.90' in ass
    assert '0:00:01.40,0:00:01.90' in ass
    assert len([s for s in ass.splitlines() if s.startswith('Dialogue:')]) == 3


@pytest.mark.parametrize('words,text', [([], 'hello'),
    ([{'word':'hello','start_ms':0,'end_ms':400}], 'changed'),
    ([{'word':'hello','start_ms':0,'end_ms':0}], 'hello'),
    ([{'word':'hello','start_ms':0,'end_ms':700},{'word':'world','start_ms':500,'end_ms':900}], 'hello world')])
def test_missing_edited_or_invalid_timing_is_not_invented(words,text):
    with pytest.raises(MediaError, match='timestamp kata'):
        word_events([{'start_ms':0,'end_ms':1000,'text':text}],words,0)


def test_asr_tokens_merge_only_on_exact_text_without_guessing_timing():
    words = [{'word':' sama','start_ms':100,'end_ms':300},
             {'word':'-sama','start_ms':300,'end_ms':600},
             {'word':' New York','start_ms':800,'end_ms':1000}]
    events, missing = align_words([{'start_ms':0,'end_ms':1200,'text':'Sama-sama New York!'}],words,0)
    assert missing == 0 and events == [{'start_ms':100,'end_ms':600,'text':'Sama-sama'},
                                      {'start_ms':800,'end_ms':1000,'text':'New York!'}]
