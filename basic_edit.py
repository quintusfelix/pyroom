import gtk
import gtk.glade
import gtksourceview
import ConfigParser

from gui import GUI
from preferences import Preferences

import restore_session #Allows a session to be restored with "-s"
import autosave
#import check_unsaved #Checks that a buffer is unmodified before closing

FILE_UNNAMED = _('* Unnamed *')

USAGE = _('Usage: pyroom [-v] [--style={style name}] file1 file2')

KEY_BINDINGS = '\n'.join([
_('Control-H: Show help in a new buffer'),
_('Control-I: Show buffer information'),
_('Control-L: Toggle line number'),
_('Control-N: Create a new buffer'),
_('Control-O: Open a file in a new buffer'),
_('Control-Q: Quit'),
_('Control-S: Save current buffer'),
_('Control-Shift-S: Save current buffer as'),
_('Control-W: Close buffer and exit if it was the last buffer'),
_('Control-Y: Redo last typing'),
_('Control-Z: Undo last typing'),
_('Control-Page Up: Switch to previous buffer'),
_('Control-Page Down: Switch to next buffer'),
_('Control-Plus: Increases font size'),
_('Control-Minus: Decreases font size'),]
)

HELP = \
    _("""PyRoom - an adaptation of write room
Copyright (c) 2007 Nicolas Rougier, NoWhereMan
Copyright (c) 2008 Bruno Bord

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.

Usage:
------

%s


Commands:
---------
%s

Warnings:
---------
No autosave.
No question whether to close a modified buffer or not
""" % (USAGE, KEY_BINDINGS))

