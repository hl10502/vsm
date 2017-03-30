#!/usr/bin/env python
# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2012, Cloudscaling
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""vsm HACKING file compliance testing

built on top of pep8.py
"""

import inspect
import logging
import os
import re
import sys
import tokenize
import warnings

import pep8

# Don't need this for testing
logging.disable('LOG')

#N1xx comments
#N2xx except
#N3xx imports
#N4xx docstrings
#N5xx dictionaries/lists
#N6xx Calling methods
#N7xx localization

IMPORT_EXCEPTIONS = ['sqlalchemy', 'migrate', 'vsm.db.sqlalchemy.session']
DOCSTRING_TRIPLE = ['"""', "'''"]
VERBOSE_MISSING_IMPORT = False

def is_import_exception(mod):
    return mod in IMPORT_EXCEPTIONS or \
        any(mod.startswith(m + '.') for m in IMPORT_EXCEPTIONS)

def import_normalize(line):
    # convert "from x import y" to "import x.y"
    # handle "from x import y as z" to "import x.y as z"
    split_line = line.split()
    if (line.startswith("from ") and "," not in line and
            split_line[2] == "import" and split_line[3] != "*" and
            split_line[1] != "__future__" and
            (len(split_line) == 4 or
                (len(split_line) == 6 and split_line[4] == "as"))):
        return "import %s.%s" % (split_line[1], split_line[3])
    else:
        return line

def vsm_todo_format(physical_line):
    """Check for 'TODO()'.

    vsm HACKING guide recommendation for TODO:
    Include your name with TODOs as in "#TODO(termie)"
    N101
    """
    pos = physical_line.find('TODO')
    pos1 = physical_line.find('TODO(')
    pos2 = physical_line.find('#')  # make sure its a comment
    if (pos != pos1 and pos2 >= 0 and pos2 < pos):
        return pos, "VSM N101: Use TODO(NAME)"

def vsm_except_format(logical_line):
    """Check for 'except:'.

    vsm HACKING guide recommends not using except:
    Do not write "except:", use "except Exception:" at the very least
    N201
    """
    if logical_line.startswith("except:"):
        yield 6, "VSM N201: no 'except:' at least use 'except Exception:'"

def vsm_except_format_assert(logical_line):
    """Check for 'assertRaises(Exception'.

    vsm HACKING guide recommends not using assertRaises(Exception...):
    Do not use overly broad Exception type
    N202
    """
    if logical_line.startswith("self.assertRaises(Exception"):
        yield 1, "VSM N202: assertRaises Exception too broad"

def vsm_one_import_per_line(logical_line):
    """Check for import format.

    vsm HACKING guide recommends one import per line:
    Do not import more than one module per line

    Examples:
    BAD: from vsm.rpc.common import RemoteError, LOG
    N301
    """
    pos = logical_line.find(',')
    parts = logical_line.split()
    if (pos > -1 and (parts[0] == "import" or
                      parts[0] == "from" and parts[2] == "import") and
            not is_import_exception(parts[1])):
        yield pos, "VSM N301: one import per line"

_missingImport = set([])

def vsm_import_module_only(logical_line):
    """Check for import module only.

    vsm HACKING guide recommends importing only modules:
    Do not import objects, only modules
    N302 import only modules
    N303 Invalid Import
    N304 Relative Import
    """
    def importModuleCheck(mod, parent=None, added=False):
        """
        If can't find module on first try, recursively check for relative
        imports
        """
        current_path = os.path.dirname(pep8.current_file)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', DeprecationWarning)
                valid = True
                if parent:
                    if is_import_exception(parent):
                        return
                    parent_mod = __import__(parent,
                                            globals(),
                                            locals(),
                                            [mod],
                                            -1)
                    valid = inspect.ismodule(getattr(parent_mod, mod))
                else:
                    __import__(mod, globals(), locals(), [], -1)
                    valid = inspect.ismodule(sys.modules[mod])
                if not valid:
                    if added:
                        sys.path.pop()
                        added = False
                        return (logical_line.find(mod),
                                ("VSM N304: No "
                                 "relative  imports. '%s' is a relative import"
                                % logical_line))
                    return (logical_line.find(mod),
                            ("VSM N302: import only "
                             "modules. '%s' does not import a module"
                            % logical_line))

        except (ImportError, NameError) as exc:
            if not added:
                added = True
                sys.path.append(current_path)
                return importModuleCheck(mod, parent, added)
            else:
                name = logical_line.split()[1]
                if name not in _missingImport:
                    if VERBOSE_MISSING_IMPORT:
                        print >> sys.stderr, ("ERROR: import '%s' failed: %s" %
                                              (name, exc))
                    _missingImport.add(name)
                added = False
                sys.path.pop()
                return

        except AttributeError:
            # Invalid import
            return logical_line.find(mod), ("VSM N303: Invalid import, "
                                            "AttributeError raised")

    # convert "from x import y" to " import x.y"
    # convert "from x import y as z" to " import x.y"
    import_normalize(logical_line)
    split_line = logical_line.split()

    if (logical_line.startswith("import ") and
            "," not in logical_line and
            (len(split_line) == 2 or
                (len(split_line) == 4 and split_line[2] == "as"))):
        mod = split_line[1]
        rval = importModuleCheck(mod)
        if rval is not None:
            yield rval

    # TODO(jogo) handle "from x import *"

#TODO(jogo): import template: N305

