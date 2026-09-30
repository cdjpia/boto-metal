"""Boto v3: casco visual + textura projetada das vistas de referencia.

As vistas em ref/v2/ (lateral, frente, baixo) sao silhuetas quase ortograficas do
mesmo boto. A intersecao das tres (o "casco visual") da uma forma que, por
construcao, bate com o contorno de cada vista - e ai da pra projetar as proprias
imagens como textura: chapas, rebites, cores e luzes saem da referencia.

  1. voxels: um ponto (x, y, z) fica se cair dentro da mascara lateral em (x, y),
     da de baixo em (x, z) e da frontal em (z, y)
  2. marching cubes + suavizacao leve + simplificacao (gltf-transform) -> low-poly
  3. xatlas -> UV; cada texel pega a cor da vista que melhor o enxerga (peso pela
     normal), textura final pequena, no espirito PS2
  4. mapa de emissao: pixels saturados e claros (bulbos, olhos, boca, LED)

Calibracao (medida nas mascaras; comprimento do boto = 2, bico em x = -1):
  lateral  xi = 1506 - (x+1)*740   yi = 500 - y*740
  baixo    xi = 1511 - (x+1)*743   zi = 484 - z*743
  frente   zi = 754 + z*979        yi = 443 - y*979   (perspectiva: mascara folgada)

  .venv/bin/python tools/casco.py
"""
import os, sys, json, struct, subprocess
import numpy as np
from PIL import Image
from scipy import ndimage
from skimage import measure

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.dirname(__file__))
from glb import ler, soldar

PASSO = 0.005
ALVO_TRIS = 6000
TEX = 512          # textura final (PS2)
TEX_BAKE = 1024    # resolucao do bake, reduzida no fim


def mascara(n, folga=0):
    m = np.load(os.path.join(RAIZ, 'ref', 'v2', n + '_mask.npy'))
    return ndimage.binary_dilation(m, iterations=folga) if folga else m


def imagem(n):
    return np.asarray(Image.open(os.path.join(RAIZ, 'ref', 'v2', n + '.webp')).convert('RGB')).astype(np.float32) / 255


VISTAS = {
    'side':   dict(px=lambda x, y, z: (1506 - (x + 1) * 740, 500 - y * 740)),
    'bottom': dict(px=lambda x, y, z: (1511 - (x + 1) * 743, 484 - z * 743)),
    'front':  dict(px=lambda x, y, z: (754 + z * 979, 443 - y * 979)),
}


def dentro(m, xi, yi):
    h, w = m.shape
    xi, yi = np.broadcast_arrays(np.round(xi).astype(int), np.round(yi).astype(int))
    ok = (xi >= 0) & (xi < w) & (yi >= 0) & (yi < h)
    out = np.zeros(xi.shape, bool)
    out[ok] = m[yi[ok], xi[ok]]
    return out


# ------------------------------------------------------------------ 1. voxels

xs = np.arange(-1.03, 1.03, PASSO)
ys = np.arange(-0.62, 0.47, PASSO)
zs = np.arange(-0.66, 0.66, PASSO)
S = dentro(mascara('side', 1), *VISTAS['side']['px'](xs[:, None], ys[None, :], 0))                 # (nx, ny)
B = dentro(mascara('bottom', 1), *VISTAS['bottom']['px'](xs[:, None], 0, zs[None, :]))             # (nx, nz)
Fm = mascara('front', 8)
zi, yi = VISTAS['front']['px'](0, ys[:, None], zs[None, :])
Fr = dentro(Fm, zi, yi)                                                           # (ny, nz)
vol = S[:, :, None] & B[:, None, :] & Fr[None, :, :]
vol = ndimage.binary_opening(vol, iterations=1)
# Tres silhuetas nao separam as nadadeiras do corpo: embaixo da barriga, entre as
# duas peitorais (e entre as ventrais), sobra um bloco que nenhuma vista corta.
# Esses vaos sao esculpidos a mao: abaixo da linha da barriga, perto do meio.
X3, Y3, Z3 = xs[:, None, None], ys[None, :, None], zs[None, None, :]
barriga = np.interp(xs, [-0.6, -0.42, -0.2, 0.0, 0.2, 0.4, 0.55], [-0.27, -0.27, -0.245, -0.225, -0.215, -0.225, -0.245])[:, None, None]
vol &= ~((X3 > -0.55) & (X3 < 0.12) & (Y3 < barriga) & (np.abs(Z3) < 0.21 - 0.35 * np.clip(barriga - Y3, 0, 1)))
vol &= ~((X3 > 0.08) & (X3 < 0.5) & (Y3 < barriga) & (np.abs(Z3) < 0.085))
print(f'voxels: {vol.sum():,} de {vol.size:,}')

