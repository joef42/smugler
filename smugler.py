#!/usr/bin/python3
#pylint: disable=C,R,W1203

from lib.smugmugapi import SmugMug, Folder, SmugMugException
import logging
from pathlib import Path
import datetime
import time
import pickle
import yaml
import argparse

def getContentFilePath(saveDir):
    return saveDir / ".smugmugContent"

def saveContentToFile(saveDir, rootFolder):
    contentFile = getContentFilePath(saveDir)
    with contentFile.open('wb') as fp:
        pickle.dump(rootFolder, fp)

def loadContentFromFile(saveDir):
    contentFile = getContentFilePath(saveDir)
    if contentFile.exists():
        with contentFile.open('rb') as fp:
            return pickle.load(fp)
    return None

def supportedFileFormat(path):
    if path.is_file() and path.suffix.lower().lstrip(".") in (
        "jpg", "jpeg", "png", "gif", "heic",
        "mp4", "mov", "avi", "mpeg", "mpg",
        "m4a", "m4v", "mts", "mkv", "wmv"):
        return True
    return False

def error_callback(error):
    logging.error("Job returned error: %r", error)

def uploadFiles(node, files):
    failCount = 0
    for f in files:
        try:
            node.upload(f)
            failCount = 0
        except Exception as e: #pylint: disable=W0718
            logging.exception("Failed to upload %r", e)
            failCount += 1
            if failCount >= 5:
                logging.error("Too many failed uploads, giving up.")
                raise

def scanNewFiles(path: Path, parent):

    assert(path.is_dir())

    filesToUpload = []
    folders = {}

    for p in path.iterdir():
        if p.is_dir():
            if not p.name.startswith("_") and (not parent or not parent.isAlbum()):
                node = parent.getChildrenByName(p.name) if parent else None
                contentInSubfolder = scanNewFiles(p, node)
                if contentInSubfolder:
                    folders[p.name] = contentInSubfolder
        elif supportedFileFormat(p) and (not parent or not parent.hasImage(p)):
            filesToUpload.append(p)

    if filesToUpload and folders:
        raise f"Found files and folders in {path}"

    if filesToUpload:
        return filesToUpload
    elif folders:
        return folders
    else:
        return None

def refreshPattern(parent, pattern):

    if parent.getName() == pattern:
        logging.info(f"Reload {parent.getName()}")
        parent.reload()
    elif not parent.isAlbum():
        childrenToDelete = []
        for child in parent.getChildren()[:]:
            try:
                refreshPattern(child, pattern)
            except SmugMugException as e:
                if e.errCode == 404:
                    childrenToDelete.append(child)

        for childToDel in childrenToDelete:
            parent.getChildren().remove(childToDel)
                    
def refreshFromRemote(changes, parent):

    if isinstance(changes, dict):

        parent.reload(incremental=True)

        for name, subItems in changes.items():
            node = parent.getChildrenByName(name)
            if node:
                refreshFromRemote(subItems, node)

    elif isinstance(changes, list):

        parent.reload()

def uploadChanges(path: Path, changes, parent):

    if isinstance(changes, dict):
        for name, subItems in changes.items():
            subPath = path / name
            node = parent.getChildrenByName(name)
            if not node:
                if isinstance(subItems, dict):
                    node = parent.createFolder(name)
                else:
                    node = parent.createAlbum(name)
            uploadChanges(subPath, subItems, node)

    elif isinstance(changes, list):
        logging.info(f"Uploading {len(changes)} files into {parent.getName()}")
        uploadFiles(parent, changes)

def upload(path: Path, root):

    logging.info("Scanning for new files to upload")

    for _ in range(3):

        changes = scanNewFiles(path, root)

        if changes:
            refreshFromRemote(changes, root)
            changes = scanNewFiles(path, root)
            uploadChanges(path, changes, root)
        else:
            logging.info("All in sync")
            break

