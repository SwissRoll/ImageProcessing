# JPEG encoder/decoder
#
# This code runs the JPEG encoder on an image, but stops after it
# collects the DC and AC components.  There is no compression (using
# DPCM, RLE, or Huffman) of those component.
#
# Immediately after encoding, the JPEG decoder is run on the DC and AC
# components and the resulting image is shown.  This is the image that
# would result after encoding, then decoding, the original image,
# since the missing parts (DPCM, RLE, and Huffman) are lossless.


import sys, os, math

import numpy as np

from PIL import Image

from OpenGL.GLUT import *
from OpenGL.GL import *
from OpenGL.GLU import *

# Globals

useTK = False

Nrows = 0                       # image dimensions.  Each is evenly divisible by 8.
Ncols = 0

inputImage = None               # image read from a file
jpegImage = None                # image after jpeg compressed/decompressed
outputImage = None              # image being shown on screen
dctImage = None                 # image of DCT coefficients
errorImage = None               # image of errors

compressionFactor = 1.0         # factor by which to multiply quantization table entries

errorFactor = 1.0               # factor by which shown errors are enhanced

showWalshHadamard = False       # 'd' shows either DCT or Walsh-Hadamard basis functions

debugOutput = False             # if true, output encoding to debug.txt

# "constants"

windowWidth = 600               # window width
windowHeight = 600              # window height

minLum = 16                     # min luminance (Y) value storable
maxLum = 235                    # max luminance (Y) value storable

blockSize = 8                   # 8x8 DCT blocks

zoom = 1.0                      # amount by which to zoom image
translate = (0.0,0.0)           # amount by which to translate image

prevZoom = None
prevTranslate = None

imageDir      = 'images'
imageFilename = 'nime.png'

YCbCr_white = (255,128,128)

texID = None


# File dialog

if useTK:
  import Tkinter, tkFileDialog
  root = Tkinter.Tk()
  root.withdraw()


# Quantization tables

quantizationTable = np.array( [
    
    [ [ 16,  11,  10,  16,  24,  40,  51,  61 ], # for Y
      [ 12,  12,  14,  19,  26,  58,  60,  55 ],
      [ 14,  13,  16,  24,  40,  57,  69,  56 ],
      [ 14,  17,  22,  29,  51,  87,  80,  62 ],
      [ 18,  22,  37,  56,  68, 109, 103,  77 ],
      [ 24,  35,  55,  64,  81, 104, 113,  92 ],
      [ 49,  64,  78,  87, 103, 121, 120, 101 ],
      [ 72,  92,  95,  98, 112, 100, 103,  99 ] ],

    [ [ 17,  18,  24,  47,  99,  99,  99,  99 ], # for Cr
      [ 18,  21,  26,  66,  99,  99,  99,  99 ],
      [ 24,  26,  56,  99,  99,  99,  99,  99 ],
      [ 47,  66,  99,  99,  99,  99,  99,  99 ],
      [ 99,  99,  99,  99,  99,  99,  99,  99 ],
      [ 99,  99,  99,  99,  99,  99,  99,  99 ],
      [ 99,  99,  99,  99,  99,  99,  99,  99 ],
      [ 99,  99,  99,  99,  99,  99,  99,  99 ] ],

    [ [ 17,  18,  24,  47,  99,  99,  99,  99 ], # for Cb
      [ 18,  21,  26,  66,  99,  99,  99,  99 ],
      [ 24,  26,  56,  99,  99,  99,  99,  99 ],
      [ 47,  66,  99,  99,  99,  99,  99,  99 ],
      [ 99,  99,  99,  99,  99,  99,  99,  99 ],
      [ 99,  99,  99,  99,  99,  99,  99,  99 ],
      [ 99,  99,  99,  99,  99,  99,  99,  99 ],
      [ 99,  99,  99,  99,  99,  99,  99,  99 ] ]
] ).astype( np.intc )


# Zig-zag mapping from 2D DCT to 1D encoding

