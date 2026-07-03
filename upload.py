import sys
import argparse
from pathlib import Path
from waggle.plugin import Plugin


def run(args):
    print(f'uploading {args.file_path}')
    with Plugin() as plugin:
        meta = {
            "camera": args.name if args.name != "" else args.file_path.stem,
        }
        plugin.upload_file(args.file_path, meta=meta)
        print(f'Done')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--file-path', dest='file_path',
        action='store', required=True, type=Path,
        help='Path to file to upload')
    parser.add_argument(
        '--name', dest='name',
        action='store',
        help='(optional) Name of the camera to report.')
    args = parser.parse_args()
    exit(run(args))