# ------------------------------------------------------------------ 2. malha

pad = np.pad(vol, 2).astype(np.float32)
pad = ndimage.gaussian_filter(pad, 0.9)   # tira a escada do voxel antes do marching cubes
verts, faces, _, _ = measure.marching_cubes(pad, 0.5)
verts = (verts - 2) * PASSO + np.array([xs[0], ys[0], zs[0]])
print(f'marching cubes: {len(verts):,} vertices, {len(faces):,} triangulos')


def salvar_glb(caminho, malhas):
    bin_, views, accs, meshes, nodes = b'', [], [], [], []
    def add(arr, comp, tipo, alvo):
        nonlocal bin_
        arr = np.ascontiguousarray(arr)
        off = len(bin_)
        bin_ += arr.tobytes() + b'\0' * ((4 - arr.nbytes % 4) % 4)
        views.append({'buffer': 0, 'byteOffset': off, 'byteLength': arr.nbytes, 'target': alvo})
        accs.append({'bufferView': len(views) - 1, 'componentType': comp, 'count': len(arr), 'type': tipo})
        return len(accs) - 1
    for nome, m in malhas:
        at = {}
        ip = add(m['pos'].astype(np.float32), 5126, 'VEC3', 34962)
        accs[ip]['min'] = m['pos'].min(0).tolist(); accs[ip]['max'] = m['pos'].max(0).tolist()
        at['POSITION'] = ip
        if 'nrm' in m: at['NORMAL'] = add(m['nrm'].astype(np.float32), 5126, 'VEC3', 34962)
        if 'uv' in m: at['TEXCOORD_0'] = add(m['uv'].astype(np.float32), 5126, 'VEC2', 34962)
        prim = {'attributes': at}
        if 'idx' in m: prim['indices'] = add(m['idx'].astype(np.uint32).reshape(-1), 5125, 'SCALAR', 34963)
        meshes.append({'name': nome, 'primitives': [prim]})
        nodes.append({'name': nome, 'mesh': len(meshes) - 1})
    js = {'asset': {'version': '2.0', 'generator': 'boto-metal casco.py'}, 'scene': 0,
          'scenes': [{'nodes': list(range(len(nodes)))}], 'nodes': nodes, 'meshes': meshes,
          'buffers': [{'byteLength': len(bin_)}], 'bufferViews': views, 'accessors': accs}
    j = json.dumps(js, separators=(',', ':')).encode(); j += b' ' * ((4 - len(j) % 4) % 4)
    with open(caminho, 'wb') as f:
        f.write(struct.pack('<III', 0x46546C67, 2, 12 + 8 + len(j) + 8 + len(bin_)))
        f.write(struct.pack('<II', len(j), 0x4E4F534A)); f.write(j)
        f.write(struct.pack('<II', len(bin_), 0x004E4942)); f.write(bin_)


cru = os.path.join(RAIZ, 'build_casco_cru.glb')
low = os.path.join(RAIZ, 'build_casco.glb')
salvar_glb(cru, [('casco', {'pos': verts, 'idx': faces})])
razao = min(1.0, ALVO_TRIS / len(faces))
subprocess.run([os.path.join(RAIZ, 'node_modules', '.bin', 'gltf-transform'), 'simplify', cru, low,
                '--ratio', f'{razao:.4f}', '--error', '0.01'], check=True, capture_output=True)
pos, tris = ler(low)
V, F = soldar(pos, tris)
print(f'low-poly: {len(V):,} vertices, {len(F):,} triangulos')
np.savez(os.path.join(RAIZ, 'build_casco.npz'), V=V, F=F)

# ------------------------------------------------------------------ 3. UV + textura projetada

import xatlas
VN = np.zeros_like(V)
fnrm = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
for k in range(3):
    np.add.at(VN, F[:, k], fnrm)
