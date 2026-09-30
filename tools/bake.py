"""Bake da textura "PS2" do boto-aparelhagem.

A malha (boto.glb) nao tem UV nem material, e a pose dela nao bate com as imagens
de referencia (mandibula, barriga e cauda diferentes), entao nao da pra projetar as
imagens direto. Em vez disso a textura e pintada aqui, peca por peca, com a
referencia como fonte de paleta e de granulado:

  1. build_mid.glb (decimada ~18k tris) e desembrulhada com xatlas -> UV
  2. cada texel do atlas vira um ponto 3D (posicao + normal)
  3. chapas: Voronoi de sementes espalhadas na superficie (~0.11 de lado); a cor
     e decidida POR CHAPA, entao a borda entre magenta e aco cai sempre numa costura
  4. costura escura + bisel + fileira de rebites ao longo de cada borda de chapa
  5. granulado copiado da referencia: recortes sem costura das imagens em ref/,
     um por chapa, mapeados no plano da chapa
  6. regioes especiais por texel: bulbos, faixa de cobre, olhos, boca, dentes e a
     grade de LED das nadadeiras - e o mapa de emissao pra essas mesmas regioes

Saida em public/: boto.glb (com UV e normais), boto_color.png, boto_glow.png

  .venv/bin/python tools/bake.py [RESOLUCAO]
"""
import sys, json, struct, os
import numpy as np
import xatlas
from PIL import Image
from scipy.spatial import cKDTree
from scipy import ndimage

sys.path.insert(0, os.path.dirname(__file__))
from glb import ler, soldar

RAIZ = os.path.join(os.path.dirname(__file__), '..')
R = int(sys.argv[1]) if len(sys.argv) > 1 else 1024
rng = np.random.default_rng(7)
os.makedirs(os.path.join(RAIZ, 'public'), exist_ok=True)


def norm(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def smooth(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def hexrgb(h):
    return np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)], float) / 255


# ------------------------------------------------------------------ malha + UV

pos, tris = ler(os.path.join(RAIZ, 'build_mid.glb'))
V, F = soldar(pos, tris)
fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
VN = np.zeros_like(V)
for k in range(3):
    np.add.at(VN, F[:, k], fn)
VN = norm(VN)
print(f'malha: {len(V)} vertices, {len(F)} triangulos')

atlas = xatlas.Atlas()
atlas.add_mesh(V.astype(np.float32), F.astype(np.uint32), VN.astype(np.float32))
po = xatlas.PackOptions()
po.resolution = R
po.padding = 4
po.bilinear = True
co = xatlas.ChartOptions()
co.max_iterations = 2
atlas.generate(chart_options=co, pack_options=po)
vmap, IDX, UV = atlas[0]
PV, PN = V[vmap], VN[vmap]
print(f'atlas: {len(PV)} vertices apos cortes de UV, {atlas.chart_count} charts')

# ------------------------------------------------------------------ rasterizacao

# Pra cada triangulo em espaco UV, os texels cujo centro cai dentro dele. Guardamos
# o indice do triangulo e as baricentricas -> posicao e normal 3D por texel.
tri_de = np.full((R, R), -1, np.int32)
bar = np.zeros((R, R, 3), np.float32)
uvp = UV * R
for t, (a, b, c) in enumerate(IDX):
    pa, pb, pc = uvp[a], uvp[b], uvp[c]
    x0, x1 = int(np.floor(min(pa[0], pb[0], pc[0]))), int(np.ceil(max(pa[0], pb[0], pc[0])))
    y0, y1 = int(np.floor(min(pa[1], pb[1], pc[1]))), int(np.ceil(max(pa[1], pb[1], pc[1])))
    x0, y0 = max(x0, 0), max(y0, 0)
    x1, y1 = min(x1, R - 1), min(y1, R - 1)
    if x1 < x0 or y1 < y0:
        continue
    gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
    d = (pb[1] - pc[1]) * (pa[0] - pc[0]) + (pc[0] - pb[0]) * (pa[1] - pc[1])
    if abs(d) < 1e-12:
        continue
    l1 = ((pb[1] - pc[1]) * (gx - pc[0]) + (pc[0] - pb[0]) * (gy - pc[1])) / d
    l2 = ((pc[1] - pa[1]) * (gx - pc[0]) + (pa[0] - pc[0]) * (gy - pc[1])) / d
    l3 = 1 - l1 - l2
    dentro = (l1 >= -1e-4) & (l2 >= -1e-4) & (l3 >= -1e-4)
    ys, xs = np.nonzero(dentro)
    tri_de[y0 + ys, x0 + xs] = t
    bar[y0 + ys, x0 + xs] = np.stack([l1[dentro], l2[dentro], l3[dentro]], -1)

