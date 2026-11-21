const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const token = $('meta[name="brain-token"]').content;
const state = {kind: '', folder: null, query: '', view: 'library', limit: 30, status: null, results: [], request: 0, answerRequest: 0, job: null, opener: null};
const paths = {
  grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  folder: '<path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10H3z"/>',
  activity: '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  terminal: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="m7 9 3 3-3 3m6 0h4"/>',
  shield: '<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6z"/><path d="m8 12 3 3 5-6"/>',
  monitor: '<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8m-4-4v4"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4.5 4.5"/>',
  image: '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8" cy="8" r="1.5"/><path d="m3 17 6-6 4 4 3-3 5 5"/>',
  mic: '<rect x="9" y="3" width="6" height="12" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2m-7 9v3m-4 0h8"/>',
  file: '<path d="M14 3H5v18h14V8zM14 3v5h5M8 12h8m-8 4h6"/>',
  calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 11h18m-13 4h2m4 0h2"/>',
  chevron: '<path d="m7 10 5 5 5-5"/>',
  spark: '<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z"/>',
  archive: '<path d="M4 8v13h16V8M3 3h18v5H3zm6 10h6"/>',
  lock: '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 5v2"/>',
  play: '<path d="m9 5 11 7-11 7z"/>',
  copy: '<rect x="8" y="8" width="12" height="13" rx="2"/><path d="M15 8V3H3v13h5"/>',
  check: '<path d="m5 12 4 4 10-10"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
};
function icon(name) {
  const span = document.createElement('span');
  span.className = 'icon';
  span.setAttribute('aria-hidden', 'true');
  // Only authored SVG path constants enter this HTML; file contents never do.
  span.innerHTML = `<svg viewBox="0 0 24 24">${paths[name] || paths.file}</svg>`;
  return span;
}
function node(tag, className = '', text = '') {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text) element.textContent = text;
  return element;
}
$$('[data-icon]').forEach(element => element.append(icon(element.dataset.icon).firstChild));

async function api(path, body, method = body === undefined ? 'GET' : 'POST') {
  const response = await fetch(path, {method, headers: {'Content-Type': 'application/json', 'X-Brain-Token': token}, body: body === undefined ? undefined : JSON.stringify(body)});
  if (!response.ok) {
    let message = `${response.status}: request failed`;
    try { const error = await response.json(); message = typeof error.detail === 'string' ? error.detail : 'Check the supplied values and try again.'; } catch {}
    throw new Error(message);
  }
  return response.json();
}
function notice(message, error = false) {
  $('#notice').textContent = message;
  $('#notice').classList.toggle('error', error);
  $('#notice').hidden = !message;
}
let toastTimer;
function toast(message) {
  $('#toast').textContent = message;
  $('#toast').hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { $('#toast').hidden = true; }, 3000);
}
function bytes(value) {
  if (!value) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const index = Math.min(3, Math.floor(Math.log(value) / Math.log(1024)));
  return `${(value / 1024 ** index).toFixed(index > 1 ? 1 : 0)} ${units[index]}`;
}
function fileName(path) { return path.split(/[\\/]/).filter(Boolean).pop() || path; }
function date(stamp) { return new Intl.DateTimeFormat(undefined, {day: 'numeric', month: 'short'}).format(new Date(stamp * 1000)); }
function timestamp(seconds) { return `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`; }
function setView(view) {
  state.view = view;
  $$('.view').forEach(element => { element.hidden = element.id !== `view-${view}`; });
  $$('.nav-item').forEach(element => {
    element.classList.toggle('active', element.dataset.view === view);
    if (element.dataset.view === view) element.setAttribute('aria-current', 'page'); else element.removeAttribute('aria-current');
  });
  $('#breadcrumb-current').textContent = {library: 'All memories', folders: 'Folders', activity: 'Activity & storage', cli: 'CLI guide'}[view];
}
$$('[data-view]').forEach(button => button.addEventListener('click', () => {
  setView(button.dataset.view);
  if (button.dataset.view === 'library') { state.folder = null; refreshSearch(); }
}));

