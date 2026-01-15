import os
from xml.etree import ElementTree

from aiohttp import web, ClientSession

SPEAKERS = {
    "dining-room": "192.168.68.53",
    "living-room": "192.168.68.64",
    "kitchen": "192.168.68.60",
    "office": "192.168.68.56",
}


async def bluos_api(session: ClientSession, host: str, endpoint: str) -> ElementTree.Element:
    """Make a BluOS API call and return parsed XML."""
    async with session.get(f"http://{host}:11000/{endpoint}") as response:
        text = await response.text()
        return ElementTree.fromstring(text)


async def activate_vinyl(session: ClientSession, main_speaker: str) -> dict:
    """Group all speakers under the specified speaker and switch to Record Player input."""
    all_ips = list(SPEAKERS.values())
    follower_ips = [ip for ip in all_ips if ip != main_speaker]

    # Ungroup all speakers from any existing groups
    for ip in all_ips:
        sync = await bluos_api(session, ip, "SyncStatus")
        master = sync.find("master")
        if master is not None and master.text:
            # This speaker is following someone, remove it
            await bluos_api(session, master.text, f"RemoveSlave?slave={ip}&port=11000")
        # Also remove any followers this speaker might have
        for slave in sync.findall("slave"):
            slave_ip = slave.get("id")
            if slave_ip:
                await bluos_api(session, ip, f"RemoveSlave?slave={slave_ip}&port=11000")

    # Add followers to create a group under main speaker
    for ip in follower_ips:
        await bluos_api(session, main_speaker, f"AddSlave?slave={ip}&port=11000")

    # Select Record Player input only for Dining Room (has the turntable)
    if main_speaker == SPEAKERS["dining-room"]:
        inputs_xml = await bluos_api(session, main_speaker, "RadioBrowse?service=Capture")
        for item in inputs_xml.findall("item"):
            if item.get("text") == "Record Player":
                await bluos_api(session, main_speaker, f"Play?url={item.get('URL')}")
                break

    # Return status
    status = await bluos_api(session, main_speaker, "Status")
    sync = await bluos_api(session, main_speaker, "SyncStatus")
    return {"state": status.findtext("state"), "group": sync.get("group")}


async def ungroup_all(session: ClientSession) -> dict:
    """Ungroup all speakers to standalone mode."""
    all_ips = list(SPEAKERS.values())

    for ip in all_ips:
        sync = await bluos_api(session, ip, "SyncStatus")
        # Remove from any group this speaker is following
        master = sync.find("master")
        if master is not None and master.text:
            await bluos_api(session, master.text, f"RemoveSlave?slave={ip}&port=11000")
        # Remove any followers this speaker has
        for slave in sync.findall("slave"):
            slave_ip = slave.get("id")
            if slave_ip:
                await bluos_api(session, ip, f"RemoveSlave?slave={slave_ip}&port=11000")

    return {"status": "ungrouped"}


async def handle_group(request: web.Request) -> web.Response:
    speaker = request.query.get("speaker", "dining-room")
    if speaker not in SPEAKERS:
        return web.json_response(
            {"error": f"Unknown speaker: {speaker}", "valid": list(SPEAKERS.keys())},
            status=400,
        )
    result = await activate_vinyl(request.app["session"], SPEAKERS[speaker])
    return web.json_response(result)


async def handle_ungroup(request: web.Request) -> web.Response:
    result = await ungroup_all(request.app["session"])
    return web.json_response(result)


async def handle_health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def on_startup(app: web.Application) -> None:
    app["session"] = ClientSession()


async def on_cleanup(app: web.Application) -> None:
    await app["session"].close()


def create_app() -> web.Application:
    app = web.Application()
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    app.router.add_get("/group", handle_group)
    app.router.add_get("/ungroup", handle_ungroup)
    app.router.add_get("/health", handle_health)
    return app


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    web.run_app(create_app(), host="0.0.0.0", port=port)