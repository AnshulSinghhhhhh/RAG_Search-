import re
import time

import pytest
from fastapi.testclient import TestClient

from secondbrain.api import create_app


@pytest.fixture
def client(brain):
    with TestClient(create_app(brain=brain)) as client:
        yield client


def headers(client):
    html = client.get('/').text
    token = re.search(r'name="brain-token" content="([^"]+)"', html).group(1)
    return {'X-Brain-Token': token}


def test_rejects_cross_origin_mutations_and_dns_rebinding(client):
    assert client.post('/api/search', json={'query': 'test'}).status_code == 403
    assert client.post('/api/search', json={'query': 'test'}, headers={**headers(client), 'Origin': 'https://evil.example'}).status_code == 403
    assert client.get('/api/status', headers={'Host': 'evil.example'}).status_code == 403


def test_cli_engine_and_api_share_collection(client, brain, tmp_path):
    file = tmp_path / 'note.txt'; file.write_text('Juniper cafe next to the library')
    brain.ingest_file(file)
    response = client.post('/api/search', json={'query': 'Juniper'}, headers=headers(client))
    assert response.status_code == 200
    result = response.json()['results'][0]
    assert result['name'] == 'note.txt'
    assert client.get(f"/api/files/{result['id']}").text == file.read_text()
    assert client.get('/api/status').json()['assets'] == 1


def test_index_job_reports_failures_without_hiding_success(client, tmp_path):
    folder = tmp_path / 'inbox'; folder.mkdir()
    (folder / 'note.txt').write_text('project design review')
    (folder / 'bad.png').write_bytes(b'broken image')
    response = client.post('/api/index', json={'path': str(folder)}, headers=headers(client))
    assert response.status_code == 202
    for _ in range(100):
        job = client.get('/api/jobs/' + response.json()['job_id']).json()
        if job['state'] in {'complete', 'error'}: break
        time.sleep(.01)
    assert job['state'] == 'complete' and job['report']['indexed'] == 1
    assert len(job['report']['errors']) == 1


def test_file_route_only_resolves_registered_ids(client):
    assert client.get('/api/files/not-registered').status_code == 404
    assert client.get('/api/thumbnails/not-registered').status_code == 404


def test_frontend_and_fonts_are_bundled(client):
    response = client.get('/')
    assert response.status_code == 200 and '__SESSION_TOKEN__' not in response.text
    assert "frame-ancestors 'none'" in response.headers['content-security-policy']
    assert client.get('/static/app.js').status_code == 200
    assert client.get('/static/styles.css').status_code == 200
    assert client.get('/static/fonts/DM-Sans.ttf').status_code == 200


def test_invalid_index_path_has_useful_error(client):
    response = client.post('/api/index', json={'path': 'Z:/missing-secondbrain-sample'}, headers=headers(client))
    assert response.status_code == 400 and 'does not exist' in response.json()['detail']
