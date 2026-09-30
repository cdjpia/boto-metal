#!/usr/bin/env node
// Le um .glb e imprime contagem de vertices/triangulos, atributos e bounding box.
// Uso: node scripts/glbinfo.mjs boto.glb
import { readFileSync } from 'node:fs';

const file = process.argv[2] || 'boto.glb';
const buf = readFileSync(file);

if (buf.readUInt32LE(0) !== 0x46546c67) {
  console.error(`${file}: nao é um GLB binario (magic errado)`);
  process.exit(1);
}

// chunk 0 = JSON, chunk 1 = BIN
let offset = 12;
let json = null;
while (offset < buf.length) {
  const len = buf.readUInt32LE(offset);
  const type = buf.readUInt32LE(offset + 4);
  if (type === 0x4e4f534a) json = JSON.parse(buf.slice(offset + 8, offset + 8 + len).toString('utf8'));
  offset += 8 + len + ((4 - (len % 4)) % 4);
}

const acc = json.accessors || [];
let verts = 0;
let tris = 0;
const attrs = new Set();
const bbox = { min: [Infinity, Infinity, Infinity], max: [-Infinity, -Infinity, -Infinity] };

for (const mesh of json.meshes || []) {
  for (const prim of mesh.primitives || []) {
    for (const key of Object.keys(prim.attributes)) attrs.add(key);
    const pos = acc[prim.attributes.POSITION];
    verts += pos.count;
    tris += (prim.indices != null ? acc[prim.indices].count : pos.count) / 3;
    if (pos.min && pos.max) {
      for (let i = 0; i < 3; i++) {
        bbox.min[i] = Math.min(bbox.min[i], pos.min[i]);
        bbox.max[i] = Math.max(bbox.max[i], pos.max[i]);
      }
    }
  }
}

const size = bbox.max.map((v, i) => v - bbox.min[i]);
const f = (n) => n.toFixed(3);

console.log(`arquivo      ${file}  (${(buf.length / 1048576).toFixed(2)} MB)`);
console.log(`vertices     ${verts.toLocaleString('pt-BR')}`);
console.log(`triangulos   ${Math.round(tris).toLocaleString('pt-BR')}`);
console.log(`atributos    ${[...attrs].join(', ')}`);
console.log(`materiais    ${(json.materials || []).length}   texturas ${(json.textures || []).length}`);
console.log(`bbox min     ${bbox.min.map(f).join('  ')}`);
console.log(`bbox max     ${bbox.max.map(f).join('  ')}`);
console.log(`bbox size    ${size.map(f).join('  ')}`);
