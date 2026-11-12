#!/usr/bin/env python3
"""Dump the .proto files compiled into the game's binaries.

Every protoc-generated C++ file embeds its FileDescriptorProto, serialized, so the
binaries carry the full definition of every message they use. This finds those
descriptors and writes them back out as .proto text, in the same layout
SteamDatabase/GameTracking-CS2 publishes (SteamKit's ProtobufDumper), so the SDK can
be refreshed straight from a build without waiting for anyone else's dump.

    ./dump_protos.py -o <outdir> <binary> [<binary> ...]

Standard library only. The descriptors are decoded by hand rather than with the
protobuf package, because Valve's descriptor.proto differs from Google's (FieldOptions
20 and 21 are boxed_type and synthetic_default, where Google's 20 is a message), and a
stock parser rejects every field that uses them. Options are decoded with the
binary's own descriptor.proto, the way ProtobufDumper does.
"""

import argparse
import os
import re
import struct
import sys

# --- wire format -----------------------------------------------------------------


class WireError(Exception):
    pass


def read_varint(data, i):
    result = 0
    shift = 0
    while True:
        if i >= len(data):
            raise WireError("truncated varint")
        b = data[i]
        i += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, i
        shift += 7
        if shift >= 70:
            raise WireError("varint too long")


def iter_fields(data):
    """Yields (number, wire_type, value) for one message. value is an int for varints
    and fixed fields, bytes for length-delimited ones."""
    i = 0
    n = len(data)
    while i < n:
        key, i = read_varint(data, i)
        number, wt = key >> 3, key & 7
        if number == 0:
            raise WireError("field number 0")
        if wt == 0:
            value, i = read_varint(data, i)
        elif wt == 1:
            if i + 8 > n:
                raise WireError("truncated fixed64")
            value = int.from_bytes(data[i:i + 8], "little")
            i += 8
        elif wt == 2:
            length, i = read_varint(data, i)
            if i + length > n:
                raise WireError("truncated length-delimited field")
            value = data[i:i + length]
            i += length
        elif wt == 5:
            if i + 4 > n:
                raise WireError("truncated fixed32")
            value = int.from_bytes(data[i:i + 4], "little")
            i += 4
        else:
            raise WireError(f"unsupported wire type {wt}")
        yield number, wt, value


def consume_one_message(data, start):
    """Length of the FileDescriptorProto starting at data[start]: up to a field
    number 0, a second field 1 (the next file's name) or the first unreadable field."""
    i = start
    seen_name = False
    n = len(data)
    while i < n:
        before = i
        try:
            key, i = read_varint(data, i)
            number, wt = key >> 3, key & 7
            if number == 0:
                return before - start
            if number == 1:
                if seen_name:
                    return before - start
                seen_name = True
            if wt == 0:
                _, i = read_varint(data, i)
            elif wt == 1:
                i += 8
            elif wt == 2:
                length, i = read_varint(data, i)
                i += length
            elif wt == 5:
                i += 4
            else:
                return before - start
            if i > n:
                return before - start
        except WireError:
            return before - start
    return i - start


def to_int32(v):
    v &= 0xFFFFFFFFFFFFFFFF
    v &= 0xFFFFFFFF
    return v - (1 << 32) if v & 0x80000000 else v


def to_int64(v):
    v &= 0xFFFFFFFFFFFFFFFF
    return v - (1 << 64) if v & (1 << 63) else v


# --- descriptor model --------------------------------------------------------------
# Only the structure is decoded here. Options stay raw (a list of wire fields) and are
# interpreted later against the binary's own descriptor.proto.


class Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def parse_options(data):
    return list(iter_fields(data))


def parse_field(data):
    f = Obj(name="", number=0, label=1, type=0, type_name="", extendee="", default_value=None,
            oneof_index=None, json_name=None, options=None, proto3_optional=False)
    for num, wt, v in iter_fields(data):
        if num == 1: f.name = v.decode()
        elif num == 2: f.extendee = v.decode()
        elif num == 3: f.number = to_int32(v)
        elif num == 4: f.label = v
        elif num == 5: f.type = v
        elif num == 6: f.type_name = v.decode()
        elif num == 7: f.default_value = v.decode("utf-8", "surrogateescape")
        elif num == 8: f.options = parse_options(v)
        elif num == 9: f.oneof_index = to_int32(v)
        elif num == 10: f.json_name = v.decode()
        elif num == 17: f.proto3_optional = bool(v)
    return f


