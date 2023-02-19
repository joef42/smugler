#!/usr/bin/python3
#pylint: disable=C,R,W0201

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