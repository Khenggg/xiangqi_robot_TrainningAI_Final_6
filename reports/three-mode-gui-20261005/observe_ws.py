"""Read-only packet capture during manual GUI trials; sends no commands."""
import asyncio
from pathlib import Path
import websockets

async def main():
    path = Path(__file__).with_name('telemetry.jsonl')
    async with websockets.connect('ws://127.0.0.1:8899') as socket:
        print('Read-only telemetry observer connected', flush=True)
        with path.open('a', encoding='utf-8') as stream:
            async for packet in socket:
                stream.write(packet + '\n')
                stream.flush()

asyncio.run(main())
