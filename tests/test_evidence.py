import json
import sys
import wave
from types import SimpleNamespace

from PIL import Image
import pytest
from fastapi.testclient import TestClient

from secondbrain import cli
from secondbrain.answers import answer
from secondbrain.api import create_app


def line(text, y, x=20):
    return {'text': text, 'confidence': .98, 'box': [x, y, x + len(text) * 8, y + 18]}


def indexed_image(brain, path, lines, color='white'):
    Image.new('RGB', (600, 400), color).save(path)
    brain.workspace.settings.ocr = True
    brain.extractors.ocr = lambda _: lines
    return brain.ingest_file(path, force=True)['id']


def post_ask(client, query, **filters):
    page = client.get('/').text
    token = page.split('name="brain-token" content="')[1].split('"')[0]
    result = client.post('/api/ask', json={'query': query, 'lexical_only': True, **filters},
                         headers={'X-Brain-Token': token})
    assert result.status_code == 200
    return result.json()


@pytest.mark.parametrize(('query', 'lines', 'expected'), [
    ('What is the receipt total for Alder Bakery?',
     [line('ALDER BAKERY', 20), line('SUBTOTAL INR 130.00', 100), line('TOTAL INR', 150), line('145.00', 150, 350)], 'INR 145.00'),
    ('Show the invoice number for Harbor Books',
     [line('HARBOR BOOKS', 20), line('Invoice No. HB-51/3', 100)], 'HB-51/3'),
    ('What is the displayed price of the Larch Desk Lamp?',
     [line('Larch Desk Lamp', 20), line('USD 49.95', 100)], 'USD 49.95'),
])
def test_cited_field_via_cli_and_api(brain, tmp_path, monkeypatch, capsys, query, lines, expected):
    asset = indexed_image(brain, tmp_path / 'source.png', lines)
    monkeypatch.setattr(cli, 'Brain', lambda _: brain)
    brain.workspace.settings.ollama_model = 'configured-local-model'
    assert cli.main(['ask', query, '--lexical-only', '--json']) == 0
    from_cli = json.loads(capsys.readouterr().out)
    with TestClient(create_app(brain=brain)) as client:
        from_api = post_ask(client, query)
        assert client.get(f'/api/evidence-images/{asset}').headers['content-type'] == 'image/png'
    for result in [from_cli, from_api]:
        assert result['evidence_status'] == 'supported'
        citation, = result['citations']
        assert citation['value'] == expected and citation['asset_id'] == asset
        assert citation['box'][1] == lines[-1]['box'][1]
        assert expected in citation['text']


def test_ask_abstains_for_missing_field_unrelated_merchant_and_conflicting_prices(brain, tmp_path):
    indexed_image(brain, tmp_path / 'first.png', [line('Alder Bakery', 20), line('TOTAL USD 12', 100)])
    indexed_image(brain, tmp_path / 'second.png', [line('Larch Desk Lamp', 20), line('USD 49', 100), line('USD 69', 200)], 'blue')
    with TestClient(create_app(brain=brain)) as client:
        for query in ['invoice ID for Alder Bakery', 'receipt total for Other Bakery']:
            result = post_ask(client, query)
            assert result['results'] and result['evidence_status'] == 'insufficient' and not result['citations']
        result = post_ask(client, 'displayed price of the Larch Desk Lamp')
        assert result['evidence_status'] == 'insufficient'
        assert {citation['value'] for citation in result['citations']} == {'USD 49', 'USD 69'}
        assert post_ask(client, 'find Alder Bakery')['evidence_status'] == 'unassessed'


def test_explicit_retry_preserves_conflicting_high_confidence_readings(brain, tmp_path):
    asset = indexed_image(brain, tmp_path / 'invoice.png', [line('Alder Bakery', 20), line('INV-2006-1042', 100)])
    calls = []

    def retry(image):
        calls.append(image.size)
        return [line('INV-2026-1042', 48, 40)]

    brain.extractors.ocr = retry
    with TestClient(create_app(brain=brain)) as client:
        assert post_ask(client, 'invoice number for Alder Bakery')['evidence_status'] == 'supported'
        assert not calls
        result = post_ask(client, 'invoice number for Alder Bakery', refine=True)
    assert calls == [(296, 132)]
    assert result['evidence_status'] == 'insufficient'
    assert result['refinement']['attempted'] == 1
    assert {c['value'] for c in result['citations']} == {'INV-2006-1042', 'INV-2026-1042'}
    assert result['citations'][1]['box'] == [20, 100, 72, 109]
    assert 'INV-2006-1042' in brain.store.asset(asset)['chunks'][0]['text']


