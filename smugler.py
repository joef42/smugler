#!/usr/bin/python3
#pylint: disable=C,R

from lib.smugmugapi import SmugMug, Folder
import logging
from pathlib import Path
import datetime
import time
import sys
import pickle
import yaml

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
        "m4a", "m4v", "mts", "mkv"):
        return True
    return False

def error_callback(error):
    logging.error("Job returned error: %r", error)

def uploadFiles(node, files):
    for f in files:
        node.upload(f)

def scanRecursive(path, nodeName, parent):
    if nodeName:
        node = parent.getChildrenByUrlName(nodeName)
        if not node:
            parent.reload()
            node = parent.getChildrenByUrlName(nodeName)
    else:
        node = parent

    filesToUpload = []
    folders = []
    for p in path.iterdir():
        if supportedFileFormat(p) and (not node or not node.getImageByFileName(p.name)):
            filesToUpload.append(p)
        elif p.is_dir() and not p.name.startswith("_"):
            folders.append(p)

    if (not node and filesToUpload) or (node and node.isAlbum()):
        if filesToUpload:
            if not node:
                node = parent.createAlbum(path.name)
            else:
                node.reload()

            filesToUpload = [f for f in filesToUpload if not node.getImageByFileName(f.name)]

            if filesToUpload:
                uploadFiles(node, filesToUpload)
                node.reload()
        for f in folders:
            logging.info("Ignored folder: %s", f)
    elif folders:
        if not node:
            node = parent.createFolder(path.name)
        for f in folders:
            scanRecursive(f, f.name, node)
        for f in filesToUpload:
            logging.info("Ignored images: %s", f)

def scanRemoteRecursive(path, parent):
    if not parent.isAlbum():
        for c in parent.getChildren():
            subPath = path / c.getName()
            if subPath.exists():
                scanRemoteRecursive(subPath, c)
            else:
                logging.error("Ignoring folder not found on disk: %r", subPath)
    else:
        for i in range(2):
            seenSet = set()
            delList = []
            for p in parent.getImages():
                imgPath = path / p.getFileName()
                if not imgPath.exists():
                    if i==0:
                        parent.reload()
                        break
                    logging.info("Delete missing  : %s", imgPath)
                    delList.append(p)
                elif imgPath in seenSet:
                    if i==0:
                        parent.reload()
                        break
                    logging.info("Delete duplicate: %s", imgPath)
                    delList.append(p)
                else:
                    seenSet.add(imgPath)
            else:
                break

        if delList:
            logging.info("Delete %d images in %s? [y/n]", len(delList), parent.getName())
            if input() != "y":
                logging.info("Skipping")
            else:
                for i in delList:
                    parent.deleteImage(i)
                parent.reload()

def main():

    useCachedContent = True
    debug = False
    for p in sys.argv[1:-2]:
        if p == "--refresh":
            useCachedContent = False
        if p == "--debug":
            debug = True

    imageDir = Path(sys.argv[-1])

    logHandlers = []
    if debug:
        fileHandler = logging.FileHandler(
            filename=imageDir / ("smugler_%s.log" % datetime.datetime.fromtimestamp(time.time()).strftime('%Y_%m_%d_%H.%M.%S')),
            mode='w')
        fileHandler.setLevel(logging.DEBUG)
        logHandlers.append(fileHandler)

    consoleHandler = logging.StreamHandler()
    consoleHandler.setLevel(logging.INFO)
    logHandlers.append(consoleHandler)

    logging.basicConfig(level= logging.DEBUG if debug else logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s",
                        handlers=logHandlers)

    logging.debug('Started')

    configLocations = [ 
        Path("smuglerconf.yaml"),
        imageDir / "smuglerconf.yaml",
        Path.home() / "smuglerconf.yaml"]

    for cl in configLocations:
        if cl.exists():
            with open(cl, "r", encoding="utf-8") as fp:
                config = yaml.safe_load(fp)
            break
    else:
        logging.error("Config file not found")
        exit(-1)

    SmugMug(imageDir / ".smugmugToken", config)

    rootFolder = None
    if useCachedContent:
        rootFolder = loadContentFromFile(imageDir)
    if not rootFolder:
        rootFolder = Folder(lazy=True)

    try:
        if sys.argv[-2] == "sync":
            scanRecursive(imageDir, None, rootFolder)
        elif sys.argv[-2] == "syncRemote":
            scanRemoteRecursive(imageDir, rootFolder)
    finally:
        saveContentToFile(imageDir, rootFolder)

if __name__ == "__main__":
    main()
