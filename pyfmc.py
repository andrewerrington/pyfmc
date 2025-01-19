#!/usr/bin/env python3

# X-Plane FMC

# Uses X-Plane UDP communication to get FMC screen contents from server
# and send FMC keypresses to server.

# Licenced under GPL v3

# Copyright 2021 Andrew Errington
# All rights reserved

# Portions adapted from
# https://github.com/charlylima/XPlaneUDP/blob/master/examples/XPlane10MulticastBeacon.py


import pygame as pg
import socket
import struct
import binascii
import time
import select

class XPlaneIpNotFound(Exception):
  args="Could not find any running XPlane instance in network."

class XPlaneTimeout(Exception):
  args="XPlane timeout."

"""
Make sure these characters are present in the chosen font.
\u00b0 - degree symbol
\u2610 - ballot box
\u2190, \u2191, \u2192, \u2193 - left, up, right, down arrows
\u0394 - Greek capital delta
\u2b21 - white hexagon
\u25c0 - left triangle
\u25b6 - right triangle

Font attributes and colours:
Large/small font (bit 7)
Reverse video (bit 6)
Flashing (bit 5)
Underline (bit 4)
Colours: bits 3:0
0-Black, 1-Cyan, 2-Red, 3-Yellow,
4-Green, 5-Magenta, 6-Amber, 7-White
"""

