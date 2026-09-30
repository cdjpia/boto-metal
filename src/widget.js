// Widget do boto de chapa rebitada. Canvas no frame inteiro (sem proporcao fixa),
// boto sempre centrado e do mesmo tamanho, girando livre em qualquer direcao
// (arrastar, rolar ou setas). Os ajustes ficam guardados no botao "Adjustments":
// abrem na lateral no desktop e por baixo no celular.
//
// Modelo e textura saem do tools/casco.py (public/boto3.glb, boto3_color.jpg,
// boto3_glow.jpg): casco visual das vistas em ref/v2/ com as proprias vistas
// projetadas como textura.
//
// Parametros de URL, pra configurar pelo Embed do Framer:
//   ?bg=transparent|black|white   fundo (default transparent)
//   ?spin=0       comeca parado (default: girando)
//   ?speed=24     graus por segundo
//   ?glow=0.405   forca do bloom (0..1.5)
//   ?hint=0       sem a animacao de "arraste pra girar"
//   ?ui=0         sem painel nem botao

import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { criarAmbiente, criarComposer } from './pipeline.js';

const DEG = THREE.MathUtils.degToRad;
const $ = (s) => document.querySelector(s);
const url = new URLSearchParams(location.search);

// ---------------------------------------------------------------- estado

const FUNDOS = [
  ['transparente', 'Transparent', 'xadrez'], ['preto', 'Black', '#000000'], ['branco', 'White', '#FFFFFF'],
];
const FUNDO_URL = { transparent: 'transparente', black: 'preto', white: 'branco' };
const reduzMovimento = matchMedia('(prefers-reduced-motion: reduce)').matches;
const num = (v, min, max) => {
  const n = parseFloat(v);
  return Number.isFinite(n) ? THREE.MathUtils.clamp(n, min, max) : null;
};

const estado = {
  brilho: num(url.get('glow'), 0, 1.5) ?? 0.405,   // 27% no controle
  girando: url.get('spin') !== '0' && !reduzMovimento,
  velocidade: num(url.get('speed'), 4, 120) ?? 24,
  fundo: FUNDO_URL[url.get('bg')] ?? 'transparente',
};

// Esfera envolvente do boto na tela: diametro = PREENCHIMENTO x o lado menor do
// frame. Como ele gira em qualquer eixo, e a esfera (nao a silhueta de agora) que
// garante que nada sai do quadro.
const PREENCHIMENTO = 0.9;

const P = {
  luzKey: 0.45, luzRim: 0.2,
  bloomForca: estado.brilho, bloomRaio: 0.3, bloomThreshold: 0.85, alphaBrilho: 1.0,
};

// ---------------------------------------------------------------- renderer

const canvas = $('#view');
const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true, powerPreference: 'high-performance' });
renderer.setClearColor(0x000000, 0);
renderer.toneMapping = THREE.NoToneMapping; // cores da textura como vieram da referencia
renderer.outputColorSpace = THREE.SRGBColorSpace;

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(30, 1, 0.01, 100);
criarAmbiente(renderer, scene, P);
// luz quase so ambiente: a textura ja vem iluminada (textura "pre-iluminada", como no PS2)
scene.add(new THREE.AmbientLight(0xffffff, 2.3));

// pivo: gira em torno do centro da esfera envolvente; o modelo vai deslocado dentro
const pivo = new THREE.Group();
scene.add(pivo);
const modelo = new THREE.Group();
pivo.add(modelo);
// pose inicial: tres-quartos com o bico pra esquerda, levemente de cima
pivo.quaternion.setFromEuler(new THREE.Euler(DEG(10), DEG(-28), 0, 'YXZ'));

const { composer, bloom, alphaPass } = criarComposer(renderer, scene, camera, P, 1, 1);
alphaPass.uniforms.corte.value = 0.22; // apara a cauda do halo sobre a pagina

let raioModelo = 1;
let carregado = false;

// ---------------------------------------------------------------- tamanho e enquadramento

let largura = 0, altura = 0;

