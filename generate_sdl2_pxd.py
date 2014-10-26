#!/usr/bin/env python

import pycparser
import pycparser.c_generator
import pycparser.c_ast as c_ast

import sys

whitelist = {
    "Sint8",
    "Uint8",
    "Sint16",
    "Uint16",
    "Sint32",
    "Uint32",
    "Sint64",
    "Uint64",
    }

blacklist = {
    "SDL_LogMessageV",
    "SDL_vsscanf",
    "SDL_vsnprintf",
    }

# A list of structs to omit, since they'll be followed by ctypedefs with
# the same name.
omit_cdef = {
    "SDL_mutex",
    "SDL_cond",
    "SDL_Thread",
    "SDL_AudioCvt",
    "SDL_SysWMmsg",
    "SDL_Renderer",
    "SDL_Texture",
    "SDL_AudioCVT",
    }

def name_filter(name):
    """
    Returns true if `name` should be included in the .pyx, and False
    otherwise.
    """

    if name in blacklist:
        return False

    if name in whitelist:
        return True

    if name.startswith("SDL_dummy"):
        return False

    if name.startswith("SDL_DUMMY"):
        return False

    if name.startswith("SDL"):
        return True

    return False

def check_name(n):
    """
    Tries to figure out (a) name for node. If the name matches the name
    filter, returns true, otherwise returns false.
    """

    name = getattr(n, "name", None)

    if isinstance(name, basestring):
        return name_filter(name)

    for _, node in n.children():
        if check_name(node):
            return True

    return False


cgen = pycparser.c_generator.CGenerator()

def cython_from_c(n):
    """
    Tries to turn `n` into cython code by textual substitution. This only
    works for nodes that are not
    """

    rv = cgen.visit(n)

    rv = rv.replace("(void)", "()")
    rv = rv.replace("struct ", "")
    rv = rv.replace("[SDL_MESSAGEBOX_COLOR_MAX]", "[5]")

    return rv

anonymous_serial = 0

def anonymous(n):
    global anonymous_serial
    anonymous_serial += 1

    if isinstance(n, c_ast.Union):
        kind = "union"
    elif isinstance(n, c_ast.Struct):
        kind = "struct"
    else:
        raise Exception("unknown node")

    if n.name:
        name = n.name
    else:
        name = "anon"

    return "{}_{}_{}".format(name, kind, anonymous_serial)


class Writer(object):
    def __init__(self, s):
        self.first = s
        self.rest = [ ]

    def add(self, s):
        self.rest.append(s)

    def write(self):
        sys.stdout.write("    " + self.first + "\n")
        for i in self.rest:
            sys.stdout.write("        " + i + "\n")

        sys.stdout.write("\n")

def remove_modifiers(n):
    """
    Removes quals and storage modifiers from `n` and its children.
    """

    for name, node in n.children():
        remove_modifiers(node)

    if hasattr(n, "quals"):
        n.quals = [ ]
    if hasattr(n, "storage"):
        n.storage = [ ]

def reorganize_decl(n):
    """
    Turns nested declarations into anonymous declarations.
    """

    if isinstance(n, (c_ast.Union, c_ast.Struct)):
        name = n.name
        if not name:
            name = anonymous(n)

        if n.decls:
            generate_decl(n, '', name)

        return c_ast.IdentifierType(names=[ name ])

    for name, child in n.children():

        new_child = reorganize_decl(child)

        if new_child is not child:

            if "[" in name:
                field, _, num = name[:-1].partition("[")
                getattr(n, field)[int(num)] = new_child
            else:
                setattr(n, name, new_child)

    return n

def generate_struct_or_union(kind, n, ckind, name):
    """
    Generates a struct or union.
    """

    if name is None:
        name = n.name

    if not ckind:
        ckind = 'cdef '

    if ckind == 'cdef ' and (name in omit_cdef):
        return

    if n.decls:
        w = Writer("{}{} {}:".format(ckind, kind, name))

        for i in n.decls:
            i = reorganize_decl(i)
            w.add(cython_from_c(i))

    else:
        w = Writer("{}{} {}".format(ckind, kind, name))

    w.write()


def generate_decl(n, ckind='', name=None):
    """
    Produces a declaration from `n`.

    `ckind`
        The cython-kind of declaration to produce. Either 'cdef' or 'ctypedef'.

    `name`
        The name of the declaration we're producing, if known.
    """

    if isinstance(n, c_ast.Typedef):
        if name is None:
            name = n.name

        ckind = 'ctypedef '

        n.storage = [ ]
        n.quals = [ ]

        if not generate_decl(n.type, ckind, name):
            w = Writer("{}{}".format(ckind, cython_from_c(n)))
            w.write()

    elif isinstance(n, c_ast.Decl):
        if name is None:
            name = n.name

        n.storage = [ ]

        if not generate_decl(n.type, ckind, name):
            w = Writer("{}{}".format(ckind, cython_from_c(n)))
            w.write()

    elif isinstance(n, c_ast.TypeDecl):

        if name is None:
            name = n.name

        return generate_decl(n.type, ckind, name)

    elif isinstance(n, c_ast.Struct):
        generate_struct_or_union("struct", n, ckind, name)
        return True

    elif isinstance(n, c_ast.Union):
        generate_struct_or_union("union", n, ckind, name)
        return True

    elif isinstance(n, c_ast.Enum):
        if not ckind:
            ckind = 'cdef '

        if not name:
            name = n.name

        if name:
            w = Writer('{}enum {}:'.format(ckind, name))
        else:
            w = Writer('{} enum:'.format(ckind, name))

        for i in n.values.enumerators:
            w.add(i.name)

        w.write()

        return True

    else:
        return False

PREAMBLE = """\
from libc.stdint cimport *
from libc.stdio cimport *
from libc.stddef cimport *

cdef extern from "SDL.h" nogil:

    cdef struct _SDL_iconv_t

    cdef struct SDL_BlitMap

    ctypedef struct SDL_AudioCVT
"""

def main():
    a = pycparser.parse_file("sdl2.i")

    sys.stdout.write(PREAMBLE)

    for n in a.ext:
        # n.show(nodenames=True, attrnames=True)
        if check_name(n):
            remove_modifiers(n)
            generate_decl(n, '')

if __name__ == "__main__":
    main()