def test_changed_image_cannot_supply_evidence_or_be_refined(brain, tmp_path):
    path = tmp_path / 'receipt.png'
    asset = indexed_image(brain, path, [{**line('TOTAL USD 12', 100), 'confidence': .4}])
    Image.new('RGB', (600, 400), 'blue').save(path)

    def unexpected(_):
        pytest.fail('OCR received replacement pixels for the old asset')

    brain.extractors.ocr = unexpected
    with TestClient(create_app(brain=brain)) as client:
        assert post_ask(client, 'receipt total', refine=True)['evidence_status'] == 'insufficient'
        assert client.get(f'/api/evidence-images/{asset}').status_code == 404
    assert brain.refine('TOTAL', lexical_only=True)['refinement']['completed'] == []


def test_cli_retry_can_recover_a_missing_value(brain, tmp_path, monkeypatch, capsys):
    asset = indexed_image(brain, tmp_path / 'invoice.png', [line('Alder Bakery', 20), line('Invoice Number:', 100)])
    brain.extractors.ocr = lambda image: [line('Invoice Number: AB-109', 48, 40)]
    monkeypatch.setattr(cli, 'Brain', lambda _: brain)
    assert cli.main(['ask', 'invoice number for Alder Bakery', '--lexical-only', '--refine', '--json']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['evidence_status'] == 'supported'
    citation, = result['citations']
    assert (citation['value'], citation['origin'], citation['asset_id']) == ('AB-109', 'retry', asset)
    assert 'AB-109' not in brain.store.asset(asset)['chunks'][0]['text']


def test_recording_bounds_at_ingestion_and_api(brain, tmp_path, monkeypatch):
    path = tmp_path / 'memo.wav'
    with wave.open(str(path), 'wb') as stream:
        stream.setparams((1, 2, 100, 0, 'NONE', 'not compressed'))
        stream.writeframes(b'\0\0' * 1227)
    def segment(text, start, end):
        return SimpleNamespace(text=text, start=start, end=end, avg_logprob=0)

    segments = [segment('Early', -1, 2), segment('Bring the screenshots', 8.08, 17.6),
                segment('Past the end', 15, 18), segment('Backwards', 3, 2),
                segment('Empty interval', 2, 2), segment('Nonfinite', 1, float('inf'))]
    info = SimpleNamespace(duration=12.275, duration_after_vad=10, language='en')
    monkeypatch.setitem(sys.modules, 'faster_whisper', SimpleNamespace(WhisperModel=None))
    brain.extractors._whisper = SimpleNamespace(transcribe=lambda *args, **kwargs: (iter(segments), info))
    asset = brain.ingest_file(path)['id']
    with TestClient(create_app(brain=brain)) as client:
        result = client.get(f'/api/assets/{asset}').json()
    metadata = result['metadata']
    assert metadata['duration'] == 12.27
    assert metadata['timestamp_checks'] == {'clamped': 2, 'discarded': 4,
                                            'original_spans': [{'start': -1, 'end': 2}, {'start': 8.08, 'end': 17.6}]}
    for spans in [metadata['segments'], result['chunks']]:
        assert [(span['start'], span['end']) for span in spans] == [(0, 2), (8.08, 12.27)]


def test_repair_resumes_legacy_individual_assets(brain, tmp_path):
    paths = [tmp_path / 'a.png', tmp_path / 'b.png']
    ids = [indexed_image(brain, path, [line('TOTAL USD 12', 100)], color)
           for path, color in zip(paths, ['white', 'blue'])]
    with brain.store.connection() as db:
        db.execute("UPDATE assets SET metadata=json_remove(metadata, '$.processing_version')")
    assert brain.repair(dry_run=True)['pending'] == 2
    assert answer(brain, 'receipt total', lexical_only=True)['evidence_status'] == 'insufficient'
    calls = 0

    def interrupt(_):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt
        return [line('TOTAL USD 12', 100)]

    brain.extractors.ocr = interrupt
    with pytest.raises(KeyboardInterrupt):
        brain.repair()
    assert brain.repair(dry_run=True)['pending'] == 1
    assert brain.store.asset(sorted(ids)[1])['chunks'][0]['text'] == 'TOTAL USD 12'
    assert brain.repair()['repaired'] == 1
    assert brain.repair()['pending'] == 0
