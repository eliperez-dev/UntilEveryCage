import { describe, expect, it } from 'vitest';
import { parseRecordReference } from '../../src/app/recordReference';
const id = '27d7ef4b-39de-4d9f-bacc-4062f560321e';
describe('recordReference', () => {
  it('accepts IDs and current or legacy public record links without fetching', () => {
    for (const reference of [id, `#/records/${id}`, `https://example.test/v2-preview/#/locations/${id}?map=context`, `https://example.test/records/${id}`]) expect(parseRecordReference(reference)).toBe(id);
  });
  it('rejects malformed IDs, unsupported links, and credential-bearing URLs', () => {
    for (const reference of ['not-a-record', 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx', `javascript:/records/${id}`, `https://user:pass@example.test/records/${id}`, `https://example.test/api/private/${id}`, '']) expect(parseRecordReference(reference)).toBe('');
  });
});
