package com.douglas.fantasycommandcenter;

import android.content.Context;
import org.json.*;
import org.xmlpull.v1.XmlPullParser;
import org.xmlpull.v1.XmlPullParserFactory;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.time.*;
import java.time.format.DateTimeFormatter;
import java.util.*;
import java.util.regex.Pattern;

public final class NewsRepository {
    public static final String KEY_CACHE="native_news_cache";
    private static final Pattern LOW_VALUE=Pattern.compile("(statistics|stats|estatisticas).*(games|jogos).*(profile|perfil)|player profile|career stats",Pattern.CASE_INSENSITIVE);
    private NewsRepository(){}

    private static final class Item {
        JSONObject obj; long epoch; int quality; String key;
        Item(JSONObject obj,long epoch,int quality,String key){this.obj=obj;this.epoch=epoch;this.quality=quality;this.key=key;}
    }

    public static String fetch(Context context,String playersJson) throws Exception {
        String requestedUid=AccountRepository.uid(context);
        if(requestedUid.isEmpty())throw new IllegalStateException("LOGIN_REQUIRED");
        JSONArray input=new JSONArray(playersJson==null?"[]":playersJson);
        List<String> names=new ArrayList<>(); Set<String> seenNames=new HashSet<>();
        for(int i=0;i<input.length() && names.size()<72;i++){
            String n=input.optString(i,"").trim(),k=norm(n);
            if(n.length()>2 && seenNames.add(k)) names.add(n);
        }

        Map<String,Item> merged=new LinkedHashMap<>();
        int successBatches=0, failedBatches=0;

        for(int i=0;i<names.size();i+=5){
            List<String> batch=names.subList(i,Math.min(i+5,names.size()));
            StringBuilder q=new StringBuilder();
            for(String n:batch){
                if(q.length()>0)q.append(" OR ");
                q.append('"').append(n.replace("\"","")).append('"');
            }
            q.append(" (NFL OR \"fantasy football\") when:7d");
            String url="https://news.google.com/rss/search?q="+URLEncoder.encode(q.toString(),"UTF-8")+"&hl=en-US&gl=US&ceid=US:en";

            try{
                parseFeed(url,batch,merged);
                successBatches++;
            }catch(Exception ignored){
                failedBatches++;
                // Um lote com erro não invalida os demais e não apaga o cache anterior.
            }
        }

        List<Item> items=new ArrayList<>(merged.values());
        items.sort((a,b)->{
            int q=Integer.compare(b.quality,a.quality);
            if(q!=0)return q;
            return Long.compare(b.epoch,a.epoch);
        });

        JSONArray out=new JSONArray();
        for(int i=0;i<Math.min(60,items.size());i++)out.put(items.get(i).obj);

        JSONObject payload=new JSONObject();
        payload.put("generatedAt",Instant.now().toString());
        payload.put("news",out);
        payload.put("successBatches",successBatches);
        payload.put("failedBatches",failedBatches);

        String raw=payload.toString();

        // Só substitui o cache nativo quando alguma coleta funcionou ou trouxe dados.
        synchronized(AccountRepository.class){
        if(!requestedUid.equals(AccountRepository.uid(context)))throw new IllegalStateException("ACCOUNT_CHANGED");
        if(successBatches>0 || out.length()>0){
            context.getSharedPreferences(SyncRepository.PREFS,Context.MODE_PRIVATE)
                    .edit().putString(KEY_CACHE,raw).apply();
        }

        }
        return raw;
    }

