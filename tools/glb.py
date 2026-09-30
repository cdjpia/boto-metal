# Leitura minima de GLB (so POSITION, com ou sem indices) -> numpy.
import json, struct, numpy as np

def ler(path):
    b = open(path, 'rb').read()
    n = struct.unpack_from('<I', b, 12)[0]
    js = json.loads(b[20:20 + n])
    off = 20 + n
    blen = struct.unpack_from('<I', b, off)[0]
    bin_ = b[off + 8: off + 8 + blen]
    prim = js['meshes'][0]['primitives'][0]
    def acc(i, comps):
        a = js['accessors'][i]; bv = js['bufferViews'][a['bufferView']]
        st = bv.get('byteOffset', 0) + a.get('byteOffset', 0)
        dt = {5126: np.float32, 5125: np.uint32, 5123: np.uint16}[a['componentType']]
        return np.frombuffer(bin_, dt, a['count'] * comps, st).reshape(-1, comps) if comps > 1 else np.frombuffer(bin_, dt, a['count'], st)
    pos = acc(prim['attributes']['POSITION'], 3).astype(np.float64)
    idx = acc(prim['indices'], 1).astype(np.int64) if 'indices' in prim else np.arange(len(pos))
    return pos, idx.reshape(-1, 3)

def soldar(pos, tris, casas=5):
    chave = np.round(pos, casas)
    uniq, inv = np.unique(chave, axis=0, return_inverse=True)
    return uniq, inv.reshape(-1)[tris]

def componentes(nv, tris):
    pai = np.arange(nv)
    def raiz(i):
        while pai[i] != i:
            pai[i] = pai[pai[i]]; i = pai[i]
        return i
    for a, b, c in tris:
        ra, rb, rc = raiz(a), raiz(b), raiz(c)
        pai[rb] = ra; pai[raiz(rc)] = ra
    r = np.array([raiz(i) for i in range(nv)])
    return r
