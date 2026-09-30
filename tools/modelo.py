"""Modelo v2 do boto, construido a partir das vistas em ref/v2/.

As vistas novas (lateral, frente, baixo, tres-quartos) mostram um modelo diferente
do boto.glb: dorsal, nadadeiras ventrais, caudais horizontais, boca bem aberta com
fileiras de dentes, faixa de aco com bulbos dos dois lados da dorsal. Em vez de
repintar a malha antiga, este script MODELA o boto low-poly (cada faceta = uma
chapa, como na referencia), com as medidas lidas das vistas lateral e de baixo
(mesma escala, ~740 px por unidade, comprimento 2), e assa a textura "PS2":

  - cada chapa recebe a cor (magenta / aco) amostrada da vista que melhor a enxerga
  - granulado recortado das proprias vistas, costura escura, bisel e rebites
  - pecas de luz com material proprio: boca, dentes, bulbos, olhos, painel de LED

Saida em public/: boto2.glb (varias malhas nomeadas), boto2_color.jpg, led.jpg

  .venv/bin/python tools/modelo.py
"""
import sys, os, json, struct
import numpy as np
import xatlas
from PIL import Image
from scipy import ndimage

RAIZ = os.path.join(os.path.dirname(__file__), '..')
R = 1024
rng = np.random.default_rng(11)


