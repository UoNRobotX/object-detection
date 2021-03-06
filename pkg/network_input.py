import math, random, re
import numpy as np
from PIL import Image, ImageFilter, ImageOps

from .constants import *

class CoarseBatchProducer:
    """ Produces input values for the coarse network """
    #constructor
    def __init__(self, dataFile, cellFilter, outFile=None):
        self.inputs  = []
        self.outputs = []
        self.posInputIndices = []
        self.negInputIndices = []
        #read "dataFile"
        if re.search(r"\.npz$", dataFile):
            print("Reading data from binary file")
            data = np.load(dataFile)
            self.inputs = data["arr_0"]
            self.outputs = data["arr_1"]
            self.posInputIndices = data["arr_2"]
            self.negInputIndices = data["arr_3"]
        else:
            print("Generating data")
            filenames = []
            waterCells = []
            with open(dataFile) as file:
                filename = None
                for line in file:
                    if line[0] != " ":
                        filename = line.strip()
                        filenames.append(filename)
                        waterCells.append([])
                    elif filename == None:
                        raise Exception("Invalid data file")
                    else:
                        waterCells[-1].append([int(c) for c in line.strip()])
            if len(filenames) == 0:
                raise Exception("No filenames")
            #load images
            self.loadImages(filenames, cellFilter, waterCells)
        #save data if requested
        if outFile != None:
            print("Saving data to binary file")
            np.savez_compressed(outFile, \
                self.inputs, self.outputs, self.posInputIndices, self.negInputIndices)
    #load next image
    def loadImages(self, filenames, cellFilter, waterCells):
        for fileIdx in range(len(filenames)):
            #obtain PIL image
            image = Image.open(filenames[fileIdx])
            #get inputs and outputs
            for row in range(len(waterCells[fileIdx])):
                for col in range(len(waterCells[fileIdx][row])):
                    #use static filter
                    if cellFilter[row][col] == 1:
                        continue
                    #determine whether the input should have a positive prediction
                    containsWater = waterCells[fileIdx][row][col] == 1
                    ##randomly skip
                    #if not containsWater and random.random() < 0.75:
                    #    continue
                    #get cell image
                    cellImg = image.crop(
                        (col*CELL_WIDTH, row*CELL_HEIGHT, (col+1)*CELL_WIDTH, (row+1)*CELL_HEIGHT)
                    )
                    cellImg = cellImg.resize((INPUT_WIDTH, INPUT_HEIGHT), resample=Image.LANCZOS)
                    #preprocess image
                    cellImgs = [cellImg]
                    if False: #maximise image contrast
                        cellImgs = [ImageOps.autocontrast(img) for img in cellImgs]
                    if False: #equalize image histogram
                        cellImgs = [ImageOps.equalize(img) for img in cellImgs]
                    if False: #blur image
                        cellImgs = [img.filter(ImageFilter.GaussianBlur(radius=2)) for img in cellImgs]
                    if False: #sharpen
                        cellImgs = [
                            img.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))
                            for img in cellImgs
                        ]
                    if False: #use kernel
                        cellImgs = [
                            img.filter(ImageFilter.Kernel((3,3), (0, 0, 0, 0, 1, 0, 0, 0, 0)))
                            for img in cellImgs
                    ]
                    if False: #other
                        cellImgs = [img.filter(ImageFilter.FIND_EDGES) for img in cellImgs]
                    if False: #add rotated images
                        cellImgs += [img.rotate(180) for img in cellImgs]
                        cellImgs += [img.rotate(90) for img in cellImgs]
                    if True: #add flipped images
                        cellImgs += [img.transpose(Image.FLIP_LEFT_RIGHT) for img in cellImgs]
                    if False: #add sheared images
                        shearFactor = random.random()*0.8 - 0.4
                        cellImgs += [
                            img.transform(
                                (img.size[0], img.size[1]),
                                Image.AFFINE,
                                data=(
                                    (1-shearFactor, shearFactor, 0, 0, 1, 0) if shearFactor>0 else
                                    (1+shearFactor, shearFactor, -shearFactor*img.size[0], 0, 1, 0)
                                ),
                                resample=Image.BICUBIC)
                            for img in cellImgs
                        ]
                    #get inputs
                    self.inputs += [np.array(img).astype(np.float32) for img in cellImgs]
                    #get outputs
                    self.outputs += [
                        np.array([1, 0]).astype(np.float32) if containsWater else
                        np.array([0, 1]).astype(np.float32)
                    ] * len(cellImgs)
        if len(self.inputs) == 0:
            raise Exception("No inputs")
        #get indices of positive/negative inputs
        self.posInputIndices = [
            i for i in range(len(self.inputs)) if self.outputs[i][0]
        ]
        self.negInputIndices = [
            i for i in range(len(self.inputs)) if not self.outputs[i][0]
        ]
        if len(self.posInputIndices) == 0:
            raise Exception("No positive inputs")
        if len(self.negInputIndices) == 0:
            raise Exception("No negative inputs")
    #returns a tuple containing a numpy array of "size" inputs, and a numpy array of "size" outputs
    def getBatch(self, size):
        inputs = []
        outputs = []
        c = 0
        while c < size:
            #randomly select an input and output
            choosePositive = random.random() < 0.5
            if choosePositive:
                idx = math.floor(random.random() * len(self.posInputIndices))
                inputs.append(self.inputs[self.posInputIndices[idx]])
                outputs.append(self.outputs[self.posInputIndices[idx]])
            else:
                idx = math.floor(random.random() * len(self.negInputIndices))
                inputs.append(self.inputs[self.negInputIndices[idx]])
                outputs.append(self.outputs[self.negInputIndices[idx]])
            #update
            c += 1
        return np.array(inputs), np.array(outputs)
    #returns the data set size
    def getDatasetSize(self):
        return len(self.inputs)
    #returns the ratio of positive inputs
    def getRps(self):
        return [len(self.posInputIndices) / len(self.inputs)]