zigzag = np.array( [
    [  0,  1,  5,  6, 14, 15, 27, 28 ],
    [  2,  4,  7, 13, 16, 26, 29, 42 ],
    [  3,  8, 12, 17, 25, 30, 41, 43 ],
    [  9, 11, 18, 24, 31, 40, 44, 53 ],
    [ 10, 19, 23, 32, 39, 45, 52, 54 ],
    [ 20, 22, 33, 38, 46, 51, 55, 60 ],
    [ 21, 34, 37, 47, 50, 56, 59, 61 ],
    [ 35, 36, 48, 49, 57, 58, 62, 63 ]
] ).astype( np.intc )



# Apply JPEG compression to inputImage
#
# Store compressed values in two arrays: DCencoding[k][i] and ACencoding[k][i].
#
#    k = 0,1,2 for Y,Cb,Cr
#    i = index of next unused space in array
#        ( i should be kept updated in DCencodingIndex[k] and ACencodingIndex[k]. )


DCencoding = None
ACencoding = None

DCencodingIndex = [0,0,0]
ACencodingIndex = [0,0,0]
    
debug = False


def forwardJPEG():

    global DCencoding, ACencoding, DCencodingIndex, ACencodingIndex

    # Set up arrays to receive DC and AC components
    #
    # DC array is 3 x numberOfBlocks x 1
    # AC array is 3 x numberOfBlocks x 63   (63 = blockSize*blockSize-1)

    DCencoding = np.empty( (3, int((Nrows/blockSize)*(Ncols/blockSize))), np.intc )
    ACencoding = np.empty( (3, int((Nrows/blockSize)*(Ncols/blockSize)*(blockSize*blockSize-1))), np.intc )

    # The DCencodingIndex and ACencodingIndex arrays keep track, for
    # each channel k, of the next position in the DCencoding and
    # ACencoding to store a value.
    
    for k in range(3):
        DCencodingIndex[k] = 0
        ACencodingIndex[k] = 0

    # Enumerate blocks in inputImage.  Each is blockSize x blockSize.

    dct = np.empty( (blockSize,blockSize), np.intc )

    for i in range( 0, Nrows, blockSize):

        sys.stdout.write( '\rencoding: %d     ' % ((Nrows-i)/blockSize) )
        sys.stdout.flush()

        for j in range( 0, Ncols, blockSize ): # Apply to block starting at i,j
            for k in range(3):                 # Apply to channel Y (k=0), Cb (k=1), or Cr (k=2)

                # Step 1. Compute DCT of this block of inputImage.  The block
                # has coordinates [i,i+blockSize-1]x[j,j+blockSize-1],
                # and channel, k.  Store the DCT in dct[u][v].

                # YOUR CODE HERE [2 marks]

                pass
              

                # Step 2. Apply quantization.  This will modify the coefficients in dct[u][v].
                # Be sure to use the Quantization Tables (above) and be sure to multiply
                # each divisor by compressionFactor BEFORE USING that divisor; this
                # allows you to adjust the compression.

                # YOUR CODE HERE [1 mark]
              
                pass
              

                # Step 3. Add DC component to DCencoding vector for this
                # channel, k.  See the comment where 'DCencoding' is
                # defined.  Use, then update, the current index in
                # DCencodingIndex[k], which allows the next iteration
                # of the loop to know where to put ITS DC component.

                # YOUR CODE HERE [1 mark]

                pass
              
              
                # Step 4. Add the 63 AC components to the ACencoding vector.
                # Use and update the ACencodingIndex[k] so that the
                # next iteration knows where to start putting ITS 63
                # AC components.
                #
                # YOU MUST USE THE zigzag ARRAY OF INDICES!

                # YOUR CODE HERE [2 marks] 

                pass
              

    # At this point, the 'DCencoding' and 'ACencoding' vectors are
    # filled up.  Normally, JPEG would use DPCM, RLE, and Huffman to
    # further compress these, but this code will not do that.
    #
    # The inverseJPEG() function, below, will take those two vectors
    # and decode them to reconstruct the original image.
              
    sys.stdout.write( '\r                        \r' )
    sys.stdout.flush()

    # Output encodings for debugging

    if debugOutput:

        with open( 'debug.txt', 'w' ) as f:

            for k in range(3):
                f.write( "DCencoding[%d]\n" % k )
                for i in range(DCencodingIndex[k]):
                    f.write( "%d " % DCencoding[k,i] )
                f.write( "\n\n" )

            for k in range(3):
                f.write( "ACencoding[%d]\n" % k )
                for i in range(ACencodingIndex[k]):
                    f.write( "%d " % ACencoding[k,i] )
                f.write( "\n\n" )


