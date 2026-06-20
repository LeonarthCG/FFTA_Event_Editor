from ffta_common import *
from pathlib import Path

scene_opcode_frequency = {byte: 0 for byte in range(len(SCENE_OPCODES))}
conditionals_opcode_frequency = {byte: 0 for byte in range(len(CONDITIONALS_OPCODES))}

scene_opcode_script_frequency = {byte: set() for byte in range(len(SCENE_OPCODES))}
conditionals_opcode_script_frequency = {byte: set() for byte in range(len(CONDITIONALS_OPCODES))}

current_script_id = 0

# reads the ROM's binary data, starting from a given offset, and parses all branches of execution
def _parse_raw_script(starting_offsets, label_offsets, empty_starts, operators):
    visited_labels = [False for offset in label_offsets]
    script_data = ''
    for offset in label_offsets:
        while True:
            if offset in starting_offsets and starting_offsets.index(offset) in empty_starts:
                break
            # prevent visiting the same label more than once
            if offset in label_offsets:
                # if already visited, ignore
                if visited_labels[label_offsets.index(offset)]:
                    break
                # otherwise, mark as visited and proceed
                else:
                    visited_labels[label_offsets.index(offset)] = True
            # add the label to the output
            if offset in label_offsets:
                script_data += f'_{hex(offset)}:\n'
            # decode the next opcode
            opcode_byte = readByte(offset)
            opcode = operators[opcode_byte]
            # keep track of opcodes found the most, to determine how important they are
            if operators == SCENE_OPCODES:
                scene_opcode_frequency[opcode_byte] += 1
                scene_opcode_script_frequency[opcode_byte].add(current_script_id)
            elif operators == CONDITIONALS_OPCODES:
                conditionals_opcode_frequency[opcode_byte] += 1
                conditionals_opcode_script_frequency[opcode_byte].add(current_script_id)
            script_data += f'/*{hex(offset)}*/ {opcode.to_string(offset)}\n'
            # if it references a new label, add it to the list
            if opcode.is_branching():
                branch_offset = opcode.get_branch_offset(offset)
                if branch_offset not in label_offsets:
                    label_offsets.append(branch_offset)
                    visited_labels.append(False)
                    # print(f'new label from {hex(offset)}: {hex(branch_offset)}')
                # print(f'jump to existing label from {hex(offset)}: {hex(branch_offset)}')
            offset = opcode.get_new_offset(offset)
            if opcode.is_terminator:
                script_data += '\n'
                break
    # handle the output for empty scripts
    # we need to print a label for each starting offset that is empty
    unique_starting_offsets = list(dict.fromkeys(starting_offsets))
    for offset in unique_starting_offsets:
        if starting_offsets.index(offset) in empty_starts:
            script_data += f'_{hex(offset)}:\n'
    return script_data.rstrip() + '\n' # standardize final newline
    

def dump_script(starting_offsets, empty_starts, operators, steps=4):
    label_offsets = [offset for offset in starting_offsets]
    # first, gather the labels used
    if steps < 1:
        return ''
    script_data = _parse_raw_script(starting_offsets, label_offsets, empty_starts, operators)
    # now, if needed, we can parse the script again with sorted label offsets
    if steps < 2:
        return script_data
    sorted_labels = sorted(label_offsets)
    if not label_offsets == sorted_labels:
        label_offsets = sorted_labels
        script_data = _parse_raw_script(starting_offsets, label_offsets, empty_starts, operators)
    # remove start offsets from label offset list
    label_offsets = [offset for offset in label_offsets if offset not in starting_offsets]
    start_labels = {offset: '' for offset in list(dict.fromkeys(starting_offsets))}
    for i, offset in enumerate(starting_offsets):
        if start_labels[offset]:
            start_labels[offset] += '\n'
        start_labels[offset] += f'start_{i}:'
    # replace start offsets with start labels
    if steps < 3:
        return script_data
    for offset, label in start_labels.items():
        script_data = script_data.replace(f'_{hex(offset)}:', label)
    for i, offset in enumerate(starting_offsets):
        script_data = script_data.replace(f'_{hex(offset)}', f'start_{i}')
    # replace other symbol names
    if steps < 4:
        return script_data
    for i, offset in enumerate(label_offsets):
        script_data = script_data.replace(f'_{hex(offset)}', f'l_{i}')
    return script_data