def norm(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def smooth(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


# ------------------------------------------------------------------ vistas de referencia

def vista(n):
    im = np.asarray(Image.open(os.path.join(RAIZ, 'ref', 'v2', n + '.webp')).convert('RGB')).astype(float) / 255
    m = np.load(os.path.join(RAIZ, 'ref', 'v2', n + '_mask.npy'))
    return im, m


LADO, LADO_M = vista('side')
BAIXO, BAIXO_M = vista('bottom')
# calibracao: bico em x=-1, ponta da caudal em x=+1 (medido na mascara)
def px_lado(x, y):
    return 1506 - (x + 1) * 740, 500 - y * 740
def px_baixo(x, z):
    return 1511 - (x + 1) * 743, 484 - np.abs(z) * 743


def amostra(im, xi, yi, r=4):
    xi, yi = int(np.clip(xi, r, im.shape[1] - r - 1)), int(np.clip(yi, r, im.shape[0] - r - 1))
    return im[yi - r:yi + r + 1, xi - r:xi + r + 1].reshape(-1, 3).mean(0)


def classe_cor(c):
    r, g, b = c * 255
    if r - g > 40 and b - g > 0:
        return 'rosa'
    if b > r + 30:          # LED azul: a moldura em volta e magenta
        return 'rosa'
    if r > 200 and g < 150:  # luz laranja/vermelha: o entorno e aco
        return 'aco'
    return 'aco'


# ------------------------------------------------------------------ geometria

CHAPAS = []    # dict(v: Nx3 poligono, n: normal pra fora, classe fixa ou None, parte)
EXTRAS = {k: {'pos': [], 'nrm': [], 'col': [], 'uv': []} for k in ('boca', 'dentes', 'bulbos', 'olhos', 'led')}


def chapa(v, fora, classe=None, parte='corpo'):
    v = np.asarray(v, float)
    n = norm(np.cross(v[1] - v[0], v[2] - v[0]))
    if len(v) > 3:  # normal media (quad nao planar)
        n = norm(sum(np.cross(v[i] - v.mean(0), v[(i + 1) % len(v)] - v.mean(0)) for i in range(len(v))))
    if np.dot(n, fora) < 0:
        v, n = v[::-1], -n
    CHAPAS.append(dict(v=v, n=n, classe=classe, parte=parte))


def extra(nome, tris, cor=(1, 1, 1), uv=None, suave=False):
    """tris: Mx3x3. Normais chapadas (ou por vertice radial se suave=callable)."""
    tris = np.asarray(tris, float)
    for i, t in enumerate(tris):
        n = norm(np.cross(t[1] - t[0], t[2] - t[0]))
        for k in range(3):
            EXTRAS[nome]['pos'].append(t[k])
            EXTRAS[nome]['nrm'].append(suave(t[k]) if suave else n)
            c = cor(t[k]) if callable(cor) else cor
            EXTRAS[nome]['col'].append(c)
            EXTRAS[nome]['uv'].append(uv[i][k] if uv is not None else (0, 0))


def anel(x, top, bot, w, n=10, ex=0.78, jit=True):
    yc, h = (top + bot) / 2, (top - bot) / 2
    th = 2 * np.pi * np.arange(n) / n
    if jit:  # tira a cara de grade: cada vertice anda um pouco no angulo e em x
        th = th + rng.uniform(-0.12, 0.12, n) * (np.arange(n) % 5 != 0)
    s, c = np.sin(th), np.cos(th)
    xs_ = np.full(n, x) + (rng.uniform(-0.022, 0.022, n) if jit else 0)
    return np.stack([xs_, yc + h * np.sign(c) * np.abs(c) ** ex, w * np.sign(s) * np.abs(s) ** ex], 1)


def loft(aneis, eixo, parte='corpo', split=0.4, classe_de=None):
    """Chapas entre aneis consecutivos: parte vira quad, parte vira dois triangulos
    (diagonal alternada), como o mosaico da referencia."""
    for k in range(len(aneis) - 1):
        a, b = aneis[k], aneis[k + 1]
        n = len(a)
        for j in range(n):
            q = [a[j], a[(j + 1) % n], b[(j + 1) % n], b[j]]
            centro = np.array([(a[j][0] + b[j][0]) / 2, *eixo((a[j][0] + b[j][0]) / 2)])
            fora = np.mean(q, 0) - centro
            cl = classe_de(k, j) if classe_de else None
            if rng.random() < split:
                if (j + k) % 2:
                    chapa([q[0], q[1], q[2]], fora, cl, parte); chapa([q[0], q[2], q[3]], fora, cl, parte)
                else:
                    chapa([q[0], q[1], q[3]], fora, cl, parte); chapa([q[1], q[2], q[3]], fora, cl, parte)
            else:
                chapa(q, fora, cl, parte)


# --- corpo: estacoes (x, topo, base, meia-largura) lidas das vistas lateral e de baixo
EST = np.array([
    [-0.64, 0.03, -0.20, 0.150],
    [-0.58, 0.11, -0.24, 0.190],
    [-0.50, 0.17, -0.26, 0.220],
    [-0.42, 0.20, -0.26, 0.245],
    [-0.30, 0.225, -0.25, 0.255],
    [-0.15, 0.245, -0.23, 0.270],
    [0.00, 0.250, -0.215, 0.265],
    [0.15, 0.235, -0.205, 0.235],
    [0.30, 0.160, -0.200, 0.180],
    [0.40, 0.090, -0.220, 0.140],
    [0.50, -0.010, -0.240, 0.100],
    [0.60, -0.100, -0.255, 0.065],
    [0.70, -0.135, -0.250, 0.045],
    [0.74, -0.150, -0.240, 0.035],
])
topo_x = lambda x: np.interp(x, EST[:, 0], EST[:, 1])
base_x = lambda x: np.interp(x, EST[:, 0], EST[:, 2])
larg_x = lambda x: np.interp(x, EST[:, 0], EST[:, 3])
eixo_corpo = lambda x: ((topo_x(x) + base_x(x)) / 2, 0.0)
aneis = [anel(*e, jit=0 < i < len(EST) - 1) for i, e in enumerate(EST)]
loft(aneis, eixo_corpo, 'corpo')
# tampas (escondidas pelas mandibulas / caudais)
for anel_, sinal in ((aneis[0], -1), (aneis[-1], 1)):
    c = anel_.mean(0)
    for j in range(len(anel_)):
        chapa([c, anel_[j], anel_[(j + 1) % len(anel_)]], np.array([sinal, 0, 0]), 'aco', 'corpo')


# --- mandibulas: aneis de 7 pontos; a face de dentro (ceu da boca / chao) e a boca acesa
def anel_mand(x, top, bot, w, dentro_embaixo):
    h = top - bot
    if dentro_embaixo:   # superior: fundo chato por dentro
        pts = [(0, top), (0.72 * w, top - 0.3 * h), (w, bot + 0.3 * h), (0.6 * w, bot), (-0.6 * w, bot), (-w, bot + 0.3 * h), (-0.72 * w, top - 0.3 * h)]
    else:                # inferior: topo chato por dentro
        pts = [(0.6 * w, top), (w, top - 0.3 * h), (0.72 * w, bot + 0.25 * h), (0, bot), (-0.72 * w, bot + 0.25 * h), (-w, top - 0.3 * h), (-0.6 * w, top)]
    return np.array([[x, y, z] for z, y in pts])


SUP = [(-0.60, 0.05, -0.130, 0.165), (-0.72, -0.06, -0.145, 0.120), (-0.84, -0.11, -0.160, 0.085), (-0.95, -0.15, -0.180, 0.045), (-1.0, -0.165, -0.185, 0.012)]
INF = [(-0.58, -0.165, -0.270, 0.175), (-0.70, -0.21, -0.300, 0.135), (-0.82, -0.28, -0.350, 0.09), (-0.91, -0.34, -0.395, 0.045), (-0.945, -0.37, -0.405, 0.012)]
for estacoes, emb, face_boca in ((SUP, True, 3), (INF, False, 6)):
    an = [anel_mand(*e, emb) for e in estacoes]
    eixo = lambda x, est=estacoes: ((np.interp(-x, [-e[0] for e in est], [e[1] for e in est]) + np.interp(-x, [-e[0] for e in est], [e[2] for e in est])) / 2, 0.0)
    boca = []
    for k in range(len(an) - 1):
        a, b = an[k], an[k + 1]
        for j in range(7):
            q = [a[j], a[(j + 1) % 7], b[(j + 1) % 7], b[j]]
            cx = (a[j][0] + b[j][0]) / 2
            fora = np.mean(q, 0) - np.array([cx, *eixo(cx)])
            if j == face_boca:
                boca += [[q[0], q[1], q[2]], [q[0], q[2], q[3]]]
            else:
                chapa(q, fora, None, 'mandibula')
    # ponta
    t = an[-1]; c = np.array([estacoes[-1][0] - 0.01, (estacoes[-1][1] + estacoes[-1][2]) / 2, 0])
    for j in range(7):
        chapa([c, t[j], t[(j + 1) % 7]], np.array([-1, 0, 0]), 'aco', 'mandibula')
    extra('boca', boca, cor=lambda p: (0.95, 0.06 + 0.16 * np.clip((p[0] + 0.95) / 0.35, 0, 1), 0.01))

# paredes internas da boca: vistas de lado pelo vao entre as mandibulas
xs = np.linspace(-0.60, -0.92, 7)
for s in (1, -1):
    tris = []
    for x0, x1 in zip(xs[:-1], xs[1:]):
        def pts(x):
            ys = np.interp(-x, [-e[0] for e in SUP], [e[2] for e in SUP])
            yi = np.interp(-x, [-e[0] for e in INF], [e[1] for e in INF])
            w = 0.62 * min(np.interp(-x, [-e[0] for e in SUP], [e[3] for e in SUP]), np.interp(-x, [-e[0] for e in INF], [e[3] for e in INF]))
            return np.array([x, ys, s * w]), np.array([x, yi, s * w])
        a0, b0 = pts(x0); a1, b1 = pts(x1)
        tris += [[a0, b0, b1], [a0, b1, a1]]
    extra('boca', tris, cor=lambda p: (0.95, 0.05 + 0.2 * np.clip((p[0] + 0.95) / 0.35, 0, 1), 0.01))

# dentes: cones de 4 lados ao longo das bordas de dentro das mandibulas
def cone(base, ponta, r, lados=4):
    eixo_ = norm(ponta - base)
    u = norm(np.cross(eixo_, [0.3, 1, 0.1])); v = np.cross(eixo_, u)
    anel_ = [base + r * (np.cos(a) * u + np.sin(a) * v) for a in 2 * np.pi * np.arange(lados) / lados]
    return [[anel_[i], anel_[(i + 1) % lados], ponta] for i in range(lados)]


dentes = []
for est, dirv in ((SUP, -1), (INF, 1)):
    x_ini, x_fim = est[0][0] - 0.05, est[-1][0] + 0.05
    for x in np.arange(x_ini, x_fim, -0.036):
        w = np.interp(-x, [-e[0] for e in est], [e[3] for e in est])
        y = np.interp(-x, [-e[0] for e in est], [e[2] if dirv < 0 else e[1] for e in est])
        comp = 0.028 + 0.018 * np.clip((x - x_fim) / (x_ini - x_fim), 0, 1)
        for s in (1, -1):
            b = np.array([x, y, s * 0.72 * w])
            dentes += cone(b, b + np.array([0.004, dirv * comp, -s * 0.004]), 0.011)
extra('dentes', dentes, cor=(0.93, 0.86, 0.76))

# --- olhos: aro octogonal de aco (chapa) + lente acesa (cores por vertice)
OLHO = np.array([-0.585, -0.045])
for s in (1, -1):
    zc = larg_x(OLHO[0]) * 0.97
    c = np.array([OLHO[0], OLHO[1], s * zc])
    n = norm(np.array([-0.55, 0.05, s]))
    u = norm(np.cross(n, [0, 1, 0])); v = np.cross(n, u)
    k = 8
    ang = 2 * np.pi * (np.arange(k) + 0.5) / k
    ext = [c + 0.074 * (np.cos(a) * u + np.sin(a) * v) + 0.004 * n for a in ang]
    inn = [c + 0.052 * (np.cos(a) * u + np.sin(a) * v) + 0.016 * n for a in ang]
    for i in range(k):
        chapa([ext[i], ext[(i + 1) % k], inn[(i + 1) % k], inn[i]], n, 'aco_escuro', 'olho')
    # lente: dois aneis concentricos + centro, do laranja-vermelho ao branco quente
    centro = c + 0.022 * n
    mid = [c + 0.028 * (np.cos(a) * u + np.sin(a) * v) + 0.02 * n for a in ang]
    tris, cores = [], []
    for i in range(k):
        tris += [[inn[i], inn[(i + 1) % k], mid[(i + 1) % k]], [inn[i], mid[(i + 1) % k], mid[i]], [mid[i], mid[(i + 1) % k], centro]]
    def cor_lente(p, c=c):
        d = np.linalg.norm(p - c) / 0.052
        if d < 0.3:
            return (1.0, 0.85, 0.45)     # nucleo quente
        return (1.0, 0.45 - 0.33 * d, 0.03) if d < 0.9 else (0.9, 0.08, 0.01)
    extra('olhos', tris, cor=cor_lente)

# --- faixa do dorso: fita de aco sobre o topo, de x -0.46 a 0.40
FX = np.linspace(-0.47, 0.41, 10)
FW, FH = 0.055, 0.024
def faixa_pts(x):
    y = topo_x(x) - 0.012
    return [np.array([x, y, FW]), np.array([x, y + FH, FW * 0.85]), np.array([x, y + FH, -FW * 0.85]), np.array([x, y, -FW])]
for x0, x1 in zip(FX[:-1], FX[1:]):
    a, b = faixa_pts(x0), faixa_pts(x1)
    for j, fora in ((0, [0, 0.2, 1]), (1, [0, 1, 0]), (2, [0, 0.2, -1])):
        chapa([a[j], a[j + 1], b[j + 1], b[j]], np.array(fora, float), 'faixa', 'faixa')
for x, sinal in ((FX[0], -1), (FX[-1], 1)):
    p = faixa_pts(x)
    chapa(p, np.array([sinal, 0, 0.0]), 'faixa', 'faixa')

# --- bulbos: icosaedros subdivididos (low-poly), acesos
def icosfera(c, r):
    t = (1 + 5 ** 0.5) / 2
    V = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t), (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
    Fc = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6), (7, 1, 8),
          (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1)]
    V = [norm(np.array(v, float)) for v in V]
    tris = []
    for a, b, cc in Fc:
        ab, bc, ca = norm(V[a] + V[b]), norm(V[b] + V[cc]), norm(V[cc] + V[a])
        for tri in ([V[a], ab, ca], [ab, V[b], bc], [ca, bc, V[cc]], [ab, bc, ca]):
            tris.append([c + r * p for p in tri])
    return tris


