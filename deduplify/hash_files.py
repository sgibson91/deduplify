"""
Hash Files
----------

Walk over a directory structure and hash the files within it. Then group
together files that have generated the same hash.

Author: Sarah Gibson
Python version: >=3.7 (developed with 3.8)
"""
# import sys

import os
import json
import hashlib
import logging
import fnmatch
from tqdm import tqdm
from typing import Tuple
from itertools import chain
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger()


def resolvepath(path):
    """Resolve and normalize a path

    1.  Handle tilde expansion; turn ~/.ssh into /home/user/.ssh and
        ~otheruser/bin to /home/otheruser/bin
    2.  Normalize the path so that it doesn't contain relative segments, turning
        e.g. /usr/local/../bin to /usr/bin
    3.  Get the real path of the actual file, resolving symbolic links
    """
    return os.path.realpath(os.path.normpath(os.path.expanduser(path)))


def get_total_number_of_files(target_dir: str, file_ext: str = ".xml") -> int:
    """Count the total number of files of a given extension in a directory.

    Args:
        target_dir (str): The target directory to search.
        file_ext (str): The file extension to search for. Default: .xml

    Returns:
        int: The number of files with the matching extension within the tree
            of the target directory
    """
    logger.info("Calculating number of files that will be hashed in %s" % target_dir)

    dirpath = resolvepath(target_dir)
    output = len(fnmatch.filter(os.listdir(dirpath), f"*{file_ext}"))

    logger.info("%s files to be hashed in %s" % (output, target_dir))

    return output


def hashfile(path: str, blocksize: int = 65536) -> Tuple[str, str]:
    """Calculate the MD5 hash of a given file

    Args:
        path ()str, os.path): Path to the file to generate a hash for
        blocksize (int, optional): Memory size to read in the file
                                   Default: 65536

    Returns:
        hash (str): The HEX digest hash of the given file
        path (str): The filepath that generated the hash
    """
    # Instatiate the hashlib module with md5
    hasher = hashlib.md5()

    # Open the file and instatiate the buffer
    f = open(path, "rb")
    buf = f.read(blocksize)

    # Continue to read in the file in blocks
    while len(buf) > 0:
        hasher.update(buf)  # Update the hash
        buf = f.read(blocksize)  # Update the buffer

    f.close()

    return hasher.hexdigest(), path


def filter_dict(results: dict) -> Tuple[dict, dict]:
    """Filter a given dictionary into two separate dictionaries based on the
    conditional that the length of the values is either greater than or equal
    to unity.

    Args:
        results (dict): Dictionary to be filtered

    Results:
        duplicated (dict): Dictionary where len(values) > 1. Considered to be
                           duplicated hashes.
        unique (dict): Dictionary where len(values) == 1. Considered to be
                       unique hashes.
    """
    logger.info("Filtering the results...")
    duplicated = {key: value for (key, value) in results.items() if len(value) > 1}
    unique = {key: value[0] for (key, value) in results.items() if len(value) == 1}

    # Calculate number of unique and duplicated files
    logger.info("Number of unique files: %s" % len(unique))

    total = 0
    for value in duplicated.values():
        total += len(value)

    logger.info("Number of duplicated files: %s" % total)

    return duplicated, unique


def run_hash(
    dir: str, count: int, dupfile: str, unfile: str, restart: bool = False, **kwargs
):
    """Hash files within a directory structure

    Args:
        dir (str): Root directory to search under
        count (int): Number of threads to parallelise over
        dupfile (str): JSON file location for duplicated hashes
        unfile (str): JSON file location for unique hashes
        restart (bool): If true, will restart a hash run. dupfile and unfile
            must exist since the filenames already hashed will be skipped.
            Default: False.
    """
    # Check the directory path exists
    if not os.path.exists(dir):
        raise ValueError("Please provide a known filepath!")

    total_file_num = get_total_number_of_files(dir)

    if restart:
        logger.info("Restarting hashing process")

        for input_file in [dupfile, unfile]:
            if not os.path.isfile(input_file):
                raise FileNotFoundError(
                    f"{input_file} must exist to restart a hash run!"
                )

        with open(dupfile) as stream:
            dup_dict = json.load(stream)

        with open(unfile) as stream:
            un_dict = json.load(stream)

        for key, value in un_dict.items():
            un_dict[key] = [value]

        pre_hashed_dict = {**dup_dict, **un_dict}
        files_to_skip = [item for values in pre_hashed_dict.values() for item in values]
    else:
        files_to_skip = []

    logger.info("Walking structure of: %s" % dir)
    logger.info("Generating MD5 hashes for files...")
    # counter = 0
    if restart:
        hashes = defaultdict(list, pre_hashed_dict)
    else:
        hashes = defaultdict(list)  # Empty dict to store hashes in

    total = total_file_num - len(files_to_skip)
    pbar = tqdm(total=total)

    for dirName, _, fileList in os.walk(dir):
        with ThreadPoolExecutor(max_workers=count) as executor:
            futures = [
                executor.submit(hashfile, os.path.join(dirName, filename))
                for filename in fileList
                if filename not in files_to_skip
            ]
            for future in as_completed(futures):
                hash, filepath = future.result()
                hashes[hash].append(filepath)

                dup_dict, unique_dict = filter_dict(hashes)  # Filter the results

                for filename, content in zip([dupfile, unfile], [dup_dict, unique_dict]):
                    logger.info("Writing outputs to: %s" % filename)
                    with open(filename, "w") as f:
                        json.dump(content, f, indent=2, sort_keys=True)

                # counter += 1
                # print(f"Total files hashed: {counter}", end="\r")
                # sys.stdout.flush()

                pbar.update(1)

    pbar.close()
