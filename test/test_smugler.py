#!/usr/bin/python3
#pylint: disable=C,R,W0201

import os
import tempfile
import yaml
import pickle
from urllib.parse import parse_qs

import unittest
import requests_mock

from test import testResponses

import smugler

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

        self.registerUserBaseCalls()

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

    def registerGetFoldersCall(self, folders, path=""):
        self.request_mock.register_uri('GET',
            '//api.smugmug.com/api/v2/folder/user/testuser!folders',
            json=testResponses.getFoldersResponse(folders, path))

    def registerGetAlbumsCall(self, albums, path=""):
        self.request_mock.register_uri('GET',
            '//api.smugmug.com/api/v2/folder/user/testuser!albums',
            json=testResponses.getAlbumsResponse(albums, path))

    def registerGetImagesCall(self, albumName, images):
        self.request_mock.register_uri('GET',
            f'//api.smugmug.com/api/v2/album/{testResponses.getItemId(albumName)}!images',
            json=testResponses.getImagesResponse(albumName, images))

    def registerGetImageCall(self, imageName):
        self.request_mock.register_uri('GET',
            f'//api.smugmug.com/api/v2/image/{testResponses.getItemId(imageName)}-0',
            json=testResponses.getImageResponse(imageName))

    def registerCreateFolderCall(self, path, folderName):
        self.request_mock.register_uri('POST',
            f'//api.smugmug.com/api/v2/folder/user/testuser{path}!folders',
            additional_matcher= lambda r : parse_qs(r.text)["Name"][0] == folderName,
            json=testResponses.postFolderResponse(folderName, path))

    def registerCreateAlbumCall(self, albumPath, albumName):
        self.request_mock.register_uri('POST',
            f'//api.smugmug.com/api/v2/folder/user/testuser{albumPath}!albums',
            additional_matcher= lambda r : parse_qs(r.text)["Name"][0] == albumName,
            json=testResponses.postAlbumResponse(albumName, albumPath))

    def registerUploadCall(self, albumName, imageName):
        def matcher(r):
            return r.text.fields['upload_file'][0] == imageName and r.headers['X-Smug-AlbumUri'] == f"/api/v2/album/{testResponses.getItemId(albumName)}".encode('ascii')
        self.request_mock.register_uri('POST',
            '//upload.smugmug.com',
            additional_matcher=matcher,
            json=testResponses.uploadResponse(imageName))

    def createLocalFiles(self, path, node):

        if isinstance(node, dict):
            for nextNode, subItems in node.items():
                nextPath = os.path.join(path, nextNode)
                os.mkdir(nextPath)

                self.createLocalFiles(nextPath, subItems)

        elif isinstance(node, list):
            for file in node:
                with open(os.path.join(path, file), "w", encoding="utf-8") as fp:
                    fp.write(file)

    def run(self, result=None):
        with requests_mock.Mocker() as self.request_mock:
            super(TestSmugler, self).run(result)

    def testSimpleEmptyUser(self):
        smugler.main(Args("sync", self.tempDir))

        print(self.request_mock.call_count)
        print(self.request_mock.request_history)

    def testSimpleUpload(self):
        self.createLocalFiles(self.tempDir, { "Album1": ["File1.jpg"]})

        self.registerGetFoldersCall([], "")
        self.registerGetAlbumsCall([], "")
        self.registerCreateAlbumCall("", "Album1")
        self.registerUploadCall("Album1", "File1.jpg")
        self.registerGetImageCall("File1.jpg")

        smugler.main(Args("sync", self.tempDir))

    def testMultipleUpload(self):
        self.createLocalFiles(self.tempDir, { "Album1": ["File1.jpg", "File2.jpg"], "Album2": ["File3.jpg", "File4,jpg"]})

        self.registerGetFoldersCall([], "")
        self.registerGetAlbumsCall([], "")
        self.registerCreateAlbumCall("", "Album1")
        self.registerCreateAlbumCall("", "Album2")
        self.registerUploadCall("Album1", "File1.jpg")
        self.registerUploadCall("Album1", "File2.jpg")
        self.registerUploadCall("Album2", "File3.jpg")
        self.registerUploadCall("Album2", "File4.jpg")
        self.registerGetImageCall("File1.jpg")
        self.registerGetImageCall("File2.jpg")
        self.registerGetImageCall("File3.jpg")
        self.registerGetImageCall("File4.jpg")

        smugler.main(Args("sync", self.tempDir))

    def testWithFolder(self):
        self.createLocalFiles(self.tempDir, { "Folder1": {"Album1": ["File1.jpg", "File2.jpg"]}})

        self.registerGetFoldersCall([], "")
        self.registerGetAlbumsCall([], "")
        self.registerCreateFolderCall("", "Folder1")
        self.registerCreateAlbumCall("/Folder1", "Album1")
        self.registerUploadCall("Album1", "File1.jpg")
        self.registerUploadCall("Album1", "File2.jpg")
        self.registerGetImageCall("File1.jpg")
        self.registerGetImageCall("File2.jpg")

        smugler.main(Args("sync", self.tempDir))

    def testSimpleNoUpload(self):
        self.createLocalFiles(self.tempDir, { "Album1": ["File1.jpg"]})

        self.registerGetFoldersCall([], "")
        self.registerGetAlbumsCall(["Album1"], "")
        self.registerGetImagesCall("Album1", ["File1.jpg"])

        smugler.main(Args("sync", self.tempDir))

if __name__ == '__main__':
    unittest.main()
