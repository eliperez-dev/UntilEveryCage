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

const PACKET_TOP_KEYS = new Set([
  'schema_version', 'source_id', 'run_dir_digest', 'run_id', 'classification', 'review_required', 'reasons',
  'provenance', 'schema', 'counts', 'review_metrics', 'facility_observation', 'classification', 'geospatial',
  'quarantine', 'run', 'release_diff', 'graph_candidates', 'gates', 'platform', 'publication_boundary',
  'blockers', 'prior_eligible_release', 'release_promotion_allowed', 'public_exposure', 'operator_actions',
]);
const PROVENANCE_KEYS = new Set(['source_url', 'retrieved_at_utc', 'publication_date', 'effective_date', 'sha256', 'checksum_sha256', 'byte_size', 'code_version', 'config_version', 'redirects']);
const SCHEMA_KEYS = new Set(['adapter_version', 'schema_version', 'schema_fingerprint', 'schema_status']);
const COUNT_KEYS = new Set(['input_rows', 'normalized_rows', 'quarantined_rows', 'reconciles', 'qa_matches_manifest']);
const METRIC_FACILITY_KEYS = new Set(['schema_version', 'source_row_unit', 'input_observations', 'accepted_observations', 'quarantined_observations', 'distinct_provisional_facility_keys', 'accepted_distinct_provisional_facility_keys', 'distinct_observation_keys', 'repeated_provisional_facility_groups', 'repeated_observation_keys', 'max_observations_per_provisional_facility', 'identity_semantics', 'disappearance_semantics']);
const METRIC_CLASSIFICATION_KEYS = new Set(['schema_version', 'rows', 'review_state_counts', 'field_presence', 'status_state_counts', 'interpretation']);
const METRIC_GEOSPATIAL_KEYS = new Set(['schema_version', 'coordinate_state_counts', 'precision_counts', 'coordinate_gate_counts', 'interpretation']);
const QUARANTINE_KEYS = new Set(['rows', 'reasons']);
const RUN_KEYS = new Set(['status', 'publication_state', 'release_state', 'input_rows', 'normalized_rows', 'quarantined_rows', 'drift_alarms']);
const RELEASE_DIFF_KEYS = new Set(['schema_version', 'status', 'delta_version', 'publication_state', 'release_promoted', 'public_surfaces', 'geocoding', 'prior_eligible_release', 'disappearance_semantics', 'error_type', 'error', 'counts', 'previous', 'current', 'added', 'changed', 'not_observed', 'suppressed']);
const RELEASE_SUMMARY_KEYS = new Set(['checksum_sha256', 'schema_fingerprint', 'config_fingerprint', 'mapping_version', 'adapter_version', 'schema_version', 'input_rows', 'normalized_rows', 'quarantined_rows']);
const GRAPH_CANDIDATE_KEYS = new Set(['status', 'storage_state', 'review_state', 'publication_status']);
const GATE_KEYS = new Set(['release_state', 'publication_state', 'release_promoted', 'public_surfaces', 'geocoding']);
const PLATFORM_KEYS = new Set(['registered', 'country_code', 'coverage', 'attribution', 'readiness', 'owner_review', 'publication']);
const COVERAGE_KEYS = new Set(['completeness', 'disappearance_semantics', 'limitations']);
const ATTRIBUTION_KEYS = new Set(['source_origin', 'terms_status', 'attribution_required', 'notice']);
const READINESS_KEYS = new Set(['state', 'owner_review', 'private_candidate', 'public_release_allowed', 'reasons']);
const OWNER_REVIEW_KEYS = new Set(['state', 'decision_recorded', 'decision_id']);
const PUBLICATION_KEYS = new Set(['state', 'approval_required', 'reason']);
const CONTRACT_VERSION_KEYS = new Set(['country', 'readiness']);

function packetError(path) {
  throw new Error(`Review packet rejected safely at ${path}.`);
}

