import webview
import threading
import uvicorn
import time
import sys
import os


from main import app 

def run_server():
    
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="error")

if __name__ == '__main__':
    
    t = threading.Thread(target=run_server)
    t.daemon = True
    t.start()

    
    time.sleep(1)

    
    window = webview.create_window(
        title='AI Media Universe', 
        url='http://127.0.0.1:8000', 
        width=1280, 
        height=800,
        min_size=(800, 600)
    )
    
   
    webview.start()