const DEV_PREVIEW_PATH = '/api/dev/preview/candidates';
const DEV_PREVIEW_TOKEN_HEADER = 'X-UEC-Dev-Preview-Token';
const GRAPH_TOKEN_HEADER = 'X-UEC-Private-Graph-Token';
const READINESS_PATH = 'private-review/readiness-matrix.json';
const READINESS_STATES = [
  'infrastructure-only',
  'acquisition-ready',
  'private-candidate-ready',
  'human-review-ready',
  'publication-eligible',
  'blocked',
];
const QUEUES = [
  { id: 'contradictions', label: 'Contradictions', columns: ['claim_id', 'facility_id', 'organization_id', 'claim_domain', 'claim_kind', 'observed_at', 'confidence', 'review_state', 'privacy_status', 'publication_status'] },
  { id: 'unresolved-identities', label: 'Unresolved identities', columns: ['crosswalk_id', 'left_identifier_id', 'right_identifier_id', 'assertion_status', 'confidence', 'observed_at', 'source_id', 'source_record_id', 'review_state', 'privacy_status', 'publication_status'] },
  { id: 'quarantine', label: 'Quarantine', columns: ['source_record_id', 'source_id', 'source_state', 'received_at'] },
  { id: 'claims', label: 'Claims / support', columns: ['claim_id', 'source_id', 'claim_domain', 'claim_kind', 'value_state', 'unknown_reason', 'observed_at', 'confidence', 'review_state', 'storage_state', 'privacy_status', 'publication_status', 'support_count', 'contradicting_support_count'] },
  { id: 'rejected-candidates', label: 'Rejected candidates', columns: ['crosswalk_id', 'source_id', 'source_record_id', 'assertion_status', 'confidence', 'observed_at', 'review_state', 'privacy_status', 'publication_status'] },
  { id: 'suppression', label: 'Suppression', columns: ['case_id', 'case_status', 'event_type', 'reason_category', 'policy_version', 'occurred_at'] },
  { id: 'statistics', label: 'Statistics', columns: ['metric', 'value'] },
];

const state = {
  candidates: [],
  selectedCandidate: null,
  queues: {},
  activeQueue: 'contradictions',
  entities: [],
  selectedEntity: null,
  observations: [],
  readiness: null,
  readinessError: false,
  reviewPacket: null,
  reviewPacketError: null,
};

export function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]));
}

export function displayValue(value, fallback = 'Unavailable') {
  return value === null || value === undefined || value === '' ? fallback : String(value);
}

