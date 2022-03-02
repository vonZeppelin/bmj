import os

from cue_parser import parse_cue_sheet
from hashlib import sha1
from invoke import Exit, task
from itertools import chain, zip_longest
from pathlib import Path
from random import shuffle
from shlex import quote


ALLOWED_TAGS = {
    "album", "artist", "date", "discnumber", "disctotal",
    "genre", "title", "tracknumber", "tracktotal"
}
AUDIO_FILES = {".flac", ".wav"}


def _error(msg, **kwargs): print(f"\033[33m{msg}\033[0m", **kwargs)


def _shq(path): return quote(str(path))


@task(
    help={
        "in-dir": "Root directory to start traversal from"
    }
)
def clean_tags(ctx, in_dir):
    """
    Traverses directories and removes images and
    not allowlisted tags from .flac files.

    Requires metaflac to be installed.
    """

    in_dir = Path(in_dir)

    if not in_dir.is_dir():
        raise Exit(message=f"'{in_dir}' is not valid directory!")

    for cur_dir, _, files in os.walk(in_dir):
        print(f"Scanning '{cur_dir}'...", end="")

        flac_files = [
            f for f in map(Path, files) if f.suffix.lower() == ".flac"
        ]

        if not flac_files:
            print(" No flac files found.")
            continue

        print()
        for cur_file in flac_files:
            print(f"\tFound '{cur_file}', processing...", end=" ")

            cur_file = _shq(cur_dir / cur_file)

            exported_tags = ctx.run(
                f"metaflac --export-tags-to - {cur_file}", hide=True
            )
            exported_tags = {
                kv[0].lower(): kv[1].strip()
                for kv in (
                    t.split("=", 1) for t in exported_tags.stdout.split("\n")
                )
                if len(kv) == 2 and kv[1].strip()
            }

            ctx.run(f"metaflac --dont-use-padding --remove-all {cur_file}")

            new_tags = " ".join(
                f"--set-tag {k}={_shq(v)}"
                for k, v in exported_tags.items()
                if k in ALLOWED_TAGS
            )
            ctx.run(
                f"metaflac --dont-use-padding {new_tags} {cur_file}"
            )

            print("OK.")


