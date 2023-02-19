#!/usr/bin/python3
#pylint: disable=C,R,W0201

import os
import tempfile
import yaml
import pickle
import requests
import json
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

    tempDir = tempfile.mkdtemp()

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

    def traversePath(self, path):
        node = self.remoteFolders
        if path:
            for p in path.split("/"):
                if isinstance(node, dict) and p in node:
                    node = node[p]
                else:
                    node = None
                    break
        return node

#https://api.smugmug.com/api/v2/folder/user/testuser!folders?_filteruri=Folders%2CFolderAlbums%2CSortFolderAlbums&_filter=Name%2CUri&_verbosity=1&_shorturis=1

    def registerFolderCalls(self):

        def folderMatcher(request):
            if request.method == "GET" and "!folders" in request.path:

                folderPath = request.path.replace("/api/v2/folder/user/testuser", "").replace("!folders", "")

                node = self.traversePath(folderPath)
                if not isinstance(node, dict):
                    node = None

                resp = requests.Response()
                if node is not None:

                    responseFolders = []
                    for k, v in node:
                        if isinstance(v, dict):
                            responseFolders.append({
                                "Name": k
                            })

                    resp.status_code = 200
                    resp._content = json.dumps({"Response" : {"Folder": responseFolders}}).encode("ascii")

                    return resp

            return None

        self.request_mock.add_matcher(folderMatcher)


#https://api.smugmug.com/api/v2/folder/user/testuser!albums?_filteruri=AlbumImages&_filter=Name%2CUri&_verbosity=1&_shorturis=1

    def registerAlbumCalls(self):

        def createAlbum(name, albumPath):
            return  {
                        "Uri": f"/api/v2/folder/user/testuser{albumPath}/{name}!albums",
                        "Name": name
                    }

        def createImage(name, albumPath):
            return  {
                        "Uri": f"/api/v2/folder/user/testuser{albumPath}/{name}!albums",
                        "Name": name
                    }

        def uploadImageResponse(name):
            return  {
                        "stat": "ok",
                        "Image": {
                            "ImageUri": "/api/v2/album/<key>/image/<key>-0"
                        }
                    }


        def albumMatcher(request):
            print(request.path)
            if "!albums" in request.path:

                albumPath = request.path.replace("/api/v2/folder/user/testuser", "").replace("!albums", "")

                if request.method == "GET":

                    node = self.traversePath(albumPath)
                    if not isinstance(node, dict):
                        node = None

                    resp = requests.Response()
                    if node is not None:

                        responseAlbums = []
                        for k, v in node:
                            if isinstance(v, list):
                                responseAlbums.append(createAlbum(k, albumPath))

                        resp.status_code = 200
                        resp._content = json.dumps({"Response" : {"Album": responseAlbums}}).encode("ascii")

                        return resp

                elif request.method == "POST":

                    albumName = parse_qs(request.text)["Name"][0]

                    resp = requests.Response()
                    resp.status_code = 200
                    resp._content = json.dumps({"Album": createAlbum(albumName, albumPath)}).encode("ascii")

                    return resp

            elif "/api/v2/image/" in request.path:

                fileName = request.path.replace("/api/v2/image/", "").replace("-0", "")

                if request.method == "GET":


                    resp = requests.Response()
                    resp._content = json.dumps(testResponses.imageResponse(fileName)).encode("ascii")
                    resp.status_code = 200

                    return resp


            elif "upload.smugmug.com" == request.hostname:

                print(request.text.fields['upload_file'][0])
                print(request.text.fields['upload_file'][1].read())


                resp = requests.Response()
                resp._content = json.dumps(testResponses.uploadResponse(request.text.fields['upload_file'][0])).encode("ascii")
                resp.status_code = 200

                return resp

            return None

        self.request_mock.add_matcher(albumMatcher)

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


    def setUp(self):

        self.createConfig()
        self.createToken()

        self.registerUserBaseCalls()

        self.remoteFolders = {}
        self.registerFolderCalls()
        self.registerAlbumCalls()

    def run(self, result=None):
        with requests_mock.Mocker() as self.request_mock:
            super(TestSmugler, self).run(result)

    def testSimpleEmptyUser(self):
        smugler.main(Args("sync", self.tempDir))

    def testSimpleUpload(self):
        self.createLocalFiles(self.tempDir, { "Album1": ["File1.jpg"]})
        smugler.main(Args("sync", self.tempDir))



print("Testdir: " + TestSmugler.tempDir)

if __name__ == '__main__':
    unittest.main()