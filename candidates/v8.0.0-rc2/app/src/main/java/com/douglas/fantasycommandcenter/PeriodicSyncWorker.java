package com.douglas.fantasycommandcenter;
import android.content.Context;
import androidx.annotation.NonNull;
import androidx.work.*;
import java.time.Instant;
import java.util.concurrent.TimeUnit;

public class PeriodicSyncWorker extends Worker {
    public PeriodicSyncWorker(@NonNull Context context,@NonNull WorkerParameters params){super(context,params);}
    @NonNull public Result doWork(){
        Context c=getApplicationContext(); if(!AccountRepository.signedIn(c))return Result.success(); int successes=0;
        StringBuilder errors=new StringBuilder();
        if(BackendApiRepository.isConfigured(c)) {
            try{AccountRepository.request(c,"POST","/v2/sync",null);BackendApiRepository.fetchLive(c);successes++;}catch(Exception e){errors.append("API: ").append(e.getClass().getSimpleName()).append("; ");}
        }
        try{NflScheduleRepository.fetch(c,0);successes++;}catch(Exception e){errors.append("Calendário: ").append(e.getClass().getSimpleName());}
        NotificationEventRepository.refreshFromCaches(c);
        android.content.SharedPreferences.Editor ed=c.getSharedPreferences(SyncRepository.PREFS,Context.MODE_PRIVATE).edit()
                .putString("background_last_attempt",Instant.now().toString()).putString("background_error",errors.toString());
        if(successes>0)ed.putString("background_last_success",Instant.now().toString());ed.apply();
        return successes>0?Result.success():Result.retry();
    }
    public static void ensure(Context c){
        Constraints constraints=new Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build();
        PeriodicWorkRequest request=new PeriodicWorkRequest.Builder(PeriodicSyncWorker.class,4,TimeUnit.HOURS)
                .setConstraints(constraints).build();
        WorkManager.getInstance(c).enqueueUniquePeriodicWork("fcc-periodic-sync",ExistingPeriodicWorkPolicy.UPDATE,request);
    }
}
