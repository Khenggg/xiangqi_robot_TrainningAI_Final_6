"""Exercise the unchanged main loop through Pygame input events; no business mocks."""
import os,sys,time,json,runpy,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
os.chdir(ROOT);sys.path.insert(0,str(ROOT))
os.environ.update(SDL_VIDEODRIVER='dummy',SDL_AUDIODRIVER='dummy',XIANGQI_SIMULATION_TOKEN='',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
import pygame,webbrowser
webbrowser.open=lambda *a,**k:False
OUT=ROOT/'reports/userflow'; OUT.mkdir(exist_ok=True)
real_get=pygame.event.get
phase='choose';mode_index=0;phase_at=time.monotonic();last_action=0;substep=0;expected_count=0;selected=None;last_revision=None;done=False
modes=['HUMAN_VS_HUMAN','HUMAN_VS_ROBOT','ROBOT_VS_ROBOT']
opening=[((4,6),(4,5)),((4,3),(4,4)),((4,5),(4,4)),((0,3),(0,4)),((0,6),(0,5)),((0,4),(0,5)),((1,7),(4,7)),((1,2),(4,2)),((7,9),(6,7)),((7,0),(6,2))]
def record(kind,**data):
    with (OUT/'ui-flow.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(dict(time=time.time(),kind=kind,mode=modes[min(mode_index,2)],phase=phase,**data),ensure_ascii=False,default=str)+'\n')
def set_phase(value):
    global phase,phase_at
    phase=value;phase_at=time.monotonic();record('phase')
def capture(g,label):
    pygame.image.save(g['game_window'].canvas,OUT/f'{mode_index}-{label}.png')
def click(g,pos):
    from src.ui.game_window import fitted_rect
    w=g['game_window'];r=fitted_rect(w.canvas_size,w.display.get_size())
    x=r.x+round(pos[0]*r.width/w.canvas_size[0]);y=r.y+round(pos[1]*r.height/w.canvas_size[1])
    return pygame.event.Event(pygame.MOUSEBUTTONDOWN,button=1,pos=(x,y))
def key(k):return pygame.event.Event(pygame.KEYDOWN,key=k,mod=0,repeat=False)
def scene_ok(g):
    s=g['state'];hw=g['hw'];t=g.get('telemetry');world=getattr(t,'_latest_world_state',None)
    if not world:return False
    active={p['id']:(p['nearest_row'],p['nearest_col']) for p in world['pieces'] if not p.get('captured',False)}
    expected={pid:cell for cell,pid in s.piece_ids.items()}
    return active==expected

def drive(g):
    global mode_index,last_action,substep,expected_count,selected,last_revision,done
    now=time.monotonic();s=g['state'];hw=g.get('hw');cfg=g['config'];mode=modes[mode_index]
    if now-phase_at>150:raise AssertionError(f'timeout {phase}: {s.status_message}; startup={g.get("startup_message")}; selfplay={getattr(g.get("self_play"),"status",None)}')
    if now-last_action<.16:return []
    from src.ui import board_renderer as br
    if phase=='choose':
        if g.get('home_screen_active') and not g['startup_worker'].busy:
            capture(g,'home');rect={'HUMAN_VS_HUMAN':br.HOME_HUMAN_RECT,'HUMAN_VS_ROBOT':br.HOME_VS_ROBOT_RECT,'ROBOT_VS_ROBOT':br.HOME_SELF_PLAY_RECT}[mode]
            set_phase('starting');last_action=now;return [click(g,rect.center)]
    elif phase=='starting':
        if g.get('difficulty_menu_active'):
            record('choose_easy');last_action=now;return [key(pygame.K_1)]
        if hw is not None and not g.get('home_screen_active') and not g.get('difficulty_menu_active') and not g['startup_worker'].busy:
            assert hw.profile.physical_robot_enabled is False and hw.cam_monitor is None
            capture(g,'started');record('started',profile=hw.profile,ready=hw.is_robot_ready,recovery=s.recovery_required)
            expected_count=0;selected=None;last_revision=None;set_phase('initial_hold')
    elif phase=='initial_hold':
        if now-phase_at>4:set_phase('playing')
    elif phase=='playing':
        if s.recovery_required or s.move_sync_error or s.physical_sync_fault:
            capture(g,'fault');raise AssertionError(f'game fault: {s.status_message}; {s.move_execution_error}')
        n=len(s.move_history)
        busy=bool(getattr(getattr(hw,'motion_worker',None),'busy',False))
        if not busy and s.pending_move is None and scene_ok(g) and last_revision!=s.board_revision:
            record('stable_commit',plies=n,revision=s.board_revision,fen=s.current_fen,pieces=len(s.piece_ids),captured=len(s.r_captured)+len(s.b_captured),joints=hw.backend.get_state_snapshot().joints_deg);last_revision=s.board_revision
            capture(g,f'ply-{n:02}')
        target=10
        if n>=target and not busy and s.pending_move is None and scene_ok(g):
            capture(g,'ten-plies');record('ten_plies',plies=n,scene_matches=True);set_phase('surrender');return []
        if s.game_over:raise AssertionError(f'game ended before target: {n}')
        if mode=='ROBOT_VS_ROBOT':return []
        if n<expected_count or busy or s.pending_move is not None or not s.is_human_turn:return []
        if selected is None:
            if mode=='HUMAN_VS_HUMAN':move=opening[n]
            else:
                from src.core import xiangqi
                legal=xiangqi.find_all_valid_moves(s.turn,s.board)
                assert legal
                vals={'K':1000,'R':10,'C':6,'H':5,'P':2,'E':2,'A':2}
                def score(m):
                    a,b=m;piece=s.board[a[1]][a[0]];dest=s.board[b[1]][b[0]]
                    return (vals.get(dest.split('_')[-1],0) if dest!='.' else 0, a==(4,6),a==(7,9),a==(1,9),-b[1],-b[0])
                move=max(legal,key=score)
            selected=move;last_action=now;record('select',move=move);return [click(g,br.BoardRenderer.grid_to_pixel(*move[0]))]
        move=selected;selected=None;expected_count=n+1;last_action=now;record('move_click',move=move);return [click(g,br.BoardRenderer.grid_to_pixel(*move[1]))]
    elif phase=='surrender':
        if s.game_over:
            record('surrendered',winner=s.winner,plies=len(s.move_history));capture(g,'surrendered');set_phase('new_game');last_action=now;return [click(g,br.BTN_NEW_GAME_RECT.center)]
        last_action=now;return [click(g,br.BTN_SURRENDER_RECT.center)]
    elif phase=='new_game':
        if len(s.move_history)==0 and not s.game_over and scene_ok(g):
            assert len(s.piece_ids)==32
            record('new_game_ok');capture(g,'new-game');set_phase('home');last_action=now;return [click(g,br.BTN_MODE_SELECT_RECT.center)]
    elif phase=='home':
        if g.get('home_screen_active') and not g.get('mode_switching'):
            record('home_ok')
            if mode_index==2:
                done=True;record('complete');set_phase('quitting');return [pygame.event.Event(pygame.QUIT)]
            mode_index+=1;set_phase('choose')
    return []

def events(*a,**kw):
    original=real_get(*a,**kw);g=sys._getframe(1).f_globals
    if g.get('__file__')!=str(ROOT/'main.py') or 'game_window' not in g:return original
    try:return original+drive(g)
    except Exception as e:
        record('failure',error=str(e),traceback=traceback.format_exc());capture(g,'failure');raise
pygame.event.get=events
sys.argv=[str(ROOT/'main.py'),'--viewer-port','8098','--telemetry-port','8775','--simulation-profile','fast']
try:
    runpy.run_path(str(ROOT/'main.py'),run_name='__main__')
finally:
    record('driver_exit',complete=done)
