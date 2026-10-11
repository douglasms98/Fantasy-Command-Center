// TEST_ONLY native bridge verifies restoration before a pending network call.
const fs=require('fs'),assert=require('assert'),{JSDOM,VirtualConsole}=require('jsdom');
const html=fs.readFileSync(require('path').join(__dirname,'../backend/static/index.html'),'utf8');
const user={uid:'TEST_ONLY_A',email:'a@example.invalid',emailVerified:true,displayName:'TEST_ONLY'};
function cached(uid){return {ok:true,userId:uid,schema:'fcc-data-v8',data:{season:2026,leagues:[{id:'TEST_ONLY_L',platform:'Sleeper',team:'TEST_ONLY_TEAM',name:'TEST_ONLY',loaded:true,roster:[],waivers:[],weekly:[],standings:[],summary:{},user:{},analysisWeek:6,sourceAnalysisWeek:6}],meta:{sourceAnalysisWeek:6},online:{news:[],nflWeeks:[]}}};}
function page(profile,payload){
 const requests=[],errors=[],vc=new VirtualConsole();vc.on('jsdomError',e=>{if(!/canvas|scrollTo/.test(e.message))errors.push(e.message)});
 const dom=new JSDOM(html,{url:'https://appassets.androidplatform.net/assets/fcc/index.html',runScripts:'dangerously',pretendToBeVisual:true,virtualConsole:vc,beforeParse(w){
  w.TextDecoder=TextDecoder;w.TextEncoder=TextEncoder;w.scrollTo=()=>{};w.matchMedia=()=>({matches:false,addEventListener(){},addListener(){}});
  w.AndroidSync={getAccountSession:()=>JSON.stringify({ok:true,user:profile}),getCachedBackendShadow:()=>JSON.stringify(payload),getSavedUiState:()=>'',getNotificationEvents:()=> '[]',
   accountRequest(id,method,path){requests.push({id,method,path});if(path.includes('google/config'))setTimeout(()=>w.FCCAccount.nativeResult(id,Buffer.from(JSON.stringify({ok:true,enabled:false})).toString('base64')),0);}};
 }});
 return {dom,w:dom.window,requests,errors};
}
const tick=()=>new Promise(r=>setTimeout(r,40));
(async()=>{
 const own=page(user,cached(user.uid));await tick();
 assert.equal(own.w.document.getElementById('accountGate').hidden,true,'Cached native profile avoids the login screen while refresh waits');
 assert.equal(own.w.document.getElementById('accountRestoring').hidden,true);
 assert.equal(own.w.eval('DATA.leagues.length'),1,'Owned data is rendered before networking');
 const refresh=own.requests.find(r=>r.path==='/v2/auth/refresh');assert(refresh);
 own.w.FCCAccount.nativeResult(refresh.id,Buffer.from(JSON.stringify({ok:false,error:'AUTH_UNAVAILABLE'})).toString('base64'));await tick();
 assert.equal(own.w.FCCAccount.user.uid,user.uid,'An outage retains the saved session');
 assert.equal(own.w.eval('DATA.leagues.length'),1);
 const position=own.w.eval(`fccBuildPositionContext({},[{_team:'TEST_ONLY_A',slot:'Starter',pos:'WR',currentProjection:10},{_team:'TEST_ONLY_A',slot:'Starter',pos:'WR',currentProjection:null},{_team:'TEST_ONLY_B',slot:'Starter',pos:'WR',currentProjection:20}],{team:'TEST_ONLY_A'})`);
 assert.equal(position.poscomp.find(p=>p.position==='WR').user,null,'Partial projections are not a complete position total');assert.equal(position.overallRank,null);
 const other=page({...user,uid:'TEST_ONLY_B'},cached(user.uid));await tick();assert.equal(other.w.eval('DATA.leagues.length'),0,'A saved payload from another UID is rejected');
 assert(own.w.document.getElementById('accountGate').textContent.includes('Reúna todas suas ligas e faça as melhores decisões'));
 assert(own.w.document.querySelector('#accountGate img').getAttribute('src').startsWith('data:image/'));
 assert.equal(own.errors.length,0,own.errors.join('\n'));assert.equal(other.errors.length,0,other.errors.join('\n'));
 own.dom.window.close();other.dom.window.close();
 console.log('PASS: native cached session before network, offline persistence, UID isolation, complete projection totals and login branding. TEST_ONLY fixtures.');
})().catch(e=>{console.error(e);process.exit(1)});
