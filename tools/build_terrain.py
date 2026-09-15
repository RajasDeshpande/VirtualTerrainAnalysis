"""One command: prepare, BlenderGIS import, analyse, verify, publish atomically."""
import os, sys, json, subprocess, shutil, time, traceback, argparse
from pathlib import Path
from datetime import datetime, timezone
PROJECT=Path(__file__).resolve().parents[1]
STATUS=PROJECT/'webxr/assets/build-status.json'

def atomic_json(path,value):
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value,indent=2),encoding='utf-8');tmp.replace(path)

def run():
    parser=argparse.ArgumentParser();parser.add_argument('--choice-file');args=parser.parse_args()
    choice_path=Path(args.choice_file) if args.choice_file else PROJECT/'data/terrain-choice.json'
    choice=json.loads(choice_path.read_text(encoding='utf-8-sig'))
    from prepare_data import validate_choice
    validate_choice(choice)
    lock=PROJECT/'data/build.lock'
    try: fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError: raise RuntimeError('Another terrain build is running (data/build.lock).')
    os.write(fd,str(os.getpid()).encode());os.close(fd)
    build_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    stage=PROJECT/'builds'/build_id
    for d in ('blender','data','logs','webxr/assets'): (stage/d).mkdir(parents=True,exist_ok=True)
    state={'id':build_id,'state':'running','stage':'Starting','place_name':choice.get('place_name','Selected terrain')}
    def progress(label):
        state['stage']=label;atomic_json(STATUS,state);print(label,flush=True)
    env={**os.environ,'TERRAIN_BUILD_ROOT':str(stage),'TERRAIN_BUILD_ID':build_id,'PYTHONIOENCODING':'utf-8'}
    blender=os.environ.get('BLENDER_EXE',r'D:\SteamLibrary\steamapps\common\Blender\blender.exe')
    try:
        validate_choice(choice)
        (stage/'data/terrain-choice.json').write_text(json.dumps(choice),encoding='utf-8')
        if not Path(blender).is_file():raise RuntimeError('Steam Blender executable not found; set BLENDER_EXE')
        steps=[('Fetching elevation and imagery',[sys.executable,str(PROJECT/'tools/prepare_data.py')]),
            ('Creating terrain in BlenderGIS',[blender,'--background','--python-exit-code','1','--python',str(PROJECT/'blender/import_prepared.py')]),
            ('Calculating slopes and exporting',[blender,'--background',str(stage/'blender/source.blend'),'--python-exit-code','1','--python',str(PROJECT/'blender/terrain_analysis.py')]),
            ('Checking geometry, georeferencing and imagery',[sys.executable,str(PROJECT/'tests/verify_accuracy.py')])]
        for i,(label,command) in enumerate(steps):
            progress(label)
            with (stage/f'logs/{i+1}.log').open('w',encoding='utf-8') as log:
                result=subprocess.run(command,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=420)
            if result.returncode:
                detail=(stage/f'logs/{i+1}.log').read_text(encoding='utf-8',errors='replace')[-3000:]
                raise RuntimeError(f'{label} failed. {detail}')
        progress('Publishing verified terrain')
        shutil.copy2(stage/'data/elevation.tif',stage/'webxr/assets/elevation.tif')
        public=PROJECT/'webxr/assets/builds'/build_id
        public.parent.mkdir(parents=True,exist_ok=True)
        shutil.copytree(stage/'webxr/assets',public)
        # These copies maintain the original documented desktop file paths.
        for folder,names in [('blender',['source.blend','terrain.blend']),('data',['provenance.json','prepared.json','elevation.tif'])]:
            for name in names:
                target=PROJECT/folder/name;temp=target.with_suffix(target.suffix+'.new')
                shutil.copy2(stage/folder/name,temp);temp.replace(target)
        for item in (stage/'webxr/assets').iterdir():
            target=PROJECT/'webxr/assets'/item.name;temp=target.with_suffix(target.suffix+'.new')
            shutil.copy2(item,temp);temp.replace(target)
        atomic_json(PROJECT/'data/terrain-choice.json',choice)
        # A viewer reads one manifest, then immutable assets from this build.
        manifest={'id':build_id,'base':f'assets/builds/{build_id}/','place_name':state['place_name']}
        atomic_json(PROJECT/'webxr/assets/current.json',manifest)
        state.update(state='complete',stage='Ready',manifest=manifest);atomic_json(STATUS,state)
        print('BUILD_VERIFIED',json.dumps(manifest),flush=True)
    except Exception as error:
        state.update(state='failed',error=str(error),stage=state['stage'])
        atomic_json(STATUS,state);traceback.print_exc();return 1
    finally: lock.unlink(missing_ok=True)
    return 0

if __name__=='__main__':sys.exit(run())
