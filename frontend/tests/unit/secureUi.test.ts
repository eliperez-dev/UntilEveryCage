import { describe, expect, it } from 'vitest';
import { isSecureAccessFailure, readRecoveryFile, readSecureRoute, RECOVERY_FILE_LIMIT } from '../../src/app/contributions/secure/secureUi';
import { SecureCommunityError } from '../../src/api/SecureCommunityRepository';
const id='18c6ef3a-28cd-4c8e-a9bb-3951f45f210d',secret='a'.repeat(64);
describe('local secure UI boundaries',()=>{
  it('distinguishes revoked access from retryable delivery failures',()=>{
    for(const status of [401,403,404])expect(isSecureAccessFailure(new SecureCommunityError('Synthetic safe error',status))).toBe(true);
    for(const status of [409,429,503])expect(isSecureAccessFailure(new SecureCommunityError('Synthetic safe error',status))).toBe(false);
    expect(isSecureAccessFailure(new Error('Synthetic failure'))).toBe(false);
  });
  it('reads credentials only from the exact inbox router fragment',()=>{
    expect(readSecureRoute(`#/secure-inbox?case_id=${id}&access_secret=${secret}`)).toEqual({caseId:id,accessSecret:secret});
    expect(readSecureRoute(`#/secure-inbox?case_id=${id}`)).toEqual({caseId:id,accessSecret:''});
    for(const value of [`?case_id=${id}&access_secret=${secret}`,`#/secure-inbox-other?case_id=${id}&access_secret=${secret}`,`#/secure-inbox?case_id=invalid&access_secret=${secret}`,`#/secure-inbox?case_id=${id}&access_secret=invalid`])expect(readSecureRoute(value)).toBeNull();
  });
  it('bounds recovery file reads and rejects empty or oversized contents',async()=>{
    await expect(readRecoveryFile({size:20,text:async()=>'synthetic encrypted armor'} as File)).resolves.toBe('synthetic encrypted armor');
    await expect(readRecoveryFile({size:0} as File)).rejects.toThrow();
    await expect(readRecoveryFile({size:RECOVERY_FILE_LIMIT+1,text:async()=>{throw new Error('Must not read');}} as unknown as File)).rejects.toThrow('256 KB');
    await expect(readRecoveryFile({size:20,text:async()=>''} as File)).rejects.toThrow();
    await expect(readRecoveryFile({size:20,text:async()=>'a'.repeat(RECOVERY_FILE_LIMIT+1)} as File)).rejects.toThrow();
  });
});