VN /= np.maximum(np.linalg.norm(VN, axis=1, keepdims=True), 1e-12)
# o marching cubes devolve a malha virada pra dentro (normal no sentido do
# gradiente, que cresce pra dentro do volume): desvira normais e ordem dos vertices
if np.sum(VN * (V - V.mean(0))) < 0:
    VN, F = -VN, F[:, [0, 2, 1]]

atlas = xatlas.Atlas()
atlas.add_mesh(V.astype(np.float32), F.astype(np.uint32), VN.astype(np.float32))
po = xatlas.PackOptions(); po.resolution = TEX_BAKE; po.padding = 6; po.bilinear = True
atlas.generate(pack_options=po)
vmap, IDX, UV = atlas[0]
PV, PN = V[vmap], VN[vmap]
print(f'atlas: {atlas.chart_count} charts')

R = TEX_BAKE
tri_de = np.full((R, R), -1, np.int32)
bar = np.zeros((R, R, 3), np.float32)
uvp = UV * R
for t, (a, b, c) in enumerate(IDX):
    pa, pb, pc = uvp[a], uvp[b], uvp[c]
    x0, x1 = max(int(min(pa[0], pb[0], pc[0])) - 1, 0), min(int(max(pa[0], pb[0], pc[0])) + 1, R - 1)
    y0, y1 = max(int(min(pa[1], pb[1], pc[1])) - 1, 0), min(int(max(pa[1], pb[1], pc[1])) + 1, R - 1)
    gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
    d = (pb[1] - pc[1]) * (pa[0] - pc[0]) + (pc[0] - pb[0]) * (pa[1] - pc[1])
    if abs(d) < 1e-12:
        continue
    l1 = ((pb[1] - pc[1]) * (gx - pc[0]) + (pc[0] - pb[0]) * (gy - pc[1])) / d
    l2 = ((pc[1] - pa[1]) * (gx - pc[0]) + (pa[0] - pc[0]) * (gy - pc[1])) / d
    l3 = 1 - l1 - l2
    ok = (l1 >= -1e-4) & (l2 >= -1e-4) & (l3 >= -1e-4)
    yy, xx = np.nonzero(ok)
    tri_de[y0 + yy, x0 + xx] = t
    bar[y0 + yy, x0 + xx] = np.stack([l1[ok], l2[ok], l3[ok]], -1)
cheio = tri_de >= 0
iy, ix = np.nonzero(cheio)
tt, bb = tri_de[iy, ix], bar[iy, ix]
P = PV[IDX[tt, 0]] * bb[:, :1] + PV[IDX[tt, 1]] * bb[:, 1:2] + PV[IDX[tt, 2]] * bb[:, 2:3]
N = PN[IDX[tt, 0]] * bb[:, :1] + PN[IDX[tt, 1]] * bb[:, 1:2] + PN[IDX[tt, 2]] * bb[:, 2:3]
N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
x, y, z = P[:, 0], P[:, 1], P[:, 2]

# Profundidade de cada vista, tirada dos proprios voxels: um texel so recebe a cor
# de uma vista se for a superficie mais proxima dela naquele pixel. Sem isso a
# nadadeira pintaria o corpo que esta atras dela.
def indice(v, eixo):
    return np.clip(np.round((v - eixo[0]) / PASSO).astype(int), 0, len(eixo) - 1)

def extremo(ocupado, eixo_len, maior):
    # indice do primeiro/ultimo voxel cheio ao longo do ultimo eixo; -1 se vazio
    tem = ocupado.any(-1)
    idx = (eixo_len - 1 - np.argmax(ocupado[..., ::-1], -1)) if maior else np.argmax(ocupado, -1)
    return np.where(tem, idx, -1)

zmax = extremo(vol, len(zs), True)                          # (nx, ny)
zmin = extremo(vol, len(zs), False)
ymin = extremo(np.transpose(vol, (0, 2, 1)), len(ys), False)  # (nx, nz)
xmin = extremo(np.transpose(vol, (1, 2, 0)), len(xs), False)  # (ny, nz)
TOL = 0.025
IX, IY, IZ = indice(x, xs), indice(y, ys), indice(z, zs)
vis_lado_mais = (zmax[IX, IY] >= 0) & (z >= zs[zmax[IX, IY]] - TOL)
vis_lado_menos = (zmin[IX, IY] >= 0) & (z <= zs[zmin[IX, IY]] + TOL)
vis_baixo = (ymin[IX, IZ] >= 0) & (y <= ys[ymin[IX, IZ]] + TOL)
vis_frente = (xmin[IY, IZ] >= 0) & (x <= xs[xmin[IY, IZ]] + TOL)

