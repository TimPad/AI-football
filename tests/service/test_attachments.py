from uuid import uuid4


def test_private_document_upload_retry_and_validation(admin_client,match_factory):
    m=match_factory(); url=f"/api/v1/matches/{m['id']}/attachments"
    headers={'X-Request-ID':str(uuid4()),'X-Expected-Revision':str(m['revision'])}
    payload=b'%PDF-1.4\nfixture document'
    r=admin_client.post(url,files={'file':('protocol.pdf',payload,'application/pdf')},headers=headers)
    assert r.status_code==200,r.text
    repeat=admin_client.post(url,files={'file':('protocol.pdf',payload,'application/pdf')},headers=headers)
    assert repeat.status_code==200 and repeat.json()==r.json()
    attachment_id=r.json()['protocol']['attachment_ids'][0]
    download=admin_client.get(f'/api/v1/attachments/{attachment_id}/download')
    assert download.status_code==200 and download.content==payload
    assert 'attachment' in download.headers['content-disposition']
    from fastapi.testclient import TestClient
    with TestClient(admin_client.app) as guest:
        assert guest.get(f'/api/v1/attachments/{attachment_id}/download').status_code==401
    bad=admin_client.post(url,files={'file':('script.html',b'<script>','text/html')},headers={
        'X-Request-ID':str(uuid4()),'X-Expected-Revision':str(r.json()['revision'])})
    assert bad.status_code==422


def test_upload_conflict_does_not_replace_saved_document(admin_client,match_factory):
    m=match_factory(); url=f"/api/v1/matches/{m['id']}/attachments"; key=str(uuid4())
    h={'X-Request-ID':key,'X-Expected-Revision':str(m['revision'])}
    first=admin_client.post(url,files={'file':('a.pdf',b'%PDF-1.4 first','application/pdf')},headers=h)
    assert first.status_code==200
    second=admin_client.post(url,files={'file':('a.pdf',b'%PDF-1.4 changed','application/pdf')},headers=h)
    assert second.status_code==409
    aid=first.json()['protocol']['attachment_ids'][0]
    assert admin_client.get(f'/api/v1/attachments/{aid}/download').content==b'%PDF-1.4 first'
