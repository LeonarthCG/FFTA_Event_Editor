from enum import Enum
from typing import Optional


class Region(Enum):
    EUR = 1
    USA = 2

def readByte(offset, source):
    return source[offset]

def writeByte(value, offset, source, autoincrement=True) -> int:
    while len(source) <= offset:
        source.append(0xFF)
    source[offset] = value & 0xFF
    return offset + (1 if autoincrement else 0)

def align(value, offset, source, autoincrement=True) -> int:
    padding : int = (value - (offset % value)) % value
    while len(source) <= (offset + padding):
        source.append(0xFF)
    return offset + (padding if autoincrement else 0)

def writeBytes(bytes, offset, source, autoincrement=True) -> int:
    for i, byte in enumerate(bytes):
        writeByte(byte, offset+i, source)
    return offset + (len(bytes) if autoincrement else 0)

def readHalfWord(offset, source):
    return source[offset] | (source[offset + 1] << 8)

def writeHalfWord(value, offset, source, autoincrement=True):
    for i in range(2):
        writeByte(value, offset + i, source)
        value >>= 8
    return offset + (2 if autoincrement else 0)

def readWord(offset, source):
    return source[offset] | (source[offset + 1] << 8) | (source[offset + 2] << 16) | (source[offset + 3] << 24)

def writeWord(value, offset, source, autoincrement=True):
    for i in range(4):
        writeByte(value, offset + i, source)
        value >>= 8
    return offset + (4 if autoincrement else 0)

def readShort(offset, source):  # alias
    return readHalfWord(offset, source)

def writeShort(value, offset, source, autoincrement=True):
    return writeHalfWord(value, offset, source, autoincrement)

def readWordBigEndian(offset, source):
    return (source[offset] << 24) | (source[offset + 1] << 16) | (source[offset + 2] << 8) | source[offset + 3]

def get_event_list_offset(region: Region, source: bytes):
    pointer = EUR_EVENT_LIST_POINTER if region == Region.EUR else USA_EVENT_LIST_POINTER
    return readWord(pointer, source) & 0x1FFFFFF

def repoint_event_list(region: Region, new_offset: int, source):
    pointer = EUR_EVENT_LIST_POINTER if region == Region.EUR else USA_EVENT_LIST_POINTER
    writeWord(new_offset | 0x08000000, pointer, source)

def get_scene_banks_offset(region: Region, source: bytes):
    pointer = EUR_SCENE_BANKS_POINTER if region == Region.EUR else USA_SCENE_BANKS_POINTER
    return readWord(pointer, source) & 0x1FFFFFF

def repoint_scene_banks(region: Region, new_offset: int, source):
    pointer = EUR_SCENE_BANKS_POINTER if region == Region.EUR else USA_SCENE_BANKS_POINTER
    writeWord(new_offset | 0x08000000, pointer, source)

def get_conditional_type_list_offset(region: Region, source: bytes):
    pointer = EUR_CONDITIONAL_TYPE_LIST_POINTER if region == Region.EUR else USA_CONDITIONAL_TYPE_LIST_POINTER
    return readWord(pointer, source) & 0x1FFFFFF

def repoint_conditional_type_list(region: Region, new_offset: int, source):
    pointer = EUR_CONDITIONAL_TYPE_LIST_POINTER if region == Region.EUR else USA_CONDITIONAL_TYPE_LIST_POINTER
    writeWord(new_offset | 0x08000000, pointer, source)

def get_lang_text_bank_offset(region: Region, source: bytes, lang: int):
    pointers = EUR_LANG_TEXT_BANKS_POINTERS if region == Region.EUR else USA_LANG_TEXT_BANKS_POINTERS
    return readWord(pointers[lang], source) & 0x1FFFFFF

def repoint_lang_text_bank(region: Region, new_offset: int, source, lang: int):
    pointers = EUR_LANG_TEXT_BANKS_POINTERS if region == Region.EUR else USA_LANG_TEXT_BANKS_POINTERS
    writeWord(new_offset | 0x08000000, pointers[lang], source)

