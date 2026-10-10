const fs=require('fs'),assert=require('assert'),vm=require('vm');
const {JSDOM,VirtualConsole}=require('jsdom');
const html=fs.readFileSync(require('path').join(__dirname,'../app/src/main/assets/fcc/index.html'),'utf8');
for(const m of html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/gi))new vm.Script(m[1]);
const errors=[],vc=new VirtualConsole();vc.on('jsdomError',e=>{if(!/navigation|scrollTo|canvas/.test(e.message))errors.push(e);});
let user=null,leagues=[],requests=[],deferRefresh=null;
function res(status,data){return Promise.resolve({status,ok:status<400,json:async()=>data});}
const dom=new JSDOM(html,{url:'https://fcc-api-322688211348.southamerica-east1.run.app/app',runScripts:'dangerously',pretendToBeVisual:true,virtualConsole:vc,beforeParse(w){
 w.TextDecoder=TextDecoder;w.TextEncoder=TextEncoder;w.matchMedia=()=>({matches:false,addListener(){},addEventListener(){}});w.scrollTo=()=>{};w.confirm=()=>true;
 w.fetch=(path,options={})=>{requests.push(path);if(path==='/v2/auth/refresh'&&deferRefresh)return deferRefresh; if(path==='/v2/auth/refresh')return user?res(200,{ok:true,user,idToken:'TEST_ONLY_TOKEN'}):res(401,{detail:'LOGIN_REQUIRED'});
 if(path==='/v2/auth/register'){const body=JSON.parse(options.body);user={uid:'TEST_ONLY_NEW',email:body.email,displayName:body.displayName,emailVerified:false};return res(200,{ok:true,user,idToken:'TEST_ONLY_TOKEN'});}
 if(path==='/v2/auth/login'){assert(user);return res(200,{ok:true,user,idToken:'TEST_ONLY_TOKEN'});}
 if(path==='/v2/auth/logout'){user=null;return res(200,{ok:true});}
 if(path==='/v2/leagues')return res(200,{ok:true,leagues});
 if(path==='/v2/app-payload')return res(200,{ok:true,userId:user.uid,schema:'fcc-data-v8',generatedAt:new Date().toISOString(),data:{season:2026,leagues:leagues.map(l=>({...l,loaded:!!l.loaded,scoring:'—',pendingReason:'TEST_ONLY_PENDING',freshness:'TEST_ONLY_PENDING',roster:l.roster||[],waivers:[],weekly:[],standings:[],poscomp:[],posRanks:{},tradeSuggestions:[],summary:{totalPlayers:(l.roster||[]).length,starters:1},user:{wins:0,losses:0,pf:0,relativeIndex:null},analysisWeek:6,sourceAnalysisWeek:6,projectionWeek:6})),meta:{loadedCount:0,pendingCount:leagues.length,combinedWins:0,combinedLosses:0,sourceAnalysisWeek:0,historyThroughWeek:0},online:{news:[],nflWeeks:[]}}});
 return res(200,{ok:true});};
}});
const w=dom.window;
const tick=()=>new Promise(r=>setTimeout(r,60));
(async()=>{
 await tick();assert.equal(errors.length,0,errors.map(e=>e.stack).join('\n'));
 assert.equal(w.document.getElementById('accountGate').hidden,false);
 assert(!html.includes('RJ Outlaws'));assert(!html.includes('id="backendToken"'));assert(!html.includes('id="syncToken"'));
 assert.equal(w.eval('DATA.leagues.length'),0);
 w.document.getElementById('accountEmailInput').value='new@example.invalid';w.document.getElementById('accountPassword').value='TEST_ONLY_PASSWORD';w.document.getElementById('accountName').value='TEST_ONLY_NEW';
 await w.FCCAccount.auth(true);assert.equal(w.FCCAccount.user.emailVerified,false);assert.equal(w.document.getElementById('accountGate').hidden,false);assert.equal(w.document.getElementById('accountCredentials').hidden,true);assert.equal(w.document.getElementById('accountPassword').value,'');assert(requests.includes('/v2/auth/verify-email'));
 await w.FCCAccount.logout();
 user={uid:'TEST_ONLY_A',email:'a@example.invalid',emailVerified:true};leagues=Array.from({length:4},(_,i)=>({id:'a'+i,name:'TEST_ONLY_A_'+i,team:'TEST_ONLY',platform:'Sleeper',status:'registered'}));
 w.document.getElementById('accountEmailInput').value=user.email;w.document.getElementById('accountPassword').value='TEST_ONLY_PASSWORD';await w.FCCAccount.auth(false);
 assert.equal(w.document.getElementById('accountGate').hidden,true);assert.equal(w.eval('DATA.leagues.length'),4);assert.equal(w.document.querySelectorAll('#accountLeagueList .account-league').length,4);
 w.eval('FCCUserStorage.setItem("TEST_ONLY_PERSONAL","A_SECRET_TEST");');
 await w.FCCAccount.logout();assert.equal(w.eval('DATA.leagues.length'),0);assert.equal(w.document.getElementById('accountGate').hidden,false);
 user={uid:'TEST_ONLY_B',email:'b@example.invalid',emailVerified:true};leagues=Array.from({length:2},(_,i)=>({id:'b'+i,name:'TEST_ONLY_B_'+i,team:'TEST_ONLY',platform:'ESPN',status:'private_pending'}));
 await w.FCCAccount.restore();await w.FCCAccount.refresh(false);
 assert.equal(w.eval('DATA.leagues.length'),2);assert.equal(w.document.querySelectorAll('#accountLeagueList .account-league').length,2);
 assert.equal(w.eval('FCCUserStorage.getItem("TEST_ONLY_PERSONAL")'),null);
 assert(!w.document.getElementById('accountLeagueList').textContent.includes('TEST_ONLY_A_'));
 assert.throws(()=>w.FCCAccount.apply({userId:'TEST_ONLY_A',schema:'fcc-data-v8',data:{leagues:[]}}),/ACCOUNT_CHANGED/);
 const malicious='<img data-test-only-xss="yes" src="x" onerror="window.TEST_ONLY_XSS=1">';
 leagues=[{id:'b0',name:malicious,team:malicious,platform:'Sleeper',status:'ready',loaded:true,roster:[{playerId:'TEST_ONLY',player:"De'Von TEST_ONLY",pos:'RB',nfl:'MIA',slot:'Starter',currentProjection:0,projectionWeek:6,ppg3:0,recentScores:[0],historicalScores:{'5':0}}]}];
 await w.FCCAccount.refresh(false);
 assert.equal(w.eval('loaded.length'),1);assert.equal(w.document.querySelector('[data-test-only-xss]'),null);assert(!w.TEST_ONLY_XSS);
 w.document.getElementById('globalPlayerSearch').value="De'Von";w.fccGlobalSearch();
 const player=w.document.querySelector('#globalSearchResults [data-player-name]');assert(player);player.click();
 assert.equal(w.document.getElementById('playerModalTitle').textContent,"De'Von TEST_ONLY");
 const watch=w.document.querySelector('[data-watch-player]');assert(watch);watch.click();
 assert.equal(w.fccWatchlist().length,1);
 let release;deferRefresh=new Promise(r=>release=r);const old=w.FCCAccount.restore();
 const quitting=w.FCCAccount.logout();release({status:200,ok:true,json:async()=>({ok:true,user:{uid:'TEST_ONLY_B',email:'b@example.invalid',emailVerified:true},idToken:'TEST_ONLY_STALE'})});
 await assert.rejects(old,/ACCOUNT_CHANGED/);await quitting;assert.equal(w.FCCAccount.user,null);assert.equal(w.eval('DATA.leagues.length'),0);assert.equal(w.document.getElementById('playerModalBody').textContent,'');assert(!w.document.getElementById('playerModal').classList.contains('show'));
 assert.equal(errors.length,0,errors.map(e=>e.stack).join('\n'));
 console.log('PASS: full HTML initializes, login gate, empty account, four vs two leagues, logout cleanup, UID-scoped storage loaded data, safe names, player/watchlist clicks and stale-session rejection. TEST_ONLY fixtures.');
 dom.window.close();
})().catch(e=>{console.error(e);dom.window.close();process.exitCode=1;});
