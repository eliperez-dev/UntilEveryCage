import { SecureCommunityError, secureSecret, secureUuid, type SecureStatus } from '../../../api/SecureCommunityRepository';

export const RECOVERY_FILE_LIMIT = 256 * 1024;
export function isSecureAccessFailure(error: unknown): error is SecureCommunityError {
  return error instanceof SecureCommunityError && [401, 403, 404].includes(error.status ?? 0);
}
export async function readRecoveryFile(file: File): Promise<string> {
  if (!file.size || file.size > RECOVERY_FILE_LIMIT) throw new Error('Choose a recovery file smaller than 256 KB.');
  const value = await file.text();
  if (!value.trim() || new TextEncoder().encode(value).byteLength > RECOVERY_FILE_LIMIT) throw new Error('This recovery file could not be read.');
  return value;
}
export function requestRecoveryDownload(armor: string, caseId?: string): void {
  const url = URL.createObjectURL(new Blob([armor], { type: 'text/plain;charset=utf-8' }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = caseId && secureUuid(caseId) ? `uec-inbox-${caseId}.asc` : 'uec-reviewer-key.asc';
  anchor.hidden = true;
  try { document.body.appendChild(anchor); anchor.click(); }
  finally { anchor.remove(); window.setTimeout(() => URL.revokeObjectURL(url), 1000); }
}
export function readSecureRoute(hash: string): { caseId: string; accessSecret: string } | null {
  if (hash.split('?')[0] !== '#/secure-inbox') return null;
  const params = new URLSearchParams(hash.split('?')[1] ?? '');
  const caseId = params.get('case_id') ?? '', accessSecret = params.get('access_secret') ?? '';
  return secureUuid(caseId) && (!accessSecret || secureSecret(accessSecret)) ? { caseId, accessSecret } : null;
}
export const secureStatusLabels: Record<SecureStatus, string> = {
  received: 'Received', in_review: 'In review', needs_information: 'More information needed', closed: 'Closed', removed: 'Removed from inbox',
};
export function displaySecureDate(value: string): string {
  const date = new Date(value);
  return Number.isFinite(date.getTime()) ? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(date) : '';
}
