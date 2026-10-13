"""Read-only Git comparison; merge-file output is stored as evidence only."""
import hashlib
import json
import subprocess
from pathlib import Path

repo = Path(__file__).resolve().parents[2]
out = Path(__file__).parent
donor = 'fe3faa8dcac121defa4c9ee000d4df0ac6c8fd09'
def git(*args, check=True):
    result = subprocess.run(['git', '-C', str(repo), *args], capture_output=True)
    if check and result.returncode:
        raise RuntimeError(result.stderr.decode('utf-8', errors='replace'))
    return result
def lines(*args):
    return git(*args).stdout.decode('utf-8').splitlines()
head = lines('rev-parse','HEAD')[0]
base = lines('merge-base',head,donor)[0]
paths = lines('diff','--name-only',base,donor)
changed = set(lines('diff','HEAD','--name-only'))
untracked = set(lines('ls-files','--others','--exclude-standard'))
records = []
scratch = out/'merge-inputs'
scratch.mkdir(exist_ok=True)
for path in paths:
    local = repo/path
    ours = local.read_bytes() if local.is_file() else b''
    old = git('show',f'{base}:{path}',check=False).stdout
    incoming = git('show',f'{donor}:{path}',check=False).stdout
    row = {'path':path, 'local_modified':path in changed or path in untracked,
           'local_present':local.is_file(), 'same_as_visual':ours==incoming,
           'local_sha256':hashlib.sha256(ours).hexdigest()}
    if not any(b'\0' in data for data in (ours,old,incoming)):
        for name,data in [('ours',ours),('base',old),('visual',incoming)]:
            (scratch/name).write_bytes(data)
        result = git('merge-file','-p','--diff3',str(scratch/'ours'),str(scratch/'base'),str(scratch/'visual'),check=False)
        row['merge_file_exit'] = result.returncode
        if result.returncode>0:
            artifact = out/'conflicts'/path
            artifact.parent.mkdir(parents=True,exist_ok=True)
            artifact.write_bytes(result.stdout)
    else:
        row['binary'] = True
    records.append(row)
merge = git('merge-tree','--write-tree',head,donor,check=False)
(out/'committed-merge-tree.txt').write_bytes(merge.stdout+merge.stderr)
result = {'head':head,'visual':donor,'merge_base':base,
          'commit_divergence':lines('rev-list','--left-right','--count',f'{head}...{donor}')[0],
          'committed_merge_exit':merge.returncode,
          'working_tree_status':lines('status','--short'),
          'donor_delta':lines('log','--format=%h %s',f'652af26..{donor}'),
          'files':records}
(out/'inventory.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'changed_visual_files':len(records),
                  'effective_working_tree_conflicts':[r['path'] for r in records if r.get('merge_file_exit',0)>0],
                  'same_as_visual':[r['path'] for r in records if r['same_as_visual']]},ensure_ascii=False,indent=2))
