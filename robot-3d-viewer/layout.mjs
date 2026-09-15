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
  [0, 0, "r", "b"], [1, 0, "n", "b"], [2, 0, "b", "b"], [3, 0, "a", "b"],
  [4, 0, "k", "b"], [5, 0, "a", "b"], [6, 0, "b", "b"], [7, 0, "n", "b"],
  [8, 0, "r", "b"],
  [1, 2, "c", "b"], [7, 2, "c", "b"],
  [0, 3, "p", "b"], [2, 3, "p", "b"], [4, 3, "p", "b"], [6, 3, "p", "b"], [8, 3, "p", "b"],

  // Red pieces (row 5 to 9) - Human side
  [0, 6, "p", "r"], [2, 6, "p", "r"], [4, 6, "p", "r"], [6, 6, "p", "r"], [8, 6, "p", "r"],
  [1, 7, "c", "r"], [7, 7, "c", "r"],
  [0, 9, "r", "r"], [1, 9, "n", "r"], [2, 9, "b", "r"], [3, 9, "a", "r"],
  [4, 9, "k", "r"], [5, 9, "a", "r"], [6, 9, "b", "r"], [7, 9, "n", "r"],
  [8, 9, "r", "r"],
]);
