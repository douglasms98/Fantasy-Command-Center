const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=require('path');
const html=fs.readFileSync(path.join(__dirname,'../app/src/main/assets/fcc/index.html'),'utf8');
function fn(name){const start=html.indexOf('function '+name+'(');assert(start>=0,name);const end=html.indexOf('\nfunction ',start+10);return html.slice(start,end<0?undefined:end);}
const ctx={console,Date,Map,Set,JSON,Number,String,Object,Array,DATA:{meta:{analysisWeek:6,sourceAnalysisWeek:6},leagues:[]},state:{week:'ALL',waiverSort:'w4'},loaded:[],
 fccClampWeek:w=>Math.max(1,Math.min(18,Number(w)||1)),fccMaybeNum:v=>v==null||v===''?null:(Number.isFinite(Number(v))?Number(v):null),fccNum:v=>Number(v)||0,
 fccKey:(id,name)=>id||name,fccNameKey:n=>n,fccPlayerOnBye:()=>false,fccAnalysisWeek:()=>6,
 fccBuildAction:()=>({title:'TEST_ONLY'}),document:{querySelector:()=>null}};
vm.createContext(ctx);
for(const name of ['fccProjectionFromRow','fccCurrentProjection','fccPlayerHistory','fccInferLeagueAnalysisWeek','fccLeagueConfirmedWeek','fccPlayerRecentValues','fccNormalizeTemporalLeague','fccNormalizeTemporalData','fccApplyBackendOverlay'])vm.runInContext(fn(name),ctx);
assert.equal(ctx.fccProjectionFromRow({'Proj W4':12},6),null);
assert.equal(ctx.fccProjectionFromRow({'Proj W6':0},6),0,'A real zero projection remains zero');
assert.equal(ctx.fccProjectionFromRow({Projection:12,Week:4},6),null);
assert.equal(ctx.fccProjectionFromRow({Projection:12,Week:6},6),12);
assert.equal(ctx.fccProjectionFromRow({Projection:12},6),null,'Untagged projection is not assigned to a new week');
assert.equal(ctx.fccCurrentProjection({currentProjection:12,projectionWeek:4}),null);
assert.equal(ctx.fccCurrentProjection({currentProjection:12,projectionWeek:6}),12);
assert.equal(ctx.fccCurrentProjection({currentProjection:12}),null);
assert.equal(ctx.fccInferLeagueAnalysisWeek({currentWeek:7},{}),7);
assert.equal(ctx.fccInferLeagueAnalysisWeek({data:{weekData:[{Week:8}]}},{}),8);
assert.equal(ctx.fccLeagueConfirmedWeek({weekly:[{week:4,result:'W'},{week:5,confirmed:true},{week:6,preliminary:true}]}),5);
const rows=new Map([['TEST_ONLY',[{Week:3,Points:99},{Week:4,Points:0},{Week:5,Points:17},{Week:6,Points:80}]]]);
const hist=ctx.fccPlayerHistory(rows,'TEST_ONLY','',6);assert.equal(hist.lastWeekPoints,17);assert.equal(hist.lastPlayedWeek,5);
assert(!hist.recentWeeks.includes(6));assert.equal(hist.historicalScores['4'],0);
const league={loaded:true,analysisWeek:6,sourceAnalysisWeek:6,projectionWeek:4,poscomp:[{delta:99}],roster:[{player:'TEST_ONLY',projW4:12,w1:3,w2:0,w3:5}],waivers:[]};
ctx.fccNormalizeTemporalLeague(league);assert.equal(league.roster[0].projectionWeek,4);assert.equal(league.roster[0].lastPlayedWeek,3);assert.equal(league.roster[0].lastWeekPoints,5);assert.equal(league.poscomp.length,0);
assert.equal(ctx.fccCurrentProjection(league.roster[0],league),null);
assert.deepEqual(Array.from(ctx.fccPlayerRecentValues(league.roster[0])),[3,0,5]);
ctx.fccNormalizeTemporalData({leagues:[league]});assert.equal(ctx.state.waiverSort,'current');
// Actual overlay path advances source metadata without re-tagging cached projections.
ctx.DATA.leagues=[Object.assign(league,{id:'TEST_ONLY',analysisWeek:4,sourceAnalysisWeek:4})];
for(const n of ['fccApplyProviderOwnership','fccApplyProviderStandings','fccApplyProviderRosterMembership','fccRefreshWeekFilter'])ctx[n]=()=>{};
ctx.fccApplyBackendOverlay({normalizedLeagues:[{id:'TEST_ONLY',analysisWeek:6,platform:'TEST_ONLY'}]});
assert.equal(league.sourceAnalysisWeek,6);assert.equal(league.roster[0].projectionWeek,4);
assert.equal(ctx.fccCurrentProjection(league.roster[0],league),null);
console.log('PASS: W4→W6 provenance, zero/null values, W5 history, confirmation bounds, source week inference, API overlay and legacy sort migration. TEST_ONLY fixtures.');
