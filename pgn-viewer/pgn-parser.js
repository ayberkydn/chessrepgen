/**
 * PGN Parser - Parses PGN format into a structured game tree
 * Supports variations, comments, NAGs, and standard headers
 */

const PGNParser = (function() {

  function PGNParser() {}

  // Parse PGN text into game objects
  PGNParser.parse = function(pgn) {
    const games = [];

    // Split into individual games (separated by empty lines between games)
    const gameTexts = splitGames(pgn);

    for (const gameText of gameTexts) {
      const game = parseGame(gameText);
      if (game) {
        games.push(game);
      }
    }

    return games;
  };

  function splitGames(pgn) {
    // Normalize line endings
    pgn = pgn.replace(/\r\n/g, '\n').replace(/\r/g, '\n');

    const games = [];
    let current = '';
    let inHeader = false;
    let hasContent = false;

    const lines = pgn.split('\n');

    for (const line of lines) {
      const trimmed = line.trim();

      if (trimmed.startsWith('[')) {
        // Header line
        if (hasContent && !inHeader) {
          // New game starting
          if (current.trim()) {
            games.push(current.trim());
          }
          current = '';
          hasContent = false;
        }
        inHeader = true;
        current += line + '\n';
      } else if (trimmed === '') {
        if (inHeader) {
          inHeader = false;
        }
        current += '\n';
      } else {
        inHeader = false;
        hasContent = true;
        current += line + '\n';
      }
    }

    if (current.trim()) {
      games.push(current.trim());
    }

    return games;
  }

  function parseGame(text) {
    const game = {
      headers: {},
      moves: [],
      result: '*'
    };

    // Parse headers
    const headerRegex = /\[(\w+)\s+"([^"]*)"\]/g;
    let match;
    while ((match = headerRegex.exec(text)) !== null) {
      game.headers[match[1]] = match[2];
    }

    // Extract movetext (everything after headers)
    const movetext = text.replace(/\[[^\]]*\]/g, '').trim();

    if (!movetext) {
      return game;
    }

    // Parse moves
    game.moves = parseMovetext(movetext);

    // Extract result
    const resultMatch = movetext.match(/(1-0|0-1|1\/2-1\/2|\*)$/);
    if (resultMatch) {
      game.result = resultMatch[1];
    }

    return game;
  }

  function parseMovetext(text) {
    const tokens = tokenize(text);
    const moves = [];
    let i = 0;

    function parseVariation() {
      const variation = [];

      while (i < tokens.length) {
        const token = tokens[i];

        if (token.type === 'move') {
          const move = {
            san: token.value,
            comments: [],
            nags: [],
            variations: []
          };
          i++;

          // Collect comments, NAGs, and variations after move
          while (i < tokens.length) {
            const next = tokens[i];
            if (next.type === 'comment') {
              move.comments.push(next.value);
              i++;
            } else if (next.type === 'nag') {
              move.nags.push(next.value);
              i++;
            } else if (next.type === 'variation_start') {
              i++;
              move.variations.push(parseVariation());
            } else {
              break;
            }
          }

          variation.push(move);
        } else if (token.type === 'variation_end') {
          i++;
          break;
        } else if (token.type === 'comment') {
          // Comment before first move (or between moves)
          if (variation.length > 0) {
            variation[variation.length - 1].comments.push(token.value);
          }
          i++;
        } else if (token.type === 'nag') {
          if (variation.length > 0) {
            variation[variation.length - 1].nags.push(token.value);
          }
          i++;
        } else if (token.type === 'variation_start') {
          i++;
          if (variation.length > 0) {
            variation[variation.length - 1].variations.push(parseVariation());
          } else {
            // Variation at start - create placeholder
            parseVariation();
          }
        } else if (token.type === 'result') {
          i++;
          // Skip result token
        } else {
          i++;
        }
      }

      return variation;
    }

    return parseVariation();
  }

  function tokenize(text) {
    const tokens = [];
    let i = 0;

    while (i < text.length) {
      const char = text[i];

      // Skip whitespace
      if (/\s/.test(char)) {
        i++;
        continue;
      }

      // Comment in braces
      if (char === '{') {
        let comment = '';
        i++;
        while (i < text.length && text[i] !== '}') {
          comment += text[i];
          i++;
        }
        i++; // Skip closing brace
        tokens.push({ type: 'comment', value: comment.trim() });
        continue;
      }

      // Comment with semicolon (to end of line)
      if (char === ';') {
        let comment = '';
        i++;
        while (i < text.length && text[i] !== '\n') {
          comment += text[i];
          i++;
        }
        tokens.push({ type: 'comment', value: comment.trim() });
        continue;
      }

      // Variation start
      if (char === '(') {
        tokens.push({ type: 'variation_start' });
        i++;
        continue;
      }

      // Variation end
      if (char === ')') {
        tokens.push({ type: 'variation_end' });
        i++;
        continue;
      }

      // NAG
      if (char === '$') {
        let nag = '';
        i++;
        while (i < text.length && /\d/.test(text[i])) {
          nag += text[i];
          i++;
        }
        tokens.push({ type: 'nag', value: parseInt(nag, 10) });
        continue;
      }

      // Move number (skip)
      if (/\d/.test(char)) {
        let num = '';
        while (i < text.length && /[\d.]/.test(text[i])) {
          num += text[i];
          i++;
        }
        // Check if it's a result
        if (num === '1-0' || num === '0-1') {
          tokens.push({ type: 'result', value: num });
        } else if (text.substring(i - num.length, i + 5).includes('1/2-1/2')) {
          tokens.push({ type: 'result', value: '1/2-1/2' });
          i = text.indexOf('1/2-1/2', i - num.length) + 7;
        }
        // Otherwise skip move number
        continue;
      }

      // Result
      if (char === '*') {
        tokens.push({ type: 'result', value: '*' });
        i++;
        continue;
      }

      // Annotation symbols
      if (char === '!' || char === '?') {
        let annotation = '';
        while (i < text.length && (text[i] === '!' || text[i] === '?')) {
          annotation += text[i];
          i++;
        }
        // Convert to NAG
        const nagMap = { '!': 1, '?': 2, '!!': 3, '??': 4, '!?': 5, '?!': 6 };
        if (nagMap[annotation] !== undefined) {
          tokens.push({ type: 'nag', value: nagMap[annotation] });
        }
        continue;
      }

      // Move (starts with letter or O for castling)
      if (/[a-hKQRBNO]/.test(char)) {
        let move = '';
        while (i < text.length && /[a-hKQRBNO0-8x=+#\-]/.test(text[i])) {
          move += text[i];
          i++;
        }
        if (move) {
          // Normalize castling
          move = move.replace(/0-0-0/g, 'O-O-O').replace(/0-0/g, 'O-O');
          tokens.push({ type: 'move', value: move });
        }
        continue;
      }

      // Skip unknown characters
      i++;
    }

    return tokens;
  }

  // Convert parsed game back to PGN string
  PGNParser.stringify = function(game) {
    let pgn = '';

    // Headers
    for (const [key, value] of Object.entries(game.headers)) {
      pgn += `[${key} "${value}"]\n`;
    }
    pgn += '\n';

    // Moves
    pgn += stringifyMoves(game.moves, true, 1);

    // Result
    pgn += ' ' + game.result;

    return pgn;
  };

  function stringifyMoves(moves, isMainline, startMoveNum) {
    let result = '';
    let moveNum = startMoveNum;
    let isWhite = true;

    for (let i = 0; i < moves.length; i++) {
      const move = moves[i];

      // Move number
      if (isWhite || i === 0) {
        result += moveNum + (isWhite ? '. ' : '... ');
      }

      // Move
      result += move.san;

      // NAGs
      for (const nag of move.nags) {
        const symbol = Chess.NAGS[nag];
        if (symbol) {
          result += symbol;
        } else {
          result += ' $' + nag;
        }
      }

      // Comments
      for (const comment of move.comments) {
        result += ' { ' + comment + ' }';
      }

      // Variations
      for (const variation of move.variations) {
        result += ' (' + stringifyMoves(variation, false, moveNum - (isWhite ? 0 : 1)) + ')';
      }

      result += ' ';

      if (!isWhite) {
        moveNum++;
      }
      isWhite = !isWhite;
    }

    return result.trim();
  }

  return PGNParser;
})();

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
  module.exports = PGNParser;
}