def find_free_space(source, can_expand=True) -> int:
    if can_expand and len(source) < 0x01FFFFFF:
        return len(source)
    offset = len(source) - 4
    while readWord(offset, source) == 0xFFFFFFFF:
        offset -= 4
    return offset + 4

def get_languages(region: Region) -> list[str]:
    languages: list[str] = EUR_LANGUAGES if region == Region.EUR else USA_LANGUAGES
    return languages


EVENT_COUNT = 234
EUR_EVENT_LIST_POINTER = 0x9AAC # EVENT_LIST = 0xD68C2C in vanilla
USA_EVENT_LIST_POINTER = 0x9A20 # EVENT_LIST = 0xA19970 in vanilla
EUR_SCENE_BANKS_POINTER = 0x125ED0 # SCENE_BANKS = 0xB946EC in vanilla
USA_SCENE_BANKS_POINTER = 0x1223C0 # SCENE_BANKS = 0x9A5D54 in vanilla
EUR_CONDITIONAL_TYPE_LIST_POINTER = 0xA234 # CONDITIONAL_TYPE_LIST = 0xD69BC4 in vanilla
USA_CONDITIONAL_TYPE_LIST_POINTER = 0xA148 # CONDITIONAL_TYPE_LIST = 0xA1A908 in vanilla
LANGUAGES = ['English', 'French', 'German', 'Italian', 'Spanish']
EUR_LANGUAGES = LANGUAGES
USA_LANGUAGES = LANGUAGES[:1]
# by bank here I mean a list of pointers to lists
EUR_LANG_TEXT_BANKS_POINTERS = [
    0x9B04, # English text bank = 0xBB064C in vanilla
    0x9AF8, # French text bank = 0xC076F0 in vanilla
    0x9AE0, # German text bank = 0xC5FBF0 in vanilla
    0x9AE8, # Italian text bank = 0xCB7C48 in vanilla
    0x9AF0, # Spanish text bank = 0xD10644 in vanilla
]
USA_LANG_TEXT_BANKS_POINTERS = [ 0x9A88 ] # English text bank = 0x9C1484 in vanilla
CONDITIONAL_TYPES : list[str] = ['Map node reached', 'Map node selected', 'Mission accepted', 'Turn start', 'Action start', 'Action end', 'Turn end', 'Victory condition met']


class OPCodeArg:
    def __init__(self, size, signed=False):
        self._size = size
        self._sign_bit = 0
        self._mask = 0
        if signed:
            self._sign_bit = 1<<(self._size*8 - 1)
            for i in range(self._size):
                self._mask |= 0xFF << (i*8)
     
    def get_size(self):
        return self._size
    
    def get_value(self, offset, source):
        value = 0
        for i in range(self._size):
            value += readByte(offset, source) << (8*i)
            offset += 1
        if self._sign_bit & value:
            value = -(~value & self._mask) - 1
        return value

    def build(self, value: int) -> bytearray:
        output = bytearray()
        mask = self._mask
        for i in range(self._size):
            byte = value & 0xFF
            value = value >> 8
            if self._sign_bit:
                byte &= mask
                mask >>= 8
            output.append(byte)
        assert len(output) == self.get_size()
        return output

