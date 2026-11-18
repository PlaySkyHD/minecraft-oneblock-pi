import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
import zipfile
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import urlopen
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('stats_web',ROOT/'server.py')
web=importlib.util.module_from_spec(spec);spec.loader.exec_module(web)


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.h=web.History(Path(self.tmp.name)/'history.sqlite3')

    def test_period_does_not_invent_earlier_history(self):
        self.h.update(100000,{'a':{'mined':100,'survival':20,'advancements':2}})
        self.h.update(100301,{'a':{'mined':125,'survival':30,'advancements':3}})
        v=self.h.views(100301,{'a':{'mined':125,'survival':30,'advancements':3}})
        self.assertFalse(v['day']['complete'])
        self.assertEqual(v['day']['since'],100000)
        self.assertEqual(v['day']['players']['a']['mined'],25)
        self.assertNotIn('survival',v['day']['players']['a'])
        self.assertNotIn('advancements',v['day']['players']['a'])

    def test_new_player_is_not_reported_with_lifetime_total_as_period_gain(self):
        self.h.update(100000,{'a':{'mined':100}})
        v=self.h.views(100301,{'a':{'mined':110},'b':{'mined':8000}})
        self.assertEqual(v['day']['unknown'],['b'])
        self.assertNotIn('b',v['day']['players'])

    def test_reset_is_explicit_and_not_a_negative_or_fake_positive_gain(self):
        self.h.update(100000,{'a':{'mined':100}})
        v=self.h.views(100301,{'a':{'mined':10}})
        self.assertEqual(v['day']['resets'],['a'])
        self.assertIsNone(v['day']['players']['a']['mined'])

    def test_history_rate_limit_and_persistence(self):
        self.h.update(100000,{'a':{'mined':1}})
        self.h.update(100001,{'a':{'mined':2}})
        again=web.History(self.h.path)
        self.assertEqual(len(again.views(100001,{})['timeline']),1)
        again.update(100300,{'a':{'mined':3}})
        self.assertEqual(len(again.views(100300,{})['timeline']),2)


class SnapshotTests(unittest.TestCase):
    def test_real_saved_units_and_unknown_online_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'world/stats').mkdir(parents=True)
            (root/'world/advancements').mkdir()
            (root/'usercache.json').write_text(json.dumps([{'uuid':'p','name':'Player'}]))
            (root/'world/stats/p.json').write_text(json.dumps({'stats':{
                'minecraft:mined':{'minecraft:stone':42},
                'minecraft:custom':{'minecraft:play_time':72000,'minecraft:walk_one_cm':12300,'minecraft:deaths':2}}}))
            s=web.Snapshot(root,root,'http://127.0.0.1:1')
            with patch.object(s,'live',return_value={'available':False,'up':None,'online':set(),'tps':None,'onlineCount':None}):
                d=s.get()
            p=d['players'][0]
            self.assertEqual(p['summary']['mined'],42)
            self.assertEqual(p['summary']['playSeconds'],3600)
            self.assertEqual(p['summary']['walkMeters'],123)
            self.assertIsNone(p['online'])
            self.assertNotIn('password',json.dumps(d).lower())


T='data/minecraft/loot_table/chests/trial_chambers/'
def item(name,weight=1,functions=None):
    e={'type':'minecraft:item','name':'minecraft:'+name,'weight':weight}
    if functions: e['functions']=functions
    return e
def count(low,high): return {'function':'minecraft:set_count','count':{'type':'minecraft:uniform','min':low,'max':high}}
def ref(name,weight=1): return {'type':'minecraft:loot_table','value':'minecraft:chests/trial_chambers/'+name,'weight':weight}
def pool(entries,rolls=1.0,chance=None):
    p={'rolls':rolls,'bonus_rolls':0.0,'entries':entries}
    if chance is not None: p['conditions']=[{'condition':'minecraft:random_chance','chance':chance}]
    return p
# Same structure and weights as Minecraft 1.21.1, reduced to the features that matter.
VANILLA={
    'reward_ominous':{'pools':[pool([ref('reward_ominous_rare',8),ref('reward_ominous_common',2)]),
        pool([ref('reward_ominous_common')],{'type':'minecraft:uniform','min':1.0,'max':3.0}),
        pool([ref('reward_ominous_unique')],chance=.75)]},
    'reward_ominous_common':{'pools':[pool([item('emerald',5,[count(4,10)]),item('wind_charge',4,[count(8,12)]),
        item('tipped_arrow',3,[count(4,12),{'function':'minecraft:set_potion','id':'minecraft:strong_slowness'}]),
        item('diamond',2,[count(2,3)]),item('ominous_bottle',1)])]},
    'reward_ominous_rare':{'pools':[pool([item('emerald_block',5),item('iron_block',4),
        item('book',2,[{'function':'minecraft:enchant_randomly','options':['minecraft:breach','minecraft:density']}]),
        item('diamond_block',1)])]},
    'reward_ominous_unique':{'pools':[pool([item('enchanted_golden_apple',3),item('flow_armor_trim_smithing_template',3),
        item('flow_banner_pattern',2),item('music_disc_creator',1),item('heavy_core',1)])]},
}
def core_override(chance):
    table=json.loads(json.dumps(VANILLA['reward_ominous_unique']))
    table['pools'][0]['entries'][4]['functions']=[{'function':'minecraft:set_count','count':0,
        'conditions':[{'condition':'minecraft:random_chance','chance':chance}]}]
    return table


class VaultModelTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        jar=self.root/'libraries/net/minecraft/server/1.21.1-1/server-1.21.1-1-extra.jar'
        jar.parent.mkdir(parents=True)
        with zipfile.ZipFile(jar,'w') as z:
            for name,table in VANILLA.items(): z.writestr(T+name+'.json',json.dumps(table))
        self.packs=self.root/'world/datapacks';self.packs.mkdir(parents=True)

    def pack(self,name,tables):
        with zipfile.ZipFile(self.packs/name,'w') as z:
            for table,content in tables.items(): z.writestr(T+table+'.json',json.dumps(content))

    def test_vanilla_and_datapack_chances(self):
        v=web.vault.build(self.root)
        self.assertTrue(v['available']);self.assertAlmostEqual(v['coreChance'],.075)
        items={i['key']:i for i in v['items']}
        self.assertAlmostEqual(items['Smaragdblock']['chance'],.8*5/12)
        self.assertAlmostEqual(items['Verzaubertes Buch (Bresche oder Dichte)']['chance'],.8*2/12)
        self.assertIn('Pfeil der Langsamkeit IV',items)
        self.pack('heavy-core.zip',{'reward_ominous_unique':core_override(1/3)})
        v=web.vault.build(self.root)
        self.assertAlmostEqual(v['coreChance'],.05);self.assertEqual(v['overrides'],['heavy-core.zip'])

    def test_simulated_openings_match_calculated_chances(self):
        import random
        rng=random.Random(4)
        v=web.vault.build(self.root)
        def roll(table,out):
            for p in table['pools']:
                if rng.random()>=p['chance']: continue
                for _ in range(rng.randint(*p['rolls'])):
                    e=rng.choices(p['entries'],[x['weight'] for x in p['entries']])[0]
                    if 'table' in e: roll(e['table'],out)
                    else:
                        alt=rng.choices(e['counts'],[c[0] for c in e['counts']])[0]
                        n=rng.randint(alt[1],alt[2])
                        if n>0: out[e['key']]=out.get(e['key'],0)+n
            return out
        n=20000; seen={}; total={}
        for _ in range(n):
            for k,c in roll(v['model'],{}).items(): seen[k]=seen.get(k,0)+1; total[k]=total.get(k,0)+c
        for it in v['items']:
            with self.subTest(item=it['name']):
                self.assertAlmostEqual(seen.get(it['key'],0)/n,it['chance'],delta=.012)
                self.assertAlmostEqual(total.get(it['key'],0)/n,it['average'],delta=max(.02,it['average']*.04))

    def test_unknown_features_or_ambiguous_overrides_disable_model(self):
        broken=json.loads(json.dumps(VANILLA['reward_ominous_unique']))
        broken['pools'][0]['entries'][0]['functions']=[{'function':'minecraft:set_name','name':'x'}]
        self.pack('a.zip',{'reward_ominous_unique':broken})
        self.assertFalse(web.vault.build(self.root)['available'])
        self.pack('a.zip',{'reward_ominous_unique':core_override(.5)})
        self.pack('b.zip',{'reward_ominous_unique':core_override(.9)})
        self.assertFalse(web.vault.build(self.root)['available'])

    def test_missing_server_jar_disables_model(self):
        self.assertFalse(web.vault.build(self.root/'missing')['available'])


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class Fake:
            def get(self):return {'players':[], 'note':'Blöcke & Sprünge'}
        cls.temp=tempfile.TemporaryDirectory()
        class FakeVault:
            def get(self):return {'available':False,'reason':'/home/secret/path'}
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),web.handler(Fake(),Path(cls.temp.name),vault_model=FakeVault()))
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.url='http://127.0.0.1:'+str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join();cls.temp.cleanup()

    def test_api_utf8_and_headers(self):
        with urlopen(self.url+'/api/stats') as r:
            self.assertEqual(json.load(r)['note'],'Blöcke & Sprünge')
            self.assertEqual(r.headers['Cache-Control'],'no-store')
            self.assertEqual(r.headers['X-Content-Type-Options'],'nosniff')

    def test_vault_api_hides_internal_reason(self):
        with urlopen(self.url+'/api/vault') as r:
            self.assertEqual(json.load(r),{'available':False})

    def test_allowlist_blocks_configuration_source_and_path_traversal(self):
        for path in ['/server.py','/../server.properties','/fonts/../../server.py','/api/admin','/world/stats']:
            with self.subTest(path=path),self.assertRaises(HTTPError) as exc:
                urlopen(self.url+path)
            self.assertEqual(exc.exception.code,404)

    def test_page_and_local_assets_are_available(self):
        for path in ['/','/app.js','/styles.css','/world.svg','/favicon.svg','/healthz']:
            with self.subTest(path=path),urlopen(self.url+path) as r:
                self.assertEqual(r.status,200)
                self.assertGreater(len(r.read()),0)

if __name__=='__main__':unittest.main()
