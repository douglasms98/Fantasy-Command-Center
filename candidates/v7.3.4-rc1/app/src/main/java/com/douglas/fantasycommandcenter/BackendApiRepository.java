package com.douglas.fantasycommandcenter;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.time.Instant;

/**
 * Operational Cloud Run client for FCC.
 *
 * The legacy SharedPreferences key names are intentionally preserved so an
 * already-configured installation keeps its API endpoint/key/cache after the
 * v7.2 update. The old fetchShadow() method remains as a compatibility alias.
 */
public final class BackendApiRepository {
    public static final String KEY_ENDPOINT = "backend_api_endpoint";
    public static final String KEY_TOKEN = "backend_api_key";
    public static final String KEY_CACHE = "backend_shadow_cache";
    public static final String KEY_LAST = "backend_shadow_last";

    public static final String DEFAULT_ENDPOINT =
            "https://fcc-api-322688211348.southamerica-east1.run.app";

    private static final String[] LEAGUES = {"sleeper1", "sleeper2", "espn1"};

    private BackendApiRepository() {}

    public static void saveConfig(Context context, String endpoint, String token) {
        SharedPreferences p = context.getSharedPreferences(SyncRepository.PREFS, Context.MODE_PRIVATE);
        p.edit()
                .putString(KEY_ENDPOINT, cleanBase(endpoint))
                .putString(KEY_TOKEN, token == null ? "" : token.trim())
                .apply();
    }

    public static boolean isConfigured(Context context) {
        SharedPreferences p = context.getSharedPreferences(SyncRepository.PREFS, Context.MODE_PRIVATE);
        String token = p.getString(KEY_TOKEN, "");
        return token != null && !token.trim().isEmpty();
    }

    public static String fetchLive(Context context) throws Exception {
        SharedPreferences p = context.getSharedPreferences(SyncRepository.PREFS, Context.MODE_PRIVATE);

        String endpoint = p.getString(KEY_ENDPOINT, DEFAULT_ENDPOINT);
        if (endpoint == null || endpoint.trim().isEmpty()) endpoint = DEFAULT_ENDPOINT;
        endpoint = cleanBase(endpoint);

        String token = p.getString(KEY_TOKEN, "");
        if (token == null || token.trim().isEmpty()) {
            throw new IllegalStateException("Chave da API FCC não configurada.");
        }

        JSONObject health = getJson(endpoint + "/health", null);
        JSONObject sourcesResponse = getJson(endpoint + "/v1/sources", token);

        JSONArray normalized = new JSONArray();
        for (String id : LEAGUES) {
            JSONObject raw = getJson(endpoint + "/v1/leagues/" + id, token);
            JSONObject league = raw.optJSONObject("league");
            normalized.put(league != null ? league : raw);
        }

        JSONObject backend = new JSONObject();
        backend.put("mode", "live-overlay");
        backend.put("transport", "cloud-run");
        backend.put("endpoint", endpoint);
        backend.put("contract", "fcc-normalized-v1");
        backend.put("health", health);

        JSONObject payload = new JSONObject();
        payload.put("ok", true);
        payload.put("schema", "fcc-backend-live-v1");
        payload.put("generatedAt", Instant.now().toString());
        payload.put("primaryDataUntouched", false);
        payload.put("backend", backend);
        payload.put("sources", sourcesResponse.optJSONArray("sources") != null
                ? sourcesResponse.optJSONArray("sources")
                : new JSONArray());
        payload.put("normalizedLeagues", normalized);

        String out = payload.toString();
        p.edit()
                .putString(KEY_CACHE, out)
                .putString(KEY_LAST, payload.optString("generatedAt", ""))
                .apply();

        NotificationEventRepository.refreshFromCaches(context);
        return out;
    }

    /** Compatibility alias for v7.0/v7.1 HTML and existing installs. */
    public static String fetchShadow(Context context) throws Exception {
        return fetchLive(context);
    }

    private static JSONObject getJson(String url, String token) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        try {
            c.setRequestMethod("GET");
            c.setConnectTimeout(12000);
            c.setReadTimeout(25000);
            c.setRequestProperty("Accept", "application/json");
            c.setRequestProperty("User-Agent", "FCC-Android/7.3.2-cloud-first");
            if (token != null && !token.trim().isEmpty()) {
                c.setRequestProperty("X-FCC-Key", token.trim());
            }

            int code = c.getResponseCode();
            InputStream stream = code >= 200 && code < 300 ? c.getInputStream() : c.getErrorStream();
            String body = readAll(stream);

            if (code < 200 || code >= 300) {
                throw new IllegalStateException("API HTTP " + code + ": " + compact(body));
            }
            return new JSONObject(body);
        } finally {
            c.disconnect();
        }
    }

    private static String readAll(InputStream in) throws Exception {
        if (in == null) return "";
        try (BufferedReader r = new BufferedReader(new InputStreamReader(in, StandardCharsets.UTF_8))) {
            StringBuilder b = new StringBuilder();
            String line;
            while ((line = r.readLine()) != null) b.append(line);
            return b.toString();
        }
    }

    private static String cleanBase(String endpoint) {
        String s = endpoint == null ? "" : endpoint.trim();
        while (s.endsWith("/")) s = s.substring(0, s.length() - 1);
        return s.isEmpty() ? DEFAULT_ENDPOINT : s;
    }

    private static String compact(String body) {
        if (body == null) return "";
        String s = body.replace('\n', ' ').replace('\r', ' ').trim();
        return s.length() > 260 ? s.substring(0, 260) + "…" : s;
    }
}
