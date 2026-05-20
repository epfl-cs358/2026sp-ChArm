declare module "stockfish" {
  interface StockfishEngine {
    listener?: (line: string) => void;
    sendCommand(command: string): void;
  }

  export default function initEngine(engine?: string): Promise<StockfishEngine>;
}
