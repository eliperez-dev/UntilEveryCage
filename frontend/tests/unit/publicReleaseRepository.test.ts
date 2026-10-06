import {describe,it,expect,vi} from 'vitest';
import {PublicReleaseRepository} from '../../src/api/PublicReleaseRepository';
const envelope = (profile='official') => ({api_version:'v2',data:{release_id:'synthetic-release',profile,manifest:{},manifest_sha256:'a'.repeat(64),suppression_generation:1}});
const response=(body:unknown,status=200)=>new Response(JSON.stringify(body),{status});
describe('public download availability',()=>{
 it('validates a data release without requiring a map artifact and returns only its safe identity',async()=>{
  const fetcher=vi.fn().mockResolvedValue(response(envelope()));
  expect(await new PublicReleaseRepository(fetcher).current('official')).toEqual({releaseId:'synthetic-release'});
  expect(fetcher).toHaveBeenCalledWith('/api/v2/releases/manifest?profile=official',expect.objectContaining({method:'GET',cache:'no-store',credentials:'omit'}));
 });
 it('distinguishes a missing release from service failure and malformed or mismatched manifests',async()=>{
  expect(await new PublicReleaseRepository(vi.fn().mockResolvedValue(response({},404))).current('official')).toBeNull();
  for(const result of [response({},503),response(envelope('community')),response({api_version:'v2',data:{release_id:'unvalidated'}})]) await expect(new PublicReleaseRepository(vi.fn().mockResolvedValue(result)).current('official')).rejects.toThrow('Release availability could not be checked. Try again.');
 });
});