function isRecord(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function finiteOrNull(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function safeHttpUrl(value) {
  if (typeof value !== 'string' || !/^https?:\/\//i.test(value)) return null;
  return value;
}

export function normalizePreviewRow(row) {
  if (!isRecord(row) || !String(row.candidate_id || row.source_record_id || '').trim() || !String(row.facility_id || '').trim()) {
    throw new Error('Private candidate preview response was rejected safely.');
  }
  const latitude = finiteOrNull(row.latitude);
  const longitude = finiteOrNull(row.longitude);
  const coordinatePair = (latitude === null) === (longitude === null);
  if (!coordinatePair) throw new Error('Private candidate preview response was rejected safely.');
  return {
    candidateId: String(row.candidate_id || row.source_record_id),
    sourceRecordId: String(row.source_record_id || row.candidate_id),
    facilityId: String(row.facility_id),
    name: displayValue(row.canonical_name, 'Unnamed candidate'),
    countryCode: displayValue(row.country_code),
    city: row.city === null || row.city === undefined ? null : String(row.city),
    category: displayValue(row.category),
    displayPrecision: displayValue(row.display_precision),
    coordinatePrecision: displayValue(row.coordinate_precision),
    coordinateReviewStatus: displayValue(row.coordinate_review_status),
    hasCoordinatePair: latitude !== null && longitude !== null,
    sourceType: displayValue(row.source_type),
    sourceId: displayValue(row.provenance_source_id),
    sourceName: displayValue(row.provenance_source_name),
    sourceUrl: safeHttpUrl(row.provenance_source_url),
    retrievedAt: displayValue(row.provenance_retrieved_at),
    factualReviewStatus: displayValue(row.factual_review_status),
    privacyStatus: displayValue(row.privacy_screening_status),
    releaseId: displayValue(row.release_id),
    releaseStatus: displayValue(row.release_status, 'candidate'),
    previewLabel: displayValue(row.preview_label, 'Private candidate — not reviewed or published'),
    projectApproval: row.project_approval === false ? false : null,
    maintainerApproval: displayValue(row.maintainer_approval),
    suppressionState: displayValue(row.suppression_state),
  };
}

function normalizeEnvelope(payload, label) {
  if (!isRecord(payload) || !Array.isArray(payload.data)) throw new Error(`${label} response was rejected safely.`);
  return payload;
}

async function requestJson(path, token, header, label, params = {}) {
  if (!String(token || '').trim()) throw new Error(`${label} requires an operator token.`);
  const url = new URL(path, window.location.href);
  Object.entries(params).forEach(([key, value]) => url.searchParams.set(key, String(value)));
  let response;
  try {
    response = await fetch(url.toString(), {
      cache: 'no-store',
      headers: { Accept: 'application/json', [header]: token },
    });
  } catch (_error) {
    throw new Error(`${label} could not be reached.`);
  }
  if (!response.ok) throw new Error(`${label} unavailable (HTTP ${response.status}).`);
  let payload;
  try {
    payload = await response.json();
  } catch (_error) {
    throw new Error(`${label} response was rejected safely.`);
  }
  return normalizeEnvelope(payload, label);
}

function setAuthStatus(id, message, status = 'idle') {
  const element = document.getElementById(id);
  if (!element) return;
  element.dataset.state = status;
  element.innerHTML = `<span class="status-dot"></span>${escapeHtml(message)}`;
}

function setText(id, value) {
  const element = document.getElementById(id);
  if (element) element.textContent = value;
}

function statusClass(value) {
  const normalized = String(value || '').toLowerCase();
  if (['passed', 'observed', 'accepted', 'confirmed', 'supported', 'active'].some((token) => normalized.includes(token))) return 'badge-green';
  if (['rejected', 'blocked', 'restricted', 'disputed', 'quarantined', 'review_required'].some((token) => normalized.includes(token))) return 'badge-red';
  if (['candidate', 'pending', 'unknown', 'unavailable', 'unreviewed'].some((token) => normalized.includes(token))) return 'badge-amber';
  return 'badge-slate';
}

function badge(value, fallback = 'Unavailable') {
  const text = displayValue(value, fallback);
  return `<span class="badge ${statusClass(text)}">${escapeHtml(text)}</span>`;
}

function unknown(value) {
  return `<span class="${value === null || value === undefined || value === '' ? 'unknown' : ''}">${escapeHtml(displayValue(value))}</span>`;
}

function candidateStatusNote(candidate) {
  if (!candidate) return 'Private preview not loaded';
  return `${candidate.releaseStatus} · not a published record`;
}

function renderSummary() {
  const candidateCount = state.candidates.length;
  const queueCount = Object.values(state.queues).reduce((total, queue) => total + (Array.isArray(queue) ? queue.length : 0), 0);
  const countryCount = state.readiness && isRecord(state.readiness.countries) ? Object.keys(state.readiness.countries).length : null;
  const blockedCountries = countryCount === null ? null : Object.values(state.readiness.countries).filter((item) => isRecord(item) && item.state === 'blocked').length;
  const packetBlockers = state.reviewPacket?.blockers && isRecord(state.reviewPacket.blockers)
    ? Object.values(state.reviewPacket.blockers).reduce((total, values) => total + (Array.isArray(values) ? values.length : 0), 0)
    : 0;
  const blockerCount = blockedCountries === null ? null : blockedCountries + (state.queues.quarantine?.length || 0) + (state.queues['unresolved-identities']?.length || 0) + packetBlockers;
  setText('metric-candidates', String(candidateCount));
  setText('metric-candidates-note', candidateCount ? 'Authenticated candidate rows' : 'No candidate rows returned');
  setText('metric-queues', Object.keys(state.queues).length ? String(queueCount) : '—');
  setText('metric-queues-note', Object.keys(state.queues).length ? 'Separate graph queue observations' : 'Graph access required');
  setText('metric-countries', countryCount === null ? '—' : String(countryCount));
  setText('metric-countries-note', countryCount === null ? 'Readiness asset unavailable' : 'Derived context, not an approval');
  setText('metric-blockers', blockerCount === null ? '—' : String(blockerCount));
  setText('metric-blockers-note', blockerCount === null ? 'Unknown until evidence loads' : 'Contextual blockers and unresolved queues');
  setText('rail-candidate-count', String(candidateCount));
  setText('rail-queue-count', Object.keys(state.queues).length ? String(queueCount) : '—');
  setText('rail-country-count', countryCount === null ? '—' : String(countryCount));
}

function renderCandidateList() {
  const list = document.getElementById('candidate-list');
  if (!list) return;
  setText('candidate-list-count', state.candidates.length ? `${state.candidates.length} row${state.candidates.length === 1 ? '' : 's'}` : '0 rows');
  if (!state.candidates.length) {
    list.innerHTML = '<div class="empty-state"><strong>No private candidate rows.</strong><span>The authenticated response was empty. No fallback records are shown.</span></div>';
    return;
  }
  list.innerHTML = state.candidates.map((candidate, index) => `<button class="candidate-item ${state.selectedCandidate === index ? 'active' : ''}" data-candidate-index="${index}" type="button"><strong>${escapeHtml(candidate.name)}</strong><small>${escapeHtml(candidate.countryCode)} · ${escapeHtml(candidate.category)}</small><span class="item-state">${escapeHtml(candidate.releaseStatus)}</span></button>`).join('');
  list.querySelectorAll('[data-candidate-index]').forEach((button) => {
    button.addEventListener('click', () => {
      state.selectedCandidate = Number(button.dataset.candidateIndex);
      renderCandidateList();
      renderCandidateDetail();
    });
  });
}

function fact(label, value, isUnknown = false) {
  return `<div><dt>${escapeHtml(label)}</dt><dd class="${isUnknown ? 'unknown' : ''}">${isUnknown ? 'Unavailable' : value}</dd></div>`;
}

function renderCandidateDetail() {
  const detail = document.getElementById('candidate-detail');
  if (!detail) return;
  const candidate = state.selectedCandidate === null ? null : state.candidates[state.selectedCandidate];
  if (!candidate) {
    detail.innerHTML = '<div class="empty-state empty-state-large"><span class="empty-icon" aria-hidden="true">↳</span><strong>Select a candidate row.</strong><span>Details are limited to safe review fields. Private addresses, raw source material, geocoder details, and reviewer identities stay out of this surface.</span></div>';
    return;
  }
  const location = [candidate.city, candidate.countryCode].filter(Boolean).join(', ') || 'Region unavailable';
  const coordinateState = candidate.hasCoordinatePair ? 'Pair present under authenticated private preview contract' : 'No coordinate pair in preview response';
  const projectDecision = candidate.projectApproval === false ? 'false — candidate is not approved' : 'Unavailable — no positive decision is inferred';
  detail.innerHTML = `
    <div class="detail-title">
      <div><p class="eyebrow">PRIVATE CANDIDATE · ${escapeHtml(candidate.candidateId)}</p><h3>${escapeHtml(candidate.name)}</h3><p class="detail-subtitle">${escapeHtml(location)} · ${escapeHtml(candidate.category)} · source record ${escapeHtml(candidate.sourceRecordId)}</p></div>
      <div class="detail-badges">${badge(candidate.releaseStatus, 'candidate')}${badge(candidate.factualReviewStatus)}${badge(candidate.privacyStatus)}</div>
    </div>
    <div class="detail-grid">
      <article class="detail-card"><h4>Source terms / attribution</h4><dl class="facts">${fact('Source type', escapeHtml(candidate.sourceType))}${fact('Source name', escapeHtml(candidate.sourceName))}${fact('Source ID', escapeHtml(candidate.sourceId))}${fact('Source URL', candidate.sourceUrl ? `<span class="unknown">text only — no public link</span>` : 'Unavailable', !candidate.sourceUrl)}${fact('Terms status', 'Unavailable in candidate contract', true)}</dl><p class="notice-small">Attribution metadata is shown as supplied. A URL is intentionally not made clickable by this console.</p></article>
      <article class="detail-card"><h4>Provenance</h4><dl class="facts">${fact('Retrieved at', escapeHtml(candidate.retrievedAt))}${fact('Release ID', escapeHtml(candidate.releaseId))}${fact('Release status', badge(candidate.releaseStatus, 'candidate'))}${fact('Candidate label', escapeHtml(candidate.previewLabel))}</dl></article>
      <article class="detail-card"><h4>Privacy / location risk</h4><dl class="facts">${fact('Privacy screening', badge(candidate.privacyStatus))}${fact('Address', 'Withheld by console')}${fact('Coordinate pair', escapeHtml(coordinateState))}${fact('Display precision', badge(candidate.displayPrecision))}${fact('Coordinate precision', badge(candidate.coordinatePrecision))}${fact('Coordinate review state', badge(candidate.coordinateReviewStatus))}</dl></article>
      <article class="detail-card"><h4>Review state</h4><dl class="facts">${fact('Factual review', badge(candidate.factualReviewStatus))}${fact('Project decision', escapeHtml(projectDecision))}${fact('Maintainer approval', badge(candidate.maintainerApproval))}${fact('Suppression state', badge(candidate.suppressionState))}${fact('Reviewer identity', 'Withheld by console')}</dl></article>
      <article class="detail-card detail-card-wide"><h4>Counts, deltas, quarantine, and blockers</h4><div class="detail-grid detail-grid-inner"><dl class="facts">${fact('Candidate count', 'Unavailable in preview contract', true)}${fact('Count delta', 'Unavailable — do not infer from this page', true)}${fact('Observation count', 'Unavailable in preview contract', true)}</dl><ul class="blocker-list"><li>Candidate release status remains <strong>${escapeHtml(candidate.releaseStatus)}</strong>.</li><li>Project decision is not positive in this preview contract.</li><li>Quarantine reason is not included; inspect the quarantine queue.</li><li>Suppression state is not included; absence is not clearance.</li><li>No publication, export, or public-link action is available here.</li></ul></div><p class="notice-small">The preview payload is allowlisted before rendering. Raw source payloads, addresses, geocoder requests/responses, requester details, sensitive notes, and reviewer identities are never rendered.</p></article>
    </div>`;
}

const FORBIDDEN_PACKET_KEYS = new Set([
  'source_values', 'raw_fields', 'address', 'street', 'street_address', 'latitude', 'longitude',
  'coordinates', 'geocoder_query', 'geocoder_response', 'phone', 'email', 'requester',
  'requester_contact', 'reviewer_identity', 'records', 'rows',
]);

export function validateReviewPacket(value, path = 'packet') {
  if (Array.isArray(value)) {
    value.forEach((child, index) => validateReviewPacket(child, `${path}[${index}]`));
    return value;
  }
  if (!isRecord(value)) return value;
  const leaked = Object.keys(value).filter((key) => FORBIDDEN_PACKET_KEYS.has(key.toLowerCase()));
  if (leaked.length) throw new Error(`Review packet rejected safely at ${path}.`);
  Object.entries(value).forEach(([key, child]) => validateReviewPacket(child, `${path}.${key}`));
  return value;
}

function packetEntries(value) {
  if (!isRecord(value)) return '<li class="unknown">Unavailable</li>';
  const entries = Object.entries(value);
  if (!entries.length) return '<li class="unknown">None recorded</li>';
  return entries.slice(0, 24).map(([key, child]) => {
    const display = Array.isArray(child) ? child.join(' · ') : isRecord(child) ? JSON.stringify(child) : displayValue(child);
    return `<li><span>${escapeHtml(key.replaceAll('_', ' '))}</span><strong>${escapeHtml(display)}</strong></li>`;
  }).join('');
}

function renderReviewPacket() {
  const panel = document.getElementById('packet-summary');
  if (!panel) return;
  if (state.reviewPacketError) {
    panel.innerHTML = `<div class="error-state"><strong>Review packet unavailable.</strong> ${escapeHtml(state.reviewPacketError)}<p>Only row-free aggregate packets are accepted; no candidate fallback is inferred.</p></div>`;
    return;
  }
  const packet = state.reviewPacket;
  if (!packet) {
    panel.innerHTML = '<div class="empty-state"><strong>No local review packet loaded.</strong><span>The console does not infer counts, deltas, quarantine reasons, or blockers from candidate rows.</span></div>';
    return;
  }
  const counts = packet.counts || {};
  const diff = packet.release_diff || {};
  const diffCounts = diff.counts || {};
  const geospatial = packet.geospatial || {};
  panel.innerHTML = `<div class="packet-heading"><div><p class="eyebrow">LOCAL ROW-FREE PACKET</p><h3>${escapeHtml(displayValue(packet.source_id, 'Source unavailable'))}</h3><p class="notice-small">${escapeHtml(displayValue(packet.publication_boundary, 'Packet is evidence only; no approval is implied.'))}</p></div><span class="badge badge-amber">inspection only</span></div><div class="packet-grid"><article class="packet-card"><h4>Counts / deltas</h4><ul class="packet-facts">${packetEntries({ input: counts.input_rows, normalized: counts.normalized_rows, quarantined: counts.quarantined_rows, reconciles: counts.reconciles, added: diffCounts.added, changed: diffCounts.changed, not_observed: diffCounts.not_observed })}</ul></article><article class="packet-card"><h4>Quarantine reasons</h4><ul class="packet-facts">${packetEntries(packet.quarantine?.reasons)}</ul></article><article class="packet-card"><h4>Coordinate / privacy gates</h4><ul class="packet-facts">${packetEntries(geospatial.coordinate_gate_counts || geospatial.precision_counts)}</ul></article><article class="packet-card"><h4>Publication blockers</h4><ul class="packet-facts">${packetEntries(packet.blockers)}</ul></article></div>`;
}

async function loadReviewPacket(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  state.reviewPacket = null;
  state.reviewPacketError = null;
  try {
    const value = JSON.parse(await file.text());
    validateReviewPacket(value);
    if (!isRecord(value) || !String(value.schema_version || '').startsWith('private-review-packet-')) throw new Error('Unsupported packet schema.');
    state.reviewPacket = value;
  } catch (error) {
    state.reviewPacketError = error.message || 'Packet parsing failed.';
  }
  renderReviewPacket();
  renderSummary();
}

function normalizeQueueRows(kind, payload) {
  normalizeEnvelope(payload, `${kind} queue`);
  const definition = QUEUES.find((queue) => queue.id === kind);
  if (!definition || payload.data.some((row) => !Array.isArray(row))) throw new Error(`${kind} queue response was rejected safely.`);
  return payload.data.map((row) => definition.columns.map((_column, index) => displayValue(row[index], 'Unavailable')));
}

function renderQueue() {
  const panel = document.getElementById('queue-panel');
  if (!panel) return;
  const definition = QUEUES.find((queue) => queue.id === state.activeQueue);
  const rows = state.queues[state.activeQueue];
  if (!definition) return;
  if (rows?.error) {
    panel.innerHTML = `<div class="queue-error"><strong>${escapeHtml(rows.error)}</strong><p>Queue contents were cleared. Re-authenticate and retry; this console does not substitute candidate data.</p></div>`;
    return;
  }
  if (!Array.isArray(rows)) {
    panel.innerHTML = '<div class="empty-state"><strong>Private graph access required.</strong><span>Queue contents are not inferred from candidate rows.</span></div>';
    return;
  }
  if (!rows.length) {
    panel.innerHTML = `<div class="empty-state"><strong>No ${escapeHtml(definition.label.toLowerCase())} returned.</strong><span>An empty queue is not evidence that other review obligations are cleared.</span></div>`;
    return;
  }
  const headers = definition.columns.map((column) => `<th scope="col">${escapeHtml(column.replaceAll('_', ' '))}</th>`).join('');
  const body = rows.map((row) => `<tr>${row.map((value, index) => `<td class="${index === 0 ? 'value-strong' : ['blocked', 'quarantined', 'disputed', 'review_required', 'candidate'].some((token) => value.includes(token)) ? 'value-amber' : ''}">${escapeHtml(value)}</td>`).join('')}</tr>`).join('');
  panel.innerHTML = `<div class="queue-table-wrap"><table class="queue-table"><thead><tr>${headers}</tr></thead><tbody>${body}</tbody></table></div>`;
}

function setQueueTab(kind) {
  state.activeQueue = kind;
  document.querySelectorAll('.queue-tab').forEach((tab) => tab.classList.toggle('active', tab.dataset.queue === kind));
  renderQueue();
}

function normalizeEntity(row) {
  if (!isRecord(row) || !String(row.entity_id || '').trim()) throw new Error('Entity response was rejected safely.');
  return { id: String(row.entity_id), type: displayValue(row.entity_type), name: displayValue(row.canonical_name, 'Unnamed entity'), countryCode: displayValue(row.country_code), createdAt: displayValue(row.created_at) };
}

function normalizeObservation(row) {
  if (!isRecord(row)) throw new Error('Neighborhood response was rejected safely.');
  return {
    observationId: displayValue(row.relationship_observation_id),
    fromOrganizationId: displayValue(row.from_organization_id),
    targetFacilityId: displayValue(row.target_facility_id),
    targetOrganizationId: displayValue(row.target_organization_id),
    relationshipType: displayValue(row.relationship_type),
    assertionStatus: displayValue(row.assertion_status),
    observedAt: displayValue(row.observed_at),
    confidence: displayValue(row.confidence),
    reviewState: displayValue(row.review_state),
    storageState: displayValue(row.storage_state),
    privacyStatus: displayValue(row.privacy_status),
    publicationStatus: displayValue(row.publication_status),
    sourceId: displayValue(row.source_id),
    sourceRecordId: displayValue(row.source_record_id),
  };
}

function observationBucket(observation) {
  const status = `${observation.assertionStatus} ${observation.reviewState}`.toLowerCase();
  if (/(reject|disput)/.test(status)) return 'rejected';
  if (/(accept|confirm|support|observed)/.test(status)) return 'supporting';
  return 'other';
}

function renderEntities() {
  const list = document.getElementById('entity-list');
  if (!list) return;
  setText('entity-count', state.entities.length ? `${state.entities.length} result${state.entities.length === 1 ? '' : 's'}` : '0 results');
  if (!state.entities.length) {
    list.innerHTML = '<div class="empty-state"><strong>No entities returned.</strong><span>No fallback entities are shown when the private search is empty.</span></div>';
    return;
  }
  list.innerHTML = state.entities.map((entity, index) => `<button class="entity-item ${state.selectedEntity === index ? 'active' : ''}" data-entity-index="${index}" type="button"><strong>${escapeHtml(entity.name)}</strong><small>${escapeHtml(entity.type)} · ${escapeHtml(entity.countryCode)}</small><span class="item-state">bounded entity metadata</span></button>`).join('');
  list.querySelectorAll('[data-entity-index]').forEach((button) => button.addEventListener('click', () => {
    state.selectedEntity = Number(button.dataset.entityIndex);
    renderEntities();
    loadNeighborhood(state.entities[state.selectedEntity]);
  }));
}

function observationCard(observation) {
  const endpoint = [observation.fromOrganizationId, observation.targetFacilityId, observation.targetOrganizationId].filter((value) => value !== 'Unavailable').join(' → ') || 'Endpoints unavailable';
  return `<article class="observation"><div class="observation-head"><strong>${escapeHtml(observation.relationshipType)}</strong><span>${escapeHtml(observation.assertionStatus)}</span></div><p>${escapeHtml(endpoint)}</p><div class="observation-meta"><span>observed ${escapeHtml(observation.observedAt)}</span><span>confidence ${escapeHtml(observation.confidence)}</span><span>review ${escapeHtml(observation.reviewState)}</span><span>privacy ${escapeHtml(observation.privacyStatus)}</span><span>publication ${escapeHtml(observation.publicationStatus)}</span><span>source ${escapeHtml(observation.sourceId)}</span><span>record ${escapeHtml(observation.sourceRecordId)}</span></div></article>`;
}

function renderNeighborhood() {
  const panel = document.getElementById('neighborhood-panel');
  if (!panel) return;
  const entity = state.selectedEntity === null ? null : state.entities[state.selectedEntity];
  if (!entity) {
    panel.innerHTML = '<div class="empty-state empty-state-large"><strong>Select an entity.</strong><span>Neighborhood results will be displayed as retained relationship observations, never as an ownership or operational-status conclusion.</span></div>';
    return;
  }
  const groups = { supporting: [], other: [], rejected: [] };
  state.observations.forEach((observation) => groups[observationBucket(observation)].push(observation));
  const group = (title, key, note) => `<section class="observation-group"><h4>${escapeHtml(title)} <span>${groups[key].length} retained</span></h4>${groups[key].length ? groups[key].map(observationCard).join('') : '<div class="empty-state"><span>No observations in this bucket.</span></div>'}<p class="notice-small">${escapeHtml(note)}</p></section>`;
  panel.innerHTML = `<div class="neighborhood-header"><div><p class="eyebrow">ENTITY NEIGHBORHOOD</p><h3>${escapeHtml(entity.name)}</h3><p>${escapeHtml(entity.type)} · ${escapeHtml(entity.countryCode)} · created ${escapeHtml(entity.createdAt)}</p></div><span class="badge badge-slate">${state.observations.length} observations</span></div>${group('Supporting observations', 'supporting', 'Status is shown as returned by the private graph; it is not a conclusion about ownership or operation.')}${group('Rejected or candidate observations', 'rejected', 'Rejected/disputed statuses remain visible as separate observations and are not silently merged away.')}${group('Other retained observations', 'other', 'Unresolved and unclassified statuses remain separate until an authorized human review records a decision.')}`;
}

function renderReadiness() {
  const matrix = document.getElementById('readiness-matrix');
  const legend = document.getElementById('readiness-legend');
  if (!matrix || !legend) return;
  legend.innerHTML = READINESS_STATES.map((stateName) => `<span class="legend-item">${escapeHtml(stateName)}</span>`).join('');
  if (state.readinessError || !state.readiness || !isRecord(state.readiness.countries)) {
    matrix.innerHTML = '<div class="error-state"><strong>Readiness context unavailable.</strong> The console fails closed and does not infer country status from candidate rows.</div>';
    return;
  }
  const entries = Object.entries(state.readiness.countries).sort(([, left], [, right]) => displayValue(left.name).localeCompare(displayValue(right.name)));
  matrix.innerHTML = entries.map(([code, item]) => {
    const safeState = READINESS_STATES.includes(item?.state) ? item.state : 'blocked';
    const basis = Array.isArray(item?.basis) ? item.basis.map((value) => displayValue(value)).join(' · ') : 'Basis unavailable';
    const sourceDetails = Array.isArray(item?.sources) ? item.sources.map((source) => {
      const attribution = source.attribution || {};
      const status = source.status || {};
      const blockers = Array.isArray(source.coverage?.limitations) ? source.coverage.limitations : [];
      return `<div class="readiness-source"><strong>${escapeHtml(displayValue(source.source_id))}</strong><span>${badge(status.acquisition)} · ${badge(status.metadata)}</span><small>Terms: ${escapeHtml(displayValue(attribution.terms_status))} · attribution required: ${attribution.attribution_required === true ? 'yes' : 'unknown'}</small><small>Notice: ${escapeHtml(displayValue(attribution.notice))}</small>${blockers.length ? `<small>Blockers: ${escapeHtml(blockers.join(' · '))}</small>` : ''}</div>`;
    }).join('') : '<span class="unknown">Source details unavailable</span>';
    return `<article class="readiness-card"><div><p class="eyebrow">${escapeHtml(code)}</p><h3>${escapeHtml(displayValue(item?.name, 'Country unavailable'))}</h3></div><span class="readiness-state state-${escapeHtml(safeState)}">${escapeHtml(safeState)}</span><p>${escapeHtml(displayValue(item?.summary, 'Context summary unavailable.'))}</p><div class="basis">Basis: ${escapeHtml(basis)}</div><details class="readiness-sources"><summary>${escapeHtml(displayValue(item?.source_count, 0))} source contracts</summary>${sourceDetails}</details></article>`;
  }).join('') || '<div class="empty-state"><strong>No country classifications.</strong><span>The readiness asset contained no country map.</span></div>';
}

async function loadReadiness() {
  setAuthStatus('readiness-status', 'Readiness context loading', 'loading');
  try {
    const response = await fetch(READINESS_PATH, { cache: 'no-store', headers: { Accept: 'application/json' } });
    if (!response.ok) throw new Error('unavailable');
    const payload = await response.json();
    if (!isRecord(payload) || payload.derived_context !== true || !isRecord(payload.countries)) throw new Error('invalid');
    state.readiness = payload;
    state.readinessError = false;
    setAuthStatus('readiness-status', 'Readiness context loaded · derived only', 'ready');
  } catch (_error) {
    state.readiness = null;
    state.readinessError = true;
    setAuthStatus('readiness-status', 'Readiness context unavailable', 'error');
  }
  renderReadiness();
  renderSummary();
}

async function loadCandidates() {
  const token = document.getElementById('dev-token')?.value || '';
  setAuthStatus('dev-auth-status', 'Loading private candidates', 'loading');
  state.candidates = [];
  state.selectedCandidate = null;
  renderCandidateList();
  renderCandidateDetail();
  renderSummary();
  try {
    const payload = await requestJson(`${DEV_PREVIEW_PATH}?limit=100`, token, DEV_PREVIEW_TOKEN_HEADER, 'Private candidate preview');
    if (payload.api_version !== 'dev-preview-v1' || payload.meta?.test_only !== true || payload.meta?.private_preview !== true) throw new Error('Private candidate preview response was rejected safely.');
    state.candidates = payload.data.map(normalizePreviewRow);
    state.selectedCandidate = state.candidates.length ? 0 : null;
    setAuthStatus('dev-auth-status', `Candidate preview connected · ${state.candidates.length} rows`, 'ready');
  } catch (error) {
    state.candidates = [];
    state.selectedCandidate = null;
    setAuthStatus('dev-auth-status', error.message || 'Private candidate preview unavailable', 'error');
  }
  renderCandidateList();
  renderCandidateDetail();
  renderSummary();
}

async function loadQueues() {
  const token = document.getElementById('graph-token')?.value || '';
  setAuthStatus('graph-auth-status', 'Loading private queues', 'loading');
  state.queues = {};
  renderQueue();
  renderSummary();
  try {
    const results = await Promise.all(QUEUES.map(async (queue) => {
      const payload = await requestJson(`/api/private/graph/queues/${queue.id}`, token, GRAPH_TOKEN_HEADER, `${queue.label} queue`, { limit: 100 });
      return [queue.id, normalizeQueueRows(queue.id, payload)];
    }));
    state.queues = Object.fromEntries(results);
    setAuthStatus('graph-auth-status', 'Private graph connected · queues loaded', 'ready');
  } catch (error) {
    state.queues = {};
    setAuthStatus('graph-auth-status', error.message || 'Private graph queues unavailable', 'error');
  }
  QUEUES.forEach((queue) => setText(`queue-count-${queue.id}`, Array.isArray(state.queues[queue.id]) ? String(state.queues[queue.id].length) : '—'));
  renderQueue();
  renderSummary();
}

async function searchEntities() {
  const token = document.getElementById('graph-token')?.value || '';
  const query = document.getElementById('entity-query')?.value || '';
  setText('graph-status', 'Searching private entities…');
  state.entities = [];
  state.selectedEntity = null;
  state.observations = [];
  renderEntities();
  renderNeighborhood();
  try {
    const payload = await requestJson('/api/private/graph/entities', token, GRAPH_TOKEN_HEADER, 'Private entity search', { q: query, limit: 50 });
    state.entities = payload.data.map(normalizeEntity);
    setText('graph-status', `${state.entities.length} bounded entities returned. Select one to read separate observations.`);
  } catch (error) {
    state.entities = [];
    setText('graph-status', error.message || 'Private entity search unavailable.');
  }
  renderEntities();
  renderNeighborhood();
}

async function loadNeighborhood(entity) {
  if (!entity) return;
  const token = document.getElementById('graph-token')?.value || '';
  const direction = document.getElementById('graph-direction')?.value || 'both';
  const depth = document.getElementById('graph-depth')?.value || '1';
  const panel = document.getElementById('neighborhood-panel');
  if (panel) panel.innerHTML = '<div class="empty-state"><strong>Loading bounded observations…</strong><span>Observations remain separate evidence records.</span></div>';
  try {
    const payload = await requestJson(`/api/private/graph/entities/${encodeURIComponent(entity.id)}/neighborhood`, token, GRAPH_TOKEN_HEADER, 'Private neighborhood', { direction, depth, limit: 100 });
    if (payload.meta?.private !== true) throw new Error('Private neighborhood response was rejected safely.');
    state.observations = payload.data.map(normalizeObservation);
    setText('graph-status', `${state.observations.length} retained observations for ${entity.name}.`);
  } catch (error) {
    state.observations = [];
    if (panel) panel.innerHTML = `<div class="error-state"><strong>${escapeHtml(error.message || 'Private neighborhood unavailable.')}</strong><p>Observation details were cleared. No graph conclusion is inferred.</p></div>`;
  }
  renderNeighborhood();
}

function clearSession() {
  const devInput = document.getElementById('dev-token');
  const graphInput = document.getElementById('graph-token');
  if (devInput) devInput.value = '';
  if (graphInput) graphInput.value = '';
  state.candidates = [];
  state.selectedCandidate = null;
  state.queues = {};
  state.entities = [];
  state.selectedEntity = null;
  state.observations = [];
  state.reviewPacket = null;
  state.reviewPacketError = null;
  const packetInput = document.getElementById('review-packet-file');
  if (packetInput) packetInput.value = '';
  setAuthStatus('dev-auth-status', 'Candidate preview not connected');
  setAuthStatus('graph-auth-status', 'Private graph not connected');
  setText('graph-status', 'Private graph search is not connected.');
  QUEUES.forEach((queue) => setText(`queue-count-${queue.id}`, '—'));
  renderCandidateList();
  renderCandidateDetail();
  renderQueue();
  renderEntities();
  renderNeighborhood();
  renderReviewPacket();
  renderSummary();
}

function bindEvents() {
  document.getElementById('load-candidates')?.addEventListener('click', loadCandidates);
  document.getElementById('load-queues')?.addEventListener('click', loadQueues);
  document.getElementById('search-entities')?.addEventListener('click', searchEntities);
  document.getElementById('clear-session')?.addEventListener('click', clearSession);
  document.getElementById('review-packet-file')?.addEventListener('change', loadReviewPacket);
  document.getElementById('entity-query')?.addEventListener('keydown', (event) => { if (event.key === 'Enter') searchEntities(); });
  document.getElementById('graph-direction')?.addEventListener('change', () => { if (state.selectedEntity !== null) loadNeighborhood(state.entities[state.selectedEntity]); });
  document.getElementById('graph-depth')?.addEventListener('change', () => { if (state.selectedEntity !== null) loadNeighborhood(state.entities[state.selectedEntity]); });
  document.querySelectorAll('.queue-tab').forEach((tab) => tab.addEventListener('click', () => setQueueTab(tab.dataset.queue)));
}

function init() {
  bindEvents();
  renderCandidateList();
  renderCandidateDetail();
  renderQueue();
  renderEntities();
  renderNeighborhood();
  renderReviewPacket();
  renderReadiness();
  renderSummary();
  loadReadiness();
}

if (typeof document !== 'undefined' && document.body?.dataset?.privateReview === 'true') init();
