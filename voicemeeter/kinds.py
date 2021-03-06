from collections import namedtuple
from .errors import VMRError
from .driver import bits

"""
Represents a major version of Voicemeeter and describes
its strip layout.
"""
VMKind = namedtuple('VMKind', ['id', 'name', 'layout', 'executable', 'vban'])

_kind_map = {
  'basic': VMKind('basic', 'Basic', (2,1), 'voicemeeter.exe', (4, 4)),
  'banana': VMKind('banana', 'Banana', (3,2), 'voicemeeterpro.exe', (8, 8)),
  'potato': VMKind('potato', 'Potato', (5,3),
  f'voicemeeter8{"x64" if bits == 64 else ""}.exe', (8, 8))
}

def get(kind_id):
    try:
        return _kind_map[kind_id]
    except KeyError:
        raise VMRError(f'Invalid Voicemeeter kind: {kind_id}')

all = list(_kind_map.values())