# Apply JPEG decompression
#
# Store image in jpegImage
#
# Use the compressed values from DCencoding[k][i] and ACencoding[k][i],
# which were filled in by forwardJPEG().
#
# No RLE or DPCM or Huffman coding is done.


def inverseJPEG():

    global DCencoding, ACencoding, DCencodingIndex, ACencodingIndex, jpegImage
    
    # Decode and put the Y, Cb, Cr components into image[k][x][y]
    #
    # After this: image[0][x][y] = Y
    #             image[1][x][y] = Cr
    #             image[2][x][y] = Cb

    image = np.empty( (Nrows, Ncols, 3), np.intc )
 
    for k in range(3):
        DCencodingIndex[k] = 0
        ACencodingIndex[k] = 0

    # Enumerate blocks in image.  Each is blockSize x blockSize.
    #
    # DO NOT USE 8.  USE blockSize INSTEAD.  DO THIS EVERYWHERE.

    dct = np.empty( (blockSize,blockSize), np.intc )

    for i in range(0, Nrows, blockSize):

        sys.stdout.write( '\rdecoding: %d     ' % ((Nrows-i)/blockSize) )
        sys.stdout.flush()

        for j in range(0, Ncols, blockSize): # Apply to block starting at i,j
            for k in range(3):               # Apply to channel Y (k=0), Cb (k=1), or Cr (k=2)

                # --- Fill the dct[u][v] from the DCencoding[k] and ACencoding[k] vectors. ---

                # Extract AC components from ACencoding vector and put
                # them in dct[u,v].  This is the opposite of Step 4 in
                # forwardJPEG().  Don't forget to use and update ACencodingIndex.

                # YOUR CODE HERE [1 mark]

                pass

              
                # Extract DC component from DCencoding vector.  This
                # is the opposite of Step 3 in forwardJPEG().  Don't
                # forget to use and update DCencodingIndex.

                # YOUR CODE HERE [1 mark]

                pass


                # Reverse the quantization.  This is the opposite of
                # Step 2 in forwardJPEG().

                # YOUR CODE HERE [1 mark]
              
                pass


                # Compute inverse DCT of this block, [i,i+7]x[j,j+7],
                # in this channel, k.  This is the opposite of Step 1
                # in forwardJPEG().  You should fill the image[x,y]
                # array with the three-component pixel values, using
                # dct[,] and dctBases[,,,].

                # YOUR CODE HERE [1 mark]

                pass



    sys.stdout.write( '\r                        \r' )
    sys.stdout.flush()

    # Copy Y, Cb, Cr from image[k][x][y] to jpegImage.pixels[]

    jpegImage = image



# Compute DCT basis functions
#
# Fill in the dctBases[u][v][x][y] array with DCT basis functions


dctBases = np.empty( (blockSize,blockSize,blockSize,blockSize), np.single )


def computeDCTBases():

    PI = 3.14159
    recipRoot2 = 1/np.sqrt(2)
 
    alphaU = 0.0
    alphaV = 0.0

    for u in range(blockSize):
        alphaU = (recipRoot2 if u == 0 else 1)

        for v in range(blockSize):
            alphaV = (recipRoot2 if v == 0 else 1)

            # Fill in dctBases[u][v]

            for x in range(blockSize):
                for y in range(blockSize):
                    dctBases[u][v][x][y] = 0.25 * alphaU * alphaV * np.cos( (2*x+1)*u*PI/(2*blockSize) ) * np.cos( (2*y+1)*v*PI/(2*blockSize) )