function enquadrar() {
  // distancia em que a esfera de raio R ocupa PREENCHIMENTO do lado menor
  const tanV = Math.tan(DEG(camera.fov) / 2);
  const tanMenor = camera.aspect >= 1 ? tanV : tanV * camera.aspect;
  const d = raioModelo / Math.sin(Math.atan(PREENCHIMENTO * tanMenor));
  camera.position.set(0, 0, d);
  camera.lookAt(0, 0, 0);
  camera.updateProjectionMatrix();
  sujo = true;
}

function redimensionar() {
  const w = Math.max(1, window.innerWidth), h = Math.max(1, window.innerHeight);
  if (w !== largura || h !== altura) {
    largura = w; altura = h;
    // DPR ate 2: acima disso o bloom custa caro no celular e ninguem ve a diferenca
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    renderer.setPixelRatio(dpr);
    renderer.setSize(w, h, false);
    composer.setPixelRatio(dpr);
    composer.setSize(w, h);
    camera.aspect = w / h;
    enquadrar();
  }
  arrumarPainel();
}
window.addEventListener('resize', redimensionar);

// ---------------------------------------------------------------- painel

// O painel mora sempre no botao "Adjustments". Deitado (desktop, tablet) ele abre
// na lateral; em pe (celular), por baixo - o CSS cuida disso pela classe.
const ajustes = $('#ajustes');

function arrumarPainel() {
  document.body.classList.toggle('deitado', largura >= altura);
}

function abrirPainel(abrir, focar = true) {
  document.body.classList.toggle('aberto', abrir);
  ajustes.setAttribute('aria-expanded', String(abrir));
  if (abrir) { esconderDica(); if (focar) $('#fechar').focus(); }
  else if (focar) ajustes.focus();
}
ajustes.addEventListener('click', () => abrirPainel(!document.body.classList.contains('aberto')));
$('#fechar').addEventListener('click', () => abrirPainel(false));
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && document.body.classList.contains('aberto')) abrirPainel(false);
});
// clicar no boto com o painel aberto por cima fecha o painel
canvas.addEventListener('pointerdown', () => {
  if (document.body.classList.contains('aberto')) abrirPainel(false, false);
}, true);
if (url.get('ui') === '0') document.body.classList.add('sem-ui');

// ---------------------------------------------------------------- giro livre

// Velocidade angular em dois eixos da CAMERA (graus/s): y = girar pros lados,
// x = tombar pra frente/tras. Solta o arrasto com inercia, que decai ate o giro
// automatico (so em y) - a mesma regra do boto-loop, agora em 2D.
const GRAUS_POR_PX = 0.4;
const vel = { x: 0, y: 0 };
let arrastando = false;
let ultX = 0, ultY = 0, ultT = 0;
let sujo = true;

const _qx = new THREE.Quaternion(), _qy = new THREE.Quaternion();
const EIXO_X = new THREE.Vector3(1, 0, 0), EIXO_Y = new THREE.Vector3(0, 1, 0);

function girar(gx, gy) {
  // rotacao em torno dos eixos da tela, aplicada por fora (premultiply): arrastar
  // pra direita sempre gira pra direita, qualquer que seja a pose atual
  _qy.setFromAxisAngle(EIXO_Y, DEG(gy));
  _qx.setFromAxisAngle(EIXO_X, DEG(gx));
  pivo.quaternion.premultiply(_qy).premultiply(_qx).normalize();
  sujo = true;
}

canvas.addEventListener('pointerdown', (e) => {
  if (e.button !== 0) return;
  arrastando = true;
  ultX = e.clientX; ultY = e.clientY; ultT = e.timeStamp;
  vel.x = vel.y = 0;
  canvas.setPointerCapture(e.pointerId);
  canvas.classList.add('arrastando');
  esconderDica();
});

canvas.addEventListener('pointermove', (e) => {
  if (!arrastando) return;
  const dx = e.clientX - ultX, dy = e.clientY - ultY;
  const dt = Math.max(1, e.timeStamp - ultT) / 1000;
  girar(dy * GRAUS_POR_PX, dx * GRAUS_POR_PX);
  // media movel: um evento isolado com dt minusculo nao vira arremesso
  vel.y = THREE.MathUtils.lerp(vel.y, (dx * GRAUS_POR_PX) / dt, 0.5);
  vel.x = THREE.MathUtils.lerp(vel.x, (dy * GRAUS_POR_PX) / dt, 0.5);
  ultX = e.clientX; ultY = e.clientY; ultT = e.timeStamp;
});