class OPCode:
    def __init__(self, args=None, name='', is_terminator=False, branch=None):
        if args is None:
            args = []
        self._args = args
        self._name = name
        self._size = 1 + sum(arg.get_size() for arg in args)
        self.is_terminator = is_terminator
        self._byte = None
        self._branch = branch

    def build(self, base_offset, values: list[int]) -> bytearray:
        output = bytearray()
        output.append(self.get_byte())
        assert len(values) == len(self._args)
        i = 0
        for arg, value in zip(self._args, values):
            if self._branch == i:
                value -= base_offset
                value -= self.get_size()
            output.extend(arg.build(value))
            i += 1
        assert len(output) == self._size
        return output

    def get_arg_count(self):
        return len(self._args)
    
    def set_byte(self, byte):
        if self._byte is not None:
            print('OPCode byte already set!')
            exit(0)
        self._byte = byte
        if not self._name:
            self._name = f'_UNDEFINED_{str(self._byte)}_'

    def get_byte(self) -> int:
        return self._byte
     
    def get_name(self) -> str:
        return self._name
     
    def get_size(self):
        return self._size
    
    def to_string(self, offset, source):
        base_offset = offset
        if self._byte is None:
            print('OPCode byte not set!')
            exit(0)
        if readByte(offset, source) != self._byte:
            print('OPCode mismatch!')
            exit(0)
        out = self._name
        offset += 1
        for i, arg in enumerate(self._args):
            if i == self._branch:
                branch_offset = base_offset + self.get_size()
                branch_offset += self._args[i].get_value(offset, source)
                out += f' _{hex(branch_offset)}'
            else:
                out += f' {arg.get_value(offset, source)}'
            offset += arg.get_size()
        return out

    def get_new_offset(self, offset):
        """
        if self.is_terminator:
            print('Terminator OPCode does not lead to new offset!')
            exit(0)
        """
        return offset + self.get_size()
    
    def is_branching(self):
        return self._branch is not None
    
    def get_branch_offset(self, offset, source):
        if self._branch is None:
            print('Non-branching OPCode does not lead to new label!')
            exit(0)
        branch_offset = offset + self.get_size()
        offset += 1
        i = 0
        while i != self._branch:
            offset += self._args[i].get_size()
            i += 1
        branch_offset += self._args[self._branch].get_value(offset, source)
        return branch_offset

byte_arg = OPCodeArg(1)
half_arg = OPCodeArg(2)
word_arg = OPCodeArg(4)

s_half_arg = OPCodeArg(2, signed=True)


class InstructionSet:
    _opcodes : list[OPCode]
    _name_to_byte : dict[str, int]

    def __init__(self, opcodes: list[OPCode]):
        self._opcodes = opcodes
        self._name_to_byte = {op.get_name(): op.get_byte() for op in opcodes}

    def get_opcode(self, byte) -> Optional[OPCode]:
        self.get_opcode_by_byte(byte)

    def get_opcode_by_byte(self, byte) -> Optional[OPCode]:
        if 0 <= byte < len(self._opcodes):
            return self._opcodes[byte]
        else:
            return None

    def get_opcode_by_name(self, name) -> Optional[OPCode]:
        if name in self._name_to_byte:
            return self.get_opcode_by_byte(self._name_to_byte[name])
        else:
            return None


