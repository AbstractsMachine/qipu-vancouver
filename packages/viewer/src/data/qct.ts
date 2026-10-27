import { FormatError, list, natural, record, str } from "./validate";

/**
 * QCT1, the city data's binary chunk container:
 *
 *   0   4  magic "QCT1"
 *   4   4  u32 header length H
 *   8   4  u32 payload length P
 *   12  4  u32 CRC-32 of the payload
 *   16  H  header JSON {k, kind, fields: [{n, t, o, c}]}
 *   ... zero padding to a multiple of 8, then the payload
 *
 * Fields are little-endian typed arrays at byte offset `o` into the payload,
 * `c` elements each. The magic and the CRC are checked before anything is
 * read, so an HTML error page or a truncated download throws instead of
 * decoding into plausible numbers.
 */
export type FieldArray = Uint8Array | Int8Array | Uint16Array | Int16Array | Uint32Array | Int32Array | Float32Array;

export interface Chunk {
  readonly key: string;
  readonly kind: string;
  readonly fields: ReadonlyMap<string, FieldArray>;
}

const ARRAYS = {
  u8: Uint8Array,
  i8: Int8Array,
  u16: Uint16Array,
  i16: Int16Array,
  u32: Uint32Array,
  i32: Int32Array,
  f32: Float32Array,
} as const;

type DType = keyof typeof ARRAYS;

const isDType = (t: string): t is DType => t in ARRAYS;

export function decodeChunk(buffer: ArrayBuffer): Chunk {
  if (buffer.byteLength < 16) throw new FormatError("chunk", "at least 16 bytes");
  const view = new DataView(buffer);
  const magic = String.fromCharCode(view.getUint8(0), view.getUint8(1), view.getUint8(2), view.getUint8(3));
  if (magic !== "QCT1") throw new FormatError("chunk", 'the magic "QCT1"');
  const headerLength = view.getUint32(4, true);
  const payloadLength = view.getUint32(8, true);
  const crc = view.getUint32(12, true);
  const payloadStart = align8(16 + headerLength);
  if (payloadStart + payloadLength > buffer.byteLength) throw new FormatError("chunk", "a complete payload");

  const payload = new Uint8Array(buffer, payloadStart, payloadLength);
  if (crc32(payload) !== crc) throw new FormatError("chunk", "a payload matching its CRC-32");

  const header = record(JSON.parse(new TextDecoder().decode(new Uint8Array(buffer, 16, headerLength))), "chunk.header");
  const fields = new Map<string, FieldArray>();
  list(header.fields, "chunk.header.fields").forEach((f, i) => {
    const p = `chunk.header.fields[${i}]`;
    const field = record(f, p);
    const t = str(field.t, `${p}.t`);
    if (!isDType(t)) throw new FormatError(`${p}.t`, `a dtype (got "${t}")`);
    const Ctor = ARRAYS[t];
    const offset = natural(field.o, `${p}.o`);
    const count = natural(field.c, `${p}.c`);
    if (offset % Ctor.BYTES_PER_ELEMENT !== 0 || offset + count * Ctor.BYTES_PER_ELEMENT > payloadLength) {
      throw new FormatError(p, "an aligned field inside the payload");
    }
    fields.set(str(field.n, `${p}.n`), new Ctor(buffer, payloadStart + offset, count));
  });
  return { key: str(header.k, "chunk.header.k"), kind: str(header.kind, "chunk.header.kind"), fields };
}

const align8 = (n: number): number => (n + 7) & ~7;

let table: Uint32Array | null = null;

/** CRC-32/IEEE, the checksum zlib and Python's `zlib.crc32` compute. */
export function crc32(bytes: Uint8Array): number {
  if (!table) {
    table = new Uint32Array(256);
    for (let n = 0; n < 256; n++) {
      let c = n;
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      table[n] = c >>> 0;
    }
  }
  let c = 0xffffffff;
  for (let i = 0; i < bytes.length; i++) c = (table[(c ^ (bytes[i] as number)) & 0xff] as number) ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}