function soltar(e) {
  if (!arrastando) return;
  arrastando = false;
  canvas.classList.remove('arrastando');
  if (e.timeStamp - ultT > 80) vel.x = vel.y = 0; // parou antes de soltar: sem impulso
  vel.x = THREE.MathUtils.clamp(vel.x, -720, 720);
  vel.y = THREE.MathUtils.clamp(vel.y, -720, 720);
}
canvas.addEventListener('pointerup', soltar);
canvas.addEventListener('pointercancel', soltar);

// Rolagem (roda do mouse ou dois dedos no trackpad) tambem gira: vertical tomba,
// horizontal vira. So enquanto o ponteiro esta em cima do boto.
canvas.addEventListener('wheel', (e) => {
  e.preventDefault();
  const k = e.deltaMode === 1 ? 6 : 0.25; // deltaMode 1 = linhas (Firefox com roda)
  girar(e.deltaY * k, e.deltaX * k);
  esconderDica();
}, { passive: false });

canvas.addEventListener('keydown', (e) => {
  const p = e.shiftKey ? 45 : 15;
  const mapa = { ArrowLeft: [0, -p], ArrowRight: [0, p], ArrowUp: [-p, 0], ArrowDown: [p, 0] };
  if (!mapa[e.key]) return;
  e.preventDefault();
  girar(...mapa[e.key]);
  esconderDica();
});

// ---------------------------------------------------------------- dica

const dica = $('#dica');
let dicaFeita = url.get('hint') === '0';
let dicaTimer = 0;

function mostrarDica() {
  if (dicaFeita || !carregado) return;
  dicaFeita = true;
  dica.classList.add('visivel');
  dicaTimer = setTimeout(esconderDica, 3100);
}
function esconderDica() {
  dicaFeita = true;
  clearTimeout(dicaTimer);
  dica.classList.remove('visivel');
}

// ---------------------------------------------------------------- loop

// So renderiza na tela: numa pagina do Framer o widget passa muito tempo fora da vista.
let naTela = true;
new IntersectionObserver(([en]) => {
  naTela = en.isIntersecting;
  if (naTela) mostrarDica();
}, { threshold: 0.4 }).observe(canvas);

let anterior = performance.now();

function loop(agora) {
  requestAnimationFrame(loop);
  const dt = Math.min(0.1, (agora - anterior) / 1000);
  anterior = agora;
  if (!naTela || !carregado) return;

  if (!arrastando) {
    const k = 1 - Math.exp(-dt * 1.6);
    vel.y += ((estado.girando ? estado.velocidade : 0) - vel.y) * k;
    vel.x += (0 - vel.x) * k;
    if (Math.abs(vel.x) < 0.01) vel.x = 0;
    if (Math.abs(vel.y) < 0.01 && !estado.girando) vel.y = 0;
    if (vel.x || vel.y) girar(vel.x * dt, vel.y * dt);
  }
  if (!sujo) return;
  sujo = false;
  composer.render();
}

// ---------------------------------------------------------------- carga

