"""Authoritative temporal gate for physical human moves.

This class is intentionally pure: callers provide a monotonic time in each
observation, and a caller performs a requested commit exactly once.
"""
from __future__ import annotations

from src.vision.legal_successor_matcher import LegalSuccessorMatcher
from src.vision.player_turn_types import (
    BoardObservation, CommitRequest, InteractionCapability, MatchKind,
    PlayerTurnState, Visibility,
)


class PlayerTurnArbiter:
    def __init__(self, *, clear_seconds=0.8, clear_samples=3,
                 interaction_settle_seconds=1.2, idle_settle_seconds=3.0,
                 idle_samples=5):
        self.clear_seconds = float(clear_seconds)
        self.clear_samples = int(clear_samples)
        self.interaction_settle_seconds = float(interaction_settle_seconds)
        self.idle_settle_seconds = float(idle_settle_seconds)
        self.idle_samples = int(idle_samples)
        self.state = PlayerTurnState.INACTIVE
        self._token = 0
        self._matcher = None
        self._interaction_seen = False
        self._clear_started_at = None
        self._clear_samples = 0
        self._candidate = None
        self._candidate_started_at = None
        self._candidate_samples = 0
        self._emitted = False

    @property
    def turn_token(self):
        return self._token

    def activate(self, board, capability=InteractionCapability.AVAILABLE):
        self._token += 1
        self._matcher = LegalSuccessorMatcher(board)
        self._interaction_seen = False
        self._reset_transient()
        self._emitted = False
        self.state = (PlayerTurnState.PLAYER_IDLE
                      if capability == InteractionCapability.AVAILABLE
                      else PlayerTurnState.INACTIVE)
        return self.state

    def deactivate(self):
        self._reset_transient()
        self._matcher = None
        self.state = PlayerTurnState.INACTIVE

    def _reset_transient(self):
        self._clear_started_at = None
        self._clear_samples = 0
        self._candidate = None
        self._candidate_started_at = None
        self._candidate_samples = 0

    @staticmethod
    def _blocked(observation):
        return (observation.visibility != Visibility.CLEAR
                or observation.hand_or_object_present
                or observation.motion_active
                or observation.coverage_ratio < 0.95
                or observation.aggregate_confidence < 0.70)

    def ingest(self, observation: BoardObservation):
        if self._matcher is None or self.state == PlayerTurnState.INACTIVE or self._emitted:
            return None
        now = observation.observed_at
        if self._blocked(observation):
            self._interaction_seen = self._interaction_seen or observation.hand_or_object_present or observation.motion_active
            self._reset_transient()
            self.state = PlayerTurnState.INTERACTING_OR_OCCLUDED
            return None

        if self.state == PlayerTurnState.INTERACTING_OR_OCCLUDED:
            self.state = PlayerTurnState.WAITING_FOR_CLEAR
        if self.state == PlayerTurnState.WAITING_FOR_CLEAR:
            if self._clear_started_at is None:
                self._clear_started_at, self._clear_samples = now, 1
                return None
            self._clear_samples += 1
            if (self._clear_samples < self.clear_samples
                    or now - self._clear_started_at < self.clear_seconds):
                return None
            self.state = PlayerTurnState.VALIDATING_FINAL_BOARD

        result = self._matcher.match(observation.layout)
        if result.kind == MatchKind.BASELINE_EQUAL:
            self._candidate = None
            self._candidate_started_at = None
            self._candidate_samples = 0
            self.state = PlayerTurnState.PLAYER_IDLE
            return None
        if result.kind == MatchKind.AMBIGUOUS:
            self._reset_transient()
            self.state = PlayerTurnState.AMBIGUOUS_BOARD
            return None
        if result.kind in (MatchKind.INVALID, MatchKind.UNAVAILABLE):
            self._reset_transient()
            self.state = PlayerTurnState.WAITING_FOR_CORRECTION
            return None

        # A unique legal successor must stay unchanged and clear continuously.
        if result.move != self._candidate:
            self._candidate = result.move
            self._candidate_started_at = now
            self._candidate_samples = 1
            self.state = PlayerTurnState.UNSETTLED_PLACEMENT
            return None
        self._candidate_samples += 1
        required_seconds = (self.interaction_settle_seconds if self._interaction_seen
                            else self.idle_settle_seconds)
        required_samples = 3 if self._interaction_seen else self.idle_samples
        if (self._candidate_samples < required_samples
                or now - self._candidate_started_at < required_seconds):
            self.state = PlayerTurnState.UNSETTLED_PLACEMENT
            return None
        self._emitted = True
        self.state = PlayerTurnState.MOVE_CONFIRMED
        return CommitRequest(self._token, result.move)
