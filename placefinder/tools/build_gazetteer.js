// Builds data/places.json (gazetteer) and data/world.json (basemap TopoJSON)
// Sources: Natural Earth (public domain) + GeoNames cities >= 15,000 people via all-the-cities (CC BY 4.0)
const fs = require('fs');
const path = require('path');
const NM = '/home/claude/build/node/node_modules/';
const d3 = require(NM + 'd3-geo');
const cities = require(NM + 'all-the-cities');
const wl = require(NM + 'wordlist-english');
const topo = require(NM + 'topojson-server');
const simp = require(NM + 'topojson-simplify');

const NE = '/home/claude/build/ne/';
const OUT = process.argv[2] || '/home/claude/build/app/data';
fs.mkdirSync(OUT, { recursive: true });
const rd = f => JSON.parse(fs.readFileSync(NE + f + '.geojson'));

const COMMON = new Set([].concat(wl['english/10'], wl['english/20'], wl['english/35']));
const r4 = x => Math.round(x * 1e4) / 1e4;
const tc = s => s && s === s.toUpperCase() ? s.toLowerCase().replace(/(^|[\s\-'(])(\p{L})/gu, (m, a, b) => a + b.toUpperCase()).replace(/\bOf\b/g, 'of').replace(/\bThe\b/g, 'the').replace(/\bAnd\b/g, 'and') : s;

// type codes
const T = { country: 0, state: 1, city: 2, continent: 3, ocean: 4, sea: 5, river: 6, lake: 7, mountain: 8, island: 9, region: 10, worldregion: 11 };
const TYPES = ['Country', 'State / province', 'City / town', 'Continent', 'Ocean', 'Sea / bay / strait', 'River', 'Lake', 'Mountain / range', 'Island', 'Physical region', 'World region'];

const places = []; // [name, type, lon, lat, cc, within, score, flags, alts]
// flags: 1 = abbreviation (exact upper-case only), 2 = common English word (caution), 4 = capital city
function add(name, type, lon, lat, cc, within, score, flags = 0, alts = []) {
  if (!name || !isFinite(lon) || !isFinite(lat)) return -1;
  name = name.replace(/\s+/g, ' ').trim();
  alts = [...new Set(alts.filter(a => a && a !== name).map(a => a.replace(/\s+/g, ' ').trim()))];
  const single = !/\s/.test(name);
  if (single && type !== T.country && type !== T.continent && type !== T.ocean && COMMON.has(name.toLowerCase())) flags |= 2;
  places.push([name, type, r4(lon), r4(lat), cc || '', within || '', Math.round(score * 10) / 10, flags, alts]);
  return places.length - 1;
}

// ---------- Countries ----------
const countries = rd('ne_50m_admin_0_countries');
const ccName = {}, ccCont = {};
const countryIdx = {};
for (const f of countries.features) {
  const p = f.properties;
  const cc = p.ISO_A2_EH !== '-99' ? p.ISO_A2_EH : (p.ISO_A2 !== '-99' ? p.ISO_A2 : p.ADM0_A3);
  if (/\./.test(p.NAME)) p.NAME = p.NAME_LONG && !/\./.test(p.NAME_LONG) ? p.NAME_LONG : p.ADMIN;
  const home = p.HOMEPART === 1 && (p.TYPE !== 'Dependency' || !ccName[cc]);
  if (home || !ccName[cc]) { ccName[cc] = p.NAME; ccCont[cc] = p.CONTINENT; }
  const alts = [p.NAME_LONG, p.ADMIN, p.BRK_NAME, p.FORMAL_EN, p.NAME_EN, p.GEOUNIT, p.SUBUNIT].filter(a => a && !/^-99$/.test(a));
  const score = (p.TYPE === 'Dependency' || p.TYPE === 'Lease') ? 85 : 100;
  const ci = add(p.NAME, T.country, p.LABEL_X, p.LABEL_Y, cc, p.CONTINENT, score + (p.POP_RANK || 0) / 4, 0, alts);
  if (home || countryIdx[cc] === undefined) countryIdx[cc] = ci;
}
// extra constituent countries / common names
const extraCountries = [
  ['England', -1.6, 52.6, 'GB', 'United Kingdom'],
  ['Scotland', -4.2, 56.8, 'GB', 'United Kingdom'],
  ['Wales', -3.7, 52.3, 'GB', 'United Kingdom'],
  ['Northern Ireland', -6.7, 54.6, 'GB', 'United Kingdom'],
];
for (const [n, x, y, cc, w] of extraCountries) add(n, T.country, x, y, cc, w, 99);
// aliases that point to existing countries: [alias, cc, abbreviation?]
const countryAliases = [
  ['United States', 'US'], ['United States of America', 'US'], ['America', 'US'], ['USA', 'US', 1], ['U.S.A.', 'US', 1], ['U.S.', 'US', 1], ['US', 'US', 1], ['U.S', 'US', 1],
  ['United Kingdom', 'GB'], ['UK', 'GB', 1], ['U.K.', 'GB', 1], ['Britain', 'GB'], ['Great Britain', 'GB'],
  ['Holland', 'NL'], ['The Netherlands', 'NL'], ['Burma', 'MM'], ['Ivory Coast', 'CI'], ["Côte d'Ivoire", 'CI'], ["Cote d'Ivoire", 'CI'],
  ['Czech Republic', 'CZ'], ['Czechia', 'CZ'], ['Swaziland', 'SZ'], ['Eswatini', 'SZ'], ['Macedonia', 'MK'], ['North Macedonia', 'MK'],
  ['East Timor', 'TL'], ['Timor-Leste', 'TL'], ['DRC', 'CD', 1], ['DR Congo', 'CD'], ['Democratic Republic of Congo', 'CD'], ['Democratic Republic of the Congo', 'CD'],
  ['Republic of the Congo', 'CG'], ['Congo-Brazzaville', 'CG'], ['Congo-Kinshasa', 'CD'], ['Türkiye', 'TR'], ['Turkiye', 'TR'],
  ['UAE', 'AE', 1], ['U.A.E.', 'AE', 1], ['Emirates', 'AE'], ['South Korea', 'KR'], ['Republic of Korea', 'KR'], ['North Korea', 'KP'],
  ['Russian Federation', 'RU'], ['Vatican', 'VA'], ['Vatican City', 'VA'], ['Cape Verde', 'CV'], ['Cabo Verde', 'CV'], ['Laos', 'LA'],
  ['Viet Nam', 'VN'], ['Bosnia', 'BA'], ['Bosnia-Herzegovina', 'BA'], ['Trinidad', 'TT'], ['PNG', 'PG', 1], ['Persia', 'IR'],
  ['Ceylon', 'LK'], ['Siam', 'TH'], ['Zaire', 'CD'], ['Rhodesia', 'ZW'], ['Kampuchea', 'KH'], ['NZ', 'NZ', 1], ['Aotearoa', 'NZ'],
  ['PRC', 'CN', 1], ["People's Republic of China", 'CN'], ['Mainland China', 'CN'], ['Republic of Ireland', 'IE'], ['Eire', 'IE'], ['Éire', 'IE'],
];
const aliasExtra = []; // [alias, idx, flags]
for (const [a, cc, ab] of countryAliases) if (countryIdx[cc] >= 0) aliasExtra.push([a, countryIdx[cc], ab ? 1 : 0]);

// ---------- Admin-1 (states / provinces) ----------
const admin1 = rd('ne_10m_admin_1_states_provinces');
const a1ByGn = {};
for (const f of admin1.features) {
  const p = f.properties;
  if (!p.name) continue;
  const cc = p.iso_a2 !== '-99' ? p.iso_a2 : p.adm0_a3;
  const alts = (p.name_alt || '').split('|').concat([p.woe_name, p.gns_name, p.name_en]).filter(Boolean);
  if (p.gn_a1_code) (a1ByGn[p.gn_a1_code] = a1ByGn[p.gn_a1_code] || []).push(p.name);
  // US / CA / AU postal abbreviations e.g. "TX" only when preceded by a comma — handled in app; store as abbreviation alias
  if (['US', 'CA', 'AU'].includes(cc) && p.postal && p.postal.length === 2) alts.push('§' + p.postal);
  const score = 70 - (p.scalerank || 5) * 1.5 + (['US', 'CA', 'AU', 'IN', 'CN', 'BR', 'MX'].includes(cc) ? 4 : 0);
  add(p.name, T.state, p.longitude, p.latitude, cc, ccName[cc] || p.admin, score, 0, alts);
}
// GB admin1 "within" names for GeoNames cities
const gbA1 = { ENG: 'England', SCT: 'Scotland', WLS: 'Wales', NIR: 'Northern Ireland' };
function a1Name(cc, code) {
  if (cc === 'GB') return gbA1[code] || '';
  const l = a1ByGn[cc + '.' + code];
  return l && l.length === 1 ? l[0] : '';
}

// ---------- Cities ----------
const ne = rd('ne_10m_populated_places');
const neGeo = new Set();
for (const f of ne.features) {
  const p = f.properties;
  if (p.GEONAMESID > 0) neGeo.add(p.GEONAMESID);
  const pop = Math.max(p.POP_MAX || 0, 1000);
  let score = 10 * Math.log10(pop);
  let flags = 0;
  if (p.ADM0CAP === 1 || /^Admin-0 capital/.test(p.FEATURECLA)) { score += 15; flags |= 4; }
  else if (/Admin-1 capital/.test(p.FEATURECLA)) score += 4;
  const cc = p.ISO_A2 !== '-99' ? p.ISO_A2 : p.ADM0_A3;
  const within = [p.ADM1NAME, ccName[cc] || p.ADM0NAME].filter(Boolean).join(', ');
  const alts = [p.NAMEASCII, p.MEGANAME, p.LS_NAME].concat((p.NAMEALT || '').split('|')).filter(Boolean);
  add(p.NAME, T.city, p.LONGITUDE, p.LATITUDE, cc, within, score, flags, alts);
}
let gnCount = 0;
for (const c of cities) {
  if (c.population < 15000 || neGeo.has(c.cityId)) continue;
  if (!/^PPL/.test(c.featureCode)) continue;
  const [lon, lat] = c.loc.coordinates;
  let score = 10 * Math.log10(c.population);
  if (c.featureCode === 'PPLA') score += 3;
  const within = [a1Name(c.country, c.adminCode), ccName[c.country] || c.country].filter(Boolean).join(', ');
  const alts = (c.altName || '').split(',').filter(Boolean);
  add(c.name, T.city, lon, lat, c.country, within, score, 0, alts);
  gnCount++;
}
// city aliases
const cityAliasTargets = [['New York', 'US', ['NYC', 'New York City', 'NY City']], ['Washington, D.C.', 'US', ['Washington DC', 'Washington D.C.', 'D.C.']], ['Los Angeles', 'US', ['L.A.']],
  ['Mumbai', 'IN', ['Bombay']], ['Kolkata', 'IN', ['Calcutta']], ['Chennai', 'IN', ['Madras']], ['Beijing', 'CN', ['Peking']], ['Yangon', 'MM', ['Rangoon']], ['Ho Chi Minh City', 'VN', ['Saigon']],
  ['Kyiv', 'UA', ['Kiev']], ['Istanbul', 'TR', ['Constantinople', 'Byzantium']], ['Xian', 'CN', ["Xi'an", 'Xi’an']], ['St. Petersburg', 'RU', ['Saint Petersburg', 'Leningrad']], ['Mexico City', 'MX', []]];
for (const [n, cc, al] of cityAliasTargets) {
  const i = places.findIndex(p => p[1] === T.city && p[4] === cc && (p[0] === n || p[8].includes(n)));
  if (i >= 0) for (const a of al) aliasExtra.push([a, i, /^[A-Z.]+$/.test(a) ? 1 : 0]);
  else console.warn('city alias target missing', n);
}

// ---------- Physical ----------
const regions = rd('ne_10m_geography_regions_polys');
const classMap = { 'Continent': T.continent, 'Island': T.island, 'Island group': T.island, 'Range/mtn': T.mountain, 'Lake': T.lake };
for (const f of regions.features) {
  const p = f.properties;
  if (p.FEATURECLA === 'Dragons-be-here' || !p.NAME) continue;
  const [lon, lat] = d3.geoCentroid(f);
  const t = classMap[p.FEATURECLA] ?? T.region;
  let name = tc(p.NAME);
  const malts = [];
  if (t === T.mountain) {
    if (/\bMts\.?$/.test(name)) { malts.push(name); name = name.replace(/\bMts\.?$/, 'Mountains'); }
    const b = name.replace(/ Mountains$/, '');
    if (/s$/.test(b) && !/ /.test(b)) malts.push(b.slice(0, -1) + ' Mountains', b + ' Mountains', b.slice(0, -1) + ' Range');
    if (/ Mountains$/.test(name)) malts.push(b + ' Range', b + ' Mts', b + ' Mts.');
  }
  const score = t === T.continent ? 98 : 62 - (p.SCALERANK || 5) * 2;
  add(name, t, lon, lat, '', [p.SUBREGION, p.REGION].filter(Boolean).join(', '), score, 0, [tc(p.NAMEALT), tc(p.LABEL), ...malts].filter(Boolean));
}
for (const [n, ...al] of [['Oceania'], ['Antarctica']]) if (!places.some(p => p[0] === n)) add(n, T.continent, n === 'Oceania' ? 150 : 0, n === 'Oceania' ? -20 : -82, '', '', 97);
const rpts = rd('ne_10m_geography_regions_points');
for (const f of rpts.features) {
  const p = f.properties; if (!p.name) continue;
  const t = /island/.test(p.featurecla) ? T.island : T.region;
  add(p.name, t, p.long_x, p.lat_y, '', [p.subregion, p.region].filter(Boolean).join(', '), 55 - (p.scalerank || 5) * 2);
}
const elev = rd('ne_10m_geography_regions_elevation_points');
for (const f of elev.features) {
  const p = f.properties; if (!p.name || p.featurecla === 'spot elevation') continue;
  const alts = [];
  const m = p.name.match(/^(Mt\.?|Mount|Mont|Monte)\s+(.+)$/);
  if (m) { alts.push('Mount ' + m[2], 'Mt. ' + m[2], 'Mt ' + m[2]); }
  add(p.name, T.mountain, p.long_x, p.lat_y, '', [p.subregion, p.region].filter(Boolean).join(', '), 58 - (p.scalerank || 5) * 2 + (p.elevation || 0) / 1000, 0, alts);
}
const marine = rd('ne_10m_geography_marine_polys');
for (const f of marine.features) {
  const p = f.properties; if (!p.name) continue;
  const t = p.featurecla === 'ocean' ? T.ocean : (p.featurecla === 'river' ? T.river : T.sea);
  const [lon, lat] = d3.geoCentroid(f);
  const score = t === T.ocean ? 95 : 72 - (p.scalerank || 5) * 2;
  add(tc(p.name), t, lon, lat, '', '', score, 0, [tc(p.namealt)].filter(Boolean));
}
// commonly used world and national regions not in Natural Earth (approximate centre points)
const REGIONS = [
  ['Middle East', 44, 29, ['Near East']], ['Central Asia', 66, 43, []], ['Southeast Asia', 110, 8, ['South-East Asia', 'South East Asia']], ['South Asia', 78, 22, []], ['East Asia', 118, 35, []],
  ['West Africa', -3, 11, []], ['East Africa', 37, 0, []], ['North Africa', 10, 28, []], ['Southern Africa', 25, -25, []], ['Sub-Saharan Africa', 20, 0, []], ['Horn of Africa', 45, 8, []],
  ['Latin America', -65, -10, []], ['Central America', -86, 14, []], ['Scandinavia', 15, 63, []], ['Balkans', 21, 43, ['the Balkans']], ['Caribbean', -72, 18, ['the Caribbean']],
  ['Sahel', 5, 15, ['the Sahel']], ['Siberia', 100, 62, []], ['Patagonia', -69, -46, []], ['Mesopotamia', 44, 33, []], ['Levant', 36, 33, ['the Levant']], ['Arctic', 0, 82, ['the Arctic']],
  ['Midwest', -92, 42, ['the Midwest']], ['Great Plains', -101, 41, []], ['New England', -71.5, 43.5, []], ['Pacific Northwest', -122, 46, []], ['Deep South', -87, 32.5, []],
  ['Gobi Desert', 105, 43, ['Gobi']], ['Lake District', -3.1, 54.5, ['the Lake District']], ['Cotswolds', -1.85, 51.85, ['the Cotswolds', 'Cotswold Hills']], ['Scottish Highlands', -4.8, 57.2, ['Highlands of Scotland']],
  ['Peak District', -1.8, 53.3, ['the Peak District']], ['Yosemite Valley', -119.6, 37.73, ['Yosemite']], ['Grand Canyon', -112.1, 36.1, []], ['Amazon Rainforest', -62, -4, ['Amazon rainforest', 'Amazon Basin']],
];
for (const [n, x, y, al] of REGIONS) { if (!places.some(p => p[0] === n)) add(n, n.match(/Desert|District|Cotswolds|Highlands|Valley|Canyon|Rainforest/) ? T.region : T.worldregion, x, y, '', '', 75, 0, al); }
add('Atlantic Ocean', T.ocean, -35, 15, '', '', 96, 0, ['Atlantic', 'the Atlantic']);
add('Pacific Ocean', T.ocean, -160, 5, '', '', 96, 0, ['Pacific', 'the Pacific']);
add('Mediterranean Sea', T.sea, 18, 35, '', '', 85, 0, ['Mediterranean', 'the Mediterranean']);

const lakes = rd('ne_10m_lakes');
for (const f of lakes.features) {
  const p = f.properties; if (!p.name || p.featurecla === 'Reservoir' && p.scalerank > 6) continue;
  const [lon, lat] = d3.geoCentroid(f);
  const alts = [];
  const m = p.name.match(/^Lake (.+)$/); if (m) alts.push('Lake ' + m[1]);
  const m2 = p.name.match(/^(Lago|Lac) (de |du )?(.+)$/); if (m2) alts.push('Lake ' + m2[3]);
  add(p.name, T.lake, lon, lat, '', p.admin || '', 66 - (p.scalerank || 5) * 2, 0, alts);
}

// Rivers: group segments by name, pick a representative point
const rivers = rd('ne_10m_rivers_lake_centerlines');
const rgroups = {};
for (const f of rivers.features) {
  const p = f.properties; if (!p.name || p.featurecla !== 'River') continue;
  const name = p.name.replace(/\s+/g, ' ');
  const g = rgroups[name] = rgroups[name] || { rank: 99, coords: [] };
  g.rank = Math.min(g.rank, p.scalerank);
  const lines = f.geometry.type === 'LineString' ? [f.geometry.coordinates] : f.geometry.coordinates;
  for (const l of lines) if (l.length > g.coords.length) g.coords = l;
}
const riverAliases = { 'Amazonas': ['Amazon'], 'Chang Jiang': ['Yangtze'], 'Huang': ['Huang He', 'Yellow River', 'Huang Ho'], 'Ganges': ['Ganga'], 'Dnipro': ['Dnieper'], 'Rhein': [], 'Rhine': ['Rhein', 'Rhin'], 'Danube': ['Donau', 'Duna'], 'Ayeyarwady': ['Irrawaddy'], 'Al Furat': [], 'Euphrates': ['Firat'], 'Tigris': ['Dicle'], 'Yenisey': ['Yenisei'], 'Sénégal': ['Senegal'], 'São Francisco': ['Sao Francisco'], 'St. Lawrence': ['Saint Lawrence'], 'Rio Grande': ['Río Grande'] };
const skipRivers = new Set(['Yangtze', 'Al Furat', 'Rhein', 'Rhin', 'Donau', 'Firat', 'Dicle', 'Dnepre']);
const riverPlaces = [];
for (const [name, g] of Object.entries(rgroups)) {
  if (skipRivers.has(name) || !g.coords.length) continue;
  const c = g.coords[Math.floor(g.coords.length / 2)];
  const al = riverAliases[name] || [];
  const DISPLAY = { 'Amazonas': 'Amazon', 'Chang Jiang': 'Yangtze', 'Huang': 'Yellow', 'Ayeyarwady': 'Irrawaddy', 'Dnipro': 'Dnieper' };
  const disp = DISPLAY[name] || name;
  const forms = [];
  for (const n of [name, disp, ...al]) forms.push(n + ' River', 'River ' + n, 'the ' + n + ' River', 'Rio ' + n, 'Río ' + n);
  const i = add(disp.match(/River/i) ? disp : disp + ' River', T.river, c[0], c[1], '', '', 66 - g.rank * 2.5, 0, forms);
  riverPlaces.push([i, [...new Set([name, disp, ...al])]]);
}

// ---------- Well-known volcanoes, mountains and sites (hand-checked coordinates) ----------
const RENAME = { 'Vesuvio': ['Mount Vesuvius', ['Vesuvius', 'Mt Vesuvius', 'Vesuvio']], 'Monte Etna': ['Mount Etna', ['Etna', 'Mt Etna']], 'Krakatau': ['Krakatoa', ['Krakatau']], 'Volcán Popocatépetl': ['Popocatépetl', ['Popocatepetl']] };
for (const p of places) if (p[1] === T.mountain && RENAME[p[0]]) { const [n, al] = RENAME[p[0]]; p[8].push(p[0], ...al); p[0] = n; p[6] = Math.max(p[6], 62); }
const MANUAL = [
  ['Mount St. Helens', T.mountain, -122.194, 46.191, 'US', 'Washington, United States of America', 66, ['Mount Saint Helens', 'Mt. St. Helens', 'Mt St Helens']],
  ['Mount Fuji', T.mountain, 138.727, 35.361, 'JP', 'Japan', 66, ['Fujiyama', 'Fuji-san', 'Mt Fuji']],
  ['Eyjafjallajökull', T.mountain, -19.62, 63.63, 'IS', 'Iceland', 64, ['Eyjafjallajokull']],
  ['Kīlauea', T.mountain, -155.287, 19.421, 'US', 'Hawaii, United States of America', 64, ['Kilauea']],
  ['Mauna Loa', T.mountain, -155.608, 19.475, 'US', 'Hawaii, United States of America', 64, []],
  ['Denali', T.mountain, -151.007, 63.069, 'US', 'Alaska, United States of America', 64, ['Mount McKinley', 'Mt McKinley']],
  ['Stromboli', T.mountain, 15.213, 38.789, 'IT', 'Italy', 62, []],
  ['Mount Tambora', T.mountain, 118.0, -8.25, 'ID', 'Indonesia', 62, ['Tambora']],
  ['Hekla', T.mountain, -19.70, 63.98, 'IS', 'Iceland', 62, []],
  ['Mount Pelée', T.mountain, -61.17, 14.81, 'MQ', 'Martinique', 62, ['Mount Pelee', 'Montagne Pelée']],
  ['Mount Nyiragongo', T.mountain, 29.25, -1.52, 'CD', 'Democratic Republic of the Congo', 62, ['Nyiragongo']],
  ['Mount Merapi', T.mountain, 110.446, -7.54, 'ID', 'Indonesia', 62, ['Merapi']],
  ['Cotopaxi', T.mountain, -78.44, -0.68, 'EC', 'Ecuador', 60, []],
  ['Soufrière Hills', T.mountain, -62.18, 16.72, 'MS', 'Montserrat', 60, ['Soufriere Hills']],
  ['Matterhorn', T.mountain, 7.658, 45.976, 'CH', 'Switzerland', 62, []],
  ['Aconcagua', T.mountain, -70.011, -32.653, 'AR', 'Argentina', 62, []],
  ['Yellowstone', T.region, -110.59, 44.43, 'US', 'Wyoming, United States of America', 66, ['Yellowstone National Park', 'Yellowstone Caldera']],
  ['Pompeii', T.city, 14.485, 40.749, 'IT', 'Campania, Italy', 58, ['Pompei']],
  ['Herculaneum', T.city, 14.348, 40.806, 'IT', 'Campania, Italy', 55, ['Ercolano']],
  ['Mid-Atlantic Ridge', T.region, -29, 10, '', 'Atlantic Ocean', 64, []],
  ['San Andreas Fault', T.region, -119.6, 35.1, 'US', 'California, United States of America', 64, []],
  ['Great Rift Valley', T.region, 36.5, 0.5, '', 'East Africa', 64, ['East African Rift', 'Rift Valley']],
];
for (const [n, t, x, y, cc, w, sc, al] of MANUAL) add(n, t, x, y, cc, w, sc, 0, al);

// ---------- Keys / collisions ----------
const norm = s => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
  .replace(/[’`]/g, "'").replace(/\./g, '').replace(/[-–—]/g, ' ')
  .replace(/\b(saint|ste?)\b/g, 'st').replace(/\b(mount|mt)\b/g, 'mt').replace(/\bfort\b|\bft\b/g, 'fort')
  .replace(/^the /, '').replace(/\s+/g, ' ').trim();
const keyList = {};
places.forEach((p, i) => { for (const n of [p[0], ...p[8]]) { const k = norm(n.replace(/^§/, '')); (keyList[k] = keyList[k] || []).push(i); } });
// admin-1 units named after a town (e.g. Reading, Bristol): prefer the town unless it is a major federal state
const federal = new Set(['US', 'CA', 'AU', 'IN', 'BR', 'MX', 'CN', 'RU', 'DE', 'NG', 'AR', 'MY', 'PK', 'ZA']);
for (const list of Object.values(keyList)) {
  const states = list.filter(j => places[j][1] === T.state && !federal.has(places[j][4]));
  for (const j of states) {
    const towns = list.filter(c => places[c][1] === T.city && places[c][4] === places[j][4]);
    if (towns.length) places[j][6] = Math.min(places[j][6], Math.max(...towns.map(c => places[c][6])) - 5);
  }
}
// bare river names only when unambiguous and not a common English word
const FAMOUS = new Set(['Nile', 'Amazon', 'Thames', 'Danube', 'Rhine', 'Seine', 'Volga', 'Mekong', 'Ganges', 'Indus', 'Yangtze', 'Zambezi', 'Limpopo', 'Tigris', 'Euphrates', 'Orinoco', 'Severn', 'Loire', 'Rhone', 'Rhône', 'Elbe', 'Brahmaputra', 'Irrawaddy', 'Murray', 'Yukon', 'Mackenzie', 'Tiber']);
for (const [i, names] of riverPlaces) {
  if (names.some(n => FAMOUS.has(n))) { places[i][6] = Math.max(places[i][6], 80); for (const n of names) if (FAMOUS.has(n)) places[i][8].push(n); continue; }
  for (const n of names) {
    const k = norm(n);
    if (COMMON.has(k) || n.length <= 3 || places[i][6] <= 45) continue;
    const clash = keyList[k] || [];
    if (clash.every(j => places[j][1] === T.city && places[j][6] < places[i][6])) { places[i][8].push(n); }
  }
}
// extra aliases go into alts with flag markers (abbreviations start with '§')
for (const [a, i, ab] of aliasExtra) places[i][8].push(ab ? '§' + a : a);

// Words never treated as places on their own
const NEVER = ['Of', 'Central', 'North', 'South', 'East', 'West', 'Northern', 'Southern', 'Eastern', 'Western', 'Capital', 'Centre', 'Center', 'Coast', 'Lakes', 'Upper', 'Lower', 'Island', 'Islands', 'Hope', 'Unity', 'Liberty', 'Independence', 'Union', 'Progress', 'Paradise', 'Victory', 'Concord', 'Industry', 'Commerce', 'Enterprise', 'Opportunity', 'Mobile', 'Nice', 'Split', 'March', 'May', 'August', 'Of', 'Most', 'Best', 'Bar', 'Male', 'Bad', 'Gap', 'Mission', 'Pace', 'Police', 'Sale', 'Deal', 'Battle', 'Normal', 'Federal', 'Republic', 'Metropolitan', 'Interior', 'Highlands', 'Plateau', 'Coastal', 'Littoral', 'Distrito', 'National', 'Delta', 'Valley', 'Mountain', 'Hill', 'Hills', 'Port', 'Bay', 'Sound', 'Rock', 'Rocky', 'Long', 'Grand', 'Great', 'Pleasant'];

const out = {
  version: '1.0',
  built: new Date().toISOString().slice(0, 10),
  sources: 'Natural Earth (public domain); GeoNames cities with 15,000+ people via all-the-cities 3.1.0 (CC BY 4.0)',
  types: TYPES,
  common: [...new Set([].concat(wl['english/10'], wl['english/20']).map(w => w.toLowerCase()))].filter(w => /^[a-z]+$/.test(w)),
  never: [...new Set(NEVER)],
  fields: ['name', 'type', 'lon', 'lat', 'cc', 'within', 'score', 'flags', 'alts'],
  places,
};
fs.writeFileSync(path.join(OUT, 'places.json'), JSON.stringify(out));
console.log('places', places.length, 'geonames-only cities', gnCount, 'bytes', fs.statSync(path.join(OUT, 'places.json')).size);

// ---------- Basemap ----------
const world = { type: 'FeatureCollection', features: countries.features.map(f => ({ type: 'Feature', properties: { cc: f.properties.ISO_A2_EH !== '-99' ? f.properties.ISO_A2_EH : f.properties.ADM0_A3, n: f.properties.NAME }, geometry: f.geometry })) };
const lines = rd('ne_50m_admin_1_states_provinces_lines');
const a1l = { type: 'FeatureCollection', features: lines.features.map(f => ({ type: 'Feature', properties: {}, geometry: f.geometry })) };
let t = topo.topology({ countries: world, a1: a1l }, 1e5);
t = simp.presimplify(t);
t = simp.simplify(t, simp.quantile(t, 0.8));
t = simp.filter(t, simp.filterWeight(t, simp.quantile(t, 0.2)));
t = require(NM + 'topojson-client').quantize(t, 1e4);
fs.writeFileSync(path.join(OUT, 'world.json'), JSON.stringify(t));
console.log('world bytes', fs.statSync(path.join(OUT, 'world.json')).size);