async function carregar() {
  const base = new URL('../public/', import.meta.url);
  const tl = new THREE.TextureLoader();
  const [gltf, mapa, brilhoMap] = await Promise.all([
    new GLTFLoader().loadAsync(new URL('boto3.glb', base).href),
    tl.loadAsync(new URL('boto3_color.jpg', base).href),
    tl.loadAsync(new URL('boto3_glow.jpg', base).href),
  ]);
  for (const t of [mapa, brilhoMap]) { t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4; }

  // Textura projetada das vistas de referencia (tools/casco.py): ela ja traz a luz
  // e o brilho metalico pintados, entao o material quase nao acende nada por cima -
  // como num jogo de PS2. O mapa de emissao (bulbos, olhos, boca, LED) alimenta o bloom.
  const corpo = gltf.scene.getObjectByProperty('type', 'Mesh');
  corpo.material = new THREE.MeshLambertMaterial({
    map: mapa, emissiveMap: brilhoMap, emissive: 0xffffff, emissiveIntensity: 1.4,
  });
  modelo.add(corpo);

  // esfera envolvente de tudo: o pivo gira em torno do centro dela
  const caixa = new THREE.Box3().setFromObject(modelo);
  const centro = caixa.getCenter(new THREE.Vector3());
  modelo.position.copy(centro).negate();
  raioModelo = 0;
  const v = new THREE.Vector3();
  modelo.updateMatrixWorld(true);
  modelo.traverse((o) => {
    if (!o.isMesh) return;
    const pos = o.geometry.attributes.position;
    for (let i = 0; i < pos.count; i++) {
      v.fromBufferAttribute(pos, i).applyMatrix4(o.matrixWorld);
      raioModelo = Math.max(raioModelo, v.length());
    }
  });
  raioModelo *= 1.04; // folga pro halo dos bulbos

  bloom.strength = estado.brilho;
  enquadrar();
  vel.y = estado.girando ? estado.velocidade : 0;
  carregado = true;
  canvas.classList.add('pronto');
  requestAnimationFrame((ts) => { anterior = ts; loop(ts); });
  if (naTela) setTimeout(mostrarDica, 500);
}

carregar().catch((err) => {
  console.error(err);
  const d = document.createElement('div');
  d.className = 'erro';
  d.textContent = 'Could not load the 3D model.';
  document.body.append(d);
});

// ---------------------------------------------------------------- controles

function montarAmostras(el, opcoes, chave, aplicar) {
  const botoes = opcoes.map(([valor, nome, visual]) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'amostra';
    if (visual === 'xadrez') b.classList.add('xadrez');
    else b.style.setProperty('--c', visual);
    b.setAttribute('aria-label', nome);
    b.title = nome;
    b.addEventListener('click', () => { estado[chave] = valor; aplicar(); sincronizar(); });
    el.append(b);
    return [valor, b];
  });
  return () => { for (const [valor, b] of botoes) b.setAttribute('aria-pressed', String(valor === estado[chave])); };
}

const aplicarFundo = () => { document.body.dataset.fundo = estado.fundo; };
const marcarFundo = montarAmostras($('#amostras-fundo'), FUNDOS, 'fundo', aplicarFundo);
const brilho = $('#brilho'), velocidade = $('#velocidade'), chave = $('#girar');

function pintarTrilho(r) {
  r.style.setProperty('--p', `${((r.value - r.min) / (r.max - r.min)) * 100}%`);
}

function sincronizar() {
  marcarFundo();
  brilho.value = estado.brilho;
  $('#brilho-v').textContent = `${Math.round((estado.brilho / 1.5) * 100)}%`;
  velocidade.value = estado.velocidade;
  $('#velocidade-v').textContent = `${Math.round(estado.velocidade)}°/s`;
  velocidade.disabled = !estado.girando;
  $('#r-giro').classList.toggle('off', !estado.girando);
  chave.setAttribute('aria-checked', String(estado.girando));
  $('#fundo-v').textContent = FUNDOS.find(([v]) => v === estado.fundo)[1];
  pintarTrilho(brilho);
  pintarTrilho(velocidade);
}

brilho.addEventListener('input', () => {
  estado.brilho = parseFloat(brilho.value); bloom.strength = estado.brilho; sincronizar(); sujo = true;
});
velocidade.addEventListener('input', () => { estado.velocidade = parseFloat(velocidade.value); sincronizar(); });
chave.addEventListener('click', () => { estado.girando = !estado.girando; sincronizar(); });

aplicarFundo();
sincronizar();
redimensionar();

// so dev (?debug=1): grava o quadro atual em shots/ pelo server.mjs, e expoe o pivo
if (url.get('debug') === '1') {
  window.debugBoto = {
    pivo,
    async foto(nome, euler) {
      if (euler) { pivo.quaternion.setFromEuler(new THREE.Euler(...euler.map(DEG), 'YXZ')); vel.x = vel.y = 0; estado.girando = false; }
      composer.render();
      const blob = await new Promise((r) => canvas.toBlob(r, 'image/png'));
      await fetch(`/api/shot?name=${nome}.png`, { method: 'POST', body: blob });
      return nome;
    },
  };
}
