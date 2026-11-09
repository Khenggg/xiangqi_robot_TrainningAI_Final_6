// Replay the real local WebSocket trace through the shipped viewer functions.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import * as THREE from '../../node_modules/three/build/three.module.js';
import { createLivePacketOrderGuard, validateLivePacket } from '../../robot-3d-viewer/live_state.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const source = fs.readFileSync(path.join(here, '../../robot-3d-viewer/main.mjs'), 'utf8');
const start = source.indexOf('function applyJointsDeg(');
const end = source.indexOf('\n}\n', start) + 2;
if (start < 0 || end < start) throw new Error('Shipped applyJointsDeg function not found');
const applyJointsDeg = new Function('THREE', `return (${source.slice(start, end)});`)(THREE);
const frames = JSON.parse(fs.readFileSync(path.join(here, 'motion-frames.json'), 'utf8'));
const arm = {jointRotators: Array.from({length: 6}, () => new THREE.Group())};
const guard = createLivePacketOrderGuard();
const rotations = new Set();
const rejected = [];
let accepted = 0;
for (const frame of frames) {
  if (!guard.accept(frame) || frame.type !== 'robot_state') continue;
  const result = validateLivePacket(frame, Array.from({length: 6}, () => [-360, 360]), 'FR3');
  if (!result.ok) { rejected.push(result.reason); continue; }
  applyJointsDeg(arm, result.joints);
  rotations.add(arm.jointRotators.map(j => j.rotation.z.toFixed(6)).join(','));
  accepted++;
}
const report = {
  scope: 'Actual viewer packet validation and shipped joint application; no WebGL or CAD loading',
  accepted_robot_packets: accepted,
  distinct_rotator_poses: rotations.size,
  rejected_robot_packets: rejected,
  physical_actuation: 'NOT RUN',
};
fs.writeFileSync(path.join(here, 'viewer-motion.json'), JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
if (rotations.size < 3 || rejected.length) process.exitCode = 1;
