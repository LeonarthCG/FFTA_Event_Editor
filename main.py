# TODO: mission accepted conditionals do not extract?

import hashlib
import json
from enum import Enum
from typing import List, Optional

from antlr4 import *
from PyQt6 import QtCore, QtWidgets, uic, QtGui
import sys
import os
import webbrowser

import constants
import ffta
from constants import EUR_KNOWN_HASHES
from ffta import SCRIPT_INSTRUCTION_SET, CONDITIONALS_INSTRUCTION_SET, find_free_space, repoint_event_list, \
    writeByte, writeWord, writeBytes, repoint_scene_banks, repoint_lang_text_bank, writeShort, align, \
    repoint_conditional_type_list, CONDITIONAL_TYPES, get_languages, LANGUAGES, Region, readByte
from parse.ScriptCodeVisitor import ScriptCodeVisitor
from parse.ScriptLexer import ScriptLexer
from parse.ScriptParser import ScriptParser
from parse.ScriptSemanticVisitor import ScriptSemanticVisitor
from parse.StringCodeVisitor import StringCodeVisitor
from parse.StringLexer import StringLexer
from parse.StringParser import StringParser

script_semantic_visitor = ScriptSemanticVisitor(SCRIPT_INSTRUCTION_SET)
script_code_compiler = ScriptCodeVisitor(SCRIPT_INSTRUCTION_SET)

conditionals_semantic_visitor = ScriptSemanticVisitor(CONDITIONALS_INSTRUCTION_SET)
conditionals_code_compiler = ScriptCodeVisitor(CONDITIONALS_INSTRUCTION_SET)

string_code_compiler = StringCodeVisitor()

expand_policy : QtWidgets.QSizePolicy = QtWidgets.QSizePolicy(
    QtWidgets.QSizePolicy.Policy.Expanding,
    QtWidgets.QSizePolicy.Policy.Expanding)

app = None
main = None
project_path: Optional[str] = None # TODO: add version?

class ItemType(Enum):
    DUMMY = 0
    EVENT = 1
    SCRIPT = 2
    SCENE = 3
    STRING = 4
    CONDITIONALS = 5

class Rom:
    data: bytes
    path: str
    def __init__(self, data: bytes, path: str):
        self.data = data
        self.path = path

project_data: Optional[dict] = None


class TreeChild(QtWidgets.QTreeWidgetItem):
    _data_type : ItemType = ItemType.DUMMY
    _data_path : List[str] = []

    def __init__(self, label, data_type: ItemType = ItemType.DUMMY, data_path=None):
        super().__init__([label, ''])
        self.setCheckState(1, QtCore.Qt.CheckState.Unchecked)
        self.setFlags(self.flags() | QtCore.Qt.ItemFlag.ItemIsAutoTristate)
        self._data_type = data_type
        self._data_path = data_path
        self._label = label

    def get_type(self):
        return self._data_type

    def get_path(self):
        return self._data_path

    def get_data(self):
        if self._data_path is None:
            return None

        match self._data_type:
            case ItemType.EVENT:
                return project_data['events'][self._data_path[0]]
            case ItemType.SCRIPT:
                return project_data['scripts'][self._data_path[0]]
            case ItemType.SCENE:
                return project_data['scripts'][self._data_path[0]]['scenes'][self._data_path[1]]
            case ItemType.STRING:
                return project_data['scripts'][self._data_path[0]]['strings'][self._data_path[1]]
            case ItemType.CONDITIONALS:
                return project_data['scripts'][self._data_path[0]]['conditionals'][self._data_path[1]]
            case _:
                return None

    def update_data(self):
        if self._data_path is None:
            return

        match self._data_type:
            case ItemType.EVENT:
                project_data['events'][self._data_path[0]]['script'] = main.window.event_script_edit.currentText()
                project_data['events'][self._data_path[0]]['scene'] = main.window.event_scene_edit.currentText()
                project_data['events'][self._data_path[0]]['has_strings'] = main.window.event_has_strings_edit.isChecked()
            case ItemType.SCRIPT:
                project_data['scripts'][self._data_path[0]]['data'] = main.window.script_edit.toPlainText()
                assemble_script(self._data_path)
            case ItemType.SCENE:
                project_data['scripts'][self._data_path[0]]['scenes'][self._data_path[1]]['label'] = main.window.scene_edit.currentText()
            case ItemType.STRING:

                region: Region = Region(project_data['region'])
                languages = get_languages(region)
                if len(languages) > 0:
                    project_data['scripts'][self._data_path[0]]['strings'][self._data_path[1]]['data'][0] = main.window.english_edit.toPlainText()
                if len(languages) > 1:
                    project_data['scripts'][self._data_path[0]]['strings'][self._data_path[1]]['data'][1] = main.window.french_edit.toPlainText()
                if len(languages) > 2:
                    project_data['scripts'][self._data_path[0]]['strings'][self._data_path[1]]['data'][2] = main.window.german_edit.toPlainText()
                if len(languages) > 3:
                    project_data['scripts'][self._data_path[0]]['strings'][self._data_path[1]]['data'][3] = main.window.italian_edit.toPlainText()
                if len(languages) > 4:
                    project_data['scripts'][self._data_path[0]]['strings'][self._data_path[1]]['data'][4] = main.window.spanish_edit.toPlainText()
                assemble_string(self._data_path)
            case ItemType.CONDITIONALS:
                conditionals_data : str = main.window.conditionals_edit.toPlainText()
                project_data['scripts'][self._data_path[0]]['conditionals'][self._data_path[1]]['data'] = conditionals_data
                assemble_conditionals(self._data_path)

    def set_text_changed(self, changed: bool):
        self.setText(0, f'{self._label}{"*" if changed else ""}')


