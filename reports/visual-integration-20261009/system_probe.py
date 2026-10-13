"""Isolated replay of 3 modes with real PyBullet and fixture engine; no hardware/API."""
import sys, json, time, threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
import config
from src.core.game_state import GameState
from src.core.ai_execution import execute_ai_move
from src.core.self_play_controller import SelfPlayController
from src.ui.input_handler import InputHandler
from src.ui.board_renderer import BoardRenderer, BTN_SURRENDER_RECT
from src.hardware.hardware_manager import HardwareManager
from src.hardware.telemetry_publisher import TelemetryPublisher
from src.core.launch_options import ViewerServer
config.ROBOT_BACKEND='VIRTUAL'
config.DRY_RUN=True
config.GAME_ONLY=False
OUT=ROOT/'reports/visual-integration-20261009'
OUT.mkdir(parents=True,exist_ok=True)
sequences={
 'HUMAN_VS_ROBOT':['e6e5','h2e2','b9c7','e3e4','h9g7','e4e5','g7e6','e5e6','h7e7','e6e7'],
 'HUMAN_VS_HUMAN':['e6e5','e3e4','e5e4','b0c2','b9c7','h0g2','h9g7','i0h0','i9h9','c0e2'],
 'ROBOT_VS_ROBOT':['b9c7','h0g2','h7g7','b2c2','g7g3','c2c6','h9g7','b0c2','i9h9','a0b0']}
def parse(text): return ((ord(text[0])-97,int(text[1])),(ord(text[2])-97,int(text[3])))
report={ 'kind':'fixture opening replay via InputHandler/controller + actual PyBullet; not native mouse', 'modes':[] }
manager=None
telemetry=None
viewer=None
try:
    for mode,text_moves in sequences.items():
        if manager: manager.cleanup()
        config.GAME_MODE=mode
        manager=HardwareManager(config,ROOT)
        manager._init_robot()
        bridge=manager.setup_digital_twin(start=False)
        state=GameState(allow_mouse_move=True)
        state.api_client=Mock(room_id=None)
        state.set_board_observer(manager.sync_committed_board)
        assert state.sync_current_board()
        assert manager.simulation_runtime.runtime_go_service_safe()['success']
        handler=InputHandler(state,manager)
        controller=None
        if mode=='ROBOT_VS_ROBOT':
            engine_moves=iter(map(parse,text_moves))
            manager.ai_ctrl=SimpleNamespace(pick_move=lambda *a,**kw:next(engine_moves),local_engine=None,cloud_engine=None)
            manager.difficulty_availability=lambda:{'easy':True}
            controller=SelfPlayController(state,manager)
            assert controller.start('easy','easy')
        entry={'mode':mode,'plies':[], 'initial_joints':manager.backend.get_state_snapshot().joints_deg}
        raw_evidence=[]
        actual_execution=manager.execute_piece_move
        def observed_execution(*args,**kwargs):
            result=actual_execution(*args,**kwargs)
            if result.success:
                row=kwargs.get('d_row',args[3] if len(args)>3 else None)
                col=kwargs.get('d_col',args[2] if len(args)>2 else None)
                pid=kwargs['piece_id']
                position=manager.simulation_runtime.world.pieces[pid].get_position_robot().copy()
                target=manager.simulation_runtime.placement_state.cell_to_robot_xyz(row,col)
                error=float(np.linalg.norm(position[:2]-target[:2])*1000)
                assert error<1,(pid,error)
                assert manager.simulation_runtime.find_nearest_cell(position)==(row,col)
                assert manager.simulation_runtime.world.get_attached_piece() is None
                victim=kwargs.get('captured_piece_id')
                if victim is not None:
                    assert not manager.simulation_runtime.placement_state.is_in_bounds_robot(
                        manager.simulation_runtime.world.pieces[victim].get_position_robot())
                raw_evidence.append({'piece_id':pid,'xy_error_mm_before_fen_commit':error,'captured_piece_id':victim})
            return result
        manager.execute_piece_move=observed_execution
        entry['robot_settle_before_commit']=raw_evidence
        report['modes'].append(entry)
        for i,text in enumerate(text_moves):
            src,dst=parse(text)
            captured=state.board[dst[1]][dst[0]]!='.'
            before=len(state.move_history)
            if controller:
                assert controller.request_next_move()
                deadline=time.monotonic()+120
                while not controller.accepts_next and not state.game_over and time.monotonic()<deadline:
                    controller.tick()
                    if controller.status.value=='faulted': raise RuntimeError(state.status_message)
                    time.sleep(.005)
            elif mode=='HUMAN_VS_HUMAN' or state.turn=='r':
                handler.handle_mouse_down(*BoardRenderer.grid_to_pixel(*src))
                handler.handle_mouse_down(*BoardRenderer.grid_to_pixel(*dst))
            else:
                assert execute_ai_move(state,manager,(src,dst),True,True),state.status_message
            assert len(state.move_history)==before+1,(mode,text,state.status_message)
            assert not state.physical_sync_fault and not state.move_sync_error
            assert manager.simulation_runtime.world.get_attached_piece() is None
            errors=[]
            for cell,pid in state.piece_ids.items():
                actual=manager.simulation_runtime.world.pieces[pid].get_position_robot()
                expected=manager.simulation_runtime.placement_state.cell_to_robot_xyz(*cell)
                errors.append(float(np.linalg.norm(actual[:2]-expected[:2])*1000))
                assert manager.simulation_runtime.find_nearest_cell(actual)==cell
            assert max(errors,default=0)<1
            entry['plies'].append({'index':i+1,'move':text,'capture':captured,'max_active_piece_xy_error_mm':max(errors),
                'joint_pose':manager.backend.get_state_snapshot().joints_deg,'fen':state.current_fen})
            (OUT/'system.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            print('PROBE',mode,i+1,text,'capture',captured,flush=True)
        if controller:
            assert controller.end_match()
            state.handle_game_over('b',reason='RESIGN')
        else:
            handler.handle_mouse_down(*BTN_SURRENDER_RECT.center)
        assert state.game_over
        entry['surrendered']=True
        entry['final_joints']=manager.backend.get_state_snapshot().joints_deg
        if mode=='HUMAN_VS_HUMAN': assert entry['initial_joints']==entry['final_joints']
    # Keep only the last isolated virtual scene alive for browser/reconnect evidence.
    telemetry=TelemetryPublisher(port=8897,robot_model='FR3')
    telemetry.start()
    bridge.telemetry=telemetry
    manager.telemetry=telemetry
    manager.simulation_runtime.telemetry=telemetry
    manager.backend.telemetry_publisher=telemetry
    telemetry.register_command_handler(manager.simulation_runtime._handle_client_command)
    bridge.start()
    viewer=ViewerServer(ROOT,8097)
    viewer.thread.start()
    report['complete']=True
    (OUT/'system.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('READY http://127.0.0.1:8097/robot-3d-viewer/?ws=ws://127.0.0.1:8897&autoconnect=1',flush=True)
    marker=OUT/'STOP_PROBE_V2'
    while not marker.exists(): time.sleep(.25)
finally:
    if manager: manager.cleanup()
    if telemetry: telemetry.stop()
    if viewer: viewer.close()
