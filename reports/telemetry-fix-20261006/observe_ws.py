"""Read-only packet capture during manual GUI trials; sends no commands."""
import asyncio
import json
import time
from pathlib import Path
import websockets

async def main():
    path = Path(__file__).with_name('telemetry-after.jsonl')
    async with websockets.connect('ws://127.0.0.1:8899') as socket:
        print('Read-only telemetry observer connected', flush=True)
        last = {}
        with path.open('a', encoding='utf-8') as stream:
            async for packet in socket:
                kind = json.loads(packet).get('type')
                now = time.monotonic()
                if kind not in ('robot_state', 'world_state') or now-last.get(kind, 0) >= 1:
                    stream.write(packet + '\n')
                    stream.flush()
                    last[kind] = now

asyncio.run(main())
