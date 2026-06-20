from ffta_common import *

print('scene opcode data:')
offset = 0x3ACEBC
for opcode in range(115):
    print(f'{str(readHalfWord(offset))} {hex(readWord(offset + 2))}')
    offset += 6
print()

print('conditionals opcode data:')
offset = 0x370F94
for opcode in range(17):
    print(f'{str(readHalfWord(offset))} {hex(readWord(offset + 2))}')
    offset += 6
print()