@task(
    help={
        "in-dir": "Root directory to start traversal from",
        "out-dir": "Output directory (hierarchy of input dir is preserved)",
        "checksum": "Generate SHA1 checksum file, in sha1deep compatible form"
    }
)
def split_files(ctx, in_dir, out_dir, checksum=False):
    """
    Traverses directories and splits audio files
    into multiple tracks using found cue sheets.

    Requires FFmpeg to be installed.
    """

    def ff_time(idx_time):
        ms = (idx_time.m * 60 + idx_time.s + idx_time.f / 75.0) * 1000
        return f"{ms:.2f}ms"

    def first_index(track):
        return track and next(i.time for i in track.indices if i.num == 1)

    in_dir, out_dir = Path(in_dir), Path(out_dir)

    if not in_dir.is_dir():
        raise Exit(message=f"'{in_dir}' is not valid directory!")
    if out_dir.is_dir() and any(out_dir.iterdir()):
        raise Exit(message=f"'{out_dir}' is not empty directory!")

    hashes = []
    for cur_dir, _, files in os.walk(in_dir):
        print(f"Scanning '{cur_dir}'...", end="")

        cue_files = [
            f for f in map(Path, files) if f.suffix.lower() == ".cue"
        ]

        if not cue_files:
            print(" No cue sheets found.")
            continue

        print()
        for cue_file in cue_files:
            print(f"\tFound '{cue_file}' sheet, parsing...", end=" ")

            cue_file = Path(cur_dir, cue_file)
            cue_sheet = parse_cue_sheet(cue_file)
            if len(cue_sheet.files) > 1:
                _error("Sheet has more than one FILE, skipping!")
                continue

            audio_file = Path(cue_sheet.files[0].path)
            if not audio_file.is_absolute():
                audio_file = Path(cur_dir, audio_file)
            if not audio_file.exists():
                _error(f"FILE '{audio_file}' doesn't exist, skipping!")
                continue

            print("OK.")
            cur_out_dir = out_dir / cue_file.parent.relative_to(in_dir)
            cur_out_dir.mkdir(parents=True)

            tracks = cue_sheet.files[0].tracks
            print(
                f"\tSplitting '{audio_file.name}' into {len(tracks)} tracks...",
                end=" "
            )

            for track, next_track in zip_longest(tracks, tracks[1:]):
                track_start = first_index(track)
                track_end = first_index(next_track)
                track_tags = [
                    ("album", cue_sheet.title),
                    ("artist", cue_sheet.performer),
                    ("date", cue_sheet.date),
                    ("genre", cue_sheet.genre),
                    ("title", track.title),
                    ("tracknumber", track.num),
                    ("tracktotal", len(tracks))
                ]

                out_file_args = f"-map_metadata -1 -ss {ff_time(track_start)}"
                if track_end:
                    out_file_args += f" -to {ff_time(track_end)}"
                for k, v in track_tags:
                    if v:
                        out_file_args += f" -metadata {k}={_shq(v)}"
                out_file = cur_out_dir / f"{track.num:02d}. {track.title}.flac"

                split_result = ctx.run(
                    f"ffmpeg -hide_banner -i {_shq(audio_file)} {out_file_args} {_shq(out_file)}",
                    hide=True, warn=True
                )
                if split_result.ok:
                    if checksum:
                        hasher = sha1()
                        with open(out_file, "rb") as f:
                            while chunk := f.read(8192):
                                hasher.update(chunk)
                        hashes.append(
                            (hasher.hexdigest(), out_file.relative_to(out_dir))
                        )
                    print("*", end="", flush=True)
                else:
                    _error("*", end="", flush=True)

            print(" OK.")

    if hashes:
        with open(out_dir / "checksum.sha1", "w") as f:
            for sha1hash, file in hashes:
                f.write(f"{sha1hash}  {os.curdir}{os.sep}{file}\n")
        print("Checksum file created.")

@task(
    help={
        "in-dir": "Source directories",
        "out-dir": "Output directory",
        "limit": "Limit of files to convert"
    },
    iterable=["in_dir"]
)
def random_tracks(ctx, in_dir, out_dir, limit=100):
    """
    Given a list of directories, traverses directories and converts
    found audio files into MP4 format.

    Requires FFmpeg to be installed.
    """

    def to_valid_dir(d):
        d = Path(d)
        if not d.is_dir():
            raise Exit(message=f"'{d}' is not valid directory!")
        return d

    def find_audio_files(in_dir):
        for cur_dir, _, files in os.walk(in_dir):
            print(f"Scanning '{cur_dir}'...")

            for f in files:
                f = Path(cur_dir, f)
                if f.suffix.lower() in AUDIO_FILES:
                    yield f

    in_dir, out_dir = map(to_valid_dir, in_dir), Path(out_dir)

    if out_dir.is_dir() and any(out_dir.iterdir()):
        raise Exit(message=f"'{out_dir}' is not empty directory!")
    out_dir.mkdir(parents=True)

    audio_files = list(
        chain.from_iterable(
            map(find_audio_files, in_dir)
        )
    )
    shuffle(audio_files)
    audio_files = audio_files[:limit]

    print(
        f"Converting {len(audio_files)} audio files...", end=" "
    )

    convert_args = "-c:a aac_at -q:a 5"

    for idx, audio_file in enumerate(audio_files, start=1):
        out_file = Path(out_dir, f"Track {idx}.m4a")
        convert_result = ctx.run(
            f"ffmpeg -hide_banner -i {_shq(audio_file)} {convert_args} {_shq(out_file)}",
            hide=True, warn=True
        )
        if convert_result.ok:
            print("*", end="", flush=True)
        else:
            _error("*", end="", flush=True)

    print(" OK.")
