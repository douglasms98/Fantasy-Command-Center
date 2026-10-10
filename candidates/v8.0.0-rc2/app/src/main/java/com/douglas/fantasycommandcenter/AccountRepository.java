package com.douglas.fantasycommandcenter;

import android.content.Context;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import org.json.JSONObject;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.io.InputStream;
import java.io.ByteArrayOutputStream;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/** Firebase refresh credentials remain in encrypted native storage, outside the WebView. */
public final class AccountRepository {
    public static final String BASE="https://fcc-api-322688211348.southamerica-east1.run.app";
    private static final String PREFS="fcc_account_v8", ALIAS="fcc_account_aes_v8";
    private static long sessionGeneration=0;
    private AccountRepository(){}

    private static SecretKey key() throws Exception {
        KeyStore ks=KeyStore.getInstance("AndroidKeyStore");ks.load(null);
        if(!ks.containsAlias(ALIAS)){
            KeyGenerator kg=KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES,"AndroidKeyStore");
            kg.init(new KeyGenParameterSpec.Builder(ALIAS,KeyProperties.PURPOSE_ENCRYPT|KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build());kg.generateKey();
        }
        return (SecretKey)ks.getKey(ALIAS,null);
    }

    private static synchronized JSONObject read(Context c){
        try{
            String value=c.getSharedPreferences(PREFS,0).getString("session","");
            if(value.isEmpty())return new JSONObject();
            String[] parts=value.split(":");Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE,key(),new GCMParameterSpec(128,Base64.decode(parts[0],Base64.NO_WRAP)));
            return new JSONObject(new String(cipher.doFinal(Base64.decode(parts[1],Base64.NO_WRAP)),StandardCharsets.UTF_8));
        }catch(Exception e){return new JSONObject();}
    }

    private static synchronized void save(Context c,JSONObject result) throws Exception {
        String next=result.getJSONObject("user").getString("uid"),previous=uid(c);
        if(!next.equals(previous)){sessionGeneration++;clearPersonalData(c);}
        result.put("expiresAt",System.currentTimeMillis()+result.optLong("expiresIn",3600)*1000);
        Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");cipher.init(Cipher.ENCRYPT_MODE,key());
        String value=Base64.encodeToString(cipher.getIV(),Base64.NO_WRAP)+":"+Base64.encodeToString(cipher.doFinal(result.toString().getBytes(StandardCharsets.UTF_8)),Base64.NO_WRAP);
        c.getSharedPreferences(PREFS,0).edit().putString("session",value).commit();
    }

    public static String uid(Context c){JSONObject user=read(c).optJSONObject("user");return user==null?"":user.optString("uid","");}
    public static boolean signedIn(Context c){return !uid(c).isEmpty();}
    public static synchronized void logout(Context c){sessionGeneration++;c.getSharedPreferences(PREFS,0).edit().clear().commit();clearPersonalData(c);}
    public static void clearLegacyData(Context c){
        if(c.getSharedPreferences(SyncRepository.PREFS,0).getString("cache_user_uid","").isEmpty())clearPersonalData(c);
    }
    private static void clearPersonalData(Context c){
        FantasyNotificationScheduler.cancelAll(c,true);
        c.getSharedPreferences("fcc_notifications_v7",0).edit().clear().commit();
        android.app.NotificationManager nm=(android.app.NotificationManager)c.getSystemService(Context.NOTIFICATION_SERVICE);
        if(nm!=null)nm.cancelAll();
        android.content.SharedPreferences.Editor e=c.getSharedPreferences(SyncRepository.PREFS,0).edit();
        for(String name:new String[]{BackendApiRepository.KEY_CACHE,BackendApiRepository.KEY_LAST,SyncRepository.KEY_CACHE,SyncRepository.KEY_LAST,NewsRepository.KEY_CACHE,NflScheduleRepository.KEY_CACHE,NflScheduleRepository.KEY_LAST,"notification_events_derived","ui_state","cache_user_uid","sync_endpoint","sync_token","backend_api_key","backend_api_endpoint"})e.remove(name);
        e.commit();
    }

    private static JSONObject http(String method,String path,JSONObject body,String token) throws Exception {
        if(!java.util.Arrays.asList("GET","POST","PUT","DELETE").contains(method)||!path.startsWith("/v2/")||path.contains("..")||path.contains("?")||path.contains("#"))throw new IllegalArgumentException("Invalid path");
        HttpURLConnection h=(HttpURLConnection)new URL(BASE+path).openConnection();
        try{
            h.setInstanceFollowRedirects(false);h.setRequestMethod(method);h.setConnectTimeout(15000);h.setReadTimeout(180000);
            h.setRequestProperty("Accept","application/json");h.setRequestProperty("User-Agent","FCC-Android/8.0.0-rc2");
            if(token!=null&&!token.isEmpty())h.setRequestProperty("Authorization","Bearer "+token);
            if(body!=null){h.setDoOutput(true);h.setRequestProperty("Content-Type","application/json");try(java.io.OutputStream o=h.getOutputStream()){o.write(body.toString().getBytes(StandardCharsets.UTF_8));}}
            int code=h.getResponseCode();InputStream input=code>=200&&code<300?h.getInputStream():h.getErrorStream();ByteArrayOutputStream out=new ByteArrayOutputStream();
            if(input!=null)try(InputStream in=input){byte[] b=new byte[8192];int n;while((n=in.read(b))!=-1){out.write(b,0,n);if(out.size()>15_000_000)throw new IllegalStateException("Response too large");}}
            JSONObject result=new JSONObject(out.toString("UTF-8"));
            if(code<200||code>=300){String detail=result.optString("detail","API_UNAVAILABLE");throw new IllegalStateException(code+":"+detail);}
            return result;
        }finally{h.disconnect();}
    }

    private static JSONObject refresh(Context c) throws Exception {
        JSONObject saved;String oldUid;long generation;
        synchronized(AccountRepository.class){saved=read(c);oldUid=uid(c);generation=sessionGeneration;}
        String rt=saved.optString("refreshToken","");
        if(rt.isEmpty())throw new IllegalStateException("401:LOGIN_REQUIRED");
        JSONObject result;
        try{result=http("POST","/v2/auth/native/refresh",new JSONObject().put("refreshToken",rt),null);}
        catch(IllegalStateException e){
            synchronized(AccountRepository.class){if(e.getMessage().startsWith("401:")&&generation==sessionGeneration)logout(c);}
            throw e;
        }
        synchronized(AccountRepository.class){
            if(generation!=sessionGeneration||!oldUid.equals(uid(c)))throw new IllegalStateException("401:ACCOUNT_CHANGED");
            save(c,result);
        }
        return result;
    }

    public static JSONObject request(Context c,String method,String path,JSONObject body) throws Exception {
        if(!path.matches("/v2/(me|leagues|sync|app-payload|nfl-schedule|auth/(login|register|logout|refresh|reset|verify-email)|leagues/[a-f0-9]{32}(/sync)?)"))throw new IllegalStateException("400:INVALID_REQUEST");
        if(path.equals("/v2/auth/logout")){logout(c);return new JSONObject().put("ok",true);}
        if(path.equals("/v2/auth/login")||path.equals("/v2/auth/register")){
            long generation; synchronized(AccountRepository.class){generation=sessionGeneration;}
            JSONObject result=http(method,path.replace("/auth/","/auth/native/"),body,null);
            synchronized(AccountRepository.class){
                if(generation!=sessionGeneration)throw new IllegalStateException("401:ACCOUNT_CHANGED");
                save(c,result);
            }
            return new JSONObject().put("ok",true).put("user",result.getJSONObject("user"));
        }
        if(path.equals("/v2/auth/reset"))return http(method,path,body,null);
        if(path.equals("/v2/auth/refresh")){JSONObject r=refresh(c);return new JSONObject().put("ok",true).put("user",r.getJSONObject("user"));}
        JSONObject saved=read(c);if(saved.optLong("expiresAt",0)<System.currentTimeMillis()+120000)saved=refresh(c);
        String account=uid(c);JSONObject result;
        try{result=http(method,path,body,saved.getString("idToken"));}
        catch(IllegalStateException e){if(!e.getMessage().startsWith("401:"))throw e; saved=refresh(c);result=http(method,path,body,saved.getString("idToken"));}
        if(!account.equals(uid(c)))throw new IllegalStateException("401:ACCOUNT_CHANGED");
        if(method.equals("GET")&&path.equals("/v2/app-payload"))cachePayload(c,result);
        return result;
    }

    private static void cachePayload(Context c,JSONObject response) throws Exception {
        String account=uid(c);
        if(!account.equals(response.optString("userId")))throw new IllegalStateException("401:ACCOUNT_MISMATCH");
        synchronized(AccountRepository.class){
            if(!account.equals(uid(c)))throw new IllegalStateException("401:ACCOUNT_CHANGED");
            c.getSharedPreferences(SyncRepository.PREFS,0).edit().putString(BackendApiRepository.KEY_CACHE,response.toString()).putString(BackendApiRepository.KEY_LAST,response.optString("generatedAt")).putString("cache_user_uid",account).commit();
            NotificationEventRepository.refreshFromCaches(c);
        }
    }

    public static String payload(Context c) throws Exception {
        return request(c,"GET","/v2/app-payload",null).toString();
    }
}
