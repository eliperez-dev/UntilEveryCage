const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
/** Extract a public record reference locally; never fetch the pasted URL. */
export function parseRecordReference(value: string): string {
  const trimmed = value.trim();
  if (uuid.test(trimmed)) return trimmed;
  try {
    const url = new URL(trimmed, 'https://record-reference.invalid');
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) return '';
    const path = url.hash.startsWith('#/') ? url.hash.slice(1).split('?')[0] : url.pathname;
    const id = path?.match(/^\/(?:records|locations)\/([^/]+)$/)?.[1];
    return id && uuid.test(id) ? id : '';
  } catch { return ''; }
}