class XPlaneUdp:

  '''
  Get data from XPlane via network.
  Use a class to implement RAI Pattern for the UDP socket.
  '''

  #constants
  UDP_PORT = 49000
  MCAST_GRP = "239.255.1.1"
  MCAST_PORT = 49707 # (MCAST_PORT was 49000 for XPlane10)

  def __init__(self):
    # Open a UDP Socket to receive on Port 49000
    self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    self.socket.settimeout(3.0)
    # list of requested datarefs with index
    self.allDatarefs = {} # key = idx, value = dataref
    self.unseenDatarefs = []  # Contains datarefs we haven't seen yet this cycle
    # Beacon information from X-Plane
    self.BeaconData = {}
    self.defaultFreq = 4
    self.idxvals={} # key = idx, value = int
    self.totalVals=0

  def __del__(self):
    print("Unsubscribing datarefs")
    for dataref in self.allDatarefs.values():
      cmd = b"RREF\x00"
      message = struct.pack("<5sii400s", cmd, 0, 0, dataref.encode('utf-8'))
      assert(len(message)==413)
      self.socket.sendto(message, (self.BeaconData["IP"], self.UDP_PORT))
      time.sleep(0.001)

    self.socket.close()

  def SendCommand(self, command):
    print("Sending: '%s'"%command)
    msg = struct.pack('=5s500s', b'CMND', command.encode('utf-8'))
    self.socket.sendto(msg, (self.BeaconData["IP"], self.UDP_PORT))

  def RequestDataRefs(self):
    '''
    Send a request to subscribe to all datarefs. Split into batches so that X-Plane can handle the load.
    '''

    # Request datarefs in blocks of 100, with a short pause between blocks.
    for i in range(0,len(self.unseenDatarefs),100):
      print("Block %s of %s"%((i//100),len(self.unseenDatarefs)//100))
      for dataref in self.unseenDatarefs[i:i+100]:

        idx = list(self.allDatarefs.keys())[list(self.allDatarefs.values()).index(dataref)]
        freq = self.defaultFreq        
        cmd = b"RREF\x00"

        message = struct.pack("<5sii400s", cmd, freq, idx, dataref.encode('utf-8'))
        assert(len(message)==413)
        self.socket.sendto(message, (self.BeaconData["IP"], self.UDP_PORT))

      time.sleep(0.1)     # Sleep for 100ms before requesting more


  def AddDataRef(self, dataref, idx):

    self.allDatarefs[idx]=dataref
    self.unseenDatarefs.append(dataref)

  def restoreUnseen(self):
    self.unseenDatarefs=list(self.allDatarefs.values())

  def GetValues(self):
    while True:
      # Receive packet (we should get a packet in less than 1s)
      dataIn, dataOut, dataErr = select.select([self.socket],[],[],0)
      if dataIn:
        #print("Got some data.")
        data, addr = self.socket.recvfrom(1500) # buffer size
        # Decode Packet
        retvalues = {}
        #print("Length is %i"%len(data))
        #print("Contains %i"%data.count(b"RREF"))
        # * Read the Header "RREFO".
        header=data[0:5]
        if(header!=b"RREF,"): # (was b"RREFO" for XPlane10)
          print("Unknown packet: ", binascii.hexlify(data))
        else:
          # We get 8 bytes for every dataref sent:
          # An integer for idx and the float value.
          values = data[5:]
          lenvalue = 8
          numvalues = int(len(values) / lenvalue)
          #print("Contains %i"%numvalues)
          self.totalVals+=numvalues
          for i in range(0, numvalues):
            singledata = data[(5 + lenvalue * i): (5 + lenvalue * (i + 1))]
            (idx,value) = struct.unpack("<if", singledata)
            self.idxvals[idx] = int(value)  # Luckily, everything is an INT
            try:
              self.unseenDatarefs.remove(self.allDatarefs[idx])
            except ValueError:
              pass
      else:
        # No data
        break

    return self.idxvals

  def FindIp(self):

      '''
      Find the IP of XPlane Host in Network.
      It takes the first one it can find.
      '''

      self.BeaconData = {}

      # open socket for multicast group.
      sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
      sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
      sock.bind((self.MCAST_GRP, self.MCAST_PORT)) # Linux
      #sock.bind(('', self.MCAST_PORT)) # Windows (sigh)
      mreq = struct.pack("=4sl", socket.inet_aton(self.MCAST_GRP), socket.INADDR_ANY)
      sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
      sock.settimeout(3.0)

      while not self.BeaconData:

        # receive data
        try:
          print("Listening for BECN.")
          packet, sender = sock.recvfrom(15000)

          # decode data
          # * Header
          header = packet[0:5]
          if header != b"BECN\x00":
            print("Unknown packet from "+sender[0])
            print(str(len(packet)) + " bytes")
            print(packet)
            print(binascii.hexlify(packet))
          else:
            # * Data
            print("Got BECN")
            data = packet[5:21]
            # struct becn_struct
            # {
            # 	uchar beacon_major_version;		// 1 at the time of X-Plane 10.40
            # 	uchar beacon_minor_version;		// 1 at the time of X-Plane 10.40
            # 	xint application_host_id;			// 1 for X-Plane, 2 for PlaneMaker
            # 	xint version_number;			// 104014 for X-Plane 10.40b14
            # 	uint role;						// 1 for master, 2 for extern visual, 3 for IOS
            # 	ushort port;					// port number X-Plane is listening on
            # 	xchr	computer_name[strDIM];		// the hostname of the computer 
            # };
            beacon_major_version = 0
            beacon_minor_version = 0
            application_host_id = 0
            xplane_version_number = 0
            role = 0
            port = 0
            (
              beacon_major_version,  # 1 at the time of X-Plane 10.40
              beacon_minor_version,  # 1 at the time of X-Plane 10.40
              application_host_id,   # 1 for X-Plane, 2 for PlaneMaker
              xplane_version_number, # 104014 for X-Plane 10.40b14
              role,                  # 1 for master, 2 for extern visual, 3 for IOS
              port,                  # port number X-Plane is listening on
              ) = struct.unpack("<BBiiIH", data)
            computer_name = packet[21:-1]
            print(beacon_major_version)
            print(beacon_minor_version) # 2 for X-Plane 11
            print(application_host_id)
            if beacon_major_version == 1 \
               and beacon_minor_version == 2 \
               and application_host_id == 1:
                self.BeaconData["IP"] = sender[0]
                self.BeaconData["Port"] = port
                self.BeaconData["hostname"] = computer_name.decode()
                self.BeaconData["XPlaneVersion"] = xplane_version_number
                self.BeaconData["role"] = role

        except socket.timeout:
          raise XPlaneIpNotFound()

      sock.close()
      return self.BeaconData




# Main code starts here

cdu = 1               # Which CDU are we displaying (1=Pilot or 2=Co-Pilot)

xp = XPlaneUdp()

f = 3                 # Dataref update frequency

fetch_chars = 24      # How much data to fetch (max 24 chars)
fetch_lines = 14      # How much data to fetch (max 16 lines)
display_chars = 24    # How many characters to display
display_lines = 15    # How many lines to display

fms_string = '' if cdu==1 else '2'
key_actions = {
  pg.K_F1:'sim/FMS%s/ls_1l'%fms_string,
  pg.K_F2:'sim/FMS%s/ls_2l'%fms_string,
  pg.K_F3:'sim/FMS%s/ls_3l'%fms_string,
  pg.K_F4:'sim/FMS%s/ls_4l'%fms_string,
  pg.K_F5:'sim/FMS%s/ls_5l'%fms_string,
  pg.K_F6:'sim/FMS%s/ls_6l'%fms_string,
  pg.K_F7:'sim/FMS%s/ls_1r'%fms_string,
  pg.K_F8:'sim/FMS%s/ls_2r'%fms_string,
  pg.K_F9:'sim/FMS%s/ls_3r'%fms_string,
  pg.K_F10:'sim/FMS%s/ls_4r'%fms_string,
  pg.K_F11:'sim/FMS%s/ls_5r'%fms_string,
  pg.K_F12:'sim/FMS%s/ls_6r'%fms_string,
  pg.K_ESCAPE:'sim/FMS%s/index'%fms_string,
  pg.K_LEFT:'sim/FMS%s/fpln'%fms_string,
  #pg.K_:'sim/FMS%s/clb'%fms_string,
  #pg.K_:'sim/FMS%s/crz'%fms_string,
  #pg.K_:'sim/FMS%s/des'%fms_string,
  pg.K_DOWN:'sim/FMS%s/dir_intc'%fms_string,
  pg.K_RIGHT:'sim/FMS%s/legs'%fms_string,
  pg.K_COMMA:'sim/FMS%s/dep_arr'%fms_string,
  #pg.K_:'sim/FMS%s/hold'%fms_string,
  #pg.K_:'sim/FMS%s/prog'%fms_string,
  pg.K_RETURN:'sim/FMS%s/exec'%fms_string,
  #pg.K_:'sim/FMS%s/fix'%fms_string,
  #pg.K_:'sim/FMS%s/navrad'%fms_string,
  #pg.K_:'sim/FMS%s/init'%fms_string,
  pg.K_PAGEUP:'sim/FMS%s/prev'%fms_string,
  pg.K_PAGEDOWN:'sim/FMS%s/next'%fms_string,
  pg.K_BACKSPACE:'sim/FMS%s/clear'%fms_string,
  #pg.K_:'sim/FMS%s/direct'%fms_string,
  #pg.K_:'sim/FMS%s/sign'%fms_string,
  #pg.K_:'sim/FMS%s/type_apt'%fms_string,
  #pg.K_:'sim/FMS%s/type_vor'%fms_string,
  #pg.K_:'sim/FMS%s/type_ndb'%fms_string,
  #pg.K_:'sim/FMS%s/type_fix'%fms_string,
  #pg.K_:'sim/FMS%s/type_latlon'%fms_string,
  pg.K_0:'sim/FMS%s/key_0'%fms_string,
  pg.K_1:'sim/FMS%s/key_1'%fms_string,
  pg.K_2:'sim/FMS%s/key_2'%fms_string,
  pg.K_3:'sim/FMS%s/key_3'%fms_string,
  pg.K_4:'sim/FMS%s/key_4'%fms_string,
  pg.K_5:'sim/FMS%s/key_5'%fms_string,
  pg.K_6:'sim/FMS%s/key_6'%fms_string,
  pg.K_7:'sim/FMS%s/key_7'%fms_string,
  pg.K_8:'sim/FMS%s/key_8'%fms_string,
  pg.K_9:'sim/FMS%s/key_9'%fms_string,
  pg.K_a:'sim/FMS%s/key_a'%fms_string,
  pg.K_b:'sim/FMS%s/key_b'%fms_string,
  pg.K_c:'sim/FMS%s/key_c'%fms_string,
  pg.K_d:'sim/FMS%s/key_d'%fms_string,
  pg.K_e:'sim/FMS%s/key_e'%fms_string,
  pg.K_f:'sim/FMS%s/key_f'%fms_string,
  pg.K_g:'sim/FMS%s/key_g'%fms_string,
  pg.K_h:'sim/FMS%s/key_h'%fms_string,
  pg.K_i:'sim/FMS%s/key_i'%fms_string,
  pg.K_j:'sim/FMS%s/key_j'%fms_string,
  pg.K_k:'sim/FMS%s/key_k'%fms_string,
  pg.K_l:'sim/FMS%s/key_l'%fms_string,
  pg.K_m:'sim/FMS%s/key_m'%fms_string,
  pg.K_n:'sim/FMS%s/key_n'%fms_string,
  pg.K_o:'sim/FMS%s/key_o'%fms_string,
  pg.K_p:'sim/FMS%s/key_p'%fms_string,
  pg.K_q:'sim/FMS%s/key_q'%fms_string,
  pg.K_r:'sim/FMS%s/key_r'%fms_string,
  pg.K_s:'sim/FMS%s/key_s'%fms_string,
  pg.K_t:'sim/FMS%s/key_t'%fms_string,
  pg.K_u:'sim/FMS%s/key_u'%fms_string,
  pg.K_v:'sim/FMS%s/key_v'%fms_string,
  pg.K_w:'sim/FMS%s/key_w'%fms_string,
  pg.K_x:'sim/FMS%s/key_x'%fms_string,
  pg.K_y:'sim/FMS%s/key_y'%fms_string,
  pg.K_z:'sim/FMS%s/key_z'%fms_string,
  pg.K_PERIOD:'sim/FMS%s/key_period'%fms_string,
  pg.K_MINUS:'sim/FMS%s/key_minus'%fms_string,
  pg.K_SLASH:'sim/FMS%s/key_slash'%fms_string,
  #pg.K_:'sim/FMS%s/key_back'%fms_string,
  pg.K_SPACE:'sim/FMS%s/key_space'%fms_string,
  #pg.K_:'sim/FMS%s/key_load'%fms_string,
  #pg.K_:'sim/FMS%s/key_save'%fms_string,
  #pg.K_:'sim/FMS%s/key_delete'%fms_string,
  #pg.K_:'sim/FMS%s/key_clear'%fms_string,
  #pg.K_:'sim/FMS%s/CDU_popup'%fms_string,
  #pg.K_:'sim/FMS%s/CDU_popout'%fms_string,
  #pg.K_:'sim/FMS%s/fix_next'%fms_string,
  #pg.K_:'sim/FMS%s/fix_prev'%fms_string,
}

try:
  beacon = xp.FindIp()
  print(beacon)
  print()
  print("Building dataref list")

  for i in range(fetch_lines):
    for j in range(fetch_chars*4):    # Characters could be 4-byte unicode
      xp.AddDataRef("sim/cockpit2/radios/indicators/fms_cdu%i_text_line%i[%i]"%(cdu,i,j), idx=(0x1000 | (i<<8) | j))
    for j in range(fetch_chars):      # Styles are one byte
      xp.AddDataRef("sim/cockpit2/radios/indicators/fms_cdu%i_style_line%i[%i]"%(cdu,i,j), idx=(0x2000 | (i<<8) | j))

  print("Done")

  print("Subscribing to datarefs")

  xp.RequestDataRefs()

  print("Done")

  timeout_counter = 0
  last_s = 0

  pg.init()
  pg.mouse.set_visible(False)

  x_resolution = 640
  y_resolution = 480

  antialias = 1

  font_name = "DejaVuSans.ttf"
  #font_name = "B612Mono-Regular.ttf"
  #font_name = "BoeingCDU.ttf"
  #font_name = "awnxmcduL_101.TTF"
  #font_name = "DejaVuSansMonoSlash.ttf"
  #font_name = "Consolas.ttf"
  small_font_size = 24
  large_font_size = 32

  # Colours 0-Black, 1-Cyan, 2-Red, 3-Yellow, 4-Green, 5-Magenta
  # 6-Amber, 7-White
  colours = (
    (0, 0, 0),
    (0, 255, 255),
    (255, 0, 0),
    (255, 255, 0),
    (50, 205, 50),
    (255, 0, 255),
    (255, 165, 0),
    (255, 255, 255)
  )

  fg = colours[4]
  wincolor = colours[0]
  print("Setting up display")
  screen = pg.display.set_mode((x_resolution, y_resolution))
  print("Done")
  print("Building fonts")
  # load font
  lg_font = pg.font.Font(font_name, large_font_size)
  sm_font = pg.font.Font(font_name, small_font_size)
  print("Done")

  # Contents of test screen
  #screen_contents.append("- PyFMC character grid -")
  #screen_contents.append("ABCDEFGHIJKLMNOPQRSTUVWX")
  #screen_contents.append("[\u00b0] Degrees 234567890123")
  #screen_contents.append("[\u2610] Box 8901234567890123")
  #screen_contents.append("[\u2190][\u2191][\u2192][\u2193] LRUD arrows")
  #screen_contents.append("[\u0394] Delta 01234567890123")
  #screen_contents.append("[\u2b21] Hexagon 234567890123")
  #screen_contents.append("[\u25c0] Left triangle 890123")
  #screen_contents.append("[\u25b6] Right triangle 90123")
  #screen_contents.append("1 CYAN 78901234567890123")
  #screen_contents.append("2 RED 678901234567890123")
  #screen_contents.append("3 YELLOW 901234567890123")
  #screen_contents.append("4 GREEN 8901234567890123")
  #screen_contents.append("5 MAGENTA 01234567890123")
  #screen_contents.append("6 AMBER 8901234567890123")
  #screen_contents.append("7 WHITE 8901234567890123")

  x_cell = x_resolution / display_chars
  y_cell = y_resolution / display_lines

  flasher = True

  # Main pygame loop
  while True:
    # use event.wait to keep from polling 100% cpu
    #if pg.event.wait().type in (pg.QUIT, pg.KEYDOWN, pg.MOUSEBUTTONDOWN):
    #  break
    pg.time.wait(10)
    
    for event in pg.event.get():
      if event.type == pg.KEYDOWN:
        if event.key in key_actions:
          xp.SendCommand(key_actions[event.key])
        else:
          print("No key mapping")

    # Refresh screen contents by listening for incoming data
    xp.GetValues()

    if not(xp.unseenDatarefs):
      print("Refreshing screen.")
      flasher = not(flasher)
      xp.restoreUnseen()
      screen.fill(wincolor)
      for i in range(fetch_lines):
        cdu_text_line = []
        for j in range(fetch_chars * 4):
          try:
            cdu_text_line.append(xp.idxvals[0x1000 | (i<<8) | j])
          except KeyError:
            pass
        # Convert all the collected bytes into a Unicode string
        try:
          cdu_text_line = bytearray(cdu_text_line).decode('utf-8')
        except UnicodeDecodeError as e:
          #print("Unicode error %s"%cdu_text_line)
          #print(e.start)
          # This should work...
          cdu_text_line = bytearray(cdu_text_line[:e.start]).decode('utf-8')

        # Render the display
        # Go through the character cells and print each character
        # centred in its cell. Use the attributes array to get the
        # attributes for each cell and apply them whilst rendering
        for j in range(fetch_chars):
          cdu_text = cdu_text_line[j]   # Python will return multi-byte unicode characters as single characters
          cdu_style = (xp.idxvals[0x2000 | (i<<8) |j])
            
          # Format the character
          # Large/small font (bit 7) 0x80
          # Reverse video (bit 6)    0x40
          # Flashing (bit 5)         0x20
          # Underline (bit 4)        0x10
          # Colours: bits 3:0        0x07
          # 0-Black, 1-Cyan, 2-Red, 3-Yellow,
          # 4-Green, 5-Magenta, 6-Amber, 7-White          

          font = lg_font if (cdu_style & 0x80) else sm_font
          font.set_underline(cdu_style & 0x10)

          fg = colours[cdu_style & 0x07]
          bg = 0

          if (cdu_style & 0x40):
            bg = fg
            fg = 0
           
          if (cdu_style & 0x20):
            if flasher:
              fg = bg
          
          xsize, ysize = font.size(cdu_text)
          ren = font.render(cdu_text, antialias, fg, bg)
          screen.blit(ren, \
            ((j * x_cell) + (x_cell / 2) - (xsize / 2), \
            (i * y_cell) + (y_cell / 2) - (ysize / 2)))

      pg.display.update()
      print("Done")
      print("Totalvals=%i"%xp.totalVals)
      xp.totalVals=0


except XPlaneIpNotFound:
  print("XPlane IP not found. Probably there is no XPlane running in your local network.")