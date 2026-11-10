// asset loading
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
export const assets = { heli: null, soldiers: null, props: null, village: null };
export async function loadAssets(onProgress) {
  const loader = new GLTFLoader(); const names = Object.keys(assets); let done = 0;
  await Promise.all(names.map(n => loader.loadAsync(`./assets/models/${n === 'heli' ? 'heli' : n}.glb`).then(g => { assets[n] = g; done++; onProgress && onProgress(done / names.length); })));
  return assets;
}
// find a top-level-ish node by name
export function node(gltf, name) { return gltf.scene.getObjectByName(name); }
