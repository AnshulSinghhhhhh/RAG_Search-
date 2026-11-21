import json
import os
from datetime import datetime, timezone

import numpy as np
import pytest
from PIL import Image, ImageDraw

from secondbrain.embeddings import quantize
from secondbrain.engine import date_filters
from secondbrain.extract import Extractors, audio_chunks, changed_region


def test_quantization_retains_cosine_and_quarter_payload():
    random = np.random.default_rng(8)
    left, right = random.normal(size=(2, 512)).astype(np.float32)
    packed, scale, norm = quantize(left)
    reconstructed = np.frombuffer(packed, dtype=np.int8).astype(np.float32) * scale
    assert len(packed) == left.nbytes // 4
    assert np.dot(left, reconstructed) / (np.linalg.norm(left) * np.linalg.norm(reconstructed)) > .999
    expected = np.dot(left, right) / (np.linalg.norm(left) * np.linalg.norm(right))
    actual = np.dot(np.frombuffer(packed, dtype=np.int8), right) / norm / np.linalg.norm(right)
    assert abs(expected - actual) < .002


@pytest.mark.parametrize('vector', [np.array([float('nan')]), np.array([])])
def test_invalid_model_output_is_rejected(vector):
    with pytest.raises(ValueError): quantize(vector)


def test_duplicate_locations_and_cached_processing(brain, tmp_path):
    first, second = tmp_path / 'first.txt', tmp_path / 'second.txt'
    first.write_text('Juniper cafe is near the old library.', encoding='utf-8')
    second.write_bytes(first.read_bytes())
    assert brain.ingest_file(first)['action'] == 'indexed'
    assert brain.ingest_file(first)['action'] == 'cached'
    assert brain.ingest_file(second)['action'] == 'duplicate'
    stats = brain.store.stats()
    assert stats['assets'] == 1 and stats['locations'] == 2
    assert stats['vector_bytes'] * 4 == stats['float32_vector_bytes']
    result = brain.search('Juniper')['results'][0]
    assert len(result['paths']) == 2 and result['channels'] == ['keyword', 'text']


def test_changed_file_with_same_size_and_mtime_replaces_fts(brain, tmp_path):
    file = tmp_path / 'receipt.txt'
    file.write_text('price 2999', encoding='utf-8')
    stamp = file.stat().st_mtime_ns
    old = brain.ingest_file(file)['id']
    file.write_text('price 2499', encoding='utf-8')
    os.utime(file, ns=(stamp, stamp))
    fresh = brain.ingest_file(file)['id']
    assert old != fresh and brain.store.asset(old) is None
    assert not brain.search('2999', lexical_only=True)['results']
    assert brain.search('2499', lexical_only=True)['results'][0]['id'] == fresh


def test_failed_reindex_does_not_destroy_previous_index(brain, tmp_path):
    file = tmp_path / 'important.txt'
    file.write_text('original evidence', encoding='utf-8')
    original = brain.ingest_file(file)['id']
    file.write_text('new evidence', encoding='utf-8')
    def fail(*args, **kwargs): raise RuntimeError('Model unavailable')
    brain.embeddings.text = fail
    with pytest.raises(RuntimeError): brain.ingest_file(file)
    assert brain.store.asset(original)
    assert brain.search('original', lexical_only=True)['results']


def test_forget_removes_vectors_and_fts_but_preserves_originals(brain, tmp_path):
    folder = tmp_path / 'receipts'; folder.mkdir()
    file = folder / 'test.txt'; file.write_text('invoice 7718')
    brain.ingest(folder)
    assert brain.store.remove(folder) == 1
    assert file.exists()
    assert brain.store.stats()['vectors'] == 0
    assert not brain.search('7718', lexical_only=True)['results']


def test_prune_keeps_surviving_alias(brain, tmp_path):
    first, second = tmp_path / 'one.txt', tmp_path / 'two.txt'
    first.write_text('shared memory'); second.write_text('shared memory')
    brain.ingest_file(first); brain.ingest_file(second)
    first.unlink()
    assert brain.prune() == 1
    assert brain.store.stats()['assets'] == 1
    assert brain.search('shared')['results'][0]['paths'] == [str(second.resolve())]


def test_date_filter_handles_january_and_cleans_query():
    now = datetime(2026, 1, 15, 12, tzinfo=timezone.utc)
    clean, start, end = date_filters('white sneaker last month', now)
    assert clean == 'white sneaker'
    assert datetime.fromtimestamp(start, timezone.utc) == datetime(2025, 12, 1, tzinfo=timezone.utc)
    assert datetime.fromtimestamp(end, timezone.utc) == datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_filters_are_applied_before_ranking(brain, tmp_path):
    one, two = tmp_path / 'one', tmp_path / 'two'; one.mkdir(); two.mkdir()
    (one / 'a.txt').write_text('cafe receipt 400')
    (two / 'b.txt').write_text('cafe receipt 500')
    brain.ingest(one); brain.ingest(two)
    result = brain.search('cafe', folder=str(two), lexical_only=True)
    assert len(result['results']) == 1 and result['results'][0]['name'] == 'b.txt'
    assert not brain.search('cafe', kind='audio')['results']
    assert not brain.search('cafe', after=4102444800)['results']


def test_folder_like_wildcards_are_literal(brain, tmp_path):
    one, two = tmp_path / 'folder_100%', tmp_path / 'folder_100x'; one.mkdir(); two.mkdir()
    (one / 'a.txt').write_text('invoice'); (two / 'b.txt').write_text('invoice')
    brain.ingest(one); brain.ingest(two)
    assert [r['name'] for r in brain.search('invoice', folder=str(one), lexical_only=True)['results']] == ['a.txt']


