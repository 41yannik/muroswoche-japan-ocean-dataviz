// USB link to the model (Web Serial, Chrome only). The page leads: it sends the
// current command every HEARTBEAT_MS; the sketch falls back to its own loop
// after 5 s without a valid line. Without a board the page runs unchanged.
import { zeile } from "./ablauf";

export const HEARTBEAT_MS = 250;
const BAUD = 115200;
const LOG_LINES = 200;

// Minimal Web Serial types (not part of lib.dom in TypeScript 5.9).
interface SerialPortLike {
  open(options: { baudRate: number }): Promise<void>;
  close(): Promise<void>;
  readable: ReadableStream<Uint8Array> | null;
  writable: WritableStream<Uint8Array> | null;
}
interface SerialLike extends EventTarget {
  getPorts(): Promise<SerialPortLike[]>;
  requestPort(): Promise<SerialPortLike>;
}

export type Status = "unsupported" | "disconnected" | "connecting" | "connected";

export class Modell {
  status: Status = "disconnected";
  /** Last lines from the board, newest last (for the rehearsal log). */
  readonly log: string[] = [];
  private port: SerialPortLike | null = null;
  private writer: WritableStreamDefaultWriter<Uint8Array> | null = null;
  private reader: ReadableStreamDefaultReader<Uint8Array> | null = null;
  private command = "R";
  private timer: ReturnType<typeof setInterval> | null = null;
  private readonly encoder = new TextEncoder();
  private readonly serial: SerialLike | null;
  private started = false;

  constructor(private readonly onStatus: (s: Status) => void = () => {}) {
    const nav = (globalThis as { navigator?: { serial?: SerialLike } }).navigator;
    this.serial = nav?.serial ?? null;
  }

  /** Reconnects to a port granted earlier and watches for replugging. */
  async start(): Promise<void> {
    if (!this.serial) return this.setStatus("unsupported");
    if (this.started) return;
    this.started = true;
    this.serial.addEventListener("connect", (e) => {
      if (!this.port) void this.open((e.target as unknown) as SerialPortLike);
    });
    this.serial.addEventListener("disconnect", (e) => {
      if ((e.target as unknown) === this.port) void this.drop();
    });
    const [granted] = await this.serial.getPorts();
    if (granted) await this.open(granted);
  }

  /** Needs a click: Chrome asks which port to grant. */
  async verbinden(): Promise<void> {
    if (!this.serial) return;
    try {
      await this.open(await this.serial.requestPort());
    } catch {
      // the visitor closed the dialog
    }
  }

  /** Sets the command; it goes out at once and then with every heartbeat. */
  senden(cmd: string): void {
    if (cmd === this.command) return;
    // the act clock (A <ms>) changes every frame; the heartbeat carries it, only a new kind goes out at once
    const sofort = cmd[0] !== "A" || this.command[0] !== "A";
    this.command = cmd;
    if (sofort) void this.write();
  }

  private async open(port: SerialPortLike): Promise<void> {
    if (this.port) return;
    this.port = port;
    this.setStatus("connecting");
    let reader: ReadableStreamDefaultReader<Uint8Array>;
    try {
      await port.open({ baudRate: BAUD });
      // both streams can be missing or still locked right after a replug
      if (!port.readable || !port.writable) throw new Error("streams not ready");
      this.writer = port.writable.getWriter();
      reader = port.readable.getReader();
    } catch {
      await this.drop();
      return;
    }
    this.reader = reader;
    void this.readLoop(port, reader);
    void this.write();
    this.timer = setInterval(() => void this.write(), HEARTBEAT_MS);
  }

  private async readLoop(port: SerialPortLike, reader: ReadableStreamDefaultReader<Uint8Array>): Promise<void> {
    const decoder = new TextDecoder();
    let rest = "";
    try {
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        rest += decoder.decode(value, { stream: true });
        let nl: number;
        while ((nl = rest.indexOf("\n")) >= 0) {
          const line = rest.slice(0, nl).replace(/\r$/, "");
          rest = rest.slice(nl + 1);
          if (!line) continue;
          this.log.push(`${Date.now()} ${line}`);
          if (this.log.length > LOG_LINES) this.log.shift();
          // connected only once the board has answered
          if (this.status !== "connected") this.setStatus("connected");
        }
      }
    } catch {
      // cable pulled; the disconnect event or the next write cleans up
    }
    if (this.port === port) await this.drop();
  }

  private async write(): Promise<void> {
    const writer = this.writer;
    if (!writer) return;
    try {
      await writer.write(this.encoder.encode(zeile(this.command)));
    } catch {
      // a late failure of an old session must not close a newer one
      if (this.writer === writer) await this.drop();
    }
  }

  private async drop(): Promise<void> {
    const port = this.port;
    if (!port) return;
    this.port = null;
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
    try { await this.reader?.cancel(); } catch { /* already gone */ }
    try { this.reader?.releaseLock(); } catch { /* already gone */ }
    try { this.writer?.releaseLock(); } catch { /* already gone */ }
    this.reader = null;
    this.writer = null;
    try { await port.close(); } catch { /* already gone */ }
    this.setStatus("disconnected");
  }

  private setStatus(s: Status): void {
    if (s === this.status) return;
    this.status = s;
    this.onStatus(s);
  }
}
