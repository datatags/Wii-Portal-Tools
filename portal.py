from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Awaitable
from data_structures import *
import asyncio
import hid


class Comms(ABC):
    comms_def: CommsDefinition

    def __init__(self, serial: str | None = None):
        self.device = self._init_base(serial)
        self.finish = False
        self.pending_requests = {}
        self.message_number = 0
        self.observers = []
        self.lock = asyncio.Lock()
        self.uid_cache = {}


    def _init_base(self, serial: str | None):
        device = hid.Device(*self.comms_def.vid_pid(), serial)
        print(f"Connected to {device.serial}")
        device.nonblocking = False
        return device

    async def run(self):
        while not self.finish:
            fields = await asyncio.get_event_loop().run_in_executor(None, self.device.read, 32, 1000)
            if len(fields) == 0:
                continue

            if fields[0] == self.comms_def.reply_standard_id(): # reply message
                length = fields[1]
                message_id = fields[2]
                if message_id in self.pending_requests:
                    # TODO: might be good to check that the checksum matches
                    self.pending_requests[message_id].set_result(fields[3:length+2])
                    del self.pending_requests[message_id]
                    continue
            elif fields[0] == self.comms_def.reply_standard_id() + 1: # event message
                # Do on a separate task in case observers send commands
                asyncio.create_task(self._generate_event(fields[2:]))
                continue
            self._unknown_message(fields)

    @abstractmethod
    async def _unpack_tag_event(data: bytes) -> TagChangeEvent:
        """Convert the bytes from an event message into a TagChangeEvent,
        including sending follow-up requests if necessary to obtain all information."""
        pass

    @abstractmethod
    async def _fetch_tag_uid(self, tag: Tag) -> bytes:
        pass

    async def get_tag_uid(self, tag: Tag) -> bytes:
        try:
            return self.uid_cache[tag.index]
        except KeyError:
            try:
                uid = await self._fetch_tag_uid(tag)
                self.uid_cache[tag.index] = uid
                return uid
            except ValueError:
                # Oh well, we tried
                return None

    async def _generate_event(self, data: bytes):
        event = await self._unpack_tag_event(data)
        if event.tag.uid is None:
            try:
                event.tag.uid = self.uid_cache[event.tag.index]
            except KeyError:
                if not event.is_removed:
                    try:
                        event.tag.uid = await self._fetch_tag_uid(event.tag)
                        self.uid_cache[event.tag.index] = event.tag.uid
                    except ValueError:
                        pass
        else:
            self.uid_cache[event.tag.index] = event.tag.uid
        if event.is_removed:
            self.uid_cache.pop(event.tag.index, None)

        for obs in self.observers:
            await obs.tags_updated(event)

    def add_observer(self, object):
        self.observers.append(object)

    def _unknown_message(self, fields):
        print("UNKNOWN MESSAGE RECEIVED ", fields)

    def _next_message_number(self):
        self.message_number = (self.message_number + 1) % 256
        return self.message_number

    def get_command(self, command: CommandType) -> int:
        try:
            return self.comms_def.get_command_set()[command]
        except KeyError:
            raise ValueError(f"Unsupported command: {command}")

    async def send_message(self, command: CommandType, data: list[int] = []):
        message_id, message = self._construct_message(self.get_command(command), bytes(data))
        result = asyncio.get_event_loop().create_future()
        self.pending_requests[message_id] = result
        async with self.lock:
            self.device.write(message)
        return await result

    def _construct_message(self, command: int, data: bytes):
        message_id = self._next_message_number()
        def to_bytes(val: int):
            return val.to_bytes(1, byteorder="big")
        command_bytes = to_bytes(0) # ???
        command_bytes += to_bytes(self.comms_def.magic_prefix())
        command_bytes += to_bytes(2 + len(data))
        command_bytes += to_bytes(command)
        command_bytes += to_bytes(message_id)
        command_bytes += data

        checksum = 0
        for byte in command_bytes:
            checksum += byte
        command_bytes += to_bytes(checksum & 0xFF)
        # Technically it will still work without padding out the message,
        # but it's the polite thing to do to conform to the USB spec.
        command_bytes += b"\0" * (32 - len(command_bytes))
        return (message_id, command_bytes)

    def _check_for_error(self, code: int):
        if code == ErrorType.SUCCESS.value:
            return # yay!
        # Mask out some of the upper bits since LD sets them but DI doesn't
        code &= 0x8F
        try:
            error = ErrorType(code)
        except ValueError:
            raise ValueError(f"Unknown error: {hex(code)}")
        raise ValueError(error.msg)