# Display the DCT basis functions


def showDCT():

    global outputImage, dctImage, translate
    
    # Find dimensions and factors
 
    separator = 3

    n = blockSize * blockSize + (blockSize+1) * separator; # rows & columns needed

    minDim = 0                   # min window dimension
    if windowWidth < windowHeight:
        minDim = windowWidth
    else:
        minDim = windowHeight - 20  # 20 for message at bottom

    factor = int(minDim / n)          # factor by which to scale dctBases[][]

    # Find min & max values

    min = 0.0
    max = 0.0

    for u in range(blockSize):
        for v in range(blockSize):
            for x in range(blockSize):
                for y in range(blockSize):
                    c = dctBases[u,v,x,y]
                    if c < min:
                        min = c
                    if c > max:
                        max = c

    # We'll assume that min<0 and max>0
    #
    # Set min and max to be equidistant from 0.

    if -min > max:
        max = -min
    else:
        min = -max

    # Draw the image
            
    start = int(np.round_( factor*(0.5*separator) ))
    end   = int(np.round_( factor*(blockSize*blockSize + (blockSize+0.5)*separator) ))

    dctImage = np.empty( (start+end+2,start+end+2,3), np.uint8 )

    # white background

    dctImage[:,:,:] = YCbCr_white

    # Draw each basis function

    for u in range(blockSize):
        for v in range(blockSize):
            
            for x in range(blockSize):
                xStart = factor * (u*blockSize + (u+1)*separator + x)

                for y in range(blockSize):
                    yStart = factor * (v*blockSize + (v+1)*separator + y)

                    if showWalshHadamard:
                        c = ( np.round_( (dctBases[u,v,x,y] - min) / (max-min) ) * 255, 128, 128 ) # grey level
                    else:
                        c = ( np.round_( (dctBases[u,v,x,y] - min) / (max-min) * 255 ), 128, 128 )

                    for i in range(factor):
                        for j in range(factor):
                            dctImage[xStart+i,yStart+j] = c

    # Separate with lines

    start = int(np.round_( factor*(0.5*separator) ))
    end   = int(np.round_( factor*(blockSize*blockSize + (blockSize+0.5)*separator) ))

    for u in range(blockSize+1):
        x = int(np.round_( factor * (u*blockSize + (u+0.5)*separator) ))
        for y in range(start,end+1):
            dctImage[x,y,:] = ( 203, 86, 75 )
            dctImage[y,x,:] = ( 203, 86, 75 )

    outputImage = dctImage.copy()
    

# Display the difference between inputImage and jpegImage


def showError():

    global errorImage

    errorImage = np.empty( (Nrows,Ncols,3), np.uint8 )

    for i in range(Nrows):
        for j in range(Ncols):

            c1 = inputImage[i,j]
            c2 = jpegImage[i,j]

            yErr  = np.clip( errorFactor * (c1[0] - c2[0]) + 127.5, 0, 255 )
            CrErr = np.clip( errorFactor * (c1[1] - c2[1]) + 127.5, 0, 255 )
            CbErr = np.clip( errorFactor * (c1[2] - c2[2]) + 127.5, 0, 255 )

            errorImage[i,j] = ( np.round_(yErr), np.round_(CrErr), np.round_(CbErr) )




# ---------------- I/O: OpenGL, mouse, keyword, and file ----------------



# Draw to window

