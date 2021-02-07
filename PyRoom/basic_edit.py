# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# PyRoom - A clone of WriteRoom
# Copyright (c) 2007 Nicolas P. Rougier & NoWhereMan
# Copyright (c) 2008 The Pyroom Team - See AUTHORS file for more information
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program.  If not, see <http://www.gnu.org/licenses/>.
# -----------------------------------------------------------------------------

"""
provide basic editor functionality

contains basic functions needed for pyroom - any core functionality is included
within this file
"""

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk
from gi.repository import GObject
import os
import urllib.parse

from .pyroom_error import PyroomError
from .gui import GUI
from .preferences import Preferences
from . import autosave
from .globals import state, config

FILE_UNNAMED = _('* Unnamed *')

KEY_BINDINGS = '\n'.join([
_('Control-H: Show help in a new buffer'),
_('Control-I: Show buffer information'),
_('Control-P: Shows Preferences dialog'),
_('Control-M: Minimize PyRoom'),
_('Control-N: Create a new buffer'),
_('Control-O: Open a file in a new buffer'),
_('Control-Q: Quit'),
_('Control-S: Save current buffer'),
_('Control-Shift-S: Save current buffer as'),
_('Control-W: Close buffer and exit if it was the last buffer'),
_('Control-Y: Redo last typing'),
_('Control-Z: Undo last typing'),
_('Control-Page Up: Switch to previous buffer'),
_('Control-Page Down: Switch to next buffer'), ])

HELP = \
    _("""PyRoom - distraction free writing
Copyright (c) 2007 Nicolas Rougier, NoWhereMan
Copyright (c) 2008 Bruno Bord and the PyRoom team

Welcome to PyRoom and distraction-free writing.

To hide this help window, press Control-W.

PyRoom stays out of your way with formatting options and buttons,
it is largely keyboard controlled, via shortcuts. You can find a list
of available keyboard shortcuts later.

If enabled in preferences, pyroom will save your files automatically every
few minutes or when you press the keyboard shortcut.

Commands:
---------
%s

""") % KEY_BINDINGS


def get_likely_chooser_path(buffers, current):
    """determine where the user might want to start browsing open/save dialogs

    takes other buffer filenames into account, returns the closest one"""
    if len(buffers) > 0:
        # search in both directions for named buffers, backwards first
        directions = (
            (range(current, 0, -1)),
            (range(current, len(buffers), 1))
        )
        for direction in directions:
            for buf_num in direction:
                if buffers[buf_num].filename != FILE_UNNAMED:
                    return os.path.dirname(
                        os.path.abspath(
                            buffers[buf_num].filename
                        )
                    )

def dispatch(*args, **kwargs):
    """call the method passed as args[1] without passing other arguments"""
    def eat(accel_group, acceleratable, keyval, modifier):
        """eat all the extra arguments

        this is ugly, but it works with the code we already had
        before we changed to AccelGroup et al"""
        args[0]()
        pass
    return eat

def make_accel_group(edit_instance):
    keybindings = {
        'h': edit_instance.show_help,
        'i': edit_instance.show_info,
        'n': edit_instance.new_buffer,
        'o': edit_instance.open_file,
        'p': edit_instance.preferences.show,
        'q': edit_instance.dialog_quit,
        's': edit_instance.save_file,
        'w': edit_instance.close_dialog,
        'y': edit_instance.redo,
        'z': edit_instance.undo,
        'm': edit_instance.dialog_minimize,
    }
    ag = Gtk.AccelGroup()
    for key, value in list(keybindings.items()):
        ag.connect(
            ord(key),
            Gdk.ModifierType.CONTROL_MASK,
            Gtk.AccelFlags.VISIBLE,
            dispatch(value)
        )
    ag.connect(
        ord('s'),
        Gdk.ModifierType.CONTROL_MASK|Gdk.ModifierType.SHIFT_MASK,
        Gtk.AccelFlags.VISIBLE,
        dispatch(edit_instance.save_file_as)
    )
    return ag

