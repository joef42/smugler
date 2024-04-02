#pylint: disable=C,R,W0212

from requests_oauthlib import OAuth1Session
import json
import pickle
import logging
import time
import urllib.parse as urlparse
from requests_toolbelt.multipart import encoder

CurrentSmugMugApi = None

urlTransTab = str.maketrans('', '', ' _.+&/\\\'()@')

def sizeFormat(nbytes):
    suffixes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
    if nbytes == 0:
        return '0 B'
    i = 0
    while nbytes >= 1024 and i < len(suffixes)-1:
        nbytes /= 1024.
        i += 1
    f = ('%.2f' % nbytes).rstrip('0').rstrip('.')
    return '%s %s' % (f, suffixes[i])

class SmugMugException(Exception):
    def __init__(self, errCode, errMsg):
        super().__init__(errCode, errMsg)
        self.errCode = errCode
        self.errMsg = errMsg

    def __repr__(self):
        return "SmugMugExcpetion " + repr(self.errCode) + ": " + repr(self.errMsg)

def extractUri(uri):
    if "Uri" in uri:
        return uri["Uri"]
    return uri

def normalizeName(name):
    # Needed to match files. Smugmug API is sometimes
    # returning a different extension to what was uploaded.
    for ff in (("_mp4.MP4", ".mp4"), (".MP4", ".mp4")):
        if name.endswith(ff[0]):
            return name.replace(ff[0], ff[1])
    return name

class Image():

    def __init__(self, resp):
        super().__init__()
        self._resp = resp

    def __str__(self):
        return "%s [Image]" % (self.getFileName())

    def getFileName(self):
        return self._resp["FileName"]

    def toString(self, depth=0):
        return "%s%s\n" % ((" " * (depth*4)), self)

class Album():

    def __init__(self, resp, lazy=True):
        super().__init__()
        self._filenameCache = dict()
        self.__load(resp, lazy)

    def __load(self, resp=None, lazy=True):
        if resp:
            self._resp = resp
        else:
            self._resp = CurrentSmugMugApi._get(self._resp["Uri"],
                dataFilter=Album.dataFilter,
                uriFilter=Album.uriFilter)["Album"]

        self._images = []
        self._filenameCache.clear()

        if not lazy:
            self.__reloadChildren()
        else:
            logging.debug("Lazy load Album %s", self.getName())

    def reload(self):
        logging.debug("Reload of Album %s", self.getName())
        self.__load(lazy=False)

    def __reloadChildren(self):
        pagedResp = CurrentSmugMugApi._get(extractUri(self._resp["Uris"]["AlbumImages"]),
            dataFilter=["FileName"],
            paged=True)

        self._filenameCache.clear()
        for resp in pagedResp:
            if "AlbumImage" in resp:
                for img in resp["AlbumImage"]:
                    self._images.append(Image(img))

        logging.debug("%s has %d images", self._resp["Name"], len(self._images))

    def hasImage(self, path):
        if not self._filenameCache:
            for img in self._images:
                self._filenameCache[normalizeName(img.getFileName())] = img

        from pathlib import Path
        assert isinstance(path, Path)

        return normalizeName(path.name) in self._filenameCache

    def getImages(self):
        return self._images

    def deleteImage(self, image):
        self._filenameCache.clear()
        self._images.remove(image)
        CurrentSmugMugApi._delete(image._resp["Uri"])

    def getName(self):
        return self._resp["Name"]

    def getUri(self):
        return self._resp["Uri"]

    def isAlbum(self):
        return True

    def upload(self, path):

        start_time = time.time()
        logging.info("Uploading %s (%s) into %s", path.name, sizeFormat(path.stat().st_size), self._resp["Name"])
        resp = CurrentSmugMugApi.upload(self._resp["Uri"], path)
        elapsed_time = time.time() - start_time
        logging.info("Uploading %s finished after %ds.", path.name, elapsed_time)

        if resp:
            self._filenameCache.clear()
            self._images.append(Image(resp))

        return path

    def toString(self, depth):
        result = "%s%s\n" % ((" " * (depth*4)), self)
        for img in self._images:
            result += img.toString(depth+1)
        return result

    def __str__(self):
        return "%s [Album]" % (self.getName(),)

Album.uriFilter = ["AlbumImages"]
Album.dataFilter = ["Name", "Uri"]

