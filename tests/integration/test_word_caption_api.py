from app.domain.models import Transcript, TranscriptSegment, ClipRevision, Clip
from app.domain.subtitle_timing import source_words


def test_word_captions_use_pinned_transcript_and_require_matching_text(clients, database, ready_project):
    owner, other = clients
    with database() as db:
        transcript = Transcript(project_id=ready_project['project_id'],version=1,language='id',model='fixture')
        db.add(transcript); db.flush()
        db.add(TranscriptSegment(transcript_id=transcript.id,order=0,start_ms=500,end_ms=3500,text='Ini momen seru.',
            words_json=[{'word':' Ini','start_ms':500,'end_ms':900},{'word':' momen','start_ms':1400,'end_ms':1900},{'word':' seru.','start_ms':2800,'end_ms':3500}]))
        db.commit()
    response = owner.post(f"/api/v1/projects/{ready_project['project_id']}/clips",json={
        'start_ms':0,'end_ms':6000,'subtitle_style_json':{'display_mode':'words'}})
    assert response.status_code == 201
    clip = response.json()
    assert len(clip['revision']['source_words']) == 3
    path = f"/api/v1/clips/{clip['id']}"
    assert other.get(path+'/subtitle-words?start_ms=0&end_ms=6000').status_code == 404
    assert owner.get(path+'/subtitle-words?start_ms=0&end_ms=50000').status_code == 422
    assert len(owner.get(path+'/subtitle-words?start_ms=0&end_ms=6000').json()['source_words']) == 3
    assert owner.post(path+'/exports',json={'revision':1,'resolution':720}).status_code == 202
    with database() as db:
        db.add(Transcript(project_id=ready_project['project_id'],version=2,language='id',model='new-version'))
        db.commit()
        revision = db.get(ClipRevision,db.get(Clip,clip['id']).active_revision_id)
        assert len(source_words(db,revision)) == 3  # Existing revision stays pinned to v1.
    edit = owner.patch(path,json={'expected_revision':1,'cues':[{'start_ms':500,'end_ms':3500,'text':'Teks lain'}]})
    assert edit.status_code == 200  # Corrections can be saved even when timing needs attention.
    exported = owner.post(path+'/exports',json={'revision':2,'resolution':720})
    assert exported.status_code == 422 and exported.json()['code'] == 'SUBTITLE_WORD_TIMING'
    assert owner.patch(path,json={'expected_revision':2,'subtitle_style_json':{'display_mode':'sentence'}}).status_code == 200
    assert owner.post(path+'/exports',json={'revision':3,'resolution':720}).status_code == 202