def define_keybindings(edit_instance):
    """define keybindings, respectively to keyboard layout"""
    keymap = Gdk.Keymap.get_default()
    basic_bindings = {
        Gdk.KEY_Page_Up: edit_instance.prev_buffer,
        Gdk.KEY_Page_Down: edit_instance.next_buffer,
    }
    translated_bindings = {}
    for key, value in list(basic_bindings.items()):
        key_is_found, hardware_keycode = keymap.get_entries_for_keyval(key)
        if key_is_found:
            translated_bindings[hardware_keycode[0]] = value
    return translated_bindings

class UndoableInsert(object):
    """something that has been inserted into our textbuffer"""
    def __init__(self, text_iter, text, length):
        self.offset = text_iter.get_offset()
        self.text = text
        self.length = length
        if self.length > 1 or self.text in ("\r", "\n", " "):
            self.mergeable = False
        else:
            self.mergeable = True

class UndoableDelete(object):
    """something that has ben deleted from our textbuffer"""
    def __init__(self, text_buffer, start_iter, end_iter):
        self.deleted_text = text_buffer.get_text(start_iter, end_iter, False)
        self.start = start_iter.get_offset()
        self.end = end_iter.get_offset()
        # need to find out if backspace or delete key has been used
        # so we don't mess up during redo
        insert_iter = text_buffer.get_iter_at_mark(text_buffer.get_insert())
        if insert_iter.get_offset() <= self.start:
            self.delete_key_used = True
        else:
            self.delete_key_used = False
        if self.end - self.start > 1 or self.deleted_text in ("\r", "\n", " "):
            self.mergeable = False
        else:
            self.mergeable = True