async function refreshStatus() {
  state.status = await api('/api/status');
  const stats = state.status;
  $('#nav-total').textContent = stats.assets;
  for (const key of ['image', 'audio', 'text']) $(`#count-${key}`).textContent = stats.kinds[key] || 0;
  $('#count-all').textContent = stats.assets;
  const list = $('#source-list');
  list.replaceChildren();
  for (const source of stats.sources) {
    const button = node('button', `source-item${state.folder === source.path ? ' selected' : ''}`);
    button.title = source.path;
    button.append(icon('folder'), node('span', '', fileName(source.path)));
    button.addEventListener('click', () => { state.folder = source.path; setView('library'); refreshSearch(); });
    list.append(button);
  }
  if (!stats.sources.length) list.append(node('p', 'sidebar-empty', 'Add a folder to start collecting.'));
  renderFolders(stats.sources);
  renderStorage(stats);
}
function renderFolders(sources) {
  const container = $('#folder-management');
  container.replaceChildren();
  for (const source of sources) {
    const row = node('div', 'folder-row');
    const info = node('div', 'folder-info');
    info.append(node('strong', '', fileName(source.path)), node('p', '', source.path));
    const actions = node('div', 'folder-actions');
    const view = node('button', 'text-button', 'View memories');
    view.addEventListener('click', () => { state.folder = source.path; setView('library'); refreshSearch(); });
    const sync = node('button', 'text-button', 'Index changes');
    sync.addEventListener('click', () => startIndex(source.path));
    const forget = node('button', 'text-button danger-link', 'Forget folder');
    forget.addEventListener('click', async () => {
      forget.disabled = true;
      try {
        const result = await api('/api/sources', {path: source.path}, 'DELETE');
        if (state.folder === source.path) state.folder = null;
        await refreshStatus(); await refreshSearch();
        toast(`Forgot ${result.removed_locations} locations. Originals preserved.`);
      } catch (error) { toast(error.message); } finally { forget.disabled = false; }
    });
    actions.append(view, sync, forget); row.append(icon('folder'), info, actions); container.append(row);
  }
  if (!sources.length) container.append(node('p', 'helper', 'No source folders yet. Add a folder to index the files inside it.'));
}
function renderStorage(stats) {
  const container = $('#storage-summary');
  container.replaceChildren();
  const vectors = node('div', 'storage-block');
  vectors.append(node('h2', '', 'Searchable vectors'), node('strong', '', bytes(stats.vector_bytes)), node('p', '', `${stats.vectors} INT8 vectors · ${bytes(stats.float32_vector_bytes)} as float32`));
  const meter = node('div', 'storage-meter');
  const fill = node('span'); fill.style.width = stats.float32_vector_bytes ? '25%' : '0%'; meter.append(fill); vectors.append(meter);
  vectors.append(node('p', '', '4× fewer raw vector bytes. This excludes model files, metadata, and originals.'));
  const database = node('div', 'storage-block');
  database.append(node('h2', '', 'Local database'), node('strong', '', bytes(stats.database_bytes)), node('p', '', `${stats.assets} unique memories · ${stats.locations} file locations · ${stats.chunks} text chunks`), node('p', '', `${bytes(stats.source_bytes)} of original media referenced in place.`));
  container.append(vectors, database);
  const activities = $('#activity-list'); activities.replaceChildren();
  for (const event of stats.events) {
    const row = node('div', `activity-row ${event.action === 'error' ? 'error' : ''}`);
    const content = node('div');
    content.append(node('strong', '', fileName(event.path)));
    const details = [];
    const actions = {indexed: 'Indexed', cached: 'Reused cached embeddings', duplicate: 'Duplicate linked; embeddings reused', error: 'Indexing failed'};
    details.push(actions[event.action] || event.action);
    if (event.detail.ocr_strategy === 'delta') details.push(`OCR on ${(event.detail.ocr_area_fraction * 100).toFixed(1)}% of the image`);
    if (event.detail.reused_lines) details.push(`${event.detail.reused_lines} text lines reused`);
    if (event.detail.error) details.push(event.detail.error);
    content.append(node('p', '', details.join(' · ')));
    row.append(icon(event.action === 'error' ? 'close' : 'check'), content, node('span', 'activity-time', `${event.seconds.toFixed(2)}s`)); activities.append(row);
  }
  if (!stats.events.length) activities.append(node('p', 'helper', 'Processing activity will appear after you index your first files.'));
  $('#runtime-details').textContent = JSON.stringify({collection: stats.home, models: stats.settings}, null, 2);
}

