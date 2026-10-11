package com.douglas.fantasycommandcenter;

import android.content.Context;
import org.json.JSONArray;
import org.json.JSONObject;
import java.time.Instant;

/** News comes from the account API. No roster query is sent to public publishers. */
public final class NewsRepository {
    public static final String KEY_CACHE="native_news_cache";
    private NewsRepository(){}

    public static String fetch(Context context,String playersJson) throws Exception {
        String uid=AccountRepository.uid(context);
        if(uid.isEmpty())throw new IllegalStateException("LOGIN_REQUIRED");
        android.content.SharedPreferences prefs=context.getSharedPreferences(SyncRepository.PREFS,Context.MODE_PRIVATE);
        if(!uid.equals(prefs.getString("cache_user_uid","")))throw new IllegalStateException("ACCOUNT_CHANGED");
        String cached=prefs.getString(BackendApiRepository.KEY_CACHE,"");
        if(cached.isEmpty())throw new IllegalStateException("API_UNAVAILABLE");
        JSONObject payload=new JSONObject(cached);
        if(!uid.equals(payload.optString("userId")))throw new IllegalStateException("ACCOUNT_CHANGED");
        JSONObject data=payload.optJSONObject("data"),online=data==null?null:data.optJSONObject("online");
        JSONArray news=online==null?null:online.optJSONArray("news");
        if(news==null)news=new JSONArray();
        String raw=new JSONObject().put("generatedAt",Instant.now().toString()).put("news",news)
            .put("successBatches",1).put("failedBatches",0).toString();
        synchronized(AccountRepository.class){
            if(!uid.equals(AccountRepository.uid(context)))throw new IllegalStateException("ACCOUNT_CHANGED");
            prefs.edit().putString(KEY_CACHE,raw).apply();
        }
        return raw;
    }
}
