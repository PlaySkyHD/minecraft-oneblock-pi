import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_web_stats import web


def line(text, source='net.minecraft.server.MinecraftServer'):
    return f'[15Nov2026 20:20:39.715] [Server thread/INFO] [{source}/]: {text}\n'


class LiveFeedTests(unittest.TestCase):
    def test_only_game_events_not_commands_or_private_messages(self):
        for text,kind in [('<PlaySkyHD> Hallo <script>alert(1)</script>', 'chat'),
                          ('[Not Secure] <Fissi17> Moin', 'chat'),
                          ('Fissi17 joined the game','joined'),
                          ('Fissi17 left the game','left'),
                          ('Fissi17 has made the advancement [Stone Age]','advancement'),
                          ('Fissi17 was slain by Zombie','death')]:
            self.assertEqual(web.LiveFeed.parse(line(text).strip())['type'],kind)
        for text in ['[Server] secret','Fissi17 whispers to you: secret','Fissi17 has the following entity data: [1d,2d,3d]']:
            self.assertIsNone(web.LiveFeed.parse(line(text).strip()))
        self.assertIsNone(web.LiveFeed.parse(line('<PlaySkyHD> Hallo','some.mod.Logger').strip()))
        self.assertIsNone(web.LiveFeed.parse(line('<PlaySkyHD> Hi').replace('Server thread','RCON Client /127.0.0.1 #1').strip()))

    def test_partial_lines_rotation_and_bounded_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'latest.log';p.write_bytes(line('<PlaySkyHD> Grüße').encode()[:-2])
            feed=web.LiveFeed(p)
            self.assertEqual(feed.get()['events'],[])
            with p.open('ab') as f:f.write(line('<PlaySkyHD> Grüße').encode()[-2:])
            self.assertEqual(feed.get()['events'][0]['text'],'Grüße')
            self.assertEqual(len(feed.get()['events']),1)
            p.rename(p.with_suffix('.old'));p.write_text(line('Fissi17 joined the game'))
            self.assertEqual(feed.get()['events'][-1]['type'],'joined')
            with p.open('a') as f:f.write(line('<Fissi17> Hello')*300)
            self.assertEqual(len(feed.get()['events']),250)
            p.unlink();self.assertFalse(feed.get()['available'])


class PositionTests(unittest.TestCase):
    def test_real_response_and_invalid_values(self):
        self.assertEqual(web.Positions.parse_position('A has the following entity data: [-1.5d, 64.0d, 20.3d]\n'),{'x':-1.5,'y':64,'z':20.3})
        for text in ['No entity was found','A has the following entity data: [NaNd, 64d, 0d]','A has the following entity data: [1d,2d]']:
            with self.assertRaises(ValueError):web.Positions.parse_position(text)

    def test_fixed_commands_and_global_cache(self):
        commands=[]
        class FakeRcon:
            def __init__(self,*args,**kwargs):pass
            def command(self,cmd):
                commands.append(cmd)
                return {'list':'There are 1 of a max of 20 players online: PlaySkyHD\n',
                        'data get entity PlaySkyHD Pos':'PlaySkyHD has the following entity data: [1d,64d,2d]',
                        'data get entity PlaySkyHD Dimension':'PlaySkyHD has the following entity data: "minecraft:overworld"'}[cmd]
            def close(self):pass
        with patch.object(web.exporter,'Rcon',FakeRcon),patch.object(web.exporter,'read_properties',return_value={'enable-rcon':'true'}):
            p=web.Positions(Path('/not-used'));a=p.get();b=p.get()
        self.assertTrue(a['available']);self.assertEqual(a,b)
        self.assertEqual(a['players'][0]['dimension'],'minecraft:overworld')
        self.assertEqual(commands,['list','data get entity PlaySkyHD Pos','data get entity PlaySkyHD Dimension'])

    def test_rcon_unavailable_is_explicit(self):
        with patch.object(web.exporter,'read_properties',side_effect=OSError()):
            result=web.Positions(Path('/not-used')).get()
        self.assertFalse(result['available']);self.assertEqual(result['players'],[])
