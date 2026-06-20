from dataclasses import dataclass
from typing import List

from ffta.ffta_common import *
from main import MainWindow

# these are scenes that were determined to be empty by first running empty_script_finder.py, then checking the data for the scenes manually
# keys are script indexes that have empty scenes, and the items are lists of scenes that are empty for that script
EXCLUDED_SCENES = {36: [0], 46: [1], 49: [1], 54: [0], 59: [0, 1]}

class dumping:
    @staticmethod
    def get_events(region: Region, source: bytes, main: MainWindow):
        main.set_message('Extracting events')

        events = {}
        event_list_offset : int = get_event_list_offset(region, source)

        for event_id in list(range(1, EVENT_COUNT)):
            main.set_progress(event_id, EVENT_COUNT)

            # event 0 is reserved
            if event_id == 0:
                continue

            event_offset : int = event_list_offset + event_id * 4

            script_id : int = readByte(event_offset, source)
            scene_id : int = readByte(event_offset + 1, source)
            strings_id : int = readByte(event_offset + 2, source)
            has_strings : bool = strings_id != 61 # in-game hardcoded value

            events[str(event_id)] = {
                'offset': event_offset,
                'script': str(script_id),
                'scene': str(scene_id),
                'has_strings': has_strings
            }
        return events

    @staticmethod
    # reads the ROM's binary data, starting from a given offset, and parses all branches of execution
    def _parse_raw_script(starting_offsets, label_offsets, empty_starts, operators, source):
        visited_labels = [False for _ in label_offsets]
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
                opcode_byte = readByte(offset, source)
                current_opcode = operators.get_opcode_by_byte(opcode_byte)
                if current_opcode is None:
                    print(f'Unexpected operator {hex(opcode_byte)} found at {hex(offset)}.')
                    current_opcode = operators.get_opcode_by_name('END')
                    script_data += 'END\n'
                else:
                    #script_data += f'/*{hex(offset)}*/'
                    script_data += f'{current_opcode.to_string(offset, source)}\n'
                # if it references a new label, add it to the list
                if current_opcode.is_branching():
                    branch_offset = current_opcode.get_branch_offset(offset, source)
                    if branch_offset not in label_offsets:
                        label_offsets.append(branch_offset)
                        visited_labels.append(False)
                offset = current_opcode.get_new_offset(offset)
                if current_opcode.is_terminator:
                    script_data += '\n'
                    break
        # handle the output for empty scripts
        # we need to print a label for each starting offset that is empty
        unique_starting_offsets = list(dict.fromkeys(starting_offsets))
        for offset in unique_starting_offsets:
            if starting_offsets.index(offset) in empty_starts:
                script_data += f'_{hex(offset)}:\n'
        return script_data.rstrip() + '\n'  # standardize final newline

    @staticmethod
    def _dump_script(starting_offsets, empty_starts, operators, source, steps=4):
        label_offsets = [offset for offset in starting_offsets]
        # first, gather the labels used
        if steps < 1:
            return ''
        script_data = dumping._parse_raw_script(starting_offsets, label_offsets, empty_starts, operators, source)
        # now, if needed, we can parse the script again with sorted label offsets
        if steps < 2:
            return script_data
        sorted_labels = sorted(label_offsets)
        if not label_offsets == sorted_labels:
            label_offsets = sorted_labels
            script_data = dumping._parse_raw_script(starting_offsets, label_offsets, empty_starts, operators, source)
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
            script_data = script_data.replace(f'_{hex(offset)}', f'${i}')
        return script_data

    @staticmethod
    def _dump_string_compact(offset, source):
        string = ''
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

    @staticmethod
    def _dump_string(offset, source):
        header = readHalfWord(offset, source)
        compression = header & 0x3
        offset += 2
        if compression == 1:
            return ''
        elif compression == 2:
            source = decompress_lzss(offset, source)
            offset = 0

        string = ''
        string_ended = False
        while not string_ended:
            byte = readByte(offset, source)
            offset += 1
            match byte:
                case 0:
                    string_ended = True
                case 1:
                    string += dumping._dump_string_compact(offset, source)
                    string_ended = True
                case 0x40:
                    control = readByte(offset, source)
                    offset += 1
                    match control:
                        case 0x6E:
                            string += '\n'
                        case 0x73:
                            string += ' '
                        case _:
                            if control in CONTROL_CODES.values():
                                control_name = list(CONTROL_CODES.keys())[list(CONTROL_CODES.values()).index(control)]
                                if control in LONG_CONTROL_CODES:
                                    string += f'[{control_name}, {readByte(offset, source)}]'
                                    offset += 1
                                else:
                                    string += f'[{control_name}]'
                            else:
                                string += f'[{hex(control)}]'
                    if control == 0x63:
                        string += '\n'
                case _:
                    character_index = ((byte << 8) | readByte(offset, source)) - 0x8000
                    if 0 <= character_index < len(CHARACTER_TABLE):
                        character = CHARACTER_TABLE[character_index]
                    else:
                        character = f'({hex(character_index)})'
                    string += character
                    offset += 1
        return string.rstrip('\n')

    @staticmethod
    def get_scripts(region: Region, source: bytes, main: MainWindow):
        main.set_message('Extracting scripts')

        used_scenes = get_used_scenes(region, source)
        scripts = {}

        # and dump the data
        for script_id in used_scenes:
            main.set_progress(script_id, len(used_scenes))
            # get the offset of the scene list
            scene_banks = get_scene_banks_offset(region, source)
            scene_list_relative_offset = readWord(scene_banks - 4 + script_id * 4, source)
            scene_list = scene_banks + scene_list_relative_offset
            # and the offset of each scene used
            scene_offsets = []
            scenes = {}
            for scene_id in used_scenes[script_id]:
                if script_id == 0:
                    continue
                scene_relative_offset = readWord(scene_list + scene_id * 4, source)
                scene_offset = scene_list + scene_relative_offset
                scene_offsets.append(scene_offset)
                scenes[str(scene_id)] = {'offset': scene_id, 'label': f'start_{scene_id}'}
            empty_scenes = EXCLUDED_SCENES.get(script_id, [])

            script_data = dumping._dump_script(scene_offsets, empty_scenes, SCRIPT_INSTRUCTION_SET, source)

            conditionals = {}
            conditional_type_list = get_conditional_type_list_offset(region, source)
            for conditional_type, conditional_type_name in enumerate(CONDITIONAL_TYPES):
                # conditionals of type 2 are only available for script 0, and script 0 only has type 2 conditionals
                if script_id == 0:
                    if conditional_type != 2:
                        continue
                elif conditional_type == 2:
                    continue
                # get list for this type of conditional
                conditionals_relative_offset = readHalfWord(conditional_type_list + conditional_type * 2, source)
                conditionals_list = conditional_type_list + conditionals_relative_offset
                # and get the offset for this script's conditionals of that type
                conditionals_offset = conditionals_list + readHalfWord(conditionals_list + script_id * 2, source)
                conditionals_data = dumping._dump_script([conditionals_offset], [], CONDITIONALS_INSTRUCTION_SET, source)
                conditionals[conditional_type_name] = {'offset': conditionals_offset, 'data': conditionals_data}

            string_offsets_list : List[List[int]] = []
            string_data_list : List[List[str]] = []
            languages = get_languages(region)
            for language_id, language in enumerate(languages):
                string_offsets_list.append([])
                string_data_list.append([])
                if script_id == 61:  # hardcoded to not display text
                    continue
                # get list for this language
                lang_text_list = get_lang_text_bank_offset(region, source, language_id)
                # and get the offset for this script's text list for this language
                scene_text_list = lang_text_list + readWord(lang_text_list + script_id * 4, source)
                list_end = scene_text_list + readHalfWord(scene_text_list, source)  # the offset of the first string marks the end of the table, padding included
                for string_id, offset in enumerate(range(scene_text_list, list_end, 2)):
                    string_offsets_list[language_id].append(0)
                    string_data_list[language_id].append('')

                    string_relative_offset = readHalfWord(offset, source)
                    # check if this is padding
                    if string_relative_offset == 0xFFFF:
                        continue
                    string_offset = scene_text_list + string_relative_offset
                    string_offsets_list[language_id][string_id] = string_offset
                    if (readHalfWord(string_offset, source) & 0x3) == 1:
                        continue
                    string_data = dumping._dump_string(string_offset, source)
                    string_data_list[language_id][string_id] = string_data

            strings = {}
            assert len(string_data_list) == len(languages)
            assert (len(l) == len(string_data_list[0]) for l in iter(string_data_list))
            for string_id in range(len(string_data_list[0])):
                offsets = [string_offsets_list[language_id][string_id] for language_id, language in enumerate(languages)]
                data = [string_data_list[language_id][string_id] for language_id, language in enumerate(languages)]
                strings[str(string_id)] = {'offsets': offsets, 'data': data}

            scripts[str(script_id)] = {
                'offset': scene_list,
                'scenes': scenes,
                'conditionals': conditionals,
                'strings': strings,
                'data': script_data
            }

        return scripts