BULBOS_X = [-0.45, -0.40, -0.35, -0.30, -0.25, -0.20, -0.155, 0.12, 0.175, 0.23, 0.285]
RB = 0.027
bulbos = []
for x in BULBOS_X:
    c = np.array([x, topo_x(x) - 0.012 + FH + RB * 0.75, 0])
    bulbos += icosfera(c, RB)
extra('bulbos', bulbos, cor=lambda p: (1.0, 0.18 + 0.3 * np.clip((p[1] - topo_x(p[0])) / 0.07, 0, 1) ** 2, 0.01))

# --- placas planas extrudadas (dorsal, peitorais, ventrais, caudais)
def placa(poly2, origem, eu, ev, esp, parte, fora_face, led_inset=None, classe_borda='aco_escuro', interior=None):
    """poly2: contorno 2D (a, b) no plano origem + a*eu + b*ev. Duas faces com
    chapas em leque a partir de um ponto interno, borda (espessura) escura."""
    eu, ev = norm(np.asarray(eu, float)), norm(np.asarray(ev, float))
    n = norm(np.cross(eu, ev))
    if np.dot(n, fora_face) < 0:
        n = -n
    P2 = np.asarray(poly2, float)
    to3 = lambda ab, off: origem + ab[0] * eu + ab[1] * ev + off * n
    m = len(P2)
    cen = P2.mean(0) if interior is None else np.asarray(interior, float)
    for lado in (1, -1):
        off = lado * esp / 2
        if lado == 1 and led_inset is not None:
            # face de fora: moldura de chapas em volta do painel de LED
            I2 = cen + (P2 - cen) * led_inset
            for i in range(m):
                j = (i + 1) % m
                chapa([to3(P2[i], off), to3(P2[j], off), to3(I2[j], off), to3(I2[i], off)], n, None, parte)
            tri = [[to3(I2[i], off + 0.002), to3(I2[(i + 1) % m], off + 0.002), to3(cen, off + 0.002)] for i in range(m)]
            lo, hi = I2.min(0), I2.max(0)
            uvs = [[(p - lo) / (hi - lo) for p in (I2[i], I2[(i + 1) % m], cen)] for i in range(m)]
            extra('led', tri, uv=uvs)
        else:
            for i in range(m):
                j = (i + 1) % m
                chapa([to3(P2[i], off), to3(P2[j], off), to3(cen, off)], lado * n, None, parte)
    for i in range(m):
        j = (i + 1) % m
        a, b = P2[i], P2[j]
        fora = to3((a + b) / 2, 0) - to3(cen, 0)
        chapa([to3(a, esp / 2), to3(b, esp / 2), to3(b, -esp / 2), to3(a, -esp / 2)], fora, classe_borda, parte)


