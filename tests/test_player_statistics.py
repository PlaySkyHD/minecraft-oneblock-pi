import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / 'exporter/oneblock_exporter.py'
spec = importlib.util.spec_from_file_location('exporter', MODULE)
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)


class PlayerStatisticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'world/stats').mkdir(parents=True)
        (self.root / 'world/advancements').mkdir()
        (self.root / 'usercache.json').write_text(json.dumps([{'uuid': 'test-id', 'name': 'Player'}]))
        self.file = self.root / 'world/stats/test-id.json'
        self.stats = {
            'minecraft:custom': {'minecraft:walk_one_cm': 1200, 'minecraft:sprint_one_cm': 3400,
                                 'minecraft:crouch_one_cm': 100, 'minecraft:play_time': 72000,
                                 'minecraft:time_since_death': 100, 'minecraft:damage_taken': 35,
                                 'waystones:waystone_activated': 7},
            'minecraft:mined': {'minecraft:stone': 20, 'create:andesite_casing': 3},
            'minecraft:used': {'minecraft:bow': 5, 'minecraft:stone': 8},
            'minecraft:crafted': {'minecraft:planks': 64},
        }
        self.file.write_text(json.dumps({'stats': self.stats}))
        self.collector = exporter.PlayerStatistics(str(self.root))

    def metrics(self):
        m = exporter.Metrics()
        self.collector.collect(m)
        return m.render()

    def test_real_units_aggregation_and_missing_zero_values(self):
        m = self.metrics()
        self.assertIn('minecraft_player_on_foot_meters_total{player="Player",uuid="test-id"} 47.0', m)
        self.assertIn('minecraft_player_blocks_mined_total{player="Player",uuid="test-id"} 23', m)
        self.assertIn('activity="play_time",player="Player",uuid="test-id"} 3600.0', m)
        self.assertIn('kind="damage_taken",player="Player",uuid="test-id"} 3.5', m)
        self.assertIn('minecraft_player_time_since_death_seconds{player="Player",uuid="test-id"} 5.0', m)
        self.assertIn('action="minecraft:player_kills",player="Player",uuid="test-id"} 0', m)
        self.assertIn('action="waystones:waystone_activated",player="Player",uuid="test-id"} 7', m)
        self.assertIn('minecraft_player_item_uses_total{player="Player",uuid="test-id"} 13', m)
        self.assertNotIn('blocks_placed', m)
        self.assertIn('category="minecraft:mined",player="Player",statistic="create:andesite_casing"', m)

    def test_partial_write_keeps_last_good_data_with_visible_error(self):
        self.metrics()
        self.file.write_text('{"stats":')
        m = self.metrics()
        self.assertIn('minecraft_player_blocks_mined_total{player="Player",uuid="test-id"} 23', m)
        self.assertIn('minecraft_player_statistics_read_success{player="Player",uuid="test-id"} 0', m)
        self.assertIn('minecraft_statistics_read_errors 1', m)
        self.assertIn('minecraft_statistics_players 1', m)

    def test_unreadable_first_snapshot_is_not_reported_as_zero(self):
        self.file.write_text('{')
        m = self.metrics()
        self.assertNotIn('minecraft_player_blocks_mined_total', m)
        self.assertIn('minecraft_statistics_players 0', m)

    def test_advancement_counts_exclude_recipe_unlocks_and_include_mods(self):
        (self.root / 'world/advancements/test-id.json').write_text(json.dumps({
            'DataVersion': 3955,
            'minecraft:story/root': {'done': True},
            'create:root': {'done': True},
            'create:unfinished': {'done': False},
            'minecraft:recipes/tools/iron_pickaxe': {'done': True},
        }))
        m = self.metrics()
        self.assertIn('minecraft_player_advancements_completed{player="Player",uuid="test-id"} 2', m)
        self.assertIn('minecraft_player_recipe_advancements_completed{player="Player",uuid="test-id"} 1', m)
        self.assertNotIn('advancement="minecraft:recipes/', m)

    def test_malformed_statistic_is_rejected_and_removed_files_are_not_cached(self):
        self.metrics()
        self.file.write_text(json.dumps({'stats': {'minecraft:custom': {'bad': True}}}))
        self.assertIn('minecraft_statistics_read_errors 1', self.metrics())
        self.file.unlink()
        self.assertIn('minecraft_statistics_players 0', self.metrics())
        self.assertEqual(self.collector.cache, {})

    def test_missing_name_uses_uuid_and_labels_are_escaped(self):
        (self.root / 'usercache.json').unlink()
        self.assertIn('player="test-id",uuid="test-id"', self.metrics())
        self.assertEqual(exporter._esc('a"\\\nb'), 'a\\"\\\\\\nb')


if __name__ == '__main__':
    unittest.main()
