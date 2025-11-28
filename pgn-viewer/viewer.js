/**
 * PGN Viewer - Lichess-style chess game viewer
 * Main application logic with full variation/branch support
 */

const PGNViewer = (function () {
  // Piece SVGs (Lichess cburnett style)
  const PIECE_SVGS = {
    wK: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 45 45"><g fill="none" fill-rule="evenodd" stroke="#000" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"><path stroke-linejoin="miter" d="M22.5 11.63V6M20 8h5"/><path fill="#fff" stroke-linecap="butt" stroke-linejoin="miter" d="M22.5 25s4.5-7.5 3-10.5c0 0-1-2.5-3-2.5s-3 2.5-3 2.5c-1.5 3 3 10.5 3 10.5"/><path fill="#fff" d="M11.5 37c5.5 3.5 15.5 3.5 21 0v-7s9-4.5 6-10.5c-4-6.5-13.5-3.5-16 4V27v-3.5c-3.5-7.5-13-10.5-16-4-3 6 5 10 5 10V37z"/><path d="M11.5 30c5.5-3 15.5-3 21 0m-21 3.5c5.5-3 15.5-3 21 0m-21 3.5c5.5-3 15.5-3 21 0"/></g></svg>`,
    wQ: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 45 45"><g fill="#fff" fill-rule="evenodd" stroke="#000" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"><path d="M8 12a2 2 0 1 1-4 0 2 2 0 1 1 4 0zm16.5-4.5a2 2 0 1 1-4 0 2 2 0 1 1 4 0zM41 12a2 2 0 1 1-4 0 2 2 0 1 1 4 0zM16 8.5a2 2 0 1 1-4 0 2 2 0 1 1 4 0zM33 9a2 2 0 1 1-4 0 2 2 0 1 1 4 0z"/><path stroke-linecap="butt" d="M9 26c8.5-1.5 21-1.5 27 0l2-12-7 11V11l-5.5 13.5-3-15-3 15-5.5-14V25L6 14l3 12z"/><path stroke-linecap="butt" d="M9 26c0 2 1.5 2 2.5 4 1 1.5 1 1 .5 3.5-1.5 1-1.5 2.5-1.5 2.5-1.5 1.5.5 2.5.5 2.5 6.5 1 16.5 1 23 0 0 0 1.5-1 0-2.5 0 0 .5-1.5-1-2.5-.5-2.5-.5-2 .5-3.5 1-2 2.5-2 2.5-4-8.5-1.5-18.5-1.5-27 0z"/><path fill="none" d="M11.5 30c3.5-1 18.5-1 22 0M12 33.5c6-1 15-1 21 0"/></g></svg>`,
    wR: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 45 45"><g fill="#fff" fill-rule="evenodd" stroke="#000" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"><path stroke-linecap="butt" d="M9 39h27v-3H9v3zm3-3v-4h21v4H12zm-1-22V9h4v2h5V9h5v2h5V9h4v5"/><path d="M34 14l-3 3H14l-3-3"/><path stroke-linecap="butt" stroke-linejoin="miter" d="M31 17v12.5H14V17"/><path d="M31 29.5l1.5 2.5h-20l1.5-2.5"/><path fill="none" stroke-linejoin="miter" d="M11 14h23"/></g></svg>`,
    wB: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 45 45"><g fill="none" fill-rule="evenodd" stroke="#000" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"><g fill="#fff" stroke-linecap="butt"><path d="M9 36c3.39-.97 10.11.43 13.5-2 3.39 2.43 10.11 1.03 13.5 2 0 0 1.65.54 3 2-.68.97-1.65.99-3 .5-3.39-.97-10.11.46-13.5-1-3.39 1.46-10.11.03-13.5 1-1.35.49-2.32.47-3-.5 1.35-1.46 3-2 3-2z"/><path d="M15 32c2.5 2.5 12.5 2.5 15 0 .5-1.5 0-2 0-2 0-2.5-2.5-4-2.5-4 5.5-1.5 6-11.5-5-15.5-11 4-10.5 14-5 15.5 0 0-2.5 1.5-2.5 4 0 0-.5.5 0 2z"/><path d="M25 8a2.5 2.5 0 1 1-5 0 2.5 2.5 0 1 1 5 0z"/></g><path stroke-linejoin="miter" d="M17.5 26h10M15 30h15m-7.5-14.5v5M20 18h5"/></g></svg>`,
    wN: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 45 45"><g fill="none" fill-rule="evenodd" stroke="#000" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"><path fill="#fff" d="M22 10c10.5 1 16.5 8 16 29H15c0-9 10-6.5 8-21"/><path fill="#fff" d="M24 18c.38 2.91-5.55 7.37-8 9-3 2-2.82 4.34-5 4-1.042-.94 1.41-3.04 0-3-1 0 .19 1.23-1 2-1 0-4.003 1-4-4 0-2 6-12 6-12s1.89-1.9 2-3.5c-.73-.994-.5-2-.5-3 1-1 3 2.5 3 2.5h2s.78-1.992 2.5-3c1 0 1 3 1 3"/><path fill="#000" d="M9.5 25.5a.5.5 0 1 1-1 0 .5.5 0 1 1 1 0zm5.433-9.75a.5 1.5 30 1 1-.866-.5.5 1.5 30 1 1 .866.5z"/></g></svg>`,
    wP: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 45 45"><path fill="#fff" stroke="#000" stroke-width="1.5" d="M22.5 9c-2.21 0-4 1.79-4 4 0 .89.29 1.71.78 2.38C17.33 16.5 16 18.59 16 21c0 2.03.94 3.84 2.41 5.03-3 1.06-7.41 5.55-7.41 13.47h23c0-7.92-4.41-12.41-7.41-13.47 1.47-1.19 2.41-3 2.41-5.03 0-2.41-1.33-4.5-3.28-5.62.49-.67.78-1.49.78-2.38 0-2.21-1.79-4-4-4z"/></svg>`,
    bK: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 45 45"><g fill="none" fill-rule="evenodd" stroke="#000" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"><path stroke-linejoin="miter" d="M22.5 11.63V6"/><path fill="#000" stroke-linecap="butt" stroke-linejoin="miter" d="M22.5 25s4.5-7.5 3-10.5c0 0-1-2.5-3-2.5s-3 2.5-3 2.5c-1.5 3 3 10.5 3 10.5"/><path fill="#000" d="M11.5 37c5.5 3.5 15.5 3.5 21 0v-7s9-4.5 6-10.5c-4-6.5-13.5-3.5-16 4V27v-3.5c-3.5-7.5-13-10.5-16-4-3 6 5 10 5 10V37z"/><path stroke-linejoin="miter" d="M20 8h5"/><path stroke="#fff" d="M11.5 30c5.5-3 15.5-3 21 0m-21 3.5c5.5-3 15.5-3 21 0m-21 3.5c5.5-3 15.5-3 21 0"/></g></svg>`,
    bQ: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 45 45"><g fill-rule="evenodd" stroke="#000" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"><g fill="#000" stroke="none"><circle cx="6" cy="12" r="2.75"/><circle cx="14" cy="9" r="2.75"/><circle cx="22.5" cy="8" r="2.75"/><circle cx="31" cy="9" r="2.75"/><circle cx="39" cy="12" r="2.75"/></g><path fill="#000" stroke-linecap="butt" d="M9 26c8.5-1.5 21-1.5 27 0l2.5-12.5L31 25l-.3-14.1-5.2 13.6-3-14.5-3 14.5-5.2-13.6L14 25 6.5 13.5 9 26z"/><path fill="#000" stroke-linecap="butt" d="M9 26c0 2 1.5 2 2.5 4 1 1.5 1 1 .5 3.5-1.5 1-1.5 2.5-1.5 2.5-1.5 1.5.5 2.5.5 2.5 6.5 1 16.5 1 23 0 0 0 1.5-1 0-2.5 0 0 .5-1.5-1-2.5-.5-2.5-.5-2 .5-3.5 1-2 2.5-2 2.5-4-8.5-1.5-18.5-1.5-27 0z"/><path fill="none" stroke="#fff" d="M11.5 30c3.5-1 18.5-1 22 0M12 33.5c6-1 15-1 21 0"/></g></svg>`,
    bR: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 45 45"><g fill-rule="evenodd" stroke="#000" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"><path fill="#000" stroke-linecap="butt" d="M9 39h27v-3H9v3zm3.5-7l1.5-2.5h17l1.5 2.5h-20zm-.5 4v-4h21v4H12z"/><path fill="#000" stroke-linecap="butt" stroke-linejoin="miter" d="M14 29.5v-13h17v13H14z"/><path fill="#000" stroke-linecap="butt" d="M14 16.5L11 14h23l-3 2.5H14zM11 14V9h4v2h5V9h5v2h5V9h4v5H11z"/><path fill="none" stroke="#fff" stroke-linejoin="miter" stroke-width="1" d="M12 35.5h21m-20-4h19m-18-2h17m-17-13h17M11 14h23"/></g></svg>`,
    bB: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 45 45"><g fill="none" fill-rule="evenodd" stroke="#000" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"><g fill="#000" stroke-linecap="butt"><path d="M9 36c3.39-.97 10.11.43 13.5-2 3.39 2.43 10.11 1.03 13.5 2 0 0 1.65.54 3 2-.68.97-1.65.99-3 .5-3.39-.97-10.11.46-13.5-1-3.39 1.46-10.11.03-13.5 1-1.35.49-2.32.47-3-.5 1.35-1.46 3-2 3-2z"/><path d="M15 32c2.5 2.5 12.5 2.5 15 0 .5-1.5 0-2 0-2 0-2.5-2.5-4-2.5-4 5.5-1.5 6-11.5-5-15.5-11 4-10.5 14-5 15.5 0 0-2.5 1.5-2.5 4 0 0-.5.5 0 2z"/><path d="M25 8a2.5 2.5 0 1 1-5 0 2.5 2.5 0 1 1 5 0z"/></g><path stroke="#fff" stroke-linejoin="miter" d="M17.5 26h10M15 30h15m-7.5-14.5v5M20 18h5"/></g></svg>`,
    bN: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 45 45"><g fill="none" fill-rule="evenodd" stroke="#000" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"><path fill="#000" d="M22 10c10.5 1 16.5 8 16 29H15c0-9 10-6.5 8-21"/><path fill="#000" d="M24 18c.38 2.91-5.55 7.37-8 9-3 2-2.82 4.34-5 4-1.042-.94 1.41-3.04 0-3-1 0 .19 1.23-1 2-1 0-4.003 1-4-4 0-2 6-12 6-12s1.89-1.9 2-3.5c-.73-.994-.5-2-.5-3 1-1 3 2.5 3 2.5h2s.78-1.992 2.5-3c1 0 1 3 1 3"/><path fill="#fff" d="M9.5 25.5a.5.5 0 1 1-1 0 .5.5 0 1 1 1 0zm5.433-9.75a.5 1.5 30 1 1-.866-.5.5 1.5 30 1 1 .866.5z"/><path fill="#fff" stroke="#fff" stroke-width="1.5" d="M24.55 10.4l-.45 1.45.5.15c3.15 1 5.65 2.49 7.9 6.75S35.75 29.06 35.25 39l-.05.5h2.25l.05-.5c.5-10.06-.88-16.85-3.25-21.34-2.37-4.49-5.79-6.64-9.19-7.16l-.51-.1z"/></g></svg>`,
    bP: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 45 45"><path fill="#000" stroke="#000" stroke-width="1.5" d="M22.5 9c-2.21 0-4 1.79-4 4 0 .89.29 1.71.78 2.38C17.33 16.5 16 18.59 16 21c0 2.03.94 3.84 2.41 5.03-3 1.06-7.41 5.55-7.41 13.47h23c0-7.92-4.41-12.41-7.41-13.47 1.47-1.19 2.41-3 2.41-5.03 0-2.41-1.33-4.5-3.28-5.62.49-.67.78-1.49.78-2.38 0-2.21-1.79-4-4-4z"/></svg>`,
  };

  // Move tree node class
  class MoveNode {
    constructor(options = {}) {
      this.id = options.id || MoveNode.nextId++;
      this.san = options.san || null;
      this.fen = options.fen;
      this.lastMove = options.lastMove || null;
      this.parent = options.parent || null;
      this.children = []; // Array of MoveNodes (first is mainline, rest are variations)
      this.comments = options.comments || [];
      this.nags = options.nags || [];
      this.ply = options.ply || 0; // Half-move number (0 = initial position)
    }

    // Get move number (1-indexed, for display)
    get moveNumber() {
      return Math.floor((this.ply + 1) / 2);
    }

    // Is this a white move?
    get isWhiteMove() {
      return this.ply % 2 === 1;
    }

    // Add a child move
    addChild(node) {
      node.parent = this;
      this.children.push(node);
      return node;
    }

    // Get sibling variations (alternative moves at this point)
    getSiblings() {
      if (!this.parent) return [];
      return this.parent.children.filter((c) => c !== this);
    }

    // Get index among siblings
    getSiblingIndex() {
      if (!this.parent) return 0;
      return this.parent.children.indexOf(this);
    }

    // Is this the mainline continuation?
    isMainline() {
      if (!this.parent) return true;
      return this.parent.children[0] === this;
    }

    // Get path from root to this node
    getPath() {
      const path = [];
      let node = this;
      while (node) {
        path.unshift(node);
        node = node.parent;
      }
      return path;
    }

    // Get the mainline continuation from this node
    getMainlineContinuation() {
      const moves = [];
      let node = this;
      while (node.children.length > 0) {
        node = node.children[0];
        moves.push(node);
      }
      return moves;
    }
  }
  MoveNode.nextId = 0;

  class PGNViewer {
    constructor(options = {}) {
      this.boardEl = document.getElementById("board");
      this.movesEl = document.getElementById("moves");
      this.pgnInput = document.getElementById("pgn-input");

      this.chess = new Chess();
      this.game = null;
      this.games = [];
      this.rootNode = null; // Root of move tree
      this.currentNode = null; // Currently displayed position
      this.nodeMap = new Map(); // Map of node ID to DOM element
      this.flipped = false;
      this.autoplayInterval = null;
      this.autoplaySpeed = 1000;

      this.initBoard();
      this.initControls();
      this.initKeyboard();
      this.initFileUpload();
      this.loadSampleGame();
    }

    initBoard() {
      this.boardEl.innerHTML = "";

      for (let rank = 0; rank < 8; rank++) {
        for (let file = 0; file < 8; file++) {
          const isLight = (rank + file) % 2 === 0;
          const square = document.createElement("div");
          square.className = `square ${isLight ? "light" : "dark"}`;
          square.dataset.rank = rank;
          square.dataset.file = file;
          this.boardEl.appendChild(square);
        }
      }

      this.updateCoordinates();
    }

    updateCoordinates() {
      const ranksEl = document.querySelector(".coords-ranks");
      const filesEl = document.querySelector(".coords-files");

      ranksEl.innerHTML = "";
      filesEl.innerHTML = "";

      const ranks = this.flipped
        ? ["1", "2", "3", "4", "5", "6", "7", "8"]
        : ["8", "7", "6", "5", "4", "3", "2", "1"];
      const files = this.flipped
        ? ["h", "g", "f", "e", "d", "c", "b", "a"]
        : ["a", "b", "c", "d", "e", "f", "g", "h"];

      for (const r of ranks) {
        const coord = document.createElement("span");
        coord.className = "coord";
        coord.textContent = r;
        ranksEl.appendChild(coord);
      }

      for (const f of files) {
        const coord = document.createElement("span");
        coord.className = "coord";
        coord.textContent = f;
        filesEl.appendChild(coord);
      }
    }

    initControls() {
      document
        .getElementById("btn-first")
        .addEventListener("click", () => this.goToStart());
      document
        .getElementById("btn-prev")
        .addEventListener("click", () => this.prevMove());
      document
        .getElementById("btn-next")
        .addEventListener("click", () => this.nextMove());
      document
        .getElementById("btn-last")
        .addEventListener("click", () => this.goToEnd());
      document
        .getElementById("btn-flip")
        .addEventListener("click", () => this.flipBoard());
      document
        .getElementById("btn-autoplay")
        .addEventListener("click", () => this.toggleAutoplay());
      document
        .getElementById("btn-load")
        .addEventListener("click", () => this.loadPGN());

      document.getElementById("game-select").addEventListener("change", (e) => {
        const index = parseInt(e.target.value, 10);
        if (index >= 0 && index < this.games.length) {
          this.loadGame(this.games[index]);
        }
      });
    }

    initFileUpload() {
      const fileInput = document.getElementById("file-input");

      fileInput.addEventListener("change", (e) => {
        const file = e.target.files[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = (event) => {
          const pgn = event.target.result;
          this.pgnInput.value = pgn;
          this.loadPGNContent(pgn);
        };
        reader.readAsText(file);
        fileInput.value = "";
      });

      const dropZone = document.querySelector(".pgn-input-container");

      dropZone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropZone.classList.add("drag-over");
      });

      dropZone.addEventListener("dragleave", () => {
        dropZone.classList.remove("drag-over");
      });

      dropZone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropZone.classList.remove("drag-over");

        const file = e.dataTransfer.files[0];
        if (
          file &&
          (file.name.endsWith(".pgn") || file.name.endsWith(".txt"))
        ) {
          const reader = new FileReader();
          reader.onload = (event) => {
            const pgn = event.target.result;
            this.pgnInput.value = pgn;
            this.loadPGNContent(pgn);
          };
          reader.readAsText(file);
        }
      });
    }

    initKeyboard() {
      document.addEventListener("keydown", (e) => {
        if (e.target.tagName === "TEXTAREA" || e.target.tagName === "SELECT")
          return;

        switch (e.key) {
          case "ArrowLeft":
            e.preventDefault();
            this.prevMove();
            break;
          case "ArrowRight":
            e.preventDefault();
            this.nextMove();
            break;
          case "ArrowUp":
            e.preventDefault();
            this.prevVariation();
            break;
          case "ArrowDown":
            e.preventDefault();
            this.nextVariation();
            break;
          case "Home":
            e.preventDefault();
            this.goToStart();
            break;
          case "End":
            e.preventDefault();
            this.goToEnd();
            break;
          case "f":
            this.flipBoard();
            break;
          case " ":
            e.preventDefault();
            this.toggleAutoplay();
            break;
        }
      });
    }

    loadPGN() {
      const pgn = this.pgnInput.value.trim();
      if (!pgn) return;
      this.loadPGNContent(pgn);
    }

    loadPGNContent(pgn) {
      const games = PGNParser.parse(pgn);
      if (games.length === 0) return;

      this.games = games;

      const selector = document.getElementById("game-selector");
      const select = document.getElementById("game-select");

      if (games.length > 1) {
        select.innerHTML = "";
        games.forEach((game, index) => {
          const option = document.createElement("option");
          option.value = index;
          const white = game.headers.White || "?";
          const black = game.headers.Black || "?";
          const result = game.result || "*";
          const event = game.headers.Event || "";
          const round = game.headers.Round ? `R${game.headers.Round}` : "";
          option.textContent = `${index + 1}. ${white} vs ${black} ${result}${round ? " " + round : ""}${event ? " - " + event : ""}`;
          select.appendChild(option);
        });
        selector.style.display = "flex";
      } else {
        selector.style.display = "none";
      }

      this.loadGame(games[0]);
    }

    loadSampleGame() {
      // Sample game with variations for testing
      const samplePGN = `[Event "Example with Variations"]
[Site "Demo"]
[Date "2024.01.01"]
[Round "1"]
[White "Player, White"]
[Black "Player, Black"]
[Result "*"]

1. e4 e5 (1... c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 {Sicilian Defense}) (1... e6 2. d4 d5 {French Defense}) 2. Nf3 Nc6 (2... Nf6 {Petrov Defense} 3. Nxe5 d6 4. Nf3 Nxe4) 3. Bb5 (3. Bc4 Bc5 {Italian Game} 4. c3 Nf6 5. d4 exd4 6. cxd4 Bb4+ 7. Nc3) 3... a6 {Morphy Defense} 4. Ba4 Nf6 5. O-O Be7 6. Re1 b5 7. Bb3 d6 8. c3 O-O *`;

      this.pgnInput.value = samplePGN;
      const games = PGNParser.parse(samplePGN);
      if (games.length > 0) {
        this.loadGame(games[0]);
      }
    }

    loadGame(game) {
      this.game = game;
      MoveNode.nextId = 0;
      this.nodeMap.clear();

      // Create root node (starting position)
      this.chess.reset();
      this.rootNode = new MoveNode({
        fen: this.chess.fen(),
        ply: 0,
      });

      // Build move tree from parsed moves
      this.buildMoveTree(this.rootNode, game.moves, this.chess);

      // Update UI
      this.updateGameInfo();
      this.renderMoves();
      this.goToNode(this.rootNode);
    }

    buildMoveTree(parentNode, moves, chess) {
      let currentNode = parentNode;

      for (const moveData of moves) {
        // Save the position BEFORE making this move (for variations)
        const positionBeforeMove = chess.fen();
        const parentForVariations = currentNode;

        // Make the move
        const move = chess.move(moveData.san);
        if (!move) {
          console.warn("Invalid move:", moveData.san);
          continue;
        }

        // Create node for this move
        const node = new MoveNode({
          san: moveData.san,
          fen: chess.fen(),
          lastMove: { from: move.from, to: move.to },
          comments: moveData.comments || [],
          nags: moveData.nags || [],
          ply: currentNode.ply + 1,
        });
        currentNode.addChild(node);

        // Process variations (alternative moves to THIS move)
        // Variations branch from the parent position (before this move was made)
        if (moveData.variations && moveData.variations.length > 0) {
          for (const variation of moveData.variations) {
            // Save current state (after mainline move)
            const savedFen = chess.fen();

            // Go back to position before this move was made
            chess.load(positionBeforeMove);

            // Build variation tree from the parent node
            this.buildMoveTree(parentForVariations, variation, chess);

            // Restore state to continue mainline
            chess.load(savedFen);
          }
        }

        currentNode = node;
      }
    }

    updateGameInfo() {
      const headers = this.game.headers;

      document.getElementById("player-white").textContent =
        headers.White || "White";
      document.getElementById("player-black").textContent =
        headers.Black || "Black";
      document.getElementById("rating-white").textContent = headers.WhiteElo
        ? `(${headers.WhiteElo})`
        : "";
      document.getElementById("rating-black").textContent = headers.BlackElo
        ? `(${headers.BlackElo})`
        : "";

      const metaEl = document.getElementById("game-meta");
      metaEl.innerHTML = "";

      if (headers.Event) {
        const span = document.createElement("span");
        span.textContent = headers.Event;
        metaEl.appendChild(span);
      }
      if (headers.Date) {
        const span = document.createElement("span");
        span.textContent = headers.Date;
        metaEl.appendChild(span);
      }
      if (headers.ECO) {
        const span = document.createElement("span");
        span.textContent = headers.ECO;
        metaEl.appendChild(span);
      }
    }

    renderMoves() {
      this.movesEl.innerHTML = "";
      this.nodeMap.clear();

      if (!this.rootNode) return;

      // Render the move tree starting from root
      this.renderMoveTree(this.rootNode, this.movesEl, true);

      // Add result
      if (this.game.result && this.game.result !== "*") {
        const resultDiv = document.createElement("div");
        resultDiv.className = "game-result";
        resultDiv.textContent = this.game.result;
        this.movesEl.appendChild(resultDiv);
      }
    }

    renderMoveTree(node, container, isMainline) {
      // If this is the root, start rendering children
      if (!node.san) {
        for (let i = 0; i < node.children.length; i++) {
          if (i === 0) {
            this.renderMoveTree(node.children[i], container, true);
          } else {
            // Root-level alternatives (rare, but handle them)
            const varDiv = document.createElement("div");
            varDiv.className = "variation";
            this.renderMoveTree(node.children[i], varDiv, false);
            container.appendChild(varDiv);
          }
        }
        return;
      }

      // Create move element
      const moveSpan = document.createElement("span");
      moveSpan.className = `move ${isMainline ? "mainline" : "variation-move"}`;
      moveSpan.dataset.nodeId = node.id;

      // Add move number if needed
      const needsMoveNumber =
        node.isWhiteMove ||
        (node.parent && node.parent.children.indexOf(node) > 0) ||
        (node.parent && !node.parent.san);

      if (needsMoveNumber) {
        const numSpan = document.createElement("span");
        numSpan.className = "move-number";
        numSpan.textContent =
          node.moveNumber + (node.isWhiteMove ? ". " : "... ");
        moveSpan.appendChild(numSpan);
      }

      // Add move text
      const sanSpan = document.createElement("span");
      sanSpan.className = "move-san";
      sanSpan.textContent = node.san;
      moveSpan.appendChild(sanSpan);

      // Add NAG symbols
      if (node.nags && node.nags.length > 0) {
        for (const nag of node.nags) {
          const symbol = Chess.NAGS[nag];
          if (symbol) {
            const nagSpan = document.createElement("span");
            nagSpan.className = "nag";
            nagSpan.textContent = symbol;
            moveSpan.appendChild(nagSpan);
          }
        }
      }

      // Mark if has variations
      if (node.parent && node.parent.children.length > 1) {
        moveSpan.classList.add("has-variations");
      }

      moveSpan.addEventListener("click", () => this.goToNode(node));
      container.appendChild(moveSpan);
      this.nodeMap.set(node.id, moveSpan);

      // Add comments
      if (node.comments && node.comments.length > 0) {
        for (const comment of node.comments) {
          const commentSpan = document.createElement("span");
          commentSpan.className = "comment";
          commentSpan.textContent = " " + comment + " ";
          container.appendChild(commentSpan);
        }
      }

      // Render variations (alternative continuations from parent)
      if (
        node.parent &&
        node.parent.children.length > 1 &&
        node.parent.children[0] === node
      ) {
        // Render sibling variations inline after mainline move
        for (let i = 1; i < node.parent.children.length; i++) {
          const variation = node.parent.children[i];
          const varDiv = document.createElement("span");
          varDiv.className = "variation inline";

          // Opening paren
          const openParen = document.createElement("span");
          openParen.className = "variation-bracket";
          openParen.textContent = "(";
          varDiv.appendChild(openParen);

          // Render variation moves
          this.renderVariationLine(variation, varDiv);

          // Closing paren
          const closeParen = document.createElement("span");
          closeParen.className = "variation-bracket";
          closeParen.textContent = ")";
          varDiv.appendChild(closeParen);

          container.appendChild(varDiv);
        }
      }

      // Continue with mainline children
      if (node.children.length > 0) {
        // Add space before next move
        container.appendChild(document.createTextNode(" "));

        // Render first child (mainline continuation)
        this.renderMoveTree(node.children[0], container, isMainline);
      }
    }

    renderVariationLine(node, container) {
      // Render a node and its mainline continuation within a variation
      const moveSpan = document.createElement("span");
      moveSpan.className = "move variation-move";
      moveSpan.dataset.nodeId = node.id;

      // Move number
      const numSpan = document.createElement("span");
      numSpan.className = "move-number";
      numSpan.textContent = node.moveNumber + (node.isWhiteMove ? "." : "...");
      moveSpan.appendChild(numSpan);

      // Move text
      const sanSpan = document.createElement("span");
      sanSpan.className = "move-san";
      sanSpan.textContent = node.san;
      moveSpan.appendChild(sanSpan);

      // NAGs
      if (node.nags && node.nags.length > 0) {
        for (const nag of node.nags) {
          const symbol = Chess.NAGS[nag];
          if (symbol) {
            const nagSpan = document.createElement("span");
            nagSpan.className = "nag";
            nagSpan.textContent = symbol;
            moveSpan.appendChild(nagSpan);
          }
        }
      }

      moveSpan.addEventListener("click", (e) => {
        e.stopPropagation();
        this.goToNode(node);
      });
      container.appendChild(moveSpan);
      this.nodeMap.set(node.id, moveSpan);

      // Comments
      if (node.comments && node.comments.length > 0) {
        for (const comment of node.comments) {
          const commentSpan = document.createElement("span");
          commentSpan.className = "comment";
          commentSpan.textContent = " " + comment + " ";
          container.appendChild(commentSpan);
        }
      }

      // Nested variations
      if (node.children.length > 1) {
        for (let i = 1; i < node.children.length; i++) {
          const nestedVar = document.createElement("span");
          nestedVar.className = "variation nested";
          nestedVar.textContent = "(";
          this.renderVariationLine(node.children[i], nestedVar);
          nestedVar.appendChild(document.createTextNode(")"));
          container.appendChild(nestedVar);
        }
      }

      // Continue mainline of variation
      if (node.children.length > 0) {
        container.appendChild(document.createTextNode(" "));
        this.renderVariationLine(node.children[0], container);
      }
    }

    renderBoard() {
      if (!this.currentNode) return;

      const tempChess = new Chess(this.currentNode.fen);
      const board = tempChess.board2D();

      const squares = this.boardEl.querySelectorAll(".square");

      // Collect alternative moves to display on board
      const altMovesBySquare = this.getAlternativeMovesBySquare();

      for (let i = 0; i < 64; i++) {
        const square = squares[i];
        const rank = Math.floor(i / 8);
        const file = i % 8;

        const actualRank = this.flipped ? 7 - rank : rank;
        const actualFile = this.flipped ? 7 - file : file;
        const squareIdx = actualRank * 8 + actualFile;

        // Clear square
        const existingPiece = square.querySelector(".piece");
        if (existingPiece) existingPiece.remove();
        const existingAltMoves = square.querySelector(".alt-moves");
        if (existingAltMoves) existingAltMoves.remove();

        // Reset highlight classes
        square.classList.remove(
          "highlight-last",
          "highlight-check",
          "alt-source",
        );

        // Last move highlight
        if (this.currentNode.lastMove) {
          const fromIdx = this.currentNode.lastMove.from;
          const toIdx = this.currentNode.lastMove.to;
          const fromRank = Math.floor(fromIdx / 8);
          const fromFile = fromIdx % 8;
          const toRank = Math.floor(toIdx / 8);
          const toFile = toIdx % 8;

          if (
            (actualRank === fromRank && actualFile === fromFile) ||
            (actualRank === toRank && actualFile === toFile)
          ) {
            square.classList.add("highlight-last");
          }
        }

        // Add piece
        const piece = board[actualRank][actualFile];
        if (piece) {
          const pieceEl = document.createElement("div");
          pieceEl.className = "piece";
          const pieceKey =
            (piece.color === "w" ? "w" : "b") + piece.type.toUpperCase();
          pieceEl.innerHTML = PIECE_SVGS[pieceKey];
          square.appendChild(pieceEl);

          // Check highlight
          if (piece.type === "k" && tempChess.inCheck()) {
            square.classList.add("highlight-check");
          }
        }

        // Add alternative move indicators on destination squares
        if (altMovesBySquare.has(squareIdx)) {
          const altMovesContainer = document.createElement("div");
          altMovesContainer.className = "alt-moves";

          const moves = altMovesBySquare.get(squareIdx);
          for (const moveInfo of moves) {
            const altMoveEl = document.createElement("span");
            altMoveEl.className = `alt-move ${moveInfo.isMainline ? "mainline" : "variation"}`;
            altMoveEl.textContent = moveInfo.san;
            altMoveEl.title = moveInfo.isMainline ? "Main line" : "Variation";
            altMoveEl.addEventListener("click", (e) => {
              e.stopPropagation();
              this.goToNode(moveInfo.node);
            });
            altMovesContainer.appendChild(altMoveEl);
          }

          square.appendChild(altMovesContainer);
        }
      }

      // Update active move highlighting
      this.nodeMap.forEach((el, id) => {
        el.classList.remove("active");
      });

      if (this.currentNode.san) {
        const activeEl = this.nodeMap.get(this.currentNode.id);
        if (activeEl) {
          activeEl.classList.add("active");
          activeEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }
      }

      // Update comment panel
      this.updateCommentPanel();
    }

    getAlternativeMovesBySquare() {
      const movesBySquare = new Map();

      if (!this.currentNode || this.currentNode.children.length === 0) {
        return movesBySquare;
      }

      // Get all child moves (continuations from current position)
      // Use a Set to avoid duplicate SANs (same move shouldn't appear twice)
      const seenMoves = new Set();

      for (let i = 0; i < this.currentNode.children.length; i++) {
        const child = this.currentNode.children[i];
        if (child.lastMove && !seenMoves.has(child.san)) {
          seenMoves.add(child.san);
          const toSquare = child.lastMove.to;

          if (!movesBySquare.has(toSquare)) {
            movesBySquare.set(toSquare, []);
          }

          movesBySquare.get(toSquare).push({
            san: child.san,
            node: child,
            isMainline: i === 0,
          });
        }
      }

      return movesBySquare;
    }

    updateCommentPanel() {
      const commentPanel = document.getElementById("comment-panel");
      if (!commentPanel) return;

      commentPanel.innerHTML = "";

      if (
        this.currentNode &&
        this.currentNode.comments &&
        this.currentNode.comments.length > 0
      ) {
        commentPanel.textContent = this.currentNode.comments.join(" ");
      }
    }

    goToNode(node) {
      this.currentNode = node;
      this.renderBoard();
    }

    goToStart() {
      this.goToNode(this.rootNode);
    }

    goToEnd() {
      // Go to the end of the current line
      let node = this.currentNode;
      while (node.children.length > 0) {
        node = node.children[0];
      }
      this.goToNode(node);
    }

    nextMove() {
      if (this.currentNode.children.length > 0) {
        this.goToNode(this.currentNode.children[0]);
      } else if (this.autoplayInterval) {
        this.stopAutoplay();
      }
    }

    prevMove() {
      if (this.currentNode.parent) {
        this.goToNode(this.currentNode.parent);
      }
    }

    // Navigate to previous variation (sibling)
    prevVariation() {
      if (!this.currentNode.parent) return;

      const siblings = this.currentNode.parent.children;
      const currentIdx = siblings.indexOf(this.currentNode);

      if (currentIdx > 0) {
        this.goToNode(siblings[currentIdx - 1]);
      }
    }

    // Navigate to next variation (sibling)
    nextVariation() {
      if (!this.currentNode.parent) return;

      const siblings = this.currentNode.parent.children;
      const currentIdx = siblings.indexOf(this.currentNode);

      if (currentIdx < siblings.length - 1) {
        this.goToNode(siblings[currentIdx + 1]);
      }
    }

    flipBoard() {
      this.flipped = !this.flipped;
      this.updateCoordinates();
      this.renderBoard();

      if (this.flipped) {
        document.getElementById("player-black").textContent =
          this.game?.headers?.White || "White";
        document.getElementById("rating-black").textContent = this.game?.headers
          ?.WhiteElo
          ? `(${this.game.headers.WhiteElo})`
          : "";
        document.getElementById("player-white").textContent =
          this.game?.headers?.Black || "Black";
        document.getElementById("rating-white").textContent = this.game?.headers
          ?.BlackElo
          ? `(${this.game.headers.BlackElo})`
          : "";
      } else {
        document.getElementById("player-black").textContent =
          this.game?.headers?.Black || "Black";
        document.getElementById("rating-black").textContent = this.game?.headers
          ?.BlackElo
          ? `(${this.game.headers.BlackElo})`
          : "";
        document.getElementById("player-white").textContent =
          this.game?.headers?.White || "White";
        document.getElementById("rating-white").textContent = this.game?.headers
          ?.WhiteElo
          ? `(${this.game.headers.WhiteElo})`
          : "";
      }
    }

    toggleAutoplay() {
      if (this.autoplayInterval) {
        this.stopAutoplay();
      } else {
        this.startAutoplay();
      }
    }

    startAutoplay() {
      document.getElementById("icon-play").style.display = "none";
      document.getElementById("icon-pause").style.display = "block";

      this.autoplayInterval = setInterval(() => {
        this.nextMove();
      }, this.autoplaySpeed);
    }

    stopAutoplay() {
      document.getElementById("icon-play").style.display = "block";
      document.getElementById("icon-pause").style.display = "none";

      if (this.autoplayInterval) {
        clearInterval(this.autoplayInterval);
        this.autoplayInterval = null;
      }
    }
  }

  return PGNViewer;
})();

// Initialize viewer when DOM is ready
document.addEventListener("DOMContentLoaded", () => {
  window.viewer = new PGNViewer();
});
