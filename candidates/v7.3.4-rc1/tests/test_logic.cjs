const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync(require('path').join(__dirname,'../app/src/main/assets/fcc/index.html'),'utf8');
for(const m of html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/gi))new vm.Script(m[1]);
function fn(name){const start=html.indexOf('function '+name+'(');assert(start>=0,name);const end=html.indexOf('\nfunction ',start+10);return html.slice(start,end<0?undefined:end);}
const elements={lineupOptimizer:{},threeWeekPlanner:{}};
const context={console,Date,Map,Set,JSON,Number,String,window:{},DATA:{notificationEvents:[]},state:{league:'ALL'},
 FCC_OFFENSE:new Set(['RB','WR','TE','QB']),fccLeagueIsStaleWeek:()=>false,fccAnalysisWeek:()=>5,
 fccCurrentProjection:p=>p.proj,fccPlayerOnBye:p=>!!p.bye,fccStatusUnavailable:()=>false,
 fccNflCode:t=>t,FCC_2026_SCHEDULE_GRID:{},fccScheduleOpponent:()=>null,fccNflLogoOnly:t=>t,
 fccSafe:t=>t,fmt:n=>String(n),$:s=>elements[s.slice(1)],selectedLoaded:()=>[],fccLoadedLeagues:()=>[],
 fccScheduleWeeks:()=>[],fccScheduleGameForTeam:()=>null,fccKickoffLabel:()=> 'dom. 10:30'};
vm.createContext(context);
for(const name of ['fccPlayerCanChangeLineup','fccOptimizerHasLiveGame','fccLineupSuggestionsFor','fccNotificationEvents','fccRenderPlanner'])vm.runInContext(fn(name),context);
let live=false;
context.fccGameStateForNflTeam=t=>t==='DONE'?{started:true,live:false}:t==='UNKNOWN'?null:{started:live,live};
const league={name:'TEST_ONLY',roster:[{player:'starter',pos:'RB',slot:'Starter',nfl:'FUTURE',proj:4},{player:'bench',pos:'RB',slot:'Bench',nfl:'FUTURE',proj:9},{player:'locked',pos:'RB',slot:'Bench',nfl:'DONE',proj:40}]};
let rows=context.fccLineupSuggestionsFor([league]);assert.equal(rows.length,1);assert.equal(rows[0].in.player,'bench');
live=true;assert.equal(context.fccLineupSuggestionsFor([league]).length,0);live=false;
league.roster[1].nfl='UNKNOWN';assert.equal(context.fccLineupSuggestionsFor([league]).length,0);
const future=Date.now()+7200000;
context.fccLoadedLeagues=()=>[{id:'TEST_ONLY',name:'TEST_ONLY',waiverConfig:{nextProcessAt:new Date(future).toISOString()}}];
context.fccScheduleWeeks=()=>[{week:5,games:[{home:'JAX',away:'PHI',country:'United Kingdom',international:true,venue:'Test stadium',startTime:new Date(future).toISOString()}]}];
let events=context.fccNotificationEvents();assert.equal(events.length,3);assert(events.every(e=>new Date(e.at)>new Date()));
context.DATA.notificationEvents=events;assert.equal(context.fccNotificationEvents().length,3);
context.fccScheduleGameForTeam=t=>t==='JAX'?context.fccScheduleWeeks()[0].games[0]:null;
context.selectedLoaded=()=>[{name:'TEST_ONLY',roster:[{player:'starter',slot:'Starter',nfl:'BUF'}]}];
context.fccRenderPlanner();assert(elements.threeWeekPlanner.innerHTML.includes('Internacional'));assert(elements.threeWeekPlanner.innerHTML.includes('Test stadium'));
let count=0;context.window.AndroidSync={scheduleNotifications:()=>count++};context.AndroidSync=context.window.AndroidSync;
vm.runInContext(fn('fccPushNotificationScheduleNative'),context);context.fccPushNotificationScheduleNative();assert.equal(count,1);
context.fccLoadedLeagues=()=>[];context.fccScheduleWeeks=()=>[];context.DATA.notificationEvents=[];
context.fccPushNotificationScheduleNative();assert.equal(count,1,'Empty event list must not replace schedule');
assert(html.includes('#allLeaguesBtn{display:block!important;background:#58d2f2!important;color:#06131e!important'));
assert(html.includes('#rosterHealth .kpis{display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr))!important'));
console.log(JSON.stringify({passed:['all JS syntax','lineup available between games','live-game pause','started-player lock','unknown kickoff guard','provider-timestamp reminder generation','event deduplication','international games without roster player','empty list does not clear schedule','mobile layout/contrast rules'],note:'Fixtures are isolated tests; no league data was created or modified.'},null,2));
