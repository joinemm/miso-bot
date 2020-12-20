import asyncio
import signal
import websockets


CLIENTS = {}


async def dispatch(data):
    for cluster_name, client in CLIENTS.items():
        await client.send(data)
        print(f"> Cluster[{cluster_name}]: {data}")


async def serve(ws, path):
    cluster_name = await ws.recv()
    cluster_name = cluster_name.decode()
    if cluster_name in CLIENTS:
        print(f"! Cluster[{cluster_name}] attempted reconnection")
        await ws.close(4029, "already connected")
        return
    CLIENTS[cluster_name] = ws
    try:
        await ws.send(b'{"status":"ok"}')
        print(f"$ Cluster[{cluster_name}] connected successfully")
        async for msg in ws:
            print(f"< Cluster[{cluster_name}]: {msg}")
            await dispatch(msg)
    finally:
        CLIENTS.pop(cluster_name)
        print(f"$ Cluster[{cluster_name}] disconnected")


signal.signal(signal.SIGINT, signal.SIG_DFL)
signal.signal(signal.SIGTERM, signal.SIG_DFL)

server = websockets.serve(serve, "localhost", 42069)
loop = asyncio.get_event_loop()
loop.run_until_complete(server)
loop.run_forever()