def display():

    # Clear window

    glClearColor ( 1, 1, 1, 0 )
    glClear( GL_COLOR_BUFFER_BIT )

    glMatrixMode( GL_PROJECTION )
    glLoadIdentity()

    glMatrixMode( GL_MODELVIEW )
    glLoadIdentity()
    glOrtho( 0, windowWidth, 0, windowHeight, 0, 1 )

    # Set up texturing

    global texID

    if texID == None:
      texID = glGenTextures(1)

    glBindTexture( GL_TEXTURE_2D, texID )

    glTexEnvf(GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE, GL_REPLACE)
    glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER)
    glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_BORDER)
    glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
    glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexParameterfv(GL_TEXTURE_2D, GL_TEXTURE_BORDER_COLOR, [1,0,0,1] );

    # Put the image into a texture, then draw it

    imgData = ycbcr2rgb( outputImage )

    glBindTexture( GL_TEXTURE_2D, texID )
    glTexImage2D( GL_TEXTURE_2D, 0, GL_RGB, outputImage.shape[1], outputImage.shape[0], 0, GL_RGB, GL_UNSIGNED_BYTE, imgData )

    # Include zoom and translate for window coordinates

    baseX = translate[0]
    baseY = translate[1]
    height = zoom * outputImage.shape[0] # actual height and width, in pixels
    width  = zoom * outputImage.shape[1]

    # Include zoom and translate for texture coordinates

    cx     = 0.5
    cy     = 0.5
    offset = 0.5

    # Find lower-left corner

    glEnable( GL_TEXTURE_2D )

    glBegin( GL_QUADS )
    glTexCoord2f( cx-offset, cy-offset )
    glVertex2f( baseX, baseY )
    glTexCoord2f( cx+offset, cy-offset )
    glVertex2f( baseX+width, baseY )
    glTexCoord2f( cx+offset, cy+offset )
    glVertex2f( baseX+width, baseY+height )
    glTexCoord2f( cx-offset, cy+offset )
    glVertex2f( baseX, baseY+height )
    glEnd()

    glDisable( GL_TEXTURE_2D )

    # if zoom != 1 or translate != (0,0):
    #     glColor3f( 0.8, 0.8, 0.8 )
    #     glBegin( GL_LINE_LOOP )
    #     glVertex2f( baseX, baseY )
    #     glVertex2f( baseX+width, baseY )
    #     glVertex2f( baseX+width, baseY+height )
    #     glVertex2f( baseX, baseY+height )
    #     glEnd()

    # Status message: "image filename | compression = #.#"

    msg = imageFilename

    if compressionFactor >= 1:
        msg = msg + " | compression = %.1f" % compressionFactor
    else:
        msg = msg + " | compression = %.2f" % compressionFactor

    msg = msg + " | error enhancement = %.1f" % errorFactor

    if debugOutput:
        msg = msg + " | DEBUG"

    glColor3f( 0.5, 0.2, 0.4 )
    drawText( windowWidth-len(msg)*8-8, 12, msg )

    # Done

    glutSwapBuffers()



# Convert YCbCr numpy array to RGB
#
# From stackoverflow.com/questions/34913005/color-space-mapping-ycbcr-to-rgb


def ycbcr2rgb(im):

    xform = np.array([[1, 0, 1.402], [1, -0.34414, -.71414], [1, 1.772, 0]])
    rgb = im.astype(np.float)
    rgb[:,:,[1,2]] -= 128
    rgb = rgb.dot(xform.T)
    np.putmask(rgb, rgb > 255, 255)
    np.putmask(rgb, rgb < 0, 0)
    return np.uint8(rgb)
 


# Draw text in window

def drawText( x, y, text ):

    glRasterPos( x, y )
    for ch in text:
      glutBitmapCharacter( GLUT_BITMAP_8_BY_13, ord(ch) )


# Handle window reshape

def reshape( newWidth, newHeight ):

    global windowWidth, windowHeight

    windowWidth  = newWidth
    windowHeight = newHeight

    glViewport( 0, 0, windowWidth, windowHeight )

    glutPostRedisplay()



# Handle mouse click


currentButton = None
initX = 0
initY = 0
initZoom = 0
initTranslate = (0,0)

