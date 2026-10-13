"""Summarize the final read-only capture against GUI-observed moves."""
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

root = Path(__file__).parent
session = Path('D:/OJT/_simple_launch_sync_20261005/logs/20261006_013940_4599664e')
events = [json.loads(line) for line in (session/'events.jsonl').read_text(encoding='utf-8').splitlines()]
started = datetime.fromisoformat(events[0]['timestamp']).timestamp()
counts = Counter()
first_world = last_world = last_robot = last_operation = None
moving_samples = 0
with (root/'telemetry-after.jsonl').open(encoding='utf-8') as stream:
    for line in stream:
        packet = json.loads(line)
        kind = packet.get('type')
        if kind in ('robot_state', 'world_state') and (packet.get('timestamp') or 0) < started:
            continue
        counts[kind] += 1
        if kind == 'world_state':
            first_world = first_world or packet
            last_world = packet
        elif kind == 'robot_state':
            last_robot = packet
            moving_samples += packet.get('motion_state') == 'MOVING'
        elif kind == 'operation_state':
            last_operation = packet

# Screen coordinates: columns a..i=0..8, rows 0..9.
moves = [((1,9),(2,7)), ((7,0),(6,2)), ((7,7),(6,7)),
         ((1,2),(2,2)), ((6,7),(6,3)), ((2,2),(2,6)),
         ((7,9),(6,7)), ((1,0),(2,2)), ((8,9),(7,9)), ((0,0),(1,0))]
expected = {(p['nearest_col'],p['nearest_row']):p['id'] for p in first_world['pieces']}
captured = []
for source, target in moves:
    if target in expected:
        captured.append(expected.pop(target))
    expected[target] = expected.pop(source)
actual = {(p['nearest_col'],p['nearest_row']):p['id'] for p in last_world['pieces']}
result = {
    'session_id': session.name,
    'moves_total_plies': len(moves),
    'captured_ids': captured,
    'expected_pieces': len(expected), 'actual_pieces': len(actual),
    'all_piece_ids_and_cells_match': actual == expected,
    'all_remaining_pieces_resting': all(p['physical_state'] == 'RESTING' for p in last_world['pieces']),
    'packet_counts': dict(counts), 'moving_robot_samples': moving_samples,
    'twin_fault_count': sum(e['event'] == 'twin.fault' for e in events),
    'error_event_count': sum(e['level'] in ('ERROR','CRITICAL') for e in events),
    'final_robot': last_robot, 'final_operation': last_operation,
    'max_final_cell_error_mm': max(p['distance_to_nearest_intersection_m']*1000 for p in last_world['pieces']),
}
(root/'evidence-summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
