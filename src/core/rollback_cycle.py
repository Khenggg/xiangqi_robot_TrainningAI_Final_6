"""Pure ledger and inverse planning for one verified Red/Black cycle.

Coordinates use (column, row). This module never talks to a camera or controller.
Saved forward transitions authorize inverse transfers; forward chess rules do not.
"""
from dataclasses import dataclass, field
import hashlib
import json
from uuid import uuid4

_PIECES = {side + '_' + kind for side in ('r', 'b') for kind in 'KAENRCP'}


def _nonnegative_int(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError('Invalid ' + name)


def _cell(value):
    if (not isinstance(value, (tuple, list)) or len(value) != 2
            or any(type(v) is not int for v in value)
            or not 0 <= value[0] < 9 or not 0 <= value[1] < 10):
        raise ValueError('Invalid board coordinate')
    return tuple(value)


def _board(value):
    if not isinstance(value, (tuple, list)) or any(not isinstance(row, (tuple, list)) for row in value):
        raise ValueError('Invalid board rows')
    result = tuple(tuple(row) for row in value)
    if len(result) != 10 or any(len(row) != 9 for row in result):
        raise ValueError('Expected a 10 by 9 board')
    if any(not isinstance(p, str) or p not in _PIECES | {'.'} for row in result for p in row):
        raise ValueError('Unknown or invalid board cells cannot authorize rollback')
    return result


def board_signature(value):
    return hashlib.sha256(json.dumps(value, separators=(',', ':')).encode()).hexdigest()


_STATE_FIELDS = dict(turn='r', current_fen='', move_number=1, last_move=None,
    move_history=[], move_log=[], r_captured=[], b_captured=[], game_over=False,
    winner=None, human_commit_generation=0,
    ai_started_for_human_commit_generation=0, game_epoch=0, ai_epoch=0)


def _validate_metadata(data):
    if not isinstance(data, dict) or data.get('turn') not in ('r', 'b'):
        raise ValueError('Invalid snapshot metadata')
    if type(data['game_over']) is not bool or data['winner'] not in (None, 'r', 'b'):
        raise ValueError('Invalid game result metadata')
    if not isinstance(data['current_fen'], str):
        raise ValueError('Invalid saved FEN')
    for key in ('game_epoch', 'ai_epoch', 'human_commit_generation', 'ai_started_for_human_commit_generation'):
        _nonnegative_int(data[key], key)
    _nonnegative_int(data['move_number'], 'move_number', 1)
    for key, side in (('r_captured', 'r'), ('b_captured', 'b')):
        pieces = data[key]
        if (not isinstance(pieces, list) or any(not isinstance(piece, str)
                or piece not in _PIECES or not piece.startswith(side + '_') for piece in pieces)):
            raise ValueError('Invalid captured inventory ' + key)
    for key in ('move_history', 'move_log'):
        if not isinstance(data[key], list):
            raise ValueError('Invalid saved ' + key)
        for entry in data[key]:
            if not isinstance(entry, dict) or entry.get('turn') not in ('r', 'b'):
                raise ValueError('Invalid history entry')
            src, dst = _cell(entry.get('src')), _cell(entry.get('dst'))
            if src == dst:
                raise ValueError('Invalid zero-length history move')
            if key == 'move_log' or 'piece' in entry:
                piece = entry.get('piece')
                if not isinstance(piece, str) or piece not in _PIECES or not piece.startswith(entry['turn'] + '_'):
                    raise ValueError('Invalid history piece')
    if data['last_move'] is not None:
        move = data['last_move']
        if not isinstance(move, (tuple, list)) or len(move) != 2 or _cell(move[0]) == _cell(move[1]):
            raise ValueError('Invalid saved last_move')


@dataclass(frozen=True)
class StateSnapshot:
    board: tuple
    state_json: str

    def __post_init__(self):
        object.__setattr__(self, 'board', _board(self.board))
        data = json.loads(self.state_json)
        _validate_metadata(data)

    @classmethod
    def from_state(cls, state):
        data = {key: getattr(state, key, default) for key, default in _STATE_FIELDS.items()}
        return cls(_board(state.board), json.dumps(data, sort_keys=True))

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError('Invalid snapshot object')
        return cls(_board(data['board']), json.dumps(
            {k: data.get(k, default) for k, default in _STATE_FIELDS.items()}, sort_keys=True))

    def to_dict(self):
        return dict(json.loads(self.state_json), board=[list(row) for row in self.board])

    def apply_to(self, state):
        for key, value in self.to_dict().items():
            # Runtime move consumers use tuple coordinates.
            if key == 'last_move' and value is not None:
                value = tuple(tuple(p) for p in value)
            setattr(state, key, value)

    @property
    def turn(self):
        return json.loads(self.state_json)['turn']

    @property
    def current_fen(self):
        return json.loads(self.state_json)['current_fen']

    @property
    def signature(self):
        return board_signature(self.to_dict())


@dataclass(frozen=True)
class MoveRecord:
    side: str
    src: tuple
    dst: tuple
    piece: str
    captured_piece: str | None = None
    physical_verified: bool = False
    logical_ref: str = ''

    def __post_init__(self):
        object.__setattr__(self, 'src', _cell(self.src))
        object.__setattr__(self, 'dst', _cell(self.dst))
        if self.side not in ('r', 'b') or self.piece not in _PIECES or not self.piece.startswith(self.side + '_'):
            raise ValueError('Invalid mover side/piece')
        if self.src == self.dst or any(not (0 <= c < 9 and 0 <= r < 10) for c, r in (self.src, self.dst)):
            raise ValueError('Invalid move coordinates')
        if self.captured_piece == '.':
            object.__setattr__(self, 'captured_piece', None)
        if self.captured_piece is not None and (self.captured_piece not in _PIECES or self.captured_piece.startswith(self.side + '_')):
            raise ValueError('Cannot capture own piece')
        if type(self.physical_verified) is not bool or not isinstance(self.logical_ref, str):
            raise ValueError('Invalid move verification metadata')

    def to_dict(self):
        return dict(side=self.side, src=list(self.src), dst=list(self.dst), piece=self.piece,
                    captured_piece=self.captured_piece, physical_verified=self.physical_verified,
                    logical_ref=self.logical_ref)

    @classmethod
    def from_dict(cls, data):
        return cls(**data)


def _forward(before, move):
    board = [list(row) for row in before]
    sc, sr = move.src
    dc, dr = move.dst
    if board[sr][sc] != move.piece or board[dr][dc] != (move.captured_piece or '.'):
        raise ValueError('Move ledger does not match source/victim')
    board[sr][sc], board[dr][dc] = '.', move.piece
    return _board(board)


@dataclass
class CycleRecord:
    s0: StateSnapshot
    s1: StateSnapshot
    red: MoveRecord
    game_epoch: int
    revision: int
    cycle_id: str = field(default_factory=lambda: str(uuid4()))
    s2: StateSnapshot | None = None
    black: MoveRecord | None = None
    status: str = 'BUILDING'

    @classmethod
    def start(cls, s0, s1, red, game_epoch, revision, cycle_id=None):
        _nonnegative_int(game_epoch, 'cycle epoch')
        _nonnegative_int(revision, 'cycle revision')
        if s0.to_dict()['game_epoch'] != game_epoch or s1.to_dict()['game_epoch'] != game_epoch:
            raise ValueError('Snapshot/cycle epoch mismatch')
        if s0.to_dict()['game_over'] or s1.to_dict()['game_over']:
            raise ValueError('Terminal human transition cannot start a cycle')
        if cycle_id is not None and (not isinstance(cycle_id, str) or not cycle_id):
            raise ValueError('Invalid cycle ID')
        if red.side != 'r' or s0.turn != 'r' or s1.turn != 'b' or _forward(s0.board, red) != s1.board:
            raise ValueError('Invalid committed Red transition')
        return cls(s0, s1, red, game_epoch, revision, cycle_id or str(uuid4()))

    def complete(self, s2, black):
        if self.status != 'BUILDING' or self.s2 is not None:
            raise ValueError('Cycle already completed or invalidated')
        if black.side != 'b' or s2.turn != 'r' or not black.physical_verified:
            raise ValueError('Black requires a physically verified commit')
        if s2.to_dict()['game_epoch'] != self.game_epoch:
            raise ValueError('Black snapshot/cycle epoch mismatch')
        if _forward(self.s1.board, black) != s2.board:
            raise ValueError('Invalid Black transition')
        self.s2, self.black = s2, black

    def seal(self, *, arm_parked, controller_idle, board_verified, baseline_ready, no_fault):
        if self.status != 'BUILDING' or self.s2 is None or not all(value is True for value in (
                arm_parked, controller_idle, board_verified, baseline_ready, no_fault)):
            raise ValueError('Cycle not safe and complete')
        if self.s2.to_dict()['game_over']:
            raise ValueError('Terminal cycles are not rollback eligible')
        self.status = 'READY'

    def consume(self):
        if self.status != 'READY':
            raise ValueError('Latest cycle is not available')
        self.status = 'CONSUMED'

    def invalidate(self):
        self.status = 'INVALIDATED'

    def to_dict(self):
        return dict(s0=self.s0.to_dict(), s1=self.s1.to_dict(), red=self.red.to_dict(),
            game_epoch=self.game_epoch, revision=self.revision, cycle_id=self.cycle_id,
            s2=self.s2.to_dict() if self.s2 else None,
            black=self.black.to_dict() if self.black else None, status=self.status)

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or bool(data.get('s2')) != bool(data.get('black')):
            raise ValueError('Incomplete cycle transition pair')
        result = cls.start(StateSnapshot.from_dict(data['s0']), StateSnapshot.from_dict(data['s1']),
            MoveRecord.from_dict(data['red']), data['game_epoch'], data['revision'], data['cycle_id'])
        if data.get('s2'):
            result.complete(StateSnapshot.from_dict(data['s2']), MoveRecord.from_dict(data['black']))
        if data['status'] not in ('BUILDING', 'READY', 'CONSUMED', 'INVALIDATED'):
            raise ValueError('Unknown cycle status')
        result.status = data['status']
        if result.status in ('READY', 'CONSUMED') and (result.s2 is None or result.s2.to_dict()['game_over']):
            raise ValueError('Incomplete or terminal eligible cycle')
        return result


@dataclass(frozen=True)
class Transfer:
    side: str
    src: tuple
    dst: tuple
    piece: str
    before: tuple
    after: tuple
    capture: bool = False


@dataclass(frozen=True)
class Restoration:
    square: tuple
    piece: str


@dataclass(frozen=True)
class InversePlan:
    transfers: tuple
    restorations: tuple
    after_arm: tuple
    target: tuple


def build_inverse_plan(cycle):
    if cycle.status != 'READY' or cycle.s2 is None or cycle.black is None:
        raise ValueError('Only latest READY cycle can be planned')
    if cycle.s2.to_dict()['game_over'] or not cycle.black.physical_verified:
        raise ValueError('Terminal or unverified cycle is not eligible')
    red, black = cycle.red, cycle.black
    if _forward(cycle.s0.board, red) != cycle.s1.board or _forward(cycle.s1.board, black) != cycle.s2.board:
        raise ValueError('Corrupt cycle transitions')
    red_survives = black.dst != red.dst
    moves = [red, black] if red_survives else [black]
    if red_survives and black.dst == red.src:
        moves = [black, red]
    current, transfers = cycle.s2.board, []
    for move in moves:
        inverse = MoveRecord(move.side, move.dst, move.src, move.piece)
        after = _forward(current, inverse)
        transfers.append(Transfer(move.side, inverse.src, inverse.dst, move.piece, current, after))
        current = after
    restorations = []
    if red.captured_piece:
        restorations.append(Restoration(red.dst, red.captured_piece))
    if black.captured_piece:
        restorations.append(Restoration(red.src if not red_survives else black.dst, black.captured_piece))
    restored = [list(row) for row in current]
    for item in restorations:
        c, r = item.square
        if restored[r][c] != '.' or cycle.s0.board[r][c] != item.piece:
            raise ValueError('Invalid manual restoration target')
        restored[r][c] = item.piece
    if _board(restored) != cycle.s0.board:
        raise ValueError('Inverse plan does not restore complete S0')
    return InversePlan(tuple(transfers), tuple(restorations), current, cycle.s0.board)


def manual_restoration_check(plan, observed):
    if len(observed) != 10 or any(len(row) != 9 for row in observed):
        raise ValueError('Expected a 10 by 9 observed board')
    allowed = {item.square: item.piece for item in plan.restorations}
    result = dict(missing=[], wrong=[], unexpected=[], unknown=[])
    for r, row in enumerate(observed):
        for c, piece in enumerate(row):
            square = (c, r)
            expected = allowed.get(square, plan.after_arm[r][c])
            detail = dict(square=square, expected=expected, observed=piece)
            if piece in ('x', None, '?'):
                result['unknown'].append(detail)
            elif square in allowed:
                if piece == '.':
                    result['missing'].append(detail)
                elif piece != expected:
                    result['wrong'].append(detail)
            elif piece != expected:
                result['unexpected'].append(detail)
    result['complete'] = not any(result.values())
    return result