class Portal(ABC):
    comms_def: CommsDefinition

    def __init__(self, comms: Comms):
        self.comms = comms
        self.comms.add_observer(self)
        self.on_tags_changed = None

    async def connect(self):
        self.comms_task = asyncio.get_event_loop().create_task(self.comms.run())
        await self.activate()

    def disconnect(self):
        self.comms.finish = True
        self.comms_task.cancel()

    async def activate(self):
        await self.comms.send_message(CommandType.ACTIVATE, self.comms.comms_def.activation_str())

    async def tags_updated(self, event: TagChangeEvent):
        if self.on_tags_changed:
            await self.on_tags_changed(event)

    async def get_all_tags(self) -> dict[int, list[Tag]]:
        tags = await self.get_tag_index()
        if len(tags) == 0:
            return {}
        tagByPlatform = defaultdict(list)
        for tag in tags:
            if tag.uid is None:
                tag.uid = await self.comms.get_tag_uid(tag)
            tagByPlatform[tag.platform].append(tag)
        return dict(tagByPlatform)

    async def get_tag_index(self) -> list[Tag]:
        data = await self.comms.send_message(CommandType.LIST_TAGS)
        tags = []
        for i in range(0, len(data), 2):
            tags.append(Tag.from_bytes(data[i:i+2]))
        return tags

    async def set_color(self, platform: int | Platform, color: Color):
        """Set the color of a platform

        Arguments:
        platform -- the platform to control
        color -- the color to set the platform to
        """
        await self.comms.send_message(CommandType.SET_ONE, [int(platform), *color])

    async def fade_color(self, platform: int | Platform, color: Color, duration: float = 1.0, count: int = 2):
        """Fade a platform color in and out according to the parameters.

        Arguments:
        platform -- the platform to control
        color -- the color to make the platform
        duration -- the duration of the cycle in seconds
        count -- the number of half-cycles to perform, e.g. 1 is off-to-on, 2 is off-on-off, etc
        """
        d = int(self.comms_def.ticks_per_second() * duration)
        await self.comms.send_message(CommandType.FADE_ONE, [int(platform), d, count, *color])

    async def flash_color(self, platform: int | Platform, color: Color, onTime: float = 0.2, offTime: float = 0.2, count: int = 0x06):
        """Flash a platform on and off

        Arguments:
        platform -- the platform to control
        color -- the color to make the platform
        onTime -- the duration of each on-cycle in seconds
        offTime -- the duration of each off-cycle in seconds
        count -- the number of half-cycles to perform, e.g. 1 is off-to-on, 2 is off-on-off, etc
        """
        on = int(self.comms_def.ticks_per_second() * onTime)
        off = int(self.comms_def.ticks_per_second() * offTime)
        await self.comms.send_message(CommandType.FLASH_ONE, [int(platform), on, off, count, *color])

    async def fade_random(self, platform: int | Platform, duration: float = 1.0, count: int = 0x02):
        """Fade a platform between its current color and random other colors

        Arguments:
        platform -- the platform to control
        duration -- the duration of each half-cycle in seconds
        count -- the number of half-cycles to perform, e.g. 1 is src-to-dest, 2 is src-dest-src, etc
        """
        d = int(self.comms_def.ticks_per_second() * duration)
        await self.comms.send_message(CommandType.RANDOM_ONE, [int(platform), d, count])

    async def read_tag(self, tag: Tag, block: int) -> bytes:
        """Read a data block from the tag.

        Note: 16 bytes will always be returned, so on tags that have 4-byte blocks like the NTAG,
        the three subsequent blocks will also be read to fill out the response.

        Keyword arguments:
        tag -- the tag to read from
        block -- the block to read from
        """
        msg = [tag.index]
        if self.comms_def.has_nfc_sectors():
            # Technically we could just do sector=0 and leave block unchanged
            # but this seems more like how it was designed to be used.
            msg.append(block // 4)
            block %= 4
        msg.append(block)
        data = await self.comms.send_message(CommandType.READ_BLOCK, msg)
        self.comms._check_for_error(data[0])
        return data[1:]

    async def write_tag(self, tag: Tag, block: int, data: bytes):
        """Write a data block to the tag.

        In this case, the block size does matter, so the length of `data` must match the block size
        of the tag.

        Keyword arguments:
        tag -- the tag to read from
        block -- the block to read from
        """
        msg = [tag.index]
        if self.comms_def.has_nfc_sectors():
            msg.append(block // 4)
            block %= 4
        msg.append(block)
        data = await self.comms.send_message(CommandType.WRITE_BLOCK, msg + list(data))
        self.comms._check_for_error(data[0])

    async def set_auth(self, mode: AuthMode, pwd: bytes = b"\0\0\0\0"):
        msg = [84, mode] # 84 is the tag index. I guess. This is what node-ld does
        if mode == AuthMode.CUSTOM:
            msg.extend(list(pwd))
        data = await self.comms.send_message(CommandType.TAG_PWD, msg)
        self.comms._check_for_error(data[0])

    async def set_nfc_enabled(self, enabled: bool):
        await self.comms.send_message(CommandType.NFC_ON, [enabled])
        # no data returned so no error check

    @classmethod
    def enumerate(cls) -> list: # returns list of self
        return [cls(dev["serial_number"]) for dev in hid.enumerate(*cls.comms_def.vid_pid())]

