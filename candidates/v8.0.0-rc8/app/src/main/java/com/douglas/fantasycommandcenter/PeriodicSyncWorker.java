package com.douglas.fantasycommandcenter;
import android.content.Context;
import androidx.annotation.NonNull;
import androidx.work.*;
import java.time.Instant;
import java.util.concurrent.TimeUnit;

public class PeriodicSyncWorker extends Worker {
    public PeriodicSyncWorker(@NonNull Context context,@NonNull WorkerParameters params){super(context,params);}
    @NonNull public Result doWork(){
        Context c=getApplicationContext(); if(!AccountRepository.signedIn(c))return Result.success(); int successes=0;boolean checked=false;
        StringBuilder errors=new StringBuilder();
        if(BackendApiRepository.isConfigured(c)) {
            try{
                org.json.JSONObject result=AccountRepository.request(c,"POST","/v2/sync",null);
                BackendApiRepository.fetchLive(c);
                checked=true;
                org.json.JSONArray leagues=result.optJSONArray("results");int failed=0;
                if(leagues!=null)for(int i=0;i<leagues.length();i++){
                    org.json.JSONObject league=leagues.optJSONObject(i);
                    if(league==null||!league.optBoolean("ok",false))failed++;
                }
                if(failed>0)errors.append("API: ").append(failed).append(" liga(s) sem atualização; ");
                else successes++;
            }catch(Exception e){errors.append("API: ").append(e.getClass().getSimpleName()).append("; ");}
        }
        try{NflScheduleRepository.fetch(c,0);}catch(Exception e){errors.append("Calendário: ").append(e.getClass().getSimpleName());}
        NotificationEventRepository.refreshFromCaches(c);
        android.content.SharedPreferences.Editor ed=c.getSharedPreferences(SyncRepository.PREFS,Context.MODE_PRIVATE).edit()
                .putString("background_last_attempt",Instant.now().toString()).putString("background_error",errors.toString());
        if(successes>0)ed.putString("background_last_success",Instant.now().toString());ed.apply();
        // An acknowledged source error is reported above and retried on the
        // normal four-hour schedule. Private authorization needs user action;
        // it must not trigger repeated immediate background requests.
        return checked?Result.success():Result.retry();
    }
    public static void ensure(Context c){
        Constraints constraints=new Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build();
        PeriodicWorkRequest request=new PeriodicWorkRequest.Builder(PeriodicSyncWorker.class,4,TimeUnit.HOURS)
                .setConstraints(constraints).build();
        WorkManager.getInstance(c).enqueueUniquePeriodicWork("fcc-periodic-sync",ExistingPeriodicWorkPolicy.UPDATE,request);
    }
}