# dorsal (plano XY, z=0)
DORSAL = [(-0.16, 0.17), (-0.07, 0.27), (0.04, 0.37), (0.13, 0.445), (0.17, 0.44), (0.13, 0.35), (0.11, 0.27), (0.11, 0.17)]
placa(DORSAL, np.zeros(3), [1, 0, 0], [0, 1, 0], 0.032, 'dorsal', [0, 0, 1], interior=(0.03, 0.24))

def girar_em(v, eixo_, ang):
    eixo_ = norm(np.asarray(eixo_, float)); v = np.asarray(v, float)
    return v * np.cos(ang) + np.cross(eixo_, v) * np.sin(ang) + eixo_ * np.dot(eixo_, v) * (1 - np.cos(ang))


def plano_torcido(ang_desce, torcao, s, raiz):
    # plano da nadadeira: contem x e desce pra fora a ang_desce; depois torce em
    # torno do proprio vao pra face de cima olhar pra frente - na referencia a
    # face do LED aparece inteira de lado, de frente E de baixo
    ev = np.array([0, -np.sin(ang_desce), s * np.cos(ang_desce)])
    eu = np.array([1.0, 0, 0])
    n = np.array([0, np.cos(ang_desce), s * np.sin(ang_desce)])
    sinal = 1 if girar_em(n, ev, torcao)[0] < 0 else -1
    eu, n = girar_em(eu, ev, sinal * torcao), girar_em(n, ev, sinal * torcao)
    origem = raiz - eu * raiz[0]  # a coordenada 'a' do contorno continua sendo ~x
    return origem, eu, ev, n