IMG = {n: imagem(n) for n in ('side', 'bottom', 'front')}

def amostrar(n, px):
    im = IMG[n]
    xi, yi = px
    xi = np.clip(xi, 0, im.shape[1] - 1.001); yi = np.clip(yi, 0, im.shape[0] - 1.001)
    x0, y0 = np.floor(xi).astype(int), np.floor(yi).astype(int)
    fx, fy = (xi - x0)[:, None], (yi - y0)[:, None]
    return (im[y0, x0] * (1 - fx) * (1 - fy) + im[y0, x0 + 1] * fx * (1 - fy)
            + im[y0 + 1, x0] * (1 - fx) * fy + im[y0 + 1, x0 + 1] * fx * fy)

EXP = 3
lado = np.where(z >= 0, vis_lado_mais, vis_lado_menos)
w_lado = np.abs(N[:, 2]) ** EXP * lado + 1e-4 * lado
# o topo nao tem vista propria: a lateral ve o dorso de raspao (faixa e bulbos
# no alto, magenta nos flancos), entao ela cobre o que olha pra cima
w_lado += np.clip(N[:, 1], 0, 1) ** EXP * lado
w_baixo = np.clip(-N[:, 1], 0, 1) ** EXP * vis_baixo
w_frente = np.clip(-N[:, 0], 0, 1) ** EXP * vis_frente
c_lado = amostrar('side', VISTAS['side']['px'](x, y, z))
c_baixo = amostrar('bottom', VISTAS['bottom']['px'](x, y, np.abs(z)))
c_frente = amostrar('front', VISTAS['front']['px'](x, y, z))
soma = w_lado + w_baixo + w_frente
cor = (c_lado * w_lado[:, None] + c_baixo * w_baixo[:, None] + c_frente * w_frente[:, None]) / np.maximum(soma, 1e-9)[:, None]
# sem vista nenhuma (atras das nadadeiras, traseira, dentro da boca): herda a cor
# do texel visto mais proximo em 3D, levemente escurecida - a chapa continua
from scipy.spatial import cKDTree
cego = soma < 1e-3
if cego.any():
    vistos = np.nonzero(~cego)[0]
    _, j = cKDTree(P[vistos]).query(P[cego])
    cor[cego] = cor[vistos[j]] * 0.85
# fundo branco que vaza na borda da silhueta vira aco
branco = (cor.min(1) > 0.86)
cor[branco] = (0.45, 0.44, 0.45)
print(f'texels: {len(P):,}  sem vista: {cego.mean():.1%}  borda branca: {branco.mean():.1%}')

# emissao: laranja/vermelho (bulbos, olhos, boca) e azul (LED) - nunca o magenta
mx, mn = cor.max(1), cor.min(1)
sat = (mx - mn) / np.maximum(mx, 1e-6)
r, g, b = cor[:, 0], cor[:, 1], cor[:, 2]
laranja = (r >= g) & (g >= b) & (r > 0.75) & (sat > 0.55)
azul = (b > r + 0.15) & (b > 0.6) & (sat > 0.45)
brilho = np.zeros_like(cor)
brilho[laranja | azul] = cor[laranja | azul]
k = np.clip((mx - 0.6) / 0.4, 0, 1)[:, None]
brilho *= k


def gravar(valores, nome, q=90):
    img = np.zeros((R, R, 3), np.float32)
    img[iy, ix] = valores
    _, (jy, jx) = ndimage.distance_transform_edt(~cheio, return_indices=True)
    img = img[jy, jx]
    Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)[::-1]).resize((TEX, TEX), Image.LANCZOS).save(
        os.path.join(RAIZ, 'public', nome), quality=q)


gravar(cor, 'boto3_color.jpg')
gravar(brilho, 'boto3_glow.jpg')
salvar_glb(os.path.join(RAIZ, 'public', 'boto3.glb'), [('boto', {'pos': PV, 'nrm': PN, 'uv': UV, 'idx': IDX})])
print('ok -> public/boto3.glb, boto3_color.jpg, boto3_glow.jpg')
