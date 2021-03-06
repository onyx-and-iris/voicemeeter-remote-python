import ctypes as ct
import time
import abc

from .driver import dll
from .errors import VMRError, VMRDriverError
from .strip import InputStrip
from .bus import OutputBus
from .recorder import Recorder
from .macrobutton import MacroButton
from .vban import Vban
from . import kinds
from . import profiles
from .util import merge_dicts, polling

from typing import Union

class VMRemote(abc.ABC):
    """ Wrapper around Voicemeeter Remote's C API. """
    def __init__(self, delay: float, max_polls: int):
        self.delay = delay
        self.max_polls = max_polls
        self.cache = {}

    def _call(self, fn: str, *args: list, check: bool=True, expected: tuple=(0,)) -> int:
        """
        Runs a C API function.

        Raises an exception when check is True and the
        function's return value is not 0 (OK).
        """
        fn_name = 'VBVMR_' + fn
        retval = getattr(dll, fn_name)(*args)
        if check and retval not in expected:
            raise VMRDriverError(fn_name, retval)
        if '_Get' in fn_name:
            time.sleep(self.delay)

        return retval

    def login(self):
        self._call('Login')
        while self.mdirty or self.pdirty:
            pass
    def logout(self):
        time.sleep(0.02)
        self._call('Logout')


    @property
    def type(self) -> str:
        """ Returns the type of Voicemeeter installation (basic, banana, potato). """
        buf = ct.c_long()
        self._call('GetVoicemeeterType', ct.byref(buf))
        val = buf.value
        if val == 1:
            return 'basic'
        elif val == 2:
            return 'banana'
        elif val == 3:
            return 'potato'
        else:
            raise VMRError(f'Unexpected Voicemeeter type: {val}')

    @property
    def version(self) -> tuple:
        """ Returns Voicemeeter's version as a tuple (v1, v2, v3, v4) """
        buf = ct.c_long()
        self._call('GetVoicemeeterVersion', ct.byref(buf))
        v1 = (buf.value & 0xFF000000) >> 24
        v2 = (buf.value & 0x00FF0000) >> 16
        v3 = (buf.value & 0x0000FF00) >> 8
        v4 = (buf.value & 0x000000FF)
        return (v1, v2, v3, v4)

    @property
    def pdirty(self) -> bool:
        """ True iff UI parameters have been updated. """
        return (self._call('IsParametersDirty', expected=(0,1)) == 1)
    @property
    def mdirty(self) -> bool:
        """ True iff MB parameters have been updated. """
        return (self._call('MacroButton_IsDirty', expected=(0,1)) == 1)

    @polling
    def get(self, param: str, string=False) -> Union[str, float]:
        """ Retrieves a parameter from cache if pdirty else run getter """
        param = param.encode('ascii')
        if string:
            buf = (ct.c_wchar * 512)()
            self._call('GetParameterStringW', param, ct.byref(buf))
        else:
            buf = ct.c_float()
            self._call('GetParameterFloat', param, ct.byref(buf))

        return buf.value

    def set(self, param: str, val: Union[str, float]):
        """ Updates a parameter. Attempts to cache value """
        if isinstance(val, str):
            if len(val) >= 512:
                raise VMRError('String is too long')
            self._call('SetParameterStringW', param.encode('ascii'), ct.c_wchar_p(val))
        else:
            self._call('SetParameterFloat', param.encode('ascii'), ct.c_float(float(val)))

        self.cache[param] = [True, val]

    def setmulti(self, params: dict):
        """ alternative set many through dict """
        if not isinstance(params, dict):
                raise VMRError('Error, expected a dictionary')

        param_string = str()
        for key, val in params.items():
            m = key.split("-")
            if m[0] == 'in':
                identifier = f'Strip[{m[1]}]'
            elif m[0] == 'out':
                identifier = f'Bus[{m[1]}]'
                val['EQ.on'] = val.pop('eq', None)
            elif m[0] == 'vban':
                identifier = f'{m[0]}.{m[1]}stream[{m[2]}]'

            for k, v in val.items():
                if v is not None:
                    param_string += f'{identifier}.{k}={float(v)};'
                    self.cache[f'{identifier}.{k}'] = [True, float(v)]
            self._call('SetParameters', param_string.encode('ascii'))
            param_string = str()


    def show(self):
        """ Shows Voicemeeter if it's hidden. """
        self.set('Command.Show', 1)
    def shutdown(self):
        """ Closes Voicemeeter. """
        self.set('Command.Shutdown', 1)
    def restart(self):
        """ Restarts Voicemeeter's audio engine. """
        self.set('Command.Restart', 1)

    def apply(self, mapping: dict):
        """ Sets all parameters of a di """
        for key, submapping in mapping.items():
            strip, index = key.split('-')
            index = int(index)
            if strip in ('in', 'input'):
                target = self.strip[index]
            elif strip in ('out', 'output'):
                target = self.bus[index]
            else:
                raise ValueError(strip)
            target.apply(submapping)

    def apply_profile(self, name):
        try:
            profile = self.profiles[name]
            if 'extends' in profile:
                base = self.profiles[profile['extends']]
                profile = merge_dicts(base, profile)
                del profile['extends']
            self.apply(profile)
        except KeyError:
            raise VMRError(f'Unknown profile: {self.kind.id}/{name}')

    @polling
    def button_getstatus(self, logical_id: int, mode: int) -> int:
        c_logical_id = ct.c_long(logical_id)
        c_state = ct.c_float()
        c_mode = ct.c_long(mode)

        self._call('MacroButton_GetStatus', c_logical_id, ct.byref(c_state), c_mode)

        return int(c_state.value)

    def button_setstatus(self, logical_id: int, state: int, mode: int):
        c_logical_id = ct.c_long(logical_id)
        c_state = ct.c_float(float(state))
        c_mode = ct.c_long(mode)

        self._call('MacroButton_SetStatus', c_logical_id, c_state, c_mode)
        param = f'mb_{logical_id}_{mode}'
        self.cache[param] = [True, int(c_state.value)]

    def show_vbanchat(self, state: int):
        if state not in (0, 1):
            raise VMRError('State must be 0 or 1')

        self.set('Command.DialogShow.VBANCHAT', state)


    def reset(self):
        self.apply_profile('base')

    def __enter__(self):
        self.login()
        return self

    def __exit__(self, type, value, traceback):
        self.logout()


