import { afterEach, describe, expect, it, vi } from "vitest";
import { zeile } from "./ablauf";
import { HEARTBEAT_MS, Modell, type Status } from "./seriell";

// A port that records what the page writes and lets the test play the board.
function fakePort() {
  const written: string[] = [];
  let board!: ReadableStreamDefaultController<Uint8Array>;
  const port = {
    opened: 0,
    closed: 0,
    readable: null as ReadableStream<Uint8Array> | null,
    writable: null as WritableStream<Uint8Array> | null,
    async open() {
      port.opened++;
      port.readable = new ReadableStream<Uint8Array>({ start: (c) => { board = c; } });
      port.writable = new WritableStream<Uint8Array>({ write: (chunk) => { written.push(new TextDecoder().decode(chunk)); } });
    },
    async close() { port.closed++; },
    say(text: string) { board.enqueue(new TextEncoder().encode(text)); },
    pull() { board.error(new Error("cable pulled")); },
  };
  return { port, written };
}

function fakeSerial(granted: unknown[]) {
  const serial = new EventTarget() as EventTarget & Record<string, unknown>;
  serial.getPorts = async () => granted;
  serial.requestPort = async () => granted[0];
  return serial;
}

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

afterEach(() => vi.unstubAllGlobals());

describe("Modell (Web Serial link)", () => {
  it("reports unsupported without navigator.serial", async () => {
    vi.stubGlobal("navigator", {});
    const seen: Status[] = [];
    await new Modell((s) => seen.push(s)).start();
    expect(seen).toEqual(["unsupported"]);
  });

  it("reopens a granted port, sends the heartbeat and counts as connected only after a reply", async () => {
    const { port, written } = fakePort();
    vi.stubGlobal("navigator", { serial: fakeSerial([port]) });
    const seen: Status[] = [];
    const m = new Modell((s) => seen.push(s));
    await m.start();
    expect(port.opened).toBe(1);
    expect(m.status).toBe("connecting");

    m.senden("S 53");
    await wait(HEARTBEAT_MS * 2 + 60);
    expect(written[0]).toBe(zeile("R"));
    expect(written.filter((l) => l === zeile("S 53")).length).toBeGreaterThanOrEqual(3);
    expect(m.status).toBe("connecting");

    port.say("remote S 5");
    port.say("3\r\n");
    await wait(10);
    expect(m.status).toBe("connected");
    expect(m.log.at(-1)).toMatch(/ remote S 53$/);
    expect(seen).toEqual(["connecting", "connected"]);

    port.pull();
    await wait(20);
    expect(m.status).toBe("disconnected");
    expect(port.closed).toBe(1);
    const n = written.length;
    await wait(HEARTBEAT_MS + 50);
    expect(written.length).toBe(n);
  });

  it("reconnects when the cable comes back", async () => {
    const { port } = fakePort();
    const serial = fakeSerial([]);
    vi.stubGlobal("navigator", { serial });
    const m = new Modell();
    await m.start();
    expect(m.status).toBe("disconnected");
    const ev = new Event("connect");
    Object.defineProperty(ev, "target", { value: port });
    serial.dispatchEvent(ev);
    await wait(10);
    expect(port.opened).toBe(1);
    expect(m.status).toBe("connecting");
  });

  it("sends the act clock with the heartbeat, not with every frame", async () => {
    const { port, written } = fakePort();
    vi.stubGlobal("navigator", { serial: fakeSerial([port]) });
    const m = new Modell();
    await m.start();
    await wait(10);
    const before = written.length;
    for (let ms = 0; ms < 100; ms += 16) m.senden(`A ${ms}`);
    await wait(10);
    // one line for the switch from R to A, the later frames wait for the heartbeat
    expect(written.slice(before)).toEqual([zeile("A 0")]);
    await wait(HEARTBEAT_MS);
    expect(written.at(-1)).toBe(zeile("A 96"));
  });

  it("asks for granted ports only once when start() runs twice", async () => {
    const serial = fakeSerial([]);
    let asked = 0;
    serial.getPorts = async () => { asked++; return []; };
    vi.stubGlobal("navigator", { serial });
    const m = new Modell();
    await m.start();
    await m.start();
    expect(asked).toBe(1);
  });

  it("gives up cleanly when the opened port has no streams", async () => {
    const { port } = fakePort();
    port.open = async () => { port.opened++; };
    vi.stubGlobal("navigator", { serial: fakeSerial([port]) });
    const m = new Modell();
    await m.start();
    expect(m.status).toBe("disconnected");
    expect(port.closed).toBe(1);
  });

  it("does not let a late write failure of an old port close the new one", async () => {
    const slow = fakePort().port;
    let fail!: (e: Error) => void;
    slow.open = async () => {
      slow.opened++;
      slow.readable = new ReadableStream<Uint8Array>();
      slow.writable = new WritableStream<Uint8Array>({
        write: () => new Promise<void>((_, reject) => { fail = reject; }),
      });
    };
    const { port: fresh } = fakePort();
    const serial = fakeSerial([slow]);
    vi.stubGlobal("navigator", { serial });
    const m = new Modell();
    await m.start();
    await wait(10);

    const gone = new Event("disconnect");
    Object.defineProperty(gone, "target", { value: slow });
    serial.dispatchEvent(gone);
    await wait(10);
    const back = new Event("connect");
    Object.defineProperty(back, "target", { value: fresh });
    serial.dispatchEvent(back);
    await wait(10);
    expect(fresh.opened).toBe(1);

    fail(new Error("old write failed late"));
    await wait(20);
    expect(fresh.closed).toBe(0);
    expect(m.status).toBe("connecting");
  });
});
