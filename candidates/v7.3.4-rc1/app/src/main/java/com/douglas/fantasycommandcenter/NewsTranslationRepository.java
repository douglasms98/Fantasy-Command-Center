package com.douglas.fantasycommandcenter;

import android.content.Context;
import com.google.android.gms.tasks.Tasks;
import com.google.mlkit.common.model.DownloadConditions;
import com.google.mlkit.nl.translate.TranslateLanguage;
import com.google.mlkit.nl.translate.Translation;
import com.google.mlkit.nl.translate.Translator;
import com.google.mlkit.nl.translate.TranslatorOptions;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.regex.Pattern;

/** On-device English-to-Portuguese title translation with protected names and NFL terms. */
public final class NewsTranslationRepository {
    private NewsTranslationRepository(){}
    public static String translate(Context context,String raw){
        JSONObject result=new JSONObject(),titles=new JSONObject();Translator translator=null;
        try{
            JSONArray rows=new JSONArray(raw==null?"[]":raw);
            translator=Translation.getClient(new TranslatorOptions.Builder()
                    .setSourceLanguage(TranslateLanguage.ENGLISH).setTargetLanguage(TranslateLanguage.PORTUGUESE).build());
            // Initial language-model download uses Wi-Fi; subsequent translations run offline.
            Tasks.await(translator.downloadModelIfNeeded(new DownloadConditions.Builder().requireWifi().build()),90,TimeUnit.SECONDS);
            for(int i=0;i<Math.min(40,rows.length());i++){
                JSONObject row=rows.optJSONObject(i);if(row==null)continue;
                String original=row.optString("title","");if(original.isEmpty())continue;
                List<String> protect=new ArrayList<>();JSONArray players=row.optJSONArray("players");
                if(players!=null)for(int j=0;j<players.length();j++){String name=players.optString(j,"");if(!name.isEmpty())protect.add(name);}
                protect.sort(Comparator.comparingInt(String::length).reversed());
                for(String term:new String[]{"IR","NFL","ESPN","PPR","BYE","DNP"})if(Pattern.compile("\\b"+term+"\\b").matcher(original).find())protect.add(term);
                String input=original;List<String> used=new ArrayList<>();
                for(String term:protect){
                    Pattern pattern=Pattern.compile("(?<![\\p{L}\\p{N}])"+Pattern.quote(term)+"(?![\\p{L}\\p{N}])");
                    if(pattern.matcher(input).find()){
                        String marker="FCCNAME"+String.format(java.util.Locale.ROOT,"%03d",used.size());
                        input=pattern.matcher(input).replaceAll(marker);used.add(term);
                    }
                }
                try{
                    String translated=Tasks.await(translator.translate(input),15,TimeUnit.SECONDS);
                    boolean valid=true;
                    for(int j=0;j<used.size();j++){
                        Pattern marker=Pattern.compile("FCC\\s*NAME\\s*"+String.format(java.util.Locale.ROOT,"%03d",j),Pattern.CASE_INSENSITIVE);
                        if(!marker.matcher(translated).find()){valid=false;break;}
                        translated=marker.matcher(translated).replaceAll(java.util.regex.Matcher.quoteReplacement(used.get(j)));
                    }
                    if(valid&&!translated.trim().isEmpty())titles.put(original,translated.trim());
                }catch(Exception ignored){}
            }
        }catch(Exception e){try{result.put("error","Tradução indisponível; conecte ao Wi-Fi para baixar o idioma e tente novamente.");}catch(Exception ignored){}}
        finally{if(translator!=null)translator.close();}
        try{result.put("titles",titles);if(titles.length()==0&&!result.has("error"))result.put("error","Nenhum título pôde ser traduzido nesta tentativa.");}catch(Exception ignored){}
        return result.toString();
    }
}
