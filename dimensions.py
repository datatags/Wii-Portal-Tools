from portal import Comms, Portal
from data_structures import *

class LegoCommsDefinition(CommsDefinition):
    @staticmethod
    def activation_str() -> bytes:
        return b"(c) LEGO 2014"

    @staticmethod
    def get_command_set() -> dict[CommandType, int]:
        return {
            CommandType.ACTIVATE: 0xb0,
            CommandType.SEED_RNG: 0xb1,
            CommandType.GET_RNG: 0xb3,
            CommandType.SET_ONE: 0xc0,
            CommandType.GET_ONE: 0xc1,
            CommandType.FADE_ONE: 0xc2,
            CommandType.FLASH_ONE: 0xc3,
            CommandType.RANDOM_ONE: 0xc4,
            CommandType.SET_ALL: 0xc8,
            CommandType.FADE_ALL: 0xc6,
            CommandType.FLASH_ALL: 0xc7,
            CommandType.LIST_TAGS: 0xd0,
            CommandType.READ_BLOCK: 0xd2,
            CommandType.WRITE_BLOCK: 0xd3,
            CommandType.TAG_PWD: 0xe1,
            CommandType.NFC_ON: 0xe5,
        }

    @staticmethod
    def magic_prefix() -> int:
        return 0x55

    @staticmethod
    def reply_standard_id() -> int:
        """Message ID for a standard reply. Event message is assumed to be this + 1"""
        return 0x55

    @staticmethod
    def vid_pid() -> tuple[int, int]:
        """USB VID and PID for the device"""
        return 0x0e6f, 0x0241


class LegoComms(Comms):
    comms_def = LegoCommsDefinition()

    def __init__(self, serial: str = None):
        super().__init__(serial)

    async def _unpack_tag_event(self, data: bytes) -> TagChangeEvent:
        tag = Tag(data[0], data[2], data[1], data[4:11])
        is_present = data[3]
        return TagChangeEvent(tag, is_present)

    async def _fetch_tag_uid(self, tag: Tag) -> bytes:
        return None


class LegoPortal(Portal):
    comms_def = LegoCommsDefinition()

    def __init__(self, serial: str | None = None):
        super().__init__(LegoComms(serial))

