// TEST_ONLY users and responses. This does not execute a real Google sign-in.
const {JSDOM,VirtualConsole}=require('jsdom');
const fs=require('fs'),assert=require('assert/strict');
const html=fs.readFileSync('backend/static/index.html','utf8');
const tick=()=>new Promise(resolve=>setTimeout(resolve,50));
const CLIENT='123456789-TEST_ONLY.apps.googleusercontent.com';
const GOOGLE_TOKEN='TEST_ONLY_HEADER.TEST_ONLY_PAYLOAD.TEST_ONLY_SIGNATURE';

function create({native=false,enabled=true}={}){
 const errors=[],requests=[],rendered=[],googleCalls=[];let user=null,challengeCount=0,exchangeResult=null,deferExchange=null,nativeCancel=false;
 const response=(status,json)=>Promise.resolve({status,ok:status<400,json:async()=>json});
 const payload=()=>({ok:true,userId:user.uid,schema:'fcc-data-v8',data:{schema:'fcc-data-v8',season:2026,leagues:[],meta:{sourceAnalysisWeek:6,registeredCount:0,maxLeagues:6,remainingSlots:6}},sources:[]});
 const virtualConsole=new VirtualConsole();virtualConsole.on('jsdomError',error=>errors.push(error));
 const state={};
 const dom=new JSDOM(html,{runScripts:'dangerously',url:'https://fcc-api-v8.example.invalid/app',virtualConsole,beforeParse(w){
  w.matchMedia=()=>({matches:false,addListener(){},removeListener(){},addEventListener(){}});w.scrollTo=()=>{};w.confirm=()=>true;
  w.google={accounts:{id:{initialize(options){state.options=options;googleCalls.push(options);},renderButton(element,options){rendered.push({element,options});element.textContent='TEST_ONLY_GOOGLE_BUTTON';},cancel(){},disableAutoSelect(){state.disabledAutoSelect=true;}}}};
  w.fetch=(path,options={})=>{
   const method=options.method||'GET',body=options.body?JSON.parse(options.body):null;requests.push({path,method,body});
   if(path==='/v2/auth/google/config')return response(200,{ok:true,enabled,clientId:enabled?CLIENT:''});
   if(path==='/v2/auth/google/challenge')return response(200,{ok:true,clientId:CLIENT,challengeId:String(++challengeCount).padStart(64,'0'),nonce:'TEST_ONLY_NONCE_'+challengeCount,expiresIn:300});
   if(path==='/v2/auth/google'||path==='/v2/auth/google/link'){
    if(deferExchange)return deferExchange;
    if(exchangeResult)return response(exchangeResult.status,exchangeResult.json);
    user={uid:user?.uid||'TEST_ONLY_GOOGLE',email:'google@example.invalid',emailVerified:true,provider:'google.com'};
    return response(200,{ok:true,idToken:'TEST_ONLY_FIREBASE_ID',user});
   }
   if(path==='/v2/auth/refresh')return user?response(200,{ok:true,user,idToken:'TEST_ONLY_FIREBASE_ID'}):response(401,{detail:'LOGIN_REQUIRED'});
   if(path==='/v2/auth/login'){user={uid:'TEST_ONLY_PASSWORD',email:'password@example.invalid',emailVerified:true,provider:'password'};return response(200,{ok:true,user,idToken:'TEST_ONLY_FIREBASE_ID'});}
   if(path==='/v2/auth/logout'){user=null;return response(200,{ok:true});}
   if(path==='/v2/app-payload')return response(200,payload());
   if(path==='/v2/leagues')return response(200,{ok:true,leagues:[],registeredCount:0,maxLeagues:6,remainingSlots:6});
   if(path==='/v2/nfl-schedule')return response(200,{ok:true,weeks:[]});
   return response(200,{ok:true});
  };
  if(native){
   w.AndroidSync={accountRequest(id,method,path,body){
    w.fetch(path,{method,body:body||undefined}).then(async response=>{
     const result=await response.json();if(!response.ok){result.ok=false;result.error=result.detail;}
     w.FCCAccount.nativeResult(id,Buffer.from(JSON.stringify(result)).toString('base64'));
    });
   },signInWithGoogle(id,link){
    state.nativeCalls=(state.nativeCalls||0)+1;state.nativeLink=link;
    const result=nativeCancel?{ok:false,error:'GOOGLE_CANCELLED'}:{ok:true,user:{uid:'TEST_ONLY_NATIVE',email:'native@example.invalid',emailVerified:true,provider:'google.com'}};
    if(result.user)user=result.user;
    setTimeout(()=>w.FCCAccount.nativeResult(id,Buffer.from(JSON.stringify(result)).toString('base64')),0);
   }};
  }
 }});
 return {dom,w:dom.window,errors,requests,rendered,googleCalls,state,
  setExchange(result){exchangeResult=result;},defer(promise){deferExchange=promise;},cancelNative(value){nativeCancel=value;}};
}