_SCENE_OPCODES = [
    OPCode([byte_arg, s_half_arg], name='THREAD_WITH_TAG', branch=1), #4 0x8126625
    OPCode([s_half_arg], name='THREAD', branch=0), #3 0x8126661
    OPCode(name='END', is_terminator=True), #1 0x812669d
    OPCode([byte_arg], name='JOIN_TAG'), #2 0x81266b5
    OPCode(name='JOIN'), #1 0x81266d9
    OPCode(), #1 0x81266fd
    OPCode([byte_arg, byte_arg, byte_arg], name='FADE_SCREEN'), #4 0x812670d
    OPCode(), #1 0x8126739
    OPCode(), #1 0x812674d
    OPCode(), #1 0x812677d
    OPCode([byte_arg, byte_arg]), #3 0x81267b9
    OPCode([byte_arg, byte_arg, byte_arg]), #4 0x8126815
    OPCode([byte_arg], name='SET_MAP'), #2 0x8126831
    OPCode(), #1 0x8126875
    OPCode([byte_arg]), #2 0x8126885
OPCode([byte_arg, byte_arg, byte_arg], name='CHAR_TALK'), #4 0x81268bd
    OPCode([half_arg]), #3 0x81268cd
    OPCode([byte_arg]), #2 0x81268e5
    OPCode([byte_arg]), #2 0x81268f9
    OPCode(), #1 0x812692d
    OPCode([byte_arg]), #2 0x812693d
    OPCode([byte_arg], name='SLEEP'), #2 0x8126945
    OPCode([half_arg]), #3 0x8126951
    OPCode([byte_arg], is_terminator=True), #2 0x8126961
    OPCode([byte_arg]), #2 0x8125fc9
    OPCode([s_half_arg], name='GO_TO', is_terminator=True, branch=0), #3 0x812698d
OPCode([half_arg, byte_arg], name='SET_FLAG'), #4 0x81269a1
OPCode([half_arg, byte_arg]), #4 0x81269b9
    OPCode([half_arg]), #3 0x81269d1
    OPCode([byte_arg]), #2 0x8126a09
    OPCode([byte_arg]), #2 0x8126a35
    OPCode([byte_arg, byte_arg, byte_arg, byte_arg, byte_arg], name='LOAD_CHAR'), #6 0x8126a69
    OPCode([byte_arg, byte_arg, byte_arg, byte_arg], name='LOAD_UNIT'), #5 0x8126a9d
    OPCode([byte_arg, byte_arg]), #3 0x8126ac9
    OPCode([byte_arg]), #2 0x8126add
    OPCode([byte_arg]), #2 0x8126af9
    OPCode([byte_arg]), #2 0x8126b0d
    OPCode([byte_arg, byte_arg, byte_arg], name='CHAR_SET_IDLE_POSE'), #4 0x8126b21
    OPCode([byte_arg, byte_arg]), #3 0x8126b3d
    OPCode([byte_arg, half_arg, byte_arg], name='CHAR_POSE'), #5 0x8126b55
    OPCode([byte_arg], name='CHAR_FREEZE_POSE'), #2 0x8126b75
    OPCode([byte_arg, byte_arg], name='CHAR_SET_DIRECTION'), #3 0x8126b91
    OPCode([byte_arg], name='CHAR_STOP_ANIMATION'), #2 0x8126ba9
OPCode([byte_arg, byte_arg, byte_arg, byte_arg]), #5 0x8126bb9
OPCode([byte_arg, byte_arg, byte_arg]), #4 0x8126bd5
OPCode([byte_arg, byte_arg, byte_arg]), #4 0x8126bed
    OPCode([byte_arg, half_arg, half_arg, half_arg], name='CHAR_WARP_TO_POS_RELATIVE'), #8 0x8126c1d ; char, x, y, height
    OPCode([byte_arg, byte_arg, byte_arg], name='CHAR_WARP_TO_TILE'), #4 0x81260a9 ; character, row, col
    OPCode([byte_arg, byte_arg, byte_arg], name='CHAR_SET_SHADOW'), #4 0x8126c5d
OPCode([byte_arg, byte_arg, byte_arg, byte_arg]), #5 0x8126cc1
    OPCode([byte_arg]), #2 0x8126d0d
OPCode([byte_arg, byte_arg, byte_arg, byte_arg, byte_arg, byte_arg, byte_arg, byte_arg]), #9 0x8126d35
    OPCode([byte_arg, byte_arg]), #3 0x812611d
    OPCode([byte_arg, byte_arg]), #3 0x8126d45
    OPCode([byte_arg]), #2 0x8126da5
    OPCode([byte_arg]), #2 0x8126db5
OPCode([byte_arg, byte_arg, byte_arg, byte_arg, byte_arg, byte_arg]), #7 0x8126dd9
    OPCode([byte_arg, half_arg, half_arg, byte_arg, half_arg], 'CHAR_MOVE_TO_POS'), #9 0x8126e31 ; char, x, y, ?, height?
OPCode([byte_arg, byte_arg, byte_arg, byte_arg, byte_arg, byte_arg]), #7 0x8126ea9
OPCode([byte_arg, byte_arg, byte_arg, byte_arg, byte_arg, byte_arg, byte_arg]), #8 0x8126f09
OPCode([byte_arg, byte_arg, byte_arg, byte_arg, byte_arg]), #6 0x8126f11
OPCode([byte_arg, byte_arg, byte_arg, byte_arg, byte_arg, byte_arg, byte_arg, byte_arg, byte_arg]), #10 0x8126281
OPCode([byte_arg, byte_arg, byte_arg, byte_arg, byte_arg, byte_arg, byte_arg]), #8 0x8126f19
OPCode([byte_arg, byte_arg, byte_arg]), #4 0x8126f85
OPCode([byte_arg, byte_arg, byte_arg]), #4 0x8126fc5
OPCode([byte_arg, byte_arg, byte_arg]), #4 0x812700d
OPCode([byte_arg, byte_arg, byte_arg]), #4 0x812703d
    OPCode([byte_arg, byte_arg]), #3 0x8127075
OPCode([byte_arg, byte_arg, byte_arg, byte_arg]), #5 0x8127091
OPCode([byte_arg, byte_arg, byte_arg]), #4 0x81270b9
OPCode([byte_arg, byte_arg, byte_arg]), #4 0x8126309
    OPCode([half_arg, half_arg, byte_arg, byte_arg], name='CAMERA_MOVE_TO_POS'), #7 0x81263e5 ; x, y, ?, ?
    OPCode([byte_arg], name='SET_MAP_TYPE'), #2 0x81270d1
    OPCode([byte_arg]), #2 0x81270f5
    OPCode(), #1 0x8127161
    OPCode([byte_arg], name='PLAY_SONG'), #2 0x8127185
    OPCode([half_arg, byte_arg], name='PLAY_SOUND'), #4 0x8127261
    OPCode([byte_arg, half_arg, byte_arg], name='FADE_MUSIC'), #5 0x8127205 ; final volume, frames to take, ?
    OPCode(name='START_MAP'), #1 0x81272c1
    OPCode([byte_arg, byte_arg]), #3 0x8127305
    OPCode([byte_arg]), #2 0x8127325
    OPCode(), #1 0x8127339
    OPCode(), #1 0x8127351
    OPCode([half_arg]), #3 0x8127389
    OPCode([byte_arg]), #2 0x81273f1
OPCode([byte_arg, byte_arg, byte_arg, byte_arg]), #5 0x812740d
    OPCode(), #1 0x8127429
    OPCode(), #1 0x8127439
    OPCode(), #1 0x8127449
    OPCode([byte_arg]), #2 0x8127459
    OPCode([byte_arg]), #2 0x812746d
    OPCode(), #1 0x8127485
    OPCode([half_arg]), #3 0x81274b5
    OPCode([byte_arg, byte_arg]), #3 0x81274cd
    OPCode(), #1 0x81274e9
    OPCode([byte_arg]), #2 0x81274f9
    OPCode(), #1 0x812750d
    OPCode(), #1 0x812751d
OPCode([byte_arg, byte_arg, byte_arg, byte_arg, byte_arg, byte_arg, byte_arg, byte_arg]), #9 0x8127551
    OPCode(), #1 0x812756d
OPCode([byte_arg, byte_arg, byte_arg]), #4 0x812757d
    OPCode([half_arg, s_half_arg], name='GO_TO_IF_FLAG', branch=1), #5 0x81275bd
OPCode([byte_arg, byte_arg, s_half_arg]), #5 0x81275ed
OPCode([byte_arg, byte_arg, byte_arg]), #4 0x8127625
OPCode([byte_arg, byte_arg, byte_arg]), #4 0x8127659
    OPCode([half_arg]), #3 0x81276b9
    OPCode([half_arg]), #3 0x81276fd
    OPCode(), #1 0x8127741
OPCode([byte_arg, byte_arg, byte_arg]), #4 0x8127749
    OPCode([half_arg]), #3 0x81277b1
    OPCode([half_arg]), #3 0x81277ed
OPCode([byte_arg, byte_arg, byte_arg, byte_arg]), #5 0x8126495
    OPCode([half_arg]), #3 0x8126511
    OPCode([half_arg]), #3 0x8127819
OPCode([byte_arg, byte_arg, byte_arg]), #4 0x8127841
]

