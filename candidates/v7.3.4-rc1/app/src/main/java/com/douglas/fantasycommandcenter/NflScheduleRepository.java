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

public final class NflScheduleRepository {
    public static final String KEY_CACHE = "nfl_schedule_cache_v728";
    public static final String KEY_LAST = "nfl_schedule_last_v728";
    private static final String BASE = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard";

    private NflScheduleRepository() {}

    public static String fetch(Context context, int startWeek) throws Exception {
        // Busca também a semana anterior para detectar fechamento/virada sem depender
        // da plataforma de fantasy, e três semanas à frente para o planner.
        int current = startWeek;
        if(current<=0) {
            JSONObject currentBoard=getJson(BASE);
            JSONObject currentWeek=currentBoard.optJSONObject("week");
            current=currentWeek==null?0:currentWeek.optInt("number",0);
            if(current<=0)throw new IllegalStateException("Semana NFL atual não confirmada");
        }
        int requested = Math.max(1, Math.min(18, current));
        int first = Math.max(1, requested - 1);
        int last = Math.min(18, requested + 3);
        JSONArray weeks = new JSONArray();
        int successfulWeeks = 0;

        for (int week = first; week <= last; week++) {
            try {
                JSONObject raw = getJson(BASE + "?dates=2026&seasontype=2&week=" + week);
                JSONObject normalized = normalizeWeek(raw, week);
                weeks.put(normalized);
                successfulWeeks++;
            } catch (Exception ignored) {
                // A partial refresh is still useful. Missing weeks are filled by the HTML fallback.
            }
        }

        if (successfulWeeks == 0) {
            SharedPreferences p = context.getSharedPreferences(SyncRepository.PREFS, Context.MODE_PRIVATE);
            String cached = p.getString(KEY_CACHE, "");
            if (cached != null && !cached.trim().isEmpty()) return cached;
            throw new IllegalStateException("NFL schedule unavailable");
        }

        JSONObject payload = new JSONObject();
        payload.put("ok", true);
        payload.put("season", 2026);
        payload.put("requestedWeek", requested);
        payload.put("startWeek", first);
        payload.put("endWeek", last);
        payload.put("generatedAt", Instant.now().toString());
        payload.put("successfulWeeks", successfulWeeks);
        payload.put("weeks", weeks);

        String out = payload.toString();
        context.getSharedPreferences(SyncRepository.PREFS, Context.MODE_PRIVATE)
                .edit()
                .putString(KEY_CACHE, out)
                .putString(KEY_LAST, payload.optString("generatedAt", ""))
                .apply();
        NotificationEventRepository.refreshFromCaches(context);
        return out;
    }

    private static JSONObject normalizeWeek(JSONObject raw, int week) throws Exception {
        JSONObject out = new JSONObject();
        out.put("week", week);
        out.put("source", "ESPN NFL scoreboard");
        JSONArray games = new JSONArray();
        JSONArray events = raw.optJSONArray("events");
        if (events == null) events = new JSONArray();

        for (int i = 0; i < events.length(); i++) {
            JSONObject e = events.optJSONObject(i);
            if (e == null) continue;
            JSONObject comp = null;
            JSONArray comps = e.optJSONArray("competitions");
            if (comps != null && comps.length() > 0) comp = comps.optJSONObject(0);
            if (comp == null) continue;

            String home = "", away = "";
            JSONArray competitors = comp.optJSONArray("competitors");
            if (competitors != null) {
                for (int j = 0; j < competitors.length(); j++) {
                    JSONObject c = competitors.optJSONObject(j);
                    if (c == null) continue;
                    JSONObject team = c.optJSONObject("team");
                    String code = team == null ? "" : normalizeCode(team.optString("abbreviation", ""));
                    if ("home".equalsIgnoreCase(c.optString("homeAway"))) home = code;
                    else if ("away".equalsIgnoreCase(c.optString("homeAway"))) away = code;
                }
            }
            if (home.isEmpty() || away.isEmpty()) continue;

            JSONObject status = e.optJSONObject("status");
            JSONObject type = status == null ? null : status.optJSONObject("type");
            String state = type == null ? "" : type.optString("state", "");
            String detail = type == null ? "" : type.optString("detail", type.optString("shortDetail", ""));
            boolean completed = type != null && type.optBoolean("completed", false);
            boolean live = "in".equalsIgnoreCase(state) || "in progress".equalsIgnoreCase(state)
                    || "in_progress".equalsIgnoreCase(state);

            JSONObject g = new JSONObject();
            g.put("id", e.optString("id", ""));
            g.put("week", week);
            g.put("home", home);
            g.put("away", away);
            g.put("startTime", e.optString("date", comp.optString("date", "")));
            g.put("state", state);
            g.put("status", detail);
            g.put("completed", completed);
            g.put("live", live);
            if (status != null) {
                g.put("period", status.optInt("period", 0));
                g.put("clock", status.optString("displayClock", ""));
            }
            JSONObject venue=comp.optJSONObject("venue");
            JSONObject address=venue==null?null:venue.optJSONObject("address");
            String country=address==null?"":address.optString("country", "");
            g.put("venue",venue==null?"":venue.optString("fullName", ""));
            g.put("country",country);
            g.put("neutralSite",comp.optBoolean("neutralSite",false));
            g.put("international",!country.isEmpty()&&!country.matches("(?i)USA|US|United States|Estados Unidos"));
            games.put(g);
        }

        out.put("games", games);
        return out;
    }

    private static String normalizeCode(String code) {
        String c = code == null ? "" : code.trim().toUpperCase();
        if ("WSH".equals(c)) return "WAS";
        if ("JAC".equals(c)) return "JAX";
        return c;
    }

    private static JSONObject getJson(String url) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setRequestMethod("GET");
        c.setConnectTimeout(10000);
        c.setReadTimeout(15000);
        c.setRequestProperty("Accept", "application/json");
        c.setRequestProperty("User-Agent", "FCC-Android/7.2.8");
        int code = c.getResponseCode();
        InputStream in = code >= 200 && code < 300 ? c.getInputStream() : c.getErrorStream();
        String body = readAll(in);
        c.disconnect();
        if (code < 200 || code >= 300) throw new IllegalStateException("NFL schedule HTTP " + code);
        return new JSONObject(body);
    }

    private static String readAll(InputStream in) throws Exception {
        if (in == null) return "";
        StringBuilder b = new StringBuilder();
        try (BufferedReader r = new BufferedReader(new InputStreamReader(in, StandardCharsets.UTF_8))) {
            String line;
            while ((line = r.readLine()) != null) b.append(line);
        }
        return b.toString();
    }
}
