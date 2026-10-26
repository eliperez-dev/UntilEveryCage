/** This experiment is intentionally excluded from production builds. */
export const SECURE_INBOX_LOCAL = import.meta.env.DEV && import.meta.env.VITE_SECURE_INBOX_EXPERIMENT === 'true';
export function configuredReviewerFingerprint(): string {
  const value = import.meta.env.VITE_SECURE_REVIEWER_FINGERPRINT?.trim() ?? '';
  if (!/^(?:[0-9a-f]{40}|[0-9a-f]{64})$/.test(value)) throw new Error('The reviewer fingerprint is not configured.');
  return value;
}
