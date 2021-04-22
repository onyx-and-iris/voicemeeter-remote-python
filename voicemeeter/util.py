import os
import time
from functools import wraps

PROJECT_DIR = os.path.realpath(os.path.join(os.path.dirname(os.path.realpath(__file__)), '..'))

def project_path(*parts):
    return os.path.join(PROJECT_DIR, *parts)

def merge_dicts(*srcs, dest={}):
    target = dest
    for src in srcs:
        for key, val in src.items():
            if isinstance(val, dict):
                node = target.setdefault(key, {})
                merge_dicts(val, dest=node)
            else:
                target[key] = val
    return target

def polling(func):
    """ check if recently cached was an updated value """
    @wraps(func)
    def wrapper(*args, **kwargs):
        get = False
        mb_get = False
        if func.__name__ == 'get':
            get = True
            _remote, param, *remaining = args
        elif func.__name__ == 'button_getstatus':
            mb_get = True
            _remote, logical_id, mode = args
            param = f'mb_{logical_id}_{mode}'

        if param in _remote.cache and _remote.cache[param][0]:
            _remote.cache[param][0] = False
            for i in range(_remote.max_polls):
                if get and _remote.pdirty \
                or mb_get and _remote.mdirty:
                    return _remote.cache[param][1]
                time.sleep(_remote.delay)
        elif param in _remote.cache and get and _remote.pdirty \
        or param in _remote.cache and mb_get and _remote.mdirty:
            return _remote.cache[param][1]


        res = func(*args, **kwargs)

        _remote.cache[param] = [False, res]

        return _remote.cache[param][1]
    return wrapper
