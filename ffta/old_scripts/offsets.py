from ffta_common import *

# print data for each event
# also take note of used scripts and scenes
"""
each event is composed of:
- a script id
- a scene id
- a text list id (which is the same as the script id, except when it is set to the special case 61)
- 1 byte of padding
"""
scripts = {}
for event_id in range(1, EVENT_COUNT): # event 0 is reserved
    event_offset = EVENT_LIST + event_id*4
    
    script_index = readByte(event_offset)
    scene_index = readByte(event_offset + 1)
    text_list_index = readByte(event_offset + 2)
    # the last byte goes unused
    
    if  text_list_index == 61: # text list 61 is hardcoded to display no dialogue
        print(f'Event {event_id}: Script {script_index}, Scene {scene_index}, No text')
    elif script_index != text_list_index:
        print(f'Event {event_id}: Script {script_index}, Scene {scene_index}, Text {text_list_index}')
    else:
        print(f'Event {event_id}: Script {script_index}, Scene {scene_index}')
    
    # if this is a new script, or a new scene for a known script, add it to the dict
    if script_index not in scripts.keys():
        scripts[script_index] = set()
    scripts[script_index].add(scene_index)

# print data for each found script
"""
script ids are used to access:
- for each conditional type, a pointer to conditionals
- for each language, a list of pointers to strings
- a list of pointers to scenes
"""
offsets = []
for script_index, scene_indexes in scripts.items():
    print()
    print(f'Script {script_index} Offsets:')
    print()
    
    # there are 8 types of conditionals that run at different points (at the start of a turn, at the end of a turn, etc)
    for conditional_type in range(8):
        # get list for this type of conditional
        conditionals_relative_offset = readHalfWord(CONDITIONAL_TYPE_LIST + conditional_type*2)
        conditionals_list = CONDITIONAL_TYPE_LIST + conditionals_relative_offset
        # and get the offset for this script's conditionals of that type
        conditionals_offset = conditionals_list + readHalfWord(conditionals_list + script_index*2)
        offsets.append(conditionals_offset)
        print(f'  Type {conditional_type} conditionals ({hex(conditionals_list)}): {hex(conditionals_offset)}  (from: {hex(conditionals_list + script_index*2)})')
    print()
    
    for language_id, language in enumerate(LANGUAGES):
        # get list for this language
        lang_text_list = LANG_TEXT_BANKS[language_id]
        # and get the offset for this script's text list for this language
        scene_text_list = lang_text_list + readWord(lang_text_list + script_index*4)
        offsets.append(scene_text_list)
        print(f'  {language} text list: {hex(scene_text_list)}')
    print()
    
    # get the offset of the scene list
    scene_list_relative_offset = readWord(SCENE_BANKS - 4 + script_index*4)
    scene_list = SCENE_BANKS + scene_list_relative_offset
    print(f'  Scene list: {hex(scene_list)}')
    # and the offset of each scene used
    for scene_index in scene_indexes:
        scene_relative_offset = readWord(scene_list + scene_index*4)
        scene_offset = scene_list + scene_relative_offset
        offsets.append(scene_offset)
        print(f'    Scene {str(scene_index).zfill(2)}: {hex(scene_offset)}')
    print()

offsets = sorted(offsets)
for offset in offsets:
    print(hex(offset))
