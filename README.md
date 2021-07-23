PyRoom Project
==============

PyRoom is a fullscreen simple text editor, without a toolbar, a menubar or
anything that would distract the user from his most important task: writing.

Dependencies
------------

PyRoom depends on Python 3, PyGi and XDG bindings for Python (xdg). Please
refer to your system documentation for information on how to install these
modules if they're not currently available.
Optional: install via  
```
pip install -r requirements.txt
```

Optional dependencies
---------------------

In order to use GNOME default fonts in PyRoom, gconf bindings (python-gconf)
are recommended.

If you're installing manually from our tarball and want to use PyRoom in your
own language, you'll need to install gettext.

Installing and Running 
----------------------

PyRoom is available as a distutils enabled package. Installation procedures
for those are easy:

Either unpack the tarball 
```    
tar xvfz pyroom*.tar.gz
```

or check out our git repo for a development version (we try to keep those
unbroken and ready for production use)
```    
git clone https://github.com/quintusfelix/PyRoom
```

From there, you can either run pyroom from commandline
```
cd pyroom/
./pyroom
```

Or install it system wide
```
cd pyroom
python3 setup.py install # as root
pyroom
```

Usage 
-----

### Running PyRoom

To run pyroom and instruct it to load some existing files, type:
```
pyroom /path/to/file1 /other/path/to/file2
```

### Example Usage

For example, to load PyRoom and instruct it to load the files `article.txt` and
`blogpost.txt`, type the following:
```
pyroom article.txt blog.txt
```

### Key Bindings

There are a few keys allowing you to perform a few useful commands:

* <kbd>Ctrl</kbd>+<kbd>H</kbd>: Show help in a new buffer
* <kbd>Ctrl</kbd>+<kbd>I</kbd>: Show buffer information
* <kbd>Ctrl</kbd>+<kbd>M</kbd>: Minimize buffer
* <kbd>Ctrl</kbd>+<kbd>N</kbd>: Create a new buffer
* <kbd>Ctrl</kbd>+<kbd>O</kbd>: Open a file in a new buffer
* <kbd>Ctrl</kbd>+<kbd>Q</kbd>: Quit
* <kbd>Ctrl</kbd>+<kbd>S</kbd>: Save current buffer
* <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>S</kbd>: Save current buffer as
* <kbd>Ctrl</kbd>+<kbd>W</kbd>: Close buffer and exit if it was the last buffer
* <kbd>Ctrl</kbd>+<kbd>Y</kbd>: Redo last typing
* <kbd>Ctrl</kbd>+<kbd>Z</kbd>: Undo last typing
* <kbd>Ctrl</kbd>+<kbd>Page Up</kbd>: Switch to previous buffer
* <kbd>Ctrl</kbd>+<kbd>Page Down</kbd>: Switch to next buffer

## Want to know more?

* PyRoom Website: http://pyroom.org
* PyRoom project page on github: https://github.com/quintusfelix/PyRoom