def printChanges(path: Path, changes):
    if isinstance(changes, dict):
        for name, subItems in changes.items():
            subPath = path / name
            printChanges(subPath, subItems)
    
    elif isinstance(changes, list):
        logging.info(f"Missing {len(changes)} files in {path}")

def scan(path: Path, root):

    logging.info("Scanning for new files")

    changes = scanNewFiles(path, root)
    if changes:
        refreshFromRemote(changes, root)
        changes = scanNewFiles(path, root)

    if changes:
        printChanges(Path(), changes)
    else:
        logging.info("All in sync")

def scanRemoteRecursive(path, parent):
    if not parent.isAlbum():
        for c in parent.getChildren():
            subPath = path / c.getName()
            if subPath.exists():
                scanRemoteRecursive(subPath, c)
            else:
                logging.error("Ignoring folder not found on disk: %r", subPath)
    else:
        seenSet = set()
        delList = []
        for p in parent.getImages():
            imgPath = path / p.getFileName()
            if not imgPath.exists():
                logging.info("Delete missing  : %s", imgPath)
                delList.append(p)
            elif imgPath in seenSet:
                logging.info("Delete duplicate: %s", imgPath)
                delList.append(p)
            else:
                seenSet.add(imgPath)

        if delList:
            logging.info("Delete %d images in %s? [y/n]", len(delList), parent.getName())
            if input() != "y":
                logging.info("Skipping")
            else:
                for i in delList:
                    parent.deleteImage(i)
                parent.reload()

def main(args):

    imageDir = Path(args.imagePath)

    logHandlers = []
    if args.debug:
        fileHandler = logging.FileHandler(
            filename=imageDir / ("smugler_%s.log" % datetime.datetime.fromtimestamp(time.time()).strftime('%Y_%m_%d_%H.%M.%S')),
            mode='w')
        fileHandler.setLevel(logging.DEBUG)
        logHandlers.append(fileHandler)

    consoleHandler = logging.StreamHandler()
    consoleHandler.setLevel(logging.INFO)
    logHandlers.append(consoleHandler)

    logging.basicConfig(level= logging.DEBUG if args.debug else logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s",
                        handlers=logHandlers)

    logging.debug('Started')

    configLocations = [
        Path("smuglerconf.yaml"),
        imageDir / "smuglerconf.yaml",
        Path.home() / "smuglerconf.yaml"]

    for cl in configLocations:
        if cl.exists():
            with cl.open("r", encoding="utf-8") as fp:
                config = yaml.safe_load(fp)
            break
    else:
        logging.error("Config file not found")
        exit(-1)

    SmugMug(imageDir / ".smugmugToken", config)

    rootFolder = loadContentFromFile(imageDir)
    if not rootFolder:
        rootFolder = Folder(lazy=True)
    
    if args.refresh == "*":
        rootFolder = Folder(lazy=False)
    elif args.refresh:
        refreshPattern(rootFolder, args.refresh)        

    try:
        if args.action == "sync":
            upload(imageDir, rootFolder)
        elif args.action == "scan":
            scan(imageDir, rootFolder)
        #elif args.action == "syncRemote":
        #    scanRemoteRecursive(imageDir, rootFolder)
    finally:
        saveContentToFile(imageDir, rootFolder)

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Sync folder to Smugmug')
    parser.add_argument('action', type=str, choices=["sync", "scan"], help='sync: Upload images to Smugmug')
    parser.add_argument('imagePath', type=str, help='Path to local gallery')
    parser.add_argument('--refresh', type=str, help='Refresh Folders/Albums with the given name from Smugmug. * for everything.')
    parser.add_argument('--debug', action='store_true', help='Print additional debug trace')
    parsedArgs = parser.parse_args()

    def run():
        main(parsedArgs)

    if parsedArgs.debug:
        import cProfile
        cProfile.run('run()', sort='cumulative')
    else:
        run()

