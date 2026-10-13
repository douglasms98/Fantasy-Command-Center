// TEST_ONLY fixtures exercise the complete page, never the deployed provider.
const fs=require('fs'),assert=require('assert'),vm=require('vm'),crypto=require('crypto');
const {JSDOM,VirtualConsole}=require('jsdom');
const html=fs.readFileSync(require('path').join(__dirname,'../app/src/main/assets/fcc/index.html'),'utf8');
for(const m of html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/gi))new vm.Script(m[1]);
const errors=[],vc=new VirtualConsole();
vc.on('jsdomError',e=>{if(!/navigation|scrollTo|canvas/.test(e.message))errors.push(e);});
let user=null,leagues=[],requests=[],deferRefresh=null,deferPayload=null,deferList=null;
function res(status,data){return Promise.resolve({status,ok:status<400,json:async()=>data});}
function payload(){
 return {ok:true,userId:user.uid,schema:'fcc-data-v8',generatedAt:new Date().toISOString(),data:{season:2026,
  leagues:leagues.map(l=>({...l,loaded:!!l.loaded,scoring:'—',pendingReason:'TEST_ONLY_PENDING',freshness:'TEST_ONLY_PENDING',roster:l.roster||[],waivers:[],weekly:[],standings:[],poscomp:[],posRanks:{},tradeSuggestions:[],summary:{totalPlayers:(l.roster||[]).length,starters:1},user:{wins:0,losses:0,pf:0,relativeIndex:null},analysisWeek:6,sourceAnalysisWeek:6,projectionWeek:6})),
  meta:{loadedCount:leagues.filter(l=>l.loaded).length,pendingCount:leagues.filter(l=>!l.loaded).length,registeredCount:leagues.length,maxLeagues:6,remainingSlots:6-leagues.length,combinedWins:0,combinedLosses:0,sourceAnalysisWeek:0,historyThroughWeek:0},online:{news:[],nflWeeks:[]}}};
}
const dom=new JSDOM(html,{url:'https://fcc-api-322688211348.southamerica-east1.run.app/app',runScripts:'dangerously',pretendToBeVisual:true,virtualConsole:vc,beforeParse(w){
 w.TextDecoder=TextDecoder;w.TextEncoder=TextEncoder;w.matchMedia=()=>({matches:false,addListener(){},addEventListener(){}});w.scrollTo=()=>{};w.confirm=()=>true;
 w.fetch=(path,options={})=>{
  const method=options.method||'GET';requests.push({path,method});
  if(path==='/v2/auth/refresh'&&deferRefresh)return deferRefresh;
  if(path==='/v2/auth/refresh')return user?res(200,{ok:true,user,idToken:'TEST_ONLY_TOKEN'}):res(401,{detail:'LOGIN_REQUIRED'});
  if(path==='/v2/auth/register'){const body=JSON.parse(options.body);user={uid:'TEST_ONLY_NEW',email:body.email,displayName:body.displayName,emailVerified:false};return res(200,{ok:true,user,idToken:'TEST_ONLY_TOKEN'});}
  if(path==='/v2/auth/login'){assert(user);return res(200,{ok:true,user,idToken:'TEST_ONLY_TOKEN'});}
  if(path==='/v2/auth/logout'){user=null;return res(200,{ok:true});}
  if(path==='/v2/leagues'&&method==='POST'){
   const body=JSON.parse(options.body),id=crypto.createHash('sha256').update(body.platform+':'+body.leagueId).digest('hex').slice(0,32);
   const existing=leagues.find(l=>l.id===id);if(existing)return res(201,{ok:true,created:false,league:existing});
   if(leagues.length>=6)return res(409,{detail:'LEAGUE_LIMIT_REACHED'});
   const league={...body,id,name:body.name||'TEST_ONLY_'+body.leagueId,team:'TEST_ONLY',status:body.platform==='ESPN'?'private_pending':'registered'};
   leagues.push(league);return res(201,{ok:true,created:true,league});
  }
  if(path==='/v2/leagues'){if(deferList)return deferList;return res(200,{ok:true,leagues:structuredClone(leagues),registeredCount:leagues.length,maxLeagues:6,remainingSlots:6-leagues.length});}
  if(path.startsWith('/v2/leagues/')&&method==='DELETE'){const id=path.split('/').pop();leagues=leagues.filter(l=>l.id!==id);return res(200,{ok:true});}
  if(path==='/v2/app-payload'){if(deferPayload)return deferPayload;return res(200,payload());}
  return res(200,{ok:true});
 };
}});
const w=dom.window,$=id=>w.document.getElementById(id);
const tick=()=>new Promise(r=>setTimeout(r,60));
function assertCount(count){
 assert.equal(w.eval('DATA.leagues.length'),count,'Only registered leagues are in the dashboard data');
 assert.equal(w.document.querySelectorAll('#accountLeagueList .account-league').length,count,'Account list follows actual registrations');
 assert.equal(w.document.querySelectorAll('#platformLeagueGroups .platform-league-card').length,count,'Home has exactly one card per registered league');
 assert.equal(w.document.querySelectorAll('#leagueFilter option:not([value="ALL"])').length,count,'Filter has no fixed or spare league slots');
 assert.equal($('accountLeagueQuota').textContent,`${count} de 6 ligas cadastradas`);
 assert.equal($('accountAddLeague').disabled,count===6);
 assert.equal($('accountLeagueLimitNote').hidden,count!==6);
}
async function registerLeague(number,platform='Sleeper'){
 $('accountPlatform').value=platform;$('accountPlatform').dispatchEvent(new w.Event('change'));
 $('accountSeason').value='2026';$('accountLeagueId').value=String(1000+number);$('accountTeamId').value='1';$('accountLeagueName').value='TEST_ONLY_'+number;
 await w.FCCAccount.add({preventDefault(){}});
}
(async()=>{
 await tick();assert.equal(errors.length,0,errors.map(e=>e.stack).join('\n'));
 assert.equal($('accountGate').hidden,false);assert.equal($('accountAddLeague').disabled,true);
 assert(!html.includes('RJ Outlaws'));assert(!html.includes('id="backendToken"'));assert(!html.includes('id="syncToken"'));
 assert.equal(w.eval('DATA.leagues.length'),0);
 $('accountEmailInput').value='new@example.invalid';$('accountPassword').value='TEST_ONLY_PASSWORD';$('accountName').value='TEST_ONLY_NEW';
 await w.FCCAccount.auth(true);
 assert.equal(w.FCCAccount.user.emailVerified,false);assert.equal($('accountGate').hidden,false);assert.equal($('accountCredentials').hidden,true);assert.equal($('accountPassword').value,'');assert(requests.some(r=>r.path==='/v2/auth/verify-email'));
 await w.FCCAccount.logout();

 user={uid:'TEST_ONLY_A',email:'a@example.invalid',emailVerified:true};leagues=[];
 $('accountEmailInput').value=user.email;$('accountPassword').value='TEST_ONLY_PASSWORD';await w.FCCAccount.auth(false);
 assert.equal($('accountGate').hidden,true);assertCount(0);
 assert($('homeRegisterLeague'));assert.equal(w.document.querySelectorAll('#platformLeagueGroups .platform-group').length,0);
 $('homeRegisterLeague').click();assert($('syncModal').classList.contains('show'));await tick();
 for(let n=1;n<=6;n++){
  await registerLeague(n,n===2?'ESPN':'Sleeper');assertCount(n);
  if(n===1)assert.equal(w.document.querySelectorAll('#platformLeagueGroups .platform-group').length,1,'No ESPN group before an ESPN league exists');
 }
 assert($('accountLeagueList').textContent.includes('Conexão privada pendente'),'Pending registrations also occupy one slot');
 const posts=requests.filter(r=>r.path==='/v2/leagues'&&r.method==='POST').length;
 await registerLeague(7);assertCount(6);
 assert.equal(requests.filter(r=>r.path==='/v2/leagues'&&r.method==='POST').length,posts,'Seventh registration is blocked in the interface');
 assert($('accountLeagueMessage').textContent.includes('limite de 6 ligas'));
 await assert.rejects(w.FCCAccount.request('POST','/v2/leagues',{platform:'Sleeper',leagueId:'1007'}),/LEAGUE_LIMIT_REACHED/,'Server rejects bypassing the disabled control');

 w.document.querySelector('#accountLeagueList button').click();await tick();assertCount(5);
 await registerLeague(7);assertCount(6);
 const accountA=structuredClone(leagues);w.eval('FCCUserStorage.setItem("TEST_ONLY_PERSONAL","A_SECRET_TEST");');
 await w.FCCAccount.logout();assert.equal(w.eval('DATA.leagues.length'),0);assert.equal($('accountGate').hidden,false);
 assert.equal(w.document.querySelectorAll('#platformLeagueGroups .platform-league-card').length,0);assert.equal($('accountAddLeague').disabled,true);

 user={uid:'TEST_ONLY_B',email:'b@example.invalid',emailVerified:true};leagues=[];
 await w.FCCAccount.restore();await w.FCCAccount.refresh(false);assertCount(0);
 for(let n=1;n<=2;n++){await registerLeague(n,'ESPN');assertCount(n);}
 assert.equal(w.eval('FCCUserStorage.getItem("TEST_ONLY_PERSONAL")'),null);
 assert.equal(w.document.querySelectorAll('#platformLeagueGroups .platform-group').length,1);
 assert.equal(accountA.length,6,'Another account keeps its independently registered leagues');
 assert.throws(()=>w.FCCAccount.apply({userId:'TEST_ONLY_A',schema:'fcc-data-v8',data:{leagues:[]}}),/ACCOUNT_CHANGED/);

 // Registering during an existing refresh must eventually update both lists.
 let releasePayload;const beforeAdd=payload();deferPayload=new Promise(r=>releasePayload=r);
 const refreshing=w.FCCAccount.refresh(false),adding=registerLeague(3);
 await tick();deferPayload=null;releasePayload({status:200,ok:true,json:async()=>beforeAdd});
 await Promise.all([refreshing,adding]);assertCount(3);
 // A late account-list response cannot undo a newer quota or list.
 let releaseList;const oldList=structuredClone(leagues);deferList=new Promise(r=>releaseList=r);
 const staleList=w.FCCAccount.list();deferList=null;await registerLeague(4);assertCount(4);
 releaseList({status:200,ok:true,json:async()=>({ok:true,leagues:oldList})});await staleList;assertCount(4);

 // Another device can fill the account after this client's last read.
 leagues.push({id:'TEST_ONLY_B_EXTERNAL5',name:'TEST_ONLY_EXTERNAL5',team:'TEST_ONLY',platform:'ESPN',status:'private_pending'},
              {id:'TEST_ONLY_B_EXTERNAL6',name:'TEST_ONLY_EXTERNAL6',team:'TEST_ONLY',platform:'ESPN',status:'private_pending'});
 await registerLeague(8);assertCount(6);assert($('accountLeagueMessage').textContent.includes('limite de 6 ligas'));

 const malicious='<img data-test-only-xss="yes" src="x" onerror="window.TEST_ONLY_XSS=1">';
 leagues=[{id:'b0',name:malicious,team:malicious,platform:'Sleeper',status:'ready',loaded:true,roster:[{playerId:'TEST_ONLY',player:"De'Von TEST_ONLY",pos:'RB',nfl:'MIA',slot:'Starter',currentProjection:0,projectionWeek:6,ppg3:0,recentScores:[0],historicalScores:{'5':0}}]}];
 await w.FCCAccount.refresh(false);assertCount(1);
 assert.equal(w.eval('loaded.length'),1);assert.equal(w.document.querySelector('[data-test-only-xss]'),null);assert(!w.TEST_ONLY_XSS);
 $('globalPlayerSearch').value="De'Von";w.fccGlobalSearch();
 const player=w.document.querySelector('#globalSearchResults [data-player-name]');assert(player);player.click();assert.equal($('playerModalTitle').textContent,"De'Von TEST_ONLY");
 const watch=w.document.querySelector('[data-watch-player]');assert(watch);watch.click();assert.equal(w.fccWatchlist().length,1);

 let release;deferRefresh=new Promise(r=>release=r);const old=w.FCCAccount.restore(),quitting=w.FCCAccount.logout();
 release({status:200,ok:true,json:async()=>({ok:true,user:{uid:'TEST_ONLY_B',email:'b@example.invalid',emailVerified:true},idToken:'TEST_ONLY_STALE'})});
 await assert.rejects(old,/ACCOUNT_CHANGED/);await quitting;assert.equal(w.FCCAccount.user,null);assert.equal(w.eval('DATA.leagues.length'),0);assert.equal($('playerModalBody').textContent,'');assert(!$('playerModal').classList.contains('show'));
 assert.equal(errors.length,0,errors.map(e=>e.stack).join('\n'));
 console.log('PASS: dynamic registration 0→1→2→6, account/dashboard/filter counts, pending leagues, seventh rejection, removal frees a slot, per-user isolation, concurrent refresh, stale lists, another-device quota, login/logout, safe names, player/watchlist clicks and stale-session rejection. TEST_ONLY fixtures.');
 dom.window.close();
})().catch(e=>{console.error(e);dom.window.close();process.exitCode=1;});
