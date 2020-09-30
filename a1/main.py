# CMPE 457 Assignment 1 - Image manipulation
# 
# Declan Rowett - 10211314
# Sept. 29th, 2020
# 
# Notes to TA:
#   • I have created Y = 0 as a global variable
#   • Image editing is cool

import sys, os, numpy, math

try: # Pillow
  from PIL import Image
except:
  print( 'Error: Pillow has not been installed.' )
  sys.exit(0)

try: # PyOpenGL
  from OpenGL.GLUT import *
  from OpenGL.GL import *
  from OpenGL.GLU import *
except:
  print( 'Error: PyOpenGL has not been installed.' )
  sys.exit(0)



haveTK = True # sys.platform != 'darwin'


# Globals

windowWidth  = 600 # window dimensions
windowHeight =  800

localHistoRadius = 5  # distance within which to apply local histogram equalization

Y = 0  # for clarity when accessing the intensity of a pixel


# Current image

imgDir      = 'images'
imgFilename = 'mandrill.png'

currentImage = Image.open( os.path.join( imgDir, imgFilename ) ).convert( 'YCbCr' ).transpose( Image.FLIP_TOP_BOTTOM )
tempImage    = None



# File dialog (doesn't work on Mac OSX)

if haveTK:
  import Tkinter, tkFileDialog
  root = Tkinter.Tk()
  root.withdraw()



# Apply brightness and contrast to tempImage and store in
# currentImage.  The brightness and constrast changes are always made
# on tempImage, which stores the image when the left mouse button was
# first pressed, and are stored in currentImage, so that the user can
# see the changes immediately.  As long as left mouse button is held
# down, tempImage will not change.

def applyBrightnessAndContrast( brightness, contrast ):

  width  = currentImage.size[0]
  height = currentImage.size[1]

  srcPixels = tempImage.load()
  dstPixels = currentImage.load()

  for x in range(width):
    for y in range(height):
      pixel = list(srcPixels[x,y])  # have to convert from immutable tuple to a list

      newIntensity = contrast * pixel[Y] + brightness

      # Enforce intensity limits
      if newIntensity > 255:
        newIntensity = 255
      elif newIntensity < 0:
        newIntensity = 0

      pixel[Y] = newIntensity
      dstPixels[x,y] = tuple(pixel)

  print( 'adjust brightness = %f, contrast = %f' % (brightness,contrast) )

  

# Perform local histogram equalization on the current image using the given radius.

def performHistoEqualization( radius ):

  pixels = currentImage.load()
  width  = currentImage.size[0]
  height = currentImage.size[1]

  lookup = {}  # maps individual pixels to their equalized intensities

  for x in range(width):
    for y in range(height):

      # Create a local histogram with zero count for each intensity value
      localHistogram = {key: 0 for key in range(256)}

      for xOffset in range(-radius, radius + 1):
        for yOffset in range(-radius, radius + 1):
          xLocal = x + xOffset
          yLocal = y + yOffset

          # Enforce coordinate limits
          if xLocal < 0:
            xLocal = 0
          elif xLocal >= width:
            xLocal = width - 1
          if yLocal < 0:
            yLocal = 0
          elif yLocal >= height:
            yLocal = height - 1

          # Increase count of intensity value in local histogram
          pixel = list(pixels[xLocal, yLocal])
          localHistogram[pixel[Y]] += 1

      pixel = list(pixels[x,y])

      # Sum up all pixel intensities up to and including 
      # center pixel intensity (summing as lists is a bit faster)
      runningSum = sum([count for intensity, count in localHistogram.items() if intensity <= pixel[Y]])

      # Store resulting intensity of local histogram equalization 
      # transformation in lookup table at current pixel coordinates
      lookup[(x,y)] = (256/(2 * radius + 1) ** 2) * runningSum - 1

  # Replace each pixel's intensity with the corresponding equalized value
  for x in range(width):
    for y in range(height):
      pixel = list(pixels[x,y])
      pixel[Y] = lookup[(x,y)]
      pixels[x,y] = tuple(pixel)

  print( 'perform local histogram equalization with radius %d' % radius )



# Scale the tempImage by the given factor and store it in
# currentImage.  Use backward projection.  This is called when the
# mouse is moved with the right button held down.

