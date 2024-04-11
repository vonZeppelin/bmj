import csv
import os
import tempfile

from cue_parser import parse_cue_sheet
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
        "out-dir": "Output directory (hierarchy of input dir is preserved)"
    }
)
def split_files(ctx, in_dir, out_dir):
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
                track_tags = {
                    "album": cue_sheet.title,
                    "artist": cue_sheet.performer,
                    "date": cue_sheet.date,
                    "genre": cue_sheet.genre,
                    "title": track.title,
                    "tracknumber": track.num,
                    "tracktotal": len(tracks)
                }

                out_file_args = f"-map_metadata -1 -ss {ff_time(track_start)}"
                if track_end:
                    out_file_args += f" -to {ff_time(track_end)}"
                for k, v in track_tags.items():
                    if v:
                        out_file_args += f" -metadata {k}={_shq(v)}"
                out_file = cur_out_dir / f"{track.num:02d}. {track.title}.flac"

                split_result = ctx.run(
                    f"ffmpeg -hide_banner -i {_shq(audio_file)} {out_file_args} {_shq(out_file)}",
                    hide=True, warn=True
                )
                if split_result.ok:
                    print("*", end="", flush=True)
                else:
                    _error("*", end="", flush=True)

            print(" OK.")


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
    found audio files into MP3 format.

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

    convert_args = "-codec:a libmp3lame -q:a 0"

    for idx, audio_file in enumerate(audio_files, start=1):
        out_file = out_dir / f"Track {idx}.mp3"
        convert_result = ctx.run(
            f"ffmpeg -hide_banner -i {_shq(audio_file)} {convert_args} {_shq(out_file)}",
            hide=True, warn=True
        )
        if convert_result.ok:
            print("*", end="", flush=True)
        else:
            _error("*", end="", flush=True)

    print(" OK.")


@task(
    help={
        "youtube-url": "YouTube URL",
        "tracks-info": "CSV file with tracks data",
        "blank": "Blank media before burning"
    }
)
def burn_youtube(ctx, youtube_url, tracks_info, blank=False):
    """
    Burns Audio CD from a YouTube video.

    Requires FFmpeg and yt-dlp to be installed.
    """

    def index_time(time):
        sec = 0
        for part in time.split(":", maxsplit=2):
            sec = sec * 60 + int(part, 10)
        return f"{(sec // 60):02d}:{(sec % 60):02d}:00"

    tracks_info = Path(tracks_info)

    if not tracks_info.is_file():
        raise Exit(message=f"'{tracks_info}' is not valid tracks info file!")

    with tempfile.TemporaryDirectory() as tmp_dir:
        print(f"Working directory is {tmp_dir}")
        with ctx.cd(tmp_dir):
            ctx.run(
                f"yt-dlp --format bestaudio --output audiotrack {_shq(youtube_url)}"
            )
            ctx.run(
                f"ffmpeg -hide_banner -i audiotrack -codec:a pcm_s16le -ar 44100 -ac 2 audiotrack.wav"
            )

            cue_file = [
                "TITLE Youtube",
                "PERFORMER Various",
                "FILE audiotrack.wav WAVE"
            ]
            with open(tracks_info) as tracks_file:
                for track in (tracks := csv.DictReader(tracks_file)):
                    cue_file.append(f"  TRACK {(tracks.line_num - 1):02d} AUDIO")
                    cue_file.append(f"    TITLE \"{track['Track']}\"")
                    cue_file.append(f"    PERFORMER \"{track['Artist']}\"")
                    cue_file.append(f"    INDEX 01 {index_time(track['Time'])}")
            Path(tmp_dir, "audiotrack.cue").write_text("\n".join(cue_file))
            if blank:
                ctx.run("cdrecord blank=fast")
            ctx.run("cdrecord -audio -dao -pad -text cuefile=audiotrack.cue")
