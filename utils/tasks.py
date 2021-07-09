import os

from concurrent.futures import ThreadPoolExecutor, wait
from cue_parser import parse_cue_sheet
from ffmpy import FFmpeg
from invoke import Exit, task
from itertools import zip_longest
from pathlib import Path


def _error(msg): print(f"\033[33m{msg}\033[0m")


def _ff_time(idx_time):
    ms = (idx_time.m * 60 + idx_time.s + idx_time.f / 75.0) * 1000
    return f"{ms:.2f}ms"


@task(
    help={
        "in-dir": "Root directory to start traversal from",
        "out-dir": "Output directory (hierarchy of input dir is preserved)"
    }
)
def split(ctx, in_dir, out_dir):
    """
    Traverses directories and splits audio files
    into multiple tracks using found cue sheets.

    Requires FFmpeg to be installed.
    """

    in_dir, out_dir = Path(in_dir), Path(out_dir)

    if not in_dir.is_dir():
        raise Exit(message=f"'{in_dir}' is not valid directory!")
    if out_dir.is_dir() and any(out_dir.iterdir()):
        raise Exit(message=f"'{out_dir}' is not empty directory!")

    for cur_dir, _, files in os.walk(in_dir):
        print(f"Scanning '{cur_dir}'...", end=" ")

        cue_files = [
            f for f in map(Path, files) if f.suffix.casefold() == ".cue"
        ]

        if not cue_files:
            print("No cue sheets found.")
            continue

        for cue_file in cue_files:
            print(f"\n\tFound '{cue_file}' sheet, parsing...", end=" ")

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
                f"\tSplitting '{audio_file.name}' FILE into {len(tracks)} tracks...",
                end=" "
            )

            with ThreadPoolExecutor() as executor:
                futures = []
                for track, next_track in zip_longest(tracks, tracks[1:]):
                    out_file = cur_out_dir / f"{track.num:02d} {track.title}.flac"
                    track_start = next(i.time for i in track.indices if i.num == 1)
                    track_end = next_track.indices[0].time if next_track else None
                    track_tags = [
                        ("album", cue_sheet.title),
                        ("artist", cue_sheet.performer),
                        ("date", cue_sheet.date),
                        ("genre", cue_sheet.genre),
                        ("title", track.title),
                        ("tracknumber", track.num),
                        ("tracktotal", len(tracks))
                    ]
                    out_file_args = [
                        "-map_metadata", "-1",
                        "-compression_level", "8",
                        "-ss", _ff_time(track_start)
                    ]
                    if track_end:
                        out_file_args += ["-to", _ff_time(track_end)]
                    for k, v in track_tags:
                        if v:
                            out_file_args += ["-metadata", f"{k}={v}"]

                    def _helper():
                        ff = FFmpeg(
                            global_options="-loglevel error",
                            inputs={audio_file: None},
                            outputs={out_file: out_file_args}
                        )
                        ff.run()
                        print("*", end="")

                    futures.append(executor.submit(_helper))

                wait(futures)

            print(" OK.")
