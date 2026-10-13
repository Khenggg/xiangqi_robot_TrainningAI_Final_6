import assert from 'node:assert/strict';
import { validateLivePacket } from '../../robot-3d-viewer/live_state.mjs';
const limits = Array.from({length: 6}, () => [-360, 360]);
const packet = {type:'robot_state',robot_model:'FR3',source:'PHYSICAL',joints:[0,0,0,0,0,0],
  connected:true,joints_valid:true,measurement_timestamp:Date.now()/1000};
assert.equal(validateLivePacket(packet,limits,'FR3').ok,true);
for (const change of [{connected:false},{joints_valid:false},{measurement_timestamp:null},
                      {measurement_timestamp:Date.now()/1000-5}]) {
  assert.equal(validateLivePacket({...packet,...change},limits,'FR3').ok,false);
}
// Virtual packets remain compatible with the simulator's snapshot contract.
assert.equal(validateLivePacket({...packet,source:'VIRTUAL',measurement_timestamp:null},limits,'FR3').ok,true);
console.log('Viewer freshness: physical valid / disconnected / invalid / absent / stale, virtual compatibility PASS');