def parse_enum(data):
    e = Obj(name="", value=[], options=None, reserved_range=[], reserved_name=[])
    for num, wt, v in iter_fields(data):
        if num == 1: e.name = v.decode()
        elif num == 2:
            ev = Obj(name="", number=0, options=None)
            for n2, _, v2 in iter_fields(v):
                if n2 == 1: ev.name = v2.decode()
                elif n2 == 2: ev.number = to_int32(v2)
                elif n2 == 3: ev.options = parse_options(v2)
            e.value.append(ev)
        elif num == 3: e.options = parse_options(v)
        elif num == 4: e.reserved_range.append(parse_range(v))
        elif num == 5: e.reserved_name.append(v.decode())
    return e


def parse_range(data):
    r = Obj(start=0, end=0, options=None)
    for num, _, v in iter_fields(data):
        if num == 1: r.start = to_int32(v)
        elif num == 2: r.end = to_int32(v)
        elif num == 3: r.options = parse_options(v)
    return r


def parse_message(data):
    m = Obj(name="", field=[], extension=[], nested_type=[], enum_type=[], extension_range=[],
            oneof_decl=[], options=None, reserved_range=[], reserved_name=[])
    for num, wt, v in iter_fields(data):
        if num == 1: m.name = v.decode()
        elif num == 2: m.field.append(parse_field(v))
        elif num == 3: m.nested_type.append(parse_message(v))
        elif num == 4: m.enum_type.append(parse_enum(v))
        elif num == 5: m.extension_range.append(parse_range(v))
        elif num == 6: m.extension.append(parse_field(v))
        elif num == 7: m.options = parse_options(v)
        elif num == 8:
            o = Obj(name="", options=None)
            for n2, _, v2 in iter_fields(v):
                if n2 == 1: o.name = v2.decode()
                elif n2 == 2: o.options = parse_options(v2)
            m.oneof_decl.append(o)
        elif num == 9: m.reserved_range.append(parse_range(v))
        elif num == 10: m.reserved_name.append(v.decode())
    return m


def parse_service(data):
    s = Obj(name="", method=[], options=None)
    for num, _, v in iter_fields(data):
        if num == 1: s.name = v.decode()
        elif num == 2:
            mt = Obj(name="", input_type="", output_type="", options=None,
                     client_streaming=False, server_streaming=False)
            for n2, _, v2 in iter_fields(v):
                if n2 == 1: mt.name = v2.decode()
                elif n2 == 2: mt.input_type = v2.decode()
                elif n2 == 3: mt.output_type = v2.decode()
                elif n2 == 4: mt.options = parse_options(v2)
                elif n2 == 5: mt.client_streaming = bool(v2)
                elif n2 == 6: mt.server_streaming = bool(v2)
            s.method.append(mt)
        elif num == 3: s.options = parse_options(v)
    return s


def parse_file(data):
    p = Obj(name="", package="", dependency=[], public_dependency=[], weak_dependency=[],
            message_type=[], enum_type=[], service=[], extension=[], options=None, syntax="")
    for num, wt, v in iter_fields(data):
        if num == 1: p.name = v.decode()
        elif num == 2: p.package = v.decode()
        elif num == 3: p.dependency.append(v.decode())
        elif num == 4: p.message_type.append(parse_message(v))
        elif num == 5: p.enum_type.append(parse_enum(v))
        elif num == 6: p.service.append(parse_service(v))
        elif num == 7: p.extension.append(parse_field(v))
        elif num == 8: p.options = parse_options(v)
        elif num == 10:
            p.public_dependency.extend(packed_ints(v) if wt == 2 else [v])
        elif num == 11:
            p.weak_dependency.extend(packed_ints(v) if wt == 2 else [v])
        elif num == 12: p.syntax = v.decode()
    if not p.name.endswith(".proto"):
        raise WireError("not a file descriptor")
    return p


def packed_ints(data):
    out, i = [], 0
    while i < len(data):
        v, i = read_varint(data, i)
        out.append(v)
    return out


# --- scanning ----------------------------------------------------------------------

NAME_RE = re.compile(r"^[a-zA-Z_0-9\\/.-]+\.proto$")


CANDIDATE_RE = re.compile(rb"[a-zA-Z_0-9\\/.-]+\.[pP][rR][oO][tT][oO]")