def _dump_string_compact(offset, source=rom):
    string = ""
    string_ended = False
    while not string_ended:
        byte = readByte(offset, source)
        offset += 1
        if not byte:
            string_ended = True
        else:
            character_index = readByte(offset, source) - 1
            if character_index < len(CHARACTER_TABLE):
                character = CHARACTER_TABLE[character_index]
            else:
                character = f'{hex(character_index)}'
            string += character
    return string


def dump_string(offset):
    header = readHalfWord(offset)
    compression = header & 0x3
    offset += 2
    if compression == 1:
        return ""
        return _dump_string_compact(offset, rom)
    elif compression == 2:
        source = decompress_lzss(offset)
        offset = 0
    else:
        source = rom

    string = ""
    string_ended = False
    while not string_ended:
        byte = readByte(offset, source)
        offset += 1
        match byte:
            case 0:
                string_ended = True
            case 1:
                string += _dump_string_compact(offset, source)
                string_ended = True
            case 0x40:
                control = readByte(offset, source)
                offset += 1
                match control:
                    case 0x21:
                        string += f'[UNK_0x21][{readByte(offset, source)}]'
                        offset += 1
                    case 0x25:
                        string += f'[VARNAME][{readByte(offset, source)}]'
                        offset += 1
                    case 0x3E:
                        string += f'[SPACE][{readByte(offset, source)}]'
                        offset += 1
                    case 0x61:
                        string += '[A]'
                    case 0x63:
                        string += '[CLS]'
                    case 0x6E:
                        string += '\n'
                    case 0x72:
                        string += f'[NAME][{readByte(offset, source)}]'
                        offset += 1
                    case 0x73:
                        string += ' '
                    case 0x74:
                        string += f'[WAIT][{readByte(offset, source)}]'
                        offset += 1
                    case _:
                        string += f'[{hex(control)}]'
            case _:
                character_index = ((byte << 8) | readByte(offset, source)) - 0x8000
                if character_index >= 0 and character_index < len(CHARACTER_TABLE):
                    character = CHARACTER_TABLE[character_index]
                else:
                    #print(f'type: {hex(byte)}')
                    character = f'({hex(character_index)})'
                string += character
                offset += 1
    if string:
        string += '\n'
    return string


used_scenes = get_used_scenes()
# these are scenes that were determined to be empty by first running empty_script_finder.py, then checking the data for the scenes manually
# keys are script indexes that have empty scenes, and the items are lists of scenes that are empty for that script
EXCLUDED_SCENES = {36: [0], 46: [1], 48: [1], 49: [1], 54: [0], 59: [0, 1]}

# these are conditionals that were determined to be empty by first running empty_script_finder.py, then checking the data for the conditionals manually
# keys are script indexes that have empty conditionals, and the items are lists of conditionals that are empty for that script
EXCLUDED_CONDITIONALS = {
    1: [2],
    2: [2],
    3: [2],
    4: [2],
    5: [2],
    6: [2],
    7: [2],
    8: [2],
    10: [2],
    12: [2],
    17: [2],
    20: [2],
    23: [2],
    24: [2],
    26: [2],
    29: [2],
    31: [2],
    32: [2],
    33: [2],
    35: [2],
    36: [2],
    38: [2],
    39: [2],
    40: [2],
    43: [2],
    44: [2],
    45: [2],
    47: [2],
    48: [2],
    50: [2],
    52: [2],
    53: [2],
    54: [2],
    56: [2],
    57: [2],
    59: [2],
    62: [2],
}

