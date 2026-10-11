// TEST_ONLY fixtures: shared games, persistent decisions, transaction actors,
// same matchup behavior across providers and safe contextual headlines.
const fs=require('fs'),assert=require('assert'),{JSDOM,VirtualConsole}=require('jsdom');
const html=fs.readFileSync(require('path').join(__dirname,'../backend/static/index.html'),'utf8');
const user={uid:'TEST_ONLY_RELIABLE',email:'test@example.invalid',emailVerified:true,googleLinked:true};
const old=[{week:1,at:'2026-10-11T00:00:00Z',moves:[]},{week:1,at:'2026-09-01T00:00:00Z',moves:['TEST_ONLY real W1 decision']}];
const errors=[],vc=new VirtualConsole();vc.on('jsdomError',e=>{if(!/canvas|scrollTo/.test(e.message))errors.push(e.message)});
const dom=new JSDOM(html,{url:'https://appassets.androidplatform.net/assets/fcc/index.html',runScripts:'dangerously',pretendToBeVisual:true,virtualConsole:vc,beforeParse(w){
 w.TextDecoder=TextDecoder;w.TextEncoder=TextEncoder;w.scrollTo=()=>{};w.matchMedia=()=>({matches:false,addEventListener(){},addListener(){}});
 w.localStorage.setItem('fcc-user-'+user.uid+'-fcc_decisions_v59',JSON.stringify(old));
 w.AndroidSync={getAccountSession:()=>JSON.stringify({ok:true,user}),getCachedBackendShadow:()=>'',getSavedUiState:()=>'',getNotificationEvents:()=> '[]',accountRequest(){}};
}});
const w=dom.window;
function league(id,platform){return {id,platform,team:'TEST_ONLY_'+id,name:'TEST_ONLY_LEAGUE_'+id,loaded:true,sourceAnalysisWeek:5,analysisWeek:5,
 roster:[{player:'TEST_ONLY_BYE',slot:'Starter',pos:'WR',nfl:'BUF',currentProjection:10,projectionWeek:5},{player:'TEST_ONLY_GAME',slot:'Starter',pos:'RB',nfl:id==='A'?'NYJ':'MIA',currentProjection:12,projectionWeek:5}],waivers:[],weekly:[],standings:[],user:{},summary:{},
 matchup:{week:5,myScore:12,oppScore:0,myProjectionEstimate:100,oppProjectionEstimate:120,myProjectionCoverage:{known:2,total:2},oppProjectionCoverage:{known:2,total:2}},
 transactions:[{id:'TEST_ONLY_OLD',at:'2026-10-09T00:00:00Z',Action:'DROP',Player:'TEST_ONLY_OLD_PLAYER',User:'TEST_ONLY_OWNER'},
 {id:'TEST_ONLY_NEW',at:id==='A'?'2026-10-11T12:00:00Z':'2026-10-11T13:00:00Z',Action:'ADD',Player:'TEST_ONLY_NEW_PLAYER',Team:'TEST_ONLY_ACTOR_'+id,'Waiver Bid':0}]};}
