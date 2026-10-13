// TEST_ONLY: public enrichment reaches analysis and coverage without score changes.
const fs=require('fs'),assert=require('assert'),{JSDOM,VirtualConsole}=require('jsdom');
const html=fs.readFileSync(require('path').join(__dirname,'../backend/static/index.html'),'utf8');
const vc=new VirtualConsole(),errors=[];vc.on('jsdomError',e=>{if(!/canvas|scrollTo/.test(e.message))errors.push(e.message)});
const player={playerId:'TEST_ONLY_PLAYER',player:'TEST_ONLY_RECEIVER',pos:'WR',nfl:'BUF',slot:'Starter',currentProjection:12,projectionWeek:6,ppg3:8,usageScore:80,draftOverall:45,age:24,draftYear:2023,draftRound:2,draftSource:'NFL • TEST_ONLY',snapShare:.85,usageFacts:{throughWeek:5,games:[{week:5,targets:0,carries:null,receptions:0}]},qbContext:{qb1:'TEST_ONLY_QUARTERBACK',status:'UNAVAILABLE'}};
const league={id:'TEST_ONLY_L',name:'TEST_ONLY_LEAGUE',team:'TEST_ONLY_TEAM',platform:'Sleeper',loaded:true,sourceAnalysisWeek:6,analysisWeek:6,projectionWeek:6,roster:[player],_allRosters:[{...player,_team:'TEST_ONLY_TEAM'}],waivers:[],standings:[],weekly:[],summary:{},user:{},enrichmentCoverage:{eligible:1,usage:1,snaps:1,draft:1,qbEligible:1,qbContext:1}};
const payload={ok:true,schema:'fcc-data-v8',userId:'TEST_ONLY',dataVersion:'TEST_ONLY_V1',data:{season:2026,leagues:[league],meta:{sourceAnalysisWeek:6},online:{news:[],nflWeeks:[]}}};
const dom=new JSDOM(html,{url:'https://appassets.androidplatform.net/assets/fcc/index.html',runScripts:'dangerously',pretendToBeVisual:true,virtualConsole:vc,beforeParse(w){w.TextEncoder=TextEncoder;w.TextDecoder=TextDecoder;w.scrollTo=()=>{};w.matchMedia=()=>({matches:false,addEventListener(){},addListener(){}});w.AndroidSync={getAccountSession:()=>JSON.stringify({ok:true,user:{uid:'TEST_ONLY',emailVerified:true}}),getCachedBackendShadow:()=>JSON.stringify(payload),getSavedUiState:()=>'',getNotificationEvents:()=> '[]',accountRequest(){}};}});
try{
 const w=dom.window;w.eval("state.league='TEST_ONLY_L';renderAll()");
 const analysis=w.eval('rosterAnalysis(getLeague())[0]');
 assert(analysis.reason.includes('uso/volume forte'));
 assert(analysis.reason.includes('TEST_ONLY_QUARTERBACK'));
 assert.equal(w.eval('getLeague().roster[0].currentProjection'),12);
 const coverage=w.document.getElementById('dataQualityGrid').textContent;
 for(const label of ['Uso recente','Snaps','Draft','Contexto do QB'])assert(coverage.includes(label));
 assert(coverage.includes('1/1'));
 w.fccOpenPlayer('TEST_ONLY_RECEIVER');const detail=w.document.getElementById('playerModalBody').textContent;assert(detail.includes('85,0%'));assert(detail.includes('Draft NFL 2023'));assert(detail.includes('TEST_ONLY_QUARTERBACK'));assert(detail.includes('0,0 targets/jogo'));assert(!detail.includes('corridas/jogo'));
 const original=w.eval('DATA');w.FCCAccount.apply({...payload,generatedAt:'TEST_ONLY_LATER'});assert.equal(w.eval('DATA'),original);
 assert.equal(errors.length,0,errors.join('\n'));
 console.log('PASS: observed volume, QB availability, per-player coverage and unchanged-data reuse. TEST_ONLY fixtures.');
}finally{dom.window.close();}
