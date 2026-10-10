package com.douglas.fantasycommandcenter;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Locale;
import java.util.Map;

public final class SyncRepository {

    public static final String PREFS = "fcc_native";
    public static final String KEY_ENDPOINT = "sync_endpoint";
    public static final String KEY_TOKEN = "sync_token";
    public static final String KEY_CACHE = "cached_payload";
    public static final String KEY_LAST = "last_sync";

    private SyncRepository() {
    }

    public static boolean migrateLegacyConfig(Context context) {
        SharedPreferences target = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        String ep = target.getString(KEY_ENDPOINT, "");
        String tk = target.getString(KEY_TOKEN, "");

        if (isEndpoint(ep) && tk != null && !tk.trim().isEmpty()) return false;

        String foundEndpoint = isEndpoint(ep) ? ep : "";
        String foundToken = tk == null ? "" : tk.trim();

        try {
            File dir = new File(context.getApplicationInfo().dataDir, "shared_prefs");
            File[] files = dir.listFiles((d, n) -> n.endsWith(".xml"));

            if (files != null) {
                for (File f : files) {
                    String name = f.getName().substring(0, f.getName().length() - 4);
                    SharedPreferences legacy = context.getSharedPreferences(name, Context.MODE_PRIVATE);
                    Map<String, ?> all = legacy.getAll();
                    if (all == null) continue;

                    String localEndpoint = "";
                    String localToken = "";

                    for (Map.Entry<String, ?> e : all.entrySet()) {
                        if (!(e.getValue() instanceof String)) continue;
                        String key = e.getKey() == null ? "" : e.getKey().toLowerCase(Locale.ROOT);
                        String val = ((String) e.getValue()).trim();
                        if (isEndpoint(val)) localEndpoint = val;
                        if (isLikelyToken(key, val)) localToken = val;
                    }

                    if (foundEndpoint.isEmpty() && !localEndpoint.isEmpty()) foundEndpoint = localEndpoint;
                    if (foundToken.isEmpty() && !localToken.isEmpty() &&
                            (!localEndpoint.isEmpty() ||
                                    name.toLowerCase(Locale.ROOT).contains("fcc") ||
                                    name.toLowerCase(Locale.ROOT).contains("fantasy"))) {
                        foundToken = localToken;
                    }

                    if (!foundEndpoint.isEmpty() && !foundToken.isEmpty()) break;
                }
            }
        } catch (Exception ignored) {
        }

        boolean changed = false;
        SharedPreferences.Editor ed = target.edit();

        if (!foundEndpoint.isEmpty() && !isEndpoint(ep)) {
            ed.putString(KEY_ENDPOINT, foundEndpoint);
            changed = true;
        }

        if (!foundToken.isEmpty() && (tk == null || tk.trim().isEmpty())) {
            ed.putString(KEY_TOKEN, foundToken);
            changed = true;
        }

        if (changed) ed.apply();
        return changed;
    }

    private static boolean isEndpoint(String value) {
        if (value == null) return false;
        String v = value.trim();
        return v.startsWith("https://script.google.com/macros/s/") && v.contains("/exec");
    }

    private static boolean isLikelyToken(String key, String value) {
        if (value == null) return false;
        String x = value.trim();
        if (x.length() < 24 || x.length() > 256 || x.startsWith("http")) return false;

        String k = key == null ? "" : key.toLowerCase(Locale.ROOT);
        boolean named = k.contains("token") || k.contains("sync_key") || k.contains("synckey") ||
                k.equals("key") || k.contains("api_key");
        boolean shape = x.matches("[A-Za-z0-9_-]{24,256}");
        return named && shape;
    }

    public static String sync(Context context) throws Exception {
        SharedPreferences p = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        String endpoint = p.getString(KEY_ENDPOINT, "");
        String token = p.getString(KEY_TOKEN, "");

        if (endpoint == null || endpoint.trim().isEmpty()) {
            throw new IllegalStateException("Endpoint de sincronização não configurado.");
        }

        endpoint = endpoint.trim();
        String sep = endpoint.contains("?") ? "&" : "?";
        String urlString = endpoint + sep + "key=" +
                URLEncoder.encode(token == null ? "" : token, StandardCharsets.UTF_8.name()) +
                "&t=" + System.currentTimeMillis();

        URL url = new URL(urlString);
        HttpURLConnection c = (HttpURLConnection) url.openConnection();
        c.setConnectTimeout(15000);
        c.setReadTimeout(30000);
        c.setRequestMethod("GET");
        c.setUseCaches(false);
        c.setRequestProperty("Accept", "application/json");

        try {
            int code = c.getResponseCode();
            InputStream in = code >= 200 && code < 300 ? c.getInputStream() : c.getErrorStream();
            String body = read(in);

            if (code < 200 || code >= 300) {
                throw new IOException("HTTP " + code + ": " + body);
            }

            JSONObject j = new JSONObject(body);
            if (!j.optBoolean("ok", false)) {
                throw new IOException(j.optString("error", "Resposta inválida do servidor"));
            }

            String now = j.optString("generatedAt", Instant.now().toString());
            p.edit().putString(KEY_CACHE, body).putString(KEY_LAST, now).apply();

            NotificationEventRepository.refreshFromCaches(context);
            return body;
        } finally {
            c.disconnect();
        }
    }

    private static void scheduleNotificationsFromPayload(
            Context context,
            SharedPreferences prefs,
            JSONObject payload
    ) {
        if (context == null || prefs == null || payload == null) return;

        try {
            if (!prefs.getBoolean("notifications_enabled", true)) return;

            JSONArray events = payload.optJSONArray("notificationEvents");
            if (events == null) return;

            FantasyNotificationScheduler.schedule(context, events.toString());
        } catch (Exception ignored) {
            // Falha no agendamento nunca deve derrubar a sincronização principal.
        }
    }

    private static String read(InputStream in) throws IOException {
        if (in == null) return "";

        try (BufferedReader br = new BufferedReader(
                new InputStreamReader(in, StandardCharsets.UTF_8))) {
            StringBuilder sb = new StringBuilder();
            String line;
            while ((line = br.readLine()) != null) sb.append(line);
            return sb.toString();
        }
    }
}
