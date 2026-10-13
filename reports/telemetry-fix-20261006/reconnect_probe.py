"""Read-only reconnect check; never sends commands."""
import asyncio
import json
import time
from pathlib import Path
import websockets

async def main():
    started = time.monotonic()
    states = {}
    async with websockets.connect('ws://127.0.0.1:8899', open_timeout=2) as socket:
        while not {'robot_state', 'world_state', 'operation_state'} <= states.keys():
            packet = json.loads(await asyncio.wait_for(socket.recv(), 2))
            states[packet['type']] = packet
    robot = states['robot_state']
    result = dict(observed_at=time.time(), reconnect_s=time.monotonic()-started,
                  motion_state=robot['motion_state'], joints=robot['joints'],
                  operation_state=states['operation_state']['state'],
                  pieces=len(states['world_state']['pieces']))
    with Path(__file__).with_name('reconnects.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(result)+'\n')
    print(json.dumps(result), flush=True)

asyncio.run(main())