for index, opcode in enumerate(_SCENE_OPCODES):
    opcode.set_byte(index)

SCRIPT_INSTRUCTION_SET = InstructionSet(_SCENE_OPCODES)


_CONDITIONALS_OPCODES = [
    OPCode(name='END', is_terminator=True), #1 0x800a295
    OPCode([s_half_arg], name='GO_TO', is_terminator=True, branch=0), #3 0x800a299
    OPCode([half_arg, byte_arg], name='SET_FLAG_1'), #4 0x800a2a9
    OPCode([half_arg, byte_arg], name='SET_FLAG_2'), #4 0x800a2bd
    OPCode([half_arg, s_half_arg], name='GO_TO_IF_FLAG', branch=1), #5 0x800a2d1
    OPCode([half_arg], name='START_EVENT'), #3 0x800a2fd
OPCode([byte_arg, s_half_arg], branch=1), #4 0x800a331
OPCode([byte_arg, byte_arg, s_half_arg], branch=2), #5 0x800a3dd
OPCode([byte_arg, byte_arg, s_half_arg], branch=2), #5 0x800a41d
OPCode([byte_arg, byte_arg, s_half_arg], branch=2), #5 0x800a459
OPCode([byte_arg, s_half_arg], branch=1), #4 0x800a4d1
OPCode([byte_arg, s_half_arg], branch=1), #4 0x800a50d
OPCode([byte_arg, s_half_arg], branch=1), #4 0x800a57d
OPCode([byte_arg, s_half_arg], branch=1), #4 0x800a5d9
OPCode([s_half_arg], branch=0), #3 0x800a5e5
OPCode([s_half_arg], branch=0), #3 0x800a651
OPCode([s_half_arg], branch=0), #3 0x800a68d
]