# peitorais: raiz em (y -0.165, z +-0.22), descendo pra fora a 41 graus, torcidas 38
PEIT = [(-0.44, -0.06), (-0.37, 0.20), (-0.20, 0.43), (-0.07, 0.53), (0.0, 0.49), (-0.04, 0.26), (-0.08, -0.06)]
for s in (1, -1):
    origem, eu, ev, n = plano_torcido(np.radians(41), np.radians(38), s, np.array([-0.24, -0.165, s * 0.22]))
    placa(PEIT, origem, eu, ev, 0.036, 'peitoral', n, led_inset=0.62, interior=(-0.19, 0.25))

# ventrais: pequenas, mais atras
VENT = [(0.12, -0.04), (0.34, -0.04), (0.42, 0.21), (0.35, 0.23)]
for s in (1, -1):
    origem, eu, ev, n = plano_torcido(np.radians(45), np.radians(20), s, np.array([0.24, -0.19, s * 0.1]))
    placa(VENT, origem, eu, ev, 0.026, 'ventral', n, interior=(0.3, 0.08))

# caudais: plano horizontal na altura do pedunculo
# cada lobo levemente erguido (diedro), como na referencia: aparece de lado e de baixo
LOBO = [(0.68, -0.01), (0.69, 0.05), (0.785, 0.20), (1.0, 0.31), (0.975, 0.22), (0.89, 0.02), (0.87, -0.01)]
DIEDRO = np.radians(22)
for s in (1, -1):
    ev = np.array([0, np.sin(DIEDRO), s * np.cos(DIEDRO)])
    placa(LOBO, np.array([0, -0.195, 0]), [1, 0, 0], ev, 0.028, 'caudal', np.array([0, np.cos(DIEDRO), -s * np.sin(DIEDRO)]), interior=(0.82, 0.1))

print(f'chapas: {len(CHAPAS)}')

# ------------------------------------------------------------------ cor de cada chapa

