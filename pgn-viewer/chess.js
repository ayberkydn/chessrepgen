/**
 * Chess.js - Minimal chess logic library for PGN viewer
 * Handles board state, move validation, and FEN parsing
 */

const Chess = (function() {
  // Piece constants
  const PAWN = 'p';
  const KNIGHT = 'n';
  const BISHOP = 'b';
  const ROOK = 'r';
  const QUEEN = 'q';
  const KING = 'k';

  const WHITE = 'w';
  const BLACK = 'b';

  const EMPTY = null;

  // Starting position FEN
  const DEFAULT_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

  // Square indices
  const SQUARES = {
    a8: 0, b8: 1, c8: 2, d8: 3, e8: 4, f8: 5, g8: 6, h8: 7,
    a7: 8, b7: 9, c7: 10, d7: 11, e7: 12, f7: 13, g7: 14, h7: 15,
    a6: 16, b6: 17, c6: 18, d6: 19, e6: 20, f6: 21, g6: 22, h6: 23,
    a5: 24, b5: 25, c5: 26, d5: 27, e5: 28, f5: 29, g5: 30, h5: 31,
    a4: 32, b4: 33, c4: 34, d4: 35, e4: 36, f4: 37, g4: 38, h4: 39,
    a3: 40, b3: 41, c3: 42, d3: 43, e3: 44, f3: 45, g3: 46, h3: 47,
    a2: 48, b2: 49, c2: 50, d2: 51, e2: 52, f2: 53, g2: 54, h2: 55,
    a1: 56, b1: 57, c1: 58, d1: 59, e1: 60, f1: 61, g1: 62, h1: 63
  };

  const SQUARE_NAMES = Object.keys(SQUARES);

  // Piece movement offsets
  const PIECE_OFFSETS = {
    n: [-17, -15, -10, -6, 6, 10, 15, 17],
    b: [-9, -7, 7, 9],
    r: [-8, -1, 1, 8],
    q: [-9, -8, -7, -1, 1, 7, 8, 9],
    k: [-9, -8, -7, -1, 1, 7, 8, 9]
  };

  // Mailbox arrays for move generation
  const MAILBOX = [
    -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
    -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
    -1,  0,  1,  2,  3,  4,  5,  6,  7, -1,
    -1,  8,  9, 10, 11, 12, 13, 14, 15, -1,
    -1, 16, 17, 18, 19, 20, 21, 22, 23, -1,
    -1, 24, 25, 26, 27, 28, 29, 30, 31, -1,
    -1, 32, 33, 34, 35, 36, 37, 38, 39, -1,
    -1, 40, 41, 42, 43, 44, 45, 46, 47, -1,
    -1, 48, 49, 50, 51, 52, 53, 54, 55, -1,
    -1, 56, 57, 58, 59, 60, 61, 62, 63, -1,
    -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
    -1, -1, -1, -1, -1, -1, -1, -1, -1, -1
  ];

  const MAILBOX64 = [
    21, 22, 23, 24, 25, 26, 27, 28,
    31, 32, 33, 34, 35, 36, 37, 38,
    41, 42, 43, 44, 45, 46, 47, 48,
    51, 52, 53, 54, 55, 56, 57, 58,
    61, 62, 63, 64, 65, 66, 67, 68,
    71, 72, 73, 74, 75, 76, 77, 78,
    81, 82, 83, 84, 85, 86, 87, 88,
    91, 92, 93, 94, 95, 96, 97, 98
  ];

  // NAG symbols
  const NAGS = {
    1: '!', 2: '?', 3: '!!', 4: '??', 5: '!?', 6: '?!',
    7: '□', 10: '=', 13: '∞', 14: '⩲', 15: '⩱',
    16: '±', 17: '∓', 18: '+-', 19: '-+',
    22: '⨀', 23: '⨀', 32: '⟳', 33: '⟳',
    36: '→', 37: '→', 40: '↑', 41: '↑',
    132: '⇆', 133: '⇆', 138: '⊕', 139: '⊕',
    140: '∆', 141: '∇', 142: '⌓', 143: '<=',
    144: '==', 145: 'RR', 146: 'N'
  };

  function Chess(fen) {
    this.board = new Array(64).fill(EMPTY);
    this.turn = WHITE;
    this.castling = { K: false, Q: false, k: false, q: false };
    this.epSquare = null;
    this.halfmoves = 0;
    this.fullmoves = 1;
    this.history = [];
    this.kings = { w: null, b: null };

    this.load(fen || DEFAULT_FEN);
  }

  Chess.prototype.load = function(fen) {
    const parts = fen.split(/\s+/);
    const position = parts[0];

    this.board = new Array(64).fill(EMPTY);
    this.kings = { w: null, b: null };

    let square = 0;
    for (let i = 0; i < position.length; i++) {
      const char = position[i];
      if (char === '/') continue;
      if (/[1-8]/.test(char)) {
        square += parseInt(char, 10);
      } else {
        const color = char === char.toUpperCase() ? WHITE : BLACK;
        const piece = char.toLowerCase();
        this.board[square] = { type: piece, color: color };
        if (piece === KING) {
          this.kings[color] = square;
        }
        square++;
      }
    }

    this.turn = parts[1] === 'b' ? BLACK : WHITE;

    this.castling = { K: false, Q: false, k: false, q: false };
    if (parts[2] && parts[2] !== '-') {
      if (parts[2].includes('K')) this.castling.K = true;
      if (parts[2].includes('Q')) this.castling.Q = true;
      if (parts[2].includes('k')) this.castling.k = true;
      if (parts[2].includes('q')) this.castling.q = true;
    }

    this.epSquare = (parts[3] && parts[3] !== '-') ? SQUARES[parts[3]] : null;
    this.halfmoves = parseInt(parts[4], 10) || 0;
    this.fullmoves = parseInt(parts[5], 10) || 1;

    return true;
  };

  Chess.prototype.fen = function() {
    let fen = '';
    let empty = 0;

    for (let i = 0; i < 64; i++) {
      if (i > 0 && i % 8 === 0) {
        if (empty > 0) {
          fen += empty;
          empty = 0;
        }
        fen += '/';
      }

      const piece = this.board[i];
      if (piece === EMPTY) {
        empty++;
      } else {
        if (empty > 0) {
          fen += empty;
          empty = 0;
        }
        const char = piece.type;
        fen += piece.color === WHITE ? char.toUpperCase() : char;
      }
    }
    if (empty > 0) fen += empty;

    fen += ' ' + this.turn;

    let castling = '';
    if (this.castling.K) castling += 'K';
    if (this.castling.Q) castling += 'Q';
    if (this.castling.k) castling += 'k';
    if (this.castling.q) castling += 'q';
    fen += ' ' + (castling || '-');

    fen += ' ' + (this.epSquare !== null ? SQUARE_NAMES[this.epSquare] : '-');
    fen += ' ' + this.halfmoves;
    fen += ' ' + this.fullmoves;

    return fen;
  };

  Chess.prototype.get = function(square) {
    const idx = typeof square === 'string' ? SQUARES[square] : square;
    return this.board[idx];
  };

  Chess.prototype.put = function(piece, square) {
    const idx = typeof square === 'string' ? SQUARES[square] : square;
    this.board[idx] = piece;
    if (piece && piece.type === KING) {
      this.kings[piece.color] = idx;
    }
  };

  Chess.prototype.remove = function(square) {
    const idx = typeof square === 'string' ? SQUARES[square] : square;
    const piece = this.board[idx];
    this.board[idx] = EMPTY;
    return piece;
  };

  // Check if a square is attacked by a given color
  Chess.prototype.isAttacked = function(square, color) {
    const idx = typeof square === 'string' ? SQUARES[square] : square;

    // Check pawn attacks
    const pawnDir = color === WHITE ? -1 : 1;
    const pawnRank = Math.floor(idx / 8);
    const file = idx % 8;

    for (const fileOffset of [-1, 1]) {
      const newFile = file + fileOffset;
      const newRank = pawnRank + pawnDir;
      if (newFile >= 0 && newFile < 8 && newRank >= 0 && newRank < 8) {
        const newIdx = newRank * 8 + newFile;
        const piece = this.board[newIdx];
        if (piece && piece.type === PAWN && piece.color === color) {
          return true;
        }
      }
    }

    // Check knight attacks
    for (const offset of PIECE_OFFSETS.n) {
      const newIdx = MAILBOX[MAILBOX64[idx] + offset];
      if (newIdx !== -1) {
        const piece = this.board[newIdx];
        if (piece && piece.type === KNIGHT && piece.color === color) {
          return true;
        }
      }
    }

    // Check king attacks
    for (const offset of PIECE_OFFSETS.k) {
      const newIdx = MAILBOX[MAILBOX64[idx] + offset];
      if (newIdx !== -1) {
        const piece = this.board[newIdx];
        if (piece && piece.type === KING && piece.color === color) {
          return true;
        }
      }
    }

    // Check sliding pieces (bishop, rook, queen)
    for (const [pieceType, offsets] of [['b', PIECE_OFFSETS.b], ['r', PIECE_OFFSETS.r]]) {
      for (const offset of offsets) {
        let newIdx = idx;
        while (true) {
          newIdx = MAILBOX[MAILBOX64[newIdx] + offset];
          if (newIdx === -1) break;

          const piece = this.board[newIdx];
          if (piece) {
            if (piece.color === color && (piece.type === pieceType || piece.type === QUEEN)) {
              return true;
            }
            break;
          }
        }
      }
    }

    return false;
  };

  Chess.prototype.inCheck = function() {
    const kingSquare = this.kings[this.turn];
    return this.isAttacked(kingSquare, this.turn === WHITE ? BLACK : WHITE);
  };

  Chess.prototype.isCheckmate = function() {
    return this.inCheck() && this.generateMoves().length === 0;
  };

  Chess.prototype.isStalemate = function() {
    return !this.inCheck() && this.generateMoves().length === 0;
  };

  Chess.prototype.isDraw = function() {
    return this.isStalemate() || this.halfmoves >= 100 || this.isInsufficientMaterial();
  };

  Chess.prototype.isInsufficientMaterial = function() {
    const pieces = { w: [], b: [] };
    for (let i = 0; i < 64; i++) {
      const piece = this.board[i];
      if (piece && piece.type !== KING) {
        pieces[piece.color].push({ type: piece.type, square: i });
      }
    }

    // King vs King
    if (pieces.w.length === 0 && pieces.b.length === 0) return true;

    // King + minor vs King
    if (pieces.w.length === 0 && pieces.b.length === 1) {
      if (pieces.b[0].type === BISHOP || pieces.b[0].type === KNIGHT) return true;
    }
    if (pieces.b.length === 0 && pieces.w.length === 1) {
      if (pieces.w[0].type === BISHOP || pieces.w[0].type === KNIGHT) return true;
    }

    // King + Bishop vs King + Bishop (same color)
    if (pieces.w.length === 1 && pieces.b.length === 1) {
      if (pieces.w[0].type === BISHOP && pieces.b[0].type === BISHOP) {
        const sq1 = pieces.w[0].square;
        const sq2 = pieces.b[0].square;
        const color1 = (Math.floor(sq1 / 8) + sq1 % 8) % 2;
        const color2 = (Math.floor(sq2 / 8) + sq2 % 8) % 2;
        if (color1 === color2) return true;
      }
    }

    return false;
  };

  Chess.prototype.isGameOver = function() {
    return this.isCheckmate() || this.isDraw();
  };

  // Generate all legal moves
  Chess.prototype.generateMoves = function() {
    const moves = [];
    const us = this.turn;
    const them = us === WHITE ? BLACK : WHITE;

    for (let from = 0; from < 64; from++) {
      const piece = this.board[from];
      if (!piece || piece.color !== us) continue;

      if (piece.type === PAWN) {
        const dir = us === WHITE ? -8 : 8;
        const startRank = us === WHITE ? 6 : 1;
        const promoRank = us === WHITE ? 0 : 7;
        const rank = Math.floor(from / 8);
        const file = from % 8;

        // Single push
        const to1 = from + dir;
        if (to1 >= 0 && to1 < 64 && !this.board[to1]) {
          if (Math.floor(to1 / 8) === promoRank) {
            for (const promo of [QUEEN, ROOK, BISHOP, KNIGHT]) {
              moves.push({ from, to: to1, promotion: promo });
            }
          } else {
            moves.push({ from, to: to1 });
          }

          // Double push
          if (rank === startRank) {
            const to2 = from + dir * 2;
            if (!this.board[to2]) {
              moves.push({ from, to: to2 });
            }
          }
        }

        // Captures
        for (const fileOffset of [-1, 1]) {
          const newFile = file + fileOffset;
          if (newFile < 0 || newFile >= 8) continue;
          const to = from + dir + fileOffset;
          if (to < 0 || to >= 64) continue;

          const target = this.board[to];
          if ((target && target.color === them) || to === this.epSquare) {
            if (Math.floor(to / 8) === promoRank) {
              for (const promo of [QUEEN, ROOK, BISHOP, KNIGHT]) {
                moves.push({ from, to, promotion: promo, capture: true });
              }
            } else {
              moves.push({ from, to, capture: true });
            }
          }
        }
      } else if (piece.type === KNIGHT) {
        for (const offset of PIECE_OFFSETS.n) {
          const to = MAILBOX[MAILBOX64[from] + offset];
          if (to === -1) continue;
          const target = this.board[to];
          if (!target || target.color === them) {
            moves.push({ from, to, capture: !!target });
          }
        }
      } else if (piece.type === KING) {
        for (const offset of PIECE_OFFSETS.k) {
          const to = MAILBOX[MAILBOX64[from] + offset];
          if (to === -1) continue;
          const target = this.board[to];
          if (!target || target.color === them) {
            moves.push({ from, to, capture: !!target });
          }
        }

        // Castling
        if (!this.inCheck()) {
          if (us === WHITE) {
            if (this.castling.K && !this.board[61] && !this.board[62] &&
                !this.isAttacked(61, them) && !this.isAttacked(62, them)) {
              moves.push({ from: 60, to: 62, castling: 'K' });
            }
            if (this.castling.Q && !this.board[59] && !this.board[58] && !this.board[57] &&
                !this.isAttacked(59, them) && !this.isAttacked(58, them)) {
              moves.push({ from: 60, to: 58, castling: 'Q' });
            }
          } else {
            if (this.castling.k && !this.board[5] && !this.board[6] &&
                !this.isAttacked(5, them) && !this.isAttacked(6, them)) {
              moves.push({ from: 4, to: 6, castling: 'k' });
            }
            if (this.castling.q && !this.board[3] && !this.board[2] && !this.board[1] &&
                !this.isAttacked(3, them) && !this.isAttacked(2, them)) {
              moves.push({ from: 4, to: 2, castling: 'q' });
            }
          }
        }
      } else {
        // Sliding pieces
        const offsets = piece.type === BISHOP ? PIECE_OFFSETS.b :
                        piece.type === ROOK ? PIECE_OFFSETS.r : PIECE_OFFSETS.q;

        for (const offset of offsets) {
          let to = from;
          while (true) {
            to = MAILBOX[MAILBOX64[to] + offset];
            if (to === -1) break;
            const target = this.board[to];
            if (!target) {
              moves.push({ from, to });
            } else {
              if (target.color === them) {
                moves.push({ from, to, capture: true });
              }
              break;
            }
          }
        }
      }
    }

    // Filter illegal moves (those that leave king in check)
    return moves.filter(move => {
      const savedState = this.saveState();
      this.makeMove(move, true);
      const kingSquare = this.kings[us];
      const inCheck = this.isAttacked(kingSquare, them);
      this.restoreState(savedState);
      return !inCheck;
    });
  };

  Chess.prototype.saveState = function() {
    return {
      board: this.board.map(p => p ? { ...p } : null),
      turn: this.turn,
      castling: { ...this.castling },
      epSquare: this.epSquare,
      halfmoves: this.halfmoves,
      fullmoves: this.fullmoves,
      kings: { ...this.kings }
    };
  };

  Chess.prototype.restoreState = function(state) {
    this.board = state.board;
    this.turn = state.turn;
    this.castling = state.castling;
    this.epSquare = state.epSquare;
    this.halfmoves = state.halfmoves;
    this.fullmoves = state.fullmoves;
    this.kings = state.kings;
  };

  // Make a move (internal, doesn't validate)
  Chess.prototype.makeMove = function(move, skipHistory) {
    const us = this.turn;
    const them = us === WHITE ? BLACK : WHITE;
    const piece = this.board[move.from];

    if (!skipHistory) {
      this.history.push({
        move: { ...move },
        state: this.saveState()
      });
    }

    // Remove piece from source
    this.board[move.from] = EMPTY;

    // Handle en passant capture
    if (piece.type === PAWN && move.to === this.epSquare) {
      const captureSquare = move.to + (us === WHITE ? 8 : -8);
      this.board[captureSquare] = EMPTY;
    }

    // Handle castling
    if (move.castling) {
      if (move.castling === 'K' || move.castling === 'k') {
        const rookFrom = move.to + 1;
        const rookTo = move.to - 1;
        this.board[rookTo] = this.board[rookFrom];
        this.board[rookFrom] = EMPTY;
      } else {
        const rookFrom = move.to - 2;
        const rookTo = move.to + 1;
        this.board[rookTo] = this.board[rookFrom];
        this.board[rookFrom] = EMPTY;
      }
    }

    // Place piece at destination (with promotion if applicable)
    if (move.promotion) {
      this.board[move.to] = { type: move.promotion, color: us };
    } else {
      this.board[move.to] = piece;
    }

    // Update king position
    if (piece.type === KING) {
      this.kings[us] = move.to;
    }

    // Update en passant square
    if (piece.type === PAWN && Math.abs(move.to - move.from) === 16) {
      this.epSquare = (move.from + move.to) / 2;
    } else {
      this.epSquare = null;
    }

    // Update castling rights
    if (piece.type === KING) {
      if (us === WHITE) {
        this.castling.K = false;
        this.castling.Q = false;
      } else {
        this.castling.k = false;
        this.castling.q = false;
      }
    }
    if (piece.type === ROOK) {
      if (move.from === 63) this.castling.K = false;
      if (move.from === 56) this.castling.Q = false;
      if (move.from === 7) this.castling.k = false;
      if (move.from === 0) this.castling.q = false;
    }
    // Update castling if rook is captured
    if (move.to === 63) this.castling.K = false;
    if (move.to === 56) this.castling.Q = false;
    if (move.to === 7) this.castling.k = false;
    if (move.to === 0) this.castling.q = false;

    // Update halfmove clock
    if (piece.type === PAWN || move.capture) {
      this.halfmoves = 0;
    } else {
      this.halfmoves++;
    }

    // Update fullmove number
    if (this.turn === BLACK) {
      this.fullmoves++;
    }

    // Switch turns
    this.turn = them;
  };

  // Parse SAN and make move
  Chess.prototype.move = function(san) {
    const moves = this.generateMoves();
    const move = this.sanToMove(san, moves);

    if (!move) {
      return null;
    }

    const us = this.turn;
    const piece = this.board[move.from];

    this.makeMove(move);

    // Generate SAN for the move
    move.san = this.moveToSan(move, piece, us);
    move.piece = piece;

    return move;
  };

  // Convert SAN to move object
  Chess.prototype.sanToMove = function(san, moves) {
    // Clean SAN
    san = san.replace(/[+#?!=]/g, '').replace(/x/g, '');

    // Castling
    if (san === 'O-O' || san === '0-0') {
      return moves.find(m => m.castling === (this.turn === WHITE ? 'K' : 'k'));
    }
    if (san === 'O-O-O' || san === '0-0-0') {
      return moves.find(m => m.castling === (this.turn === WHITE ? 'Q' : 'q'));
    }

    let pieceType = PAWN;
    let promotion = null;
    let fromFile = null;
    let fromRank = null;
    let toSquare = null;

    // Check for promotion
    const promoMatch = san.match(/=?([QRBN])$/);
    if (promoMatch) {
      promotion = promoMatch[1].toLowerCase();
      san = san.replace(/=?[QRBN]$/, '');
    }

    // Parse piece type
    if (/^[KQRBN]/.test(san)) {
      pieceType = san[0].toLowerCase();
      san = san.slice(1);
    }

    // Parse destination square (last 2 chars)
    toSquare = san.slice(-2);
    const toIdx = SQUARES[toSquare];
    if (toIdx === undefined) return null;
    san = san.slice(0, -2);

    // Parse disambiguation
    if (san.length > 0) {
      for (const char of san) {
        if (/[a-h]/.test(char)) {
          fromFile = char.charCodeAt(0) - 'a'.charCodeAt(0);
        } else if (/[1-8]/.test(char)) {
          fromRank = 8 - parseInt(char, 10);
        }
      }
    }

    // Find matching move
    for (const move of moves) {
      const piece = this.board[move.from];
      if (piece.type !== pieceType) continue;
      if (move.to !== toIdx) continue;
      if (promotion && move.promotion !== promotion) continue;
      if (!promotion && move.promotion) continue;

      const file = move.from % 8;
      const rank = Math.floor(move.from / 8);

      if (fromFile !== null && file !== fromFile) continue;
      if (fromRank !== null && rank !== fromRank) continue;

      return move;
    }

    return null;
  };

  // Convert move to SAN
  Chess.prototype.moveToSan = function(move, piece, color) {
    if (move.castling === 'K' || move.castling === 'k') return 'O-O';
    if (move.castling === 'Q' || move.castling === 'q') return 'O-O-O';

    let san = '';
    const toSquare = SQUARE_NAMES[move.to];

    if (piece.type !== PAWN) {
      san += piece.type.toUpperCase();
    }

    // Add disambiguation if needed
    // (Simplified - just add file for pawns capturing)
    if (piece.type === PAWN && move.capture) {
      san += SQUARE_NAMES[move.from][0];
    }

    if (move.capture) {
      san += 'x';
    }

    san += toSquare;

    if (move.promotion) {
      san += '=' + move.promotion.toUpperCase();
    }

    // Check for check/checkmate
    const savedState = this.saveState();
    // Check if move puts opponent in check
    const them = color === WHITE ? BLACK : WHITE;
    const theirKing = this.kings[them];
    if (this.isAttacked(theirKing, color)) {
      const tempTurn = this.turn;
      this.turn = them;
      if (this.generateMoves().length === 0) {
        san += '#';
      } else {
        san += '+';
      }
      this.turn = tempTurn;
    }

    return san;
  };

  Chess.prototype.undo = function() {
    if (this.history.length === 0) return null;
    const { move, state } = this.history.pop();
    this.restoreState(state);
    return move;
  };

  Chess.prototype.reset = function() {
    this.load(DEFAULT_FEN);
    this.history = [];
  };

  // Get board as 2D array for rendering
  Chess.prototype.board2D = function() {
    const result = [];
    for (let rank = 0; rank < 8; rank++) {
      const row = [];
      for (let file = 0; file < 8; file++) {
        row.push(this.board[rank * 8 + file]);
      }
      result.push(row);
    }
    return result;
  };

  // Static helpers
  Chess.SQUARES = SQUARES;
  Chess.SQUARE_NAMES = SQUARE_NAMES;
  Chess.WHITE = WHITE;
  Chess.BLACK = BLACK;
  Chess.NAGS = NAGS;

  return Chess;
})();

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
  module.exports = Chess;
}
