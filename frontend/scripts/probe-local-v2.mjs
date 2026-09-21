const base=process.argv[2]??'http://127.0.0.1:8000';
try {
  const list=await fetch(`${base}/api/v2/locations?profile=official&limit=1`);
  if(!list.ok)throw new Error(`list probe failed: ${list.status}`);
  const body=await list.json();
  if(body.api_version!=='v2'||!body.meta)throw new Error('list contract probe failed');
  console.log(`list probe passed: release=${body.meta.release_id}`);
  if(Array.isArray(body.data)&&body.data[0]?.facility_id){
    const id=encodeURIComponent(body.data[0].facility_id);
    const detail=await fetch(`${base}/api/v2/locations/${id}?profile=official`);
    if(!detail.ok)throw new Error(`detail probe failed: ${detail.status}`);
    const detailBody=await detail.json();
    if(detailBody.api_version!=='v2'||!detailBody.data)throw new Error('detail contract probe failed');
    console.log('detail probe passed');
  }else console.log('detail probe skipped: no public promoted record');
} catch (error) {
  const unreachable=error?.cause?.code==='ECONNREFUSED'||error?.message==='fetch failed';
  console.error(`Local V2 probe failed: ${unreachable?'backend is not reachable; run the local-v2 start command first':error instanceof Error?error.message:'unknown probe error'}`);
  process.exitCode=1;
}