cheio = tri_de >= 0
iy, ix = np.nonzero(cheio)
tt = tri_de[iy, ix]
bb = bar[iy, ix]
P = (PV[IDX[tt, 0]] * bb[:, :1] + PV[IDX[tt, 1]] * bb[:, 1:2] + PV[IDX[tt, 2]] * bb[:, 2:3])
N = norm(PN[IDX[tt, 0]] * bb[:, :1] + PN[IDX[tt, 1]] * bb[:, 1:2] + PN[IDX[tt, 2]] * bb[:, 2:3])
x, y, z = P[:, 0], P[:, 1], P[:, 2]
az = np.abs(z)
print(f'texels ocupados: {len(P)} ({len(P) / R / R:.0%})')

# ------------------------------------------------------------------ paleta (da referencia)

# Cores medianas medidas nas imagens de ref/ (miolo das chapas, sem costura).
COBRE = hexrgb('#7A5230')
COSTURA = hexrgb('#1A1418')
LARANJA = hexrgb('#FF7A12')
BOCA = hexrgb('#FF3A10')
DENTE = hexrgb('#E9D6BE')
LED = hexrgb('#1E7BFF')
LED_FUNDO = hexrgb('#16204A')

# ------------------------------------------------------------------ granulado da referencia

# Recortes quadrados SEM costura das imagens de referencia: janelas com gradiente
# baixo (nenhuma linha escura cruzando) e matiz certo. Cada chapa recebe um deles
# como detalhe de alta frequencia (recorte / recorte borrado), e a mediana dos
# recortes vira a cor base - a paleta sai da propria referencia.
def recortes(caminhos, filtro, n=24, lado=40):
    out = []
    for c in caminhos:
        im = np.asarray(Image.open(c).convert('RGBA')).astype(float) / 255
        rgb, a = im[..., :3], im[..., 3]
        lum = rgb @ [0.3, 0.59, 0.11]
        gm = np.hypot(ndimage.sobel(lum, 0), ndimage.sobel(lum, 1))
        cand = []
        for yy in range(0, im.shape[0] - lado, lado // 2):
            for xx in range(0, im.shape[1] - lado, lado // 2):
                if a[yy:yy + lado, xx:xx + lado].min() < 0.99:
                    continue
                bloco = rgb[yy:yy + lado, xx:xx + lado]
                if not filtro(bloco.reshape(-1, 3).mean(0)):
                    continue
                if lum[yy:yy + lado, xx:xx + lado].min() < 0.12:  # costura escura
                    continue
                cand.append((gm[yy:yy + lado, xx:xx + lado].max(), bloco))
        cand.sort(key=lambda c: c[0])
        out += [b for _, b in cand[:n]]
    det = [1 + 0.55 * (np.clip(b / np.maximum(ndimage.gaussian_filter(b, (6, 6, 0)), 1e-3), 0.55, 1.45) - 1) for b in out]
    media = np.median([b.reshape(-1, 3).mean(0) for b in out], axis=0)
    return det, media


refs = [os.path.join(RAIZ, 'ref', f) for f in ('LEFT.png', 'RIGHT.png', 'FRONT.png', 'BACK.png')]
eh_rosa = lambda m: m[0] > 0.45 and m[2] > 0.3 and m[1] < 0.35
eh_cinza = lambda m: abs(m[0] - m[1]) < 0.06 and abs(m[1] - m[2]) < 0.08 and 0.25 < m[1] < 0.75
GR_ROSA, MAGENTA = recortes(refs, eh_rosa)
MAGENTA = MAGENTA * 0.85 + np.array([0.5, 0.45, 0.5]) * 0.15 * MAGENTA.mean()   # um tom menos chiclete
GR_CINZA, ACO = recortes(refs, eh_cinza)
ACO = ACO * 0.78   # o aco do video e mais escuro que o das vistas de ref/
print(f'granulado: {len(GR_ROSA)} recortes magenta {np.round(MAGENTA * 255)}, {len(GR_CINZA)} de aco {np.round(ACO * 255)}')

# ------------------------------------------------------------------ anatomia

# Faixa de cobre do dorso: altura do topo medida nas bordas da faixa (|z| 0.05..0.07),
# onde os bulbos (centrados em z=0) nao chegam.
m = (np.abs(V[:, 2]) > 0.045) & (np.abs(V[:, 2]) < 0.07) & (V[:, 0] > -0.3) & (V[:, 0] < 0.62) & (V[:, 1] > 0.1)
bx = np.round(V[m, 0] / 0.02)
topo = {k: V[m][bx == k, 1].max() for k in np.unique(bx)}
kx = np.array(sorted(topo)) * 0.02
ky = np.array([topo[k] for k in sorted(topo)])
faixa_y = lambda xx: np.interp(xx, kx, ky)

# Bulbos: picos do perfil da linha do meio (|z| pequeno) acima da faixa. Cada pico
# e o topo de um bulbo; a largura do pico a meia altura da o raio.
from scipy.signal import find_peaks
meio_ = (az < 0.008) & (x > -0.28) & (x < 0.66) & (y > faixa_y(x) - 0.01)
PASSO = 0.002
bins = np.round(x[meio_] / PASSO).astype(int)
perfil = np.full(bins.max() - bins.min() + 1, -1.0)
np.maximum.at(perfil, bins - bins.min(), y[meio_])
xs_ = (np.arange(len(perfil)) + bins.min()) * PASSO
ok = perfil > -1
perfil = np.interp(xs_, xs_[ok], perfil[ok])
acima = perfil - faixa_y(xs_)
picos, prop = find_peaks(acima, height=0.012, distance=int(0.03 / PASSO), width=3, rel_height=0.9)
BULBOS = []
for pk in picos:
    # o bulbo assenta na faixa: diametro ~ altura do pico acima dela
    r = float(np.clip(acima[pk] / 2, 0.012, 0.034))
    BULBOS.append((np.array([xs_[pk], perfil[pk] - r, 0.0]), r))
print(f'bulbos detectados: {len(BULBOS)}  raios {[round(float(r), 3) for _, r in BULBOS]}')

# Relevo: quanto cada vertice sai da versao suavizada da malha, ao longo da normal.
# Dentes e bulbos sao picos claros disso.
import scipy.sparse as sp
ii = np.concatenate([F[:, 0], F[:, 1], F[:, 2], F[:, 1], F[:, 2], F[:, 0]])
jj = np.concatenate([F[:, 1], F[:, 2], F[:, 0], F[:, 0], F[:, 1], F[:, 2]])
Adj = sp.coo_matrix((np.ones(len(ii)), (ii, jj)), shape=(len(V), len(V))).tocsr()
Adj.data[:] = 1
Adj = sp.diags(1 / np.asarray(Adj.sum(1)).ravel()) @ Adj
Vs = V.copy()
for _ in range(12):
    Vs = 0.5 * Vs + 0.5 * (Adj @ Vs)
RELEVO_V = ((V - Vs) * VN).sum(1)
rel_pv = RELEVO_V[vmap]
relevo = rel_pv[IDX[tt, 0]] * bb[:, 0] + rel_pv[IDX[tt, 1]] * bb[:, 1] + rel_pv[IDX[tt, 2]] * bb[:, 2]

# Olhos: aro visto de lado centrado em (-0.47, 0.12), um de cada lado.
OLHO_X, OLHO_Y, OLHO_R_LENTE, OLHO_R_ARO = -0.47, 0.12, 0.044, 0.064

# Boca: linhas das bordas das mandibulas, lidas da vista lateral.
BORDA_SUP = lambda xx: np.interp(xx, [-1.0, -0.55, -0.44], [-0.125, -0.025, -0.005])
BORDA_INF = lambda xx: np.interp(xx, [-0.9, -0.55, -0.44], [-0.215, -0.085, -0.035])

# ------------------------------------------------------------------ chapas

# Sementes por disco de Poisson sobre a superficie. As chapas sao os TRIANGULOS do
# dual do Voronoi dessas sementes (tres sementes vizinhas = uma chapa), como as
# placas facetadas da referencia: costura reta de semente a semente.
areas = np.linalg.norm(fn, axis=1) / 2
amostras = rng.choice(len(F), 30000, p=areas / areas.sum())
r1, r2 = rng.random((2, 30000))
s1 = np.sqrt(r1)
cand = (V[F[amostras, 0]] * (1 - s1)[:, None] + V[F[amostras, 1]] * (s1 * (1 - r2))[:, None]
        + V[F[amostras, 2]] * (s1 * r2)[:, None])
S = np.zeros((0, 3))
for p in cand:
    lado = 0.21 if p[0] > -0.3 else 0.13   # cabeca e rostro: chapas menores
    if len(S) == 0 or np.min(np.sum((S - p) ** 2, 1)) > lado * lado:
        S = np.vstack([S, p])

arv_s = cKDTree(S)
_, ik = arv_s.query(P, k=3)


def dist_bissetriz(sa, sb):
    return (np.sum((P - sb) ** 2, 1) - np.sum((P - sa) ** 2, 1)) / (2 * np.linalg.norm(sb - sa, axis=1))


bAB = dist_bissetriz(S[ik[:, 0]], S[ik[:, 1]])
bAC = dist_bissetriz(S[ik[:, 0]], S[ik[:, 2]])
pares = np.concatenate([ik[bAB < 0.01][:, [0, 1]], ik[bAC < 0.01][:, [0, 2]]])
pares = np.unique(np.sort(pares, 1), axis=0)
viz = [set() for _ in range(len(S))]
for a, b in pares:
    viz[a].add(b); viz[b].add(a)
faces = set()
for a, b in pares:
    for c in viz[a] & viz[b]:
        faces.add(tuple(sorted((a, b, c))))
FACES = np.array(sorted(faces))
por_semente = [[] for _ in range(len(S))]
for fi, f in enumerate(FACES):
    for s in f:
        por_semente[s].append(fi)
M = max(len(l) for l in por_semente)
FA = np.full((len(S), M), -1)
for s, l in enumerate(por_semente):
    FA[s, :len(l)] = l
print(f'chapas: {len(S)} sementes, {len(FACES)} chapas triangulares')

# Pra cada texel: das chapas que tocam a semente mais proxima, a que contem o
# ponto projetado (maior baricentrica minima), descartando as do outro lado de
# partes finas (distancia ao plano grande).
cands = FA[ik[:, 0]]
valido = cands >= 0
cf = FACES[np.maximum(cands, 0)]
A, B, C = S[cf[..., 0]], S[cf[..., 1]], S[cf[..., 2]]
v0, v1, v2 = B - A, C - A, P[:, None, :] - A
d00, d01, d11 = (v0 * v0).sum(-1), (v0 * v1).sum(-1), (v1 * v1).sum(-1)
d20, d21 = (v2 * v0).sum(-1), (v2 * v1).sum(-1)
den = np.maximum(d00 * d11 - d01 * d01, 1e-12)
bv = (d11 * d20 - d01 * d21) / den
bw = (d00 * d21 - d01 * d20) / den
bu = 1 - bv - bw
fnrm = norm(np.cross(v0, v1))
plano = np.abs((v2 * fnrm).sum(-1))
score = np.minimum(np.minimum(bu, bv), bw) - (plano > 0.06) * 10 - (~valido) * 100
melhor = score.argmax(1)
lin = np.arange(len(P))
achou = score[lin, melhor] > -0.3
chapa = np.where(achou, cands[lin, melhor], len(FACES) + ik[:, 0])   # fallback: celula de Voronoi

# distancia ate a borda da chapa MEDIDA NO PLANO da chapa: baricentrica x altura do
# triangulo. (A distancia 3D ate o segmento semente-semente nao serve: a corda
# corta por dentro do corpo curvo e a costura sumia.)
Pa, Pb, Pc = A[lin, melhor], B[lin, melhor], C[lin, melhor]
area2 = np.linalg.norm(np.cross(Pb - Pa, Pc - Pa), axis=1)
lados = [(Pb, Pc), (Pc, Pa), (Pa, Pb)]            # oposto a A, B, C
Ls = np.stack([np.linalg.norm(q1 - q0, axis=1) for q0, q1 in lados], 1)
bar_m = np.stack([bu[lin, melhor], bv[lin, melhor], bw[lin, melhor]], 1)
dist_e = np.maximum(bar_m, 0) * (area2[:, None] / np.maximum(Ls, 1e-9))
qual = dist_e.argmin(1)
borda = dist_e[lin, qual]
L_e = Ls[lin, qual]
q0 = np.stack([lados[k][0] for k in range(3)], 1)[lin, qual]
q1 = np.stack([lados[k][1] for k in range(3)], 1)[lin, qual]
t_e = np.clip(((P - q0) * (q1 - q0)).sum(1) / np.maximum(L_e, 1e-9), 0, L_e)
bvor = np.minimum(bAB, bAC)
borda = np.where(achou, borda, bvor)

# Cor por chapa, pelo centroide: aco na calota da cabeca, na faixa da testa, no
# topo do rostro, na cauda; magenta no resto, com algumas chapas de aco avulsas.
cent = np.concatenate([S[FACES].mean(1), S])
cx, cy, cz = cent[:, 0], cent[:, 1], np.abs(cent[:, 2])
aco = np.zeros(len(cent), bool)
aco |= (cx < -0.26) & (cy > 0.12)
aco |= (cx < -0.26) & (cx > -0.62) & (cz < 0.1) & (cy > -0.02)
aco |= (cx < -0.55) & (cy > -0.07)
aco |= cx < -0.88                    # ponta do rostro e da mandibula
aco |= cx > 0.84
aco |= (cx > -0.2) & (cx < 0.8) & (rng.random(len(cent)) < 0.12)
CHAPA_COR = np.where(aco[:, None], ACO, MAGENTA)
CHAPA_TOM = 0.8 + 0.3 * rng.random(len(cent)) ** 1.5   # algumas chapas bem mais claras, como no video
CHAPA_GR = rng.integers(0, 10 ** 6, len(cent))

# ------------------------------------------------------------------ pintura base

cor = CHAPA_COR[chapa] * CHAPA_TOM[chapa, None]

# granulado: recorte da referencia no plano da chapa
ref_t = norm(np.cross(N, np.array([0.0, 1.0, 0.0]) + 1e-3))
ref_b = np.cross(N, ref_t)
rel = P - cent[chapa]
gu = np.sum(rel * ref_t, 1) / 0.09   # 1 recorte ~ 0.09 de lado
gv = np.sum(rel * ref_b, 1) / 0.09
detalhe = np.ones((len(P), 3))
for grupo, fontes in ((False, GR_ROSA), (True, GR_CINZA)):
    sel = aco[chapa] == grupo
    if not fontes or not sel.any():
        continue
    qual_gr = CHAPA_GR[chapa[sel]] % len(fontes)
    for k in np.unique(qual_gr):
        mm = np.nonzero(sel)[0][qual_gr == k]
        img = fontes[k]
        h, w, _ = img.shape
        uu = np.abs(((gu[mm] * w) % (2 * w)) - w).astype(int).clip(0, w - 1)   # espelhado: sem emenda
        vv = np.abs(((gv[mm] * h) % (2 * h)) - h).astype(int).clip(0, h - 1)
        detalhe[mm] = img[vv, uu]
cor *= detalhe

# costura escura, bisel (escurece rumo a costura, com um fio de brilho na quina) e rebites
cor *= (0.55 + 0.45 * smooth(0.006, 0.02, borda))[:, None]
fio = np.abs(borda - 0.0075) < 0.0012
cor[fio] = cor[fio] * 1.4
cor[borda < 0.006] = COSTURA
n_riv = np.maximum(1, np.round(L_e / 0.05))
esp = L_e / n_riv
fase = (t_e / esp) % 1.0 - 0.5
dr = np.hypot(borda - 0.019, fase * esp)
rebite = (dr < 0.0048) & (t_e > 0.025) & (t_e < L_e - 0.025) & achou
k_r = (dr[rebite] / 0.0048)[:, None]
cor[rebite] = ACO * (1.25 - 0.7 * k_r) + 0.08

if os.environ.get('DEBUG_CHAPAS'):
    # cada chapa numa cor aleatoria; fallback de Voronoi em cinza; costura preta
    paleta = rng.random((len(cent), 3)) * 0.8 + 0.2
    cor = paleta[chapa]
    cor[~achou] = 0.5
    cor[borda < 0.006] = 0
    print(f'debug: {(~achou).mean():.1%} dos texels sem chapa triangular')

glow = np.zeros_like(cor)

# ------------------------------------------------------------------ regioes especiais

# faixa de cobre
fy = faixa_y(x)
na_faixa = (x > -0.315) & (x < 0.64) & (az < 0.078) & (y > fy - 0.034)
cor[na_faixa] = COBRE * (0.85 + 0.25 * detalhe[na_faixa].mean(1, keepdims=True))
ff = na_faixa & (np.abs(az - 0.074) < 0.004)
cor[ff] = COSTURA
riv = na_faixa & (np.abs(y - (fy - 0.017)) < 0.006) & (np.abs(((x / 0.04) % 1) - 0.5) < 0.12) & (az > 0.07)
cor[riv] = COBRE * 1.5

# bulbos: laranja com nucleo claro no topo
for c, r in BULBOS:
    d = np.linalg.norm(P - c, axis=1)
    mm = (d < r * 1.25) & (y > faixa_y(c[0]) + 0.001)
    topo_ = np.clip((P[mm, 1] - c[1]) / r, -1, 1)[:, None]
    cor[mm] = LARANJA * (0.75 + 0.3 * topo_) + np.array([0.3, 0.25, 0.1]) * np.clip(topo_, 0, 1) ** 4
    glow[mm] = LARANJA * (0.7 + 0.3 * np.clip(topo_, 0, 1))

# olhos: lente incandescente + aro de aco com borda escura
for s in (1, -1):
    mm = (z * s > 0.1) & (x > -0.56) & (x < -0.38)
    rr = np.hypot(x - OLHO_X, y - OLHO_Y)
    lente = mm & (rr < OLHO_R_LENTE)
    aro = mm & (rr >= OLHO_R_LENTE) & (rr < OLHO_R_ARO)
    k = (rr[lente] / OLHO_R_LENTE)[:, None]
    cor[lente] = np.array([1.0, 0.93, 0.7]) * (1 - k) ** 2 + LARANJA * (1 - (1 - k) ** 2)
    glow[lente] = cor[lente] * 0.9
    kk = (rr[aro] - OLHO_R_LENTE) / (OLHO_R_ARO - OLHO_R_LENTE)
    cor[aro] = ACO * (0.45 + 0.55 * np.sin(kk * np.pi))[:, None]
    cor[aro & (np.abs(rr - OLHO_R_LENTE) < 0.0035)] = COSTURA
    cor[aro & (np.abs(rr - OLHO_R_ARO) < 0.0035)] = COSTURA

# boca: no vao entre as bordas das mandibulas. Superficie virada pra cima/baixo
# (ceu da boca, lingua) = miolo vermelho aceso; o resto no vao = dentes.
no_vao = (x < -0.44) & (y < BORDA_SUP(x) + 0.006) & (y > BORDA_INF(x) - 0.006)
dente = no_vao & (relevo > 0.006)
miolo = no_vao & ~dente
cor[miolo] = BOCA
glow[miolo] = BOCA * 0.8
cor[dente] = DENTE * (0.8 + 0.25 * np.clip(N[dente, 1] * -np.sign(y[dente] - (BORDA_SUP(x[dente]) + BORDA_INF(x[dente])) / 2), 0, 1))[:, None]
glow[dente] = LARANJA * 0.18

# nadadeiras: face externa com grade de LED no miolo, moldura magenta. O plano de
# cada nadadeira sai do PCA dos proprios texels; a mascara 2D nesse plano da a
# distancia ate a borda.
for s in (1, -1):
    todo = (x > -0.3) & (x < 0.08) & (z * s > 0.29) & (y < -0.03)
    pts = P[todo]
    c0 = pts.mean(0)
    _, _, vt = np.linalg.svd(pts - c0, full_matrices=False)
    e1, e2, nrm = vt[0], vt[1], vt[2]
    if nrm[2] * s + nrm[1] < 0:
        nrm = -nrm
    ext = todo & (N @ nrm > 0.2)
    idx = np.nonzero(ext)[0]
    u, v = (P[idx] - c0) @ e1, (P[idx] - c0) @ e2
    res = 0.004
    u0, v0_ = u.min() - 0.02, v.min() - 0.02
    gi, gj = ((v - v0_) / res).astype(int), ((u - u0) / res).astype(int)
    mask = np.zeros((gi.max() + 6, gj.max() + 6), bool)
    mask[gi, gj] = True
    mask = ndimage.binary_fill_holes(ndimage.binary_closing(mask, iterations=2))
    dd = (ndimage.distance_transform_edt(mask) * res)[gi, gj]
    print(f'nadadeira {s:+d}: {len(idx)} texels na face externa, miolo max {dd.max():.3f}')
    grade = idx[dd >= 0.03]
    cor[idx[(dd >= 0.026) & (dd < 0.03)]] = COSTURA
    CEL = 0.026
    fu, fv = (u[dd >= 0.03] / CEL) % 1, (v[dd >= 0.03] / CEL) % 1
    celula = (np.abs(fu - 0.5) < 0.33) & (np.abs(fv - 0.5) < 0.33)
    cor[grade] = LED_FUNDO
    acesa = grade[celula]
    brilho = 0.8 + 0.35 * rng.random(len(acesa))
    cor[acesa] = (LED * 0.9 + np.array([0.0, 0.05, 0.1])) * brilho[:, None]
    glow[acesa] = LED * 0.75 * brilho[:, None]

cor = np.clip(cor, 0, 1)
glow = np.clip(glow, 0, 1)

# ------------------------------------------------------------------ imagens

def imagem(valores):
    img = np.zeros((R, R, 3), np.float32)
    img[iy, ix] = valores
    # dilatacao: preenche o entorno dos charts com o texel mais proximo, pro filtro
    # bilinear e o mipmap nao puxarem preto pras bordas
    _, (jy, jx) = ndimage.distance_transform_edt(~cheio, return_indices=True)
    img = img[jy, jx]
    return Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)[::-1])  # v pra cima