class Tree(QtWidgets.QTreeWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setColumnCount(1)
        self.header().swapSections(1,0)
        self.header().resizeSection(1, 80)


def show_error(title: str, message: str) -> None:
    _show_message(title, message, QtWidgets.QMessageBox.Icon.Critical)


def show_warning(title: str, message: str) -> None:
    _show_message(title, message, QtWidgets.QMessageBox.Icon.Warning)

def _show_message(title: str, message: str, icon: QtWidgets.QMessageBox.Icon) -> None:
    message_box = QtWidgets.QMessageBox()
    message_box.setIcon(QtWidgets.QMessageBox.Icon.Critical)
    message_box.setWindowTitle(title)
    message_box.setText(message)
    message_box.setStandardButtons(QtWidgets.QMessageBox.StandardButton(QtWidgets.QMessageBox.StandardButton.Ok))
    message_box.exec()


def ask_confirmation(title: str, message: str, is_warning: bool = False) -> bool:
    message_box = QtWidgets.QMessageBox()
    if is_warning:
        message_box.setIcon(QtWidgets.QMessageBox.Icon.Warning)
    else:
        message_box.setIcon(QtWidgets.QMessageBox.Icon.Question)
    message_box.setWindowTitle(title)
    message_box.setText(message)
    message_box.setStandardButtons(QtWidgets.QMessageBox.StandardButton(
        QtWidgets.QMessageBox.StandardButton.Cancel | QtWidgets.QMessageBox.StandardButton.Ok))
    return message_box.exec() == QtWidgets.QMessageBox.StandardButton.Ok # true if user pressed OK


def clean() -> None:
    if project_data is not None and 'scripts' in project_data:
        for script in project_data['scripts'].keys():
            if 'bin' in project_data['scripts'][script]:
                project_data['scripts'][script].pop('bin', None)
            if 'conditionals' in project_data['scripts'][script]:
                for conditionals in project_data['scripts'][script]['conditionals'].keys():
                    if 'bin' in project_data['scripts'][script]['conditionals'][conditionals]:
                        project_data['scripts'][script]['conditionals'][conditionals].pop('bin', None)
            if 'strings' in project_data['scripts'][script]:
                for string in project_data['scripts'][script]['strings'].keys():
                    if 'bin' in project_data['scripts'][script]['strings'][string]:
                        project_data['scripts'][script]['strings'][string].pop('bin', None)
    return

def assemble() -> bool:
    main.set_message('Assembling scripts')
    count = 0
    if project_data is not None and 'scripts' in project_data:
        count += len(project_data['scripts'].keys())
        for script in project_data['scripts'].keys():
            if 'conditionals' in project_data['scripts'][script]:
                count += len(project_data['scripts'][script]['conditionals'].keys())
            if 'strings' in project_data['scripts'][script]:
                count += len(project_data['scripts'][script]['strings'].keys())
    done = 0
    failed = 0
    if project_data is not None and 'scripts' in project_data:
        for script in project_data['scripts'].keys():
            main.set_progress(done, count)
            if script != '0':
                if 'bin' not in project_data['scripts'][script]:
                    if not assemble_script([script]):
                        failed += 1
                done += 1
            if 'conditionals' in project_data['scripts'][script]:
                for conditionals in project_data['scripts'][script]['conditionals'].keys():
                    if 'bin' not in project_data['scripts'][script]['conditionals'][conditionals]:
                        if not assemble_conditionals([script, conditionals]):
                            failed += 1
                    done += 1
            if 'strings' in project_data['scripts'][script]:
                for string in project_data['scripts'][script]['strings'].keys():
                    if 'bin' not in project_data['scripts'][script]['strings'][string]:
                        if not assemble_string([script, string]):
                            failed += 1
                    done += 1
    main.hide_progress()
    main.set_message('Assembling done')
    return failed == 0


def assemble_script(path: list[str]) -> bool:
    assert len(path) == 1
    assert 'scripts' in project_data
    assert path[0] in project_data['scripts']
    assert 'data' in project_data['scripts'][path[0]]

    script_data = project_data['scripts'][path[0]]['data']
    project_data['scripts'][path[0]].pop('bin', None)
    project_data['scripts'][path[0]].pop('labels', None)
    lexer = ScriptLexer(InputStream(script_data))
    stream = CommonTokenStream(lexer)
    parser = ScriptParser(stream)
    tree = parser.script()
    if parser.getNumberOfSyntaxErrors() > 0:
        # TODO: display syntax errors
        show_warning('Could not compile!', 'Syntax errors found.\nThe script could not be compiled.')
        return False
    script_semantic_visitor.visit(tree)
    error_string: str
    if len(script_semantic_visitor.errors) == 1:
        error_string = 'An error was found:'
    else:
        error_string = f'{len(script_semantic_visitor.errors)} errors were found:'
    for error in script_semantic_visitor.errors:
        error_string += f'\n {error}'
    if len(script_semantic_visitor.errors) > 0:
        show_warning('Could not compile!', error_string)
        return False
    script_code_compiler.visit(tree)
    bin_data = script_code_compiler.code
    project_data['scripts'][path[0]]['bin'] = bin_data
    project_data['scripts'][path[0]]['labels'] = script_code_compiler.labels
    return True


def assemble_conditionals(path: list[str]) -> bool:
    assert len(path) == 2
    assert 'scripts' in project_data
    assert path[0] in project_data['scripts']
    assert 'conditionals' in project_data['scripts'][path[0]]
    assert path[1] in project_data['scripts'][path[0]]['conditionals']
    assert 'data' in project_data['scripts'][path[0]]['conditionals'][path[1]]

    conditionals_data = project_data['scripts'][path[0]]['conditionals'][path[1]]['data']
    project_data['scripts'][path[0]]['conditionals'][path[1]].pop('bin', None)

    lexer = ScriptLexer(InputStream(conditionals_data))
    stream = CommonTokenStream(lexer)
    parser = ScriptParser(stream)
    tree = parser.script()
    if parser.getNumberOfSyntaxErrors() > 0:
        # TODO: display syntax errors
        show_warning('Could not compile!', 'Syntax errors found.\nThe script could not be compiled.')
        return False
    conditionals_semantic_visitor.visit(tree)
    error_string: str
    if len(conditionals_semantic_visitor.errors) == 1:
        error_string = 'An error was found:'
    else:
        error_string = f'{len(conditionals_semantic_visitor.errors)} errors were found:'
    for error in conditionals_semantic_visitor.errors:
        error_string += f'\n {error}'
    if len(conditionals_semantic_visitor.errors) > 0:
        show_warning('Could not compile!', error_string)
        return False
    conditionals_code_compiler.visit(tree)
    bin_data = conditionals_code_compiler.code
    project_data['scripts'][path[0]]['conditionals'][path[1]]['bin'] = bin_data
    return True


def assemble_string(path: list[str]) -> bool:
    region: Region = Region(project_data['region'])
    languages = get_languages(region)

    assert len(path) == 2
    assert 'scripts' in project_data
    assert path[0] in project_data['scripts']
    assert 'strings' in project_data['scripts'][path[0]]
    assert path[1] in project_data['scripts'][path[0]]['strings']
    assert 'data' in project_data['scripts'][path[0]]['strings'][path[1]]
    assert 'data' in project_data['scripts'][path[0]]['strings'][path[1]]
    assert len(project_data['scripts'][path[0]]['strings'][path[1]]['data']) == len(languages)

    string_data = project_data['scripts'][path[0]]['strings'][path[1]]['data']
    project_data['scripts'][path[0]]['strings'][path[1]].pop('bin', None)

    bin_data = []
    for lang in range(len(languages)):
        lexer = StringLexer(InputStream(string_data[lang]))
        stream = CommonTokenStream(lexer)
        parser = StringParser(stream)
        tree = parser.string()
        if parser.getNumberOfSyntaxErrors() > 0:
            # TODO: display syntax errors
            show_warning('Could not build string!',
                         f'Syntax errors found.\nThe {languages[lang]} string could not be built.')
            continue
        string_code_compiler.visit(tree)
        error_string: str
        if len(string_code_compiler.errors) == 1:
            error_string = f'An error was found for the {languages[lang]} string:'
        else:
            error_string = f'{len(string_code_compiler.errors)} errors were found for the {languages[lang]} string:'
        for error in string_code_compiler.errors:
            error_string += f'\n {error}'
        if len(string_code_compiler.errors) > 0:
            show_warning('Could not build!', error_string)
            continue
        bin_data.append(string_code_compiler.code)
    if len(bin_data) != len(languages):
        return False

    project_data['scripts'][path[0]]['strings'][path[1]]['bin'] = bin_data
    return True


def build_as() -> None:
    try:
        project_data['rom_path'] = ''
    except Exception:
        pass
    try:
        project_data['out_path'] = ''
    except Exception:
        pass
    build()


def build() -> None:
    if project_data is None:
        main.set_message('No project is loaded')
        return
    if not assemble():
        main.set_message('Could not assemble scripts')
        return
    rom = open_rom([project_data['hash']])
    if rom is None:
        main.set_message('ROM could not be loaded')
        return
    project_data['rom_path'] = rom.path
    rom_out = list(rom.data)
    region: Region = Region(project_data['region'])

    # script 61 must keep being number 61, so script order has to be kept somehow
    # also need to keep event order consistent
    main.set_message('Building ROM')
    offset = find_free_space(rom_out)
    scripts : list[str] = list(project_data['scripts'].keys())
    scenes : list[list[str]] = [list(script['scenes'].keys()) for script in project_data['scripts'].values()]

    # events
    offset = align(4, offset, rom_out)
    event_list = offset
    repoint_event_list(region, event_list, rom_out)
    main.set_message('Building events')
    offset = writeWord(0, offset, rom_out) # reserved event 0 entry
    i = 0
    for event in project_data['events'].keys():
        main.set_progress(i, len(project_data['events'].keys()))
        i += 1
        script = scripts.index(project_data['events'][event]['script'])
        scene = scenes[script].index(project_data['events'][event]['scene'])
        text = script if project_data['events'][event]['has_strings'] else 61
        offset = writeByte(script, offset, rom_out)
        offset = writeByte(scene, offset, rom_out)
        offset = writeByte(text, offset, rom_out)
        offset = writeByte(0, offset, rom_out)

    # scripts
    main.set_message('Building script bodies')
    offset = align(4, offset, rom_out)
    scene_banks = offset
    repoint_scene_banks(region, scene_banks, rom_out)
    offset += 4*len(project_data['scripts'].keys()) # reserve space for the table, script 0 has no entry
    for i, script in enumerate(project_data['scripts'].keys()):
        if i == 0:
            continue
        main.set_progress(i, len(project_data['scripts'].keys()))
        # add the scene bank to the table
        offset = align(4, offset, rom_out)
        scene_bank = offset
        writeWord(scene_bank - scene_banks, scene_banks + 4*(i-1), rom_out) # -1, because 0 does not have an entry
        # write each scene entry to this scene bank
        scene_bank_length = 4*len(project_data['scripts'][script]['scenes'].keys())
        for scene in project_data['scripts'][script]['scenes']:
            label = project_data['scripts'][script]['scenes'][scene]['label']
            label_offset = project_data['scripts'][script]['labels'][label]
            offset = writeWord(scene_bank_length + label_offset, offset, rom_out)
        # and write the script data
        bin_data = project_data['scripts'][script]['bin']
        offset = writeBytes(bin_data, offset, rom_out)

    # conditionals
    offset = align(2, offset, rom_out)
    conditionals_type_list = offset
    offset += 2*len(CONDITIONAL_TYPES) # space for each conditional list entry
    repoint_conditional_type_list(region, conditionals_type_list, rom_out)
    for cond_type, cond_type_name in enumerate(CONDITIONAL_TYPES):
        main.set_message(f'Building type {cond_type} conditionals')
        offset = align(2, offset, rom_out)
        conditionals_list = offset
        writeShort(conditionals_list - conditionals_type_list, conditionals_type_list + 2*cond_type, rom_out)
        if cond_type == 2:
            offset += 2
            writeShort(offset - conditionals_list, conditionals_list, rom_out)
            bin_data = project_data['scripts']['0']['conditionals'][cond_type_name]['bin']
            offset = writeBytes(bin_data, offset, rom_out)
        else:
            offset = writeShort(0, offset, rom_out) # reserved script 0 entry
            offset += 2*len(project_data['scripts'].keys()) # one entry for each script
            for i, script in enumerate(project_data['scripts'].keys()):
                writeShort(offset - conditionals_list, conditionals_list + 2*i, rom_out)
                if cond_type_name in project_data['scripts'][script]['conditionals']:
                    bin_data = project_data['scripts'][script]['conditionals'][cond_type_name]['bin']
                    offset = writeBytes(bin_data, offset, rom_out)

    # strings
    languages = get_languages(region)
    for language_id in range(len(languages)):
        main.set_message(f'Building {languages[language_id]} strings')
        offset = align(4, offset, rom_out)
        language_bank = offset
        repoint_lang_text_bank(region, language_bank, rom_out, language_id)
        offset += 4*len(project_data['scripts'].keys()) # reserve space for the table
        for i, script in enumerate(project_data['scripts'].keys()):
            main.set_progress(i, len(project_data['scripts'].keys()))
            offset = align(4, offset, rom_out)
            string_bank = offset
            writeWord(string_bank - language_bank, language_bank + i*4, rom_out)
            offset += 4*len(project_data['scripts'][script]['strings'].keys()) # reserve space for each string in this bank
            for j, string in enumerate(project_data['scripts'][script]['strings'].keys()):
                # TODO: need string type? (X: type of text bubble)
                writeShort(offset - string_bank, string_bank + j*2, rom_out)
                offset = writeShort(0, offset, rom_out) # string header
                bin_data = project_data['scripts'][script]['strings'][string]['bin'][language_id]
                offset = writeBytes(bin_data, offset, rom_out)

    main.hide_progress()
    main.set_message('Saving ROM')
    try:
        # try to save to previous output location
        with open(project_data['out_path'], 'wb+') as f:
            f.write(bytes(rom_out))
    except Exception as e:
        # prompt the user to select a .gba file
        rom_path = QtWidgets.QFileDialog.getSaveFileName(None, 'Save FFTA ROM', '', filter='GBA ROM Files (*.gba)')
        if rom_path and rom_path[0]:
            rom_path = rom_path[0]
        else:
            main.set_message('Could not save ROM')
            return
        try:
            with open(rom_path, 'wb+') as f:
                f.write(bytes(rom_out))
            project_data['out_path'] = rom_path
        except Exception as e:
            main.set_message('Could not save ROM')
            print(e)
            return
    main.set_message('Done')


def close_project():
    if main.project_has_changed or main.events_have_changed or main.scripts_have_changed:
        if ask_confirmation("There are unsaved changes!", "The project has unsaved changes.\nWould you like to save them?", is_warning=True):
            save_project()
    global project_path, project_data
    project_path = None
    project_data = None
    if main.script_tree is not None:
        main.script_tree.clear()
    if main.event_tree is not None:
        main.event_tree.clear()
    main.set_visible_area(None)
    main.events_have_changed = False
    main.scripts_have_changed = False
    main.previous_event = None
    main.previous_script = None
    main.window.tabs.setTabText(0, 'Scripts')
    main.window.tabs.setTabText(1, 'Events')


def open_rom(hashes=None) -> Optional[Rom]:
    if hashes is None:
        hashes = constants.KNOWN_HASHES
    rom_data = None

    try:
        # try to get previously used rom
        rom_path = project_data['rom_path']
        with open(rom_path, 'rb') as f:
            rom_data = f.read()
            sha256 = hashlib.sha256(rom_data).hexdigest().upper()
            if sha256 != project_data['hash']:
                raise Exception('Unexpected ROM hash')
    except Exception:
        # prompt the user to select a .gba file
        rom_path = QtWidgets.QFileDialog.getOpenFileName(None, 'Open FFTA ROM', '', filter='GBA ROM Files (*.gba)')
        if rom_path and rom_path[0]:
            rom_path = rom_path[0]
        else:
            return None

    # check that it is a known ROM, otherwise warn the user
    try:
        main.set_message('Checking ROM')
        with open(rom_path, 'rb') as f:
            rom_data = f.read()
            sha256 = hashlib.sha256(rom_data).hexdigest().upper()
            # if unknown ROM, asks for confirmation before proceeding
            if not sha256 in hashes:
                result = ask_confirmation(
                    'Unknown ROM!',
                    'The selected ROM does not match any expected hashes.\n'
                    '\n'
                    'If the ROM is incompatible, opening it might result in unexpected behaviour.\n'
                    'Do you wish to proceed anyway?',
                    is_warning=True
                )
                if not result:
                    return None
            main.set_message('ROM accepted')
    except Exception as e:
        print(e)
        main.set_message('Aborted')
    if rom_data is None:
        return None
    else:
        return Rom(rom_data, rom_path)


def load_from_rom(rom: Rom):
    try:
        main.set_message('Reading from ROM')

        sha256 = hashlib.sha256(rom.data).hexdigest().upper()
        # TODO: determine region through header if no hash matches, and ask the user if header is unexpected
        region = Region.EUR if sha256 in EUR_KNOWN_HASHES else Region.USA
        events = ffta.dumping.get_events(region, rom.data, main)
        scripts = ffta.dumping.get_scripts(region, rom.data, main)
        global project_data
        project_data = {'events': events, 'scripts': scripts, 'hash': sha256, 'region': region.value, 'rom_path': rom.path, 'out_path': ''}
        main.update_events()
        main.update_scripts()

        main.set_message('Ready')
    except Exception as e:
        print(e)
        main.set_message('Aborted')


def new_project():
    close_project()
    rom = open_rom()
    if Rom is not None:
        load_from_rom(rom)
    main.hide_progress()


def open_project():
    close_project()
    # prompt the user to select a .ffta file
    loaded_project_path = QtWidgets.QFileDialog.getOpenFileName(None, 'Open a FFTA project', '', filter='FFTA project files (*.ffta)')
    if loaded_project_path and loaded_project_path[0]:
        loaded_project_path = loaded_project_path[0]
    else:
        return

    # check that it is a valid FFTA project
    errors = []
    try:
        main.set_message("Opening project")
        with open(loaded_project_path, 'r') as f:
            loaded_project_data = json.load(f)
            main.set_message('Project opened')
            main.set_message('Checking events')
            if 'events' in loaded_project_data.keys():
                if isinstance(loaded_project_data['events'], dict):
                    i = 1
                    for event_id, event in loaded_project_data['events'].items():
                        main.set_message(f"Checking events: {i}/{len(loaded_project_data['events'].items())}")
                        if not 'offset' in event.keys():
                            errors.append(f"Event '{event_id}' is missing the 'offset' field.")
                        if not 'script' in event.keys():
                            errors.append(f"Event '{event_id}' is missing the 'script' field.")
                        if not 'scene' in event.keys():
                            errors.append(f"Event '{event_id}' is missing the 'scene' field.")
                        if not 'has_strings' in event.keys():
                            errors.append(f"Event '{event_id}' is missing the 'has_strings' field.")
                        i += 1
                else:
                    errors.append("The project file's 'events' field must contain a dictionary.")
            else:
                errors.append("The project file is missing the 'events' field.")
            main.set_message('Checking scripts')
            if 'scripts' in loaded_project_data.keys():
                if isinstance(loaded_project_data['scripts'], dict):
                    i = 1
                    for script_id, script in loaded_project_data['scripts'].items():
                        main.set_message(f"Checking scripts: {i}/{len(loaded_project_data['scripts'].items())}")
                        if isinstance(script, dict):
                            if 'scenes' in script.keys():
                                for scene_id, scene in script['scenes'].items():
                                    if isinstance(scene, dict):
                                        if not 'offset' in scene:
                                            errors.append(f"Scene '{scene_id}' in Script '{script_id}' is missing the 'offset' field.")
                                        if not 'label' in scene:
                                            errors.append(f"Scene '{scene_id}' in Script '{script_id}' is missing the 'label' field.")
                                    else:
                                        errors.append(f"Scene '{scene_id}' in Script '{script_id}' must contain a dictionary.")
                            else:
                                errors.append("The project's 'scripts' dictionary is missing the 'scenes' field.")
                            # TODO: check for errors in strings
                            """
                            if 'strings' in script.keys():
                                for string_id, string in script['strings'].items():
                                    if isinstance(string, dict):
                            else:
                                errors.append("The project's 'scripts' dictionary is missing the 'strings' field.")
                            """
                            # TODO: check for errors in conditionals
                            """
                            if 'conditionals' in script.keys():
                                for conditionals_type, conditionals in script['conditionals'].items():
                                    if isinstance(conditionals, dict):
                            else:
                                errors.append("The project's 'scripts' dictionary is missing the 'conditionals' field.")
                            """
                        else:
                            errors.append(f"Script '{script_id}' must contain a dictionary.")
                        i += 1
                else:
                    errors.append("The project file's 'scripts' field must contain a dictionary.")
            else:
                errors.append("The project file is missing the 'scripts' field.")

            if len(errors) == 0:
                global project_path, project_data
                project_path = loaded_project_path
                project_data = loaded_project_data
                main.update_events()
                main.update_scripts()
                main.set_message('Ready')
            else:
                raise AssertionError()
    except AssertionError as e:
        message = 'Errors occurred while opening the project file:'
        errors_added = 0
        for error in errors:
            message += f'\n{error}'
            errors_added += 1
            if errors_added > 4:
                message += f'\n\n({len(errors) - errors_added} errors omitted for brevity)'
        show_error('Invalid project file!', message)
        main.set_message('Aborted')
    except Exception as e:
        print(e)
        main.set_message('Aborted')
    main.hide_progress()

def save_project():
    if main.events_have_changed:
        main.events_have_changed = False
        if main.previous_event is not None:
            main.previous_event.update_data()
            main.previous_event.set_text_changed(False)
        if main.event_tree.currentItem() is not None:
            main.event_tree.currentItem()
            main.event_tree.currentItem().set_text_changed(False)
        main.window.tabs.setTabText(1, 'Events')

    if main.scripts_have_changed:
        main.scripts_have_changed = False
        if main.previous_script is not None:
            main.previous_script.update_data()
            main.previous_script.set_text_changed(False)
        if main.script_tree.currentItem() is not None:
            main.script_tree.currentItem()
            main.script_tree.currentItem().set_text_changed(False)
        main.window.tabs.setTabText(0, 'Scripts')

        region: Region = Region(project_data['region'])
        languages = get_languages(region)
        for i, lang in enumerate(LANGUAGES):
            main.window.language_tabs.setTabEnabled(i, lang in languages)
            main.window.language_tabs.setTabText(i, lang)


    # if there is no destination, ask the user for the destination
    if project_path is None:
        save_project_as()
    # save to the current loaded project's destination
    try:
        with open(project_path, 'w', encoding="utf-8") as f:
            f.write(json.dumps(project_data, indent=1, separators=(',', ':')))
    except Exception as e:
        print(e)


def save_project_as():
    # ask the user for the destination
    try:
        new_project_path = QtWidgets.QFileDialog.getSaveFileName(None, 'Select a destination', '', filter='FFTA project files (*.ffta)')
        if new_project_path and new_project_path[0]:
            # set the new destination as the project destination and save as normal
            global project_path
            project_path = new_project_path[0]
            save_project()
    except Exception as e:
        print(e)


def app_exit():
    close_project()
    main.window.close()


def open_manual():
    path = os.path.join(os.path.curdir, 'manual/index.html')
    webbrowser.open(rf'{path}')


def script_changed() -> None:
    if main.scripts_have_changed:
        return
    main.scripts_have_changed = main.window.script_tree.currentItem().get_data()['data'] != main.window.script_edit.toPlainText()
    if main.scripts_have_changed:
        main.window.tabs.setTabText(0, 'Scripts*')
        main.script_tree.currentItem().set_text_changed(True)


def scene_changed() -> None:
    if main.scripts_have_changed:
        return
    main.scripts_have_changed = main.window.script_tree.currentItem().get_data()['label'] != main.window.scene_edit.currentText()
    if main.scripts_have_changed:
        main.window.tabs.setTabText(0, 'Scripts*')
        main.script_tree.currentItem().set_text_changed(True)


def string_changed() -> None:
    string_field_pairs = zip(
        main.window.script_tree.currentItem().get_data()['data'],
        [main.window.english_edit, main.window.french_edit, main.window.german_edit, main.window.italian_edit, main.window.spanish_edit]
    )
    i = 0
    for string, textfield in string_field_pairs:
        language_changed = string != textfield.toPlainText()
        main.scripts_have_changed |= language_changed
        if language_changed:
            if not main.window.language_tabs.tabText(i).endswith('*'):
                main.window.language_tabs.setTabText(i, main.window.language_tabs.tabText(i)+'*')
        i += 1
    if main.scripts_have_changed:
        main.window.tabs.setTabText(0, 'Scripts*')
        main.script_tree.currentItem().set_text_changed(True)


def conditionals_changed() -> None:
    if main.scripts_have_changed:
        return
    main.scripts_have_changed = main.window.script_tree.currentItem().get_data()['data'] != main.window.conditionals_edit.toPlainText()
    if main.scripts_have_changed:
        main.window.tabs.setTabText(0, 'Scripts*')
        main.script_tree.currentItem().set_text_changed(True)


def event_script_changed() -> None:
    script_name = main.window.event_script_edit.currentText()
    if script_name != '0' and script_name in project_data['scripts'].keys():
        scene_names = list(project_data['scripts'][script_name]['scenes'].keys())
        main.window.event_scene_edit.clear()
        main.window.event_scene_edit.addItems(scene_names)
        main.window.event_scene_edit.setEditText(scene_names[0])
    event_changed()


def event_changed() -> None:
    if main.events_have_changed:
        return

    script_name = main.window.event_script_edit.currentText()
    scene_name = main.window.event_scene_edit.currentText()

    main.events_have_changed = main.window.event_tree.currentItem().get_data()['script'] != script_name
    main.events_have_changed |= main.window.event_tree.currentItem().get_data()['scene'] != scene_name
    main.events_have_changed |= main.window.event_tree.currentItem().get_data()['has_strings'] != main.window.event_has_strings_edit.isChecked()

    if main.events_have_changed:
        main.window.tabs.setTabText(1, 'Events*')
        main.event_tree.currentItem().set_text_changed(True)


class MainWindow(QtWidgets.QMainWindow):
    event_tree = None
    script_tree = None
    event_data = None
    project_has_changed = False
    scripts_have_changed = False
    events_have_changed = False
    previous_script = None
    previous_event = None

    def set_message(self, message: str) -> None:
        self.window.status.setText(message)
        self.window.status.repaint()
        app.processEvents()

    def hide_progress(self) -> None:
        self.set_progress(0, 0)

    def set_progress(self, progress: int, max_progress: int) -> None:
        if max_progress > 0:
            if progress < 0:
                progress = 0
            if progress >= max_progress:
                progress = max_progress
            self.window.progress.setValue(progress)
            self.window.progress.setMaximum(max_progress)
            self.window.progress.setVisible(True)
        else:
            self.window.progress.setValue(0)
            self.window.progress.setMaximum(0)
            self.window.progress.setVisible(False)
        app.processEvents()

    def set_visible_area(self, target):
        self.set_event_visible_area(target)
        self.set_script_visible_area(target)

    def set_event_visible_area(self, target) -> None:
        for element in [self.window.event_frame]:
            element.setVisible(element == target)

    def set_script_visible_area(self, target) -> None:
        for element in [self.window.script_frame, self.window.scene_frame, self.window.string_frame, self.window.conditionals_frame]:
            element.setVisible(element == target)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        app_exit()

    def attach_actions(self) -> None:
        self.window.action_new_project.triggered.connect(new_project)
        self.window.action_load_project.triggered.connect(open_project)
        self.window.action_close_project.triggered.connect(close_project)
        self.window.action_manual.triggered.connect(open_manual)
        self.window.action_save_project.triggered.connect(save_project)
        self.window.action_save_project_as.triggered.connect(save_project_as)
        self.window.action_exit.triggered.connect(app_exit)

        self.window.action_clean.triggered.connect(clean)
        self.window.action_assemble.triggered.connect(assemble)
        self.window.action_build.triggered.connect(build)
        self.window.action_build_as.triggered.connect(build_as)

        self.window.script_edit.textChanged.connect(script_changed)
        self.window.scene_edit.editTextChanged.connect(scene_changed)
        self.window.english_edit.textChanged.connect(string_changed)
        self.window.french_edit.textChanged.connect(string_changed)
        self.window.german_edit.textChanged.connect(string_changed)
        self.window.italian_edit.textChanged.connect(string_changed)
        self.window.spanish_edit.textChanged.connect(string_changed)
        self.window.conditionals_edit.textChanged.connect(conditionals_changed)

        self.window.event_script_edit.editTextChanged.connect(event_script_changed)
        self.window.event_scene_edit.editTextChanged.connect(event_changed)
        self.window.event_has_strings_edit.toggled.connect(event_changed)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.window = uic.loadUi('./ui/main_window.ui', self)
        self.window.setWindowTitle('FFTA Event Editor')
        self.set_visible_area(None)
        self.window.progress.setVisible(False)
        self.attach_actions()

        self.window.show()

    def update_events(self) -> None:
        # first time setup
        if not self.event_tree:
            self.event_tree = Tree()
            self.event_tree.setExpandsOnDoubleClick(False)
            self.event_tree.itemActivated.connect(self.change_event_data)
            self.event_tree.verticalScrollBar().setVisible(True)
            self.event_tree.header().setVisible(False)
            self.event_tree.setParent(self.window.event_tree_frame)
            self.window.event_tree_frame.layout().addWidget(self.event_tree)
        else:
            self.event_tree.clear()

        children = [TreeChild(f'Event {event}', ItemType.EVENT, [event]) for event in project_data['events'].keys()]
        self.event_tree.insertTopLevelItems(0, children)

    def update_scripts(self) -> None:
        # first time setup
        if not self.script_tree:
            self.script_tree = Tree()
            self.script_tree.setExpandsOnDoubleClick(False)
            self.script_tree.itemActivated.connect(self.change_script_data)
            self.script_tree.verticalScrollBar().setVisible(True)
            self.script_tree.header().setVisible(False)
            self.script_tree.setParent(self.window.script_tree_frame)
            self.window.script_tree_frame.layout().addWidget(self.script_tree)
        else:
            self.script_tree.clear()

        children = []
        for script in project_data['scripts'].keys():
            script_child = TreeChild(f'Script {script}', ItemType.DUMMY, [])

            if script != '0':
                script_body = TreeChild('Body', ItemType.SCRIPT, [script])
                script_child.addChild(script_body)

            if script != '0':
                scenes_category = TreeChild(f'Scenes')
                for scene in project_data['scripts'][script]['scenes'].keys():
                    scene_child = TreeChild(f'Scene {scene}', ItemType.SCENE, [script, scene])
                    scenes_category.addChild(scene_child)
                script_child.addChild(scenes_category)

            strings_category = TreeChild(f'Strings')
            for string in project_data['scripts'][script]['strings'].keys():
                string_child = TreeChild(f'String {string}', ItemType.STRING, [script, string])
                strings_category.addChild(string_child)
            script_child.addChild(strings_category)

            conditionals_category = TreeChild(f'Conditionals')
            for conditionals in project_data['scripts'][script]['conditionals'].keys():
                conditionals_child = TreeChild(conditionals, ItemType.CONDITIONALS, [script, conditionals])
                conditionals_category.addChild(conditionals_child)
            script_child.addChild(conditionals_category)

            children.append(script_child)
        self.script_tree.insertTopLevelItems(0, children)

    def change_event_data(self):
        if self.previous_event is not None and main.events_have_changed:
            wants_to_save = ask_confirmation('There are unsaved changes!',
                                             'The item previously being edited has uncommited changes.\n'
                                             'Would you like to save the changes?')
            if wants_to_save:
                save_project()

        item_type = self.event_tree.currentItem().get_type()
        item_data = self.event_tree.currentItem().get_data()

        if item_type == ItemType.EVENT:
            script_name = str(item_data['script'])
            scene_name = str(item_data['scene'])
            self.window.event_script_edit.clear()
            script_names = list(project_data['scripts'].keys())[1:]
            self.window.event_script_edit.addItems(script_names)
            self.window.event_script_edit.setEditText(script_name)
            self.window.event_scene_edit.setEditText(scene_name)
            self.window.event_has_strings_edit.setChecked(item_data['has_strings'])
            self.set_event_visible_area(self.window.event_frame)
        self.events_have_changed = False
        self.event_tree.currentItem().set_text_changed(False)
        self.window.tabs.setTabText(1, 'Events')
        if self.previous_event is not None:
            self.previous_event.set_text_changed(False)
        self.previous_event = self.event_tree.currentItem()

    def change_script_data(self):
        if self.previous_script is not None and main.scripts_have_changed:
            wants_to_save = ask_confirmation('There are unsaved changes!',
                                             'The item previously being edited has uncommited changes.\n'
                                             'Would you like to save the changes?')
            if wants_to_save:
                save_project()

        item_type = self.script_tree.currentItem().get_type()
        item_data = self.script_tree.currentItem().get_data()
        if item_type == ItemType.SCRIPT:
            self.window.script_edit.setText(item_data['data'])
            self.set_script_visible_area(self.window.script_frame)
        elif item_type == ItemType.SCENE:
            self.window.scene_edit.clear()
            path = self.script_tree.currentItem().get_path()
            if 'labels' in project_data['scripts'][path[0]].keys():
                labels = list(project_data['scripts'][path[0]]['labels'].keys())
                self.window.scene_edit.addItems(labels)
            self.window.scene_edit.setEditText(item_data['label'])
            self.set_script_visible_area(self.window.scene_frame)
        elif item_type == ItemType.STRING:
            region: Region = Region(project_data['region'])
            languages = get_languages(region)
            if len(languages) > 0:
                self.window.english_edit.setText(item_data['data'][0])
            if len(languages) > 1:
                self.window.french_edit.setText(item_data['data'][1])
            if len(languages) > 2:
                self.window.german_edit.setText(item_data['data'][2])
            if len(languages) > 3:
                self.window.italian_edit.setText(item_data['data'][3])
            if len(languages) > 4:
                self.window.spanish_edit.setText(item_data['data'][4])
            for i, lang in enumerate(LANGUAGES):
                main.window.language_tabs.setTabEnabled(i, lang in languages)
                main.window.language_tabs.setTabText(i, lang)
            self.set_script_visible_area(self.window.string_frame)
        elif item_type == ItemType.CONDITIONALS:
            self.window.conditionals_edit.setText(item_data['data'])
            self.set_script_visible_area(self.window.conditionals_frame)
        self.scripts_have_changed = False
        self.script_tree.currentItem().set_text_changed(False)
        self.window.tabs.setTabText(0, 'Scripts')
        if self.previous_script is not None:
            self.previous_script.set_text_changed(False)
        self.previous_script = self.script_tree.currentItem()

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    main = MainWindow()
    main.show()
    sys.exit(app.exec())
