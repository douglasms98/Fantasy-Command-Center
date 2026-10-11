// TEST_ONLY fixtures exercise calculation reuse, refresh races and provenance.
const fs=require('fs'),assert=require('assert'),{JSDOM,VirtualConsole}=require('jsdom');
const html=fs.readFileSync(require('path').join(__dirname,'../backend/static/index.html'),'utf8');
const user={uid:'TEST_ONLY_PERF',email:'perf@example.invalid',emailVerified:true,googleLinked:true};
const roster=Array.from({length:12},(_,i)=>({playerId:'TEST_ONLY_'+i,player:'TEST_ONLY_'+i,pos:['QB','RB','WR','TE'][i%4],nfl:'BUF',slot:i<8?'Starter':'Bench',currentProjection:8+i,projectionWeek:6,ppg3:8+i,historicalScores:{'5':8+i}}));
const league={id:'TEST_ONLY_L',platform:'Sleeper',team:'TEST_ONLY_TEAM',name:'TEST_ONLY',loaded:true,sourceAnalysisWeek:6,analysisWeek:6,projectionWeek:6,
 roster,waivers:Array.from({length:240},(_,i)=>({playerId:'TEST_ONLY_W_'+i,player:'TEST_ONLY_W_'+i,pos:['QB','RB','WR','TE'][i%4],nfl:'NYJ',slot:'Bench',currentProjection:i%20,projectionWeek:6,ppg3:i%20,available:true})),
 weekly:[],standings:[],summary:{openActive:0},user:{},_allRosters:roster.map(p=>({...p,_team:'TEST_ONLY_TEAM'}))};
const calendar=[6,7,8].map(week=>({week,complete:true,games:[{home:'BUF',away:'NYJ',startTime:'2030-10-20T18:00:00Z'}]}));
function payload(version='TEST_ONLY_1'){return {ok:true,schema:'fcc-data-v8',userId:user.uid,dataVersion:version,generatedAt:new Date().toISOString(),registrations:[{id:league.id,platform:'Sleeper',name:league.name,team:league.team,status:'ready'}],sources:[{status:'ready',updatedAt:new Date().toISOString()}],data:{season:2026,leagues:[structuredClone(league)],meta:{sourceAnalysisWeek:6},online:{nflWeeks:calendar,nflScheduleUpdatedAt:new Date().toISOString(),news:[]}}};}
const errors=[],vc=new VirtualConsole();vc.on('jsdomError',e=>{if(!/canvas|scrollTo/.test(e.message))errors.push(e.message)});
const dom=new JSDOM(html,{url:'https://appassets.androidplatform.net/assets/fcc/index.html',runScripts:'dangerously',pretendToBeVisual:true,virtualConsole:vc,beforeParse(w){
 w.TextDecoder=TextDecoder;w.TextEncoder=TextEncoder;w.scrollTo=()=>{};w.matchMedia=()=>({matches:false,addEventListener(){},addListener(){}});
 w.AndroidSync={getAccountSession:()=>JSON.stringify({ok:true,user}),getCachedBackendShadow:()=>JSON.stringify(payload()),getSavedUiState:()=>'',getNotificationEvents:()=> '[]',accountRequest(){}};
}});
(async()=>{
 const w=dom.window;let counts={roster:0,waivers:0};
 const rosterCalc=w.fccCalculateRosterAnalysis,waiverCalc=w.fccCalculateWaiverQualityRows;
 w.fccCalculateRosterAnalysis=function(...args){counts.roster++;return rosterCalc(...args);};
 w.fccCalculateWaiverQualityRows=function(...args){counts.waivers++;return waiverCalc(...args);};
 w.eval("state.league='TEST_ONLY_L';renderAll()");
 assert.equal(counts.roster,1,'The complete roster is evaluated once for 240 waiver candidates');
 assert.equal(counts.waivers,1,'Home and waivers reuse their quality scores during a render');
 const cached=w.eval('fccCalculationPass(()=>fccWaiverPlan(getLeague(),waiverQualityRows(getLeague())))');
 const uncached=w.eval('fccWaiverPlan(getLeague(),waiverQualityRows(getLeague()))');
 assert.equal(JSON.stringify(cached.ranked),JSON.stringify(uncached.ranked),'Recommendations and ordering stay identical');
 const before=w.eval('rosterAnalysis(getLeague())[0].proj');
 w.eval('getLeague().roster.forEach(p=>p.currentProjection=50);renderAll()');
 assert(w.eval('rosterAnalysis(getLeague()).every(p=>p.proj===50)'),'A new render invalidates all projection calculations');
 assert.notEqual(before,50);
 const full=w.fccPlayerProjectionDisplay({currentProjection:0,projectionWeek:6,sleeperPublishedProjection:0,sleeperPublishedScoring:'PPR padrão'},league,6);
 assert(full.includes('0,00')&&full.includes('Sleeper (PPR padrão)'));
 const partial=w.fccPlayerProjectionDisplay({projectionEstimate:12,projectionWeek:6,projectionMissingStats:['TEST_ONLY_RULE']},league,6);
 assert(partial.includes('PARCIAL')&&partial.includes('12,00'));
 assert.equal(w.fccCurrentProjection({projectionEstimate:12,projectionWeek:6},league),null,'A partial forecast is not used as a complete optimizer input');
 assert(Number.isFinite(w.fccMatchupProbability({myProjectionEstimate:12,myProjection:null,myProjectionCoverage:{known:1,total:1},myScore:5,oppProjection:20,oppScore:10})),'A complete roster with partial rules can produce an explicitly labeled estimate');
 assert.equal(w.fccMatchupProbability({myScore:5,oppScore:10,oppProjection:20}),null,'A score is never used as a missing final forecast');
 const dataBefore=w.eval('DATA');w.FCCAccount.apply(payload());assert.equal(w.eval('DATA'),dataBefore,'An unchanged revision does not repeat trade calculations');
 w.FCCAccount.apply(payload('TEST_ONLY_2'));assert.notEqual(w.eval('DATA'),dataBefore);
 let release,calls=[];const gate=new Promise(r=>release=r);
 w.FCCAccount.request=async(method,path)=>{calls.push(path);if(path==='/v2/app-payload'){await gate;return payload('TEST_ONLY_3');}throw new Error('Unexpected redundant request: '+path);};
 const flights=[w.FCCAccount.refresh(false),w.FCCAccount.refresh(false),w.FCCAccount.refresh(false)];
 release();await Promise.all(flights);
 assert.deepEqual(calls,['/v2/app-payload'],'Concurrent refreshes, registrations and the fresh calendar require one read');
 assert.equal(w.FCCAccount.leagueCount,1);
 assert.equal(errors.length,0,errors.join('\n'));dom.window.close();
 console.log('PASS: linear roster calculations, unchanged recommendation ordering, fresh projection invalidation, complete/partial Sleeper distinction, snapshot reuse and one coalesced API read. TEST_ONLY fixtures.');
})().catch(e=>{console.error(e);dom.window.close();process.exit(1)});
