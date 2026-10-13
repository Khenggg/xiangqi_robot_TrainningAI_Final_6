"""Snapshot current sources in a temporary index; never alter the user's index."""
import json
import os
import subprocess
from pathlib import Path
root = Path(__file__).parent
repo = root.parents[1]
env = dict(os.environ, GIT_INDEX_FILE=str(root/'snapshot.index'))
def run(*args,check=True,env=env,input=None):
    p = subprocess.run(['git','-C',str(repo),*args],env=env,input=input,capture_output=True)
    if check and p.returncode:
        raise RuntimeError(p.stderr.decode('utf-8',errors='replace'))
    return p
head = run('rev-parse','HEAD').stdout.decode().strip()
run('read-tree',head)
run('add','-u')
untracked = run('ls-files','--others','--exclude-standard','-z').stdout.decode().split('\0')
keep = [p for p in untracked if p and not p.startswith(('reports/','.codex/'))]
if keep:
    run('add','--',*keep)
tree = run('write-tree').stdout.decode().strip()
commit_env = dict(env, GIT_AUTHOR_NAME='Codex Review Snapshot',GIT_AUTHOR_EMAIL='review@localhost',
                  GIT_COMMITTER_NAME='Codex Review Snapshot',GIT_COMMITTER_EMAIL='review@localhost')
commit = run('commit-tree',tree,'-p',head,env=commit_env,input=b'Temporary review snapshot; no integration\n').stdout.decode().strip()
donor = 'fe3faa8dcac121defa4c9ee000d4df0ac6c8fd09'
result = run('merge-tree','--write-tree',commit,donor,check=False)
(root/'working-snapshot-merge-tree.txt').write_bytes(result.stdout+result.stderr)
snapshot = dict(snapshot_commit=commit,snapshot_tree=tree,parent=head,visual=donor,
                included_untracked=keep,excluded='reports/ and .codex/ untracked; ignored files excluded',
                merge_exit=result.returncode)
(root/'working-snapshot.json').write_text(json.dumps(snapshot,indent=2),encoding='utf-8')
print(json.dumps(snapshot,indent=2))
