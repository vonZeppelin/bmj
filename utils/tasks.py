from invoke import Exit, task
from pathlib import Path
from shlex import quote


SUPPORTED_EXTS = {".ape", ".flac"}


def _error(msg): print(f"\033[91m{msg}\033[0m")


def _shq(path): return quote(str(path))


def _validate_files(**kwargs):
    file_names = set()
    for kind, files in kwargs.items():
        if not files:
            _error(f"{kind} file not found!")
            return False
        if len(files) > 1:
            _error(f"two or more {kind} files found!")
            return False
        file_names.add(files[0].stem)
    if len(file_names) != 1:
        _error(f"{' & '.join(kwargs.keys())} files don't match!")
        return False
    return True


@task(
    help={
        "in-dir": "Root directory to start traversal from",
        "out-dir": "Output directory (hierarchy of input dir is preserved)"
    }
)
def split(ctx, in_dir, out_dir):
    """
    Traverses directories and splits audio files
    into multiple files using found CUE sheets.

    Requires ffmpeg and unflac to be installed.
    """

    in_dir, out_dir = Path(in_dir), Path(out_dir)

    if not in_dir.is_dir():
        raise Exit(message=f"{in_dir} is not valid directory!")
    if out_dir.is_dir() and any(out_dir.iterdir()):
        raise Exit(message=f"{out_dir} is not empty directory!")

    dirs = [in_dir]
    while dirs:
        cur_dir = dirs.pop()
        print(f"\nScanning {cur_dir}...", end=" ")

        audio_files, cue_files = [], []
        for child in cur_dir.iterdir():
            if child.is_dir():
                dirs.append(child)
            else:
                file_ext = child.suffix.lower()
                if file_ext == ".cue":
                    cue_files.append(child)
                elif file_ext in SUPPORTED_EXTS:
                    audio_files.append(child)

        if not _validate_files(cue=cue_files, audio=audio_files):
            continue

        cue_file, audio_file = cue_files + audio_files
        audio_file_ext = audio_file.suffix.lower()
        print(
            f"{cue_file.suffix} & {audio_file.suffix} files found, proceeding."
        )

        cur_out_dir = out_dir / cue_file.parent.relative_to(in_dir)
        cur_out_dir.mkdir(parents=True)
        ctx.run(
            f"unflac -f flac -o {_shq(cur_out_dir)} "
            "-n '{{- printf .Input.TrackNumberFmt .Track.Number}}. {{.Track.Title | Elem}}' "
            f"{_shq(cue_file)}"
        )
