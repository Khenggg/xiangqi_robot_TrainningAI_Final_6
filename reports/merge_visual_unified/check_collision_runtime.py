import json
from pathlib import Path
import numpy as np
import pybullet as p
from src.simulation.runtime import VirtualXiangqiSimulation
from src.simulation.physics.transforms import rpy_deg_to_quat
s=VirtualXiangqiSimulation(auto_sync_telemetry=False)
s.connect()
b=s.backend;w=s.world
before=b.get_state_snapshot(); evidence={}
for label,fn in [('board_penetration',lambda:b.move_cartesian([0,360,0,180,0,90])),('folded_collision',lambda:b.move_joint([0,-45,-160,-260,-160,0]))]:
 ok=fn();after=b.get_state_snapshot()
 evidence[label]={'accepted':ok,'error':after.last_error,'max_joint_delta_deg':float(np.max(np.abs(np.asarray(after.joints_deg)-before.joints_deg))),'max_tcp_delta_mm_deg':float(np.max(np.abs(np.asarray(after.tcp_pose_mm_deg)-before.tcp_pose_mm_deg))),'gripper_unchanged':after.gripper_closed==before.gripper_closed}
 assert not ok
 assert evidence[label]['max_joint_delta_deg']==0
 assert evidence[label]['max_tcp_delta_mm_deg']==0
 assert evidence[label]['gripper_unchanged']
xyz=w.board_placement_state.board_local_to_robot(0,0,z_rel_m=-.010)
w.gripper.set_tcp_pose(xyz,rpy_deg_to_quat([180,0,90]))
contacts=[c[8] for bid in w.gripper.proxy_body_ids for c in p.getClosestPoints(bid,w.board_body_id,.05,physicsClientId=w.client_id)]
evidence['direct_board_penetration_min_mm']=min(contacts)*1000
assert min(contacts)<0
w.sync_robot_collision_configuration(np.deg2rad([0,-45,-160,-260,-160,0]))
arm=[(int(c[4]),c[8]*1000) for bid in w.gripper.proxy_body_ids for c in p.getClosestPoints(bid,w.robot_body_id,.01,physicsClientId=w.client_id) if int(c[4]) != 5 and c[8] < 0]
assert any(link==2 for link,dist in arm)
evidence['direct_gripper_arm_penetrations_mm']=arm
s.stop()
Path('reports/merge_visual_unified/collision_evidence.json').write_text(json.dumps(evidence,indent=2))
print(json.dumps(evidence))