def candidates(data):
    """Offsets of a 0x0A tag followed by a varint length and that many bytes of a
    .proto file name: the start of a serialized FileDescriptorProto."""
    for m in CANDIDATE_RE.finditer(data):
        end = m.end()
        for start in range(m.start(), end - 6):
            length = end - start
            if length < 128:
                if start >= 2 and data[start - 2] == 0x0A and data[start - 1] == length:
                    yield start - 2, data[start:end]
            elif start >= 3 and data[start - 3] == 0x0A and data[start - 2] == (length & 0x7F) | 0x80 \
                    and data[start - 1] == length >> 7:
                yield start - 3, data[start:end]


def scan(path, found, sources):
    data = open(path, "rb").read()
    consumed_to = 0
    for offset, name_bytes in candidates(data):
        if offset < consumed_to:
            continue
        if not NAME_RE.match(name_bytes.decode("ascii")):
            continue
        size = consume_one_message(data, offset)
        blob = data[offset:offset + size]
        try:
            proto = parse_file(blob)
        except (WireError, UnicodeDecodeError):
            continue
        consumed_to = offset + size
        if proto.name in found:
            if found[proto.name][1] != blob:
                print(f"warning: {proto.name} in {path} differs from the copy in {sources[proto.name]}, keeping the first",
                      file=sys.stderr)
        else:
            found[proto.name] = (proto, blob)
            sources[proto.name] = path


# --- dumping -----------------------------------------------------------------------

TYPE_NAMES = {1: "double", 2: "float", 3: "int64", 4: "uint64", 5: "int32", 6: "fixed64", 7: "fixed32",
              8: "bool", 9: "string", 10: "GROUP", 11: "message", 12: "bytes", 13: "uint32", 14: "enum",
              15: "sfixed32", 16: "sfixed64", 17: "sint32", 18: "sint64"}
TYPE_MESSAGE, TYPE_ENUM, TYPE_STRING, TYPE_BYTES = 11, 14, 9, 12
LABEL_OPTIONAL, LABEL_REQUIRED, LABEL_REPEATED = 1, 2, 3
MAX_FIELD_NUMBER = 536870911
INT_MAX = 2147483647

# The options SteamKit's compiled descriptor.proto knows, in the order ProtobufDumper
# writes them. (number, name, kind) where kind says how the value prints. Options in
# the binary's descriptor.proto but not here (Valve's additions) are written after
# these, in the binary's order; options known here never appear a second time.
ENUM_VALUES = {
    "optimize_for": {1: "SPEED", 2: "CODE_SIZE", 3: "LITE_RUNTIME"},
    "ctype": {0: "STRING", 1: "CORD", 2: "STRING_PIECE"},
    "jstype": {0: "JS_NORMAL", 1: "JS_STRING", 2: "JS_NUMBER"},
    "idempotency_level": {0: "IDEMPOTENCY_UNKNOWN", 1: "NO_SIDE_EFFECTS", 2: "IDEMPOTENT"},
}
BUILTIN_OPTIONS = {
    "FileOptions": ([(23, "deprecated", "bool"), (9, "optimize_for", "enum"), (16, "cc_generic_services", "bool"),
                     (31, "cc_enable_arenas", "bool"), (11, "go_package", "string"), (1, "java_package", "string"),
                     (8, "java_outer_classname", "string"), (20, "java_generate_equals_and_hash", "bool"),
                     (17, "java_generic_services", "bool"), (10, "java_multiple_files", "bool"),
                     (27, "java_string_check_utf8", "bool"), (18, "py_generic_services", "bool"),
                     (45, "ruby_package", "string"), (36, "objc_class_prefix", "string"),
                     (37, "csharp_namespace", "string"), (39, "swift_prefix", "string"),
                     (42, "php_generic_services", "bool"), (40, "php_class_prefix", "string"),
                     (41, "php_namespace", "string"), (44, "php_metadata_namespace", "string")], set()),
    "FieldOptions": ([(1, "ctype", "enum"), (3, "deprecated", "bool"), (5, "lazy", "bool"), (2, "packed", "bool"),
                      (10, "weak", "bool"), (6, "jstype", "enum")], set()),
    "MessageOptions": ([(1, "message_set_wire_format", "bool"), (2, "no_standard_descriptor_accessor", "bool"),
                        (3, "deprecated", "bool")], {7}),
    "EnumOptions": ([(2, "allow_alias", "bool"), (3, "deprecated", "bool")], set()),
    "EnumValueOptions": ([(1, "deprecated", "bool")], set()),
    "ServiceOptions": ([(33, "deprecated", "bool")], set()),
    "MethodOptions": ([(33, "deprecated", "bool"), (34, "idempotency_level", "enum")], set()),
    "OneofOptions": ([], set()),
    "ExtensionRangeOptions": ([], set()),
}


