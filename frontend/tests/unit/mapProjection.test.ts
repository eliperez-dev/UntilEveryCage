import{describe,expect,it}from'vitest';import{locations}from'../../src/fixtures/locations';import{clusterFeatures,projectLocations}from'../../src/map/mapProjection';
describe('map projection',()=>{
  it('excludes unmapped fixtures',()=>expect(projectLocations(locations)).toHaveLength(2));
  it('clusters only the current release-filtered page and preserves member IDs',()=>{
    const features=projectLocations([{...locations[0],id:'one',lat:55,lon:10},{...locations[1],id:'two',lat:55.1,lon:10.1}]);
    const display=clusterFeatures(features);
    expect(display).toHaveLength(1);
    expect(display[0]).toMatchObject({count:2,memberIds:['one','two']});
  });
  it('keeps distant records as individual display points',()=>{
    const features=projectLocations([{...locations[0],id:'one',lat:55,lon:10},{...locations[1],id:'two',lat:56,lon:12}]);
    expect(clusterFeatures(features)).toHaveLength(2);
  });
});