def test_file_errors_do_not_abort_folder(brain, tmp_path):
    folder = tmp_path / 'inbox'; folder.mkdir()
    (folder / 'good.txt').write_text('good searchable note')
    (folder / 'broken.png').write_bytes(b'not an image')
    report = brain.ingest(folder)
    assert report['indexed'] == 1 and len(report['errors']) == 1
    assert brain.search('searchable')['results']


def test_own_data_is_not_indexed(brain):
    file = brain.workspace.home / 'secret.txt'; file.write_text('internal metadata')
    assert brain.ingest_file(file)['action'] == 'ignored'
    with pytest.raises(ValueError): brain.add_source(brain.workspace.home)


def test_delta_ocr_preserves_changed_digit_and_reuses_heading(brain):
    previous = Image.new('RGB', (700, 500), 'white')
    current = previous.copy()
    ImageDraw.Draw(current).rectangle((95, 201, 103, 214), fill='black')
    lines = [{'text': 'Shoe shop', 'confidence': .99, 'box': [40, 30, 210, 65]},
             {'text': '2999', 'confidence': .98, 'box': [70, 190, 170, 230]}]
    extractor = Extractors(brain.workspace)
    calls = []
    def ocr(crop):
        calls.append(crop.size)
        return [{'text': '2499', 'confidence': .99, 'box': [24, 24, 100, 60]}]
    extractor.ocr = ocr
    result, metrics = extractor.image_text(current, previous, lines)
    assert metrics['ocr_strategy'] == 'delta'
    assert 0 < metrics['ocr_area_fraction'] < .1 and metrics['reused_lines'] == 1
    assert {line['text'] for line in result} == {'Shoe shop', '2499'}
    assert calls[0] != current.size


def test_deleted_ocr_line_is_not_reused(brain):
    previous = Image.new('RGB', (600, 400), 'white')
    ImageDraw.Draw(previous).rectangle((90, 180, 170, 200), fill='black')
    current = Image.new('RGB', (600, 400), 'white')
    extractor = Extractors(brain.workspace); extractor.ocr = lambda crop: []
    result, _ = extractor.image_text(current, previous, [{'text': 'deleted', 'box': [90, 180, 171, 201], 'confidence': .9}])
    assert result == []


def test_identical_pixels_skip_ocr(brain):
    image = Image.new('RGB', (600, 400), 'white')
    extractor = Extractors(brain.workspace)
    def fail(*args): raise AssertionError('OCR should be reused')
    extractor.ocr = fail
    result, metrics = extractor.image_text(image, image.copy(), [{'text': 'existing', 'box': [1, 1, 50, 20], 'confidence': .9}])
    assert result[0]['text'] == 'existing' and metrics['ocr_area_fraction'] == 0


@pytest.mark.parametrize('keep_alias', [False, True])
def test_overwritten_image_gets_new_ocr(brain, tmp_path, keep_alias):
    brain.workspace.settings.ocr = True
    path = tmp_path / 'a-price.png'
    old_image = Image.new('RGB', (700, 500), 'white')
    old_image.save(path)

    def ocr(image):
        price = '2499' if image.getpixel((image.width // 2, image.height // 2))[0] == 0 else '2999'
        return [{'text': price, 'confidence': .99, 'box': [image.width // 2 - 5, image.height // 2 - 5,
                                                           image.width // 2 + 5, image.height // 2 + 5]}]

    brain.extractors.ocr = ocr
    previous = brain.ingest_file(path)['id']
    if keep_alias:
        alias = tmp_path / 'z-copy.png'
        alias.write_bytes(path.read_bytes())
        brain.ingest_file(alias)
    ImageDraw.Draw(old_image).rectangle((347, 247, 353, 253), fill='black')
    old_image.save(path)
    current = brain.ingest_file(path)['id']
    assert previous != current
    assert [r['id'] for r in brain.search('2499', lexical_only=True)['results']] == [current]
    assert [r['id'] for r in brain.search('2999', lexical_only=True)['results']] == ([previous] if keep_alias else [])


def test_audio_chunks_preserve_original_offsets():
    chunks = audio_chunks([{'text': 'first cafe', 'start': 15., 'end': 18.},
                           {'text': 'near library', 'start': 18.5, 'end': 21.},
                           {'text': 'second topic', 'start': 60., 'end': 65.}])
    assert chunks[0] == {'text': 'first cafe near library', 'start': 15., 'end': 21.}
    assert chunks[1]['start'] == 60.


@pytest.mark.parametrize('lexical_only', [True, False])
def test_long_document_cannot_fill_channel_candidate_budget(brain, tmp_path, lexical_only):
    long_file = tmp_path / 'long.txt'
    short_file = tmp_path / 'short.txt'
    long_file.write_text('needle ' * 16000, encoding='utf-8')
    short_file.write_text('needle ' * 40 + 'filler ' * 100, encoding='utf-8')
    brain.ingest_file(long_file)
    brain.ingest_file(short_file)
    query = 'needle'
    if not lexical_only:
        # Query for a word absent from both files through the dense-only path.
        dense_query = brain.embeddings.text(['needle'], query=True)
        brain.embeddings.text = lambda texts, query=False: dense_query
        query = 'semantic-query-without-a-keyword-match'
    results = brain.search(query, lexical_only=lexical_only)['results']
    assert {result['name'] for result in results} == {'long.txt', 'short.txt'}
    assert all(result['channels'] == (['keyword'] if lexical_only else ['text']) for result in results)