try{
 assert.equal(w.fccDecisionHistory().length,1,'Empty W1 loading records are removed');
 assert.equal(w.fccDecisionHistory()[0].week,1,'Genuine W1 decisions are preserved');
 w.fccRecordDecisionSnapshot();assert.equal(w.fccDecisionHistory().length,1,'Authenticated empty loading state does not log W1');
 const leagues=[league('A','ESPN'),league('B','Sleeper')],weeks=[5,6,7].map(week=>({week,complete:true,games:[
  {id:'TEST_ONLY_GAME',home:'MIA',away:'NYJ',startTime:'2030-10-20T18:00:00Z'},
  {id:'TEST_ONLY_DUPLICATE',home:'NYJ',away:'MIA',startTime:'2030-10-20T18:00:00Z'},
  {home:'JAX',away:'PHI',international:true,venue:'TEST_ONLY_VENUE',startTime:'2030-10-20T13:30:00Z'}]}));
 const payload={ok:true,schema:'fcc-data-v8',userId:user.uid,dataVersion:'TEST_ONLY_V1',data:{season:2026,leagues,meta:{sourceAnalysisWeek:5},online:{news:[],nflWeeks:weeks}}};
 w.FCCAccount.apply(payload);
 const planner=w.document.querySelector('#threeWeekPlanner');assert.equal(planner.querySelectorAll('.planner-row-v605').length,3);
 for(const row of planner.querySelectorAll('.planner-row-v605')){
  assert.equal(row.querySelectorAll('[data-game-key]').length,2,'Shared/reversed league games appear once');
  assert(row.textContent.includes('TEST_ONLY_LEAGUE_A')&&row.textContent.includes('TEST_ONLY_LEAGUE_B'),'Each league retains its own BYE players');
  assert(!row.textContent.includes('Internacional')&&!row.textContent.includes('TEST_ONLY_VENUE'),'International kickoff follows the standard presentation');
 }
 const cards=w.document.querySelectorAll('#matchupCards .matchup-card');
 assert.equal(cards.length,2);for(const card of cards){assert(card.textContent.includes('Estim. parcial'));assert(card.textContent.includes('≈ -20,0'));}
 assert(w.document.querySelector('#decisionCenter').textContent.includes('estimativa parcial'));
 const moves=w.document.querySelectorAll('#recentMoves .move-row');
 assert(moves[0].textContent.includes('TEST_ONLY_ACTOR_B'),'Global moves sort by event time across providers');
 assert(moves[0].textContent.includes('bid 0'),'Real zero bids remain visible');
 w.eval("state.league='A';fccRenderRecentMoves();fccRenderPlanner()");
 assert(!w.document.querySelector('#recentMoves').textContent.includes('TEST_ONLY_ACTOR_B'),'Transactions obey the selected league');
 assert(w.document.querySelector('#recentMoves').textContent.includes('TEST_ONLY_OWNER'),'Legacy User names remain supported');
 const hist=JSON.stringify(w.fccDecisionHistory());w.eval("state.league='ALL';renderAll()");w.eval("state.league='A';renderAll()");w.FCCAccount.apply(payload);
 assert.equal(JSON.stringify(w.fccDecisionHistory()),hist,'Filters and equal data do not create decision records');
 assert(!w.fccDecisionHistory().some(x=>x.week===1&&!x.moves.length));
 assert.equal(w.fccMatchupProbability({myScore:12,oppScore:0,myProjectionEstimate:100,oppProjectionEstimate:120,myProjectionCoverage:{known:1,total:2}}),null,'A missing starter prevents a misleading probability');
 assert.equal(w.fccMatchupProbability({myScore:12,oppScore:0}),null,'Actual points are not missing forecasts');
 assert.equal(w.fccMatchupProbability({myProjectionEstimate:100,oppProjectionEstimate:120}),null,'Legacy partial cache without starter coverage cannot imply a probability');
 assert.equal(w.fccMatchupProbability({myProjectionEstimate:100,myProjectionCoverage:{known:0,total:0},oppProjection:120}),null,'Zero-coverage totals cannot imply a complete roster');
 assert(!w.document.querySelector('#decisionCenter').textContent.includes('Não se aplica à fonte atual'),'Both platforms support the same optional ranking field');
 assert.equal(w.fccPct('75%'),0.75,'Standings percentages keep their fraction representation');
 assert.equal(w.fccPct(0),0,'A winless team retains a real zero, independently of probability bounds');
 const dataBefore=w.eval('DATA'),checked=structuredClone(payload);
 checked.sources=[{id:'A',status:'ready',updatedAt:'2026-10-11T18:00:00Z'}];
 checked.notificationEvents=[];w.FCCAccount.apply(checked);
 assert.equal(w.eval('DATA'),dataBefore,'A same-data freshness check avoids replacing the heavy league snapshot');
 assert.equal(w.eval("DATA.leagues.find(l=>l.id==='A').sourceUpdatedAt"),'2026-10-11T18:00:00Z','A same revision still advances the real last-check timestamp');
 checked.sources[0].status='error';checked.sources[0].error='PROVIDER_UNAVAILABLE';w.FCCAccount.apply(checked);
 assert(w.document.querySelector('#syncStatus').classList.contains('warn'),'A provider failure cannot display a green synchronization success');
 assert(w.document.querySelector('#syncLeagueStatus').textContent.includes('CACHE / ERRO'));
 w.eval('DATA.online.nflWeeks[0].stale=true;renderAll()');
 assert(w.document.querySelector('#threeWeekPlanner').textContent.includes('calendário em cache'),'Retained schedules show their freshness');
 assert(w.document.querySelector('#dataQualityGrid').textContent.includes('Última publicação válida'),'Calendar failure is visible in data quality');
 const a=w.fccNewsTitle({title:"Can the Seahawks' defense again silence the 49ers' hot offense Sunday?",titlePt:'TEST_ONLY bad old translation'});
 assert(a.includes('ataque em boa fase')&&a.includes('Seahawks')&&a.includes('49ers'));
 const b=w.fccNewsTitle({title:"Fantasy football buzz: Expect Bears' Swift to retain RB1 role with Monangai out"});
 assert(b.includes('Bears')&&b.includes('Swift')&&b.includes('Monangai')&&b.includes('deve'));
 const c={title:'Bears and Seahawks update',titlePt:'ursos e falcões atualizados',translationVersion:'rc7'};
 assert.equal(w.fccNewsTitle(c),c.title,'Changed team names invalidate a machine translation');
 assert.equal(errors.length,0,errors.join('\n'));
 console.log('PASS: shared NFL games and individual BYEs, partial projections on both providers, no W1 loading records, stable history, latest named transactions and contextual team-safe news. TEST_ONLY fixtures.');
}finally{dom.window.close();}
