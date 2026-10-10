package com.douglas.fantasycommandcenter;

import android.Manifest;
import android.app.Activity;
import android.app.AlarmManager;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.util.Base64;
import android.view.View;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends Activity {
    private WebView web;
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private android.content.SharedPreferences prefs;
    private GoogleLogin googleLogin;

    @Override
    public void onCreate(Bundle b) {
        super.onCreate(b);
        AccountRepository.clearLegacyData(this);
        prefs = getSharedPreferences(SyncRepository.PREFS, MODE_PRIVATE);
        googleLogin=new GoogleLogin(this,executor,this::accountResult);

        getWindow().setStatusBarColor(Color.rgb(9, 17, 30));
        getWindow().setNavigationBarColor(Color.rgb(9, 17, 30));

        web = new WebView(this);
        web.setBackgroundColor(Color.rgb(9, 17, 30));
        setContentView(web);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        s.setCacheMode(WebSettings.LOAD_DEFAULT);
        s.setMediaPlaybackRequiresUserGesture(true);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);

        web.addJavascriptInterface(new AndroidSyncBridge(), "AndroidSync");
        web.setWebChromeClient(new WebChromeClient());
        final androidx.webkit.WebViewAssetLoader assetLoader=new androidx.webkit.WebViewAssetLoader.Builder()
            .addPathHandler("/assets/",new androidx.webkit.WebViewAssetLoader.AssetsPathHandler(this)).build();
        web.setWebViewClient(new WebViewClient() {
            @Override public android.webkit.WebResourceResponse shouldInterceptRequest(WebView v, WebResourceRequest r){return assetLoader.shouldInterceptRequest(r.getUrl());}
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest r) {
                Uri u = r.getUrl();
                if ("https".equals(u.getScheme()) && "appassets.androidplatform.net".equals(u.getHost()) && u.getPath().startsWith("/assets/fcc/")) return false;
                if(!"https".equals(u.getScheme())&&!"http".equals(u.getScheme()))return true;
                startActivity(new Intent(Intent.ACTION_VIEW, u));
                return true;
            }
        });

        web.loadUrl("https://appassets.androidplatform.net/assets/fcc/index.html");

        FantasyNotificationScheduler.ensureChannel(this);
        PeriodicSyncWorker.ensure(this);
        requestNotificationPermission();
    }

    private void requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= 33 &&
                checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 1001);
        }
    }

    private void requestExactAlarmPermissionNative() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S || FantasyNotificationScheduler.canScheduleExact(this)) return;
        try {
            Intent intent = new Intent(Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM);
            intent.setData(Uri.parse("package:" + getPackageName()));
            startActivity(intent);
        } catch (Exception ignored) {
            try {
                startActivity(new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:" + getPackageName())));
            } catch (Exception ignoredAgain) {}
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        // The HTML visibility/focus hooks refresh the API and news. Reschedule alarms
        // here as an extra recovery layer after system/app lifecycle changes.
        FantasyNotificationScheduler.rescheduleSaved(this);
        if(web!=null)js("window.FCCNative&&FCCNative.onBackgroundCacheChanged&&FCCNative.onBackgroundCacheChanged()");
    }

    @Override
    protected void onSaveInstanceState(Bundle out) {
        web.saveState(out);
        super.onSaveInstanceState(out);
    }

    @Override
    protected void onDestroy() {
        if(googleLogin!=null)googleLogin.cancel();
        executor.shutdownNow();
        web.destroy();
        super.onDestroy();
    }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }

    private void js(String code) {
        runOnUiThread(() -> {if(web!=null&&!isDestroyed())web.evaluateJavascript(code, null);});
    }

    private void accountResult(String requestId,org.json.JSONObject result){
        String b64=Base64.encodeToString(result.toString().getBytes(StandardCharsets.UTF_8),Base64.NO_WRAP);
        js("window.FCCAccount&&FCCAccount.nativeResult('"+requestId+"','"+b64+"')");
    }

    private void callbackPayload(String payload) {
        String b64 = Base64.encodeToString(payload.getBytes(StandardCharsets.UTF_8), Base64.NO_WRAP);
        js("window.FCCNative&&FCCNative.onSyncSuccessFromBase64('" + b64 + "')");
    }

    private void callbackBackendPayload(String payload) {
        String b64 = Base64.encodeToString(payload.getBytes(StandardCharsets.UTF_8), Base64.NO_WRAP);
        js("window.FCCNative&&FCCNative.onBackendSuccessFromBase64&&FCCNative.onBackendSuccessFromBase64('" + b64 + "')");
    }

    private void callbackBackendError(String message) {
        String msg = message == null ? "Falha na API FCC" : message;
        String b64 = Base64.encodeToString(msg.getBytes(StandardCharsets.UTF_8), Base64.NO_WRAP);
        js("window.FCCNative&&FCCNative.onBackendError&&FCCNative.onBackendError(new TextDecoder().decode(Uint8Array.from(atob('" + b64 + "'),c=>c.charCodeAt(0))))");
    }

    private void callbackNflSchedule(String payload) {
        String b64 = Base64.encodeToString(payload.getBytes(StandardCharsets.UTF_8), Base64.NO_WRAP);
        js("window.FCCNative&&FCCNative.onNflScheduleFromBase64&&FCCNative.onNflScheduleFromBase64('" + b64 + "')");
    }

    public final class AndroidSyncBridge {
        @JavascriptInterface
        public void accountRequest(String requestId,String method,String path,String body){
            if(!requestId.matches("[A-Za-z0-9_-]{1,80}"))return;
            if(path.equals("/v2/auth/logout")){
                // Invalidate pending authentication immediately, before queued HTTP completes.
                AccountRepository.logout(MainActivity.this);
                runOnUiThread(()->googleLogin.clearState());
                org.json.JSONObject result=new org.json.JSONObject();
                try{result.put("ok",true);}catch(Exception ignored){}
                accountResult(requestId,result);return;
            }
            executor.submit(()->{
                org.json.JSONObject result;
                try{result=AccountRepository.request(MainActivity.this,method,path,body==null||body.isEmpty()?null:new org.json.JSONObject(body));}
                catch(Exception e){result=new org.json.JSONObject();try{result.put("ok",false).put("error",e.getMessage()!=null&&e.getMessage().matches("[0-9]{3}:[A-Z_]+")?e.getMessage():"API_UNAVAILABLE");}catch(Exception ignored){}}
                accountResult(requestId,result);
            });
        }

        @JavascriptInterface
        public void signInWithGoogle(String requestId,boolean link){
            runOnUiThread(()->googleLogin.start(requestId,link));
        }

        @JavascriptInterface
        public String getEndpoint() {
            return "";
        }

        @JavascriptInterface
        public String getToken() {
            return "";
        }

        @JavascriptInterface
        public String getBackendEndpoint() {
            return AccountRepository.BASE;
        }

        @JavascriptInterface
        public String getBackendKey() {
            return "";
        }

        @JavascriptInterface
        public String getCachedBackendShadow() {
            return AccountRepository.uid(MainActivity.this).equals(prefs.getString("cache_user_uid","")) && AccountRepository.signedIn(MainActivity.this) ? prefs.getString(BackendApiRepository.KEY_CACHE, "") : "";
        }

        @JavascriptInterface
        public String getLastBackendShadow() {
            return prefs.getString(BackendApiRepository.KEY_LAST, "");
        }

        @JavascriptInterface
        public void saveBackendConfig(String endpoint, String token) {
            // Account login owns configuration. Shared keys are no longer accepted.
            js("window.FCCNative&&FCCNative.onBackendConfigSaved&&FCCNative.onBackendConfigSaved()");
        }

        @JavascriptInterface
        public void saveConfig(String endpoint, String token) { }

        @JavascriptInterface
        public String getCachedPayload() {
            return "";
        }

        @JavascriptInterface
        public String getLastSync() {
            return prefs.getString(SyncRepository.KEY_LAST, "");
        }

        @JavascriptInterface
        public void clearCache() {
            prefs.edit()
                    .remove(SyncRepository.KEY_CACHE)
                    .remove(SyncRepository.KEY_LAST)
                    .apply();
            js("window.FCCNative&&FCCNative.onCacheCleared&&FCCNative.onCacheCleared()");
        }

        @JavascriptInterface
        public String getUiState() {
            return prefs.getString("ui_state_"+AccountRepository.uid(MainActivity.this), "");
        }

        @JavascriptInterface
        public void saveUiState(String raw) {
            prefs.edit().putString("ui_state_"+AccountRepository.uid(MainActivity.this), raw == null ? "" : raw).apply();
        }

        @JavascriptInterface
        public void setTheme(String theme) {
            String normalized = theme == null ? "semi-dark" : theme.trim().toLowerCase();
            final boolean light = "light".equals(normalized);
            final boolean fullDark = "full-dark".equals(normalized) || "amoled".equals(normalized);
            final int bg = light ? Color.rgb(242, 245, 250)
                    : fullDark ? Color.BLACK
                    : Color.rgb(9, 17, 30);

            prefs.edit()
                    .putBoolean("light_theme", light)
                    .putString("fcc_theme_native", fullDark ? "full-dark" : light ? "light" : "semi-dark")
                    .apply();

            runOnUiThread(() -> {
                getWindow().setStatusBarColor(bg);
                getWindow().setNavigationBarColor(bg);
                if (web != null) web.setBackgroundColor(bg);

                int f = getWindow().getDecorView().getSystemUiVisibility();
                if (Build.VERSION.SDK_INT >= 23) {
                    if (light) f |= View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR;
                    else f &= ~View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR;
                }
                if (Build.VERSION.SDK_INT >= 26) {
                    if (light) f |= View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
                    else f &= ~View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
                }
                getWindow().getDecorView().setSystemUiVisibility(f);
            });
        }

        // Compatibilidade com HTMLs antigos que enviavam apenas claro/escuro.
        @JavascriptInterface
        public void setLightTheme(boolean light) {
            setTheme(light ? "light" : "semi-dark");
        }

        @JavascriptInterface
        public boolean notificationsEnabled() {
            return prefs.getBoolean("notifications_enabled", true);
        }

        @JavascriptInterface
        public void setNotificationsEnabled(boolean enabled) {
            prefs.edit().putBoolean("notifications_enabled", enabled).apply();
            if (enabled) {
                FantasyNotificationScheduler.rescheduleSaved(MainActivity.this);
                runOnUiThread(() -> {
                    requestNotificationPermission();
                    requestExactAlarmPermissionNative();
                });
            } else {
                FantasyNotificationScheduler.cancelAll(MainActivity.this, false);
            }
        }

        @JavascriptInterface
        public void scheduleNotifications(String json) {
            try{
                org.json.JSONObject envelope=new org.json.JSONObject(json);
                org.json.JSONArray events=envelope.getJSONArray("events");
                FantasyNotificationScheduler.schedule(MainActivity.this,events.toString(),envelope.optString("userId",""));
            }catch(Exception ignored){}
        }

        @JavascriptInterface
        public void scheduleNotificationEvents(String json) {
            scheduleNotifications(json);
        }

        @JavascriptInterface
        public void requestExactAlarmPermission() {
            runOnUiThread(MainActivity.this::requestExactAlarmPermissionNative);
        }

        @JavascriptInterface
        public String getNotificationEvents() {
            return prefs.getString("notification_events_derived", "[]");
        }

        @JavascriptInterface
        public String notificationDiagnostics() {
            return FantasyNotificationScheduler.diagnostics(MainActivity.this);
        }

        @JavascriptInterface
        public void testNotification() {
            runOnUiThread(() -> {
                requestNotificationPermission();
                requestExactAlarmPermissionNative();
            });
            FantasyNotificationScheduler.scheduleTest(MainActivity.this, 8000L);
        }

        @JavascriptInterface
        public String getCachedNews() {
            return AccountRepository.signedIn(MainActivity.this) ? prefs.getString(NewsRepository.KEY_CACHE, "") : "";
        }

        @JavascriptInterface
        public void translateNewsTitles(String newsJson) {
            final String accountUid=AccountRepository.uid(MainActivity.this);if(accountUid.isEmpty())return;
            executor.execute(() -> {
                String body=NewsTranslationRepository.translate(MainActivity.this,newsJson);
                String b64=Base64.encodeToString(body.getBytes(StandardCharsets.UTF_8),Base64.NO_WRAP);
                js("window.FCCAccount&&FCCAccount.user&&FCCAccount.user.uid==="+org.json.JSONObject.quote(accountUid)+"&&window.FCCNative&&FCCNative.onNewsTitlesPtFromBase64&&FCCNative.onNewsTitlesPtFromBase64('"+b64+"')");
            });
        }

        @JavascriptInterface
        public void fetchNews(String playersJson) {
            final String accountUid=AccountRepository.uid(MainActivity.this);if(accountUid.isEmpty())return;
            executor.execute(() -> {
                try {
                    String body = NewsRepository.fetch(MainActivity.this, playersJson);
                    String b64 = Base64.encodeToString(body.getBytes(StandardCharsets.UTF_8), Base64.NO_WRAP);
                    js("window.FCCAccount&&FCCAccount.user&&FCCAccount.user.uid==="+org.json.JSONObject.quote(accountUid)+"&&window.FCCNative&&FCCNative.onNativeNewsFromBase64&&FCCNative.onNativeNewsFromBase64('" + b64 + "')");
                } catch (Exception ignored) {
                    // Keep previous valid cache.
                }
            });
        }

        @JavascriptInterface
        public String getCachedNflSchedule() {
            return prefs.getString(NflScheduleRepository.KEY_CACHE, "");
        }

        @JavascriptInterface
        public String getLastNflSchedule() {
            return prefs.getString(NflScheduleRepository.KEY_LAST, "");
        }

        @JavascriptInterface
        public void fetchNflSchedule(int startWeek) {
            final String accountUid=AccountRepository.uid(MainActivity.this);if(accountUid.isEmpty())return;
            executor.execute(() -> {
                try {
                    String body = NflScheduleRepository.fetch(MainActivity.this, startWeek);
                    if(accountUid.equals(AccountRepository.uid(MainActivity.this)))callbackNflSchedule(body);
                } catch (Exception ignored) {
                    // Keep last valid schedule cache and UI fallback.
                }
            });
        }

        @JavascriptInterface
        public void syncNow() { backendNow(); }

        @JavascriptInterface
        public void backendNow() {
            js("window.FCCNative&&FCCNative.onBackendStarted&&FCCNative.onBackendStarted('Atualizando API FCC...')");
            executor.execute(() -> {
                try {
                    String body = BackendApiRepository.fetchLive(MainActivity.this);
                    callbackBackendPayload(body);
                } catch (Exception e) {
                    callbackBackendError(e.getMessage() == null ? e.toString() : e.getMessage());
                }
            });
        }

        /** Compatibility alias for the installed v7.0/v7.1 HTML contract. */
        @JavascriptInterface
        public void backendShadowNow() {
            backendNow();
        }
    }
}