def scaleImage( factor ):

  width  = currentImage.size[0]
  height = currentImage.size[1]

  srcPixels = tempImage.load()
  dstPixels = currentImage.load()

  # Uses backward projection with bilinear interpolation
  for xDst in range(width):
    for yDst in range(height):

      # 3x3 homogeneous transformation matrix consists of:
      #   • translation by (-width/2, -height/2)
      #   • scaling by factor
      #   • translation by (+width/2, +height/2)

      # Set values for x and y using inverse of the transformation matrix
      x = (1/factor) * (xDst - width/2 * (1 - factor))
      y = (1/factor) * (yDst - height/2 * (1 - factor))

      # Define values needed for bilinear interpolation
      floorX = math.floor(x)
      floorY = math.floor(y)
      alpha = x - floorX
      beta = y - floorY

      # Enforce coordinate limits
      if floorX + 1 >= width:
        floorX = width - 2
      elif floorX < 0:
        floorX = 0
      if floorY + 1 >= height:
        floorY = height - 2
      elif floorY < 0:
        floorY = 0

      # Perform bilinear interpolation on backward projected pixel
      interpolatedIntensity = (1 - alpha) * (1 - beta) * srcPixels[floorX, floorY][Y] + \
                              (1 - alpha) * beta * srcPixels[floorX, floorY + 1][Y] + \
                              alpha * (1 - beta) * srcPixels[floorX + 1, floorY][Y] + \
                              alpha * beta * srcPixels[floorX + 1, floorY + 1][Y]

      # Map to pixel only if within bounds of original image
      if width > x >= 0 and height > y >= 0:
        pixel = list(srcPixels[x,y])
        pixel[Y] = interpolatedIntensity
        dstPixels[xDst, yDst] = tuple(pixel)

      # Otherwise, make the pixel white
      else:
        dstPixels[xDst, yDst] = (255, 128, 128)

  print( 'scale image by %f' % factor )

  

# Set up the display and draw the current image

def display():

  # Clear window

  glClearColor ( 1, 1, 1, 0 )
  glClear( GL_COLOR_BUFFER_BIT )

  # rebuild the image

  img = currentImage.convert( 'RGB' )

  width  = img.size[0]
  height = img.size[1]

  # Find where to position lower-left corner of image

  baseX = (windowWidth-width)/2
  baseY = (windowHeight-height)/2

  glWindowPos2i( baseX, baseY )

  # Get pixels and draw

  imageData = numpy.array( list( img.getdata() ), numpy.uint8 )

  glDrawPixels( width, height, GL_RGB, GL_UNSIGNED_BYTE, imageData )

  glutSwapBuffers()


  
# Handle keyboard input

def keyboard( key, x, y ):

  global localHistoRadius

  if key == '\033': # ESC = exit
    sys.exit(0)

  elif key == 'l':
    if haveTK:
      path = tkFileDialog.askopenfilename( initialdir = imgDir )
      if path:
        loadImage( path )

  elif key == 's':
    if haveTK:
      outputPath = tkFileDialog.asksaveasfilename( initialdir = '.' )
      if outputPath:
        saveImage( outputPath )

  elif key == 'h':
    performHistoEqualization( localHistoRadius )

  elif key in ['+','=']:
    localHistoRadius = localHistoRadius + 1
    print( 'radius =', localHistoRadius )

  elif key in ['-','_']:
    localHistoRadius = localHistoRadius - 1
    if localHistoRadius < 1:
      localHistoRadius = 1
    print( 'radius =', localHistoRadius )

  else:
    print( 'key =', key )    # DO NOT REMOVE THIS LINE.  It will be used during automated marking.

  glutPostRedisplay()



# Load and save images.
#
# Modify these to load to the current image and to save the current image.
#
# DO NOT CHANGE THE NAMES OR ARGUMENT LISTS OF THESE FUNCTIONS, as
# they will be used in automated marking.


def loadImage( path ):

  global currentImage

  currentImage = Image.open( path ).convert( 'YCbCr' ).transpose( Image.FLIP_TOP_BOTTOM )


def saveImage( path ):

  global currentImage

  currentImage.transpose( Image.FLIP_TOP_BOTTOM ).convert('RGB').save( path )
  


# Handle window reshape


def reshape( newWidth, newHeight ):

  global windowWidth, windowHeight

  windowWidth  = newWidth
  windowHeight = newHeight

  glutPostRedisplay()



# Mouse state on initial click

button = None
initX = 0
initY = 0



# Handle mouse click/release

def mouse( btn, state, x, y ):

  global button, initX, initY, tempImage

  if state == GLUT_DOWN:
    tempImage = currentImage.copy()
    button = btn
    initX = x
    initY = y
  elif state == GLUT_UP:
    tempImage = None
    button = None

  glutPostRedisplay()

  

# Handle mouse motion

def motion( x, y ):

  if button == GLUT_LEFT_BUTTON:

    diffX = x - initX
    diffY = y - initY

    applyBrightnessAndContrast( 255 * diffX/float(windowWidth), 1 + diffY/float(windowHeight) )

  elif button == GLUT_RIGHT_BUTTON:

    initPosX = initX - float(windowWidth)/2.0
    initPosY = initY - float(windowHeight)/2.0
    initDist = math.sqrt( initPosX*initPosX + initPosY*initPosY )
    if initDist == 0:
      initDist = 1

    newPosX = x - float(windowWidth)/2.0
    newPosY = y - float(windowHeight)/2.0
    newDist = math.sqrt( newPosX*newPosX + newPosY*newPosY )

    scaleImage( newDist / initDist )

  glutPostRedisplay()
  


# Run OpenGL

glutInit()
glutInitDisplayMode( GLUT_DOUBLE | GLUT_RGB )
glutInitWindowSize( windowWidth, windowHeight )
glutInitWindowPosition( 50, 50 )

glutCreateWindow( 'imaging' )

glutDisplayFunc( display )
glutKeyboardFunc( keyboard )
glutReshapeFunc( reshape )
glutMouseFunc( mouse )
glutMotionFunc( motion )

glutMainLoop()