function dateRange() {
  const value = $('#date-filter').value;
  const now = new Date(), midnight = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  let after = null, before = null;
  if (value === 'today') { after = midnight; before = new Date(midnight); before.setDate(before.getDate() + 1); }
  if (value === 'week') { after = new Date(now); after.setDate(after.getDate() - 7); }
  if (value === 'month') after = new Date(now.getFullYear(), now.getMonth(), 1);
  if (value === 'last-month') { after = new Date(now.getFullYear(), now.getMonth() - 1, 1); before = new Date(now.getFullYear(), now.getMonth(), 1); }
  return {after: after ? after.getTime() / 1000 : null, before: before ? before.getTime() / 1000 : null};
}
function searchBody() { return {query: state.query, kind: state.kind || null, folder: state.folder, limit: state.limit, ...dateRange()}; }
function skeletons() {
  $('#memory-grid').replaceChildren(...Array.from({length: 6}, () => {
    const card = node('div', 'memory-card skeleton');
    card.append(node('div', 'preview-button'), node('div', 'skeleton-title'), node('div', 'skeleton-meta')); return card;
  }));
}
async function refreshSearch(refine = false) {
  const request = ++state.request;
  state.query = $('#search-input').value.trim();
  closeAnswer();
  $('#empty-state').hidden = true;
  $('#results-description').textContent = state.query ? 'Finding your memories…' : 'Opening your collection…';
  $('#search-form').setAttribute('aria-busy', 'true');
  skeletons();
  try {
    const response = await api('/api/search', {...searchBody(), refine});
    if (request !== state.request) return;
    state.results = response.results;
    renderResults(response);
    if (response.warnings.length) notice(response.warnings.join('\n'), true);
  } catch (error) {
    if (request !== state.request) return;
    $('#memory-grid').replaceChildren();
    $('#results-description').textContent = 'Search could not finish.';
    notice(`${error.message} Check Activity & storage, or retry your search.`, true);
  } finally {
    if (request === state.request) $('#search-form').removeAttribute('aria-busy');
  }
}
function renderResults(response) {
  const grid = $('#memory-grid'); grid.replaceChildren();
  response.results.forEach(item => grid.append(memoryCard(item)));
  const filtered = state.query || state.kind || state.folder || $('#date-filter').value;
  $('#collection-title').textContent = state.folder ? fileName(state.folder) : 'All memories';
  $('#collection-subtitle').textContent = state.folder ? state.folder : 'The things you saved. Ready when you need them.';
  $('#results-description').textContent = `${response.results.length}${response.results.length === state.limit ? '+' : ''} ${filtered ? 'matching ' : ''}${response.results.length === 1 ? 'memory' : 'memories'}${state.query ? ` for “${state.query}”` : ''}`;
  $('#search-timing').textContent = `${response.seconds.toFixed(2)}s`;
  $('#clear-filters').hidden = !filtered;
  $('#ask-button').hidden = !state.query;
  $('#refine-button').hidden = !state.query || !response.results.some(item => item.kind === 'image');
  $('#load-more').hidden = response.results.length < state.limit || state.limit >= 100;
  $('#empty-state').hidden = response.results.length > 0;
  const emptyCollection = !state.status?.assets;
  $('#empty-title').textContent = emptyCollection ? 'A place for the things you want to find again.' : 'Nothing matched this search.';
  $('#empty-copy').textContent = emptyCollection ? 'Add your screenshot folder, saved receipts, or voice notes. Then search in your own words.' : 'Try a simpler description, another date, or a different folder. You can also add more files.';
  $('#empty-add').textContent = emptyCollection ? 'Add your first folder' : 'Add files or folder';
}
function memoryCard(item) {
  const card = node('article', 'memory-card');
  const preview = node('button', `preview-button ${item.kind}-preview-button`); preview.setAttribute('aria-label', `${item.kind === 'audio' ? 'Play' : 'Inspect'} ${item.name}`);
  if (item.kind === 'image') {
    const image = node('img'); image.src = `/api/thumbnails/${item.id}`; image.alt = `Preview of ${item.name}`; image.loading = 'lazy';
    image.addEventListener('error', () => { image.remove(); const fallback = node('div', 'missing-preview'); fallback.append(icon('image'), node('span', '', 'Preview unavailable')); preview.prepend(fallback); }, {once: true});
    preview.append(image);
  } else if (item.kind === 'audio') {
    const voice = node('div', 'voice-preview');
    const top = node('div', 'voice-top'); top.append(icon('mic'), node('span', '', 'Voice memo'));
    const wave = node('div', 'waveform'); wave.setAttribute('aria-hidden', 'true'); wave.title = 'Decorative waveform; not an audio amplitude plot';
    for (let index = 0; index < 40; index++) { const bar = node('i'); bar.style.height = `${12 + Math.abs(Math.sin(index * 1.7) * Math.cos(index * .43)) * 42}px`; wave.append(bar); }
    const bottom = node('div', 'voice-bottom'); const play = node('span', 'voice-play'); play.append(icon('play'));
    bottom.append(play, node('span', '', `${timestamp(item.metadata.duration || 0)} · ${item.metadata.language || 'audio'}`));
    voice.append(top, wave, bottom); preview.append(voice);
  } else {
    const note = node('div', 'note-preview');
    const lines = item.text.split(/\n|(?<=[.!?])\s+/);
    note.append(icon('file'), node('strong', '', lines[0]?.replace(/^#+\s*/, '') || item.name), node('p', '', lines.slice(1).join(' ') || item.text)); preview.append(note);
  }
  if (item.kind === 'image') { const tag = node('span', 'preview-tag'); tag.append(icon('image'), node('span', '', 'Image')); preview.append(tag); }
  preview.addEventListener('click', () => inspect(item, preview, item.kind === 'audio'));
  const heading = node('div', 'card-heading');
  const title = node('button', 'card-title', item.name); title.addEventListener('click', () => inspect(item, title));
  heading.append(title, node('span', 'card-date', date(item.captured_at)));
  const meta = node('div', 'card-meta');
  const sourcePath = item.paths[0] || '';
  const parent = sourcePath.split(/[\\/]/).slice(-2, -1)[0] || 'Local files';
  meta.append(icon('folder'), node('span', '', `${parent} · ${bytes(item.size)}${item.paths.length > 1 ? ` · ${item.paths.length} locations` : ''}`));
  card.append(preview, heading, meta);
  if (item.text) card.append(node('p', 'card-excerpt', item.text));
  if (state.query && item.channels.length) { const match = node('div', 'match-label'); match.append(icon('search'), node('span', '', `${item.channels.join(' + ')} match${item.start !== null ? ` · ${timestamp(item.start)}` : ''}`)); card.append(match); }
  return card;
}

async function inspect(item, opener, autoplay = false, citation = null) {
  state.opener = opener;
  $('#inspector-title').textContent = item.name;
  $('#inspector-kind').textContent = {image: 'Saved image', audio: 'Voice note', text: 'Text note'}[item.kind];
  $('#inspector-date').textContent = `${new Date(item.captured_at * 1000).toLocaleString()} · ${bytes(item.size)}`;
  $('#inspector-media').replaceChildren(); $('#inspector-evidence').textContent = 'Loading source evidence…'; $('#inspector-paths').replaceChildren();
  const source = citation ? `/api/evidence-images/${item.id}` : `/api/files/${item.id}`;
  $('#original-link').href = source;
  $('#original-link').textContent = citation ? 'Open cited image' : 'Open original';
  $('#original-link').hidden = false;
  $('#inspector').showModal();
  let audio;
  if (item.kind === 'image') {
    const image = node('img'); image.alt = item.name;
    if (citation) {
      const frame = node('div', 'citation-image');
      const highlight = node('span', 'citation-highlight');
      const [left, top, right, bottom] = citation.box;
      const [width, height] = citation.dimensions;
      highlight.setAttribute('aria-hidden', 'true');
      highlight.style.left = `${100 * left / width}%`;
      highlight.style.top = `${100 * top / height}%`;
      highlight.style.width = `${100 * (right - left) / width}%`;
      highlight.style.height = `${100 * (bottom - top) / height}%`;
      image.addEventListener('load', () => { highlight.hidden = false; }, {once: true});
      image.addEventListener('error', () => {
        frame.replaceChildren(node('p', 'helper', 'The cited image changed or is unavailable. Reindex the file to refresh its evidence.'));
        $('#original-link').hidden = true;
      }, {once: true});
      highlight.hidden = true;
      frame.append(image, highlight);
      $('#inspector-media').append(frame);
    } else {
      $('#inspector-media').append(image);
    }
    image.src = source;
  }
  if (item.kind === 'audio') {
    audio = node('audio'); audio.controls = true; audio.preload = 'metadata'; audio.src = `/api/files/${item.id}`; audio.setAttribute('aria-label', `Play ${item.name}`);
    audio.addEventListener('loadedmetadata', () => { if (item.start !== null) audio.currentTime = item.start; }, {once: true});
    $('#inspector-media').append(audio);
    if (autoplay) audio.play().catch(() => toast('Use the audio controls to start playback.'));
  }
  try {
    const detail = await api(`/api/assets/${item.id}`);
    const evidence = $('#inspector-evidence'); evidence.replaceChildren();
    if (citation) evidence.append(node('p', 'citation-quote', citation.text));
    if (audio) evidence.append(node('p', 'transcript-notice', 'Machine-generated transcript. Names and numbers may be misheard; listen to the original to verify.'));
    for (const chunk of detail.chunks) {
      if (!chunk.text) continue;
      if (audio && chunk.start !== null) {
        const segment = node('div', 'segment'); const seek = node('button', '', timestamp(chunk.start)); seek.setAttribute('aria-label', `Play from ${timestamp(chunk.start)}`);
        seek.addEventListener('click', () => { audio.currentTime = chunk.start; audio.play().catch(error => toast(error.message)); });
        segment.append(seek, node('p', '', chunk.text)); evidence.append(segment);
      } else evidence.append(node('p', '', chunk.text));
    }
    if (!citation && !detail.chunks.some(chunk => chunk.text)) evidence.textContent = 'No text was extracted. This file is searchable through its visual embedding when visual indexing is enabled.';
    $('#inspector-paths').append(node('strong', '', 'Original file locations'));
    detail.paths.forEach(path => $('#inspector-paths').append(node('div', '', path)));
    if (detail.metadata.ocr_strategy === 'delta') $('#inspector-paths').append(node('p', '', `Changed-region OCR processed ${(detail.metadata.ocr_area_fraction * 100).toFixed(1)}% of this image and reused ${detail.metadata.reused_lines} text lines.`));
  } catch (error) { $('#inspector-evidence').textContent = error.message; }
}
$('#close-inspector').addEventListener('click', () => $('#inspector').close());
$('#inspector').addEventListener('close', () => { $('#inspector-media audio')?.pause(); state.opener?.focus(); });
$('#inspector').addEventListener('click', event => { if (event.target === $('#inspector') && event.offsetX < 0) $('#inspector').close(); });

function openImport() { setView('library'); $('#import-panel').hidden = false; $('#import-path').focus(); }
for (const id of ['add-files', 'sidebar-add', 'folders-add', 'empty-add']) $(`#${id}`).addEventListener('click', openImport);
$('#close-import').addEventListener('click', () => { $('#import-panel').hidden = true; $('#add-files').focus(); });
$('#import-form').addEventListener('submit', event => { event.preventDefault(); startIndex($('#import-path').value); });
async function startIndex(path) {
  setView('library');
  $('#index-path').disabled = true;
  notice('');
  try {
    const response = await api('/api/index', {path});
    state.job = response.job_id;
    sessionStorage.setItem('brain-job', state.job);
    $('#import-panel').hidden = true;
    $('#index-progress').hidden = false;
    pollJob();
  } catch (error) { notice(error.message, true); $('#index-path').disabled = false; }
}
async function pollJob() {
  if (!state.job) return;
  try {
    const job = await api(`/api/jobs/${state.job}`);
    $('#index-progress').hidden = false;
    $('#progress-title').textContent = job.state === 'queued' ? 'Preparing local models…' : 'Making your files searchable…';
    $('#progress-count').textContent = `${job.current} / ${job.total || '…'}`;
    $('#progress-bar').value = job.total ? job.current / job.total * 100 : 0;
    $('#progress-file').textContent = job.path;
    if (job.state === 'complete' || job.state === 'error') {
      state.job = null; sessionStorage.removeItem('brain-job'); $('#index-progress').hidden = true; $('#index-path').disabled = false;
      if (job.state === 'error') notice(job.error, true);
      else {
        const report = job.report;
        const message = `${report.indexed} indexed · ${report.cached} cached · ${report.duplicate} duplicates reused · ${report.seconds.toFixed(1)}s`;
        notice(message + (report.errors.length ? `\n${report.errors.map(item => `${fileName(item.path)}: ${item.error}`).join('\n')}` : ''), report.errors.length > 0);
        await refreshStatus(); await refreshSearch();
      }
      return;
    }
    setTimeout(pollJob, 1000);
  } catch (error) { state.job = null; sessionStorage.removeItem('brain-job'); $('#index-progress').hidden = true; $('#index-path').disabled = false; notice(error.message, true); }
}
async function browse(path) {
  try {
    const response = await api('/api/folders' + (path ? `?path=${encodeURIComponent(path)}` : ''));
    const container = $('#folder-browser'); container.hidden = false; container.replaceChildren();
    const top = node('div', 'browser-actions'); top.append(node('p', '', response.path || 'Choose a starting folder'));
    if (response.path) { const choose = node('button', 'text-button', 'Use this folder'); choose.addEventListener('click', () => { $('#import-path').value = response.path; container.hidden = true; }); top.append(choose); }
    container.append(top);
    if (response.parent) { const parent = node('button', 'browser-row', 'Parent folder'); parent.prepend(icon('folder')); parent.addEventListener('click', () => browse(response.parent)); container.append(parent); }
    for (const folder of response.folders) { const row = node('button', 'browser-row', response.path ? fileName(folder) : folder); row.prepend(icon('folder')); row.addEventListener('click', () => browse(folder)); container.append(row); }
    if (!response.folders.length) container.append(node('p', 'helper', 'No subfolders. Use this folder to index its files.'));
  } catch (error) { notice(error.message, true); }
}
$('#browse-folders').addEventListener('click', () => browse($('#import-path').value.trim() || null));
$('#search-form').addEventListener('submit', event => { event.preventDefault(); state.limit = 30; notice(''); refreshSearch(); });
$('#search-input').addEventListener('search', () => { if (!$('#search-input').value) refreshSearch(); });
$$('.tab').forEach(button => button.addEventListener('click', () => {
  state.kind = button.dataset.kind; state.limit = 30;
  $$('.tab').forEach(tab => { tab.classList.toggle('active', tab === button); tab.setAttribute('aria-pressed', tab === button ? 'true' : 'false'); });
  refreshSearch();
}));
$$('[data-query]').forEach(button => button.addEventListener('click', () => {
  $('#search-input').value = button.dataset.query;
  if (button.dataset.kind) $(`.tab[data-kind="${button.dataset.kind}"]`).click(); else refreshSearch();
}));
$('#date-filter').addEventListener('change', () => refreshSearch());
$('#clear-filters').addEventListener('click', () => { $('#search-input').value = ''; $('#date-filter').value = ''; state.folder = null; state.limit = 30; $('.tab[data-kind=""]').click(); });
$('#load-more').addEventListener('click', () => { state.limit = Math.min(100, state.limit + 30); refreshSearch(); });
function closeAnswer() {
  state.answerRequest++;
  $('#answer-panel').hidden = true;
  $('#ask-button').disabled = false;
  $('#refine-button').disabled = false;
  $('#refine-button').hidden = !state.query || !state.results.some(item => item.kind === 'image');
}

async function showAnswer(refine = false) {
  const request = ++state.answerRequest;
  $('#ask-button').disabled = true;
  $('#refine-button').disabled = true;
  $('#answer-panel').hidden = false;
  $('#answer-text').textContent = refine ? 'Retrying text recognition…' : 'Reading matching files…';
  $('#answer-mode').textContent = '';
  const citations = $('#answer-citations');
  citations.replaceChildren();
  citations.hidden = true;
  try {
    const response = await api('/api/ask', {...searchBody(), refine});
    if (request !== state.answerRequest) return;
    $('#answer-text').textContent = response.answer;
    const related = new Map(response.results.map(item => [item.id, item]));
    $('#refine-button').hidden = !response.results.some(item => item.kind === 'image');
    for (const citation of response.citations) {
      const line = node('li');
      const button = node('button', 'text-button', `${citation.value} · ${citation.source}`);
      button.addEventListener('click', () => inspect(related.get(citation.asset_id), button, false, citation));
      line.append(button);
      citations.append(line);
    }
    citations.hidden = !response.citations.length;
    $('#answer-mode').textContent = response.mode === 'ollama' ? `Generated locally with ${response.model}. Verify the cited sources.` : '';
    if (refine && response.refinement?.attempted === 0) $('#answer-mode').textContent = 'No matching image could be retried within the time budget.';
    if (response.warnings.length) notice(response.warnings.join('\n'), true);
  } catch (error) {
    if (request === state.answerRequest) $('#answer-text').textContent = error.message;
  } finally {
    if (request === state.answerRequest) {
      $('#ask-button').disabled = false;
      $('#refine-button').disabled = false;
    }
  }
}

$('#refine-button').addEventListener('click', () => {
  if (!$('#answer-panel').hidden) showAnswer(true);
  else { toast('Retrying text recognition…'); refreshSearch(true); }
});
$('#ask-button').addEventListener('click', () => showAnswer());
$('#close-answer').addEventListener('click', closeAnswer);
document.addEventListener('keydown', event => {
  if (event.key === '/' && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName) && !$('#inspector').open) { event.preventDefault(); setView('library'); $('#search-input').focus(); }
});

const commands = [
  ['Start a collection', 'brain init', 'Creates a local index. Models download only when first needed.'],
  ['Add one file', 'brain index "C:\\Users\\you\\Pictures\\receipt.png"', 'Extracts content and embeds the file for search.'],
  ['Index an entire folder', 'brain index "C:\\Users\\you\\Pictures\\Screenshots"', 'Recursively indexes supported files and saves the folder as a source.'],
  ['Find something you remember', 'brain search "white sneakers last month"', 'Combines visual, semantic, and keyword rankings with a calendar date filter.'],
  ['Find a moment in a voice note', 'brain search "cafe name" --kind audio', 'Returns the source audio file and matching timestamp.'],
  ['Watch for new files', 'brain watch', 'Watches saved source folders until you press Ctrl+C.'],
  ['Open this interface', 'brain serve', 'Runs the app at http://127.0.0.1:8765.'],
  ['Try the synthetic playground', 'brain index playground/inbox\nbrain benchmark playground/scenarios.json', 'Scenario labels stay outside the indexed inbox.'],
];
for (const [title, command, description] of commands) {
  const section = node('section', 'cli-command'); const line = node('div', 'command-line'); const copy = node('button', 'icon-button'); copy.setAttribute('aria-label', `Copy ${title.toLowerCase()} command`); copy.append(icon('copy'));
  copy.addEventListener('click', async () => { try { await navigator.clipboard.writeText(command); toast('Command copied.'); } catch { toast('Select the command to copy it manually.'); } });
  line.append(node('code', '', command), copy); section.append(node('h2', '', title), line, node('p', '', description)); $('#cli-commands').append(section);
}
async function boot() {
  try {
    await refreshStatus(); await refreshSearch();
    const jobs = await api('/api/jobs');
    const active = jobs.find(job => ['queued', 'running'].includes(job.state));
    state.job = active?.id || sessionStorage.getItem('brain-job');
    if (state.job) { $('#index-path').disabled = true; pollJob(); }
  } catch (error) { notice(`Could not connect to the local backend: ${error.message}. Restart brain serve and reload.`, true); }
}
boot();
// Changes made through the CLI become visible without reloading the app.
let refreshing = false;
setInterval(async () => {
  if (document.hidden || refreshing || state.job || $('#inspector').open) return;
  refreshing = true;
  try {
    const previous = JSON.stringify([state.status?.assets, state.status?.locations, state.status?.events?.[0]?.id]);
    await refreshStatus();
    const current = JSON.stringify([state.status.assets, state.status.locations, state.status.events?.[0]?.id]);
    if (previous !== current && state.view === 'library') await refreshSearch();
  } catch {} finally { refreshing = false; }
}, 8000);