def mouse( button, state, x, y ):

  global currentButton, initX, initY, initZoom, initTranslate

  if state == GLUT_DOWN:

    currentButton = button
    initX = x
    initY = y
    initZoom = zoom
    initTranslate = translate

  elif state == GLUT_UP:

    currentButton = None

    if button == GLUT_LEFT_BUTTON and initX == x and initY == y:

        # Process a left click (with no dragging)
        pass

    glutPostRedisplay()



# Handle mouse dragging
#
# Zoom out/in with right button dragging up/down.
# Translate with left button dragging.


def mouseMotion( x, y ):

    global zoom, translate

    if currentButton == GLUT_RIGHT_BUTTON: # zoom

        factor = 1 # controls the zoom rate

        if y > initY: # zoom in
          zoom = initZoom * (1 + factor*(y-initY)/float(windowHeight))

          zoomRatio = zoom/initZoom
          cx = windowWidth/2
          cy = windowHeight/2 
          translate = ( zoomRatio*(initTranslate[0]-cx)+cx, zoomRatio*(initTranslate[1]-cy)+cy )

        else: # zoom out

          zoom = initZoom / (1 + factor*(initY-y)/float(windowHeight))

          zoomRatio = zoom/initZoom
          cx = windowWidth/2
          cy = windowHeight/2 
          translate = ( zoomRatio*(initTranslate[0]-cx)+cx, zoomRatio*(initTranslate[1]-cy)+cy )

        glutPostRedisplay()

    elif currentButton == GLUT_LEFT_BUTTON: # translate

        translate = ( initTranslate[0] + (x-initX), initTranslate[1] + (initY-y) )

        glutPostRedisplay()



  
def keyboard( key, x, y ):

    global image, imageFilename, inputImage, outputImage, jpegImage, showWalshHadamard, debugOutput, compressionFactor, errorFactor, translate, zoom, prevZoom, prevTranslate

    if key == b'\033': # ESC = exit
        sys.exit(0)

    if prevZoom is not None:
      zoom = prevZoom
      translate = prevTranslate
      prevZoom = None

    if key == b'i':

        if useTK:
            imagePath = tkFileDialog.askopenfilename( initialdir=imageDir )
            if imagePath:
                inputImage = loadImage( imagePath )
                outputImage = inputImage 
                imageFilename = os.path.basename( imagePath )

    elif key == b'c':
        forwardJPEG()
        inverseJPEG() # produces 'jpegImage'
        outputImage = jpegImage

    elif key == b'o':
        outputImage = inputImage

    elif key == b'j':
        if jpegImage is not None:
            outputImage = jpegImage

    elif key == b'd':
        showWalshHadamard = False
        showDCT()
        prevTranslate = translate
        prevZoom = zoom
        translate = ((windowWidth-outputImage.shape[1])/2, (windowHeight-outputImage.shape[0])/2)
        zoom = 1

    elif key == b'e':
        if jpegImage is not None:
            showError() # produces 'errorImage'
            outputImage = errorImage

    elif key == b'w':
        showWalshHadamard = True
        showDCT()
        prevTranslate = translate
        prevZoom = zoom
        translate = ((windowWidth-outputImage.shape[1])/2, (windowHeight-outputImage.shape[0])/2)
        zoom = 1

    elif key == b'x':
        debugOutput = not debugOutput

    elif key in [ b'-', b'_' ]:
        if compressionFactor > 0.1:
            compressionFactor /= 1.2
            forwardJPEG()
            inverseJPEG()
            outputImage = jpegImage

    elif key in [ b'+', b'=' ]:
        compressionFactor *= 1.2
        forwardJPEG()
        inverseJPEG()
        outputImage = jpegImage

    elif key in [ b'<', b',' ]:
        errorFactor /= 1.1
        if jpegImage is not None:
          showError()
          outputImage = errorImage

    elif key in [ b'>', b'.' ]:
        errorFactor *= 1.1
        if jpegImage is not None:
          showError()
          outputImage = errorImage

    elif key == b'?':
    
        print( '''keys:
        i   get image from file (only if useTK = True in the code)
        c   compute and show JPEG after compression/decompression
        e   show error after JPEG compression/decompression
        o   show original image
        j   show JPEG after compression/decompression
        d   show DCT basis functions
        w   show Walsh/Hadamard basis functions
        x   toggle debugging output to debug.txt

        -   decrease compression
        +   increase compression
        <   decrease error exaggeration
        >   increase error exaggeration

        ?   help
        ESC exit

        mouse left drag          - move the image
        mouse right drag up/down - zoom the image''' )

    glutPostRedisplay()


    
