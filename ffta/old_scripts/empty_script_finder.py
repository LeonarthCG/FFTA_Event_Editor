from ffta_common import *

print('potentially empty scenes:')
used_scenes = get_used_scenes()
scene_lists = {}
for script_index in used_scenes.keys():
    scene_list_relative_offset = readWord(SCENE_BANKS - 4 + script_index*4)
    scene_list = SCENE_BANKS + scene_list_relative_offset
    scene_lists[script_index] = scene_list
for script_index, offset in scene_lists.items():
    if script_index == 62:
        continue
    scene_list_relative_offset = readWord(SCENE_BANKS - 4 + script_index*4)
    scene_list = SCENE_BANKS + scene_list_relative_offset
    for scene_index in used_scenes[script_index]:
        scene_relative_offset = readWord(scene_list + scene_index*4)
        scene_offset = scene_list + scene_relative_offset
        aligned_offset = scene_offset + 3
        aligned_offset &= ~3
        if aligned_offset == scene_lists[script_index + 1]:
            print(f'script {script_index}, scene {scene_index} ({hex(scene_offset)})')

conditionals_lists = []
for conditional_type in range(8):
    # get list for this type of conditional
    conditionals_relative_offset = readHalfWord(CONDITIONAL_TYPE_LIST + conditional_type*2)
    conditionals_list = CONDITIONAL_TYPE_LIST + conditionals_relative_offset
    conditionals_lists.append(conditionals_list)
conditionals_lists.append(0xD6ABC8) # end of the data for type 7 conditionals
for conditional_type in range(8):
    possible_unused = []
    safer = []
    for script_index in used_scenes.keys():
        # get list for this type of conditional
        conditionals_relative_offset = readHalfWord(CONDITIONAL_TYPE_LIST + conditional_type*2)
        conditionals_list = CONDITIONAL_TYPE_LIST + conditionals_relative_offset
        # and get the offset for this script's conditionals of that type
        conditionals_offset = conditionals_list + readHalfWord(conditionals_list + script_index*2)
        aligned_offset = conditionals_offset + 3
        aligned_offset &= ~3
        if aligned_offset >= conditionals_lists[conditional_type + 1]:
            possible_unused.append(conditionals_offset)
        else:
            safer.append(conditionals_offset)
    print(f'potentially empty type {conditional_type} conditionals:')
    possible_unused = list(dict.fromkeys(possible_unused))
    for offset in possible_unused:
        print(hex(offset))
    print(f'potentially used type {conditional_type} conditionals:')
    safer = list(dict.fromkeys(safer))
    for offset in safer:
        print(hex(offset))
