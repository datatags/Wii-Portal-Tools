from data_structures import TagChangeEvent, Color, AuthMode
from infinity import InfinityPortal
from dimensions import LegoPortal
from portal import Portal
import asyncio
import math

try:
    import ndef
    ndef_loaded = True
except ImportError:
    ndef_loaded = False

async def run_base(base: Portal):
    off = Color(0, 0, 0)
    red = Color(200, 0, 0)
    green = Color(0, 56, 0)
    blue = Color(0, 0, 200)

    # dimensions supports some extra features
    is_lego = isinstance(base, LegoPortal)

    async def on_change(event: TagChangeEvent):
        if event.tag.platform == 1:
            return

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

        if not event.is_removed:
            try:
                data = await base.read_tag(event.tag, 0)
                print(f"Tag data, block 0: {data.hex()}")
            except ValueError as e:
                print(f"Failed to read tag data: {e}")

            if not is_lego or not ndef_loaded:
                return

            BLOCK_START = 4
            BYTES_PER_BLOCK = 4
            rec = ndef.UriRecord("https://github.com/datatags/Wii-Portal-Tools")
            ndef_data = b''.join(ndef.message_encoder([rec]))
            block_count = math.ceil(len(ndef_data) / BYTES_PER_BLOCK)
            # Before we write anything, make sure that:
            #   1. We can actually read all the blocks we want to write
            #   2. The tag is NDEF formatted and empty
            #   3. The remaining blocks we're going to overwrite are zeroed.
            # This way we make sure we never overwrite a tag erroneously
            try:
                blocks = []
                # First, read in all the blocks. Since we get them 4 at a time it's easier
                # to read them all and then process them all.
                for i in range(BLOCK_START, block_count + BLOCK_START, 4):
                    data = await base.read_tag(event.tag, i)
                    for j in range(0,len(data),4):
                        blocks.append(data[j:j+4])
                for i,data in enumerate(blocks):
                    if i >= block_count:
                        break
                    if i == 0:
                        if data[:3] == b"\x03\x00\xfe":
                        # Blank NDEF header. At least when written by NFC Tools
                            continue
                    else:
                        if data == (b'\0' * BYTES_PER_BLOCK):
                            # Zeroed out, fine to overwrite
                            continue
                    return # Otherwise we don't know what it is and shouldn't overwrite it
            except ValueError:
                return

            print("Writing URL to tag...")
            data = b'\x03' + len(ndef_data).to_bytes(1, byteorder="big") + ndef_data + b'\xfe'
            try:
                for index in range(0, len(data), BYTES_PER_BLOCK):
                    chunk = data[index:index + BYTES_PER_BLOCK]
                    if len(chunk) < BYTES_PER_BLOCK:
                        # Pad out to 4 bytes if we come up short
                        chunk += b'\0' * (BYTES_PER_BLOCK - len(chunk))
                    await base.write_tag(event.tag, (index // BYTES_PER_BLOCK) + BLOCK_START, chunk)
            except ValueError as e:
                print(f"Failed to write tag data: {e}")
            print("URL written, try tapping your phone to it")

    base.on_tags_changed = on_change

    await base.connect()

    if is_lego:
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