# Handle special key (e.g. arrows) input

def special( key, x, y ):

  if key == GLUT_KEY_DOWN:
    pass

  elif key == GLUT_KEY_UP:
    pass

  glutPostRedisplay()




# Load an image
#
# Return the image as a 2D numpy array of unsigned bytes
#
# IMPORTANT NOTE: Pillow's conversion to YCbCr uses the *JPEG*
# conversion equations, which have all components in the full [0,255]
# range.


def loadImage( path ):

    global translate, zoom, Nrows, Ncols
    
    try:
        img = Image.open( path ).convert( 'YCbCr' ).transpose( Image.FLIP_TOP_BOTTOM )
    except:
        print( 'Failed to load image %s' % path )
        sys.exit(1)

    ret = np.array( img, np.uint8 )  # .reshape( (img.size[0],img.size[1],3) )

    # ensure multiple-of-eight dimensions

    if ret.shape[0] % 8 != 0:
        ret = np.append( ret, [ [YCbCr_white]*ret.shape[1] ] * (8 - (ret.shape[0] % 8)), axis=0 )

    if ret.shape[1] % 8 != 0:
        ret = np.append( ret, [[YCbCr_white] * (8 - (ret.shape[1] % 8)) ]*ret.shape[0], axis=1 )

    translate = ((windowWidth-ret.shape[1])/2, (windowHeight-ret.shape[0])/2)
    zoom = 1

    Nrows = ret.shape[0]
    Ncols = ret.shape[1]

    return ret



# ---------------- Initialization ----------------



# The command line (stored in sys.argv) could have:
#
#     main.py {image filename}

if len(sys.argv) > 1:
    imageFilename = sys.argv[1]

imagePath = os.path.join( imageDir, imageFilename )
inputImage = loadImage( imagePath )
outputImage = inputImage.copy()


# Compute and store the DCT basis functions

computeDCTBases()


# If commands exist on the command line (i.e. there are more than one
# argument), process each command, then exit.  Otherwise, go into
# interactive mode.

if len(sys.argv) > 2:

  # process commands

  cmds = sys.argv[2:]

  while len(cmds) > 0:
    cmd = cmds.pop(0)
    if cmd == 'f':
      pass
    else:
      print( """
command '%s' not understood.
command-line arguments:
""" % cmd )

else:
      
  # Run OpenGL

  glutInit()
  glutInitDisplayMode( GLUT_DOUBLE | GLUT_RGB )
  glutInitWindowSize( windowWidth, windowHeight )
  glutInitWindowPosition( 50, 50 )

  glutCreateWindow( 'JPEG encoder/decoder' )

  glutDisplayFunc( display )
  glutKeyboardFunc( keyboard )
  glutSpecialFunc( special )
  glutReshapeFunc( reshape )
  glutMouseFunc( mouse )
  glutMotionFunc( mouseMotion )

  glTexEnvf(GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE, GL_REPLACE)
  glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER)
  glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_BORDER)
  glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
  glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
  glTexParameterfv(GL_TEXTURE_2D, GL_TEXTURE_BORDER_COLOR, [1,0,0,1] )

  glEnable( GL_TEXTURE_2D )
  glDisable( GL_DEPTH_TEST )

  glutMainLoop()
