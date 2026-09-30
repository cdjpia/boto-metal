#!/usr/bin/env node
// Servidor local so de estaticos (inclusive node_modules, de onde sai o three pelo
// importmap das paginas de debug).   npm start  ->  http://localhost:5174
import { createServer } from 'node:http';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { extname, join, normalize, resolve } from 'node:path';

const ROOT = resolve(import.meta.dirname);
const PORT = Number(process.env.PORT || 5174);
const MIME = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8', '.glb': 'model/gltf-binary',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.webp': 'image/webp', '.svg': 'image/svg+xml',
};

createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`);
  // so dev: as paginas de debug gravam renders em ./shots/ pra inspecao
  if (url.pathname === '/api/shot' && req.method === 'POST') {
    const nome = (url.searchParams.get('name') || '').split(/[\\/]/).pop();
    if (!/^[\w.-]+\.png$/.test(nome)) { res.writeHead(400); return res.end('nome invalido'); }
    const partes = [];
    for await (const c of req) partes.push(c);
    await mkdir(join(ROOT, 'shots'), { recursive: true });
    await writeFile(join(ROOT, 'shots', nome), Buffer.concat(partes));
    res.writeHead(200); return res.end('ok');
  }

  let caminho = decodeURIComponent(url.pathname);
  if (caminho === '/') caminho = '/index.html';
  const alvo = join(ROOT, normalize(caminho).replace(/^(\.\.[/\\])+/, ''));
  if (!alvo.startsWith(ROOT)) { res.writeHead(403); return res.end('fora da raiz'); }
  try {
    const dados = await readFile(alvo);
    res.writeHead(200, { 'Content-Type': MIME[extname(alvo).toLowerCase()] || 'application/octet-stream', 'Cache-Control': 'no-store' });
    res.end(dados);
  } catch { res.writeHead(404); res.end('nao encontrado'); }
}).listen(PORT, () => console.log(`boto-metal  ->  http://localhost:${PORT}`));
