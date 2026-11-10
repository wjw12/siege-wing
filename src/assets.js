// asset loading
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
export const assets = { heli: null, soldiers: null, props: null, village: null };
export async function loadAssets(onProgress, groundSize = 1024, aniso = 8) {
  const loader = new GLTFLoader(); const names = ['heli', 'soldiers', 'props', 'village']; let done = 0;
  const gp = loadGround(groundSize, aniso).then(g => { assets.ground = g; });
  // soldier atlas (tools/blender/soldier_atlas.py): detail x vertex colour, alpha = heraldic tint mask. The crowd falls back to plain white if it is missing.
  const sp = new THREE.TextureLoader().loadAsync('./assets/textures/soldiers/atlas.png').then(t => { t.colorSpace = THREE.SRGBColorSpace; t.flipY = false; t.premultiplyAlpha = false; t.generateMipmaps = true; t.minFilter = THREE.LinearMipmapLinearFilter; t.magFilter = THREE.LinearFilter; t.anisotropy = aniso; assets.soldierTex = t; }).catch(() => { assets.soldierTex = null; });
  await Promise.all(names.map(n => loader.loadAsync(`./assets/models/${n === 'heli' ? 'heli' : n}.glb`).then(g => { assets[n] = g; done++; onProgress && onProgress(done / names.length); })));
  await gp; await sp;
  return assets;
}
// find a top-level-ish node by name
export function node(gltf, name) { return gltf.scene.getObjectByName(name); }

// ---- photoscanned ground materials (Poly Haven, CC0) packed into two texture arrays ----
// A: rgb = albedo (sRGB), a = height.  B: rg = tangent normal xy (GL), b = roughness, a = AO.
export const GROUND = ['sparse_grass', 'leafy_grass', 'withered_grass', 'brown_mud_03', 'rock_face_03', 'forest_leaves_02', 'rocky_trail', 'aerial_grass_rock', 'aerial_rocks_02'];
async function loadGround(size, aniso) {
  const N = GROUND.length, px = size * size * 4;
  const A = new Uint8Array(px * N), B = new Uint8Array(px * N), mean = new Float32Array(N * 3);
  const cv = document.createElement('canvas'); cv.width = cv.height = size; const cx = cv.getContext('2d', { willReadFrequently: true });
  const lin = new Float32Array(256); for (let i = 0; i < 256; i++) { const c = i / 255; lin[i] = c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); }
  const img = u => fetch(u).then(r => { if (!r.ok) throw new Error('missing ' + u); return r.blob(); }).then(b => createImageBitmap(b));
  const px_ = im => { cx.drawImage(im, 0, 0, size, size); im.close && im.close(); return cx.getImageData(0, 0, size, size).data; };
  await Promise.all(GROUND.map(async (n, L) => {
    const [d, nr, h] = await Promise.all(['d', 'n', 'h'].map(s => img(`./assets/textures/terrain/${n}_${s}.jpg`)));
    const o = L * px; let r = 0, g = 0, b = 0;
    const D = px_(d); for (let i = 0; i < px; i += 4) { A[o + i] = D[i]; A[o + i + 1] = D[i + 1]; A[o + i + 2] = D[i + 2]; r += lin[D[i]]; g += lin[D[i + 1]]; b += lin[D[i + 2]]; }
    const NR = px_(nr); for (let i = 0; i < px; i += 4) { B[o + i] = NR[i]; B[o + i + 1] = NR[i + 1]; B[o + i + 2] = NR[i + 2]; }
    const H = px_(h); for (let i = 0; i < px; i += 4) { A[o + i + 3] = H[i]; B[o + i + 3] = H[i + 1]; }
    const k = 4 / px; mean[L * 3] = r * k; mean[L * 3 + 1] = g * k; mean[L * 3 + 2] = b * k;
  }));
  const mk = (data, srgb) => { const t = new THREE.DataArrayTexture(data, size, size, N); t.format = THREE.RGBAFormat; t.type = THREE.UnsignedByteType; if (srgb) t.colorSpace = THREE.SRGBColorSpace;
    t.wrapS = t.wrapT = THREE.RepeatWrapping; t.minFilter = THREE.LinearMipmapLinearFilter; t.magFilter = THREE.LinearFilter; t.generateMipmaps = true; t.anisotropy = aniso; t.needsUpdate = true; return t; };
  return { A: mk(A, true), B: mk(B, false), mean, n: N };
}
