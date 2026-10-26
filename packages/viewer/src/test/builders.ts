import { crc32 } from "../data/qct";

type Typed = Uint8Array | Int8Array | Uint16Array | Int16Array | Uint32Array | Int32Array | Float32Array;

const DTYPE = new Map<unknown, string>([
  [Uint8Array, "u8"],
  [Int8Array, "i8"],
  [Uint16Array, "u16"],
  [Int16Array, "i16"],
  [Uint32Array, "u32"],
  [Int32Array, "i32"],
  [Float32Array, "f32"],
]);

/** Encode fields as a QCT1 chunk, the way the pipeline writes them. */
export function encodeChunk(key: string, kind: string, fields: Record<string, Typed>): ArrayBuffer {
  let offset = 0;
  const layout = Object.entries(fields).map(([n, arr]) => {
    const size = arr.BYTES_PER_ELEMENT;
    offset = Math.ceil(offset / 8) * 8;
    const entry = { n, t: DTYPE.get(arr.constructor) ?? "u8", o: offset, c: arr.length, arr, size };
    offset += arr.length * size;
    return entry;
  });
  const payload = new Uint8Array(offset);
  for (const f of layout) payload.set(new Uint8Array(f.arr.buffer, f.arr.byteOffset, f.arr.byteLength), f.o);
  const header = new TextEncoder().encode(
    JSON.stringify({ k: key, kind, fields: layout.map(({ n, t, o, c }) => ({ n, t, o, c })) }),
  );
  const start = Math.ceil((16 + header.length) / 8) * 8;
  const out = new Uint8Array(start + payload.length);
  const view = new DataView(out.buffer);
  out.set([0x51, 0x43, 0x54, 0x31]);
  view.setUint32(4, header.length, true);
  view.setUint32(8, payload.length, true);
  view.setUint32(12, crc32(payload), true);
  out.set(header, 16);
  out.set(payload, start);
  return out.buffer;
}

/**
 * Two square blocks for picker and loader tests: "A" is 100 m wide at the
 * origin on flat ground; "B", the same size, sits just south of it on a 30 m
 * rise, so on the painted plane the rise hides the south edge of "A".
 */
export function twoBlocks(): ArrayBuffer {
  const square = (size: number) => [0, 0, size, 0, size, size, 0, size];
  const a = square(1000);
  const b = square(1000);
  return encodeChunk("base/blocks", "blocks", {
    cnt: new Uint16Array([4, 4]),
    sc: new Uint8Array([0, 0]),
    ox: new Float32Array([0, 0]),
    oy: new Float32Array([0, -100]),
    vx: new Int16Array([...a.filter((_, i) => i % 2 === 0), ...b.filter((_, i) => i % 2 === 0)]),
    vy: new Int16Array([...a.filter((_, i) => i % 2 === 1), ...b.filter((_, i) => i % 2 === 1)]),
    z: new Uint16Array([0, 300]),
    a: new Float32Array([10000, 10000]),
    hood: new Uint8Array([0, 255]),
    bidx: new Uint8Array([0, 0]),
  });
}

/** A fetch that answers from a table of URLs; anything else is a 404. */
export function fakeFetch(routes: Record<string, unknown>): typeof fetch {
  return (input: string | URL | Request) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    if (!(url in routes)) return Promise.resolve(new Response("missing", { status: 404 }));
    const body = routes[url];
    if (body instanceof ArrayBuffer) return Promise.resolve(new Response(body));
    return Promise.resolve(
      new Response(JSON.stringify(body), { headers: { "content-type": "application/json" } }),
    );
  };
}