class BasicEdit():
    def __init__(self,style,verbose):

        self.style = style
        self.gui = GUI(style)
        self.preferences = Preferences(self.gui,style,verbose)
        self.status = self.gui.status
        self.window = self.gui.window
        self.textbox = self.gui.textbox
        self.config = ConfigParser.ConfigParser()
        self.config.read("example.conf")

        self.new_buffer()
        restore_session.open_session(self, verbose)
        self.textbox.connect('key-press-event', self.key_press_event)
        self.textbox.set_show_line_numbers(int(self.config.get("visual","linenumber")))
        self.status.set_text(
            _('Welcome to PyRoom 1.0, type Control-H for help'))
        autosave.autosave_init(self) #autosave timer object
        self.window.show_all()
        self.window.fullscreen()
        
        #Defines the glade file functions for use on closing a buffer
        self.wTree = gtk.glade.XML("interface.glade", "SaveBuffer")
        self.dialog = self.wTree.get_widget("SaveBuffer")
        self.dialog.set_transient_for(self.window)
        dic = {
                "on_button-close_clicked" : self.unsave_dialog,
                "on_button-cancel_clicked" : self.cancel_dialog,
                "on_button-save_clicked" : self.save_dialog,
                }
        self.wTree.signal_autoconnect(dic)
        
        #Defines the glade file functions for use on exit
        self.aTree = gtk.glade.XML("interface.glade", "QuitSave")
        self.quitdialog = self.aTree.get_widget("QuitSave")
        self.quitdialog.set_transient_for(self.window)
        dic = {
                "on_button-close2_clicked" : self.quit_quit,
                "on_button-cancel2_clicked" : self.cancel_quit,
                "on_button-save2_clicked" : self.save_quit,
                }
        self.aTree.signal_autoconnect(dic)        
    def key_press_event(self, widget, event):
        """ key press event dispatcher """

        bindings = {
            gtk.keysyms.Page_Up: self.prev_buffer,
            gtk.keysyms.Page_Down: self.next_buffer,
            gtk.keysyms.h: self.show_help,
            gtk.keysyms.H: self.show_help,
            gtk.keysyms.i: self.show_info,
            gtk.keysyms.I: self.show_info,
            gtk.keysyms.n: self.new_buffer,
            gtk.keysyms.N: self.new_buffer,
            gtk.keysyms.o: self.open_file,
            gtk.keysyms.O: self.open_file,
            gtk.keysyms.p: self.preferences.show,
            gtk.keysyms.P: self.preferences.show,
            gtk.keysyms.q: self.dialog_quit,
            gtk.keysyms.Q: self.dialog_quit,
            gtk.keysyms.s: self.save_file,
            gtk.keysyms.S: self.save_file,
            gtk.keysyms.w: self.close_dialog,
            gtk.keysyms.W: self.close_dialog,
            gtk.keysyms.y: self.redo,
            gtk.keysyms.Y: self.redo,
            gtk.keysyms.z: self.undo,
            gtk.keysyms.Z: self.undo
            }
        if event.state & gtk.gdk.CONTROL_MASK:

            # Special case for Control-Shift-s

            if event.state & gtk.gdk.SHIFT_MASK:
                print event.keyval
            if event.state & gtk.gdk.SHIFT_MASK and event.keyval\
                 == gtk.keysyms.S:
                self.edit.save_file_as()
                return True
            if bindings.has_key(event.keyval):
                bindings[event.keyval]()
                return True
        return False


    current = 0
    buffers = []
    def show_info(self):
        """ Display buffer information on status label for 5 seconds """

        buffer = self.buffers[self.current]
        if buffer.can_undo() or buffer.can_redo():
            status = _(' (modified)')
        else:
            status = ''
        self.status.set_text(_('Buffer %(buffer_id)d: %(buffer_name)s%(status)s, %(char_count)d byte(s), %(word_count)d word(s), %(lines)d line(s)') % {
            'buffer_id': self.current + 1,
            'buffer_name': buffer.filename,
            'status': status,
            'char_count': buffer.get_char_count(),
            'word_count': self.word_count(buffer),
            'lines': buffer.get_line_count(),
            }, 5000)
    def undo(self):
        """ Undo last typing """

        buffer = self.textbox.get_buffer()
        if buffer.can_undo():
            buffer.undo()
        else:
            self.status.set_text(_('No more undo!'))

    def redo(self):
        """ Redo last typing """

        buffer = self.textbox.get_buffer()
        if buffer.can_redo():
            buffer.redo()
        else:
            self.status.set_text(_('No more redo!'))

    def toggle_lines(self):
        """ Toggle lines number """

        b = not self.textbox.get_show_line_numbers()
        self.textbox.set_show_line_numbers(b)

    def open_file(self):
        """ Open file """

        chooser = gtk.FileChooserDialog('PyRoom', self.window,
                gtk.FILE_CHOOSER_ACTION_OPEN,
                buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                gtk.STOCK_OPEN, gtk.RESPONSE_OK))
        chooser.set_default_response(gtk.RESPONSE_OK)

        res = chooser.run()
        if res == gtk.RESPONSE_OK:
            buffer = self.new_buffer()
            buffer.filename = chooser.get_filename()
            try:
                f = open(buffer.filename, 'r')
                buffer = self.buffers[self.current]
                buffer.begin_not_undoable_action()
                utf8 = unicode(f.read(), 'utf-8')
                buffer.set_text(utf8)
                buffer.end_not_undoable_action()
                f.close()
                self.status.set_text(_('File %s open')
                         % buffer.filename)
            except IOError, (errno, strerror):
                errortext = _('Unable to open %(filename)s.' % {'filename': buffer.filename})
                if errno == 2:
                    errortext += _(' The file does not exist.')
                elif errno == 13:
                    errortext += _(' You do not have permission to open the file.')
                buffer.set_text(_(errortext))
                if verbose:
                    print ('Unable to open %(filename)s. %(traceback)s'
                        % {'filename': buffer.filename, 'traceback': traceback.format_exc()})
                self.status.set_text(_('Failed to open %s')
                    % buffer.filename)
                buffer.filename = FILE_UNNAMED
            except:
                buffer.set_text(_('Unable to open %s\n'
                                 % buffer.filename))
                if verbose:
                    print ('Unable to open %(filename)s. %(traceback)s'
                        % {'filename': buffer.filename,
                        'traceback': traceback.format_exc()})
                buffer.filename = FILE_UNNAMED
        else:
            self.status.set_text(_('Closed, no files selected'))
        chooser.destroy()

    def save_file(self):
        """ Save file """

        buffer = self.buffers[self.current]
        if buffer.filename != FILE_UNNAMED:
            f = open(buffer.filename, 'w')
            txt = buffer.get_text(buffer.get_start_iter(),
                                  buffer.get_end_iter())
            f.write(txt)
            f.close()
            buffer.begin_not_undoable_action()
            buffer.end_not_undoable_action()
            self.status.set_text(_('File %s saved') % buffer.filename)
        else:
            self.save_file_as()

    def save_file_as(self):
        """ Save file as """

        buffer = self.buffers[self.current]
        chooser = gtk.FileChooserDialog('PyRoom', self.window,
                gtk.FILE_CHOOSER_ACTION_SAVE,
                buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                gtk.STOCK_SAVE, gtk.RESPONSE_OK))
        chooser.set_default_response(gtk.RESPONSE_OK)
        if buffer.filename != FILE_UNNAMED:
            chooser.set_filename(buffer.filename)
        res = chooser.run()
        if res == gtk.RESPONSE_OK:
            buffer.filename = chooser.get_filename()
            self.save_file()
        else:
            self.status.set_text(_('Closed, no files selected'))
        chooser.destroy()

    # BB



    def word_count(self, buffer):
        """ Word count in a text buffer """

        iter1 = buffer.get_start_iter()
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
        buffer = self.new_buffer()
        buffer.begin_not_undoable_action()
        buffer.set_text(HELP)
        buffer.end_not_undoable_action()

    def new_buffer(self):
        """ Create a new buffer """

        buffer = gtksourceview.SourceBuffer()
        buffer.set_check_brackets(False)
        buffer.set_highlight(False)
        buffer.filename = FILE_UNNAMED
        self.buffers.insert(self.current + 1, buffer)
        buffer.place_cursor(buffer.get_start_iter())
        self.next_buffer()
        return buffer
        
    def close_dialog(self):
        buffer = self.buffers[self.current]
        if buffer.can_undo() or buffer.can_redo():
            self.dialog.show()
        else:
            self.close_buffer()
            
    def cancel_dialog(self, widget, data=None):
        self.dialog.hide()
        
    def unsave_dialog(self, widget, data =None):
        self.dialog.hide()
        self.close_buffer()
        
    def save_dialog(self,widget,data=None):
        self.dialog.hide()
        try:
            self.save_file()
            self.close_buffer()
        except:
            pass
        
    def close_buffer(self):
        """ Close current buffer """


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
            buffer = self.buffers[index]
            self.textbox.set_buffer(buffer)
            if hasattr(self, 'status'):
                self.status.set_text(
                    _('Switching to buffer %(buffer_id)d (%(buffer_name)s)'
                    % {'buffer_id': self.current + 1, 'buffer_name'
                    : buffer.filename}))

    def next_buffer(self):
        """ Switch to next buffer """

        if self.current < len(self.buffers) - 1:
            self.current += 1
        else:
            self.current = 0
        self.set_buffer(self.current)

    def prev_buffer(self):
        """ Switch to prev buffer """

        if self.current > 0:
            self.current -= 1
        else:
            self.current = len(self.buffers) - 1
        self.set_buffer(self.current)
    def dialog_quit(self):
        count = 0
        ret = False
        for buffer in self.buffers:
            if buffer.can_undo() or buffer.can_redo():
                count = count + 1
        if count > 0:
            self.quitdialog.show()
        else:
            self.quit()
    def cancel_quit(self,widget, data=None):
        self.quitdialog.hide()
        
    def save_quit(self, widget, data=None):
        self.quitdialog.hide()
        try:
            for buffer in self.buffers:
                if buffer.can_undo() or buffer.can_redo():
                        if buffer.filename == FILE_UNNAMED:
                            self.save_file_as()
                        else:
                            self.save_file()
            self.quit()
        except:
            pass

    def quit_quit(self,widget,data=None):
        self.quitdialog.hide()
        self.quit()
    def quit(self):
        #Add any functions that you want to take place here before pyRoom quits
        restore_session.save_session(self)
        autosave.autosave_quit(self)
        self.gui.quit()

# EOF
