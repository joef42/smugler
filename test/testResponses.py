#!/usr/bin/python3
#pylint: disable=C,R,W0201

from hashlib import md5

def getItemId(item):
    return md5(item.encode('utf-8')).hexdigest()[:6]

def folderItem(folderName, path):
    return {
                "Name": folderName,
                "UrlName": folderName,
                #"SecurityType": "Password",
                #"SortMethod": "Name",
                #"SortDirection": "Ascending",
                #"Description": "",
                #"Keywords": "",
                #"Password": "",
                #"PasswordHint": "",
                #"Privacy": "Public",
                #"SmugSearchable": "Inherit from User",
                #"WorldSearchable": "Inherit from User",
                #"DateAdded": "2020-01-01T00:00:00+00:00",
                #"DateModified": "2020-01-01T00:00:00+00:00",
                #"UrlPath": "{path}/{folderName}",
                #"NodeID": getItemId(folderName),
                #"IsEmpty": false,
                #"Uri": f"/api/v2/folder/user/testuser{path}/{folderName}",
                #"WebUri": f"https://testuser.smugmug.com/testuser{path}/{folderName}",
                "Uris": {
                    "Folders": f"/api/v2/folder/user/testuser{path}/{folderName}!folders",
                    "FolderAlbums": f"/api/v2/folder/user/testuser{path}/{folderName}!albums",
                    "SortFolderAlbums": f"/api/v2/folder/user/testuser{path}/{folderName}!sortalbums"
                },
                #"ResponseLevel": "Full"
            }

def getFoldersResponse(folders, path):
    return {
                "Response": {
                    "Uri": "/api/v2/folder/user/testuser{path}!folders",
                    "Locator": "Folder",
                    "LocatorType": "Objects",
                    "Folder": [ folderItem(folderName, path) for folderName in folders ]
                },
                "Code": 200,
                "Message": "Ok"
            }

def albumItem(albumName, path):

    albumId = getItemId(albumName)

    return {
            "NiceName": albumName,
            "UrlName": albumName,
            "Title": albumName,
            "Name": albumName,
            #"TemplateUri": "/api/v2/template/18",
            #"AllowDownloads": true,
            #"Backprinting": "",
            #"BoutiquePackaging": "Inherit from User",
            #"CanRank": true,
            #"Clean": false,
            #"Comments": true,
            #"Description": "",
            #"EXIF": true,
            #"External": true,
            #"FamilyEdit": false,
            #"Filenames": false,
            #"FriendEdit": false,
            #"Geography": true,
            #"Header": "Custom",
            #"HideOwner": false,
            #"InterceptShipping": "Inherit from User",
            #"Keywords": "",
            #"LargestSize": "5K",
            #"PackagingBranding": true,
            #"Password": "",
            #"PasswordHint": "",
            #"Printable": true,
            #"Privacy": "Private",
            #"ProofDays": 0,
            #"Protected": false,
            #"Share": true,
            #"Slideshow": true,
            #"SmugSearchable": "Inherit from User",
            #"SortDirection": "Ascending",
            #"SortMethod": "Filename",
            #"SquareThumbs": true,
            #"Watermark": false,
            #"WorldSearchable": true,
            #"SecurityType": "None",
            #"AlbumKey": albumId,
            #"CanBuy": true,
            #"CanFavorite": false,
            #"Date": "2020-01-01T00:00:00+00:00",
            #"LastUpdated": "2020-01-01T00:00:00+00:00",
            #"ImagesLastUpdated": "2020-01-01T00:00:00+00:00",
            #"NodeID": "abcde",
            #"OriginalSizes": 0,
            #"TotalSizes": 0,
            #"ImageCount": 23,
            "UrlPath": f"{path}/{albumName}",
            #"CanShare": true,
            #"HasDownloadPassword": false,
            #"Packages": false,
            "Uri": f"/api/v2/album/{albumId}",
            "WebUri": f"https://testuser.smugmug.com{path}/{albumName}",
            "Uris": {
                "AlbumImages": f"/api/v2/album/{albumId}!images"
            },
            "ResponseLevel": "Full"
        }

def getAlbumsResponse(albums, path):
    return {
        "Response": {
            "Uri": f"/api/v2/folder/user/testuser/{path}!albums",
            "Locator": "Album",
            "LocatorType": "Objects",
            "Album": [ albumItem(albumName, path) for albumName in albums ]
        },
        "Code": 200,
        "Message": "Ok"
        }

def imageItem(imageName):
    imageId = getItemId(imageName)
    return {
        "Title": imageName,
        #"Caption": "",
        #"Keywords": "",
        #"KeywordArray": [],
        #"Watermark": "No",
        #"Latitude": "0.00000000000000",
        #"Longitude": "0.00000000000000",
        #"Altitude": 0,
        #"Hidden": false,
        #"ThumbnailUrl": f"https://photos.smugmug.com/photos/i-{imageId}/0/Th/i-{imageId}-Th.jpg",
        "FileName": imageName,
        #"Processing": false,
        #"UploadKey": "123",
        #"Date": "2020-01-01T00:00:00+00:00",
        #"Format": "JPG",
        #"OriginalHeight": 1920,
        #"OriginalWidth": 1080,
        #"LastUpdated": "2020-01-01T00:00:00+00:00",
        #"Collectable": true,
        #"IsArchive": false,
        #"IsVideo": false,
        #"CanEdit": true,
        #"CanBuy": true,
        #"Protected": false,
        #"Watermarked": false,
        #"ImageKey": imageId,
        #"ArchivedUri": f"https://photos.smugmug.com/photos/i-{imageId}/0/D/i-{imageId}-D.jpg",
        #"ArchivedSize": 12345,
        #"ArchivedMD5": "aaa",
        #"CanShare": true,
        #"Comments": true,
        #"ShowKeywords": true,
        #"FormattedValues": {
            #"Caption": {
            #    "html": "",
            #    "text": ""
            #},
            #"FileName": {
            #    "html": imageName,
            #    "text": imageName
            #}
        #},
        "Uri": f"/api/v2/album/{imageId}/image/{imageId}-0",
        #"WebUri": f"https://testuser.smugmug.com{path}/{albumName}/i-{imageId}",
        #"Movable": true,
        #"Origin": "Album"
    }

def getImagesResponse(albumName, images):
    return {
        "Response": {
            "Uri": f"/api/v2/album/{getItemId(albumName)}!images",
            "Locator": "AlbumImage",
            "LocatorType": "Objects",
            "AlbumImage": [ imageItem(imageName) for imageName in images],
        },
        "Code": 200,
        "Message": "Ok"
    }

def uploadResponse(imageId):

    return {
                "stat": "ok",
                "method": "smugmug.images.upload",
                "Image": {
                    #"StatusImageReplaceUri": null,
                    "ImageUri": f"/api/v2/image/{imageId}-0",
                    #"AlbumImageUri": f"/api/v2/album/{albumId}/image/{imageId}-0",
                    #"URL": ""
                },
                #"Asset": {
                #    "AssetComponentUri": f"/api/v2/library/asset/{imageId}/component/i/{imageId}",
                #    "AssetUri": f"/api/v2/library/asset/{imageId}"
                #}
            }


def imageResponse(fileName):

    return {
                "Response": {
                    "Uri": f"/api/v2/image/{fileName}-0",
                    "Locator": "Image",
                    "LocatorType": "Object",
                    "Image": {
                        "FileName": fileName
                    }
                },
                "Code": 200,
                "Message": "Ok"
            }
