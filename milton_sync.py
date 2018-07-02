import asyncio
import aiohttp
import websockets
import json
import pprint
import sys
import os
import traceback
import aiofiles


milton_host = "dankmeme.cjzeiger.me"
# connecting steps
REQUEST_CONNECT = 0
SEND_CODE = 1
AUTH_READBACK = 2

# milton actions
PLAY_SONG = 0
STOP_PLAYING = 1

send_queue = asyncio.Queue()

# queue
tracks = {}

# current track
current_track = None

play_state = False
s_track_id = ""

state_lock = asyncio.Lock()


pp = pprint.PrettyPrinter(indent=1)


async def server_sync(webstocket):
    global current_track
    global tracks
    global play_state
    global s_track_id
    global session
    with await state_lock:
        if play_state:
            if current_track is not None:
                current_title = current_track["title"]
                if current_title not in tracks:
                    raise Exception("Track not in queue")
                track = tracks[current_title]
                id = track["id"]

                if s_track_id == id:
                    return
                pprint.pprint(track)
                b = {"id": id, "action": "play", "title": track["title"], "artist": track["artist"],
                     "duration": track["duration"]}
                async with session.post("http://"+milton_host+":8080", json=b) as response:
                    print("Response: " + str(response))
                s_track_id = id
                print("Simulating a 5 seconds download period then resetting track progress")
                track_store = s_track_id
                await asyncio.sleep(5)
                if track_store == s_track_id:
                    await reset_desktop_client_time(webstocket)
                else:
                    print("tack has changed, not resetting time in this frame")


async def reset_desktop_client_time(webscoket):
    # playback.setCurrentTime(milliseconds)
    payload = {
        "namespace": "playback",
        "method": "setCurrentTime",
        "arguments": [0]
    }
    await webscoket.send(json.dumps(payload))


async def route_channel_message(m, websocket):
    message = json.loads(m)
    # connect channel
    if "channel" not in m:
        print("channel is none, message is :")
        pp.pprint(m)
    else:
        payload = message["payload"]
        if message["channel"] == "connect":
            await connect_channel(payload, websocket)
        elif message["channel"] == "API_VERSION":
            await api_channel(payload)
        elif message["channel"] == "track":
            await track_channel(payload, websocket)
        elif message["channel"] == "playState":
            await playState_channel(payload, websocket)
        elif message["channel"] == "lyrics":
            await lyrics_channel(payload)
        elif message["channel"] == "time":
            await time_channel(payload)
        elif message["channel"] == "rating":
            await rating_channel(payload)
        elif message["channel"] == "track":
            await track_channel(payload)
        elif message["channel"] == "shuffle":
            await shuffle_channel(payload)
        elif message["channel"] == "repeat":
            await repeat_channel(payload)
        elif message["channel"] == "playlists":
            await playlist_channel(payload)
        elif message["channel"] == "queue":
            await queue_channel(payload)
        elif message["channel"] == "search-results":
            await search_results_channel(payload)
        elif message["channel"] == "volume":
            await volume_channel(payload)
        else:
            pass
            # print("Message on skipped channel")
    """
    elif m["channel"] == "track":
        await set_current_track(m["payload"])
    elif m["channel"] == "playState":
        await on_play_state(m["payload"])
    elif m["channel"] == "queue":
        print("queue message")
        await build_tracks(m["payload"])
    """


authentication_state = {
    "stage": "startup"
}


async def load_auth_token():
    try:
        async with aiofiles.open('./auth_token.txt', 'r') as outfile:
            data = json.loads(await outfile.read())
            if data and data["auth_token"]:
                return data["auth_token"]
            else:
                return None
    except OSError as e:
        if e.errno == 2:
            print(f"Could not find stored auth token {e}")
        else:
            print(f"General error opening auth file {e}")

    except Exception as e:
        print(f"General error opening auth file {e}")
    return None


async def save_auth_token(token):
    data = {
        "auth_token": token
    }
    try:
        async with aiofiles.open("./auth_token.txt", "w") as outfile:
            await outfile.write(json.dumps(data))
    except Exception as e:
        print(f"error saving auth_token {e}")


