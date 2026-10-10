package com.douglas.fantasycommandcenter;

import android.content.Context;
import android.content.SharedPreferences;
import org.json.JSONArray;
import org.json.JSONObject;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.LinkedHashMap;
import java.util.Map;

/** Reminders derived only from confirmed provider timestamps; no fabricated schedule. */
public final class NotificationEventRepository {
    private NotificationEventRepository(){}

    public static synchronized void refreshFromCaches(Context context){
        SharedPreferences prefs=context.getSharedPreferences(SyncRepository.PREFS,Context.MODE_PRIVATE);
        Map<String,JSONObject> events=new LinkedHashMap<>();
        collectPayload(parse(prefs.getString(SyncRepository.KEY_CACHE,"")),events);
        collectPayload(parse(prefs.getString(BackendApiRepository.KEY_CACHE,"")),events);
        JSONObject schedule=parse(prefs.getString(NflScheduleRepository.KEY_CACHE,""));
        JSONArray weeks=schedule==null?null:schedule.optJSONArray("weeks");
        if(weeks!=null)for(int i=0;i<weeks.length();i++){
            JSONObject week=weeks.optJSONObject(i);if(week==null)continue;
            JSONArray games=week.optJSONArray("games");if(games==null)continue;
            Map<Long,StringBuilder> slots=new LinkedHashMap<>();
            for(int j=0;j<games.length();j++){
                JSONObject game=games.optJSONObject(j);if(game==null||game.optBoolean("fallback",false))continue;
                Long kickoff=timestamp(game.optString("startTime",""));
                if(kickoff==null||kickoff<=System.currentTimeMillis())continue;
                StringBuilder names=slots.get(kickoff);
                if(names==null){names=new StringBuilder();slots.put(kickoff,names);}
                if(names.length()>0)names.append(" • ");
                names.append(game.optString("away")).append(" x ").append(game.optString("home"));
            }
            for(Map.Entry<Long,StringBuilder> slot:slots.entrySet()){
                int w=week.optInt("week",0);long ms=slot.getKey();
                add(events,event("nfl-kickoff-"+w+"-"+ms,"round_start","",ms-1800000L,
                        "Revisar escalação • W"+w,"Jogos em 30 minutos: "+slot.getValue()+". Confira os jogadores que ainda podem ser alterados."));
            }
        }
        JSONArray out=new JSONArray();for(JSONObject event:events.values())out.put(event);
        prefs.edit().putString("notification_events_derived",out.toString()).apply();
        FantasyNotificationScheduler.schedule(context,out.toString());
    }

    private static void collectPayload(JSONObject payload,Map<String,JSONObject> events){
        if(payload==null)return;
        JSONArray supplied=payload.optJSONArray("notificationEvents");
        if(supplied!=null)for(int i=0;i<supplied.length();i++)add(events,supplied.optJSONObject(i));
        JSONArray normalized=payload.optJSONArray("normalizedLeagues");
        if(normalized!=null)for(int i=0;i<normalized.length();i++)collectLeague(normalized.optJSONObject(i),events);
        JSONObject leagues=payload.optJSONObject("leagues");
        if(leagues!=null){java.util.Iterator<String> ids=leagues.keys();while(ids.hasNext()){
            String id=ids.next();JSONObject league=leagues.optJSONObject(id);
            if(league!=null){try{if(!league.has("id"))league.put("id",id);}catch(Exception ignored){}collectLeague(league,events);}
        }}
    }

    private static void collectLeague(JSONObject league,Map<String,JSONObject> events){
        if(league==null||league.optBoolean("pending",false)||league.optBoolean("ok",true)==false)return;
        JSONObject config=league.optJSONObject("waiverConfig");if(config==null)return;
        Long ms=timestamp(config.optString("nextProcessAt",""));if(ms==null)return;
        String id=league.optString("id",""),name=league.optString("name",id);
        if(id.isEmpty())return;
        add(events,event("waiver-process-"+id+"-"+ms,"waiver_end",id,ms,"Waivers • "+name,
                "Processamento de waivers previsto para agora. Atualize para conferir o resultado."));
        add(events,event("waiver-reminder-"+id+"-"+ms,"waiver_start",id,ms-3600000L,"Revisar waivers • "+name,
                "O processamento está previsto para daqui a uma hora. Confira pedidos e cortes."));
    }

    private static void add(Map<String,JSONObject> events,JSONObject event){
        if(event==null)return;Long ms=timestamp(event.optString("at",""));
        if(ms==null||ms<=System.currentTimeMillis())return;
        String id=event.optString("id",event.optString("type")+"|"+event.optString("leagueId")+"|"+ms);
        events.put(id,event);
    }
    private static JSONObject event(String id,String type,String league,long ms,String title,String body){
        try{return new JSONObject().put("id",id).put("type",type).put("leagueId",league)
                .put("at",Instant.ofEpochMilli(ms).toString()).put("title",title).put("body",body);}
        catch(Exception e){return null;}
    }
    private static JSONObject parse(String raw){try{return new JSONObject(raw);}catch(Exception e){return null;}}
    private static Long timestamp(String raw){
        try{return Instant.parse(raw).toEpochMilli();}catch(Exception ignored){}
        try{return OffsetDateTime.parse(raw).toInstant().toEpochMilli();}catch(Exception ignored){}
        try{return raw.matches("\\d{11,}")?Long.parseLong(raw):null;}catch(Exception ignored){return null;}
    }
}
