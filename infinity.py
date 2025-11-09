from portal import Comms, Portal
from data_structures import *

class InfinityCommsDefinition(CommsDefinition):
    @staticmethod
    def activation_str() -> bytes:
        return b"(c) Disney 2013"

    @staticmethod
    def get_command_set() -> dict[CommandType, int]:
        return {
            CommandType.ACTIVATE: 0x80,
            CommandType.SEED_RNG: 0x81,
            CommandType.GET_RNG: 0x83,
            CommandType.SET_ONE: 0x90,
            CommandType.GET_ONE: 0x91,
            CommandType.FADE_ONE: 0x92,
            CommandType.FLASH_ONE: 0x93,
            CommandType.RANDOM_ONE: 0x94,
            CommandType.SET_ALL: 0x98,
            CommandType.FADE_ALL: 0x96,
            CommandType.FLASH_ALL: 0x97,
            CommandType.LIST_TAGS: 0xa1,
            CommandType.READ_BLOCK: 0xa2,
            CommandType.WRITE_BLOCK: 0xa3,
            CommandType.TAG_INFO: 0xb4,
        }

    @staticmethod
    def magic_prefix() -> int:
        return 0xff

    @staticmethod
    def reply_standard_id() -> int:
        """Message ID for a standard reply. Event message is assumed to be this + 1"""
        return 0xaa

    @staticmethod
    def vid_pid() -> tuple[int, int]:
        """USB VID and PID for the device"""
        return 0x0e6f, 0x0129


class InfinityComms(Comms):
    comms_def = InfinityCommsDefinition()

    async def _unpack_tag_event(self, data: bytes) -> TagChangeEvent:
        tag = Tag(data[0], data[2], data[1])
        is_present = data[3]
        return TagChangeEvent(tag, is_present)

    async def _fetch_tag_uid(self, tag: Tag):
        data = await self.send_message(CommandType.TAG_INFO, [tag.index])
        # First byte is a status or something, 0x00 if the tag exists, 0x80 if it doesn't
        if data[0] == ErrorType.NO_SUCH_TAG.value:
            raise ValueError("No such tag")
        return data[1:]


class InfinityPortal(Portal):
    comms_def = InfinityCommsDefinition()

    def __init__(self, serial: str | None = None):
        super().__init__(InfinityComms(serial), False)

    async def connect(self):
        await super().connect()
        await self.get_all_tags() # Cache any tags sitting on the base now
