import glob, hashlib, json, os, sys

FORMAT = 1
MAX_VARIANTS = 8


def sha1(data):
    return hashlib.sha1(data).hexdigest()


def code_digest():
    h = hashlib.sha1(f'{FORMAT} {sys.version}'.encode())
    for path in sorted(glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), '*.py'))):
        h.update(os.path.basename(path).encode())
        with open(path, 'rb') as f:
            h.update(hashlib.sha1(f.read()).digest())
    return h.hexdigest()


def _norm(value):
    return json.loads(json.dumps(value))


class _Recorder:
    def __init__(self, d):
        self._d, self.read = d, set()

    def __getitem__(self, name):
        self.read.add(name)
        return self._d[name]

    def get(self, name, default=None):
        self.read.add(name)
        return self._d.get(name, default)

    def __contains__(self, name):
        self.read.add(name)
        return name in self._d


class Cache:
    def __init__(self, path=None):
        self.path, self.code, self.dirty, self.hits, self.misses = path, code_digest(), False, 0, 0
        self.entries = {}
        if path:
            try:
                with open(path, encoding='utf-8') as f:
                    d = json.load(f)
                if isinstance(d, dict) and d.get('code') == self.code and isinstance(d.get('entries'), dict):
                    self.entries = d['entries']
            except (OSError, ValueError):
                pass

    def get(self, kind, key, compute):
        name = f'{kind} {key}'
        if name in self.entries:
            self.hits += 1
            return _norm(self.entries[name])
        self.misses += 1
        value = _norm(compute())
        self.entries[name] = value
        self.dirty = True
        return _norm(value)

    def get_variant(self, kind, key, options, compute, valid=None):
        name = f'{kind} {key}'
        variants = self.entries.get(name, [])
        for v in variants:
            if all(n in options and _norm(options[n]) == want for n, want in v['deps'].items()) \
                    and (valid is None or valid(_norm(v['value']))):
                self.hits += 1
                return _norm(v['value'])
        self.misses += 1
        view = _Recorder(options)
        value = _norm(compute(view))
        deps = {n: _norm(options[n]) for n in sorted(view.read)}
        variants = [v for v in variants if v['deps'] != deps]
        self.entries[name] = ([{'deps': deps, 'value': value}] + variants)[:MAX_VARIANTS]
        self.dirty = True
        return _norm(value)

    def save(self):
        if not self.path or not self.dirty:
            return
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump({'code': self.code, 'entries': self.entries}, f)
        os.replace(tmp, self.path)
        self.dirty = False
