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


class VaultChanceTests(unittest.TestCase):
    def test_configured_chance_and_unknown_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); packs=root/'world/datapacks'; packs.mkdir(parents=True)
            self.assertIsNone(web.vault_core_chance(root))
            entries=[{'name':'minecraft:enchanted_golden_apple','weight':3},
                     {'name':'minecraft:flow_armor_trim_smithing_template','weight':3},
                     {'name':'minecraft:flow_banner_pattern','weight':2},
                     {'name':'minecraft:music_disc_creator'},
                     {'name':'minecraft:heavy_core','functions':[{'function':'minecraft:set_count','count':0,
                        'conditions':[{'condition':'minecraft:random_chance','chance':1/3}]}]}]
            path=packs/'heavy-core-1-percent.zip'
            def write():
                with zipfile.ZipFile(path,'w') as z:
                    z.writestr('data/minecraft/loot_table/chests/trial_chambers/reward_ominous_unique.json',
                               json.dumps({'pools':[{'entries':entries}]}))
            write()
            self.assertAlmostEqual(web.vault_core_chance(root),.05)
            entries[0]['weight']=5; write()
            self.assertIsNone(web.vault_core_chance(root))


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class Fake:
            def get(self):return {'players':[], 'note':'Blöcke & Sprünge'}
        cls.temp=tempfile.TemporaryDirectory()
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),web.handler(Fake(),Path(cls.temp.name)))
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
