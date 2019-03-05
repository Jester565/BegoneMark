#Removes white watermarks from images of the same size with identical watermark placement
#Input Required: Watermark Images, Alpha of the watermark

import cv2
import os
import numpy as np
import tkinter
import tkinter.filedialog
import argparse

#Loads images from directory (and keeps their color)
def loadColoredImgsFromDir(dir):
    imgs = []
    files = os.listdir(dir)
    for filename in files:
        img = cv2.imread(dir + "/" + filename)
        imgs.append(img)
    return imgs

#Load images from directory and convert to greyscale
def loadImgsFromDir(dir):
    imgs = []
    files = os.listdir(dir)
    for filename in files:
        img = cv2.imread(dir + "/" + filename)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        imgs.append(img)
    return imgs

#Average each pixel in all the images
def imgsMean(imgs):
    iterCount = 0.0
    combImg = None
    for img in imgs:
        iterCount += 1.0
        if (iterCount == 1):
            combImg = img
        else:
            combImg = cv2.addWeighted(combImg, 1.0 - 1/iterCount, img, 1/iterCount, 0)
    return combImg

#Find other watermarks in the image matching watermark
def findWatermarkCoords(src, watermark, threshold):
    rows, cols = watermark.shape
    res = cv2.matchTemplate(src, watermark, cv2.TM_CCOEFF_NORMED)
    loc = np.where(res >= threshold)
    greatestRes = -1
    greatestResCoord = [-1, -1]
    rectCoords = []
    lastLoc = [-500, -500]
    #Zip combines the two arrays in loc into one array of pairs
    for pt in zip(*loc[::-1]):
        #True if the watermark is at a different location than from the last match
        if (abs(pt[0] - lastLoc[0]) > cols or abs(pt[1] - lastLoc[1]) > rows):
            if (greatestRes > 0):
                rectCoords.append(greatestResCoord)
                greatestRes = -1

        #ptRes is how well the image matches
        ptRes = res[pt[1]][pt[0]]
        if (greatestRes < ptRes):
            greatestRes = ptRes
            greatestResCoord = pt
        lastLoc = pt
    if (greatestRes > 0):
        rectCoords.append(greatestResCoord)
    return rectCoords

#Take the location of all the watermarks
def genMeanRois(imgs, roiCoords, roiRows, roiCols):
    rois = []
    for img in imgs:
        for coord in roiCoords:
            roi = img[coord[1]:(coord[1] + roiRows), coord[0]:(coord[0] + roiCols)]
            rois.append(roi)
    fullMeanRoi = imgsMean(rois)
    return fullMeanRoi

DISPLAY_SCALE_DEFAULT = 0.5
COLOR_DEFAULT = 255
MATCH_THRESHOLD_DEFAULT = 0.7
MASK_THRESHOLD_DEFAULT = 115
REFINE_COUNT_DEFAULT = 3

#Parse command line arguments
parser = argparse.ArgumentParser()
parser.add_argument("alpha", help="alpha of the watermark (0-255)", type=int)
parser.add_argument("--input_dir", help="directory of watermarked photos")
parser.add_argument("--output_dir", help="directory to output cleaned photos")
parser.add_argument("--display_scale", help="rescale images by this when displaying", nargs='?', const=DISPLAY_SCALE_DEFAULT, default=DISPLAY_SCALE_DEFAULT, type=float)
parser.add_argument("--color", help="black / white scale of watermark (0-255)", nargs='?', const=COLOR_DEFAULT, default=COLOR_DEFAULT, type=int)
parser.add_argument("--match_threshold", help="threshold to match watermark (0-1)", nargs='?', const=MATCH_THRESHOLD_DEFAULT, default=MATCH_THRESHOLD_DEFAULT, type=float)
parser.add_argument("--mask_threshold", help="threshold for minimum mask color (0-255)", nargs="?", const=MASK_THRESHOLD_DEFAULT, default=MASK_THRESHOLD_DEFAULT, type=int)
parser.add_argument("--refine_count", help="number of times the mask should be refined", nargs="?", const=REFINE_COUNT_DEFAULT, default=REFINE_COUNT_DEFAULT, type=int)

args = parser.parse_args()

#Create a display element to get the input and output directories
root = tkinter.Tk()
inputDirName = args.input_dir

#Show file selector if inputDir is not defined
if args.input_dir is None:
    inputDirName = tkinter.filedialog.askdirectory(parent=root, title="Select watermark image directory")
imgs = loadImgsFromDir(inputDirName)

#Take average of all watermarked images
fullMeanImg = imgsMean(imgs)

#Let user select single watermark instance
displayScale = args.display_scale
fullMeanDisplayImg = cv2.resize(fullMeanImg, (0,0), fx=(displayScale), fy=(displayScale))
fullMeanWatermarkDisplayRect = cv2.selectROI("IMAGE", fullMeanDisplayImg, False, False)
cv2.destroyAllWindows()
fmtRect = tuple(int((1.0/displayScale)*x) for x in fullMeanWatermarkDisplayRect)
meanWatermark = fullMeanImg[fmtRect[1]:fmtRect[1]+fmtRect[3], fmtRect[0]:fmtRect[0]+fmtRect[2]]

#Find matching watermarks, overlap them to create a better average in meanWatermark
watermarkRows, watermarkCols = meanWatermark.shape
watermarkCoords = None
for i in range(1, args.refine_count):
    watermarkCoords = findWatermarkCoords(fullMeanImg, meanWatermark, args.match_threshold)
    meanWatermark = genMeanRois(imgs, watermarkCoords, watermarkRows, watermarkCols)

#Get the outline of the watermark
ret, lapMask = cv2.threshold(meanWatermark, args.mask_threshold, 255, cv2.THRESH_BINARY)
lap = cv2.Laplacian(lapMask, cv2.CV_8U)
lap = cv2.Laplacian(lap, cv2.CV_8U) + lap

#Cut out noise from watermark using a threshold
ret, mask = cv2.threshold(meanWatermark, args.mask_threshold, args.alpha, cv2.THRESH_BINARY)

cImgs = loadColoredImgsFromDir(inputDirName)

outputDirName = args.output_dir
if args.output_dir is None:
    outputDirName = tkinter.filedialog.askdirectory(parent=root, title="Select output directory")

#Iterate over all watermarked images
i = 0
for cImg in cImgs:
    #Iterate over watermark instances in image
    for rect in watermarkCoords:
        rois = []
        #Split image into red, green, blue channel
        for img in cv2.split(cImg):
            roi = img[rect[1]:(rect[1] + watermarkRows), rect[0]:(rect[0] + watermarkCols)]
            for x in range(0, watermarkRows):
                for y in range(0, watermarkCols):
                    if (mask[x, y] != 0):
                        #Use inverse of alpha composition format to find color
                        realColor = 255.0 * ((float(roi[x, y]) - float(mask[x,y]) * float(args.color / 255.0)) / (255.0 - float(mask[x,y])))
                        if (realColor < 0):
                            realColor = 0
                        elif (realColor > 255):
                            realColor = 255
                        roi[x, y] = realColor
            rois.append(roi)
        #Combine red, green, blue channels
        cRoi = cv2.merge(rois)
        #Use inpaint to fill in the outline of the watermark where accuracy is worse
        cRoi = cv2.inpaint(cRoi, lap, 2, cv2.INPAINT_TELEA)
        cImg[rect[1]:(rect[1] + watermarkRows), rect[0]:(rect[0] + watermarkCols)] = cRoi
    i += 1
    cv2.imwrite(outputDirName + "/" + str(i) + ".png", cImg)
    print("Image Processed")
    
print("DONE")
