package com.douglas.fantasycommandcenter;

import android.app.Activity;
import android.os.CancellationSignal;
import android.os.Handler;
import android.os.Looper;
import androidx.credentials.ClearCredentialStateRequest;
import androidx.credentials.Credential;
import androidx.credentials.CredentialManager;
import androidx.credentials.CredentialManagerCallback;
import androidx.credentials.CustomCredential;
import androidx.credentials.GetCredentialRequest;
import androidx.credentials.GetCredentialResponse;
import androidx.credentials.exceptions.ClearCredentialException;
import androidx.credentials.exceptions.GetCredentialCancellationException;
import androidx.credentials.exceptions.GetCredentialException;
import com.google.android.libraries.identity.googleid.GetSignInWithGoogleOption;
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential;
import org.json.JSONObject;
import java.util.concurrent.Executor;
import java.util.concurrent.atomic.AtomicBoolean;

/** Credential Manager owns the account chooser; OAuth never runs in the WebView. */
public final class GoogleLogin {
    public interface Result { void complete(String requestId,JSONObject result); }
    private final Activity activity;
    private final Executor executor;
    private final Result callback;
    private final Handler handler=new Handler(Looper.getMainLooper());
    private final AtomicBoolean busy=new AtomicBoolean(false);
    private CancellationSignal cancellation;
    private Runnable timeout;
    private long operation=0;
    private long pendingGeneration=0;

    public GoogleLogin(Activity activity,Executor executor,Result callback){
        this.activity=activity;this.executor=executor;this.callback=callback;
    }

    public synchronized void start(String requestId,boolean link){
        if(!requestId.matches("[A-Za-z0-9_-]{1,80}"))return;
        if(!busy.compareAndSet(false,true)){callback.complete(requestId,error("GOOGLE_BUSY"));return;}
        final long current=++operation;
        final long generation=AccountRepository.generation();
        pendingGeneration=generation;
        cancellation=new CancellationSignal();
        timeout=()->{cancel();callback.complete(requestId,error("GOOGLE_CHALLENGE_EXPIRED"));};
        handler.postDelayed(timeout,300000);
        executor.execute(()->{
            try{
                JSONObject challenge=AccountRepository.googleChallenge(activity,link,generation);
                activity.runOnUiThread(()->{
                    if(!active(current))return;
                    try{
                        GetSignInWithGoogleOption option=new GetSignInWithGoogleOption.Builder(challenge.getString("clientId"))
                            .setNonce(challenge.getString("nonce")).build();
                        GetCredentialRequest request=new GetCredentialRequest.Builder().addCredentialOption(option).build();
                        CredentialManager.create(activity).getCredentialAsync(activity,request,cancellation,executor,
                            new CredentialManagerCallback<GetCredentialResponse,GetCredentialException>(){
                                @Override public void onResult(GetCredentialResponse response){
                                    if(!active(current))return;
                                    try{
                                        Credential credential=response.getCredential();
                                        if(!(credential instanceof CustomCredential)||
                                           !GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL.equals(credential.getType())){
                                            finish(current,requestId,error("GOOGLE_AUTH_FAILED"));return;
                                        }
                                        String token=GoogleIdTokenCredential.createFrom(credential.getData()).getIdToken();
                                        JSONObject result=AccountRepository.googleSignIn(activity,token,challenge.getString("challengeId"),link,generation);
                                        finish(current,requestId,result);
                                    }catch(Exception e){finish(current,requestId,safeError(e));}
                                }
                                @Override public void onError(GetCredentialException e){
                                    finish(current,requestId,error(e instanceof GetCredentialCancellationException?"GOOGLE_CANCELLED":"GOOGLE_DEVICE_UNAVAILABLE"));
                                }
                            });
                    }catch(Exception e){finish(current,requestId,safeError(e));}
                });
            }catch(Exception e){finish(current,requestId,safeError(e));}
        });
    }

    private synchronized boolean active(long current){return busy.get()&&operation==current&&!activity.isDestroyed();}
    private synchronized void finish(long current,String requestId,JSONObject result){
        if(!active(current))return;
        busy.set(false);handler.removeCallbacks(timeout);cancellation=null;timeout=null;
        callback.complete(requestId,result);
    }
    public synchronized void cancel(){
        if(busy.get())AccountRepository.cancelPendingAuthentication(pendingGeneration);
        operation++;busy.set(false);
        if(timeout!=null)handler.removeCallbacks(timeout);
        if(cancellation!=null)cancellation.cancel();
        cancellation=null;timeout=null;
    }
    public void clearState(){
        cancel();
        try{CredentialManager.create(activity).clearCredentialStateAsync(new ClearCredentialStateRequest(),null,executor,
            new CredentialManagerCallback<Void,ClearCredentialException>(){
                @Override public void onResult(Void ignored){}
                @Override public void onError(ClearCredentialException ignored){}
            });}catch(Exception ignored){}
    }
    private static JSONObject error(String code){
        JSONObject result=new JSONObject();
        try{result.put("ok",false).put("error",code);}catch(Exception ignored){}
        return result;
    }
    private static JSONObject safeError(Exception e){
        String message=e.getMessage();
        return error(message!=null&&message.matches("[0-9]{3}:[A-Z_]+")?message:"GOOGLE_AUTH_FAILED");
    }
}