function assertObjectKeys(value, allowed, path) {
  if (!isRecord(value)) packetError(path);
  if (Object.keys(value).some((key) => !allowed.has(key))) packetError(path);
}

function assertScalar(value, path) {
  if (!(value === null || typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean')) packetError(path);
}

function assertStringList(value, path) {
  if (!Array.isArray(value) || value.some((item) => typeof item !== 'string')) packetError(path);
}

function assertAggregateMap(value, path, mode = 'scalar') {
  if (!isRecord(value)) packetError(path);
  for (const [key, child] of Object.entries(value)) {
    if (!/^[A-Za-z][A-Za-z0-9_.-]{0,79}$/.test(key)) packetError(`${path}.${key}`);
    if (mode === 'string-list') assertStringList(child, `${path}.${key}`);
    else if (mode === 'number') {
      if (!Number.isInteger(child) || child < 0) packetError(`${path}.${key}`);
    } else assertScalar(child, `${path}.${key}`);
  }
}

function validateMetricObject(value, path, allowed) {
  if (value === undefined || value === null) return;
  assertObjectKeys(value, allowed, path);
  for (const [key, child] of Object.entries(value)) {
    const childPath = `${path}.${key}`;
    if (['review_state_counts', 'field_presence', 'status_state_counts', 'coordinate_state_counts', 'precision_counts', 'coordinate_gate_counts'].includes(key)) assertAggregateMap(child, childPath, 'number');
    else if (key === 'schema_version' || key === 'source_row_unit' || key === 'identity_semantics' || key === 'disappearance_semantics' || key === 'interpretation') assertScalar(child, childPath);
    else if (typeof child !== 'number' || !Number.isFinite(child) || child < 0) packetError(childPath);
  }
}

function validateReviewPacketBranch(value, path = 'packet') {
  if (!isRecord(value)) packetError(path);
  assertObjectKeys(value, PACKET_TOP_KEYS, path);
  for (const [key, child] of Object.entries(value)) {
    const childPath = `${path}.${key}`;
    if (['schema_version', 'source_id', 'run_dir_digest', 'run_id', 'classification', 'publication_boundary'].includes(key)) assertScalar(child, childPath);
    else if (key === 'review_required' || key === 'release_promotion_allowed' || key === 'public_exposure') {
      if (typeof child !== 'boolean') packetError(childPath);
    } else if (key === 'reasons' || key === 'operator_actions') assertStringList(child, childPath);
    else if (key === 'provenance') {
      assertObjectKeys(child, PROVENANCE_KEYS, childPath);
      Object.entries(child).forEach(([nestedKey, nestedValue]) => nestedKey === 'redirects' ? assertStringList(nestedValue, `${childPath}.${nestedKey}`) : assertScalar(nestedValue, `${childPath}.${nestedKey}`));
    } else if (key === 'schema') {
      assertObjectKeys(child, SCHEMA_KEYS, childPath);
      Object.entries(child).forEach(([nestedKey, nestedValue]) => assertScalar(nestedValue, `${childPath}.${nestedKey}`));
    } else if (key === 'counts') {
      assertObjectKeys(child, COUNT_KEYS, childPath);
      Object.entries(child).forEach(([nestedKey, nestedValue]) => {
        if (nestedKey === 'reconciles' || nestedKey === 'qa_matches_manifest') {
          if (typeof nestedValue !== 'boolean') packetError(`${childPath}.${nestedKey}`);
        } else if (!Number.isInteger(nestedValue) || nestedValue < 0) packetError(`${childPath}.${nestedKey}`);
      });
    } else if (key === 'review_metrics') {
      assertObjectKeys(child, new Set(['schema_version', 'facility_observation', 'classification', 'geospatial']), childPath);
      assertScalar(child.schema_version, `${childPath}.schema_version`);
      validateMetricObject(child.facility_observation, `${childPath}.facility_observation`, METRIC_FACILITY_KEYS);
      validateMetricObject(child.classification, `${childPath}.classification`, METRIC_CLASSIFICATION_KEYS);
      validateMetricObject(child.geospatial, `${childPath}.geospatial`, METRIC_GEOSPATIAL_KEYS);
    } else if (key === 'facility_observation') validateMetricObject(child, childPath, METRIC_FACILITY_KEYS);
    else if (key === 'classification') validateMetricObject(child, childPath, METRIC_CLASSIFICATION_KEYS);
    else if (key === 'geospatial') validateMetricObject(child, childPath, METRIC_GEOSPATIAL_KEYS);
    else if (key === 'quarantine') {
      assertObjectKeys(child, QUARANTINE_KEYS, childPath);
      if (child.rows !== undefined && (!Number.isInteger(child.rows) || child.rows < 0)) packetError(`${childPath}.rows`);
      if (child.reasons !== undefined) assertAggregateMap(child.reasons, `${childPath}.reasons`, 'number');
    } else if (key === 'run') {
      assertObjectKeys(child, RUN_KEYS, childPath);
      for (const [nestedKey, nestedValue] of Object.entries(child)) {
        if (nestedKey === 'drift_alarms') assertStringList(nestedValue, `${childPath}.${nestedKey}`);
        else assertScalar(nestedValue, `${childPath}.${nestedKey}`);
      }
    } else if (key === 'release_diff') {
      assertObjectKeys(child, RELEASE_DIFF_KEYS, childPath);
      for (const [nestedKey, nestedValue] of Object.entries(child)) {
        if (nestedKey === 'counts') {
          assertObjectKeys(nestedValue, new Set(['added', 'changed', 'not_observed', 'suppressed']), `${childPath}.counts`);
          Object.values(nestedValue).forEach((count) => { if (count !== null && (!Number.isInteger(count) || count < 0)) packetError(`${childPath}.counts`); });
        } else if (nestedKey === 'public_surfaces') {
          assertObjectKeys(nestedValue, new Set(['api', 'map', 'export', 'cache', 'history']), `${childPath}.public_surfaces`);
          Object.values(nestedValue).forEach((flag) => { if (typeof flag !== 'boolean') packetError(`${childPath}.public_surfaces`); });
        } else if (nestedKey === 'previous' || nestedKey === 'current') {
          assertObjectKeys(nestedValue, RELEASE_SUMMARY_KEYS, `${childPath}.${nestedKey}`);
          Object.values(nestedValue).forEach((summaryValue) => assertScalar(summaryValue, `${childPath}.${nestedKey}`));
        } else if (nestedKey === 'release_promoted') {
          if (typeof nestedValue !== 'boolean') packetError(`${childPath}.${nestedKey}`);
        } else assertScalar(nestedValue, `${childPath}.${nestedKey}`);
      }
    } else if (key === 'graph_candidates') {
      assertObjectKeys(child, GRAPH_CANDIDATE_KEYS, childPath);
      Object.values(child).forEach((nestedValue) => assertScalar(nestedValue, childPath));
    } else if (key === 'gates') {
      assertObjectKeys(child, GATE_KEYS, childPath);
      Object.entries(child).forEach(([nestedKey, nestedValue]) => {
        if (nestedKey === 'public_surfaces') {
          assertObjectKeys(nestedValue, new Set(['api', 'map', 'export', 'cache', 'history']), `${childPath}.public_surfaces`);
          Object.values(nestedValue).forEach((flag) => { if (typeof flag !== 'boolean') packetError(`${childPath}.public_surfaces`); });
        } else if (nestedKey === 'release_promoted') {
          if (typeof nestedValue !== 'boolean') packetError(`${childPath}.${nestedKey}`);
        } else assertScalar(nestedValue, `${childPath}.${nestedKey}`);
      });
    } else if (key === 'platform') validatePlatformPacket(child, childPath);
    else if (key === 'blockers') assertAggregateMap(child, childPath, 'string-list');
    else if (key === 'prior_eligible_release') assertScalar(child, childPath);
  }
  return value;
}

function validatePlatformPacket(value, path) {
  assertObjectKeys(value, PLATFORM_KEYS, path);
  for (const [key, child] of Object.entries(value)) {
    const childPath = `${path}.${key}`;
    if (key === 'registered') {
      if (typeof child !== 'boolean') packetError(childPath);
    } else if (key === 'country_code') assertScalar(child, childPath);
    else if (key === 'coverage') {
      assertObjectKeys(child, COVERAGE_KEYS, childPath);
      if (child.limitations !== undefined) assertStringList(child.limitations, `${childPath}.limitations`);
      if (child.completeness !== undefined) assertScalar(child.completeness, `${childPath}.completeness`);
      if (child.disappearance_semantics !== undefined) assertScalar(child.disappearance_semantics, `${childPath}.disappearance_semantics`);
    } else if (key === 'attribution') {
      assertObjectKeys(child, ATTRIBUTION_KEYS, childPath);
      Object.values(child).forEach((nestedValue) => assertScalar(nestedValue, childPath));
    } else if (key === 'readiness') {
      assertObjectKeys(child, READINESS_KEYS, childPath);
      if (child.reasons !== undefined) assertStringList(child.reasons, `${childPath}.reasons`);
      Object.entries(child).forEach(([nestedKey, nestedValue]) => {
        if (nestedKey !== 'reasons' && !['state', 'owner_review'].includes(nestedKey) && typeof nestedValue !== 'boolean') assertScalar(nestedValue, `${childPath}.${nestedKey}`);
      });
    } else if (key === 'owner_review') {
      if (isRecord(child)) {
        assertObjectKeys(child, OWNER_REVIEW_KEYS, childPath);
        Object.values(child).forEach((nestedValue) => assertScalar(nestedValue, childPath));
      } else assertScalar(child, childPath);
    } else if (key === 'publication') {
      assertObjectKeys(child, PUBLICATION_KEYS, childPath);
      Object.values(child).forEach((nestedValue) => assertScalar(nestedValue, childPath));
    }
  }
}

export function validateReviewPacket(value, path = 'packet') {
  validateReviewPacketBranch(value, path);
  if (!/^private-review-packet-v[12]$/.test(String(value.schema_version || ''))) packetError(`${path}.schema_version`);
  return value;
}

export function validateReadinessPayload(value, path = 'readiness') {
  if (!isRecord(value)) packetError(path);
  const allowed = new Set(['schema_version', 'generated_at', 'contract_versions', 'source_of_truth', 'derived_context', 'country_count', 'source_count', 'readiness_counts', 'readiness_classes', 'states', 'classification_notes', 'countries', 'country_records', 'publication_boundary']);
  assertObjectKeys(value, allowed, path);
  if (value.schema_version !== 'private-review-console-v1' || value.derived_context !== true) packetError(path);
  if (value.generated_at !== undefined) assertScalar(value.generated_at, `${path}.generated_at`);
  if (value.contract_versions !== undefined) {
    assertObjectKeys(value.contract_versions, CONTRACT_VERSION_KEYS, `${path}.contract_versions`);
    Object.values(value.contract_versions).forEach((item) => assertScalar(item, `${path}.contract_versions`));
  }
  if (value.source_of_truth !== undefined) {
    assertObjectKeys(value.source_of_truth, new Set(['platform_registry', 'publication_boundary']), `${path}.source_of_truth`);
    Object.values(value.source_of_truth).forEach((item) => assertScalar(item, `${path}.source_of_truth`));
  }
  if (value.readiness_counts !== undefined) assertAggregateMap(value.readiness_counts, `${path}.readiness_counts`, 'number');
  if (value.classification_notes !== undefined) {
    assertObjectKeys(value.classification_notes, new Set(READINESS_STATES), `${path}.classification_notes`);
    Object.values(value.classification_notes).forEach((item) => { if (typeof item !== 'string') packetError(`${path}.classification_notes`); });
  }
  if (value.publication_boundary !== undefined) assertScalar(value.publication_boundary, `${path}.publication_boundary`);
  if (!Number.isInteger(value.country_count) || value.country_count < 1 || !Number.isInteger(value.source_count) || value.source_count < 1) packetError(path);
  if (!Array.isArray(value.readiness_classes) || value.readiness_classes.length !== READINESS_STATES.length || value.readiness_classes.some((item, index) => item !== READINESS_STATES[index])) packetError(`${path}.readiness_classes`);
  if (!Array.isArray(value.states) || value.states.join('|') !== READINESS_STATES.join('|')) packetError(`${path}.states`);
  if (!isRecord(value.countries) || Object.keys(value.countries).length !== value.country_count) packetError(`${path}.countries`);
  for (const [code, country] of Object.entries(value.countries)) {
    if (!/^[A-Z]{2}$/.test(code) || !isRecord(country)) packetError(`${path}.countries.${code}`);
    assertObjectKeys(country, new Set(['name', 'country_code', 'display_name', 'state', 'readiness_class', 'summary', 'basis', 'source_count', 'acquisition_counts', 'country_reasons', 'owner_review', 'publication_state', 'sources']), `${path}.countries.${code}`);
    if (typeof country.name !== 'string' || !READINESS_STATES.includes(country.state) || typeof country.summary !== 'string' || !Array.isArray(country.basis) || !Number.isInteger(country.source_count) || country.source_count < 1 || !Array.isArray(country.sources) || country.sources.length !== country.source_count) packetError(`${path}.countries.${code}`);
    if (country.acquisition_counts !== undefined) assertAggregateMap(country.acquisition_counts, `${path}.countries.${code}.acquisition_counts`, 'number');
    if (country.country_reasons !== undefined) assertStringList(country.country_reasons, `${path}.countries.${code}.country_reasons`);
    if (country.owner_review !== undefined) assertScalar(country.owner_review, `${path}.countries.${code}.owner_review`);
    if (country.publication_state !== undefined) assertScalar(country.publication_state, `${path}.countries.${code}.publication_state`);
    country.sources.forEach((source, index) => validateReadinessSource(source, `${path}.countries.${code}.sources[${index}]`, code));
  }
  if (!Array.isArray(value.country_records) || value.country_records.length !== value.country_count) packetError(`${path}.country_records`);
  value.country_records.forEach((record, index) => {
    const recordPath = `${path}.country_records[${index}]`;
    if (!isRecord(record)) packetError(recordPath);
    assertObjectKeys(record, new Set(['country_code', 'display_name', 'readiness_class', 'source_count', 'sources', 'owner_review', 'publication_state', 'basis', 'summary', 'acquisition_counts', 'country_reasons']), recordPath);
    if (typeof record.country_code !== 'string' || !READINESS_STATES.includes(record.readiness_class) || !Number.isInteger(record.source_count) || !Array.isArray(record.sources) || record.sources.length !== record.source_count) packetError(recordPath);
    record.sources.forEach((source, sourceIndex) => validateReadinessSource(source, `${recordPath}.sources[${sourceIndex}]`, record.country_code));
  });
  return value;
}

function validateReadinessSource(value, path, countryCode) {
  const allowed = new Set(['source_id', 'country_code', 'jurisdiction_scope', 'source_url', 'access_method', 'cadence', 'status', 'readiness', 'owner_review', 'publication', 'coverage', 'attribution']);
  assertObjectKeys(value, allowed, path);
  if (value.country_code !== countryCode || typeof value.source_id !== 'string' || typeof value.status !== 'object' || typeof value.attribution !== 'object' || typeof value.coverage !== 'object') packetError(path);
  assertObjectKeys(value.status, new Set(['metadata', 'acquisition', 'runtime_health', 'publication_eligibility', 'evidence', 'next_action']), `${path}.status`);
  if (value.status.evidence !== undefined) assertStringList(value.status.evidence, `${path}.status.evidence`);
  Object.entries(value.status).forEach(([key, child]) => { if (key !== 'evidence') assertScalar(child, `${path}.status.${key}`); });
  assertObjectKeys(value.readiness, READINESS_KEYS, `${path}.readiness`);
  if (value.readiness.reasons !== undefined) assertStringList(value.readiness.reasons, `${path}.readiness.reasons`);
  Object.entries(value.readiness).forEach(([key, child]) => { if (key !== 'reasons') assertScalar(child, `${path}.readiness.${key}`); });
  assertObjectKeys(value.owner_review, new Set(['state', 'decision_id', 'decision_recorded']), `${path}.owner_review`);
  Object.values(value.owner_review).forEach((child) => assertScalar(child, `${path}.owner_review`));
  assertObjectKeys(value.publication, new Set(['state', 'approval_required', 'reason']), `${path}.publication`);
  Object.values(value.publication).forEach((child) => assertScalar(child, `${path}.publication`));
  assertObjectKeys(value.coverage, COVERAGE_KEYS, `${path}.coverage`);
  if (value.coverage.limitations !== undefined) assertStringList(value.coverage.limitations, `${path}.coverage.limitations`);
  Object.entries(value.coverage).forEach(([key, child]) => { if (key !== 'limitations') assertScalar(child, `${path}.coverage.${key}`); });
  assertObjectKeys(value.attribution, ATTRIBUTION_KEYS, `${path}.attribution`);
  Object.values(value.attribution).forEach((child) => assertScalar(child, `${path}.attribution`));
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
  const provenance = packet.provenance || {};
  const schema = packet.schema || {};
  const gates = packet.gates || {};
  const platform = packet.platform || {};
  panel.innerHTML = `<div class="packet-heading"><div><p class="eyebrow">LOCAL ROW-FREE PACKET</p><h3>${escapeHtml(displayValue(packet.source_id, 'Source unavailable'))}</h3><p class="notice-small">${escapeHtml(displayValue(packet.publication_boundary, 'Packet is evidence only; no approval is implied.'))}</p></div><span class="badge badge-amber">inspection only</span></div><div class="packet-grid"><article class="packet-card"><h4>Counts / deltas</h4><ul class="packet-facts">${packetEntries({ input: counts.input_rows, normalized: counts.normalized_rows, quarantined: counts.quarantined_rows, reconciles: counts.reconciles, added: diffCounts.added, changed: diffCounts.changed, not_observed: diffCounts.not_observed })}</ul></article><article class="packet-card"><h4>Quarantine reasons</h4><ul class="packet-facts">${packetEntries(packet.quarantine?.reasons)}</ul></article><article class="packet-card"><h4>Coordinate / privacy gates</h4><ul class="packet-facts">${packetEntries(geospatial.coordinate_gate_counts || geospatial.precision_counts)}</ul></article><article class="packet-card"><h4>Provenance / schema</h4><ul class="packet-facts">${packetEntries({ retrieved: provenance.retrieved_at_utc, effective: provenance.effective_date, sha256: provenance.sha256 || provenance.checksum_sha256, bytes: provenance.byte_size, adapter: schema.adapter_version, schema: schema.schema_version, fingerprint: schema.schema_fingerprint, schema_status: schema.schema_status })}</ul></article><article class="packet-card"><h4>Release gates</h4><ul class="packet-facts">${packetEntries({ release: gates.release_state, publication: gates.publication_state, promoted: gates.release_promoted, geocoding: gates.geocoding, public_surfaces: gates.public_surfaces })}</ul></article><article class="packet-card"><h4>Platform / attribution</h4><ul class="packet-facts">${packetEntries({ owner_review: platform.owner_review?.state || platform.owner_review, terms: platform.attribution?.terms_status, source_origin: platform.attribution?.source_origin, coverage: platform.coverage?.completeness })}</ul></article><article class="packet-card"><h4>Publication blockers</h4><ul class="packet-facts">${packetEntries(packet.blockers)}</ul></article></div>`;
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
    validateReadinessPayload(payload);
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
