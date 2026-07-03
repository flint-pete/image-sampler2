#!/usr/bin/env python3
# ANL:waggle-license
#  This file is part of the Waggle Platform.  Please see the file
#  LICENSE.waggle.txt for the legal details of the copyright and software
#  license.  For more details on the Waggle project, visit:
#           http://www.wa8.gl
# ANL:waggle-license
from datetime import datetime, timezone
import logging
import time
import os
import argparse
from multiprocessing import Process

from waggle.plugin import Plugin
from waggle.data.vision import Camera
from croniter import croniter

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(message)s',
    datefmt='%Y/%m/%d %H:%M:%S')


def capture(plugin, stream, stream_name, out_dir=""):
    sample_file_name = "sample.jpg"
    with Camera(stream) as cam:
        sample = cam.snapshot()
    if out_dir == "":
        sample.save(sample_file_name)
        # The camera name is added in the meta
        meta = {
            "camera": stream_name,
        }
        plugin.upload_file(sample_file_name, meta=meta)
    else:
        dt = datetime.fromtimestamp(sample.timestamp / 1e9)
        base_dir = os.path.join(out_dir, stream, dt.astimezone(timezone.utc).strftime('%Y/%m/%d/%H'))
        os.makedirs(base_dir, exist_ok=True)
        sample_path = os.path.join(base_dir, dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S%z.jpg'))
        sample.save(sample_path)


def run(stream, stream_name, cronjob, out_dir=""):
    logger_header = f'Stream {stream} name: {stream_name}'
    logging.info(f'{logger_header}starting image sampler.')
    if cronjob == "":
        logging.info(f'{logger_header}capturing...')
        with Plugin() as plugin:
            capture(plugin, stream, stream_name, out_dir)
        return 0
    
    logging.info(f'{logger_header}cronjob style sampling triggered')
    if not croniter.is_valid(cronjob):
        logging.error(f'{logger_header}cronjob format {cronjob} is not valid')
        return 1
    now = datetime.now(timezone.utc)
    cron = croniter(cronjob, now)
    with Plugin() as plugin:
        while True:
            n = cron.get_next(datetime).replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            next_in_seconds = (n - now).total_seconds()
            if next_in_seconds > 0:
                logging.info(f'{logger_header}sleeping for {next_in_seconds} seconds')
                time.sleep(next_in_seconds)
            logging.info(f'{logger_header}capturing...')
            capture(plugin, stream, stream_name, out_dir)
    return 0


def main(args):
    workers = []
    if len(args.name) > 0:
        for stream, name in zip(args.stream, args.name):
            worker = Process(target=run, args=(stream, name, args.cronjob, args.out_dir))
            workers.append(worker)
            worker.start()
    else:
        for stream in args.stream:
            worker = Process(target=run, args=(stream, stream, args.cronjob, args.out_dir))
            workers.append(worker)
            worker.start()

    # If one of the workers fails, the main process should return the exit code of the failed worker.
    # Hopefully, the error messages are shown in the main process's stdout.
    exit_code = 0
    for worker in workers:
        worker.join()
        if worker.exitcode != 0:
            exit_code = worker.exitcode
    return exit_code


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--stream', dest='stream',
        action='append',
        help='ID or name of a stream. Multiple streams can be specified, each stream with the --stream option.')
    parser.add_argument(
        '--name', dest='name', default=[],
        action='append',
        help='(optional) Name of the stream to report. When specified the count and order should match with given streams.')
    parser.add_argument(
        '--out-dir', dest='out_dir',
        action='store', default="", type=str,
        help='Path to save images locally in %%Y-%%m-%%dT%%H:%%M:%%S%%z.jpg format')
    parser.add_argument(
        '--cronjob', dest='cronjob',
        action='store', default="", type=str,
        help='Time interval expressed in cronjob style')

    args = parser.parse_args()
    if args.out_dir != "":
        os.makedirs(args.out_dir, exist_ok=True)
    exit(main(args))
