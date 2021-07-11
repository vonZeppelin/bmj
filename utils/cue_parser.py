from arpeggio import *
from collections import namedtuple
from functools import partial


def quoted_string(): return RegExMatch(r"(['\"]).*\1")

def number(): return RegExMatch(r"\d{1,3}")

def word(): return RegExMatch(r"\S+")

def text(): return [quoted_string, word]

def time(): return number, ":", number, ":", number

def cdtext(): return (
    [
        "ARRANGER", "CATALOG", "COMPOSER", "DISC_ID", "GENRE", "ISRC",
        "MESSAGE", "PERFORMER", "SIZE_INFO", "SONGWRITER",
        "TITLE", "TOC_INFO1", "TOC_INFO2", "UPC_EAN"
    ],
    text
)

def rem(): return (
    "REM",
    Optional(
        [
            "COMMENT", "DATE", "DISCID", "DISCNUMBER", "GENRE",
            "REPLAYGAIN_ALBUM_GAIN", "REPLAYGAIN_ALBUM_PEAK",
            "REPLAYGAIN_TRACK_GAIN", "REPLAYGAIN_TRACK_PEAK",
            "TOTALDISCS"
        ]
    ),
    OneOrMore(text, eolterm=True)
)

def track_index(): return "INDEX", number, time

def track(): return (
    ("TRACK", number, word),
    OneOrMore(
        [
            cdtext,
            rem,
            track_index,
            ("FLAGS", OneOrMore(word, eolterm=True)),
            ("POSTGAP", time),
            ("PREGAP", time),
            ("TRACK_ISRC", word)
        ]
    )
)

def file_statement(): return ("FILE", text, word), OneOrMore(track)

def global_statement(): return [cdtext, rem, ("CDTEXTFILE", text)]

def cue_file(): return (
    ZeroOrMore(global_statement), OneOrMore(file_statement), EOF
)

cue_parser = ParserPython(cue_file)


_NamedValue = namedtuple("_NamedValue", "name value")

Time = namedtuple("Time", "m s f")
Index = namedtuple("Index", "num time")
Track = namedtuple("Track", "num title indices")
File = namedtuple("File", "path tracks")
CueSheet = namedtuple(
    "CueSheet", "title performer date genre files"
)

class _CueSheetVisitor(PTNodeVisitor):
    unescape_quotes = partial(re.compile(r"\\(['\"])").sub, r"\1")

    def visit_quoted_string(self, node, children):
        return _CueSheetVisitor.unescape_quotes(str(node)[1:-1])

    def visit_number(self, node, children):
        return int(str(node))

    def visit_time(self, node, children):
        return Time(*children)

    def visit_cdtext(self, node, children):
        return _NamedValue(*children)

    def visit_rem(self, node, children):
        first, *rest = children
        if rest:
            return _NamedValue(first, " ".join(rest))
        else:
            return _NamedValue("COMMENT", first)

    def visit_track_index(self, node, children):
        return Index(*children)

    def visit_track(self, node, children):
        return Track(
            num=children[0],
            title=next(
                (v for k, v in children.cdtext if k == "TITLE"),
                "Unknown"
            ),
            indices=children.track_index
        )

    def visit_file_statement(self, node, children):
        path, _, *tracks = children
        return File(path, tracks)

    def visit_cue_file(self, node, children):
        date = None
        genre = None
        performer = "Unknown"
        title = "Unknown"

        for name, value in children.global_statement:
            if name == "DATE":
                date = value
            elif name == "GENRE":
                genre = value
            elif name == "PERFORMER":
                performer = value
            elif name == "TITLE":
                title = value

        return CueSheet(
            title, performer, date, genre, children.file_statement
        )


def parse_cue_sheet(file_name):
    return visit_parse_tree(
        cue_parser.parse_file(file_name),
        _CueSheetVisitor()
    )
