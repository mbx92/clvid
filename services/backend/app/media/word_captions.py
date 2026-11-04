from .process import MediaError


def normalized(text):
    return "".join(c.casefold() for c in text if c.isalnum())


def align_words(cues, words, clip_start_ms):
    events, missing = [], 0
    for cue in cues:
        candidates = [w for w in words if w["end_ms"] > cue["start_ms"] + clip_start_ms
                      and w["start_ms"] < cue["end_ms"] + clip_start_ms]
        if (not candidates or any(w["end_ms"] <= w["start_ms"] for w in candidates)
                or any(a["end_ms"] > b["start_ms"] for a, b in zip(candidates, candidates[1:]))):
            missing += 1
            continue
        # Keep ASR token boundaries (including multiword tokens); join only
        # continuation tokens which have no leading space.
        groups = []
        for w in candidates:
            if groups and w["word"][:1] and not w["word"][0].isspace() and w["word"].startswith(("-", "'", "’")):
                groups[-1]["word"] += w["word"]
                groups[-1]["end_ms"] = w["end_ms"]
            else:
                groups.append(dict(w))
        text = cue["text"]
        if normalized(text) != normalized("".join(w["word"] for w in groups)):
            missing += 1
            continue
        positions = [i for i, char in enumerate(text) if char.isalnum() for _ in char.casefold()]
        offset, local = 0, []
        for i, w in enumerate(groups):
            count = len(normalized(w["word"]))
            if not count:
                continue
            start = positions[offset] if offset else 0
            offset += count
            stop = positions[offset] if offset < len(positions) else len(text)
            a = max(cue["start_ms"], w["start_ms"] - clip_start_ms)
            b = min(cue["end_ms"], w["end_ms"] - clip_start_ms)
            if b > a:
                local.append(dict(start_ms=a, end_ms=b, text=text[start:stop].strip()))
        events.extend(local)
    return events, missing


def word_events(cues, words, clip_start_ms):
    events, missing = align_words(cues, words, clip_start_ms)
    if missing:
        raise MediaError("subtitle_word_timing", "Subtitle tidak memiliki timestamp kata yang cocok; gunakan mode kalimat atau transkripsikan kembali.")
    return events


def highlight_events(cues, words, clip_start_ms):
    """Whole-sentence karaoke; mirror web alignHighlightWords and shared fixtures."""
    def normalize(value):
        return ''.join(c for c in value.lower() if c.isalnum())

    output = []
    for cue in cues:
        start, end = clip_start_ms + cue['start_ms'], clip_start_ms + cue['end_ms']
        spoken_words = [w for w in words if w['end_ms'] > start and w['start_ms'] < end and normalize(w['word'])]
        tokens = [(index, normalize(token)) for index, token in enumerate(cue['text'].split()) if normalize(token)]
        valid = (bool(spoken_words) and bool(tokens)
                 and all(w['end_ms'] > w['start_ms'] for w in spoken_words)
                 and all(a['end_ms'] <= b['start_ms'] for a, b in zip(spoken_words, spoken_words[1:]))
                 and ''.join(t[1] for t in tokens) == ''.join(normalize(w['word']) for w in spoken_words))
        i, j, spans = 0, 0, []
        while valid and i < len(tokens) and j < len(spoken_words):
            first_i, first_j = i, j
            written, spoken = tokens[i][1], normalize(spoken_words[j]['word'])
            i, j = i + 1, j + 1
            while written != spoken and (i < len(tokens) or j < len(spoken_words)):
                if len(written) <= len(spoken) and i < len(tokens):
                    written += tokens[i][1]
                    i += 1
                elif j < len(spoken_words):
                    spoken += normalize(spoken_words[j]['word'])
                    j += 1
                else:
                    break
            begin, finish = max(start, spoken_words[first_j]['start_ms']), min(end, spoken_words[j - 1]['end_ms'])
            if written != spoken or finish <= begin:
                valid = False
                break
            spans.append(dict(start_ms=begin - clip_start_ms, end_ms=finish - clip_start_ms,
                              start_word=tokens[first_i][0], end_word=tokens[i - 1][0] + 1))
        if not valid or i != len(tokens) or j != len(spoken_words):
            raise MediaError('subtitle_word_timing', 'Highlight kata memerlukan timestamp yang cocok dengan teks. '
                             'Buat ulang subtitle dari suara, gunakan teks transkrip yang sesuai, atau pilih template lain.')
        output.append(dict(cue, word_spans=spans))
    return output
