package com.douglas.fantasycommandcenter;

import android.Manifest;
import android.app.Notification;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;

public class FantasyNotificationReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        FantasyNotificationScheduler.ensureChannel(context);

        String eventId = intent.getStringExtra("event_id");
        if (eventId == null || eventId.isEmpty()) eventId = "fcc-alert";

        if (Build.VERSION.SDK_INT >= 33 &&
                context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            FantasyNotificationScheduler.markDelivered(context, eventId);
            return;
        }
        String title = intent.getStringExtra("title");
        if (title == null || title.isEmpty()) title = "Fantasy Command Center";
        String body = intent.getStringExtra("body");
        if (body == null || body.isEmpty()) body = "Há uma atualização importante.";

        Intent launch = context.getPackageManager().getLaunchIntentForPackage(context.getPackageName());
        PendingIntent content = null;
        if (launch != null) {
            content = PendingIntent.getActivity(
                    context,
                    eventId.hashCode(),
                    launch,
                    PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
            );
        }

        Notification.Builder builder = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                ? new Notification.Builder(context, FantasyNotificationScheduler.CHANNEL_ID)
                : new Notification.Builder(context);

        builder.setSmallIcon(R.drawable.ic_stat_fcc_v724)
                .setContentTitle(title)
                .setContentText(body)
                .setStyle(new Notification.BigTextStyle().bigText(body))
                .setAutoCancel(true)
                .setColor(0xFF58D2F2)
                .setPriority(Notification.PRIORITY_HIGH);
        if (content != null) builder.setContentIntent(content);

        NotificationManager nm = (NotificationManager) context.getSystemService(Context.NOTIFICATION_SERVICE);
        if (nm != null) {
            nm.notify(Math.abs(eventId.hashCode()), builder.build());
            FantasyNotificationScheduler.markDelivered(context, eventId);
        }
    }
}