def _make_remote(kind) -> 'instanceof(VMRemote)':
    """
    Creates a new remote class and sets its number of inputs
    and outputs for a VM kind.

    The returned class will subclass VMRemote.
    """
    def init(self, *args: list, **kwargs: dict):
        VMRemote.__init__(self, *args, **kwargs)
        self.kind = kind
        self.num_A, self.num_B = kind.layout
        self.strip = \
        tuple(InputStrip.make((i < self.num_A), self, i)
        for i in range(self.num_A + self.num_B))
        self.bus = \
        tuple(OutputBus.make((i < self.num_B), self, i)
        for i in range(self.num_A + self.num_B))
        self.recorder = Recorder(self)
        self.button = tuple(MacroButton(self, i) for i in range(70))
        self.num_vban_in, self.num_vban_out = kind.vban
        self.vban_in = tuple(Vban(self, i, "in") for i in range(self.num_vban_in))
        self.vban_out = tuple(Vban(self, i, "out") for i in range(self.num_vban_out))
    def get_profiles(self):
        return profiles.profiles[kind.id]

    return type(f'VMRemote{kind.name}', (VMRemote,), {
        '__init__': init,
        'profiles': property(get_profiles)
    })

_remotes = {kind.id: _make_remote(kind) for kind in kinds.all}

def connect(kind_id, delay: float=.001, max_polls: int=8):
    """ Connect to Voicemeeter and sets its strip layout. """
    try:
        cls = _remotes[kind_id]
        return cls(delay=delay, max_polls=max_polls)
    except KeyError as err:
        raise VMRError(f'Invalid Voicemeeter kind: {kind_id}')
