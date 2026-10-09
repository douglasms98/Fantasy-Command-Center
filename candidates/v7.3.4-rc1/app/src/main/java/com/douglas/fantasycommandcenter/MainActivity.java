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

    @Override
    public void onCreate(Bundle b) {
        super.onCreate(b);
        SyncRepository.migrateLegacyConfig(this);
        prefs = getSharedPreferences(SyncRepository.PREFS, MODE_PRIVATE);

        getWindow().setStatusBarColor(Color.rgb(9, 17, 30));
        getWindow().setNavigationBarColor(Color.rgb(9, 17, 30));

        web = new WebView(this);
        web.setBackgroundColor(Color.rgb(9, 17, 30));
        setContentView(web);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setAllowFileAccess(true);
        s.setAllowContentAccess(true);
        s.setCacheMode(WebSettings.LOAD_DEFAULT);
        s.setMediaPlaybackRequiresUserGesture(true);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);

        web.addJavascriptInterface(new AndroidSyncBridge(), "AndroidSync");
        web.setWebChromeClient(new WebChromeClient());
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest r) {
                Uri u = r.getUrl();
                if ("file".equals(u.getScheme())) return false;
                startActivity(new Intent(Intent.ACTION_VIEW, u));
                return true;
            }
        });

        if (b != null) web.restoreState(b);
        else web.loadUrl("file:///android_asset/fcc/index.html");

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
        runOnUiThread(() -> web.evaluateJavascript(code, null));
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
        public String getEndpoint() {
            return prefs.getString(SyncRepository.KEY_ENDPOINT, "");
        }

        @JavascriptInterface
        public String getToken() {
            return prefs.getString(SyncRepository.KEY_TOKEN, "");
        }

        @JavascriptInterface
        public String getBackendEndpoint() {
            return prefs.getString(BackendApiRepository.KEY_ENDPOINT, BackendApiRepository.DEFAULT_ENDPOINT);
        }

        @JavascriptInterface
        public String getBackendKey() {
            return prefs.getString(BackendApiRepository.KEY_TOKEN, "");
        }

        @JavascriptInterface
        public String getCachedBackendShadow() {
            return prefs.getString(BackendApiRepository.KEY_CACHE, "");
        }

        @JavascriptInterface
        public String getLastBackendShadow() {
            return prefs.getString(BackendApiRepository.KEY_LAST, "");
        }

        @JavascriptInterface
        public void saveBackendConfig(String endpoint, String token) {
            BackendApiRepository.saveConfig(MainActivity.this, endpoint, token);
            js("window.FCCNative&&FCCNative.onBackendConfigSaved&&FCCNative.onBackendConfigSaved()");
        }

        @JavascriptInterface
        public void saveConfig(String endpoint, String token) {
            prefs.edit()
                    .putString(SyncRepository.KEY_ENDPOINT, endpoint == null ? "" : endpoint.trim())
                    .putString(SyncRepository.KEY_TOKEN, token == null ? "" : token.trim())
                    .apply();
            PeriodicSyncWorker.ensure(MainActivity.this);
            js("window.FCCNative&&FCCNative.onConfigSaved&&FCCNative.onConfigSaved()");
        }

        @JavascriptInterface
        public String getCachedPayload() {
            return prefs.getString(SyncRepository.KEY_CACHE, "");
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
            return prefs.getString("ui_state", "");
        }

        @JavascriptInterface
        public void saveUiState(String raw) {
            prefs.edit().putString("ui_state", raw == null ? "" : raw).apply();
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
            FantasyNotificationScheduler.schedule(MainActivity.this, json);
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
            return prefs.getString(NewsRepository.KEY_CACHE, "");
        }

        @JavascriptInterface
        public void translateNewsTitles(String newsJson) {
            executor.execute(() -> {
                String body=NewsTranslationRepository.translate(MainActivity.this,newsJson);
                String b64=Base64.encodeToString(body.getBytes(StandardCharsets.UTF_8),Base64.NO_WRAP);
                js("window.FCCNative&&FCCNative.onNewsTitlesPtFromBase64&&FCCNative.onNewsTitlesPtFromBase64('"+b64+"')");
            });
        }

        @JavascriptInterface
        public void fetchNews(String playersJson) {
            executor.execute(() -> {
                try {
                    String body = NewsRepository.fetch(MainActivity.this, playersJson);
                    String b64 = Base64.encodeToString(body.getBytes(StandardCharsets.UTF_8), Base64.NO_WRAP);
                    js("window.FCCNative&&FCCNative.onNativeNewsFromBase64&&FCCNative.onNativeNewsFromBase64('" + b64 + "')");
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
            executor.execute(() -> {
                try {
                    String body = NflScheduleRepository.fetch(MainActivity.this, startWeek);
                    callbackNflSchedule(body);
                } catch (Exception ignored) {
                    // Keep last valid schedule cache and UI fallback.
                }
            });
        }

        @JavascriptInterface
        public void syncNow() {
            js("window.FCCNative&&FCCNative.onSyncStarted('Atualizando backup de compatibilidade...')");
            executor.execute(() -> {
                try {
                    String body = SyncRepository.sync(MainActivity.this);
                    callbackPayload(body);
                } catch (Exception e) {
                    String msg = e.getMessage() == null ? e.toString() : e.getMessage();
                    String enc = Base64.encodeToString(msg.getBytes(StandardCharsets.UTF_8), Base64.NO_WRAP);
                    js("window.FCCNative&&FCCNative.onSyncError(new TextDecoder().decode(Uint8Array.from(atob('" + enc + "'),c=>c.charCodeAt(0))))");
                }
            });
        }

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