string_starts = set()
string_count = 0
string_done = 0
# and dump the data
for script_index in range(1, 62):
    current_script_id = script_index

    # create the folders
    script_path = f'./scripts/{str(script_index).zfill(2)}'
    conditionals_path = f'{script_path}/conditionals'
    strings_path = f'{script_path}/strings'

    Path(conditionals_path).mkdir(parents=True, exist_ok=True)
    for language in LANGUAGES:
        Path(f'{strings_path}/{language}').mkdir(parents=True, exist_ok=True)
    
    # get the offset of the scene list
    scene_list_relative_offset = readWord(SCENE_BANKS - 4 + script_index*4)
    scene_list = SCENE_BANKS + scene_list_relative_offset
    # and the offset of each scene used
    scene_offsets = []
    #print(f'- dumping script {script_index} scenes -')
    for scene_index in used_scenes[script_index]:
        scene_relative_offset = readWord(scene_list + scene_index*4)
        scene_offset = scene_list + scene_relative_offset
        scene_offsets.append(scene_offset)
        #print(f'scene {scene_index}: {hex(scene_offset)}')
    empty_scenes = EXCLUDED_SCENES.get(script_index, [])
    
    script_data = dump_script(scene_offsets, empty_scenes, SCENE_OPCODES)
    file_path = f'{script_path}/scenes.txt'
    with open(file_path, 'w') as out:
        out.write(script_data)
    
    #print(f'- dumping script {script_index} conditionals -')
    for conditional_type in range(8):
        current_script_id = str(script_index) + '.' + str(conditional_type)
        # get list for this type of conditional
        conditionals_relative_offset = readHalfWord(CONDITIONAL_TYPE_LIST + conditional_type*2)
        conditionals_list = CONDITIONAL_TYPE_LIST + conditionals_relative_offset
        # and get the offset for this script's conditionals of that type
        conditionals_offset = conditionals_list + readHalfWord(conditionals_list + script_index*2)
        #print(f'type {conditional_type} conditionals: {hex(conditionals_offset)}')
        if conditional_type in EXCLUDED_CONDITIONALS.get(script_index, []):
            script_data = dump_script([conditionals_offset], [0], CONDITIONALS_OPCODES)
        else:
            script_data = dump_script([conditionals_offset], [], CONDITIONALS_OPCODES)
    
        file_path = f'{conditionals_path}/{conditional_type}.txt'
        with open(file_path, 'w') as out:
            out.write(script_data)

    if script_index == 61:  # hardcoded to not display text
        continue
    for language_id, language in enumerate(LANGUAGES):
        #print(f'- dumping script {script_index} {language} strings -')
        # get list for this language
        lang_text_list = LANG_TEXT_BANKS[language_id]
        # and get the offset for this script's text list for this language
        scene_text_list = lang_text_list + readWord(lang_text_list + script_index*4)
        list_end = scene_text_list + readHalfWord(scene_text_list) # the offset of the first string marks the end of the table, padding included
        for index, offset in enumerate(range(scene_text_list, list_end, 2)):
            string_count += 1
            string_relative_offset = readHalfWord(offset)
            # check if this is padding
            if (string_relative_offset == 0xFFFF):
                continue
            string_offset = scene_text_list + string_relative_offset
            string_starts.add(hex(readHalfWord(string_offset)))
            if (readHalfWord(string_offset) & 0x3) == 1:
                continue
            #print(f'{index}: {hex(string_offset)} ({hex(scene_text_list)} + {hex(string_relative_offset)})')
            string_data = dump_string(string_offset)
            if string_data:
                file_path = f'{strings_path}/{language}/{index}.txt'
                with open(file_path, 'w', encoding="utf-8") as out:
                    out.write(string_data)
                string_done += 1

total = sum([count for byte, count in scene_opcode_frequency.items()])
print('Scene opcodes sorted by usage:')
scene_opcode_frequency = dict(sorted(scene_opcode_frequency.items(), key=lambda item:item[1], reverse=True))
for byte, count in scene_opcode_frequency.items():
    print(f'opcode {SCENE_OPCODES[byte].get_name()}: {round(count / total * 100, 2)}%')

total = sum([count for byte, count in conditionals_opcode_frequency.items()])
print('Conditionals opcodes sorted by usage:')
conditionals_opcode_frequency = dict(sorted(conditionals_opcode_frequency.items(), key=lambda item:item[1], reverse=True))
for byte, count in conditionals_opcode_frequency.items():
    print(f'opcode {CONDITIONALS_OPCODES[byte].get_name()}: {round(count / total * 100, 2)}%')


print('Scene opcodes sorted by usage (max 1 per script):')
scene_opcode_script_frequency = {byte: len(scripts) for byte, scripts in scene_opcode_script_frequency.items()}
scene_opcode_script_frequency = dict(sorted(scene_opcode_script_frequency.items(), key=lambda item:item[1], reverse=True))
for byte, count in scene_opcode_script_frequency.items():
    print(f'opcode {SCENE_OPCODES[byte].get_name()}: {count}')
print('Conditionals opcodes sorted by usage (max 1 per script):')
conditionals_opcode_script_frequency = {byte: len(scripts) for byte, scripts in conditionals_opcode_script_frequency.items()}
conditionals_opcode_script_frequency = dict(sorted(conditionals_opcode_script_frequency.items(), key=lambda item:item[1], reverse=True))
for byte, count in conditionals_opcode_script_frequency.items():
    print(f'opcode {CONDITIONALS_OPCODES[byte].get_name()}: {count}')

print(f'\nstrings extracted: {100*string_done/string_count}% ({string_done}/{string_count})')