imagem(cor).save(os.path.join(RAIZ, 'public', 'boto_color.png'))
imagem(glow).save(os.path.join(RAIZ, 'public', 'boto_glow.png'))

# ------------------------------------------------------------------ glb com UV

def salvar_glb(caminho, pos, nrm, uv, idx):
    pos, nrm, uv = pos.astype(np.float32), nrm.astype(np.float32), uv.astype(np.float32)
    idx = idx.astype(np.uint32).reshape(-1)
    blobs = [pos.tobytes(), nrm.tobytes(), uv.tobytes(), idx.tobytes()]
    offs, bin_ = [], b''
    for bl in blobs:
        offs.append(len(bin_))
        bin_ += bl + b'\0' * ((4 - len(bl) % 4) % 4)
    js = {
        'asset': {'version': '2.0', 'generator': 'boto-metal bake.py'},
        'scene': 0, 'scenes': [{'nodes': [0]}], 'nodes': [{'mesh': 0, 'name': 'boto'}],
        'meshes': [{'primitives': [{'attributes': {'POSITION': 0, 'NORMAL': 1, 'TEXCOORD_0': 2}, 'indices': 3}]}],
        'buffers': [{'byteLength': len(bin_)}],
        'bufferViews': [
            {'buffer': 0, 'byteOffset': offs[0], 'byteLength': len(blobs[0]), 'target': 34962},
            {'buffer': 0, 'byteOffset': offs[1], 'byteLength': len(blobs[1]), 'target': 34962},
            {'buffer': 0, 'byteOffset': offs[2], 'byteLength': len(blobs[2]), 'target': 34962},
            {'buffer': 0, 'byteOffset': offs[3], 'byteLength': len(blobs[3]), 'target': 34963},
        ],
        'accessors': [
            {'bufferView': 0, 'componentType': 5126, 'count': len(pos), 'type': 'VEC3',
             'min': pos.min(0).tolist(), 'max': pos.max(0).tolist()},
            {'bufferView': 1, 'componentType': 5126, 'count': len(nrm), 'type': 'VEC3'},
            {'bufferView': 2, 'componentType': 5126, 'count': len(uv), 'type': 'VEC2'},
            {'bufferView': 3, 'componentType': 5125, 'count': len(idx), 'type': 'SCALAR'},
        ],
    }
    j = json.dumps(js, separators=(',', ':')).encode()
    j += b' ' * ((4 - len(j) % 4) % 4)
    total = 12 + 8 + len(j) + 8 + len(bin_)
    with open(caminho, 'wb') as f:
        f.write(struct.pack('<III', 0x46546C67, 2, total))
        f.write(struct.pack('<II', len(j), 0x4E4F534A)); f.write(j)
        f.write(struct.pack('<II', len(bin_), 0x004E4942)); f.write(bin_)


