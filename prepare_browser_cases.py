"""Additional real video cases chosen by speaker/category, never by prediction."""
import json,subprocess
from pathlib import Path
root=Path('.build/browser-cases');root.mkdir(parents=True,exist_ok=True)
clips=['1005_IWW_NEU_XX','1005_IWW_HAP_XX','1006_IWW_SAD_XX','1006_IWW_ANG_XX']
for i,clip in enumerate(clips):
    src=root/f'{clip}.flv'
    if not src.exists():subprocess.run(['curl','-fLsS','--max-time','40',f'https://media.githubusercontent.com/media/CheyneyComputerScience/CREMA-D/master/VideoFlash/{clip}.flv','-o',str(src)],check=True)
    subprocess.run(['ffmpeg','-v','error','-y','-i',str(src),'-vf','scale=640:480,setsar=1,fps=30','-af','aresample=48000','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(root/f'part-{i}.mp4')],check=True)
(root/'concat.txt').write_text(''.join(f"file 'part-{i}.mp4'\n" for i in range(4)))
subprocess.run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',str(root/'concat.txt'),'-c','copy','-movflags','+faststart',str(root/'heldout.mp4')],check=True)
(root/'sources.json').write_text(json.dumps(clips,indent=2))