def literal(s):
    out = ['"']
    for c in s:
        o = ord(c)
        if c == "\a": out.append("\\a")
        elif c == "\b": out.append("\\b")
        elif c == "\f": out.append("\\f")
        elif c == "\n": out.append("\\n")
        elif c == "\r": out.append("\\r")
        elif c == "\t": out.append("\\t")
        elif c == "\v": out.append("\\v")
        elif c == "\\": out.append("\\\\")
        elif c == '"': out.append('\\"')
        elif o < 0x20 or o == 0x7F: out.append("\\" + format(o, "o").zfill(3))
        else: out.append(c)
    out.append('"')
    return "".join(out)


def literal_bytes(b):
    out = ['"']
    for x in b:
        if x in (0x5C, 0x22):
            out.append("\\" + chr(x))
        elif x < 0x20 or x >= 0x7F:
            out.append("\\" + format(x, "o").zfill(3))
        else:
            out.append(chr(x))
    out.append('"')
    return "".join(out)


def float_literal(v, single):
    if v != v: return "nan"
    if v == float("inf"): return "inf"
    if v == float("-inf"): return "-inf"
    if single:
        # shortest text that reads back as the same float, like .NET's float ToString()
        for digits in range(1, 10):
            s = f"{v:.{digits}g}"
            if struct.unpack("<f", struct.pack("<f", float(s)))[0] == v:
                break
    else:
        s = repr(v)
    if "e" in s:
        mant, exp = s.split("e")
        sign = "-" if exp.startswith("-") else "+"
        s = f"{mant}E{sign}{exp.lstrip('+-').zfill(2)}"
    if s.endswith(".0"):
        s = s[:-2]
    return s


def package_path(package, name):
    package = package if not package or package.startswith(".") else "." + package
    return name if name.startswith(".") else f"{package}.{name}"


