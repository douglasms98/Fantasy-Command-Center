package com.douglas.fantasycommandcenter;

import android.content.Context;

/** Account-authenticated Cloud data. No configurable endpoint or shared key. */
public final class BackendApiRepository {
    public static final String KEY_CACHE="backend_shadow_cache";
    public static final String KEY_LAST="backend_shadow_last";
    private BackendApiRepository(){}
    public static boolean isConfigured(Context context){return AccountRepository.signedIn(context);}
    public static String fetchLive(Context context) throws Exception{return AccountRepository.payload(context);}
    public static String fetchShadow(Context context) throws Exception{return fetchLive(context);}
}