for index, opcode in enumerate(_CONDITIONALS_OPCODES):
    opcode.set_byte(index)

CONDITIONALS_INSTRUCTION_SET = InstructionSet(_CONDITIONALS_OPCODES)
        
# gather every script index used by an event, as well as the scenes used for that script by an event
def get_used_scenes(region: Region, source):
    used_scenes = {0: set()}
    for event_id in range(1, EVENT_COUNT): # event 0 is reserved
        event_offset = get_event_list_offset(region, source) + event_id*4
        
        script_index = readByte(event_offset, source)
        scene_index = readByte(event_offset + 1, source)
        
        # if this is a new script, or a new scene for a known script, add it to the dict
        if script_index not in used_scenes.keys():
            used_scenes[script_index] = set()
        used_scenes[script_index].add(scene_index)
    return used_scenes

CHARACTER_TABLE = [
    'Ç', '¿', 'À', 'Á', 'Â', 'Ä', 'È', 'É', 'Ê', 'Ë', 'Ì', 'Í', 'Î', 'Ï', 'Ñ', 'Ò',
    'Ó', 'Ô', 'Ö', 'Ù', 'Ú', 'Û', 'Ü', 'ß', 'À', 'á', 'â', 'ä', 'è', 'é', 'ê', 'ë',
    'ì', 'í', 'î', 'ï', 'ñ', 'ò', 'ó', 'ô', 'ö', 'ù', 'ú', 'û', 'ü', 'º', '—', 'ç',
    '¡', 'ひ', 'び', 'ぴ', 'ふ', 'ぶ', 'ぷ', 'へ', 'べ', 'ぺ', 'ほ', 'ぼ', 'ぽ', 'ま', 'み', 'む',
    'め', 'も', 'ゃ', 'や', 'ゅ', 'ゆ', 'ょ', 'よ', 'ら', 'り', 'る', 'れ', 'ろ', 'ゎ', 'わ', 'を',
    'ん', 'ァ', 'Ａ', 'ィ', 'Ｂ', 'ゥ', 'Ｃ', 'ェ', '—', 'ォ', 'オ', 'カ', 'ガ', 'キ', 'ギ', 'ク',
    'グ', 'ケ', 'ゲ', 'コ', 'ゴ', 'サ', 'ザ', 'シ', 'ジ', 'ス', 'ズ', 'セ', 'ゼ', 'ソ', 'ゾ', 'タ',
    'ダ', 'チ', 'ヂ', 'ッ', 'ツ', 'ヅ', 'テ', 'デ', 'ト', 'ド', 'ナ', 'ニ', 'ヌ', 'ネ', 'ノ', 'ハ',
    'バ', 'パ', 'ヒ', 'ビ', 'ピ', 'フ', 'ブ', 'プ', 'ヘ', 'ベ', 'ペ', 'ホ', 'ボ', 'ポ', 'マ', 'ミ',
    'ム', 'メ', 'モ', 'ャ', 'ヤ', 'ュ', 'ユ', 'ョ', 'ヨ', 'ラ', 'リ', 'ル', 'レ', 'ロ', 'ヮ', 'ワ',
    'ヲ', 'ン', 'ヴ', '、', '。', '点', 
    '0', '1', '2', '3', '4', '5', '6', '7', '8', '9',
    'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z',
    'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z',
    '.', '「', '」', '『', '』', '点', '?', '!', ',', '·', ':', '_',
    '々', '/', '~', '‘', "'", '“', '”', '(', ')', '{', '}', '【', '】', '+', '-', '±',
    '×', '=', '<', '>', '∞', '♂', '♀', '%', '&', '*', '※', '─', '│',
    '▲', '▼', '⯇', '⯈',
    '○', '△', '□', '■',
    '♪', ';', '◎',
    '０', '１', '２', '３', '４', '５', '６', '７', '８', '９',
    # the rest of these are kanji, except the final 2, which are a '○' and '#'
]