def vsm_import_alphabetical(physical_line, line_number, lines):
    """Check for imports in alphabetical order.

    vsm HACKING guide recommendation for imports:
    imports in human alphabetical order
    N306
    """
    # handle import x
    # use .lower since capitalization shouldn't dictate order
    split_line = import_normalize(physical_line.strip()).lower().split()
    split_previous = import_normalize(
        lines[line_number - 2]).strip().lower().split()
    # with or without "as y"
    length = [2, 4]
    if (len(split_line) in length and len(split_previous) in length and
            split_line[0] == "import" and split_previous[0] == "import"):
        if split_line[1] < split_previous[1]:
            return (0,
                    "VSM N306: imports not in alphabetical order (%s, %s)"
                    % (split_previous[1], split_line[1]))

def vsm_docstring_start_space(physical_line):
    """Check for docstring not start with space.

    vsm HACKING guide recommendation for docstring:
    Docstring should not start with space
    N401
    """
    pos = max([physical_line.find(i) for i in DOCSTRING_TRIPLE])  # start
    if (pos != -1 and len(physical_line) > pos + 1):
        if (physical_line[pos + 3] == ' '):
            return (pos,
                    "VSM N401: one line docstring should not start with"
                    " a space")

def vsm_docstring_one_line(physical_line):
    """Check one line docstring end.

    vsm HACKING guide recommendation for one line docstring:
    A one line docstring looks like this and ends in a period.
    N402
    """
    pos = max([physical_line.find(i) for i in DOCSTRING_TRIPLE])  # start
    end = max([physical_line[-4:-1] == i for i in DOCSTRING_TRIPLE])  # end
    if (pos != -1 and end and len(physical_line) > pos + 4):
        if (physical_line[-5] != '.' and physical_line):
            return pos, "VSM N402: one line docstring needs a period"

def vsm_docstring_multiline_end(physical_line):
    """Check multi line docstring end.

    vsm HACKING guide recommendation for docstring:
    Docstring should end on a new line
    N403
    """
    pos = max([physical_line.find(i) for i in DOCSTRING_TRIPLE])  # start
    if (pos != -1 and len(physical_line) == pos):
        print physical_line
        if (physical_line[pos + 3] == ' '):
            return (pos, "VSM N403: multi line docstring end on new line")

FORMAT_RE = re.compile("%(?:"
                       "%|"           # Ignore plain percents
                       "(\(\w+\))?"   # mapping key
                       "([#0 +-]?"    # flag
                       "(?:\d+|\*)?"  # width
                       "(?:\.\d+)?"   # precision
                       "[hlL]?"       # length mod
                       "\w))")        # type

class LocalizationError(Exception):
    pass

def check_l18n():
    """Generator that checks token stream for localization errors.

    Expects tokens to be ``send``ed one by one.
    Raises LocalizationError if some error is found.
    """
    while True:
        try:
            token_type, text, _, _, _ = yield
        except GeneratorExit:
            return
        if token_type == tokenize.NAME and text == "_":
            while True:
                token_type, text, start, _, _ = yield
                if token_type != tokenize.NL:
                    break
            if token_type != tokenize.OP or text != "(":
                continue  # not a localization call

            format_string = ''
            while True:
                token_type, text, start, _, _ = yield
                if token_type == tokenize.STRING:
                    format_string += eval(text)
                elif token_type == tokenize.NL:
                    pass
                else:
                    break

            if not format_string:
                raise LocalizationError(
                    start,
                    "VSM N701: Empty localization string")
            if token_type != tokenize.OP:
                raise LocalizationError(
                    start,
                    "VSM N701: Invalid localization call")
            if text != ")":
                if text == "%":
                    raise LocalizationError(
                        start,
                        "VSM N702: Formatting operation should be outside"
                        " of localization method call")
                elif text == "+":
                    raise LocalizationError(
                        start,
                        "VSM N702: Use bare string concatenation instead"
                        " of +")
                else:
                    raise LocalizationError(
                        start,
                        "VSM N702: Argument to _ must be just a string")

            format_specs = FORMAT_RE.findall(format_string)
            positional_specs = [(key, spec) for key, spec in format_specs
                                if not key and spec]
            # not spec means %%, key means %(smth)s
            if len(positional_specs) > 1:
                raise LocalizationError(
                    start,
                    "VSM N703: Multiple positional placeholders")

def vsm_localization_strings(logical_line, tokens):
    """Check localization in line.

    N701: bad localization call
    N702: complex expression instead of string as argument to _()
    N703: multiple positional placeholders
    """

    gen = check_l18n()
    next(gen)
    try:
        map(gen.send, tokens)
        gen.close()
    except LocalizationError as e:
        yield e.args

#TODO(jogo) Dict and list objects

current_file = ""

def readlines(filename):
    """Record the current file being tested."""
    pep8.current_file = filename
    return open(filename).readlines()

def add_vsm():
    """Monkey patch in vsm guidelines.

    Look for functions that start with vsm_  and have arguments
    and add them to pep8 module
    Assumes you know how to write pep8.py checks
    """
    for name, function in globals().items():
        if not inspect.isfunction(function):
            continue
        args = inspect.getargspec(function)[0]
        if args and name.startswith("vsm"):
            exec("pep8.%s = %s" % (name, name))

if __name__ == "__main__":
    #include vsm path
    sys.path.append(os.getcwd())
    #VSM error codes start with an N
    pep8.ERRORCODE_REGEX = re.compile(r'[EWN]\d{3}')
    add_vsm()
    pep8.current_file = current_file
    pep8.readlines = readlines
    try:
        pep8._main()
    finally:
        if len(_missingImport) > 0:
            print >> sys.stderr, ("%i imports missing in this test environment"
                                  % len(_missingImport))
