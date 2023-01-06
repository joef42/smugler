#!/usr/bin/python3
#pylint: disable=C,R

import os
import tempfile
import yaml
import pickle

import unittest
import requests_mock

import smugler

class TestSmugler(unittest.TestCase):

    tempDir = tempfile.mkdtemp()

    def createConfig(self, content = None):

        if not content:
            content = {}

        content["SmugMugApi"] = {"key": "dummy_key", "secret": "dummy_secret"}

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
                                "Uris": {
                                    "Folder": "/api/v2/folder/user/testuser!folders",
                                    "FolderAlbums": "/api/v2/folder/user/testuser!albums"
                                }
                            }
                        }}

        self.request_mock.register_uri('GET', 
            '//api.smugmug.com/api/v2/folder/user/testuser?',
            json=dataUserFolder)

    def setUp(self):

        self.createConfig()
        self.createToken()

        self.registerUserBaseCalls()

    def run(self, result=None):
        with requests_mock.Mocker() as self.request_mock:
            super(TestSmugler, self).run(result)  

    def testSimpleEmptyUser(self):
        smugler.main(["sync", self.tempDir])

print("Testdir: " + TestSmugler.tempDir)     

if __name__ == '__main__':
    unittest.main()
