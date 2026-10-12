"""Match station names written by DMRC, police or press to OpenStreetMap metro stop names."""
import re

# Map normalised written spellings to normalised OSM spellings where they differ.
ALIASES = {
    "jasola": ["jasolaviharshaheenbagh"], "barakhambaroad": ["barakhambharoad"], "chawribazar": ["chawribazaar"],
    "jafrabad": ["jaffrabad"], "ina": ["dillihaatina"], "dillihaatina": ["dillihaatina"],
    "rkashrammarg": ["ramakrishnaashrammarg"], "sevateerthudyogbhawan": ["sevateerth"], "udyogbhawan": ["sevateerth"],
    "saraikalekhannizamuddin": ["saraikalekhannizamuddin"], "maujpur": ["maujpurbabarpur"],
    "maujpurbabarpur": ["maujpurbabarpur"], "guruteghbahadurnagar": ["gtbnagar"], "guruteg bahadurnagar": ["gtbnagar"],
    "gurutegbahadurnagar": ["gtbnagar"], "rohini": ["rohinieast"], "drbabasahebambedkarhospital": ["rohiniwest"],
    "lalquila": ["lalquila"],
}


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def match(written, names, stops):
    """Return the OSM stop ids for one written station name, trying exact then prefix matches."""
    keys = ALIASES.get(norm(written), [norm(written)])
    for exact in (True, False):
        hits = [sid for sid, nm in names.items() if sid in stops and any(
            (norm(nm) == k) if exact else norm(nm).startswith(k) for k in keys)]
        if hits:
            return hits
    return []