class Folder():

    def __init__(self, resp=None, lazy=True):
        super().__init__()
        self._children = []
        self.__load(resp, lazy)

    def __load(self, resp=None, lazy=True, incremental=False):

        if resp:
            self._resp = resp
        elif hasattr(self, "_resp") and self._resp:
            self._resp = CurrentSmugMugApi._get(self._resp["Uri"],
                dataFilter=Folder.dataFilter,
                uriFilter=Folder.uriFilter)["Folder"]
        else:
            self._resp = CurrentSmugMugApi._get(CurrentSmugMugApi.rootNode,
                dataFilter=Folder.dataFilter,
                uriFilter=Folder.uriFilter)["Folder"]

        if "Node" in self._resp:
            self._resp = self._resp["Node"]

        def getNameId(o):
            return (o["Uri"], o["Name"])

        if not lazy:

            oldChildrenMap = dict()
            if incremental:
                logging.debug("Incremental load Folder %s", self.getName())
                for c in self._children:
                    oldChildrenMap[getNameId(c._resp)] = c

            self._children = []

            pagedResp = CurrentSmugMugApi._get(extractUri(self._resp["Uris"]["Folders"]),
                paged=True,
                dataFilter=Folder.dataFilter,
                uriFilter=Folder.uriFilter)

            for resp in pagedResp:
                if "Folder" in resp:
                    for folder in resp["Folder"]:
                        nameId = getNameId(folder)
                        if nameId not in oldChildrenMap or oldChildrenMap[nameId].isAlbum():
                            self._children.append(Folder(folder, lazy=False))
                        else:
                            self._children.append(oldChildrenMap[nameId])

            pagedResp = CurrentSmugMugApi._get(extractUri(self._resp["Uris"]["FolderAlbums"]),
                paged=True,
                dataFilter=Album.dataFilter,
                uriFilter=Album.uriFilter)

            for resp in pagedResp:
                if "Album" in resp:
                    for album in resp["Album"]:
                        nameId = getNameId(album)
                        if nameId not in oldChildrenMap or not oldChildrenMap[nameId].isAlbum():
                            self._children.append(Album(album, lazy=False))
                        else:
                            self._children.append(oldChildrenMap[nameId])

        else:
            logging.debug("Lazy load Folder %s", self.getName())


    def reload(self, incremental=False):
        logging.debug("Reload of %s", self.getName())
        self.__load(lazy=False, incremental=incremental)

    def getChildrenByUrlName(self, name):
        for c in self._children:
            if c._resp["UrlName"] == name.translate(urlTransTab):
                return c
        return None

    def getChildrenByName(self, name):
        for c in self._children:
            if c._resp["Name"] == name:
                return c
        return None

    def getChildren(self):
        return self._children

    def getName(self):
        return self._resp["Name"]

    def isAlbum(self):
        return False

    def createAlbum(self, name, **params):
        logging.info("Create album %s", name)
        params["UrlName"] = name.translate(urlTransTab)
        params["Name"] = name
        params.update(CurrentSmugMugApi.config["Album"])
        params["TemplateUri"] = "/api/v2/template/18"

        resp = CurrentSmugMugApi._post(extractUri(self._resp["Uris"]["FolderAlbums"]),
            params,
            dataFilter=Album.dataFilter,
            uriFilter=Album.uriFilter)
        self._children.append(Album(resp["Album"]))
        return self._children[-1]

    def createFolder(self, name):
        logging.info("Create folder %s", name)
        params = {}
        params["Name"] = name
        params["UrlName"] = name.translate(urlTransTab)
        params.update(CurrentSmugMugApi.config["Folder"])
        resp = CurrentSmugMugApi._post(extractUri(self._resp["Uris"]["Folders"]),
            params,
            dataFilter=Folder.dataFilter,
            uriFilter=Folder.uriFilter)
        self._children.append(Folder(resp["Folder"]))
        return self._children[-1]

    def toString(self, depth=0):
        result = "%s%s\n" % ((" " * (depth*4)), self)
        for nc in self._children:
            result += nc.toString(depth+1)
        return result

    def __str__(self):
        return "%s [Folder]" % (self.getName(),)

Folder.uriFilter = ["Folders", "FolderAlbums", "SortFolderAlbums"]
Folder.dataFilter = ["Name", "Uri"]

