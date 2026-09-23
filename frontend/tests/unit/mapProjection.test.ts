import{describe,expect,it}from'vitest';import{locations}from'../../src/fixtures/locations';import type{Location}from'../../src/domain/location';import{clusterFeatures,projectLocations}from'../../src/map/mapProjection';
describe('map projection',()=>{
  it('excludes unmapped fixtures',()=>expect(projectLocations(locations)).toHaveLength(2));
  it('preserves exact and city precision while keeping unmapped records out of spatial results',()=>{
    const record=(id:string,precision:'exact'|'city'|'unmapped',lat:number|null,lon:number|null):Location=>({
      ...locations[0]!,id,lat,lon,
      evidence:{displayPrecision:precision} as NonNullable<Location['evidence']>,
    });
    expect(projectLocations([record('exact','exact',55,10),record('coarse','city',56,11),record('unknown','unmapped',null,null)]))
      .toEqual([
        expect.objectContaining({id:'exact',precision:'exact',lat:55,lon:10}),
        expect.objectContaining({id:'coarse',precision:'city',lat:56,lon:11}),
      ]);
  });
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
