"""Ominous vault loot model built from the server's own loot tables.

The vanilla tables are read from the Minecraft server jar in ``libraries/`` and
overridden by world datapacks, so the website shows exactly what the server
uses. Only the loot table features used by the vault tables are supported; any
other feature makes the model unavailable instead of showing wrong numbers.
"""
import json
from pathlib import Path
import zipfile

ROOT_TABLE = 'minecraft:chests/trial_chambers/reward_ominous'
CORE = 'minecraft:heavy_core'

ITEM_NAMES = {
    'minecraft:emerald': 'Smaragd', 'minecraft:wind_charge': 'Windkugel',
    'minecraft:tipped_arrow': 'Getränkter Pfeil', 'minecraft:diamond': 'Diamant',
    'minecraft:ominous_bottle': 'Unheilvolle Flasche', 'minecraft:emerald_block': 'Smaragdblock',
    'minecraft:iron_block': 'Eisenblock', 'minecraft:crossbow': 'Armbrust',
    'minecraft:golden_apple': 'Goldener Apfel', 'minecraft:diamond_axe': 'Diamantaxt',
    'minecraft:diamond_chestplate': 'Diamantharnisch', 'minecraft:book': 'Buch',
    'minecraft:diamond_block': 'Diamantblock', 'minecraft:enchanted_golden_apple': 'Verzauberter goldener Apfel',
    'minecraft:flow_armor_trim_smithing_template': 'Schmiedevorlage: Fluss',
    'minecraft:flow_banner_pattern': 'Bannervorlage: Fluss', 'minecraft:music_disc_creator': 'Schallplatte: Creator',
    'minecraft:heavy_core': 'Heavy Core',
}
ENCHANTED_NAMES = {'minecraft:crossbow': 'Verzauberte Armbrust', 'minecraft:diamond_axe': 'Verzauberte Diamantaxt',
                   'minecraft:diamond_chestplate': 'Verzauberter Diamantharnisch', 'minecraft:book': 'Verzaubertes Buch'}
ENCHANTMENTS = {'minecraft:knockback': 'Rückstoß', 'minecraft:punch': 'Schlag', 'minecraft:smite': 'Bann',
                'minecraft:looting': 'Plünderung', 'minecraft:multishot': 'Mehrfachschuss',
                'minecraft:breach': 'Bresche', 'minecraft:density': 'Dichte', 'minecraft:wind_burst': 'Windstoß'}
POTIONS = {'minecraft:strong_slowness': 'Langsamkeit IV', 'minecraft:slowness': 'Langsamkeit',
           'minecraft:long_slowness': 'Langsamkeit (verlängert)'}
ROMAN = ['', 'I', 'II', 'III', 'IV', 'V', 'VI']
COSMETIC = {'minecraft:enchant_with_levels', 'minecraft:enchant_randomly', 'minecraft:set_enchantments',
            'minecraft:set_potion', 'minecraft:set_ominous_bottle_amplifier'}


class Unsupported(ValueError):
    pass


def table_path(table_id):
    namespace, path = table_id.split(':', 1) if ':' in table_id else ('minecraft', table_id)
    return f'data/{namespace}/loot_table/{path}.json'


def _vanilla_jar(server_dir):
    jars = sorted((server_dir/'libraries/net/minecraft/server').glob('*/server-*-extra.jar'))
    if not jars: raise Unsupported('Minecraft-Server-JAR nicht gefunden')
    return jars[-1]


def _sources(server_dir):
    """Return (label, reader) pairs; later sources override earlier ones."""
    jar = _vanilla_jar(server_dir)
    sources = [(jar, 'Minecraft')]
    packs = server_dir/'world/datapacks'
    if packs.is_dir():
        sources += [(p, p.name) for p in sorted(packs.iterdir()) if p.suffix == '.zip' or p.is_dir()]
    return sources


def _read(source, name):
    if source.is_dir():
        file = source/name
        return file.read_bytes() if file.is_file() else None
    with zipfile.ZipFile(source) as archive:
        try: return archive.read(name)
        except KeyError: return None


