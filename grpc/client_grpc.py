from typing import SupportsRound
import grpc
import comm07_pb2
import comm07_pb2_grpc
from pydub import AudioSegment
import asyncio
import pyaudio
from pydub.utils import db_to_float
from time import time
import numpy as np
import socketio 
from flask import Flask,render_template
import os
import eventlet

S_ADDRESS = '118.67.135.206:6013'
RATE = 16000
S_THRESHOLD = db_to_float(-35)
MIN_SILENCE = 6
endure = 0
frames = None
ticker = False
switch = True
ROOT_PATH = os.path.dirname(os.path.abspath(__file__))
STATIC_FOLDER = os.path.join(ROOT_PATH, "src")
TEMPLATE_FOLDER = os.path.join(ROOT_PATH, "src/view")

sio = socketio.Server(async_mode='eventlet', ping_timeout=60)

app=Flask(__name__, static_url_path='/src', static_folder=STATIC_FOLDER, template_folder=TEMPLATE_FOLDER)
app.wsgi_app = socketio.WSGIApp(sio, app.wsgi_app)

@app.route('/')
def index():
    return render_template("ui.html")

class Phone:
    
    def __init__(self,):
        self.switch = True

    def do(self,S_ADDRESS):
        self.switch=True
        self.streams(S_ADDRESS)

    def streams(self,S_ADDRESS):
        print('Sending...')
        client_loop(S_ADDRESS)
        print('Stopped')

    def stop(self):
        self.switch = False        


def client_loop(S_ADDRESS):
    global sio
    global frames
    global ticker
    global endure
    global switch
    
    audio_stream = pyaudio.PyAudio().open(format=pyaudio.paInt16,channels=1, #audio stream on
                                          rate=16000,input=True,frames_per_buffer=2048)
    diagnosis = []
    
    with grpc.insecure_channel(S_ADDRESS) as channel:                  #Define channel
        stub = comm07_pb2_grpc.Comm07Stub(channel)                     #Instantiate stub
        while switch:
            
            while True:
                
                audio = audio_stream.read(512,exception_on_overflow=False)
                audio_checker = AudioSegment(audio,sample_width=2, frame_rate=16000, channels=1)
                
                try : 
                    frames += audio
                except : 
                    frames = audio
                    
                if audio_checker.rms<S_THRESHOLD*audio_checker.max_possible_amplitude:
                    
                    if not ticker:
                        frames=frames[-64:]
                        endure=0
                    elif endure<MIN_SILENCE:
                        endure+=1
                    elif len(frames)<=300:
                        pass
                    else:
                        break
                else:
                    endure=0
                    ticker=True
            
            ticker = False
            endure = 0
            frames=frames[:-64]
            response = stub.Talker(comm07_pb2.InfRequest(audio=frames)) #Get response
            sio.start_background_task(sio.emit,"infer", response.answer)
            sio.start_background_task(sio.emit,"infer", " ")
            # sio.emit("infer", response.answer);
            print(response.answer)
            
            if response.answer ==  "집에 가자":
                break
        
    


phone = Phone()

@sio.on('join')
def connect(*args):
    global phone
    global switch
    switch = True
    phone.do(S_ADDRESS)
    
@sio.on('get_punc')
def leave(sid, full_text):
    global frames
    global ticker
    global endure
    global switch
    frames=None
    ticker=False
    endure=0
    print('leave')
    switch = False
    
    # send punc
    with grpc.insecure_channel(S_ADDRESS) as channel:     
        stub = comm07_pb2_grpc.Comm07Stub(channel) 
        punkinput = comm07_pb2.InfReply(answer=full_text)
        punkreply = stub.get_punkt(punkinput)
        punkanswer = punkreply.punked
        print(punkanswer, "punkanswer") 
        sio.emit("send_punc", punkanswer)
        
    
            

    
if __name__=='__main__':
    eventlet.wsgi.server(eventlet.listen(('localhost', 8080)), app)
    