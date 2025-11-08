import asyncio
from portal import Portal
from data_structures import TagChangeEvent, Color, AuthMode
from dimensions import LegoPortal
from infinity import InfinityPortal

async def run_base(base: Portal):
    off = Color(0, 0, 0)
    red = Color(200, 0, 0)
    green = Color(0, 56, 0)
    blue = Color(0, 0, 200)

    async def on_change(event: TagChangeEvent):
        if not event.is_removed:
            try:
                data = await base.read_tag(event.tag, 0)
                print(f"Tag data, block 0: {data.hex()}")
            except ValueError as e:
                print(f"Failed to read tag data: {e}")

        tags = await base.get_all_tags()
        color = off
        count = len(tags.get(event.tag.platform, []))
        if count == 1:
            color = blue
        elif count == 2:
            color = green
        elif count > 2:
            color = red
        await base.set_color(event.tag.platform, color)

    base.on_tags_changed = on_change

    await base.connect()

    if isinstance(base, LegoPortal):
        await base.set_auth(AuthMode.OFF)

    print(f"Tags: {await base.get_all_tags()}")

    await base.set_color(1, red)

    await base.set_color(2, green)

    await base.fade_color(3, blue)

    await asyncio.sleep(3)

    # TODO: investigate why timings are slightly different between DI and LD
    await base.fade_random(2, 0x10, 0x11)
    await base.flash_color(3, blue, 0x8, 0x8, 9)

    await base.comms_task # sleep forever

async def main():
    bases = InfinityPortal.enumerate() + LegoPortal.enumerate()
    tasks = []
    for base in bases:
        tasks.append(asyncio.create_task(run_base(base)))
    if len(tasks) == 0:
        print("No bases detected!")
        return
    await asyncio.sleep(3)
    print("Try adding and removing figures and discs to/from the base. Ctrl-C to quit")
    await asyncio.gather(*tasks)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
