import type { LabRecord, Precision } from './contract';

// Fixed, invented locations only. This broad review corpus never leaves the design lab.
const places = [
  ['Denmark','Aarhus',56.1629,10.2039],['France','Lyon',45.764,4.8357],['Italy','Parma',44.8015,10.3279],['United States','Des Moines',41.5868,-93.625],['Australia','Geelong',-38.1499,144.3617],['Germany','Oldenburg',53.1435,8.2146],
  ['Brazil','Curitiba',-25.4284,-49.2733],['Canada','Saskatoon',52.1332,-106.67],['Mexico','Merida',20.9674,-89.5926],['Argentina','Rosario',-32.9442,-60.6505],['Chile','Temuco',-38.7359,-72.5904],['Peru','Arequipa',-16.409,-71.5375],
  ['South Africa','Bloemfontein',-29.0852,26.1596],['Kenya','Nakuru',-0.3031,36.08],['Nigeria','Ibadan',7.3775,3.947],['Morocco','Meknes',33.8935,-5.5473],['Egypt','Mansoura',31.0409,31.3785],['Ghana','Kumasi',6.6885,-1.6244],
  ['India','Pune',18.5204,73.8567],['Japan','Sendai',38.2682,140.8694],['South Korea','Daegu',35.8714,128.6014],['Indonesia','Bandung',-6.9175,107.6191],['Thailand','Khon Kaen',16.4419,102.8359],['Vietnam','Can Tho',10.0452,105.7469],
  ['Philippines','Iloilo',10.7202,122.5621],['China','Chengdu',30.5728,104.0668],['Mongolia','Darkhan',49.4867,105.9228],['Kazakhstan','Karaganda',49.806,73.085],['Turkey','Konya',37.8746,32.4932],['Poland','Poznan',52.4064,16.9252],
  ['Spain','Zaragoza',41.6488,-0.8891],['Romania','Cluj-Napoca',46.7712,23.6236],['Ukraine','Lviv',49.8397,24.0297],['New Zealand','Hamilton',-37.787,175.2793],['Fiji','Nadi',-17.7765,177.435],['Iceland','Akureyri',65.6885,-18.1262],
] as const;
const categories = ['Poultry','Pig','Dairy','Processing','Laboratory','Aquaculture'] as const;
const precisions: readonly Precision[] = ['exact','city','coarse','unmapped'];
export const LAB_SENTINEL = 'F1A_SYNTHETIC_REVIEW_ONLY';

const aarhusCluster: readonly LabRecord[] = Object.freeze((['exact','city','coarse','exact'] as const).map((precision,index) => Object.freeze({ id:`syn-${String(index + 1).padStart(3,'0')}`, name:`Synthetic ${categories[index]!} record ${String(index + 1).padStart(2,'0')}`, category:categories[index]!, country:'Denmark', locality:'Aarhus', precision, latitude:56.1629 + index * .012, longitude:10.2039 + index * .012 })));
const worldwide: readonly LabRecord[] = Array.from({length:356},(_,offset) => { const index=offset+4; const place=places[offset%places.length]!; const precision=precisions[(index+Math.floor(index/6))%precisions.length]!; const spread=((offset*17)%23-11)*.0025; return Object.freeze({ id:`syn-${String(index+1).padStart(3,'0')}`, name:`Review ${categories[index%categories.length]!} record ${String(index+1).padStart(2,'0')}`, category:categories[index%categories.length]!, country:place[0], locality:place[1], precision, latitude:precision==='unmapped'?null:place[2]+spread, longitude:precision==='unmapped'?null:place[3]+spread*1.35 }); });
// Deterministic, on-land density fixture for exercising the worker cluster tree. These
// are invented records; coordinates are offsets around named cities, not random points.
const v1Cities = [
  ['United States','Kansas City',39.0997,-94.5786],['United States','Des Moines',41.5868,-93.625],['United States','Fresno',36.7378,-119.7871],['United States','Omaha',41.2565,-95.9345],
  ['Canada','Saskatoon',52.1332,-106.67],['Canada','Guelph',43.5448,-80.2482],['Canada','Red Deer',52.2681,-113.8112],
  ['Mexico','Merida',20.9674,-89.5926],['Mexico','Guadalajara',20.6597,-103.3496],['Mexico','Monterrey',25.6866,-100.3161],['Mexico','Puebla',19.0414,-98.2063],
  ['United Kingdom','Leeds',53.8008,-1.5491],['United Kingdom','Bristol',51.4545,-2.5879],['United Kingdom','Norwich',52.6309,1.2974],
  ['France','Lyon',45.764,4.8357],['France','Rennes',48.1173,-1.6778],['France','Toulouse',43.6047,1.4442],
  ['Germany','Oldenburg',53.1435,8.2146],['Germany','Munster',51.9607,7.6261],['Germany','Leipzig',51.3397,12.3731],['Germany','Regensburg',49.0134,12.1016],
  ['Denmark','Aarhus',56.1629,10.2039],['Denmark','Odense',55.4038,10.4024],['Denmark','Aalborg',57.0488,9.9217],
  ['Spain','Zaragoza',41.6488,-0.8891],['Spain','Murcia',37.9922,-1.1307],['Spain','Valladolid',41.6523,-4.7245],
  ['New Zealand','Hamilton',-37.787,175.2793],['New Zealand','Palmerston North',-40.3564,175.6111],['New Zealand','Christchurch',-43.5321,172.6362]
] as const;
const denseLocations: readonly LabRecord[] = Object.freeze(v1Cities.flatMap(([country, locality, latitude, longitude], cityIndex) => {
  const exactCount = 36 + (cityIndex % 5) * 14;
  const aggregateCount = 18 + (cityIndex % 6) * 17;
  const exact = Array.from({ length: exactCount }, (_, index) => {
    const angle = (index * 137.508 + cityIndex * 31) * Math.PI / 180;
    const radius = .012 + (index % 9) * .007;
    return Object.freeze({ id: `dense-exact-${cityIndex}-${index}`, name: `Synthetic ${categories[index % categories.length]} facility ${cityIndex + 1}-${index + 1}`, category: categories[(index + cityIndex) % categories.length]!, country, locality, precision: 'exact' as const, latitude: latitude + Math.sin(angle) * radius, longitude: longitude + Math.cos(angle) * radius * 1.28 });
  });
  const aggregate = Array.from({ length: aggregateCount }, (_, index) => {
    const precision: 'city' | 'coarse' = index % 2 ? 'city' : 'coarse';
    // City and coarse groups are separate approved-style representative points. They
    // still join their nearby exact sites at broad zoom, but split into legible nodes.
    const latitudeOffset = precision === 'city' ? .018 : -.055;
    const longitudeOffset = precision === 'city' ? .022 : -.072;
    return Object.freeze({ id: `dense-area-${cityIndex}-${index}`, name: `Synthetic ${precision} area record ${cityIndex + 1}-${index + 1}`, category: categories[(index + cityIndex + 2) % categories.length]!, country, locality, precision, latitude: latitude + latitudeOffset, longitude: longitude + longitudeOffset });
  });
  return [...exact, ...aggregate];
}));
export const labRecords: readonly LabRecord[] = Object.freeze([...aarhusCluster, ...worldwide, ...denseLocations]);
