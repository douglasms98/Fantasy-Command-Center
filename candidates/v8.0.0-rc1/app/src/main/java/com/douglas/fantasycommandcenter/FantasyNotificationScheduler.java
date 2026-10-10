package com.douglas.fantasycommandcenter;

import android.Manifest;
import android.app.AlarmManager;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.os.Build;

import org.json.JSONArray;
import org.json.JSONObject;

import java.time.Instant;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.util.HashSet;
import java.util.Set;

public final class FantasyNotificationScheduler {
    private static final String PREFS = "fcc_notifications_v7";
    private static final String KEY_IDS = "scheduled_ids";
    private static final String KEY_JSON = "scheduled_json";
    public static final String CHANNEL_ID = "fantasy_alerts_v7";

    private FantasyNotificationScheduler() {}

    public static void ensureChannel(Context context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationManager nm = (NotificationManager) context.getSystemService(Context.NOTIFICATION_SERVICE);
            if (nm == null) return;
            NotificationChannel channel = new NotificationChannel(
                    CHANNEL_ID,
                    "Fantasy Football",
                    NotificationManager.IMPORTANCE_HIGH
            );
            channel.setDescription("Alertas de rodada, waivers e mudanças importantes do Fantasy Command Center");
            nm.createNotificationChannel(channel);
        }
    }

    public static boolean canScheduleExact(Context context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) return true;
        AlarmManager alarm = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        return alarm != null && alarm.canScheduleExactAlarms();
    }

    public static void schedule(Context context, String json) {
        schedule(context,json,AccountRepository.uid(context));
    }

    public static void schedule(Context context, String json, String expectedUid) {
        synchronized(AccountRepository.class){
        if(expectedUid==null||expectedUid.isEmpty()||!expectedUid.equals(AccountRepository.uid(context)))return;
        SharedPreferences appPrefs = context.getSharedPreferences(SyncRepository.PREFS, Context.MODE_PRIVATE);
        SharedPreferences prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        JSONArray incoming;
        try { incoming = new JSONArray(json == null ? "[]" : json); }
        catch (Exception e) {
            prefs.edit().putString("reason", "Lista recebida inválida; programação preservada").apply();
            return;
        }
        JSONArray array = new JSONArray();
        java.util.LinkedHashMap<String, JSONObject> merged = new java.util.LinkedHashMap<>();
        int invalid = 0, expired = 0;
        long mergeNow = System.currentTimeMillis();
        // A validated account snapshot replaces the schedule, including removals.
        for(int i=0;i<incoming.length();i++) {
            JSONObject e=incoming.optJSONObject(i);if(e==null){invalid++;continue;}
            Long at=parseInstant(e.optString("at", ""));
            if(at==null){invalid++;continue;}
            if(at<=mergeNow){expired++;continue;}
            String id=e.optString("id", "").trim();
            if(id.isEmpty()) {
                id="fcc-"+Integer.toHexString((e.optString("type")+"|"+e.optString("leagueId")+"|"+at).hashCode());
                try{e.put("id",id);}catch(Exception ignored){}
            }
            merged.put(id,e);
        }
        for(JSONObject e:merged.values())array.put(e);
        prefs.edit().putInt("receivedCount",incoming.length()).putInt("invalidCount",invalid)
                .putInt("expiredCount",expired).putString("lastScheduleAt",Instant.now().toString()).apply();
        if(array.length()==0){
            cancelAll(context, true);
            prefs.edit().putString("reason",invalid>0?"Eventos com datas inválidas":expired>0?"Eventos recebidos já venceram":"Fonte sem eventos futuros confirmados").apply();
            return;
        }
        prefs.edit().putString(KEY_JSON,array.toString()).putString("account_uid",expectedUid).putString("reason", "").apply();
        cancelAll(context, false);
        if (!appPrefs.getBoolean("notifications_enabled", true)) return;
        ensureChannel(context);

        AlarmManager alarm = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        if (alarm == null) return;

        Set<String> ids = new HashSet<>();
        long now = System.currentTimeMillis();

        for (int i = 0; i < array.length(); i++) {
            JSONObject e = array.optJSONObject(i);
            if (e == null) continue;

            String id = e.optString("id", "fcc-" + i);
            if (id.trim().isEmpty()) id = "fcc-" + i;
            Long whenMs = parseInstant(e.optString("at", ""));
            if (whenMs == null || whenMs <= now) continue;

            Intent intent = new Intent(context, FantasyNotificationReceiver.class)
                    .putExtra("accountUid", expectedUid)
                    .putExtra("event_id", id)
                    .putExtra("title", e.optString("title", "Fantasy Command Center"))
                    .putExtra("body", e.optString("body", "Há uma atualização importante no fantasy."))
                    .putExtra("type", e.optString("type", ""))
                    .putExtra("league_id", e.optString("leagueId", ""));

            PendingIntent pi = PendingIntent.getBroadcast(
                    context,
                    id.hashCode(),
                    intent,
                    PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
            );

            try {
                scheduleAlarm(alarm, whenMs, pi);
                ids.add(id);
            } catch(Exception failure) {
                prefs.edit().putString("reason", "Android recusou um agendamento: "+failure.getClass().getSimpleName()).apply();
            }
        }

        prefs.edit().putStringSet(KEY_IDS, ids).apply();
            }
    }

    public static void rescheduleSaved(Context context) {
        synchronized(AccountRepository.class){
        SharedPreferences appPrefs = context.getSharedPreferences(SyncRepository.PREFS, Context.MODE_PRIVATE);
        if (!appPrefs.getBoolean("notifications_enabled", true)) return;
        String raw = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(KEY_JSON, "");
        if (raw != null && !raw.trim().isEmpty()) schedule(context, raw, context.getSharedPreferences(PREFS,Context.MODE_PRIVATE).getString("account_uid",""));
            }
    }

    public static void cancelAll(Context context, boolean clearSaved) {
        synchronized(AccountRepository.class){
        SharedPreferences prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        Set<String> ids = prefs.getStringSet(KEY_IDS, new HashSet<>());
        AlarmManager alarm = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);

        if (alarm != null && ids != null) {
            for (String id : new HashSet<>(ids)) {
                PendingIntent pi = PendingIntent.getBroadcast(
                        context,
                        id.hashCode(),
                        new Intent(context, FantasyNotificationReceiver.class),
                        PendingIntent.FLAG_NO_CREATE | PendingIntent.FLAG_IMMUTABLE
                );
                if (pi != null) alarm.cancel(pi);
            }
        }

        SharedPreferences.Editor ed = prefs.edit().remove(KEY_IDS);
        if (clearSaved) ed.remove(KEY_JSON);
        ed.apply();
            }
    }

    public static void markDelivered(Context context, String eventId) {
        synchronized(AccountRepository.class){
        if (eventId == null || eventId.trim().isEmpty()) return;
        SharedPreferences prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        Set<String> current = prefs.getStringSet(KEY_IDS, new HashSet<>());
        Set<String> next = current == null ? new HashSet<>() : new HashSet<>(current);
        if (next.remove(eventId)) prefs.edit().putStringSet(KEY_IDS, next).apply();
            }
    }

    public static void scheduleTest(Context context, long delayMs) {
        synchronized(AccountRepository.class){
        String expectedUid=AccountRepository.uid(context);if(expectedUid.isEmpty())return;
        ensureChannel(context);
        AlarmManager alarm = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        if (alarm == null) return;

        String id = "fcc-notification-test";
        Intent intent = new Intent(context, FantasyNotificationReceiver.class)
                .putExtra("accountUid", expectedUid)
                .putExtra("event_id", id)
                .putExtra("title", "Fantasy Command Center")
                .putExtra("body", "Notificações funcionando corretamente.")
                .putExtra("type", "test");
        PendingIntent pi = PendingIntent.getBroadcast(
                context,
                id.hashCode(),
                intent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );
        scheduleAlarm(alarm, System.currentTimeMillis() + Math.max(2000L, delayMs), pi);
            }
    }

    public static String diagnostics(Context context) {
        try {
            SharedPreferences appPrefs = context.getSharedPreferences(SyncRepository.PREFS, Context.MODE_PRIVATE);
            SharedPreferences prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
            NotificationManager nm = (NotificationManager) context.getSystemService(Context.NOTIFICATION_SERVICE);

            boolean permission = Build.VERSION.SDK_INT < 33 ||
                    context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED;
            boolean exactAllowed = canScheduleExact(context);
            boolean notificationsAllowed = nm == null || Build.VERSION.SDK_INT < Build.VERSION_CODES.N || nm.areNotificationsEnabled();
            Set<String> ids = prefs.getStringSet(KEY_IDS, new HashSet<>());

            JSONObject o = new JSONObject();
            o.put("enabled", appPrefs.getBoolean("notifications_enabled", true));
            o.put("notificationPermission", permission && notificationsAllowed);
            o.put("exactAlarmAllowed", exactAllowed);
            o.put("scheduledCount", ids == null ? 0 : ids.size());
            o.put("channel", CHANNEL_ID);
            o.put("reason",prefs.getString("reason", ""));
            o.put("receivedCount",prefs.getInt("receivedCount",0));
            o.put("invalidCount",prefs.getInt("invalidCount",0));
            o.put("expiredCount",prefs.getInt("expiredCount",0));
            o.put("lastScheduleAt",prefs.getString("lastScheduleAt",""));
            o.put("backgroundLastSuccess",appPrefs.getString("background_last_success", ""));
            o.put("backgroundError",appPrefs.getString("background_error", ""));
            o.put("hasSavedSchedule", !prefs.getString(KEY_JSON, "").trim().isEmpty());
            return o.toString();
        } catch (Exception e) {
            return "{}";
        }
    }

    private static void scheduleAlarm(AlarmManager alarm, long whenMs, PendingIntent pi) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            if (alarm.canScheduleExactAlarms()) {
                alarm.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, whenMs, pi);
            } else {
                alarm.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, whenMs, pi);
            }
        } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            alarm.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, whenMs, pi);
        } else {
            alarm.setExact(AlarmManager.RTC_WAKEUP, whenMs, pi);
        }
    }

    private static Long parseInstant(String raw) {
        if (raw == null) return null;
        String value = raw.trim();
        if (value.isEmpty()) return null;

        try {
            if (value.matches("\\d{11,}")) return Long.parseLong(value);
        } catch (Exception ignored) {}

        try { return Instant.parse(value).toEpochMilli(); }
        catch (Exception ignored) {}

        try { return OffsetDateTime.parse(value).toInstant().toEpochMilli(); }
        catch (Exception ignored) {}

        try { return ZonedDateTime.parse(value).toInstant().toEpochMilli(); }
        catch (Exception ignored) {}

        try {
            return LocalDateTime.parse(value)
                    .atZone(ZoneId.systemDefault())
                    .toInstant()
                    .toEpochMilli();
        } catch (Exception ignored) {}

        for (String pattern : new String[]{"yyyy-MM-dd HH:mm:ss", "yyyy-MM-dd HH:mm"}) {
            try {
                return LocalDateTime.parse(value, DateTimeFormatter.ofPattern(pattern))
                        .atZone(ZoneId.systemDefault())
                        .toInstant()
                        .toEpochMilli();
            } catch (Exception ignored) {}
        }
        return null;
    }
}
