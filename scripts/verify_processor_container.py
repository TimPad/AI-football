"""Synthetic Linux CPU smoke: no credentials, downloaded weights or real players."""
import os
os.environ['YOLO_AUTOINSTALL']='false'
from pathlib import Path
from tempfile import TemporaryDirectory
import cv2
import numpy as np
import torch
from ultralytics import YOLO
from aifootball.processor.media import make_window
from aifootball.processor.workspace import Workspace
from aifootball.processor.budget import Budget

with TemporaryDirectory() as tmp:
    root=Path(tmp);video=root/'synthetic.mp4'
    writer=cv2.VideoWriter(str(video),cv2.VideoWriter.fourcc(*'mp4v'),4,(128,64))
    assert writer.isOpened()
    for i in range(16):
        frame=np.zeros((64,128,3),dtype=np.uint8);frame[10:30,i:i+10]=255;writer.write(frame)
    writer.release()
    window=make_window(video,start_ms=0,end_ms=2000,out=root/'window',mode='native')
    assert window.media is not None and not window.media.has_audio and len(window.frames)==2
    # Random weights validate the installed operator/runtime, not sports accuracy.
    model=YOLO('yolo11n.yaml');prediction=model.predict(np.zeros((64,64,3),dtype=np.uint8),device='cpu',imgsz=64,verbose=False)
    assert len(prediction)==1
    workspace=Workspace(root/'work',{'source':'synthetic'})
    budget=Budget(workspace,max_requests=1);rid=budget.reserve_call('synthetic',1,1)
    budget.settle_call(rid,{'prompt_tokens':1,'completion_tokens':1})
    assert Budget(workspace,max_requests=1).snapshot()['requests']==1
    print(f'Synthetic CPU container smoke passed; torch={torch.__version__}, compiled CUDA={torch.version.cuda}, GPU available={torch.cuda.is_available()}')
