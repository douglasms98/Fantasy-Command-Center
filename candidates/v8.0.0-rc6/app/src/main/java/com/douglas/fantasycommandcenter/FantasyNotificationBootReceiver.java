package com.douglas.fantasycommandcenter;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

public class FantasyNotificationBootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        String action = intent == null ? "" : intent.getAction();
        if (Intent.ACTION_BOOT_COMPLETED.equals(action) ||
                Intent.ACTION_MY_PACKAGE_REPLACED.equals(action) ||
                Intent.ACTION_TIME_CHANGED.equals(action) ||
                Intent.ACTION_TIMEZONE_CHANGED.equals(action)) {
            FantasyNotificationScheduler.ensureChannel(context);
            FantasyNotificationScheduler.rescheduleSaved(context);
            PeriodicSyncWorker.ensure(context);
        }
    }
}