class DetailedBatchProducer:
    """Produces input values for the detailed network"""
    #constructor
    def __init__(self, dataFile, cellFilter, outFile=None):
        self.inputs  = []
        self.outputs = []
        self.posInputIndices = [] #list of lists of indices, with one indices list for each box type
        self.negInputIndices = [] #list of indices
        #read "dataFile"
        if re.search(r"\.npz$", dataFile):
            print("Reading data from binary file")
            data = np.load(dataFile)
            self.inputs = data["arr_0"]
            self.outputs = data["arr_1"]
            self.posInputIndices = data["arr_2"]
            self.negInputIndices = data["arr_3"]
        else:
            print("Generating data")
            filenames = []
            boxes = []
            with open(dataFile) as file:
                filename = None
                for line in file:
                    if line[0] != " ":
                        filename = line.strip()
                        filenames.append(filename)
                        boxes.append([])
                    elif filename == None:
                        raise Exception("Invalid data file")
                    else:
                        boxes[-1].append([int(c) for c in line.strip().split(",")])
            if len(filenames) == 0:
                raise Exception("No filenames")
            #load images
            self.loadImages(filenames, cellFilter, boxes)
        #save data if requested
        if outFile != None:
            print("Saving data to binary file")
            np.savez_compressed(outFile, \
                self.inputs, self.outputs, self.posInputIndices, self.negInputIndices)
    #load next image
    def loadImages(self, filenames, cellFilter, boxes):
        #get window positions
        windowPositions = GET_WINDOWS()
        #iterate through images
        for fileIdx in range(len(filenames)):
            #obtain PIL image
            image = Image.open(filenames[fileIdx])
            for pos in windowPositions:
                topLeftX     = pos[0]
                topLeftY     = pos[1]
                bottomRightX = pos[2]
                bottomRightY = pos[3]
                #use static filter
                if isFiltered(topLeftX, topLeftY, bottomRightX, bottomRightY, cellFilter):
                    continue
                #determine whether the input should have a positive prediction
                containedType = None
                prevOverlap = 0
                winArea = (bottomRightX-topLeftX) * (bottomRightY-topLeftY)
                for box in boxes[fileIdx]:
                    #only accept if a box is fully contained
                    if (box[0] >= topLeftX and
                        box[1] >= topLeftY and
                        box[2] <= bottomRightX and
                        box[3] <= bottomRightY):
                        #and has at least a minimum overlap
                        boxArea = (box[2]-box[0]) * (box[3]-box[1])
                        overlap = boxArea / winArea
                        if overlap >= 0.3 and overlap > prevOverlap:
                            containedType = box[4]
                            prevOverlap = overlap
                #randomly skip
                if containedType is None and random.random() < 0.8:
                    continue
                #get window image
                winImg = image.crop((topLeftX, topLeftY, bottomRightX, bottomRightY))
                winImg = winImg.resize((INPUT_WIDTH, INPUT_HEIGHT), resample=Image.LANCZOS)
                #preprocess image
                winImgs = [winImg]
                if False: #maximise image contrast
                    winImgs = [ImageOps.autocontrast(img) for img in winImgs]
                if True and containedType is not None and containedType == 0: #add rotated images
                    winImgs += [img.rotate(180) for img in winImgs]
                    winImgs += [img.rotate(90) for img in winImgs]
                if True and containedType is not None: #add flipped images
                    winImgs += [img.transpose(Image.FLIP_LEFT_RIGHT) for img in winImgs]
                if True and containedType is not None: #blur image
                    blurRadii = [1.0]
                    blurredImages = []
                    for radius in blurRadii:
                        blurredImages += [
                            img.filter(ImageFilter.GaussianBlur(radius)) for img in winImgs
                        ]
                    winImgs += blurredImages
                if True and containedType is not None and containedType == 0: #add sheared images
                    shearedImages = []
                    for maxShearFactor in [0.1, 0.2]:
                        shearFactor = random.random()*maxShearFactor*2 - maxShearFactor
                        shearedImages += [
                            img.transform(
                                (img.size[0], img.size[1]),
                                Image.AFFINE,
                                data=(
                                    (1-shearFactor, shearFactor, 0, 0, 1, 0) if shearFactor>0 else
                                    (1+shearFactor, shearFactor, -shearFactor*img.size[0], 0, 1, 0)
                                ),
                                resample=Image.BICUBIC)
                            for img in winImgs
                        ]
                    winImgs += shearedImages
                #get inputs
                self.inputs += [np.array(img).astype(np.float32) for img in winImgs]
                #get outputs
                output = [0 for i in range(NUM_BOX_TYPES+1)]
                if containedType is not None:
                    output[containedType] = 1
                else:
                    output[-1] = 1
                output = np.array(output).astype(np.float32)
                for img in range(len(winImgs)):
                    self.outputs.append(output)
                if len(self.inputs) == 0:
                    raise Exception("No inputs")
        if len(self.inputs) == 0:
            raise Exception("No inputs")
        #get indices of positive/negative inputs
        for typeIdx in range(NUM_BOX_TYPES):
            self.posInputIndices.append([
                i for i in range(len(self.inputs)) if self.outputs[i][typeIdx]
            ])
            if len(self.posInputIndices[-1]) == 0:
                raise Exception("No positive inputs for type %d" % typeIdx)
        self.negInputIndices = [
            i for i in range(len(self.inputs)) if self.outputs[i][-1]
        ]
        if len(self.negInputIndices) == 0:
            raise Exception("No negative inputs")
    #returns a tuple containing a numpy array of "size" inputs, and a numpy array of "size" outputs
    def getBatch(self, size):
        inputs = []
        outputs = []
        #randomly select inputs and outputs
        if False: #choose inputs randomly
            for i in range(size):
                idx = math.floor(random.random() * len(inputs))
                inputs.append(self.inputs[idx])
                outputs.append(self.outputs[idx])
        else: #control proportions of positive and negative inputs
            POS_PROBS = [0.25, 0.25, 0.5] #proportions of input type_0/type_1/etc/no_object
            assert len(POS_PROBS) == NUM_BOX_TYPES + 1 and sum(POS_PROBS) == 1
            cumPosProbs = [sum(POS_PROBS[:i+1]) for i in range(len(POS_PROBS))]
            for i in range(size):
                choice = random.random()
                for j in range(len(cumPosProbs)):
                    if choice < cumPosProbs[j]:
                        choice = j
                        break
                if choice < NUM_BOX_TYPES:
                    idx = math.floor(random.random() * len(self.posInputIndices[choice]))
                    idx = self.posInputIndices[choice][idx]
                    inputs.append(self.inputs[idx])
                    outputs.append(self.outputs[idx])
                else:
                    idx = math.floor(random.random() * len(self.negInputIndices))
                    idx = self.negInputIndices[idx]
                    inputs.append(self.inputs[idx])
                    outputs.append(self.outputs[idx])
        return np.array(inputs), np.array(outputs)
    #returns the data set size
    def getDatasetSize(self):
        return len(self.inputs)
    #returns the ratio of positive inputs
    def getRps(self):
        rpsVals = [
            len(self.posInputIndices[i]) / len(self.inputs)
            for i in range(NUM_BOX_TYPES)
        ]
        return rpsVals

def getCellFilter(filterFile):
    """ Obtains filter data from "filterFile", or uses an empty filter.
        Returns a list with the form [[0, 1, ...], ...].
            Each element denotes a row of cells, where 1 indicates a filtered cell.
    """
    if filterFile != None:
        cellFilter = []
        with open(filterFile) as file:
            for line in file:
                cellFilter.append([int(c) for c in line.strip()])
    else:
        cellFilter = [
            [0 for col in IMG_WIDTH // CELL_WIDTH]
            for row in IMG_HEIGHT // CELL_HEIGHT
        ]
    return cellFilter

def isFiltered(topLeftX, topLeftY, bottomRightX, bottomRightY, cellFilter):
    for i in range(topLeftY // CELL_HEIGHT, bottomRightY // CELL_HEIGHT):
        for j in range(topLeftX // CELL_WIDTH, bottomRightX // CELL_WIDTH):
            if cellFilter[i][j]:
                return True
    return False