def classificar(ch):
    if ch['classe']:
        return ch['classe']
    v, n = ch['v'], ch['n']
    if ch['parte'] in ('caudal',):
        return 'aco'
    c = v.mean(0)
    pontos = [c] + [c + 0.55 * (p - c) for p in v]
    votos = []
    for p in pontos:
        if n[1] < -0.55:
            votos.append(classe_cor(amostra(BAIXO, *px_baixo(p[0], p[2]))))
        elif abs(n[2]) >= 0.35 or ch['parte'] in ('dorsal', 'ventral'):
            votos.append(classe_cor(amostra(LADO, *px_lado(p[0], p[1]))))
        elif n[1] > 0.55:
            votos.append('aco' if p[0] < -0.44 else 'rosa')
        elif n[0] < 0:
            votos.append('aco' if p[1] > -0.13 else 'rosa')
        else:
            votos.append(classe_cor(amostra(LADO, *px_lado(p[0], p[1]))))
    return max(set(votos), key=votos.count)


for ch in CHAPAS:
    ch['cl'] = classificar(ch)
print('classes:', {k: sum(c['cl'] == k for c in CHAPAS) for k in set(c['cl'] for c in CHAPAS)})

# ------------------------------------------------------------------ granulado (das vistas novas)

def recortes(im, m, filtro, n=40, lado=36):
    lum = im @ [0.3, 0.59, 0.11]
    gm = np.hypot(ndimage.sobel(lum, 0), ndimage.sobel(lum, 1))
    cand = []
    for yy in range(0, im.shape[0] - lado, lado // 2):
        for xx in range(0, im.shape[1] - lado, lado // 2):
            if not m[yy:yy + lado, xx:xx + lado].all():
                continue
            bloco = im[yy:yy + lado, xx:xx + lado]
            if not filtro(bloco.reshape(-1, 3).mean(0)) or lum[yy:yy + lado, xx:xx + lado].min() < 0.14:
                continue
            cand.append((np.percentile(gm[yy:yy + lado, xx:xx + lado], 97), bloco))
    cand.sort(key=lambda c: c[0])
    out = [b for _, b in cand[:n]]
    det = [1 + 0.8 * (np.clip(b / np.maximum(ndimage.gaussian_filter(b, (7, 7, 0)), 1e-3), 0.5, 1.5) - 1) for b in out]
    return det, np.median([b.reshape(-1, 3).mean(0) for b in out], axis=0)


eh_rosa = lambda c: c[0] - c[1] > 0.25 and c[2] - c[1] > 0.05
eh_aco = lambda c: abs(c[0] - c[1]) < 0.06 and abs(c[1] - c[2]) < 0.07 and 0.2 < c[1] < 0.7
GR = {}
GR['rosa'], COR_ROSA = recortes(LADO, LADO_M, eh_rosa)
ga, COR_ACO = recortes(LADO, LADO_M, eh_aco)
gb, COR_ACO_B = recortes(BAIXO, BAIXO_M, eh_aco)
GR['aco'] = ga + gb
COR_ACO = (COR_ACO + COR_ACO_B) / 2
COR_ROSA = COR_ROSA * np.array([0.95, 0.62, 0.95])   # mais saturado: a vista lavada puxa pro pastel
COR_ACO = COR_ACO * 0.82
COR = {
    'rosa': COR_ROSA, 'aco': COR_ACO, 'aco_escuro': COR_ACO * 0.55,
    'faixa': COR_ACO * np.array([1.0, 0.93, 0.85]),
}
GR['aco_escuro'] = GR['aco']; GR['faixa'] = GR['aco']
print('paleta:', {k: np.round(v * 255).astype(int).tolist() for k, v in COR.items()})
COSTURA = np.array([0.09, 0.08, 0.09])

# ------------------------------------------------------------------ malha das chapas + UV

pos, tri, chapa_de = [], [], []
for ci, ch in enumerate(CHAPAS):
    b = len(pos)
    pos += list(ch['v'])
    for k in range(1, len(ch['v']) - 1):
        tri.append([b, b + k, b + k + 1]); chapa_de.append(ci)
pos, tri, chapa_de = np.array(pos), np.array(tri), np.array(chapa_de)

atlas = xatlas.Atlas()
atlas.add_mesh(pos.astype(np.float32), tri.astype(np.uint32))
po = xatlas.PackOptions(); po.resolution = R; po.padding = 4; po.bilinear = True
atlas.generate(pack_options=po)
vmap, IDX, UV = atlas[0]
PV = pos[vmap]
print(f'atlas: {atlas.chart_count} charts, {len(PV)} vertices')

# raster
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
    ys, xs_ = np.nonzero(ok)
    tri_de[y0 + ys, x0 + xs_] = t
    bar[y0 + ys, x0 + xs_] = np.stack([l1[ok], l2[ok], l3[ok]], -1)
cheio = tri_de >= 0
iy, ix = np.nonzero(cheio)
tt = tri_de[iy, ix]; bb = bar[iy, ix]
P = PV[IDX[tt, 0]] * bb[:, :1] + PV[IDX[tt, 1]] * bb[:, 1:2] + PV[IDX[tt, 2]] * bb[:, 2:3]
cid = chapa_de[tt]   # xatlas preserva a ordem dos triangulos
print(f'texels: {len(P)}')

# ------------------------------------------------------------------ pintura

MAXL = max(len(c['v']) for c in CHAPAS)
EA = np.zeros((len(CHAPAS), MAXL, 3)); EB = np.zeros((len(CHAPAS), MAXL, 3)); EV = np.zeros((len(CHAPAS), MAXL), bool)
for i, c in enumerate(CHAPAS):
    m = len(c['v'])
    EA[i, :m] = c['v']; EB[i, :m] = np.roll(c['v'], -1, 0); EV[i, :m] = True
A_, B_ = EA[cid], EB[cid]
d_ = B_ - A_
L_ = np.linalg.norm(d_, axis=2)
t_ = np.clip(((P[:, None] - A_) * d_).sum(2) / np.maximum(L_ ** 2, 1e-12), 0, 1)
dist = np.linalg.norm(P[:, None] - (A_ + d_ * t_[..., None]), axis=2)
dist[~EV[cid]] = 9
q = dist.argmin(1)
ln = np.arange(len(P))
borda = dist[ln, q]
L_e = L_[ln, q]
t_e = t_[ln, q] * L_e

classes = np.array([c['cl'] for c in CHAPAS])
tom = 0.82 + 0.3 * rng.random(len(CHAPAS)) ** 1.4
cor = np.array([COR[k] for k in classes])[cid] * tom[cid, None]

# granulado: um recorte por chapa, no plano da chapa
Nc = np.array([c['n'] for c in CHAPAS])[cid]
e1 = norm(np.cross(Nc, np.array([0.0, 1.0, 0.0]) + 1e-3)); e2 = np.cross(Nc, e1)
ESC = 0.07
gu, gv = (P * e1).sum(1) / ESC, (P * e2).sum(1) / ESC
qual = rng.integers(0, 10 ** 6, len(CHAPAS))[cid]
det = np.ones((len(P), 3))
for k in set(classes):
    fontes = GR[k]
    sel = np.nonzero(classes[cid] == k)[0]
    ks = qual[sel] % len(fontes)
    for f in np.unique(ks):
        mm = sel[ks == f]
        img = fontes[f]; h, w, _ = img.shape
        uu = np.abs(((gu[mm] * w) % (2 * w)) - w).astype(int).clip(0, w - 1)
        vv = np.abs(((gv[mm] * h) % (2 * h)) - h).astype(int).clip(0, h - 1)
        det[mm] = img[vv, uu]
cor *= det

# costura, bisel com fio de luz, rebites
cor *= (0.6 + 0.4 * smooth(0.005, 0.016, borda))[:, None]
fio = np.abs(borda - 0.0065) < 0.0012
cor[fio] *= 1.35
cor[borda < 0.005] = COSTURA
n_r = np.maximum(1, np.round(L_e / 0.045)); esp_r = L_e / n_r
fase = (t_e / esp_r) % 1 - 0.5
dr = np.hypot(borda - 0.014, fase * esp_r)
reb = (dr < 0.0046) & (t_e > 0.02) & (t_e < L_e - 0.02) & (L_e > 0.05)
k_r = (dr[reb] / 0.0046)[:, None]
cor[reb] = COR_ACO * (1.35 - 0.8 * k_r) + 0.06
# chapas de aco escuro (aros, bordas): menos rebite, mais escuro
esc = classes[cid] == 'aco_escuro'
cor[esc] = np.minimum(cor[esc], COR['aco_escuro'] * 1.3)
cor = np.clip(cor, 0, 1)

img = np.zeros((R, R, 3), np.float32)
img[iy, ix] = cor
_, (jy, jx) = ndimage.distance_transform_edt(~cheio, return_indices=True)
img = img[jy, jx]
Image.fromarray((img * 255).astype(np.uint8)[::-1]).save(os.path.join(RAIZ, 'public', 'boto2_color.jpg'), quality=90)

# ------------------------------------------------------------------ textura do painel de LED

L = 256
ly, lx = np.mgrid[0:L, 0:L] / L
led = np.zeros((L, L, 3)); led[:] = (0.05, 0.06, 0.2)
CU, CV = 1 / 7, 1 / 13
fu, fv = (lx / CU) % 1, (ly / CV) % 1
cel = (np.abs(fu - 0.5) < 0.36) & (np.abs(fv - 0.5) < 0.3)
brilho = 0.75 + 0.35 * rng.random((13, 7))[(ly / CV).astype(int).clip(0, 12), (lx / CU).astype(int).clip(0, 6)]
nucleo = np.clip(1 - np.maximum(np.abs(fu - 0.5) / 0.36, np.abs(fv - 0.5) / 0.3), 0, 1)
azul = np.stack([0.25 + 0.5 * nucleo, 0.45 + 0.45 * nucleo, np.ones_like(nucleo)], -1)
led[cel] = (azul * brilho[..., None])[cel]
Image.fromarray((np.clip(led, 0, 1) * 255).astype(np.uint8)).save(os.path.join(RAIZ, 'public', 'led.jpg'), quality=92)

# ------------------------------------------------------------------ glb

def salvar(caminho, malhas):
    bin_, views, accs, meshes, nodes = b'', [], [], [], []
    def add(arr, comp, tipo, alvo):
        nonlocal bin_
        arr = np.ascontiguousarray(arr)
        off = len(bin_)
        bin_ += arr.tobytes() + b'\0' * ((4 - arr.nbytes % 4) % 4)
        views.append({'buffer': 0, 'byteOffset': off, 'byteLength': arr.nbytes, 'target': alvo})
        a = {'bufferView': len(views) - 1, 'componentType': comp, 'count': len(arr), 'type': tipo}
        if tipo == 'VEC3' and comp == 5126 and not accs_pos_sem_minmax[0]:
            pass
        accs.append(a)
        return len(accs) - 1
    accs_pos_sem_minmax = [False]
    for nome, m in malhas:
        at = {}
        ip = add(m['pos'].astype(np.float32), 5126, 'VEC3', 34962)
        accs[ip]['min'] = m['pos'].min(0).tolist(); accs[ip]['max'] = m['pos'].max(0).tolist()
        at['POSITION'] = ip
        at['NORMAL'] = add(m['nrm'].astype(np.float32), 5126, 'VEC3', 34962)
        if 'uv' in m:
            at['TEXCOORD_0'] = add(m['uv'].astype(np.float32), 5126, 'VEC2', 34962)
        if 'col' in m:
            at['COLOR_0'] = add(m['col'].astype(np.float32), 5126, 'VEC3', 34962)
        prim = {'attributes': at}
        if 'idx' in m:
            prim['indices'] = add(m['idx'].astype(np.uint32).reshape(-1), 5125, 'SCALAR', 34963)
        meshes.append({'name': nome, 'primitives': [prim]})
        nodes.append({'name': nome, 'mesh': len(meshes) - 1})
    js = {'asset': {'version': '2.0', 'generator': 'boto-metal modelo.py'}, 'scene': 0,
          'scenes': [{'nodes': list(range(len(nodes)))}], 'nodes': nodes, 'meshes': meshes,
          'buffers': [{'byteLength': len(bin_)}], 'bufferViews': views, 'accessors': accs}
    j = json.dumps(js, separators=(',', ':')).encode(); j += b' ' * ((4 - len(j) % 4) % 4)
    with open(caminho, 'wb') as f:
        f.write(struct.pack('<III', 0x46546C67, 2, 12 + 8 + len(j) + 8 + len(bin_)))
        f.write(struct.pack('<II', len(j), 0x4E4F534A)); f.write(j)
        f.write(struct.pack('<II', len(bin_), 0x004E4942)); f.write(bin_)


# chapas: nao indexada com normal chapada por triangulo
tp = PV[IDX]                                  # T x 3 x 3
tn = norm(np.cross(tp[:, 1] - tp[:, 0], tp[:, 2] - tp[:, 0]))
# orienta pela normal "pra fora" da chapa
fora = np.array([c['n'] for c in CHAPAS])[chapa_de]
flip = (tn * fora).sum(1) < 0
tp[flip] = tp[flip][:, ::-1]
uvt = UV[IDX]; uvt[flip] = uvt[flip][:, ::-1]
tn[flip] *= -1
malhas = [('chapas', {'pos': tp.reshape(-1, 3), 'nrm': np.repeat(tn, 3, 0), 'uv': uvt.reshape(-1, 2)})]
for nome, e in EXTRAS.items():
    if not e['pos']:
        continue
    m = {'pos': np.array(e['pos']), 'nrm': np.array(e['nrm']), 'col': np.array(e['col'], float)}
    if nome == 'led':
        m['uv'] = np.array(e['uv'], float)
    malhas.append((nome, m))
salvar(os.path.join(RAIZ, 'public', 'boto2.glb'), malhas)
print('ok -> public/boto2.glb, boto2_color.jpg, led.jpg')