    private static void parseFeed(String url,List<String> batch,Map<String,Item> merged) throws Exception {
        HttpURLConnection c=null;
        InputStream in=null;
        try{
            c=(HttpURLConnection)new URL(url).openConnection();
            c.setConnectTimeout(9000);
            c.setReadTimeout(13000);
            c.setRequestProperty("User-Agent","Mozilla/5.0 FCC/7.3.2");
            c.setRequestProperty("Accept","application/rss+xml, application/xml, text/xml");

            int code=c.getResponseCode();
            if(code<200 || code>=300)throw new IOException("Google News HTTP "+code);

            in=c.getInputStream();
            XmlPullParser p=XmlPullParserFactory.newInstance().newPullParser();
            p.setInput(new InputStreamReader(in,StandardCharsets.UTF_8));

            int event=p.getEventType();
            String tag="",title="",link="",date="",source="",desc="";
            boolean item=false;

            while(event!=XmlPullParser.END_DOCUMENT){
                if(event==XmlPullParser.START_TAG){
                    tag=p.getName();
                    if("item".equals(tag)){item=true;title=link=date=source=desc="";}
                }else if(event==XmlPullParser.TEXT&&item){
                    String t=p.getText();
                    if("title".equals(tag))title+=t;
                    else if("link".equals(tag))link+=t;
                    else if("pubDate".equals(tag))date+=t;
                    else if("source".equals(tag))source+=t;
                    else if("description".equals(tag))desc+=t;
                }else if(event==XmlPullParser.END_TAG){
                    if("item".equals(p.getName())&&item){
                        item=false;
                        String clean=title.trim();
                        if(!clean.isEmpty()&&!LOW_VALUE.matcher(stripAccents(clean)).find()){
                            JSONArray players=new JSONArray();
                            String hay=norm(clean+" "+desc);
                            for(String n:batch)if(matches(hay,n))players.put(n);

                            if(players.length()>0){
                                String src=source.trim().isEmpty()?"Google News":source.trim();
                                int quality=sourceQuality(src);
                                long epoch=epoch(date);

                                JSONObject o=new JSONObject();
                                o.put("title",clean);
                                o.put("summary",desc.trim());
                                o.put("url",link.trim());
                                o.put("publishedAt",iso(date));
                                o.put("source",src);
                                o.put("players",players);
                                o.put("sourceQuality",quality);
                                o.put("sourceCount",1);
                                o.put("origin","native");

                                String key=topicKey(clean,players);
                                Item current=merged.get(key);

                                if(current==null){
                                    merged.put(key,new Item(o,epoch,quality,key));
                                }else{
                                    int count=current.obj.optInt("sourceCount",1)+1;
                                    boolean prefer=quality>current.quality || (quality==current.quality&&epoch>current.epoch);
                                    if(prefer){
                                        o.put("sourceCount",count);
                                        merged.put(key,new Item(o,epoch,quality,key));
                                    }else{
                                        current.obj.put("sourceCount",count);
                                    }
                                }
                            }
                        }
                    }
                    tag="";
                }
                event=p.next();
            }
        }finally{
            if(in!=null)try{in.close();}catch(Exception ignored){}
            if(c!=null)c.disconnect();
        }
    }

    private static int sourceQuality(String source){
        String s=norm(source);
        if(s.matches(".*(fantasypros|rotowire|rotoballer|espn|nbc sports|yahoo sports|cbs sports|nfl com|the athletic|sports illustrated|pro football network|fantasy footballers).*"))return 90;
        if(s.matches(".*(reuters|ap news|usa today|fox sports).*"))return 75;
        if(s.matches(".*(placar|perfil|wiki).*"))return 25;
        return 55;
    }

    private static String topicKey(String title,JSONArray players){
        List<String> ps=new ArrayList<>();
        for(int i=0;i<players.length();i++)ps.add(norm(players.optString(i,"")));
        Collections.sort(ps);

        String who=String.join("|",ps),s=norm(title),topic="";
        if(s.contains("limited")&&s.contains("practice"))topic="limited-practice";
        else if(s.contains("questionable"))topic="questionable";
        else if(s.contains("doubtful"))topic="doubtful";
        else if(s.contains("ruled out")||s.contains("declared inactive")||s.contains("will not play"))topic="out";
        else if(s.contains("injured reserve")||s.matches(".*\\bir\\b.*"))topic="ir";
        else if(s.contains("expected to play"))topic="expected-play";
        else if(s.matches(".*week [0-9]+ outlook.*"))topic="outlook";

        if(!topic.isEmpty())return who+"|"+topic;
        return who+"|"+(s.length()>150?s.substring(0,150):s);
    }

    private static boolean matches(String hay,String name){
        String full=norm(name);
        if(hay.contains(full))return true;
        String[] t=full.split(" ");
        if(t.length<2)return hay.contains(full);
        String last=t[t.length-1],first=t[0];
        return last.length()>=4&&hay.contains(last)&&hay.contains(first.substring(0,Math.min(3,first.length())));
    }

    private static String stripAccents(String s){
        return Normalizer.normalize(s==null?"":s,Normalizer.Form.NFD).replaceAll("\\p{M}+","");
    }

    private static String norm(String s){
        return stripAccents(s).toLowerCase(Locale.ROOT).replaceAll("[^a-z0-9]+"," ").trim();
    }

    private static String iso(String d){
        try{return ZonedDateTime.parse(d.trim(),DateTimeFormatter.RFC_1123_DATE_TIME).toInstant().toString();}
        catch(Exception e){return "";}
    }

    private static long epoch(String d){
        try{return ZonedDateTime.parse(d.trim(),DateTimeFormatter.RFC_1123_DATE_TIME).toInstant().toEpochMilli();}
        catch(Exception e){return 0L;}
    }
}