class UndoableBuffer(Gtk.TextBuffer):
    """text buffer with added undo capabilities

    designed as a drop-in replacement for Gtksourceview,
    at least as far as undo is concerned"""

    def __init__(self):
        """
        we'll need empty stacks for undo/redo and some state keeping
        """
        Gtk.TextBuffer.__init__(self)
        self.undo_stack = []
        self.redo_stack = []
        self.modified = False
        self.not_undoable_action = False
        self.undo_in_progress = False
        self.connect('insert-text', self.on_insert_text)
        self.connect('delete-range', self.on_delete_range)
        self.connect('begin_user_action', self.on_begin_user_action)

    @property
    def can_undo(self):
        return bool(self.undo_stack)

    @property
    def can_redo(self):
        return bool(self.redo_stack)

    def on_insert_text(self, textbuffer, text_iter, text, length):
        def can_be_merged(prev, cur):
            """see if we can merge multiple inserts here

            will try to merge words or whitespace
            can't merge if prev and cur are not mergeable in the first place
            can't merge when user set the input bar somewhere else
            can't merge across word boundaries"""
            WHITESPACE = (' ', '\t')
            if not cur.mergeable or not prev.mergeable:
                return False
            if cur.offset != (prev.offset + prev.length):
                return False
            if cur.text in WHITESPACE and not prev.text in WHITESPACE:
                return False
            elif prev.text in WHITESPACE and not cur.text in WHITESPACE:
                return False
            return True

        if not self.undo_in_progress:
            self.redo_stack = []
        if self.not_undoable_action:
            return
        undo_action = UndoableInsert(text_iter, text, length)
        try:
            prev_insert = self.undo_stack.pop()
        except IndexError:
            self.undo_stack.append(undo_action)
            return
        if not isinstance(prev_insert, UndoableInsert):
            self.undo_stack.append(prev_insert)
            self.undo_stack.append(undo_action)
            return
        if can_be_merged(prev_insert, undo_action):
            prev_insert.length += undo_action.length
            prev_insert.text += undo_action.text
            self.undo_stack.append(prev_insert)
        else:
            self.undo_stack.append(prev_insert)
            self.undo_stack.append(undo_action)
        self.modified = True

    def on_delete_range(self, text_buffer, start_iter, end_iter):
        def can_be_merged(prev, cur):
            """see if we can merge multiple deletions here

            will try to merge words or whitespace
            can't merge if delete and backspace key were both used
            can't merge across word boundaries"""

            WHITESPACE = (' ', '\t')
            if prev.delete_key_used != cur.delete_key_used:
                return False
            if prev.start != cur.start and prev.start != cur.end:
                return False
            if cur.deleted_text not in WHITESPACE and \
               prev.deleted_text in WHITESPACE:
                return False
            elif cur.deleted_text in WHITESPACE and \
               prev.deleted_text not in WHITESPACE:
                return False
            return True

        if not self.undo_in_progress:
            self.redo_stack = []
        if self.not_undoable_action:
            return
        undo_action = UndoableDelete(text_buffer, start_iter, end_iter)
        try:
            prev_delete = self.undo_stack.pop()
        except IndexError:
            self.undo_stack.append(undo_action)
            return
        if not isinstance(prev_delete, UndoableDelete):
            self.undo_stack.append(prev_delete)
            self.undo_stack.append(undo_action)
            return
        if can_be_merged(prev_delete, undo_action):
            if prev_delete.start == undo_action.start: # delete key used
                prev_delete.deleted_text += undo_action.deleted_text
                prev_delete.end += (undo_action.end - undo_action.start)
            else: # Backspace used
                prev_delete.deleted_text = "%s%s" % (undo_action.deleted_text,
                                                     prev_delete.deleted_text)
                prev_delete.start = undo_action.start
            self.undo_stack.append(prev_delete)
        else:
            self.undo_stack.append(prev_delete)
            self.undo_stack.append(undo_action)
        self.modified = True

    def on_begin_user_action(self, *args, **kwargs):
        pass

    def begin_not_undoable_action(self):
        """don't record the next actions

        toggles self.not_undoable_action"""
        self.not_undoable_action = True

    def end_not_undoable_action(self):
        """record next actions

        toggles self.not_undoable_action"""
        self.not_undoable_action = False

    def undo(self):
        """undo inserts or deletions

        undone actions are being moved to redo stack"""
        if not self.undo_stack:
            return
        self.begin_not_undoable_action()
        self.undo_in_progress = True
        undo_action = self.undo_stack.pop()
        self.redo_stack.append(undo_action)
        if isinstance(undo_action, UndoableInsert):
            start = self.get_iter_at_offset(undo_action.offset)
            stop = self.get_iter_at_offset(
                undo_action.offset + undo_action.length
            )
            self.delete(start, stop)
            self.place_cursor(start)
        else:
            start = self.get_iter_at_offset(undo_action.start)
            stop = self.get_iter_at_offset(undo_action.end)
            self.insert(start, undo_action.deleted_text)
            if undo_action.delete_key_used:
                self.place_cursor(start)
            else:
                self.place_cursor(stop)
        self.end_not_undoable_action()
        self.undo_in_progress = False
        self.modified = True

    def redo(self):
        """redo inserts or deletions

        redone actions are moved to undo stack"""
        if not self.redo_stack:
            return
        self.begin_not_undoable_action()
        self.undo_in_progress = True
        redo_action = self.redo_stack.pop()
        self.undo_stack.append(redo_action)
        if isinstance(redo_action, UndoableInsert):
            start = self.get_iter_at_offset(redo_action.offset)
            self.insert(start, redo_action.text)
            new_cursor_pos = self.get_iter_at_offset(
                redo_action.offset + redo_action.length
            )
            self.place_cursor(new_cursor_pos)
        else:
            start = self.get_iter_at_offset(redo_action.start)
            stop = self.get_iter_at_offset(redo_action.end)
            self.delete(start, stop)
            self.place_cursor(start)
        self.end_not_undoable_action()
        self.undo_in_progress = False
        self.modified = True