CONTROL_CODES = {
    '0x21': 0x21,
    'VARNAME': 0x25,
    'SPACE': 0x3E,
    'A': 0x61,
    'CLS': 0x63,
    'NL': 0x6E,
    'NAME': 0x72,
    'WS': 0x73,
    'WAIT': 0x74,
}

LONG_CONTROL_CODES = [ 0x21, 0x25, 0x3E, 0x72, 0x74 ]


def decompress_lzss(offset, source):
    data = bytearray()
    # Get expected length of uncompressed file
    length = readWordBigEndian(offset, source)
    offset += 4
    # Decompress
    while length > len(data):
        # Bit 7 (0x80)
        if source[offset] & 0x80 != 0:
            count = ((source[offset] & 0x78) >> 3) + 3
            start = len(data) - (((source[offset] & 0x07) << 8) | source[offset+1]) - 1
            offset += 2
            if count != 0:
                for i in range(0, count):
                    if not (length > len(data)):
                        break
                    data.append(data[start+i])
        # Bit 6 (0x40)
        elif source[offset] & 0x40 != 0:
            count = (source[offset] & 0x3F) + 1
            offset += 1
            if count != 0:
                for i in range(0, count):
                    if not (length > len(data)):
                        break
                    data.append(source[offset])
                    offset += 1
        # Bit 5 (0x20)
        elif source[offset] & 0x20 != 0:
            count = (source[offset] & 0x1F) + 2
            offset += 1
            if count != 0:
                for i in range(0, count):
                    if not (length > len(data)):
                        break
                    data.append(0x00)
        # Bit 4 (0x10)
        elif source[offset] & 0x10 != 0:
            count = ((source[offset] & 0x0F) | ((source[offset + 1] & 0xC0) >> 0x02)) + 4
            start = len(data) - (((source[offset + 1] & 0x3F) << 8) | source[offset + 2]) - 1
            offset += 3
            if count != 0:
                for i in range(0, count):
                    if not (length > len(data)):
                        break
                    data.append(data[start+i])
        # Bit 3 (0x08) goes unused, it's data only
        # Bit 2 (0x04) goes unused, it's data only
        # Bit 1 (0x02)
        elif source[offset] == 2:
            count = source[offset + 1] + 3
            offset += 2
            if count != 0:
                for i in range(0, count):
                    if not (length > len(data)):
                        break
                    data.append(0x00)
        # Bit 0 (0x01)
        elif source[offset] == 1:
            count = source[offset + 1] + 3
            offset += 2
            if count != 0:
                for i in range(0, count):
                    if not (length > len(data)):
                        break
                    data.append(0xff)
        # No bits set (0x00)
        elif source[offset] == 0:
            count = source[offset + 1] + 5
            start = len(data) - ((source[offset + 2] << 8) | source[offset + 3]) - 1
            offset += 4
            if count != 0:
                for i in range(0, count):
                    if not (length > len(data)):
                        break
                    data.append(data[start+i])
        else:
            raise Exception("Could not decompress: invalid LZSS data.")
    return data
