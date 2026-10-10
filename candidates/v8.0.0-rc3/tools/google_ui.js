// Included in both HTML assets by tools/build_google_ui.py.
window.FCCGoogle={
 config:null,configFlight:null,preparing:null,scriptFlight:null,challenge:null,timer:null,sequence:0,nativeRequest:null,
 purpose(){return !FCCAccount.user?'login':FCCAccount.user.emailVerified&&!FCCAccount.user.googleLinked&&FCCAccount.user.provider!=='google.com'?'link':null;},
 controls(purpose=this.purpose()||'login'){
  const suffix=purpose==='link'?'Link':'Login';
  return {area:document.getElementById('accountGoogle'+suffix),web:document.getElementById('googleWeb'+suffix),
   native:document.getElementById('googleNative'+suffix),notice:document.getElementById('googleNotice'+suffix),retry:document.getElementById('googleRetry'+suffix)};
 },
 notice(text,retry=false){const c=this.controls();c.notice.textContent=text;c.retry.hidden=!retry;},
 visible(){
  const purpose=this.purpose();
  for(const p of ['login','link']){
   const c=this.controls(p);c.area.hidden=p!==purpose;
   c.native.hidden=!FCCAccount.native();c.web.hidden=FCCAccount.native();
   c.native.disabled=!this.config?.enabled||!!FCCAccount.authFlight;
  }
 },
 async configuration(force=false){
  if(force)this.config=null;
  if(this.config)return this.config;
  if(this.configFlight)return this.configFlight;
  this.configFlight=FCCAccount.raw('GET','/v2/auth/google/config');
  try{this.config=await this.configFlight;return this.config;}finally{this.configFlight=null;}
 },
 async library(){
  if(window.google?.accounts?.id)return;
  if(this.scriptFlight)return this.scriptFlight;
  this.scriptFlight=new Promise((resolve,reject)=>{
   const script=document.createElement('script');script.src='https://accounts.google.com/gsi/client?hl=pt-BR';script.async=true;
   const timer=setTimeout(()=>{script.remove();reject(new Error('GOOGLE_UNAVAILABLE'));},15000);
   script.onload=()=>{clearTimeout(timer);if(window.google?.accounts?.id)resolve();else reject(new Error('GOOGLE_UNAVAILABLE'));};
   script.onerror=()=>{clearTimeout(timer);script.remove();reject(new Error('GOOGLE_UNAVAILABLE'));};
   document.head.append(script);
  });
  try{await this.scriptFlight;}catch(e){this.scriptFlight=null;throw e;}
 },
 async prepare(force=false){
  if(this.preparing)return this.preparing;
  const sequence=this.sequence,generation=FCCAccount.generation,purpose=this.purpose(),uid=FCCAccount.user?.uid||'';
  this.visible();if(!purpose)return;
  this.preparing=(async()=>{
   try{
    const config=await this.configuration(force);if(sequence!==this.sequence||generation!==FCCAccount.generation)return;
    this.visible();
    if(!config.enabled){this.notice('O login com Google está indisponível no momento.',true);return;}
    if(FCCAccount.native()){
     if(typeof AndroidSync.signInWithGoogle!=='function'){this.notice('Atualize o aplicativo para entrar com Google.',false);this.controls().native.disabled=true;}
     else this.notice(purpose==='link'?'Use sua conta Google nas próximas entradas.':'Entre com sua conta Google, sem criar outra senha.');
     return;
    }
    if(this.challenge&&this.challenge.generation===generation&&this.challenge.purpose===purpose&&this.challenge.expiresAt>Date.now()+30000&&!force)return;
    await this.library();if(sequence!==this.sequence||generation!==FCCAccount.generation)return;
    if(FCCAccount.logoutFlight)await FCCAccount.logoutFlight;
    if(purpose==='link')await FCCAccount.restore();
    if(sequence!==this.sequence||generation!==FCCAccount.generation)return;
    const challenge=await FCCAccount.raw('POST','/v2/auth/google/challenge',{purpose});
    if(sequence!==this.sequence||generation!==FCCAccount.generation||this.purpose()!==purpose)return;
    const context={...challenge,purpose,generation,uid,expiresAt:Date.now()+challenge.expiresIn*1000};this.challenge=context;
    google.accounts.id.initialize({client_id:challenge.clientId,nonce:challenge.nonce,auto_select:false,ux_mode:'popup',
      callback:response=>this.receive(response,context)});
    const control=this.controls(purpose);control.web.replaceChildren();
    google.accounts.id.renderButton(control.web,{type:'standard',theme:'outline',size:'large',shape:'pill',text:'continue_with',
      locale:'pt-BR',width:Math.min(360,Math.max(200,control.web.clientWidth||320))});
    this.notice(purpose==='link'?'Vincule o Google à sua conta atual para manter suas ligas.':'Entre com sua conta Google, sem criar outra senha.');
    clearTimeout(this.timer);this.timer=setTimeout(()=>this.prepare(true),240000);
   }catch(e){if(sequence===this.sequence&&generation===FCCAccount.generation){this.notice('Não foi possível carregar o login com Google. Tente novamente.',true);}}
  })();
  try{await this.preparing;}finally{
   this.preparing=null;
   if(sequence!==this.sequence)this.prepare();
  }
 },
 sessionChanged(){
  if(this.challenge&&(this.challenge.generation!==FCCAccount.generation||this.challenge.uid!==(FCCAccount.user?.uid||'')||this.challenge.purpose!==this.purpose())){
   this.sequence++;this.challenge=null;clearTimeout(this.timer);this.timer=null;
   if(window.google?.accounts?.id)google.accounts.id.cancel();
  }
  this.visible();this.prepare();
 },
 async receive(response,context){
  if(FCCAccount.authFlight||context.generation!==FCCAccount.generation||context.uid!==(FCCAccount.user?.uid||'')||this.purpose()!==context.purpose)return;
  if(!response.credential)return;
  FCCAccount.authFlight=true;this.visible();let exchange;
  try{
   if(context.expiresAt<=Date.now())throw new Error('GOOGLE_CHALLENGE_EXPIRED');
   if(FCCAccount.logoutFlight)await FCCAccount.logoutFlight;
   if(context.generation!==FCCAccount.generation)throw new Error('ACCOUNT_CHANGED');
   FCCAccount.message(context.purpose==='link'?'Vinculando sua conta Google…':'Entrando com Google…');
   exchange=FCCAccount.raw('POST','/v2/auth/google'+(context.purpose==='link'?'/link':''),
    {challengeId:context.challengeId,googleIdToken:response.credential});
   FCCAccount.authExchangeFlight=exchange;
   const result=await exchange;
   if(context.generation!==FCCAccount.generation)throw new Error('ACCOUNT_CHANGED');
   document.getElementById('accountPassword').value='';FCCAccount.token=result.idToken||'';FCCAccount.setUser(result.user);
   FCCAccount.message(context.purpose==='link'?'Conta Google vinculada. Suas ligas foram mantidas.':'Você entrou com Google.');
   if(result.user.emailVerified)await FCCAccount.refresh(false);
  }catch(e){if(context.generation===FCCAccount.generation)FCCAccount.message(FCCAccount.error(e.message));}
  finally{
   if(FCCAccount.authExchangeFlight===exchange)FCCAccount.authExchangeFlight=null;
   FCCAccount.authFlight=false;this.challenge=null;clearTimeout(this.timer);this.visible();this.prepare(true);
  }
 },
 async native(purpose){
  if(FCCAccount.authFlight||!this.config?.enabled)return;
  const generation=FCCAccount.generation;FCCAccount.authFlight=true;this.visible();
  try{
   if(FCCAccount.logoutFlight)await FCCAccount.logoutFlight;
   if(generation!==FCCAccount.generation)throw new Error('ACCOUNT_CHANGED');
   FCCAccount.message(purpose==='link'?'Escolha a conta Google que deseja vincular.':'Escolha sua conta Google.');
   const result=await new Promise((resolve,reject)=>{
    const id='g'+(++FCCAccount.seq)+'_'+Date.now();this.nativeRequest=id;
    const timer=setTimeout(()=>{FCCAccount.pending.delete(id);reject(new Error('GOOGLE_CHALLENGE_EXPIRED'));},310000);
    FCCAccount.pending.set(id,{resolve,reject,timer});
    try{AndroidSync.signInWithGoogle(id,purpose==='link');}catch(e){clearTimeout(timer);FCCAccount.pending.delete(id);reject(new Error('GOOGLE_DEVICE_UNAVAILABLE'));}
   });
   if(generation!==FCCAccount.generation)throw new Error('ACCOUNT_CHANGED');
   document.getElementById('accountPassword').value='';FCCAccount.setUser(result.user);
   FCCAccount.message(purpose==='link'?'Conta Google vinculada. Suas ligas foram mantidas.':'Você entrou com Google.');
   if(result.user.emailVerified)await FCCAccount.refresh(false);
  }catch(e){if(generation===FCCAccount.generation)FCCAccount.message(FCCAccount.error(e.message));}
  finally{this.nativeRequest=null;FCCAccount.authFlight=false;this.visible();}
 },
 logout(){
  this.sequence++;this.challenge=null;clearTimeout(this.timer);this.timer=null;
  if(window.google?.accounts?.id){google.accounts.id.cancel();google.accounts.id.disableAutoSelect();}
  if(this.nativeRequest){const pending=FCCAccount.pending.get(this.nativeRequest);if(pending){clearTimeout(pending.timer);FCCAccount.pending.delete(this.nativeRequest);pending.reject(new Error('ACCOUNT_CHANGED'));}}
 },
 init(){
  for(const purpose of ['login','link']){
   const c=this.controls(purpose);c.native.addEventListener('click',()=>this.native(purpose));
   c.retry.addEventListener('click',()=>this.prepare(true));
  }
  this.sessionChanged();
 }
};
