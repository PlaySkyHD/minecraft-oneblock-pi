#!/usr/bin/env python3
"""Extend the existing dashboard, retaining all original server panels and UID."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
path = ROOT/'grafana-dashboard.json'
d = json.loads(path.read_text())
d['title'] = 'Minecraft Create – Server & Spieler'
d['version'] = 3
d['description'] = 'Servermonitoring und gespeicherte Spielerstatistiken der aktuellen Welt. Keine exakte Platzierungsstatistik.'
d['panels'] = [p for p in d['panels'] if p['id'] < 100]
ds = {'type':'prometheus','uid':'${DS_PROMETHEUS}'}
variables = d['templating']['list'][:1]

def variable(name, label, query, multi=False, current=None):
    result = {'name':name,'label':label,'type':'query','datasource':ds,'query':query,'refresh':1,'sort':1,'multi':multi,'includeAll':multi,'current':current or {}}
    if multi: result.update(allValue='.*',current={'selected':True,'text':'All','value':'$__all'})
    return result

variables += [
    variable('instance','Server','label_values(minecraft_up{job="$job"}, instance)'),
    variable('player','Spieler','label_values(minecraft_player_blocks_mined_total{job="$job",instance=~"$instance"}, player)',True),
    variable('category','Detail-Kategorie','label_values(minecraft_player_statistic_events_total{job="$job",instance=~"$instance"}, category)',current={'selected':True,'text':'minecraft:mined','value':'minecraft:mined'}),
    variable('statistic','Block / Item / Wesen','label_values(minecraft_player_statistic_events_total{job="$job",instance=~"$instance",category="$category"}, statistic)',True),
    variable('action','Aktion','label_values(minecraft_player_actions_total{job="$job",instance=~"$instance"}, action)',current={'selected':True,'text':'minecraft:deaths','value':'minecraft:deaths'}),
]
d['templating']['list'] = variables
sel = 'job="$job",instance=~"$instance",player=~"$player"'
idnum, y = 100, 25

def add(panel):
    global idnum
    panel['id'] = idnum; idnum += 1
    d['panels'].append(panel)

def row(title):
    global y
    add({'title':title,'type':'row','collapsed':False,'panels':[],'gridPos':{'x':0,'y':y,'w':24,'h':1}})
    y += 1

def target(expr, legend='{{player}}', instant=True, table=False):
    out={'datasource':ds,'expr':expr,'legendFormat':legend,'refId':'A','instant':instant,'range':not instant}
    if table: out['format']='table'
    return out

def rank(title, expr, x, unit='short', description='', width=8):
    add({'title':title,'description':description or 'Gespeicherter Gesamtwert seit Beginn dieser Welt; kann bis zum naechsten Minecraft-Speichern verzoegert sein.',
         'type':'bargauge','datasource':ds,'targets':[target('sort_desc('+expr+')')],
         'gridPos':{'x':x,'y':y,'w':width,'h':8},
         'fieldConfig':{'defaults':{'unit':unit,'min':0,'decimals':1 if unit in ('lengthm','s') else 0,
                                    'displayName':'${__field.labels.player}', 'color':{'mode':'continuous-GrYlBl'}},'overrides':[]},
         'options':{'orientation':'horizontal','displayMode':'gradient','showUnfilled':True,
                    'reduceOptions':{'values':False,'calcs':['lastNotNull'],'fields':''}}})

def metric(name, extra=''): return name+'{'+sel+extra+'}'
def action(name): return metric('minecraft_player_actions_total',',action="minecraft:'+name+'"')

row('Spieler – Gesamtwerte seit Weltstart')
add({'title':'So liest du die Statistiken','type':'text','gridPos':{'x':0,'y':y,'w':24,'h':4},'options':{'mode':'markdown','content':
'''Die Ranglisten stammen aus **gespeicherten Minecraft-Spielerdaten** und werden ohne Serverneustart gelesen. Aktualisierung erst beim regulären Speichern oder Logout; keine erzwungenen Saves. **Item-Benutzung ist nicht gleich Blockplatzierung.** Maschinen-Abbau wird nicht automatisch einem Spieler zugerechnet. Aufgehobene Items können mehrfach zählen. Spielzeit enthält AFK-Zeit; Zeitwerte entsprechen Ticks / 20. Fortschritte schließen Rezeptfreischaltungen aus. Gesamtsummen existieren rückwirkend, Zeitverläufe und Zuwächse erst ab dem ersten Prometheus-Scrape dieser Metriken.'''}})
y += 4
for title,name,x in [('Bloecke abgebaut','blocks_mined',0),('Items hergestellt','items_crafted',8),('Items aufgehoben','items_picked_up',16)]: rank(title,metric('minecraft_player_'+name+'_total'),x)
y+=8
rank('Zu Fuss (Gehen + Sprinten + Schleichen)',metric('minecraft_player_on_foot_meters_total'),0,'lengthm')
rank('Spielzeit inklusive AFK',metric('minecraft_player_time_seconds_total',',activity="play_time"'),8,'s')
rank('Fortschritte abgeschlossen',metric('minecraft_player_advancements_completed'),16)
y+=8
rank('Tode',action('deaths'),0)
rank('Mob-Kills',action('mob_kills'),8)
rank('Spieler-Kills',action('player_kills'),16)
y+=8
rank('Schaden verursacht (Lebenspunkte)',metric('minecraft_player_damage_health_points_total',',kind="damage_dealt"'),0)
rank('Schaden erhalten (Lebenspunkte)',metric('minecraft_player_damage_health_points_total',',kind="damage_taken"'),8)
rank('Spielzeit seit letztem Tod',metric('minecraft_player_time_since_death_seconds'),16,'s','Spielzeit seit dem letzten Tod in Ticks / 20; kein Zeitpunkt und keine Echtzeit seit Logout.')
y+=8
row('Aktivitaeten & Produktion')
for triple in [[('Spruenge','jump',0),('Tiere gezuechtet','animals_bred',8),('Fische gefangen','fish_caught',16)],
               [('Verzauberungen','enchant_item',0),('Villager-Handel','traded_with_villager',8),('Im Bett geschlafen','sleep_in_bed',16)]]:
    for title,name,x in triple: rank(title,action(name),x)
    y+=8
rank('Item-Benutzungen (keine Platzierungszahl)',metric('minecraft_player_item_uses_total'),0)
rank('Werkzeuge / Ausruestung zerbrochen',metric('minecraft_player_items_broken_total'),8)
rank('Items fallengelassen',metric('minecraft_player_items_dropped_total'),16)
y+=8
row('Bewegung im Detail')
for group in [[('Gehen','walk',0),('Sprinten','sprint',8),('Schleichen','crouch',16)],
              [('Schwimmen','swim',0),('Boot','boat',8),('Lore','minecart',16)],
              [('Elytra','aviate',0),('Pferd','horse',8),('Klettern','climb',16)]]:
    for title,mode,x in group: rank(title,metric('minecraft_player_distance_meters_total',',mode="'+mode+'"'),x,'lengthm')
    y+=8
row('Detail-Auswertung – alle gespeicherten Block-, Item-, Wesen- und Aktionswerte')
rank('Ausgewaehlte Aktion: $action',metric('minecraft_player_actions_total',',action="$action"'),0,width=12)
rank('Letzter gespeicherter Stand – Alter', 'time() - '+metric('minecraft_player_statistics_saved_timestamp_seconds'),12,'s',
     'Alter der Statistikdatei, NICHT zuletzt online. Bei Offline-Spielern darf dieser Wert beliebig gross werden.',width=12)
y+=8
expr=metric('minecraft_player_statistic_events_total',',category="$category",statistic=~"$statistic"')
add({'title':'Top 100 Einzelwerte: $category','type':'table','datasource':ds,'targets':[target('sort_desc(topk(100,'+expr+'))',instant=True,table=True)],
     'description':'Kategorie ueber die Variablen waehlen: mined, crafted, used, broken, picked_up, dropped, killed, killed_by. used ist Item-Benutzung, keine exakte Platzierung.',
     'gridPos':{'x':0,'y':y,'w':24,'h':12},
     'transformations':[{'id':'organize','options':{'excludeByName':{'Time':True,'__name__':True,'job':True,'instance':True,'uuid':True,'category':True,'server':True},'renameByName':{'player':'Spieler','statistic':'Block / Item / Wesen','Value':'Anzahl'}}}],
     'fieldConfig':{'defaults':{'decimals':0},'overrides':[]},'options':{'showHeader':True,'sortBy':[{'displayName':'Anzahl','desc':True}]}})
y+=12
add({'title':'Fortschritte je Spieler (ohne Rezepte)','type':'table','datasource':ds,
     'targets':[target(metric('minecraft_player_advancement_completed')+' == 1',instant=True,table=True)],
     'gridPos':{'x':0,'y':y,'w':24,'h':12},
     'transformations':[{'id':'organize','options':{'excludeByName':{'Time':True,'__name__':True,'job':True,'instance':True,'uuid':True,'Value':True,'server':True},'renameByName':{'player':'Spieler','advancement':'Fortschritt'}}}],
     'options':{'showHeader':True}})
y+=12
row('Zuwachs im gewaehlten Zeitraum – erst ab Beginn der Erfassung')
rank('Abgebaute Bloecke im Zeitraum','increase('+metric('minecraft_player_blocks_mined_total')+'[$__range])',0)
rank('Tode im Zeitraum','increase('+action('deaths')+'[$__range])',8)
rank('Mob-Kills im Zeitraum','increase('+action('mob_kills')+'[$__range])',16)
y+=8
rank('Statistikdatei erfolgreich gelesen',metric('minecraft_player_statistics_read_success'),0)
rank('Fortschrittsdatei erfolgreich gelesen',metric('minecraft_player_advancements_read_success'),8)
rank('Waystones aktiviert',metric('minecraft_player_actions_total',',action="waystones:waystone_activated"'),16)

# Keep legacy server panels filtered to the selected target too.
for panel in d['panels']:
    if panel['id'] < 100:
        for t in panel.get('targets',[]):
            if 'instance=~"$instance"' not in t['expr']:
                t['expr']=t['expr'].replace('job="$job"','job="$job",instance=~"$instance"')
assert len({p['id'] for p in d['panels']})==len(d['panels'])
path.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
print('Dashboard:',len(d['panels']),'panels;',len(variables),'filters; uid=',d['uid'])