salvar_glb(os.path.join(RAIZ, 'public', 'boto.glb'), PV, PN, UV, IDX)
print('ok -> public/boto.glb, boto_color.png, boto_glow.png')

# ------------------------------------------------------------------ nadadeira dorsal

# A malha nao tem dorsal, mas o video e a referencia tem: uma chapa de aco rebitada
# logo atras da fileira de bulbos. O contorno fica em public/fin.json (o widget
# extruda ele) e a textura em public/boto_fin.jpg, cobrindo o retangulo FIN_BOX
# em coordenadas do modelo (x, y).
from scipy.spatial import Delaunay
from matplotlib.path import Path as _Path

FIN = np.array([
    [0.50, 0.14], [0.56, 0.26], [0.63, 0.35], [0.71, 0.43], [0.78, 0.49], [0.83, 0.50],
    [0.84, 0.47], [0.81, 0.40], [0.80, 0.31], [0.82, 0.22], [0.87, 0.10], [0.87, 0.04], [0.50, 0.04],
])
FIN_BOX = [0.46, 0.0, 0.92, 0.54]   # x0, y0, x1, y1
FR = 384
gx_, gy_ = np.meshgrid(np.linspace(FIN_BOX[0], FIN_BOX[2], FR), np.linspace(FIN_BOX[3], FIN_BOX[1], FR))
pts2 = np.stack([gx_.ravel(), gy_.ravel()], 1)
dentro2 = _Path(FIN).contains_points(pts2)
# distancia ate o contorno (moldura escura + bisel)
mask2 = dentro2.reshape(FR, FR)
px_ = (FIN_BOX[2] - FIN_BOX[0]) / FR
d_cont = ndimage.distance_transform_edt(mask2).ravel() * px_
# chapas: Delaunay de pontos dentro do contorno
semi = np.vstack([FIN[[0, 2, 4, 5, 7, 9, 10]], [[0.70, 0.22]]])
tri2 = Delaunay(semi)
simp = tri2.find_simplex(pts2)
Tm = tri2.transform[simp]
b2 = np.einsum('ijk,ik->ij', Tm[:, :2], pts2 - Tm[:, 2])
bar2 = np.c_[b2, 1 - b2.sum(1)]
verts2 = semi[tri2.simplices[simp]]
area2_ = np.abs(np.cross(verts2[:, 1] - verts2[:, 0], verts2[:, 2] - verts2[:, 0]))
opp = [(1, 2), (2, 0), (0, 1)]
Ls2 = np.stack([np.linalg.norm(verts2[:, j] - verts2[:, i], axis=1) for i, j in opp], 1)
de2 = np.maximum(bar2, 0) * area2_[:, None] / np.maximum(Ls2, 1e-9)
q2 = de2.argmin(1)
ln2 = np.arange(len(pts2))
b_int = de2[ln2, q2]
L2 = Ls2[ln2, q2]
qa = np.stack([verts2[:, i] for i, _ in opp], 1)[ln2, q2]
qb = np.stack([verts2[:, j] for _, j in opp], 1)[ln2, q2]
t2 = np.clip(((pts2 - qa) * (qb - qa)).sum(1) / np.maximum(L2, 1e-9), 0, L2)

