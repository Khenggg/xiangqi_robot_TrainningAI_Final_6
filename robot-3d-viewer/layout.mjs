// Canonical Xiangqi Start Layout
// Project convention:
//   Black (Robot): row 0..4  (row 0 is Black backline)
//   Red (Human):   row 5..9  (row 9 is Red backline)
//
// Format: [col, row, piece_type, side]
// piece_type: 'k'=King, 'a'=Advisor, 'b'=Elephant (Bishop), 'n'=Knight, 'r'=Rook, 'c'=Cannon, 'p'=Pawn
// side: 'b'=Black, 'r'=Red

export const LABEL_RED = Object.freeze({
  k: "帥",
  a: "仕",
  b: "相",
  n: "馬",
  r: "車",
  c: "砲",
  p: "兵",
});

export const LABEL_BLACK = Object.freeze({
  k: "將",
  a: "士",
  b: "象",
  n: "馬",
  r: "車",
  c: "炮",
  p: "卒",
});

export const START_LAYOUT = Object.freeze([
  // Black pieces (row 0 to 4) - Robot side
  [0, 0, "r", "b", "black_rook_0"],
  [1, 0, "n", "b", "black_knight_0"],
  [2, 0, "b", "b", "black_elephant_0"],
  [3, 0, "a", "b", "black_advisor_0"],
  [4, 0, "k", "b", "black_king_0"],
  [5, 0, "a", "b", "black_advisor_1"],
  [6, 0, "b", "b", "black_elephant_1"],
  [7, 0, "n", "b", "black_knight_1"],
  [8, 0, "r", "b", "black_rook_1"],
  [1, 2, "c", "b", "black_cannon_0"],
  [7, 2, "c", "b", "black_cannon_1"],
  [0, 3, "p", "b", "black_pawn_0"],
  [2, 3, "p", "b", "black_pawn_1"],
  [4, 3, "p", "b", "black_pawn_2"],
  [6, 3, "p", "b", "black_pawn_3"],
  [8, 3, "p", "b", "black_pawn_4"],

  // Red pieces (row 5 to 9) - Human side
  [0, 6, "p", "r", "red_pawn_0"],
  [2, 6, "p", "r", "red_pawn_1"],
  [4, 6, "p", "r", "red_pawn_2"],
  [6, 6, "p", "r", "red_pawn_3"],
  [8, 6, "p", "r", "red_pawn_4"],
  [1, 7, "c", "r", "red_cannon_0"],
  [7, 7, "c", "r", "red_cannon_1"],
  [0, 9, "r", "r", "red_rook_0"],
  [1, 9, "n", "r", "red_knight_0"],
  [2, 9, "b", "r", "red_elephant_0"],
  [3, 9, "a", "r", "red_advisor_0"],
  [4, 9, "k", "r", "red_king_0"],
  [5, 9, "a", "r", "red_advisor_1"],
  [6, 9, "b", "r", "red_elephant_1"],
  [7, 9, "n", "r", "red_knight_1"],
  [8, 9, "r", "r", "red_rook_1"],
]);
