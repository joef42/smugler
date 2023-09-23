#!/usr/bin/python3
#pylint: disable=C,R,W0201

import os
import tempfile
import yaml
import pickle
from urllib.parse import parse_qs
import re
import requests
import json
from collections import deque
import shutil
import pytest
from pathlib import Path

import unittest
import requests_mock

from test import testResponses

import smugler
from lib.smugmugapi import SmugMug, Folder, SmugMugException

def isFolder(node):
    return isinstance(node, dict)

def isAlbum(node):
    return isinstance(node, list)

class Args:
    def __init__(self, action, imagePath, refresh=None, debug=False):
        self.action = action
        self.imagePath = imagePath
        self.refresh = refresh
        self.debug = debug

class TestSmugler(unittest.TestCase):

    def setUp(self):

        self.tempDir = tempfile.mkdtemp()

        self.createConfig()
        self.createToken()

        self.remote = {}

        self.uploadFail = {}

        self.registerUserBaseCalls()
        self.request_mock.add_matcher(self.remoteHandler)

    def createConfig(self, content = None):
        if not content:
            content = {}

        content["SmugMugApi"] = {"key": "dummy_key", "secret": "dummy_secret"}
        content["Album"] = {}
        content["Folder"] = {}

        with open(os.path.join(self.tempDir, "smuglerconf.yaml"), "w", encoding="utf-8") as fp:
            yaml.dump(content, fp)

        self.config = content

    def createToken(self):

        token = {}
        token['oauth_token'] = 'dummy_oauth_token'
        token['oauth_token_secret'] = 'dummy_oauth_token_secret'

        self.tokenFile = Path(os.path.join(self.tempDir, ".smugmugToken"))

        with open(self.tokenFile, "wb") as fp:
            pickle.dump(token, fp)

    def registerUserBaseCalls(self):

        dataUser = { "Response": {
                    "User": {
                        "ImageCount": 0,
                        "NickName": "TestUser",
                        "Uris": {
                            "Folder": "/api/v2/folder/user/testuser"
                        }
                    }
                }}

        self.request_mock.register_uri('GET',
            '//api.smugmug.com/api/v2!authuser?',
            json=dataUser)

        dataUserFolder = { "Response": {
                            "Folder": {
                                "Name": "",
                                "Uri": "/api/v2/folder/user/testuser",
                                "Uris": {
                                    "Folders": "/api/v2/folder/user/testuser!folders",
                                    "FolderAlbums": "/api/v2/folder/user/testuser!albums"
                                }
                            }
                        }}

        self.request_mock.register_uri('GET',
            '//api.smugmug.com/api/v2/folder/user/testuser?',
            json=dataUserFolder)

    def createErrorResponse(self, code = 400):
        resp = requests.Response()
        resp.status_code = code
        return resp

    def createResponse(self, response, code = 200):
        resp = requests.Response()
        resp.status_code = code
        resp._content = json.dumps(response).encode("ascii") # pylint: disable=protected-access
        return resp

    def traversePath(self, path):
        node = self.remote
        path = path.strip("/")
        if path:
            for p in path.split("/"):
                lowerDict = dict((k.lower(), k) for k in node)
                if isFolder(node) and p.lower() in lowerDict:
                    node = node[lowerDict[p]]
                else:
                    node = None
                    break
        return node

    def getFolderAtPath(self, nodePath):
        node = self.traversePath(nodePath)
        self.assertIsNotNone(node)
        self.assertTrue(isFolder(node))
        return node

    def findAlbumWithId(self, albumId):
        try:
            albumId = albumId.decode()
        except (UnicodeDecodeError, AttributeError):
            pass

        front = deque()
        front.append(self.remote)

        while front:
            node = front.popleft()
            for name, nextNode in node.items():
                if isAlbum(nextNode) and testResponses.getItemId(name) == albumId:
                    return name, nextNode
                elif isFolder(nextNode):
                    front.append(nextNode)

        return None, None

    def findImageWithId(self, imageId):
        try:
            imageId = imageId.decode()
        except (UnicodeDecodeError, AttributeError):
            pass

        front = deque()
        front.append(self.remote)

        while front:
            node = front.popleft()
            if isFolder(node):
                for _, nextNode in node.items():
                    front.append(nextNode)
            elif isAlbum(node):
                for imageName in node:
                    if testResponses.getItemId(imageName) == imageId:
                        return imageName

        return None

    def remoteHandler(self, request):

        method = request.method
        urlPath = request.path.replace("//api.smugmug.com/api/v2/", "")

        m = re.search("folder/user/testuser(.*)!folders", urlPath)
        if m:
            nodePath = m.group(1)
            node = self.getFolderAtPath(nodePath)
            if method == "GET":
                folders = [name for name, childNode in node.items() if isFolder(childNode)]
                return self.createResponse(testResponses.getFoldersResponse(folders, nodePath))
            elif method == "POST":
                name = parse_qs(request.text)["Name"][0]
                self.assertNotIn(name, node)
                node[name] = {}
                return self.createResponse(testResponses.postFolderResponse(name, nodePath))

        m = re.search("folder/user/testuser(.*)!albums", urlPath)
        if m:
            nodePath = m.group(1)
            node = self.getFolderAtPath(nodePath)
            if method == "GET":
                albums = [name for name, childNode in node.items() if isAlbum(childNode)]
                return self.createResponse(testResponses.getAlbumsResponse(albums, nodePath))
            elif method == "POST":
                name = parse_qs(request.text)["Name"][0]
                self.assertNotIn(name, node)
                node[name] = []
                return self.createResponse(testResponses.postAlbumResponse(name, nodePath))

        m = re.search("album/(.+)!images", urlPath)
        if m:
            if method == "GET":
                albumName, album = self.findAlbumWithId(m.group(1))
                
                return self.createResponse(testResponses.getImagesResponse(albumName, album))

        m = re.search("album/(.+)", urlPath)
        if m:
            if method == "GET":
                albumName, album = self.findAlbumWithId(m.group(1))
                if not album:
                    return self.createErrorResponse(404)
                return self.createResponse(testResponses.getAlbumResponse(albumName))

        m = re.search("image/(.+)-0", urlPath)
        if m:
            if method == "GET":
                imageName = self.findImageWithId(m.group(1))
                self.assertIsNotNone(imageName)
                return self.createResponse(testResponses.getImageResponse(imageName))

        m = re.search("folder/user/testuser/(.*)", urlPath)
        if m:
            nodePath = m.group(1).split("/")
            folderName = nodePath[-1]
            pathName = "/".join(nodePath[:-1])
            for k, v in self.getFolderAtPath(pathName).items():
                if isFolder(v) and k.lower() == folderName.lower():
                    realfolderName = k
                    break
            else:
                return self.createErrorResponse(404)
            if method == "GET":
                return self.createResponse(testResponses.getFolderResponse(realfolderName, pathName))

        if request.hostname == 'upload.smugmug.com':
            imageName = request.text.fields['upload_file'][0]
            albumId = request.headers['X-Smug-AlbumUri'].replace(b"/api/v2/album/", b"")
            albumName, album = self.findAlbumWithId(albumId)
            self.assertIsNotNone(album)
            self.assertNotIn(imageName, album)

            if imageName in self.uploadFail:
                if self.uploadFail[imageName]:
                    album.append(imageName)
                del self.uploadFail[imageName]
                return self.createErrorResponse(503)

            else:
                album.append(imageName)
                return self.createResponse(testResponses.uploadResponse(imageName))

    def assertCallCount(self, count):
        self.assertEqual(self.request_mock.call_count, count)

    def assertUploadCount(self, expectedCount):
        actualCount = 0
        for r in self.request_mock.request_history:
            if r.hostname == "upload.smugmug.com":
                actualCount += 1
        self.assertEqual(expectedCount, actualCount)

    def assertPostCount(self, expectedCount):
        actualCount = 0
        for r in self.request_mock.request_history:
            if r.method == "POST" and not r.hostname == "upload.smugmug.com":
                actualCount += 1
        self.assertEqual(expectedCount, actualCount)

    def clearLocalFiles(self, path):
        for d in os.listdir(path):
            fullPath = os.path.join(path, d)
            if os.path.isdir(fullPath):
                shutil.rmtree(fullPath)

    def createLocalFiles(self, path, node):
        def recur(path, node):
            if isinstance(node, dict):
                for nextNode, subItems in node.items():
                    nextPath = os.path.join(path, nextNode)
                    os.makedirs(nextPath, exist_ok=True)

                    recur(nextPath, subItems)

            elif isinstance(node, list):
                for file in node:
                    with open(os.path.join(path, file), "w", encoding="utf-8") as fp:
                        fp.write(file)

        self.local = node
        recur(path, node)

    def assertLocalEqRemote(self):

        def sortLists(node):
            if isFolder(node):
                for _, nextNode in node.items():
                    sortLists(nextNode)
            else:
                node.sort()

        sortLists(self.local)
        sortLists(self.remote)
        self.assertEqual(self.local, self.remote)

    def run(self, result=None):

        with requests_mock.Mocker() as self.request_mock:
            super(TestSmugler, self).run(result)

        #for r in self.request_mock.request_history:
        #    print(r.method)
        #    print("  " + r.hostname)
        #    print("  " + r.path)
        #    print("  " + repr(r.headers))
        #    print("  " + repr(r.text))

    def getTestStructure(self):
        return {
                "Folder1":
                {
                    "Album1_1": ["File1_1_1.jpg", "File1_1_2.jpg"]
                },
                "Folder2":
                {
                    "Album2_1": ["File2_1_1.jpg", "File2_1_2.jpg"],
                    "Folder2_1": 
                    {
                        "Album2_1_1": ["File2_1_1_1.jpg", "File2_1_1_2.jpg"],
                    }
                },
                "Folder3":
                {
                    "Album3_1": ["File3_1_1.jpg", "File3_1_2.jpg"]
                },
                "Album1" : ["File1_3.jpg", "File1_2.jpg", "File1_1.jpg"]
            }


    def testSimpleEmptyUser(self):
        smugler.main(Args("sync", self.tempDir))
        self.assertCallCount(2)

    def testSimpleUpload(self):
        self.createLocalFiles(self.tempDir, {"Album1": ["File1.jpg"]})

        smugler.main(Args("sync", self.tempDir))

        self.assertLocalEqRemote()
        self.assertUploadCount(1)
        self.assertPostCount(1)

    def repeatStateIterations(self, iterations):
        for localState, expectedState in iterations:
            if localState:
                self.createLocalFiles(self.tempDir, localState)

            smugler.main(Args("sync", self.tempDir))

            if expectedState:
                self.local = expectedState
            self.assertLocalEqRemote()

    def testRepeatedUpload(self):
        self.repeatStateIterations([
            ({"Album1": ["File1.jpg"], "Folder1" : {}}, {"Album1": ["File1.jpg"]}),
            ({"Album1": ["File1.jpg", "File2.jpg"], "Folder1" : {}}, {"Album1": ["File1.jpg", "File2.jpg"]}),
            (None, None),
            ({"Album1": ["File1.jpg", "File2.jpg", "File3.jpg"], "Folder1" : {"Album1_1": []}}, {"Album1": ["File1.jpg", "File2.jpg", "File3.jpg"]}),
            (None, None),
            ({"Album1": ["File1.jpg", "File2.jpg", "File3.jpg"], "Folder1" : {"Album1_1": [ "File1_1_2.jpg", "File1_1_1.jpg" ]}}, None),
            (None, None)
        ])

    def testIncompleteLocal(self):
        self.repeatStateIterations([
            ({"Folder1" : {"Album1_1": [ "File1_1_2.jpg", "File1_1_1.jpg" ]}}, None),
            ({"Album2": ["File2_1.jpg", "File2_2.jpg"]}, {"Folder1" : {"Album1_1": [ "File1_1_2.jpg", "File1_1_1.jpg" ]}, "Album2": ["File2_1.jpg", "File2_2.jpg"]})
        ])

    def testMultipleUpload(self):
        self.createLocalFiles(self.tempDir, {"Album1": ["File1.jpg", "File2.jpg"], "Album2": ["File3.jpg", "File4.jpg"]})

        smugler.main(Args("sync", self.tempDir))

        self.assertLocalEqRemote()
        self.assertUploadCount(4)
        self.assertPostCount(2)

    def testWithFolder(self):
        self.createLocalFiles(self.tempDir, { "Folder1": {"Album1": ["File1.jpg", "File2.jpg"]}})

        smugler.main(Args("sync", self.tempDir))

        self.assertLocalEqRemote()
        self.assertUploadCount(2)
        self.assertPostCount(2)

    def testComplexStructure(self):
        self.createLocalFiles(self.tempDir, {
            "Folder1":
            {
                "Folder1_1" : { "Album1_1_1": ["File1_1_1_1.jpg"] },
                "Album1_1": ["File1_1_1.jpg", "File1_1_2.jpg"]
            },
            "Album1" : ["File1_2.jpg", "File1_1.jpg"]
        })

        smugler.main(Args("sync", self.tempDir))

        self.assertLocalEqRemote()
        self.assertUploadCount(5)
        self.assertPostCount(5)

    def testIgnoredFolders(self):
        self.createLocalFiles(self.tempDir, {
            "Folder1":
            {
                "Album1_1": ["File1_1_1.jpg", "File1_1_2.jpg"]
            },
            "_NoFolder2":
            {
                "Album2_1": ["File2_1_1.jpg", "File2_1_2.jpg"]
            },
            "Album1" : ["File1_2.jpg", "File1_1.jpg"]
        })

        smugler.main(Args("sync", self.tempDir))

        del self.local["_NoFolder2"]
        self.assertLocalEqRemote()
        self.assertUploadCount(4)
        self.assertPostCount(3)

    def testIgnoredAlbum(self):
        self.createLocalFiles(self.tempDir, {
            "Folder1":
            {
                "_Album1_1": ["File1_1_1.jpg", "File1_1_2.jpg"]
            },
            "_Album1" : ["File1_2.jpg", "File1_1.jpg"]
        })

        smugler.main(Args("sync", self.tempDir))
        self.local = {}
        self.assertLocalEqRemote()
        self.assertUploadCount(0)
        self.assertPostCount(0)

    def testEmptyFolder(self):
        self.createLocalFiles(self.tempDir, {
            "Folder1":
            {
                "Folder1_1": {}
            }
        })

        smugler.main(Args("sync", self.tempDir))
        self.local = {}
        self.assertLocalEqRemote()
        self.assertUploadCount(0)
        self.assertPostCount(0)

    def testSimpleNoUpload(self):
        self.createLocalFiles(self.tempDir, {"Album1": ["File1.jpg"]})
        self.remote = { "Album1": ["File1.jpg"]}

        smugler.main(Args("sync", self.tempDir))

        self.assertLocalEqRemote()
        self.assertUploadCount(0)
        self.assertPostCount(0)

    def testSimpleNoUploadWithFolder(self):
        self.createLocalFiles(self.tempDir, {"Folder1": {"Album1": ["File1.jpg"]}})
        self.remote = {"Folder1": {"Album1": ["File1.jpg"]}}

        smugler.main(Args("sync", self.tempDir))

        self.assertLocalEqRemote()

    def testSimpleNoUploadAfterLocalAnRemoteRename(self):
        self.createLocalFiles(self.tempDir, {"Folder1": {"Album1": ["File1.jpg"]}})
        self.remote = {"Folder1": {"Album1": ["File1.jpg"]}}

        smugler.main(Args("sync", self.tempDir))

        self.clearLocalFiles(self.tempDir)
        self.createLocalFiles(self.tempDir, {"Folder2": {"Album2": ["File1.jpg"]}})
        self.remote = {"Folder2": {"Album2": ["File1.jpg"]}}

        smugler.main(Args("sync", self.tempDir))

        self.assertLocalEqRemote()
        self.assertUploadCount(0)
        self.assertPostCount(0)

    def testFailingUpload(self):
        self.createLocalFiles(self.tempDir, {"Folder1": {"Album1": ["File1.jpg", "File2.jpg", "File3.jpg", "File4.jpg"]}})

        self.uploadFail["File2.jpg"] = False
        self.uploadFail["File4.jpg"] = True

        smugler.main(Args("sync", self.tempDir))

        self.assertLocalEqRemote()
        self.assertUploadCount(5)

    def testFailingUploadGiveUp(self):
        self.createLocalFiles(self.tempDir, {"Folder1": {"Album1": ["File1.jpg", "File2.jpg", "File3.jpg", "File4.jpg", "File5.jpg"]}})

        self.uploadFail = {"File1.jpg": False, "File2.jpg": False, "File3.jpg": False, "File4.jpg": False, "File5.jpg": False}

        with pytest.raises(Exception):
            smugler.main(Args("sync", self.tempDir))

    def testRemoteRefreshAll(self):
        self.createLocalFiles(self.tempDir, self.getTestStructure())
        self.remote = self.getTestStructure()
        
        smugler.main(Args("sync", self.tempDir))

        self.assertLocalEqRemote()
        self.assertUploadCount(0)
        self.assertPostCount(0)

        del self.remote["Folder1"]["Album1_1"]
        del self.remote["Folder2"]["Album2_1"][0]
        del self.remote["Folder3"]

        smugler.main(Args("sync", self.tempDir))

        self.assertUploadCount(0)
        self.assertPostCount(0)

        smugler.main(Args("sync", self.tempDir, refresh="*"))

        self.assertUploadCount(5)
        self.assertPostCount(3)
        self.assertLocalEqRemote()
    
    def testRemoteRefreshPattern(self):
        self.createLocalFiles(self.tempDir, self.getTestStructure())
        self.remote = self.getTestStructure()
        
        smugler.main(Args("sync", self.tempDir))

        self.assertLocalEqRemote()
        self.assertUploadCount(0)
        self.assertPostCount(0)

        del self.remote["Folder1"]["Album1_1"]
        del self.remote["Folder2"]["Album2_1"][0]

        smugler.main(Args("sync", self.tempDir, refresh="Album2_1"))

        self.assertUploadCount(1)
        self.assertPostCount(0)

        smugler.main(Args("sync", self.tempDir, refresh="Folder1"))

        self.assertUploadCount(3)
        self.assertPostCount(1)

    def testRemoteRefreshPatternOnDeletedFolder(self):
        self.createLocalFiles(self.tempDir, self.getTestStructure())
        self.remote = self.getTestStructure()
        
        smugler.main(Args("sync", self.tempDir))

        self.assertLocalEqRemote()
        self.assertUploadCount(0)
        self.assertPostCount(0)

        del self.remote["Folder3"]

        smugler.main(Args("sync", self.tempDir))

        self.assertUploadCount(0)
        self.assertPostCount(0)

        smugler.main(Args("sync", self.tempDir, refresh="Folder3"))

        self.assertUploadCount(2)
        self.assertPostCount(2)

        self.assertLocalEqRemote()


    def testRemoteRefreshPatternOnDeletedAlbum(self):
        self.createLocalFiles(self.tempDir, self.getTestStructure())
        self.remote = self.getTestStructure()
        
        smugler.main(Args("sync", self.tempDir))

        self.assertLocalEqRemote()
        self.assertUploadCount(0)
        self.assertPostCount(0)

        del self.remote["Folder1"]["Album1_1"]

        smugler.main(Args("sync", self.tempDir))

        self.assertUploadCount(0)
        self.assertPostCount(0)

        smugler.main(Args("sync", self.tempDir, refresh="Album1_1"))

        self.assertUploadCount(2)
        self.assertPostCount(1)

    def testApiReloadFolder(self):

        self.remote = self.getTestStructure()

        SmugMug(self.tokenFile, self.config)

        rootFolder = Folder(lazy=True)
        rootFolder.reload()
        
        folder = rootFolder.getChildrenByName("Folder1")
        album = folder.getChildrenByName("Album1_1")
        album.reload()

        assert len(album.getImages()) == 2

    def NO_testScanRemoteWithDelete(self):

        self.createLocalFiles(self.tempDir, {"Folder1": {"Album1": ["File1.jpg"]}})
        self.remote = {"Folder1": {"Album1": ["File1.jpg", "File2.jpg"]}}

        smugler.main(Args("syncRemote", self.tempDir, refresh=True))

        self.assertLocalEqRemote()



if __name__ == '__main__':
    unittest.main()
