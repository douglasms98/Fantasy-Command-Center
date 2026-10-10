package com.douglas.fantasycommandcenter;

import android.content.Context;
import org.json.JSONObject;

/** The Cloud calendar is shared by web and Android and has no fixed season. */
public final class NflScheduleRepository {
    public static final String KEY_CACHE="nfl_schedule_cache_v728";
    public static final String KEY_LAST="nfl_schedule_last_v728";
    private NflScheduleRepository(){}
    public static String fetch(Context context,int ignoredWeek) throws Exception {
        String uid=AccountRepository.uid(context);
        JSONObject payload=AccountRepository.request(context,"GET","/v2/nfl-schedule",null);
        synchronized(AccountRepository.class){
            if(uid.isEmpty()||!uid.equals(AccountRepository.uid(context)))throw new IllegalStateException("401:ACCOUNT_CHANGED");
            context.getSharedPreferences(SyncRepository.PREFS,0).edit().putString(KEY_CACHE,payload.toString()).putString(KEY_LAST,payload.optString("generatedAt")).commit();
            NotificationEventRepository.refreshFromCaches(context);
        }
        return payload.toString();
    }
}