def _uniform(value, what):
    """Return an inclusive integer range like UniformGenerator.getInt."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return [int(value), int(value)]
    if isinstance(value, dict) and value.get('type') in ('minecraft:uniform', 'uniform'):
        low, high = int(value['min']//1), int(value['max']//1)
        if low > high: raise Unsupported(what)
        return [low, high]
    if isinstance(value, dict) and value.get('type') in ('minecraft:constant', 'constant'):
        return [int(value['value']), int(value['value'])]
    raise Unsupported(what)


def _chance(conditions, what):
    """Combined probability of random_chance conditions (all must pass)."""
    chance = 1.0
    for condition in conditions or []:
        if condition.get('condition') != 'minecraft:random_chance': raise Unsupported(what)
        value = float(condition['chance'])
        if not 0 <= value <= 1: raise Unsupported(what)
        chance *= value
    return chance


def _label(item, functions):
    name = ITEM_NAMES.get(item, item.split(':')[-1].replace('_', ' ').capitalize())
    detail = None
    for f in functions:
        kind = f.get('function')
        if kind == 'minecraft:enchant_with_levels':
            name = ENCHANTED_NAMES.get(item, name+' (verzaubert)')
        elif kind == 'minecraft:enchant_randomly':
            name = ENCHANTED_NAMES.get(item, name+' (verzaubert)')
            options = f.get('options')
            if isinstance(options, list):
                names = [ENCHANTMENTS.get(o, o) for o in options]
                detail = ', '.join(names[:-1])+' oder '+names[-1] if len(names) > 1 else ''.join(names)
        elif kind == 'minecraft:set_enchantments':
            name = ENCHANTED_NAMES.get(item, name+' (verzaubert)')
            parts = []
            for enchantment, level in f.get('enchantments', {}).items():
                level = int(level) if isinstance(level, (int, float)) else 0
                parts.append(ENCHANTMENTS.get(enchantment, enchantment)+(' '+ROMAN[level] if 0 < level < len(ROMAN) else ''))
            detail = ', '.join(parts)
        elif kind == 'minecraft:set_potion' and item == 'minecraft:tipped_arrow':
            name = 'Pfeil der '+POTIONS.get(f.get('id'), f.get('id', ''))
        elif kind == 'minecraft:set_ominous_bottle_amplifier':
            low, high = _uniform(f.get('amplifier', 0), 'Flaschenstufe')
            detail = 'Stufe '+(ROMAN[low+1] if low == high else f'{ROMAN[low+1]}–{ROMAN[high+1]}') if high+1 < len(ROMAN) else None
    return name, detail


def _item(entry):
    item = entry['name']
    counts = [[1.0, 1, 1]]  # alternatives: [probability, min, max]
    functions = entry.get('functions', [])
    for f in functions:
        kind = f.get('function')
        if kind == 'minecraft:set_count':
            if f.get('add'): raise Unsupported('set_count mit add')
            low, high = _uniform(f['count'], 'Anzahl')
            chance = _chance(f.get('conditions'), 'Bedingung an set_count')
            counts = [[p*chance, low, high] for p, _, _ in counts] + \
                     ([[p*(1-chance), a, b] for p, a, b in counts] if chance < 1 else [])
        elif kind in COSMETIC:
            if f.get('conditions'): raise Unsupported('Bedingung an '+kind)
        else:
            raise Unsupported('Funktion '+str(kind))
    name, detail = _label(item, functions)
    return {'item': item, 'key': name+(' ('+detail+')' if detail else ''), 'name': name, 'detail': detail,
            'counts': [c for c in counts if c[0] > 0]}


def _compile(table_id, lookup, stack=()):
    if table_id in stack: raise Unsupported('Rekursive Beutetabelle')
    table = lookup(table_id)
    if table.get('functions'): raise Unsupported('Tabellenfunktionen')
    pools = []
    for pool in table.get('pools', []):
        if float(pool.get('bonus_rolls', 0)) != 0 or pool.get('functions'): raise Unsupported('Pool-Optionen')
        entries = []
        for entry in pool['entries']:
            if entry.get('conditions') or entry.get('functions') and entry.get('type') != 'minecraft:item':
                raise Unsupported('Eintragsbedingungen')
            weight = int(entry.get('weight', 1))
            if weight <= 0: continue
            kind = entry.get('type')
            if kind == 'minecraft:item':
                compiled = _item(entry)
            elif kind == 'minecraft:loot_table' and isinstance(entry.get('value'), str):
                compiled = {'table': _compile(entry['value'], lookup, stack+(table_id,))}
            elif kind == 'minecraft:empty':
                compiled = {'empty': True}
            else:
                raise Unsupported('Eintragstyp '+str(kind))
            compiled['weight'] = weight
            entries.append(compiled)
        if entries:
            pools.append({'chance': _chance(pool.get('conditions'), 'Pool-Bedingung'),
                          'rolls': _uniform(pool.get('rolls', 1), 'Ziehungen'), 'entries': entries})
    return {'pools': pools}


def _present(counts):
    """Probability that the item stack is not empty."""
    total = 0.0
    for p, low, high in counts:
        positive = max(0, high-max(low, 1)+1)
        total += p*positive/(high-low+1)
    return total


def _mean(counts):
    return sum(p*(low+high)/2 for p, low, high in counts)


def _keys(table):
    found = {}
    for pool in table['pools']:
        for e in pool['entries']:
            if 'table' in e: found.update(_keys(e['table']))
            elif 'item' in e: found.setdefault(e['key'], e)
    return found


def _absent(table, key):
    """Probability that ``key`` is missing from one generation of ``table``."""
    result = 1.0
    for pool in table['pools']:
        total = sum(e['weight'] for e in pool['entries'])
        per_roll = 0.0
        for e in pool['entries']:
            if 'table' in e: miss = _absent(e['table'], key)
            elif e.get('key') == key: miss = 1-_present(e['counts'])
            else: miss = 1.0
            per_roll += e['weight']/total*miss
        low, high = pool['rolls']
        rolled = sum(per_roll**r for r in range(low, high+1))/(high-low+1)
        result *= 1-pool['chance']+pool['chance']*rolled
    return result


def _expected(table, key):
    result = 0.0
    for pool in table['pools']:
        total = sum(e['weight'] for e in pool['entries'])
        per_roll = sum(e['weight']/total*(_expected(e['table'], key) if 'table' in e else
                                         _mean(e['counts']) if e.get('key') == key else 0)
                       for e in pool['entries'])
        result += pool['chance']*sum(pool['rolls'])/2*per_roll
    return result


def build(server_dir):
    """Return the vault model for the website or ``None`` with a reason."""
    server_dir = Path(server_dir)
    try:
        sources = _sources(server_dir)
        used = {}
        def lookup(table_id):
            name = table_path(table_id)
            found = [(label, data) for source, label in sources if (data := _read(source, name)) is not None]
            if not found: raise Unsupported('Beutetabelle fehlt: '+table_id)
            overrides = [label for label, _ in found if label != 'Minecraft']
            if len(overrides) > 1: raise Unsupported('Mehrere Datapacks ändern '+table_id)
            label, data = found[-1]
            if label != 'Minecraft': used[table_id] = label
            return json.loads(data)
        model = _compile(ROOT_TABLE, lookup)
        items = [{'key': key, 'item': e['item'], 'name': e['name'], 'detail': e['detail'],
                  'chance': 1-_absent(model, key), 'average': _expected(model, key)}
                 for key, e in _keys(model).items()]
        items.sort(key=lambda i: (-i['chance'], i['name']))
        core = next((i['chance'] for i in items if i['item'] == CORE), 0.0)
        return {'available': True, 'model': model, 'items': items, 'coreChance': core,
                'overrides': sorted(set(used.values()))}
    except (Unsupported, OSError, AttributeError, KeyError, TypeError, ValueError, zipfile.BadZipFile) as error:
        return {'available': False, 'reason': str(error) or type(error).__name__}