img_fin = np.ones((len(pts2), 3)) * (ACO / 0.78) * (0.85 + 0.3 * rng.random(len(semi)))[simp % len(semi), None]
gcrop = GR_CINZA[3]
h_, w_, _ = gcrop.shape
uu_ = np.abs(((pts2[:, 0] / 0.09 * w_) % (2 * w_)) - w_).astype(int).clip(0, w_ - 1)
vv_ = np.abs(((pts2[:, 1] / 0.09 * h_) % (2 * h_)) - h_).astype(int).clip(0, h_ - 1)
img_fin *= gcrop[vv_, uu_]
borda2 = np.minimum(b_int, d_cont)
img_fin *= (0.55 + 0.45 * smooth(0.006, 0.02, borda2))[:, None]
img_fin[borda2 < 0.006] = COSTURA
nr2 = np.maximum(1, np.round(L2 / 0.05)); es2 = L2 / nr2
fs2 = (t2 / es2) % 1 - 0.5
dr2 = np.hypot(b_int - 0.019, fs2 * es2)
rv2 = (dr2 < 0.0048) & (t2 > 0.025) & (t2 < L2 - 0.025) & (d_cont > 0.02)
img_fin[rv2] = ACO * (1.25 - 0.7 * (dr2[rv2] / 0.0048))[:, None] + 0.08
img_fin[~dentro2] = ACO * 0.6
Image.fromarray((np.clip(img_fin, 0, 1).reshape(FR, FR, 3) * 255).astype(np.uint8)).save(
    os.path.join(RAIZ, 'public', 'boto_fin.jpg'), quality=88)
json.dump({'contorno': FIN.tolist(), 'caixa': FIN_BOX}, open(os.path.join(RAIZ, 'public', 'fin.json'), 'w'))

# JPEG pro site: bem menor que o PNG, e o granulado ja e ruidoso por natureza
for nome in ('boto_color', 'boto_glow'):
    Image.open(os.path.join(RAIZ, 'public', nome + '.png')).convert('RGB').save(
        os.path.join(RAIZ, 'public', nome + '.jpg'), quality=88)
print('ok -> public/boto_fin.jpg, fin.json, *.jpg')