async def start_authentication_handshake(websocket):
    global authentication_state
    if authentication_state["stage"] != "startup":
        raise Exception("Invalid connect protocol")
    stored_auth = await load_auth_token()
    if stored_auth:
        response = {
            "namespace": "connect",
            "method": "connect",
            "arguments": ["Milton Sync", stored_auth]
        }
        print("Found a stored auth code, sending that")
        await websocket.send(json.dumps(response))
        authentication_state["stage"] = "authenticated"
    else:
        response = {
            "namespace": "connect",
            "method": "connect",
            "arguments": ["Milton Sync"]
        }
        print("Sent auth request")
        await websocket.send(json.dumps(response))
        authentication_state["stage"] = "code_request"


async def connect_channel(payload, websocket):
    global authentication_state
    print(f"connect channel message {payload}")
    if payload == "CODE_REQUIRED":
        if authentication_state["stage"] == "authenticated":
            print("Authentication is invalid, clearing token")
            os.environ["MILTON_SYNC_AUTH"] = None
            authentication_state["stage"] = "code_request"
        if authentication_state["stage"] == "awaiting_token":
            print("Incorrect code was entered, moving back to code_request")
            authentication_state["stage"] = "code_request"

        if authentication_state["stage"] == "code_request":
            print("Enter the 4 digit code from the Google Music Desktop Client\n")
            line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
            line = line.replace('\n', '')
            response = {
                "namespace": "connect",
                "method": "connect",
                "arguments": ["Milton Sync", line]
            }
            await websocket.send(json.dumps(response))
            authentication_state["stage"] = "awaiting_token"
        else:
            raise Exception("Unknown connect protocol state")
    elif authentication_state["stage"] == "awaiting_token" and payload is not None:
        print(f"Auth token recv {payload}")
        await save_auth_token(payload)
        authentication_state["stage"] = "authenticated"
    elif authentication_state["stage"] == "authenticated":
        print("We are already authenticated, why are we getting another message on connect")
    else:
        raise Exception("Unknown connect protocol state")


async def api_channel(payload):
    print("Api version is {}".format(payload))


async def track_channel(payload, websocket):
    global current_track
    if payload["title"] is not None and payload["artist"] is not None:
        current_track = payload
        print("Current track set to {} - {}".format(payload["title"], payload["artist"]))
        await server_sync(websocket)


async def lyrics_channel(payload):
    pass


async def time_channel(payload):
    pass


async def shuffle_channel(payload):
    pass


async def repeat_channel(payload):
    pass


async def volume_channel(payload):
    pass


async def rating_channel(payload):
    pass


async def playState_channel(payload, websocket):
    print(f"playState {payload}")
    global play_state
    play_state = payload
    if play_state:
        await server_sync(websocket)


async def playlist_channel(payload):
    pass


async def queue_channel(payload):
    # Building track dictionary
    global tracks
    tracks = {}
    for t in payload:
        tracks[t["title"]] = t
    print("Track list updated")


async def search_results_channel(payload):
    pass


async def server_controller(command):
    action = command[0]
    data = command[1]

    if action == PLAY_SONG:
        print("send http request to play " + data)


async def handler(websocket):
    global session
    global authentication_state
    authentication_state = {
        "stage": "startup"
    }
    async with aiohttp.ClientSession() as session:
        await start_authentication_handshake(websocket)
        while True:
            message = await websocket.recv()
            await route_channel_message(message, websocket)


async def startup():
    # await send_queue.put((REQUEST_CONNECT, 0))
    while True:
        try:
            async with websockets.connect('ws://localhost:5672') as ws:
                await handler(ws)
        except Exception as exp:
            print("Exception: " + str(exp))
            try:
                traceback.print_tb(sys.last_traceback, limit=None, file=None)
            except Exception:
                pass
            print("Retrying in 10 seconds")
            await asyncio.sleep(10)

asyncio.get_event_loop().run_until_complete(startup())
