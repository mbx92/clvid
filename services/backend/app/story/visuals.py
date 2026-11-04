"""Deterministic illustration suggestions; no downloaded or generated bitmaps."""
import re
from .schemas import Document, Visual

def suggested_visual(scene, context=''):
    note = scene.get('visual_note', '').lower()
    narration = scene.get('narration', '').lower()
    combined = note + ' ' + narration + ' ' + scene.get('title', '').lower()
    if re.search(r'kopi|coffee|peaberry', combined + ' ' + context.lower()):
        if re.search(r'kembali ke piring|penggiling|yang b[.!]', combined):
            kind = 'coffee_reveal'
        elif re.search(r'satu biji|one seed|peaberry|kopi lanang', note):
            kind = 'coffee_peaberry'
        elif re.search(r'pisahkan|mempertemukan|separat', note):
            kind = 'coffee_separate'
        elif re.search(r'penampang|buah kopi merah|cross.section|dua biji.*berdempetan', combined):
            kind = 'coffee_pair'
        elif re.search(r'sisi rata|sejajar piring|yang a dulu', combined):
            kind = 'coffee_flat'
        elif re.search(r'biji|bean|piring', combined):
            kind = 'coffee_compare'
        else:
            return Visual(kind='diagram', items=[{'icon':'cup','label':scene.get('title','Kopi')[:32]}]).model_dump()
        return Visual(kind=kind).model_dump()
    icon = next((icon for pattern, icon in [('air|water','water'), ('daun|tanaman|plant|leaf','leaf'),
        ('matahari|sun','sun'), ('orang|manusia|person','person'), ('cek|check','check')]
        if re.search(pattern, combined)), 'box')
    return Visual(kind='diagram', items=[{'icon':icon,'label':scene.get('title','')[:32]}]).model_dump()

def fill_visuals(document, scene_id=None):
    result = Document.model_validate(document).model_dump()
    for scene in result['scenes']:
        if scene['asset_id'] or scene_id and scene['id'] != scene_id:
            continue
        if scene_id or scene['visual']['kind'] == 'none':
            scene['visual'] = suggested_visual(scene, result['title'])
    return result
