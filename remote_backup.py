import os,sys,json,sqlite3,tempfile,tarfile,stat,time,hashlib,io,subprocess
from pathlib import Path
import signal
def interrupted(signum,frame):raise SystemExit(128+signum)
for name in ('SIGHUP','SIGTERM'):
    if hasattr(signal,name):signal.signal(getattr(signal,name),interrupted)

# ROOTS is supplied as JSON through an immutable hexadecimal Python literal.
roots=[Path(os.path.normpath(p)) for p in ROOTS]
if not roots or any(not p.is_absolute() or str(p)=='/' for p in roots):raise RuntimeError('Select absolute real directories, not /')
roots=sorted(set(roots),key=lambda p:(len(p.parts),str(p)))
roots=[p for i,p in enumerate(roots) if not any(p!=q and q in p.parents for q in roots[:i])]
if any(not p.exists() for p in roots):raise RuntimeError('A selected source does not exist: '+str([str(p) for p in roots if not p.exists()]))
try:os.nice(10)
except OSError:pass
manifest={'format':1,'started_utc':time.time(),'sources':[str(p) for p in roots],
          'sqlite':[],'warnings':[],'files':0,'logical_bytes':0,'consistency':'SQLite uses online backup; other files are a live filesystem copy, not a coordinated VM snapshot.'}
try:
    manifest['system']={'uname':os.uname().sysname+' '+os.uname().release}
    manifest['service_definitions']=subprocess.run(['systemctl','show','steam-card-api.service','steam-card-scanner.service','--property=WorkingDirectory,ExecStart','--no-pager'],capture_output=True,text=True,timeout=10).stdout
except Exception:pass

def files():
    for root in roots:
        yield root
        if root.is_dir() and not root.is_symlink():
            for parent,dirs,names in os.walk(root,followlinks=False):
                dirs.sort();names.sort()
                for name in dirs+names:yield Path(parent)/name

with tempfile.TemporaryDirectory(prefix='drobing-sqlite-backup-') as tmp:
    snapshots={}
    for path in files():
        try:st=path.lstat()
        except FileNotFoundError:
            manifest['warnings'].append('Disappeared during SQLite discovery: '+str(path));continue
        if not stat.S_ISREG(st.st_mode):continue
        with path.open('rb') as f:header=f.read(16)
        if header!=b'SQLite format 3\x00':continue
        target=Path(tmp)/(str(len(snapshots))+'.sqlite3')
        start=time.monotonic()
        def progress(status,remaining,total):
            if time.monotonic()-start>180:raise TimeoutError('SQLite snapshot timed out: '+str(path))
        source=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=15)
        dest=sqlite3.connect(target)
        try:
            source.backup(dest,pages=512,progress=progress,sleep=.02)
            check=dest.execute('PRAGMA quick_check').fetchone()[0]
            if check!='ok':raise RuntimeError('SQLite quick_check: '+str(path)+': '+check)
        finally:source.close();dest.close()
        snapshots[str(path)]=target
        manifest['sqlite'].append({'path':str(path),'quick_check':'ok','bytes':target.stat().st_size})
    sidecars={p+suffix for p in snapshots for suffix in ('-wal','-shm','-journal')}
    out=sys.stdout.buffer
    with tarfile.open(fileobj=out,mode='w|gz',compresslevel=1,format=tarfile.PAX_FORMAT,dereference=False) as archive:
        for path in files():
            if str(path) in sidecars:continue
            try:st=path.lstat()
            except FileNotFoundError:
                manifest['warnings'].append('Disappeared during live copy: '+str(path));continue
            if not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode)):
                manifest['warnings'].append('Special device/socket/FIFO omitted: '+str(path));continue
            info=archive.gettarinfo(str(path),arcname=str(path).lstrip('/'))
            replacement=snapshots.get(str(path))
            if info.isfile():
                if replacement:info.size=replacement.stat().st_size
                with (replacement or path).open('rb') as f:archive.addfile(info,f)
                manifest['files']+=1;manifest['logical_bytes']+=info.size
            else:archive.addfile(info)
        manifest['finished_utc']=time.time()
        payload=json.dumps(manifest,ensure_ascii=False,indent=2).encode()
        info=tarfile.TarInfo('__DroBinG_Backup__/manifest.json');info.size=len(payload);info.mtime=int(time.time());info.mode=0o600
        archive.addfile(info,io.BytesIO(payload))
    out.flush()