(async()=>{
 let test=create();try{
  await tick();const {w,state,requests,rendered}=test;
  assert.equal(w.document.getElementById('accountGoogleLogin').hidden,false);
  assert.equal(rendered[0].options.locale,'pt-BR');assert.equal(state.options.client_id,CLIENT);assert.equal(state.options.nonce,'TEST_ONLY_NONCE_1');
  assert.equal(w.document.getElementById('accountGoogleLogin').closest('form'),null,'Google does not require filling the password form');
  const context=w.FCCGoogle.challenge;await w.FCCGoogle.receive({credential:GOOGLE_TOKEN},context);
  assert.equal(w.FCCAccount.user.uid,'TEST_ONLY_GOOGLE');assert.equal(w.document.getElementById('accountGate').hidden,true);
  const exchange=requests.find(request=>request.path==='/v2/auth/google');assert.deepEqual(exchange.body,{challengeId:context.challengeId,googleIdToken:GOOGLE_TOKEN});
  assert.equal(w.FCCAccount.token,'TEST_ONLY_FIREBASE_ID');
  const cached=Array.from({length:w.localStorage.length},(_,i)=>w.localStorage.getItem(w.localStorage.key(i))).join('');
  assert(!cached.includes(GOOGLE_TOKEN)&&!cached.includes('TEST_ONLY_FIREBASE_ID'),'Credentials must not be stored with UI preferences');
  assert.equal(w.document.getElementById('accountGoogleLink').hidden,true);
  assert(!requests.some(request=>request.path==='/v2/auth/verify-email'));
  await w.FCCAccount.logout();await tick();assert(state.disabledAutoSelect);
  const before=requests.length;await w.FCCGoogle.receive({credential:GOOGLE_TOKEN},context);
  assert.equal(requests.length,before,'A callback from before logout must not authenticate again');
  assert.equal(w.FCCAccount.user,null);assert.equal(test.errors.length,0);
 }finally{test.dom.window.close();}

 test=create();try{
  await tick();const {w}=test;
  test.setExchange({status:409,json:{detail:'GOOGLE_ACCOUNT_LINK_REQUIRED'}});
  await w.FCCGoogle.receive({credential:GOOGLE_TOKEN},w.FCCGoogle.challenge);
  assert.equal(w.FCCAccount.user,null);assert(w.document.getElementById('accountMessage').textContent.includes('Vincular conta Google'));
  test.setExchange(null);w.document.getElementById('accountEmailInput').value='password@example.invalid';w.document.getElementById('accountPassword').value='TEST_ONLY_PASSWORD';
  await w.FCCAccount.auth(false);await tick();assert.equal(w.document.getElementById('accountGoogleLink').hidden,false);
  const uid=w.FCCAccount.user.uid,context=w.FCCGoogle.challenge;assert.equal(context.purpose,'link');
  await w.FCCGoogle.receive({credential:GOOGLE_TOKEN},context);assert.equal(w.FCCAccount.user.uid,uid);
  assert(test.requests.some(request=>request.path==='/v2/auth/google/link'));assert.equal(test.errors.length,0);
 }finally{test.dom.window.close();}

 test=create();try{
  await tick();const {w}=test;let release;
  test.defer(new Promise(resolve=>release=resolve));
  const login=w.FCCGoogle.receive({credential:GOOGLE_TOKEN},w.FCCGoogle.challenge);await tick();
  const quitting=w.FCCAccount.logout();await tick();
  assert(!test.requests.some(request=>request.path==='/v2/auth/logout'),'Logout waits for the pending cookie exchange');
  release({status:200,ok:true,json:async()=>({ok:true,idToken:'TEST_ONLY_LATE_TOKEN',user:{uid:'TEST_ONLY_LATE',emailVerified:true,provider:'google.com'}})});
  await Promise.all([login,quitting]);await tick();
  assert(test.requests.some(request=>request.path==='/v2/auth/logout'));assert.equal(w.FCCAccount.user,null);assert.equal(w.FCCAccount.token,'');assert.equal(test.errors.length,0);
 }finally{test.dom.window.close();}

 test=create({native:true});try{
  await tick();const {w}=test;assert.equal(w.document.getElementById('googleNativeLogin').hidden,false);
  assert.equal(test.googleCalls.length,0,'Google JavaScript OAuth is not initialized inside the Android WebView');
  test.cancelNative(true);await w.FCCGoogle.native('login');assert(w.document.getElementById('accountMessage').textContent.includes('cancelado'));
  assert.equal(w.document.getElementById('googleNativeLogin').disabled,false);
  test.cancelNative(false);await w.FCCGoogle.native('login');assert.equal(w.FCCAccount.user.uid,'TEST_ONLY_NATIVE');
  assert.equal(w.FCCAccount.token,'');assert.equal(w.FCCAccount.pending.size,0);assert.equal(test.errors.length,0);
 }finally{test.dom.window.close();}

 test=create({enabled:false});try{
  await tick();const {w}=test;assert.equal(test.googleCalls.length,0);
  assert.equal(w.document.getElementById('googleRetryLogin').hidden,false);
  assert(w.document.getElementById('googleNoticeLogin').textContent.includes('indisponível'));assert.equal(test.errors.length,0);
 }finally{test.dom.window.close();}
 console.log('PASS: Google web button/nonce, password-free entry, account linking, provider errors, stale callbacks, logout during cookie exchange, native chooser/cancellation, disabled setup and no WebView OAuth. TEST_ONLY fixtures.');
})().catch(error=>{console.error(error);process.exitCode=1;});