class BasicEdit(object):
    """editing logic that gets passed around"""

    def __init__(self):
        self.current = 0
        self.buffers = []
        self.config = config
        gui = GUI()
        state['gui'] = gui
        self.preferences = Preferences()
        try:
            self.recent_manager = Gtk.RecentManager.get_default()
        except AttributeError:
            self.recent_manager = None
        self.status = gui.status
        self.window = gui.window
        self.window.add_accel_group(make_accel_group(self))
        self.textbox = gui.textbox
        self.UNNAMED_FILENAME = FILE_UNNAMED

        self.autosave_timeout_id = ''
        self.autosave_elapsed = ''

        self.textbox.connect('key-press-event', self.key_press_event)

        # Autosave timer object
        autosave.start_autosave(self)

        self.window.show_all()
        self.window.fullscreen()

        # Handle multiple monitors
        screen = Gdk.Screen.get_default()
        root_window = screen.get_root_window()
        root_window, mouse_x, mouse_y, mouse_mods = root_window.get_pointer()
        current_monitor_number = screen.get_monitor_at_point(mouse_x, mouse_y)
        monitor_geometry = screen.get_monitor_geometry(current_monitor_number)
        self.window.move(monitor_geometry.x, monitor_geometry.y)

        # Defines the glade file functions for use on closing a buffer or exit
        gladefile = os.path.join(state['absolute_path'], "interface.ui")
        builder = Gtk.Builder()
        builder.add_from_file(gladefile)
        self.dialog = builder.get_object("SaveBuffer")
        self.dialog.set_transient_for(self.window)
        self.quitdialog = builder.get_object("QuitSave")
        self.quitdialog.set_transient_for(self.window)
        dic = {
                "on_button-close_clicked": self.unsave_dialog,
                "on_button-cancel_clicked": self.cancel_dialog,
                "on_button-save_clicked": self.save_dialog,
                "on_button-close2_clicked": self.quit_quit,
                "on_button-cancel2_clicked": self.cancel_quit,
                "on_button-save2_clicked": self.save_quit,
                }
        builder.connect_signals(dic)

        self.keybindings = define_keybindings(self)

    def key_press_event(self, widget, event):
        """ key press event dispatcher """
        if event.get_state() & Gdk.ModifierType.CONTROL_MASK:
            if event.hardware_keycode in self.keybindings:
                self.keybindings[event.hardware_keycode]()
                return True
        return False

    def show_info(self):
        """ Display buffer information on status label for 5 seconds """

        buf = self.buffers[self.current]
        if buf.modified:
            status = _(' (modified)')
        else:
            status = ''
        self.status.set_text(_('Buffer %(buffer_id)d: %(buffer_name)s\
%(status)s, %(char_count)d character(s), %(word_count)d word(s)\
, %(lines)d line(s)') % {
            'buffer_id': self.current + 1,
            'buffer_name': buf.filename if int(config.get('visual', 'showpath')) else os.path.split(buf.filename)[1],
            'status': status,
            'char_count': buf.get_char_count(),
            'word_count': self.word_count(buf),
            'lines': buf.get_line_count(),
            }, 5000)

    def undo(self):
        """ Undo last typing """

        buf = self.textbox.get_buffer()
        if buf.can_undo:
            buf.undo()
        else:
            self.status.set_text(_('Nothing more to undo!'))

    def redo(self):
        """ Redo last typing """

        buf = self.textbox.get_buffer()
        if buf.can_redo:
            buf.redo()
        else:
            self.status.set_text(_('Nothing more to redo!'))

    def ask_restore(self):
        """ask if backups should be restored

        returns True if proposal is accepted
        returns False in any other case (declined/dialog closed)"""
        restore_dialog = Gtk.Dialog(
            title=_('Restore backup?'),
            parent=self.window,
            flags=Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
            buttons=(
                Gtk.STOCK_DISCARD, Gtk.ResponseType.REJECT,
                Gtk.STOCK_OPEN, Gtk.ResponseType.ACCEPT
            )
        )
        question_asked = Gtk.Label(label=
            _('''Backup information for this file has been found.
Open those instead of the original file?''')
        )
        question_asked.set_line_wrap(True)

        question_sign = Gtk.Image.new_from_stock(
            stock_id=Gtk.STOCK_DIALOG_QUESTION,
            size=Gtk.IconSize.DIALOG
        )
        question_sign.show()

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        hbox.pack_start(question_sign, True, True, 0)
        hbox.pack_start(question_asked, True, True, 0)
        hbox.show()
        restore_dialog.vbox.pack_start(
            hbox, True, True, 0
        )

        restore_dialog.set_default_response(Gtk.ResponseType.ACCEPT)
        restore_dialog.show_all()
        resp = restore_dialog.run()
        restore_dialog.destroy()
        return resp == -3

    def open_file(self):
        """ Open file """

        chooser = Gtk.FileChooserDialog('PyRoom', self.window,
                Gtk.FileChooserAction.OPEN,
                buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                Gtk.STOCK_OPEN, Gtk.ResponseType.OK))
        chooser.set_default_response(Gtk.ResponseType.OK)
        buf = self.buffers[self.current]
        if buf.filename != FILE_UNNAMED:
            chooser.set_current_folder(
                os.path.dirname(os.path.abspath(buf.filename)
            ))
        else:
            chooser_path = get_likely_chooser_path(self.buffers, self.current)
            if chooser_path:
                chooser.set_current_folder(chooser_path)
        res = chooser.run()
        if res == Gtk.ResponseType.OK:
            self.open_file_no_chooser(chooser.get_filename())
        else:
            self.status.set_text(_('Closed, no files selected'))
        chooser.destroy()

    def open_file_no_chooser(self, filename):
        """ Open specified file """
        def check_backup(filename):
            """check if restore from backup is an option

            returns backup filename if there's a backup file and
                    user wants to restore from it, else original filename
            """
            fname = autosave.get_autosave_filename(filename)
            if os.path.isfile(fname):
                if self.ask_restore():
                    return fname
                else:
                    os.remove(fname)
            return filename
        buf = self.new_buffer()
        buf.filename = filename
        filename_to_open = check_backup(filename)

        try:
            buffer_file = open(filename_to_open, 'r')
            buf = self.buffers[self.current]
            buf.begin_not_undoable_action()
            utf8 = str(buffer_file.read(), 'utf-8')
            buf.set_text(utf8)
            buf.end_not_undoable_action()
            buffer_file.close()
        except IOError as unable_to_open_file:
            (errno, strerror) = unable_to_open_file.args
            errortext = _('Unable to open %(filename)s.') % {
                'filename': filename_to_open
            }
            if errno == 13:
                errortext += _(' You do not have permission to open \
the file.')
            if not errno == 2:
                raise PyroomError(errortext)
        except:
            raise PyroomError(_('Unable to open %s\n') % filename_to_open)
        else:
            self.status.set_text(_('File %s open') % filename_to_open)

    def save_file(self):
        """ Save file """
        try:
            buf = self.buffers[self.current]
            if buf.filename != FILE_UNNAMED:
                buffer_file = open(buf.filename, 'w')
                txt = buf.get_text(buf.get_start_iter(),
                                     buf.get_end_iter(), False)
                buffer_file.write(txt)
                if self.recent_manager:
                    recent_data = Gtk.RecentData()
                    recent_data.mime_type = 'text/plain'
                    recent_data.app_name = 'pyroom'
                    recent_data.app_exec = '%F'
                    recent_data.is_private = False
                    recent_data.display_name = os.path.basename(buf.filename)

                    self.recent_manager.add_full(
                        "file://" + urllib.parse.quote(buf.filename),recent_data)
                buffer_file.close()
                buf.begin_not_undoable_action()
                buf.end_not_undoable_action()
                self.status.set_text(_('File %s saved') % buf.filename)
            else:
                self.save_file_as()
                return
        except IOError as unable_to_save:
            (errno, strerror) = unable_to_save.args
            errortext = _('Unable to save %(filename)s.') % {
                'filename': buf.filename}
            if errno == 13:
                errortext += _(' You do not have permission to write to \
the file.')
            raise PyroomError(errortext)
        except:
            raise PyroomError(_('Unable to save %s\n') % buf.filename)
        buf.modified = False

    def save_file_as(self):
        """ Save file as """

        buf = self.buffers[self.current]
        chooser = Gtk.FileChooserDialog('PyRoom', self.window,
                Gtk.FileChooserAction.SAVE,
                buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                Gtk.STOCK_SAVE, Gtk.ResponseType.OK))
        chooser.set_default_response(Gtk.ResponseType.OK)
        chooser.set_do_overwrite_confirmation(True)
        if buf.filename != FILE_UNNAMED:
            chooser.set_filename(buf.filename)
        else:
            chooser_path = get_likely_chooser_path(self.buffers, self.current)
            if chooser_path:
                chooser.set_current_folder(chooser_path)
        res = chooser.run()
        if res == Gtk.ResponseType.OK:
            buf.filename = chooser.get_filename()
            self.save_file()
        else:
            self.status.set_text(_('Closed, no files selected'))
        chooser.destroy()

    def word_count(self, buf):
        """ Word count in a text buffer """

        iter1 = buf.get_start_iter()
        iter2 = iter1.copy()
        iter2.forward_word_end()
        count = 0
        while iter2.get_offset() != iter1.get_offset():
            count += 1
            iter1 = iter2.copy()
            iter2.forward_word_end()
        return count

    def show_help(self):
        """ Create a new buffer and inserts help """
        buf = self.new_buffer()
        buf.begin_not_undoable_action()
        buf.set_text(HELP)
        buf.end_not_undoable_action()
        self.status.set_text("Displaying help. Press control W to exit and \
continue editing your document.")

    def new_buffer(self):
        """ Create a new buffer """

        buf = UndoableBuffer()
        buf.filename = FILE_UNNAMED
        self.buffers.insert(self.current + 1, buf)
        buf.place_cursor(buf.get_end_iter())
        self.next_buffer()
        return buf

    def close_dialog(self):
        """ask for confirmation if there are unsaved contents"""
        buf = self.buffers[self.current]
        if buf.modified:
            self.dialog.show()
        else:
            self.close_buffer()

    def cancel_dialog(self, widget, data=None):
        """dialog has been canceled"""
        self.dialog.hide()

    def unsave_dialog(self, widget, data =None):
        """don't save before closing"""
        self.dialog.hide()
        self.close_buffer()

    def save_dialog(self, widget, data=None):
        """save when closing"""
        self.dialog.hide()
        self.save_file()
        self.close_buffer()

    def close_buffer(self):
        """ Close current buffer """
        autosave_fname = autosave.get_autosave_filename(
            self.buffers[self.current].filename
        )
        if os.path.isfile(autosave_fname):
            try:
                os.remove(autosave_fname)
            except OSError:
                raise PyroomError(_('Could not delete autosave file.'))
        if len(self.buffers) > 1:
            self.buffers.pop(self.current)
            self.current = min(len(self.buffers) - 1, self.current)
            self.set_buffer(self.current)
        else:
            quit()

    def set_buffer(self, index):
        """ Set current buffer """

        if index >= 0 and index < len(self.buffers):
            self.current = index
            buf = self.buffers[index]
            self.textbox.set_buffer(buf)
            if hasattr(self, 'status'):
                self.status.set_text(
                    _('Switching to buffer %(buffer_id)d (%(buffer_name)s)')
                    % {'buffer_id': self.current + 1,
                       'buffer_name': buf.filename}
                )

    def next_buffer(self):
        """ Switch to next buffer """

        if self.current < len(self.buffers) - 1:
            self.current += 1
        else:
            self.current = 0
        self.set_buffer(self.current)
        state['gui'].textbox.scroll_to_mark(
            self.buffers[self.current].get_insert(),
            0.0, False, .0, .0,
        )

    def prev_buffer(self):
        """ Switch to prev buffer """

        if self.current > 0:
            self.current -= 1
        else:
            self.current = len(self.buffers) - 1
        self.set_buffer(self.current)
        state['gui'].textbox.scroll_to_mark(
            self.buffers[self.current].get_insert(),
            0.0,
        )
    def dialog_quit(self):
        """the quit dialog"""
        count = 0
        ret = False
        for buf in self.buffers:
            if buf.modified:
                count = count + 1
        if count > 0:
            self.quitdialog.show()
        else:
            self.quit()

    def cancel_quit(self, widget, data=None):
        """don't quit"""
        self.quitdialog.hide()

    def save_quit(self, widget, data=None):
        """save before quitting"""
        self.quitdialog.hide()
        for buf in self.buffers:
            if buf.modified:
                if buf.filename == FILE_UNNAMED:
                    self.save_file_as()
                else:
                    self.save_file()
        self.quit()

    def quit_quit(self, widget, data=None):
        """really quit"""
        self.quitdialog.hide()
        self.quit()

    def quit(self):
        """cleanup before quitting"""
        autosave.stop_autosave(self)
        state['gui'].quit()

    def dialog_minimize(self):
        """ Minimize (iconify) the window """
        state['gui'].iconify()
