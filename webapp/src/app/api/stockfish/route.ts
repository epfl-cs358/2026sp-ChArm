import { NextRequest, NextResponse } from "next/server";
import initEngine from "stockfish";

interface StockfishEngine {
  listener?: (line: string) => void;
  sendCommand(command: string): void;
}

let enginePromise: Promise<StockfishEngine> | null = null;

function getEngine() {
  if (!enginePromise) {
    enginePromise = initEngine("lite-single") as Promise<StockfishEngine>;
  }
  return enginePromise;
}

function findBestMove(engine: StockfishEngine, fen: string, depth: number) {
  return new Promise<string>((resolve, reject) => {
    const timeout = setTimeout(() => {
      engine.listener = undefined;
      reject(new Error("Stockfish timeout"));
    }, 5000);

    engine.listener = (line: string) => {
      if (!line.startsWith("bestmove ")) return;
      clearTimeout(timeout);
      engine.listener = undefined;
      const bestMove = line.split(/\s+/)[1];
      if (!bestMove || bestMove === "(none)") {
        reject(new Error("Stockfish returned no move"));
        return;
      }
      resolve(bestMove);
    };

    engine.sendCommand("ucinewgame");
    engine.sendCommand(`position fen ${fen}`);
    engine.sendCommand(`go depth ${depth}`);
  });
}

export async function POST(request: NextRequest) {
  const body = (await request.json().catch(() => null)) as { fen?: string; depth?: number } | null;
  if (!body?.fen) {
    return NextResponse.json({ error: "Missing fen" }, { status: 400 });
  }

  const engine = await getEngine();
  const bestMove = await findBestMove(engine, body.fen, Math.min(Math.max(body.depth ?? 8, 1), 12));
  return NextResponse.json({ bestMove });
}