class SmugMug:

    _tokenUrl = "https://api.smugmug.com/services/oauth/1.0a/getRequestToken"
    _authorizationBaseUrl = "https://api.smugmug.com/services/oauth/1.0a/authorize"
    _accessTokenUrl = "https://api.smugmug.com/services/oauth/1.0a/getAccessToken"

    _apiUrl = "https://api.smugmug.com"

    def __init__(self, tokenFile, config):
        global CurrentSmugMugApi #pylint: disable=W0603
        logging.getLogger("requests_oauthlib").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("oauthlib").setLevel(logging.WARNING)

        self.tokenFile = tokenFile
        self.config = config
        while self.createOAuthSession() == False:
            self.requestToken()

        if not CurrentSmugMugApi:
            CurrentSmugMugApi = self

    def _checkApiResponse(self, resp):

        response = resp.text
        responseMsg = resp.text
        try:
            response = json.loads(response)
            responseMsg = json.dumps(response, indent=2)
        except: #pylint: disable=W0702
            pass

        logging.debug("API response: %d, %s", resp.status_code, responseMsg)
        if resp.status_code in (200, 201, 202):
            if "Response" in response:
                response = response["Response"]
            return response
        raise SmugMugException(resp.status_code, resp.text)

    def _call(self, callType, method, params = None, data=None, uriFilter=None, dataFilter=None, paged=False):
        if not params:
            params = {}
        if uriFilter == None:
            params["_filteruri"] = "*"
        elif uriFilter:
            params["_filteruri"] = ",".join(uriFilter)
        if dataFilter == None:
            params["_filter"] = "*"
        elif dataFilter:
            params["_filter"] = ",".join(dataFilter)
        params["_verbosity"] = 1
        params["_shorturis"] = 1

        headers = {"Accept":"application/json"}

        if not method.startswith("/api/v2"):
            method = "/api/v2" + method

        pagedResponses = []

        while True:

            logging.debug("API %s: method=%s, data=%r, params=%r", callType, self._apiUrl + method, data, params)
            if callType == "get":
                resp = self.session.get(self._apiUrl + method, params=params, headers=headers)
            elif callType == "post":
                resp = self.session.post(self._apiUrl + method, data=data, params=params, headers=headers)
            elif callType == "delete":
                resp = self.session.delete(self._apiUrl + method, params=params, headers=headers)

            resp = self._checkApiResponse(resp)

            if not paged:
                if "Pages" in resp and "NextPage" in resp["Pages"]:
                    raise SmugMugException(-1, "Need to call in page mode")
                return resp
            else:
                pagedResponses.append(resp)

                if "Pages" in resp and "NextPage" in resp["Pages"]:
                    parsedParams = urlparse.parse_qs(urlparse.urlparse(resp["Pages"]["NextPage"]).query)

                    params["start"] = parsedParams["start"]
                    params["count"] = parsedParams["count"]
                else:
                    return pagedResponses

    def _get(self, method, **params):
        return self._call("get", method, **params)

    def _post(self, method, data, **params):
        return self._call("post", method, data=data, **params)

    def _delete(self, method, **params):
        return self._call("delete", method, **params)

    def loadToken(self):
        if self.tokenFile.exists():
            with self.tokenFile.open("rb") as fp:
                return pickle.load(fp)
        return None

    def storeToken(self, token):
        with self.tokenFile.open("wb") as fp:
            pickle.dump(token, fp)

    def createOAuthSession(self):
        token = self.loadToken()
        if token and "oauth_token" in token and "oauth_token_secret" in token:
            self.session = OAuth1Session(self.config["SmugMugApi"]["key"],
                client_secret=self.config["SmugMugApi"]["secret"],
                resource_owner_key=token['oauth_token'],
                resource_owner_secret=token['oauth_token_secret'])

            resp = self._get("!authuser", dataFilter=["NickName", "ImageCount"], uriFilter=["Folder"] )
            self.userName = resp["User"]["NickName"]
            self.rootNode = extractUri(resp["User"]["Uris"]["Folder"])

            logging.info("Successfully authorized as %s. Currently %d images online", self.userName, resp["User"]["ImageCount"])
            return True

        return False

    def requestToken(self):
        # 1. Get request token
        oauth = OAuth1Session(self.config["SmugMugApi"]["key"], client_secret=self.config["SmugMugApi"]["secret"], callback_uri='oob')
        requestToken = oauth.fetch_request_token(self._tokenUrl)

        # 2. Send user to Smugmug page
        authorization_url = oauth.authorization_url(self._authorizationBaseUrl)
        print('Please go here and authorize,', authorization_url)

        # 3. Get the authorization verifier code from the callback url
        verifier = input('Enter the authorization code:')

        # 4. Fetch the access token
        oauth = OAuth1Session(self.config["SmugMugApi"]["key"],
                            client_secret=self.config["SmugMugApi"]["secret"],
                            resource_owner_key=requestToken['oauth_token'],
                            resource_owner_secret=requestToken['oauth_token_secret'],
                            verifier=verifier)
        authToken = oauth.fetch_access_token(self._accessTokenUrl)
        self.storeToken(authToken)

    def upload(self, album, image):
        url = "https://upload.smugmug.com/"
        with open(image, 'rb') as f:
            file = encoder.MultipartEncoder({
                "upload_file": (image.name, f, "application/octet-stream")
            })
            headers = {'X-Smug-AlbumUri': album,
                'X-Smug-ResponseType': 'json',
                'X-Smug-Version': 'v2',
                'X-Smug-Title': image.name,
                "Content-Type": file.content_type}
            logging.debug("API upload: files=%s, headers=%r]", file, headers)
            r = self.session.post(url, data=file, headers=headers)
            response = self._checkApiResponse(r)

            uploadedFile = CurrentSmugMugApi._get(response["Image"]["ImageUri"], dataFilter=["FileName"])["Image"]
            uploadedFileName = uploadedFile["FileName"]
            if image.name != uploadedFileName:
                logging.warning("Filename missmatch after upload. Local: %s Remote: %s", image.name, uploadedFileName)
            return uploadedFile

