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

import unittest
import requests_mock

from test import testResponses

import smugler

def isFolder(node):
    return isinstance(node, dict)

def isAlbum(node):
    return isinstance(node, list)

class Args:
    def __init__(self, action, imagePath, refresh=False, debug=False):
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

    def createToken(self):

        token = {}
        token['oauth_token'] = 'dummy_oauth_token'
        token['oauth_token_secret'] = 'dummy_oauth_token_secret'

        with open(os.path.join(self.tempDir, ".smugmugToken"), "wb") as fp:
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
                self.assertIsNotNone(album)
                return self.createResponse(testResponses.getImagesResponse(albumName, album))

        m = re.search("image/(.+)-0", urlPath)
        if m:
            if method == "GET":
                imageName = self.findImageWithId(m.group(1))
                self.assertIsNotNone(imageName)
                return self.createResponse(testResponses.getImageResponse(imageName))

        if request.hostname == 'upload.smugmug.com':
            imageName = request.text.fields['upload_file'][0]
            albumId = request.headers['X-Smug-AlbumUri'].replace(b"/api/v2/album/", b"")
            albumName, album = self.findAlbumWithId(albumId)
            self.assertIsNotNone(album)
            self.assertNotIn(imageName, album)
            album.append(imageName)
            return self.createResponse(testResponses.uploadResponse(imageName))

    def assertCallCount(self, count):
        self.assertEqual(self.request_mock.call_count, count)

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

    def testSimpleEmptyUser(self):
        smugler.main(Args("sync", self.tempDir))
        self.assertCallCount(2)

    def testSimpleUpload(self):
        self.createLocalFiles(self.tempDir, {"Album1": ["File1.jpg"]})

        smugler.main(Args("sync", self.tempDir))

        self.assertLocalEqRemote()

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

    def testWithFolder(self):
        self.createLocalFiles(self.tempDir, { "Folder1": {"Album1": ["File1.jpg", "File2.jpg"]}})

        smugler.main(Args("sync", self.tempDir))

        self.assertLocalEqRemote()

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

    def testSimpleNoUpload(self):
        self.createLocalFiles(self.tempDir, {"Album1": ["File1.jpg"]})
        self.remote = { "Album1": ["File1.jpg"]}

        smugler.main(Args("sync", self.tempDir))

        self.assertLocalEqRemote()

if __name__ == '__main__':
    unittest.main()