class Dumper:
    def __init__(self, files):
        self.files = files                       # list of Obj, scan order
        self.by_name = {f.name: f for f in files}
        self.types = {}                          # full name -> (file, Obj), insertion order = ProtobufDumper's
        for f in files:
            for ext in f.extension:
                self.types.setdefault(package_path(f.package, ext.name), (f, ext))
            for e in f.enum_type:
                self.types.setdefault(package_path(f.package, e.name), (f, e))
            for m in f.message_type:
                self._analyze(f, m, f.package)
        self.public_deps = {f.name: self._all_public(f) for f in files}

    def _analyze(self, f, m, path):
        full = package_path(path, m.name)
        self.types.setdefault(full, (f, m))
        for ext in m.extension:
            self.types.setdefault(package_path(full, ext.name), (f, ext))
        for e in m.enum_type:
            self.types.setdefault(package_path(full, e.name), (f, e))
        for n in m.nested_type:
            self._analyze(f, n, full)

    def _all_public(self, f):
        out = []
        def add(node, depth):
            deps = node.dependency if depth == 0 else [node.dependency[i] for i in node.public_dependency]
            for d in deps:
                dep = self.by_name.get(d)
                if dep is None:
                    continue
                if dep not in out:
                    out.append(dep)
                add(dep, depth + 1)
        add(f, 0)
        return out

    def lookup(self, name):
        hit = self.types.get(name)
        return hit[1] if hit else None

    # options

    def option_values(self, raw, field):
        """The printed values of one option field in a raw options list."""
        vals = [(wt, v) for num, wt, v in raw if num == field.number]
        out = []
        for wt, v in vals:
            t = field.type
            if wt == 2 and t not in (TYPE_STRING, TYPE_BYTES, TYPE_MESSAGE):
                # packed repeated scalars
                items = []
                i = 0
                while i < len(v):
                    if t in (6, 16, 1):
                        items.append(int.from_bytes(v[i:i + 8], "little")); i += 8
                    elif t in (7, 15, 2):
                        items.append(int.from_bytes(v[i:i + 4], "little")); i += 4
                    else:
                        x, i = read_varint(v, i); items.append(x)
                for x in items:
                    out.append(self.scalar(field, x))
                continue
            if t == TYPE_MESSAGE:
                msg = self.lookup(field.type_name)
                out.append(self.aggregate(msg, list(iter_fields(v))))
            elif t == TYPE_STRING:
                out.append(literal(v.decode("utf-8", "replace")))
            elif t == TYPE_BYTES:
                out.append(literal_bytes(v))
            else:
                out.append(self.scalar(field, v))
        if field.label != LABEL_REPEATED and len(out) > 1:
            out = out[-1:]
        return out

    def scalar(self, field, v):
        t = field.type
        if t == 5: return str(to_int32(v))
        if t == 17:
            v &= 0xFFFFFFFF
            return str((v >> 1) ^ -(v & 1))
        if t == 15: return str(to_int32(v))
        if t in (13, 7): return str(v & 0xFFFFFFFF)
        if t == 3: return str(to_int64(v))
        if t == 18:
            v &= 0xFFFFFFFFFFFFFFFF
            return str((v >> 1) ^ -(v & 1))
        if t == 16: return str(to_int64(v))
        if t in (4, 6): return str(v & 0xFFFFFFFFFFFFFFFF)
        if t == 8: return "true" if v else "false"
        if t == 2: return float_literal(struct.unpack("<f", struct.pack("<I", v & 0xFFFFFFFF))[0], True)
        if t == 1: return float_literal(struct.unpack("<d", struct.pack("<Q", v & 0xFFFFFFFFFFFFFFFF))[0], False)
        if t == TYPE_ENUM:
            enum = self.lookup(field.type_name)
            number = to_int32(v)
            for ev in (enum.value if enum else []):
                if ev.number == number:
                    return ev.name
            return str(number)
        return str(v)

    def aggregate(self, msg, raw):
        parts = []
        for sub in msg.field:
            for value in self.option_values(raw, sub):
                parts.append(f"{sub.name} {value}" if sub.type == TYPE_MESSAGE else f"{sub.name}: {value}")
        return "{}" if not parts else "{ " + " ".join(parts) + " }"

    def field_recursive(self, field, raw, out, key):
        if field.type == TYPE_MESSAGE and field.label != LABEL_REPEATED:
            chunks = [v for num, wt, v in raw if num == field.number and wt == 2]
            if not chunks:
                return
            sub_raw = []
            for c in chunks:
                sub_raw.extend(iter_fields(c))
            count = len(out)
            for sub in self.lookup(field.type_name).field:
                self.field_recursive(sub, sub_raw, out, f"{key}.{sub.name}")
            if len(out) == count:
                out.append((key, "{}"))
            return
        for value in self.option_values(raw, field):
            out.append((key, value))

    def dump_options(self, source, kind, raw):
        out = []
        if raw is None:
            return out
        builtin, hidden = BUILTIN_OPTIONS[kind]
        known = {num for num, _, _ in builtin} | hidden | {999}
        for num, name, how in builtin:
            vals = [v for n, wt, v in raw if n == num]
            if not vals:
                continue
            v = vals[-1]
            if how == "bool": out.append((name, "true" if v else "false"))
            elif how == "enum": out.append((name, ENUM_VALUES[name].get(v, str(v))))
            else: out.append((name, literal(v.decode("utf-8", "replace"))))

        deps = self.public_deps[source.name] + [source]
        type_name = ".google.protobuf." + kind
        hit = self.types.get(type_name)
        if hit is not None and hasattr(hit[1], "field"):
            opt_file, opt_msg = hit
            count = len(out)
            for field in opt_msg.field:
                if field.name == "uninterpreted_option" or field.number in known:
                    continue
                self.field_recursive(field, raw, out, field.name)
            if len(out) > count and opt_file not in deps:
                self.option_imports.add(opt_file.name)

        for full, (f, obj) in self.types.items():
            if f in deps and hasattr(obj, "extendee") and obj.extendee == type_name:
                self.field_recursive(obj, raw, out, f"({full.lstrip('.')})")
        return out

    # declarations

    def resolve_type(self, field):
        if field.type in (TYPE_MESSAGE, TYPE_ENUM):
            return field.type_name
        return TYPE_NAMES.get(field.type, str(field.type))

    def declaration(self, source, field, emit_label=True):
        opts = []
        proto2 = not source.syntax or source.syntax == "proto2"
        if field.default_value is not None:
            d = field.default_value
            if field.type == TYPE_STRING:
                d = literal(d)
            elif field.type == TYPE_BYTES:
                d = f'"{d}"'
            opts.append(("default", d))
        elif proto2 and field.type == TYPE_ENUM and field.label != LABEL_REPEATED:
            enum = self.lookup(field.type_name)
            if enum is not None and hasattr(enum, "value") and enum.value:
                opts.append(("default", enum.value[0].name))
        if field.json_name:
            opts.append(("json_name", literal(field.json_name)))
        opts.extend(self.dump_options(source, "FieldOptions", field.options))
        params = " [" + ", ".join(f"{k} = {v}" for k, v in opts) + "]" if opts else ""

        typ = self.resolve_type(field)
        label = None
        entry = self.lookup(field.type_name) if field.type == TYPE_MESSAGE else None
        if field.label == LABEL_REPEATED and entry is not None and self.is_map_entry(entry):
            key = next(x for x in entry.field if x.number == 1)
            val = next(x for x in entry.field if x.number == 2)
            typ = f"map<{self.resolve_type(key)}, {self.resolve_type(val)}>"
        elif emit_label:
            if proto2 or field.label == LABEL_REPEATED or field.proto3_optional:
                label = {LABEL_REQUIRED: "required", LABEL_REPEATED: "repeated"}.get(field.label, "optional")
        text = f"{typ} {field.name} = {field.number}{params};"
        return f"{label} {text}" if label else text

    @staticmethod
    def is_map_entry(msg):
        return bool(msg.options) and any(n == 7 and v for n, wt, v in msg.options)

    def dump_file(self, proto):
        lines = []
        self.option_imports = set()
        marker = [False]

        def heading(m=marker):
            if m[0]:
                lines.append("")
                m[0] = False

        if proto.syntax:
            heading()
            lines.append(f"syntax = {literal(proto.syntax)};")
            marker[0] = True
        for i, dep in enumerate(proto.dependency):
            mod = "public " if i in proto.public_dependency else "weak " if i in proto.weak_dependency else ""
            lines.append(f'import {mod}"{dep}";')
            marker[0] = True
        imports_end = len(lines)
        has_heading = marker[0]
        if proto.package:
            heading()
            lines.append(f"package {proto.package};")
            marker[0] = True
        opts = self.dump_options(proto, "FileOptions", proto.options)
        for k, v in opts:
            heading()
            lines.append(f"option {k} = {v};")
        if opts:
            marker[0] = True
        self.dump_extensions(proto, proto.extension, lines, 0, marker)
        for e in proto.enum_type:
            self.dump_enum(proto, e, lines, 0, marker)
        for m in proto.message_type:
            self.dump_message(proto, m, lines, 0, marker)
        for s in proto.service:
            self.dump_service(proto, s, lines, marker)

        if self.option_imports:
            extra = [f'import "{name}";' for name in sorted(self.option_imports)]
            if not has_heading and imports_end < len(lines):
                extra.append("")
            lines[imports_end:imports_end] = extra
        return "".join(line + "\n" for line in lines)

    def dump_extensions(self, source, fields, lines, level, marker):
        ind = "\t" * level
        groups = {}
        for f in fields:
            groups.setdefault(f.extendee, []).append(f)
        for extendee, group in groups.items():
            if marker[0]:
                lines.append(""); marker[0] = False
            lines.append(f"{ind}extend {extendee} {{")
            for f in group:
                lines.append(f"{ind}\t{self.declaration(source, f)}")
            lines.append(f"{ind}}}")
            marker[0] = True

    def dump_message(self, source, msg, lines, level, marker):
        ind = "\t" * level
        inner = [False]
        if marker[0]:
            lines.append(""); marker[0] = False
        lines.append(f"{ind}message {msg.name} {{")
        opts = self.dump_options(source, "MessageOptions", msg.options)
        for k, v in opts:
            if inner[0]:
                lines.append(""); inner[0] = False
            lines.append(f"{ind}\toption {k} = {v};")
        if opts:
            inner[0] = True
        if msg.extension:
            self.dump_extensions(source, msg.extension, lines, level + 1, inner)
        for n in msg.nested_type:
            if not self.is_map_entry(n):
                self.dump_message(source, n, lines, level + 1, inner)
        for e in msg.enum_type:
            self.dump_enum(source, e, lines, level + 1, inner)
        roots = [f for f in msg.field if f.oneof_index is None or f.proto3_optional]
        for f in roots:
            if inner[0]:
                lines.append(""); inner[0] = False
            lines.append(f"{ind}\t{self.declaration(source, f)}")
        if roots:
            inner[0] = True
        for i, oneof in enumerate(msg.oneof_decl):
            fields = [f for f in msg.field if f.oneof_index == i]
            if any(f.proto3_optional for f in fields):
                continue
            if inner[0]:
                lines.append(""); inner[0] = False
            lines.append(f"{ind}\toneof {oneof.name} {{")
            for k, v in self.dump_options(source, "OneofOptions", oneof.options):
                lines.append(f"{ind}\t\toption {k} = {v};")
            for f in fields:
                lines.append(f"{ind}\t\t{self.declaration(source, f, emit_label=False)}")
            lines.append(f"{ind}\t}}")
            inner[0] = True
        for r in msg.extension_range:
            if inner[0]:
                lines.append(""); inner[0] = False
            ropts = self.dump_options(source, "ExtensionRangeOptions", r.options)
            params = " [" + ", ".join(f"{k} = {v}" for k, v in ropts) + "]" if ropts else ""
            lines.append(f"{ind}\textensions {fmt_range(r.start, r.end - 1, MAX_FIELD_NUMBER)}{params};")
        self.dump_reserved([fmt_range(r.start, r.end - 1, MAX_FIELD_NUMBER) for r in msg.reserved_range],
                           msg.reserved_name, lines, ind, inner)
        lines.append(f"{ind}}}")
        marker[0] = True

    def dump_enum(self, source, enum, lines, level, marker):
        ind = "\t" * level
        if marker[0]:
            lines.append(""); marker[0] = False
        lines.append(f"{ind}enum {enum.name} {{")
        for k, v in self.dump_options(source, "EnumOptions", enum.options):
            lines.append(f"{ind}\toption {k} = {v};")
        for ev in enum.value:
            opts = self.dump_options(source, "EnumValueOptions", ev.options)
            params = " [" + ", ".join(f"{k} = {v}" for k, v in opts) + "]" if opts else ""
            lines.append(f"{ind}\t{ev.name} = {ev.number}{params};")
        inner = [False]
        self.dump_reserved([fmt_range(r.start, r.end, INT_MAX) for r in enum.reserved_range],
                           enum.reserved_name, lines, ind, inner)
        lines.append(f"{ind}}}")
        marker[0] = True

    @staticmethod
    def dump_reserved(ranges, names, lines, ind, marker):
        if ranges:
            if marker[0]:
                lines.append(""); marker[0] = False
            lines.append(f"{ind}\treserved {', '.join(ranges)};")
        if names:
            if marker[0]:
                lines.append(""); marker[0] = False
            lines.append(f"{ind}\treserved {', '.join(literal(n) for n in names)};")

    def dump_service(self, source, service, lines, marker):
        inner = [False]
        if marker[0]:
            lines.append(""); marker[0] = False
        lines.append(f"service {service.name} {{")
        root = self.dump_options(source, "ServiceOptions", service.options)
        for k, v in root:
            lines.append(f"\toption {k} = {v};")
        if root:
            inner[0] = True
        for m in service.method:
            decl = (f"\trpc {m.name} ({'stream ' if m.client_streaming else ''}{m.input_type}) returns "
                    f"({'stream ' if m.server_streaming else ''}{m.output_type})")
            opts = self.dump_options(source, "MethodOptions", m.options)
            if inner[0]:
                lines.append(""); inner[0] = False
            if not opts:
                lines.append(decl + ";")
            else:
                lines.append(decl + " {")
                for k, v in opts:
                    lines.append(f"\t\toption {k} = {v};")
                lines.append("\t}")
                inner[0] = True
        lines.append("}")
        marker[0] = True


def fmt_range(start, end, maximum):
    if start == end:
        return str(start)
    return f"{start} to max" if end >= maximum else f"{start} to {end}"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("-o", "--output", required=True, help="directory to write the .proto files to")
    ap.add_argument("binaries", nargs="+")
    args = ap.parse_args()

    found, sources = {}, {}
    for path in args.binaries:
        scan(path, found, sources)
    if not found:
        sys.exit("no descriptors found")
    dumper = Dumper([proto for proto, _ in found.values()])
    for proto, _ in found.values():
        target = os.path.join(args.output, proto.name)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(dumper.dump_file(proto))
    print(f"{len(found)} files from {len(args.binaries)} binaries")


if __name__ == "__main__":
    main()
