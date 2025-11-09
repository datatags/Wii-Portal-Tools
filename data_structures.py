from dataclasses import dataclass, astuple
from abc import ABC, abstractmethod
from enum import Enum, IntEnum

@dataclass
class Color:
    """Simple class to avoid having to pass around r/g/b separately

    Each value should 0-255, inclusive.
    """
    r: int
    g: int
    b: int

    def __iter__(self):
        # https://stackoverflow.com/a/59569566 for easier unpacking
        return iter(astuple(self))


class CommandType(Enum):
    ACTIVATE = 0
    SEED_RNG = 1
    GET_RNG = 2
    SET_ONE = 3
    GET_ONE = 4
    FADE_ONE = 5
    FLASH_ONE = 6
    RANDOM_ONE = 7
    SET_ALL = 8
    FADE_ALL = 9
    FLASH_ALL = 10
    LIST_TAGS = 11
    READ_BLOCK = 12
    WRITE_BLOCK = 13
    TAG_INFO = 14
    TAG_PWD = 15
    NFC_ON = 16
    PING = 17


class AuthMode(IntEnum):
    OFF = 0
    DEFAULT = 1
    CUSTOM = 2


class Platform(Enum):
    ALL_PLATFORMS = 0
    CENTER = 1
    PLAYER_ONE = 2
    PLAYER_TWO = 3

    def __int__(self):
        return self.value


class ErrorType(Enum):
    SUCCESS = (0x00, "Success")
    NO_SUCH_TAG = (0x80, "No such tag") # Occurs when requesting info on a tag index that isn't there
    TAG_IO_ERROR = (0x82, "Tag I/O error") # General failure, e.g. auth failure or tag removed during communication
    TAG_AUTH_UNSUPPORTED = (0x83, "Tag auth unsupported") # Tag requires an unsupported authentication method

    def __new__(cls, val: int, msg: str):
        entry = object.__new__(cls)
        entry._value_ = val
        entry.msg = msg
        return entry

    def __str__(self):
        return self.msg


class Tag:
    def __init__(self, platform: int | Platform, index: int, sak: int, uid: bytes = None):
        self.platform = platform
        self.index    = index
        # ISO 14443A SAK, always 0x09 for DI tags (Mifare Classic Mini) and 0x00 for LD tags (NTAG/Mifare Ultralight)
        # but you may see other values by putting other NFC tags on the portal!
        self.sak      = sak
        self.uid      = uid

    @staticmethod
    def from_bytes(index: bytes):
        return Tag(index[0] >> 4, index[0] & 0x0F, index[1])

    def __str__(self):
        return f"Tag(platform={int(self.platform)},index={self.index},sak={self.sak},uid={self.uid})"

    def __repr__(self):
        return str(self)


@dataclass
class TagChangeEvent:
    tag: Tag
    is_removed: bool


class CommsDefinition(ABC):
    @classmethod
    @abstractmethod
    def activation_str(cls) -> str:
        """String sent with activation command to activate the portal"""
        pass

    @classmethod
    @abstractmethod
    def get_command_set(cls) -> dict[CommandType, int]:
        """Get the supported commands and their IDs"""
        pass

    @classmethod
    @abstractmethod
    def magic_prefix(cls) -> int:
        """Magic number that marks the beginning of a command"""
        pass

    @classmethod
    @abstractmethod
    def reply_standard_id(cls) -> int:
        """Message ID for a standard reply. Event message is assumed to be this + 1"""
        pass

    @classmethod
    @abstractmethod
    def vid_pid(cls) -> tuple[int, int]:
        """USB VID and PID for the device"""
        pass

    @classmethod
    @abstractmethod
    def has_nfc_sectors(cls) -> bool:
        """Whether the base uses a sector parameter for NFC commands (i.e. designed for Mifare Classic, like DI is)"""
        pass

    @classmethod
    @abstractmethod
    def ticks_per_second(cls) -> int:
        """Number of 'ticks', i.e. the number to put in the duration field to get 1 second"""
        pass
